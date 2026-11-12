#!/usr/bin/env python3
"""C 流 · 字体 QA：表完整性 / 空字形 / bbox / cmap 一致性 / 孔洞（对照宋体）/ 渲染检查。

思路改造自 guangeti 13_qa.py（覆盖/空字形/contact sheet）与 71_holes.py（孔洞审计）：
  - 本 demo 只映射真迹字，不做 20,992 假覆盖，所以 cmap 覆盖断言改为
    「cmap == manifest 字表」；
  - 孔洞对照基准用系统宋体（Songti TC），仅报告不硬判（刻本与宋体笔形不同，
    丢失量级才是信号）；`lost` 单列；
  - 自交/形状问题用「PIL 256px 渲染 + 连通分量/墨量/孔洞」做粗检，最终目检 specimen。

用法：
  .venv/bin/python scripts/font_qa.py --font work/font/demo/KangXiKai-demo-v0.1.0.ttf \
      --manifest work/font/demo/manifest.json --outdir work/font/qa
"""



from __future__ import annotations


# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"
sys.path.insert(0, str(WORK / "_pylibs"))

REQUIRED_TABLES = ["glyf", "loca", "cmap", "head", "hhea", "hmtx", "maxp", "name",
                   "OS/2", "post"]
SIZES = (256, 96, 48)
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"


def holes_of(mask: np.ndarray) -> int:
    import cv2
    out = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hier = out[-1]
    if hier is None:
        return 0
    return int(sum(1 for h in hier[0] if h[3] != -1))


def n_components(mask: np.ndarray) -> int:
    import cv2
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    return int(sum(1 for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 4))


def soft_flag(ch: str, mask: np.ndarray) -> dict:
    """字形级软标志：细碎成分（细化率）/ 主体外挂残段（审计2 P1-3 路/蹋 类）。

    指标：
      - thin_comps：面积>=2%主成分、且最粗处 <0.5×主成分最粗处的成分数（蹋 类细丝）；
      - frag_frac ：面积<5%主成分的碎片面积占比（碎屑）。
    触发：thin_comps>=2 或 frag_frac>0.30。仅记录，不硬判。
    """
    import cv2
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    comps = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 10:
            continue
        m = (lab == i).astype(np.uint8)
        dt = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        comps.append((area, float(dt.max())))
    if not comps:
        return {"char": ch, "flags": []}
    comps.sort(reverse=True)
    main_area, main_dt = comps[0]
    total = sum(c[0] for c in comps)
    frag_area = sum(c[0] for c in comps[1:] if c[0] < 0.05 * main_area)
    thin = sum(1 for area, d in comps[1:] if area >= 0.02 * main_area and d < 0.5 * main_dt)
    flags = []
    if thin >= 2:
        flags.append(f"thin_comps={thin}")
    if total and frag_area / total > 0.30:
        flags.append(f"frag_frac={frag_area/total:.2f}")
    return {"char": ch, "flags": flags, "n_comp": len(comps),
            "thin_comps": thin, "frag_frac": round(frag_area / total, 3) if total else 0}


def n_line_like(mask: np.ndarray) -> int:
    """细长直线状组件数（框线/栏线残片特征）：短边<=3px 且 长边>=40px（256px 渲染）。"""
    import cv2
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    cnt = 0
    for i in range(1, n):
        w, h, a = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT], st[i, cv2.CC_STAT_AREA]
        if a < 8:
            continue
        if min(w, h) <= 3 and max(w, h) >= 40:
            cnt += 1
    return cnt


