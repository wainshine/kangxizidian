#!/usr/bin/env python3
"""bf06_scan_variant_candidates.py — BF-06 T1.2 扫描对照（候选集，一次性诊断）。

背景（T1.1 已定位）：`precut_masks.apply_precut_masks` 模块级未 import numpy，E37 crossing 过滤
被 `except: pass` 静默跳过 → 扫描链比构建链多删整条页级线 mask（含块内细笔画）→ 扫描侧
ink_final bbox 偏小 → E36 配准（用 ink_final bbox 对齐 TTF）错位 → 缺件误报。

本脚本对 `missing_scan_v262.jsonl` 里的候选字，**同一份 crop 渲染**上并排跑两个变体：
  V_old = 复现旧行为（line mask 不过滤，等同 bug 时）；
  V_fix = 当前生产代码（precut_masks 已修复：crossing 过滤生效、fail-closed）。
两变体各自复刻 scan_missing_parts worker 的组件筛选 + 配准 + cov 判据，输出 flagged 组件集合与
Jaccard/差异统计（T1.2 验收：两变体 + Jaccard）。

只读：不写 manifest/font/scan 产物；输出到 --out。一次性脚本放 scripts/oneoff/。

用法：
  .venv/bin/python scripts/oneoff/bf06_scan_variant_candidates.py \
    --old-scan work/lead/missing_scan_v262.jsonl \
    --out work/lead/bf06-variant-candidates.jsonl --workers 8
"""
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
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))

import cv2
import numpy as np

FONT_DEFAULT = "work/font/build/KangXiKai-v2.6.2.ttf"


def _apply_old_precut(ink, page, box, pad150):
    """复现 bug 版本：line mask 不做 crossing 过滤（np NameError 被吞）。"""
    import precut_masks as PM
    lm_page, tm_page, bands_page = PM._page_masks(page)
    ink = ink.copy()
    h, w = ink.shape
    lm = PM._to_crop(lm_page, box, pad150, ink.shape)
    if lm is not None:
        ink[lm] = False
    for rec in bands_page:
        x0, y0, x1, y1 = [int(round(v)) for v in rec["rect"]]
        cx0 = max(0, int(round((x0 - (box[0] - pad150)) * 2)))
        cy0 = max(0, int(round((y0 - (box[1] - pad150)) * 2)))
        cx1 = min(w - 1, int(round((x1 - (box[0] - pad150)) * 2)))
        cy1 = min(h - 1, int(round((y1 - (box[1] - pad150)) * 2)))
        if cx1 >= cx0 and cy1 >= cy0:
            ink[cy0:cy1 + 1, cx0:cx1 + 1] = False
    tm = PM._to_crop(tm_page, box, pad150, ink.shape)
    if tm is not None:
        mm = 4
        kx0 = max(0, int(round(2 * pad150)) - mm)
        ky0 = max(0, int(round(2 * pad150)) - mm)
        kx1 = min(w, int(round((box[2] - box[0] + pad150) * 2)) + mm)
        ky1 = min(h, int(round((box[3] - box[1] + pad150) * 2)) + mm)
        tm = tm.copy()
        tm[ky0:ky1, kx0:kx1] = False
        ink[tm] = False
    return ink


