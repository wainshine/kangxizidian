#!/usr/bin/env python3
"""字体 QA：表完整性 / 空字形 / bbox / cmap 一致性 / 渲染为空 / 同框冲突。

口径（DECISIONS D21）：
  - **不数孔洞、不用连通分量/碎片率评判字形结构**：刻本为雕刻常把笔画刻断，
    孔洞与连通性不是缺陷信号；此前「孔洞对照宋体」指标已删除。
  - 参考字体统一为霞鹜文楷（OFL，`scripts/reffont.py`），QA 本身不再依赖参考字体。
  - 保留的硬检查都是与笔画连通性无关的：表齐全、cmap==manifest、空字形、
    bbox 越界/过小、advance、fontRevision、同框多字。
  - 字形级框线检测归 `glyph_frame_gate`（线段几何判据），不在本脚本内重复。

用法：
  .venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-v2.6.1.ttf \
      --manifest work/font/build/manifest_v261.json --outdir work/font/qa
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

    # 1) 空字形 / bbox / advance（与笔画连通性无关的几何检查）
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

    # 2) 渲染为空（只查「轮廓存在但渲染不出墨」的坏 outline；不判结构）
    render_bad = []
    for ch in sorted(want):
        mask = raster_glyph(ch, str(font_path), args.font_size_check)
        ink = int(mask.sum())
        if ink < 50:
            render_bad.append({"char": ch, "reason": f"renders empty at 256px ({ink})"})
    report["render_bad"] = render_bad

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

    # 4) 硬闸（同框多标签：manifest 带 page/half/box 时，同一 crop 不得对应两个码位）
    problems = []
    conflicts = []
    try:
        recs = [(ch, r) for ch, r in (manifest.get("chars") or {}).items()
                if isinstance(r, dict) and r.get("page") and r.get("box")]
        bybox = {}
        for ch, r in recs:  # 审计 P0-5：manifest 的键才是 char，值里没有 "char" 字段
            key = (r["page"], r.get("half", "R"), tuple(r["box"]))
            bybox.setdefault(key, []).append(ch)
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
        problems.append(f"render empty {render_bad[:5]}")
    if report.get("fontRevision_ok") is False:
        problems.append("fontRevision mismatch")
    stats = {k: report[k] for k in
             ("n_glyphs", "n_cmap", "n_manifest", "cmap_equals_manifest",
              "missing_tables", "empty", "tiny", "out_of_em", "adv_bad",
              "fontRevision_ok", "head_created", "head_modified", "family_name",
              "ps_name", "render_bad", "same_box_conflicts")}
    stats["problems"] = problems
    stats["pass"] = not problems
    (outdir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: stats[k] for k in
                      ("n_glyphs", "n_cmap", "n_manifest", "empty", "tiny",
                       "out_of_em", "adv_bad", "fontRevision_ok",
                       "same_box_conflicts")},
                     ensure_ascii=False, indent=1))
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(" -", p)
        return 1
    print("QA PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