def raster_glyph(ch: str, font_path: str, size: int, index: int | None = None,
                 top: float = 880.0) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    if index is None:
        f = ImageFont.truetype(font_path, size)
    else:
        f = ImageFont.truetype(font_path, size, index=index)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(top * size / 1000.0)), ch, fill=255,
                            font=f, anchor="ms")
    return np.array(im) > 127


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default=str(WORK / "demo" / "KangXiKai-demo-v0.1.0.ttf"))
    ap.add_argument("--manifest", default=str(WORK / "demo" / "manifest.json"))
    ap.add_argument("--outdir", default=str(WORK / "qa"))
    ap.add_argument("--font-size-check", type=int, default=256)
    args = ap.parse_args()
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    font_path = Path(args.font)
    if not font_path.is_absolute():
        font_path = ROOT / font_path
    manifest = json.load(open(args.manifest))
    want = set(manifest["chars"])

    f = TTFont(str(font_path))
    tables = sorted(f.keys())
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    cmap = f.getBestCmap()
    got = {chr(cp) for cp in cmap}
    gs = f.getGlyphSet()

    report = {"font": str(font_path.relative_to(ROOT)) if font_path.is_relative_to(ROOT)
              else str(font_path), "tables": tables,
              "missing_tables": missing,
              "n_glyphs": f["maxp"].numGlyphs,
              "n_cmap": len(cmap),
              "n_manifest": len(want),
              "cmap_equals_manifest": got == want,
              "missing_in_font": sorted(want - got),
              "extra_in_font": sorted(got - want)}

    # 1) 空字形 / bbox 闸
    empty, tiny, huge, out_of_em = [], [], [], []
    bboxes = {}
    adv_bad = []
    for cp, gname in sorted(cmap.items()):
        bp = BoundsPen(gs)
        gs[gname].draw(bp)
        if not bp.bounds:
            empty.append(chr(cp))
            continue
        x0, y0, x1, y1 = bp.bounds
        bboxes[chr(cp)] = [round(v, 1) for v in bp.bounds]
        w, h = x1 - x0, y1 - y0
        if w < 60 or h < 60:
            tiny.append((chr(cp), round(w), round(h)))
        if max(w, h) > 1000 or x0 < -80 or x1 > 1080 or y0 < -200 or y1 > 980:
            out_of_em.append((chr(cp), [round(x0), round(y0), round(x1), round(y1)]))
        adv = f["hmtx"][gname][0]
        if adv != f["head"].unitsPerEm:
            adv_bad.append((chr(cp), adv))
    report.update(empty=empty, tiny=tiny, out_of_em=out_of_em, adv_bad=adv_bad,
                  bboxes=bboxes)

    # 2) 渲染检查（256px）：墨量、连通分量、孔洞（对照宋体 TC）
    ref_ok = Path(SONGTI).exists()
    render_bad = []
    hole_rows = []
    soft_rows = []
    for ch in sorted(want):
        mask = raster_glyph(ch, str(font_path), args.font_size_check)
        ink = int(mask.sum())
        if ink < 200:
            render_bad.append({"char": ch, "reason": f"ink too small at 256px ({ink})"})
            continue
        ncomp = n_components(mask)
        line_like = n_line_like(mask)
        # 楷体复杂字合法分离笔画可达 20+；仅当「组件多且含细长直线状残片」或 极多(>24) 才判坏
        if ncomp > 24 or (ncomp > 14 and line_like >= 1):
            render_bad.append({"char": ch,
                               "reason": f"components={ncomp}, line_like={line_like}"})
        # 字形级软标志（审计2 P1-3：路/蹋 类细碎/外挂残段；不硬判，进报告）
        soft_rows.append(soft_flag(ch, mask))
        if ref_ok:
            try:
                ref = raster_glyph(ch, SONGTI, args.font_size_check, index=7)
            except Exception:
                ref = None
            if ref is not None and ref.sum() > 200:
                ho, hb = holes_of(mask), holes_of(ref)
                hole_rows.append((ch, ho, hb, ink))
    lost = [r for r in hole_rows if r[2] > 0 and r[1] == 0]
    fewer = [r for r in hole_rows if 0 < r[1] < r[2]]
    soft_flags = [r for r in soft_rows if r["flags"]]
    report.update(render_bad=render_bad, soft_flags=soft_flags,
                  holes={"n": len(hole_rows), "lost": [r[0] for r in lost],
                         "fewer": [r[0] for r in fewer],
                         "rows": hole_rows[:400]})

    # 3) version / name 一致性 + 可复现元信息
    ver_names = [str(n) for n in f["name"].names if n.nameID == 5 and n.platformID == 3]
    if ver_names:
        parts = (ver_names[0].replace("Version ", "").split(".") + ["0", "0"])[:3]
        want_rev = int(parts[0]) + int(parts[1]) / 10.0 + int(parts[2]) / 100.0
        report["fontRevision_ok"] = abs(f["head"].fontRevision - want_rev) < 1e-3
    report["head_created"] = f["head"].created
    report["head_modified"] = f["head"].modified
    report["family_name"] = f["name"].getDebugName(1)
    report["ps_name"] = f["name"].getDebugName(6)
    report["license_url"] = f["name"].getDebugName(14)

    # 4) 硬闸
    problems = []
    # 同框多标签检查（审计 P0-1）：manifest 带 page/half/box 时，同一 crop 不得对应两个码位
    conflicts = []
    try:
        recs = [r for r in (manifest.get("chars") or {}).values()
                if isinstance(r, dict) and r.get("page") and r.get("box")]
        bybox = {}
        for r in recs:
            key = (r["page"], r.get("half", "R"), tuple(r["box"]))
            bybox.setdefault(key, []).append(r["char"])
        conflicts = [{"page": k[0], "half": k[1], "box": list(k[2]), "chars": sorted(v)}
                     for k, v in bybox.items() if len(set(v)) > 1]
    except Exception:
        conflicts = []
    report["same_box_conflicts"] = conflicts
    if conflicts:
        problems.append(f"same-crop multi-char {len(conflicts)}")
    if missing:
        problems.append(f"missing tables {missing}")
    if not report["cmap_equals_manifest"]:
        problems.append("cmap != manifest")
    if empty:
        problems.append(f"empty glyphs {empty[:8]}")
    if tiny:
        problems.append(f"tiny glyphs {tiny[:8]}")
    if out_of_em:
        problems.append(f"out-of-em glyphs {out_of_em[:5]}")
    if adv_bad:
        problems.append(f"wrong advance {adv_bad[:5]}")
    if render_bad:
        problems.append(f"render bad {render_bad[:5]}")
    if report.get("fontRevision_ok") is False:
        problems.append("fontRevision mismatch")
    stats = {k: report[k] for k in
             ("n_glyphs", "n_cmap", "n_manifest", "cmap_equals_manifest",
              "missing_tables", "empty", "tiny", "out_of_em", "adv_bad",
              "fontRevision_ok", "head_created", "head_modified", "family_name",
              "ps_name", "render_bad", "holes")}
    stats["soft_flags"] = {"n": len(report.get("soft_flags", [])),
                           "chars": [r["char"] for r in report.get("soft_flags", [])][:200]}
    stats["holes"] = {"n": report["holes"]["n"], "lost": report["holes"]["lost"],
                      "fewer": report["holes"]["fewer"]}
    stats["problems"] = problems
    stats["pass"] = not problems
    (outdir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: stats[k] for k in
                      ("n_glyphs", "n_cmap", "n_manifest", "empty", "tiny",
                       "out_of_em", "adv_bad", "fontRevision_ok")},
                     ensure_ascii=False, indent=1))
    print("holes: n=%d lost=%s fewer=%s" % (stats["holes"]["n"],
                                            stats["holes"]["lost"], stats["holes"]["fewer"]))
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(" -", p)
        return 1
    print("QA PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