def _flagged_components(ch, page, half, box, gray, src, pad, block, tbb, sb, font, font_bbox):
    """按 scan_missing_parts worker 的口径（组件筛选 + 配准 + cov）返回 flagged 组件列表。"""
    import font_build as FB
    import font_norm as FN
    from fidelity_eval import glyph_mask_from_font
    bx0 = int(round((block[0] - (box[0] - pad)) * 2)) if block else 0
    by0 = int(round((block[1] - (box[1] - pad)) * 2)) if block else 0
    bx1 = int(round((block[2] - (box[0] - pad)) * 2)) if block else src.shape[1]
    by1 = int(round((block[3] - (box[1] - pad)) * 2)) if block else src.shape[0]
    bx0, by0 = max(0, bx0), max(0, by0)
    bx1, by1 = min(src.shape[1], bx1), min(src.shape[0], by1)
    n, lab, stt, _ = cv2.connectedComponentsWithStats(src.astype(np.uint8), 8)
    cs = [(stt[i, 0], stt[i, 1], stt[i, 0] + stt[i, 2], stt[i, 1] + stt[i, 3], int(stt[i, 4]))
          for i in range(1, n) if stt[i, 4] >= 20]
    pad_px = pad * 2
    center = (pad_px, pad_px, src.shape[1] - pad_px, src.shape[0] - pad_px)
    ink_final = FN.mask_to_block(src, (bx0, by0, bx1, by1))
    ink_final = FN.remove_specks(ink_final)
    ink_final = FN.clean_cluster(ink_final, box=center)
    ink_final = FN.clean_ink(ink_final, center=center)
    gm = glyph_mask_from_font(font, ch)
    gys, gxs = np.nonzero(gm)
    if len(gxs) == 0:
        return []
    gx0, gy0, gx1, gy1 = int(gxs.min()), int(gys.min()), int(gxs.max()), int(gys.max())
    tys, txs = np.nonzero(ink_final)
    if len(txs) == 0:
        return []
    tsx0, tsy0, tsx1, tsy1 = int(txs.min()), int(tys.min()), int(txs.max()) + 1, int(tys.max()) + 1
    sw = max(1, tsx1 - tsx0); sh = max(1, tsy1 - tsy0)
    gw0 = max(1, gx1 - gx0); gh0 = max(1, gy1 - gy0)
    if font_bbox and sb and (font_bbox[2] - font_bbox[0]) > 0:
        sc = (gx1 - gx0) / float(max(1, font_bbox[2] - font_bbox[0]))
        fx = lambda x: gx0 + (x - font_bbox[0]) * sc
        fy = lambda y: gy1 - (y - font_bbox[1]) * sc
        scx0, scx1 = fx(sb[0]), fx(sb[2])
        scy0, scy1 = fy(sb[3]), fy(sb[1])
        if scx1 - scx0 > 5 and scy1 - scy0 > 5:
            msx = (tsx1 - tsx0) / (scx1 - scx0); msy = (tsy1 - tsy0) / (scy1 - scy0)
            M = np.array([[msx, 0, tsx0 - msx * scx0], [0, msy, tsy0 - msy * scy0]], np.float32)
        else:
            M = np.array([[sw / float(gw0), 0, tsx0 - (sw / float(gw0)) * gx0],
                          [0, sh / float(gh0), tsy0 - (sh / float(gh0)) * gy0]], np.float32)
    else:
        sx = sw / float(gw0); sy = sh / float(gh0)
        M = np.array([[sx, 0, tsx0 - sx * gx0], [0, sy, tsy0 - sy * gy0]], np.float32)
    gwarp = cv2.warpAffine(gm.astype(np.uint8), M, (src.shape[1], src.shape[0]),
                           flags=cv2.INTER_NEAREST) > 0
    gd = cv2.dilate(gwarp.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    total = max(1, int(src[by0:by1, bx0:bx1].sum()))
    out = []
    for (x0, y0, x1, y1, a) in cs:
        if a < 0.010 * total:
            continue
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if not (bx0 - 6 <= mx <= bx1 + 6 and by0 - 6 <= my <= by1 + 6):
            continue
        if min(x1 - x0 + 1, y1 - y0 + 1) < 8:
            continue
        reg = src[y0:y1 + 1, x0:x1 + 1]
        cov = float((reg & gd[y0:y1 + 1, x0:x1 + 1]).sum()) / max(1, int(reg.sum()))
        reg_fin = ink_final[y0:y1 + 1, x0:x1 + 1]
        fin_frac = float(reg_fin.sum()) / max(1, int(reg.sum()))
        out.append({"comp": [int(x0), int(y0), int(x1), int(y1), int(a)],
                    "cov": round(cov, 4), "fin_frac": round(fin_frac, 4),
                    "flag": bool(cov < 0.45 and fin_frac >= 0.60)})
    return out


def worker(job):
    page, half, items, font, man, stats = job
    import font_build as FB
    import font_norm as FN
    from precut_masks import apply_precut_masks
    from page_frames import clip_mask_page
    from fontTools.ttLib import TTFont
    global _FT, _CMAP, _GLYF
    try:
        _FT
    except NameError:
        _FT = TTFont(os.path.join(ROOT, font))
        _CMAP = _FT.getBestCmap()
        _GLYF = _FT["glyf"]
    out = []
    try:
        ctx_lat = FB.get_page_lattice(page)
        tbb = FB.get_page_text_bbox(page)
        quads = FB.get_page_content_quads(page)
    except Exception as e:
        return [{"page": page, "half": half, "error": f"page:{str(e)[:100]}"}]
    for ch, _ in items:
        m = man.get(ch) or {}
        box = m.get("box")
        st = stats.get(ch) or {}
        pad = int(st.get("pad150") or 6)
        sb = st.get("bbox")
        block = FB.block_for_box(ctx_lat.get(half), box) if ctx_lat.get(half) else None
        if block is not None and tbb is not None:
            block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                     min(block[2], tbb[2]), min(block[3], tbb[3]))
        try:
            gray = FN.render_pdf_crop(page, box, pad150=pad, dpi=300)
            base = FN.binarize(gray)
            quad = quads.get(half)
            if quad is not None:
                base = base & clip_mask_page(gray.shape, (box[0] - pad, box[1] - pad), quad)
            base = FN.trim_crop_frame_edges(base)
            base = FN.strip_crop_frame_bands(base)
            src_old = _apply_old_precut(base.copy(), page, box, pad)
            src_fix = apply_precut_masks(base.copy(), page, box, pad150=pad, block150=block)
            gl = _GLYF[_CMAP[ord(ch)]]
            fbb = (gl.xMin, gl.yMin, gl.xMax, gl.yMax)
            old = _flagged_components(ch, page, half, box, gray, src_old, pad, block, tbb, sb, font, fbb)
            fix = _flagged_components(ch, page, half, box, gray, src_fix, pad, block, tbb, sb, font, fbb)
            out.append({"page": page, "half": half, "char": ch,
                        "old": old, "fix": fix,
                        "old_flagged": [c["comp"] for c in old if c["flag"]],
                        "fix_flagged": [c["comp"] for c in fix if c["flag"]],
                        "old_src_ink": int(src_old.sum()), "fix_src_ink": int(src_fix.sum())})
        except Exception as e:
            out.append({"page": page, "half": half, "char": ch, "error": str(e)[:150]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-scan", default="work/lead/missing_scan_v262.jsonl")
    ap.add_argument("--manifest", default="work/font/build/manifest_v262.json")
    ap.add_argument("--stats", default="work/font/build/KangXiKai-v2.6.2.build_stats.json")
    ap.add_argument("--font", default=FONT_DEFAULT)
    ap.add_argument("--out", default="work/lead/bf06-variant-candidates.jsonl")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    stats = json.load(open(os.path.join(ROOT, args.stats), encoding="utf-8")).get("glyphs") or {}
    by_page = defaultdict(list)
    for line in open(os.path.join(ROOT, args.old_scan), encoding="utf-8"):
        r = json.loads(line)
        ch = r.get("char")
        if not ch or ch not in man or not r.get("missing"):
            continue
        m = man[ch]
        by_page[(m["page"], m.get("half", "L"))].append((ch, r))
    jobs = [(p, h, items, args.font, man, stats) for (p, h), items in sorted(by_page.items())]
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, min(10, args.workers))) as ex:
        for res in ex.map(worker, jobs, chunksize=1):
            rows.extend(res)
    rows.sort(key=lambda r: (str(r.get("page")), str(r.get("char"))))
    out = os.path.join(ROOT, args.out)
    with open(out, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    old_comps = set(); fix_comps = set(); old_chars = set(); fix_chars = set()
    errs = 0
    for r in rows:
        if r.get("error"):
            errs += 1; continue
        ch = r["char"]
        for c in r.get("old_flagged") or []:
            old_comps.add((ch, tuple(c))); old_chars.add(ch)
        for c in r.get("fix_flagged") or []:
            fix_comps.add((ch, tuple(c))); fix_chars.add(ch)
    inter = old_comps & fix_comps
    union = old_comps | fix_comps
    summary = {
        "old_scan": args.old_scan, "n_chars_input": len(rows), "errors": errs,
        "old_flagged_components": len(old_comps), "fix_flagged_components": len(fix_comps),
        "old_flagged_chars": len(old_chars), "fix_flagged_chars": len(fix_chars),
        "intersection_components": len(inter),
        "resolved_components": len(old_comps - fix_comps),
        "new_components": len(fix_comps - old_comps),
        "jaccard_components": round(len(inter) / max(1, len(union)), 4),
        "jaccard_chars": round(len(old_chars & fix_chars) / max(1, len(old_chars | fix_chars)), 4),
        "note": "V_old=复现 bug（line mask 不过滤）；V_fix=当前生产代码（precut 修复）。",
    }
    sp = os.path.splitext(out)[0] + "-summary.json"
    json.dump(summary, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
