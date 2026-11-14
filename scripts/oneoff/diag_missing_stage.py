#!/usr/bin/env python3
"""diag_missing_stage.py — BF-06 构建侧逐阶段存活插桩（一次性诊断脚本，v2.6.3 T1.1）。

目标：对 `missing_scan_v262.jsonl` 的每个缺件组件，判断它在**构建侧**链路的哪个阶段消失：
  构建链（复刻 font_build._worker_page + font_norm.vectorize_box 的输入组装与内部阶段）：
    binarize → clip(content_quad) → trim_crop_frame_edges → strip_crop_frame_bands →
    erase_rects → frame_mask(line mask + page_line_bands) → mask_to_block →
    block_band → remove_specks → strip_border(默认关) → clean_cluster → clean_ink →
    trace_upscaled → normalize → prune_edge_contours → TTF 轮廓
  分类：
    absent_in_build_source / pre_cut_loss / clean_loss / prune_loss /
    trace_or_normalize_loss / scan_false_positive
  目标：234 组件 100% 归因、unknown=0（T1.3 门槛）。

注意：
- 本脚本**只读**构建/数据；trace 钩子是 font_norm.vectorize_gray 的默认关闭参数（trace=None 零开销）。
- 不用扫描侧 `apply_precut_masks` 代替构建链（audit4 GATE-401/peer 阻塞 1）。
- 一次性脚本：放在 scripts/oneoff/，不参与构建。

用法：
  .venv/bin/python scripts/oneoff/diag_missing_stage.py \
    --missing work/lead/missing_scan_v262.jsonl \
    --manifest work/font/build/manifest_v262.json \
    --stats work/font/build/KangXiKai-v2.6.2.build_stats.json \
    --out work/lead/missing-165-stage-attribution.jsonl \
    --workers 8
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

import cv2
import numpy as np
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))

STAGE_ORDER = ["binarize", "clip", "trim", "strip_bands", "erase", "frame_mask",
               "block_mask", "block_band", "remove_specks", "strip_border",
               "clean_cluster", "clean_ink"]
PRE_CUT = {"clip", "trim", "strip_bands", "erase", "frame_mask", "block_mask", "block_band"}
CLEAN = {"remove_specks", "clean_cluster", "clean_ink"}


def page_ctx(page):
    """复刻 font_build._worker_page 的页级准备（构建侧输入组装）。"""
    import font_build as fb
    ctx = {
        "lat_all": fb.get_page_lattice(page),
        "tbb": fb.get_page_text_bbox(page),
        "quads": fb.get_page_content_quads(page),
        "line_mask": fb.get_page_line_mask(page) if os.environ.get("FONT_PAGE_LINE_MASK", "1") != "0" else None,
        "band_mask": None,
        "thin_mask": fb.get_page_thin_line_mask(page) if os.environ.get("FONT_PAGE_THIN_MASK", "1") != "0" else None,
    }
    bands = fb.get_page_line_bands(page)
    if bands:
        try:
            from detect_blocks import page_gray as _pg
            g = _pg(page[:2], int(page[3:]))
            bm = g.copy()
            bm[:] = 0
            for rec in bands:
                x0, y0, x1, y1 = [int(round(v)) for v in rec["rect"]]
                bm[max(0, y0):max(0, y1) + 1, max(0, x0):max(0, x1) + 1] = 1
            ctx["band_mask"] = bm
        except Exception:
            ctx["band_mask"] = None
    return ctx


def _poly_pts(c):
    from font_norm import contour_points
    return contour_points(c)


def point_in_contours(contours, px, py):
    import numpy as np
    for c in contours or []:
        pts = np.array(_poly_pts(c), dtype=np.float32)
        if len(pts) < 3:
            continue
        try:
            if cv2.pointPolygonTest(pts, (float(px), float(py)), False) >= 0:
                return True
        except Exception:
            continue
    return False


def _affine(info):
    bx0, by0, bx1, by1 = [float(v) for v in info["bbox_px"]]
    ex0, ey0, ex1, ey1 = [float(v) for v in info["bbox_em"]]
    scale = float(info["scale"])
    mx, my = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    cx = (ex0 + ex1) / 2.0
    cy = (ey0 + ey1) / 2.0
    return mx, my, cx, cy, scale


def crop_to_em(info, px, py):
    """crop 像素 (px,py) -> EM units (y up)。"""
    mx, my, cx, cy, scale = _affine(info)
    return (px - mx) * scale + cx, (my - py) * scale + cy


def em_to_crop(info, u, v):
    """EM units (y up) -> crop 像素。"""
    mx, my, cx, cy, scale = _affine(info)
    return (u - cx) / scale + mx, my - (v - cy) / scale


def raster_contours_crop(contours, info, shape):
    """把 EM 轮廓逆变换回 crop 像素并栅格化（用于判定组件区域是否被最终字形覆盖）。"""
    import numpy as np
    m = np.zeros(shape, dtype=np.uint8)
    for c in contours or []:
        pts = []
        for (u, v) in _poly_pts(c):
            px, py = em_to_crop(info, u, v)
            pts.append([px, py])
        if len(pts) >= 3:
            cv2.fillPoly(m, [np.round(np.array(pts, dtype=np.float64)).astype(np.int32)], 1)
    return m > 0


def coverage(mask, x0, y0, x1, y1):
    """rect 面积覆盖率（调试用；稀疏组件天然 <1，不能用来判丢失）。"""
    if mask is None:
        return None
    h, w = mask.shape
    xx0, yy0 = max(0, int(x0)), max(0, int(y0))
    xx1, yy1 = min(w, int(x1) + 1), min(h, int(y1) + 1)
    if xx1 <= xx0 or yy1 <= yy0:
        return 0.0
    sub = mask[yy0:yy1, xx0:xx1]
    return float(sub.mean()) if sub.size else 0.0


def stage_ratio(mask, comp):
    """组件存活比：该阶段 mask 在组件 rect 内的墨量 / 扫描组件面积（>=1 截到 1）。

    扫描组件面积来自 scan_missing_parts 的 connectedComponents stats（真实像素数），
    因此稀疏组件的 rect 面积覆盖率虽低，但存活比应约为 1；只有墨量真正减少才下降。
    """
    if mask is None:
        return None
    x0, y0, x1, y1, area = comp
    h, w = mask.shape
    xx0, yy0 = max(0, int(x0)), max(0, int(y0))
    xx1, yy1 = min(w, int(x1) + 1), min(h, int(y1) + 1)
    if xx1 <= xx0 or yy1 <= yy0:
        return 0.0
    return min(1.0, float(mask[yy0:yy1, xx0:xx1].sum()) / max(1.0, float(area)))


def analyze_component(tr, comp, pad, page, half, ch, box):
    """返回单组件归因记录。comp = [x0,y0,x1,y1,area]（crop 300dpi 像素，与构建 crop 同源）。"""
    x0, y0, x1, y1, area = comp
    stages = tr.get("stages") or {}
    covs = {s: coverage(stages.get(s), x0, y0, x1, y1) for s in STAGE_ORDER}
    ratios = {s: stage_ratio(stages.get(s), comp) for s in STAGE_ORDER}
    rec = {"char": ch, "page": page, "half": half, "box": box, "pad150": pad,
           "component": [int(x0), int(y0), int(x1), int(y1), int(area)],
           "stage_coverage": {k: (None if v is None else round(v, 4)) for k, v in covs.items()},
           "stage_ratio": {k: (None if v is None else round(v, 4)) for k, v in ratios.items()},
           "first_drop": None, "classification": "unknown",
           "in_contours_normalized": None, "in_contours_final": None}
    if not tr.get("ok") and not stages:
        rec["classification"] = "build_error"
        rec["build_reason"] = tr.get("reason")
        return rec
    r0 = ratios.get("binarize")
    if r0 is not None and r0 < 0.50:
        rec["classification"] = "absent_in_build_source"
        return rec
    drop = None
    prev = r0 if r0 is not None else 1.0
    for s in STAGE_ORDER:
        if s == "binarize":
            continue
        v = ratios.get(s)
        if v is not None and v < 0.30 and v < 0.60 * max(prev, 1e-6):
            drop = s
            break
        if v is not None:
            prev = v
    rec["first_drop"] = drop
    if drop is not None:
        rec["classification"] = "pre_cut_loss" if drop in PRE_CUT else (
            "clean_loss" if drop in CLEAN else f"mask_loss:{drop}")
        return rec
    # 掩膜链全程存活：判定 TTF/轮廓层
    info = tr.get("norm_info")
    if not info:
        rec["classification"] = "unknown"
        return rec
    shape = next(iter((tr.get("stages") or {}).values())).shape
    mask_norm = raster_contours_crop(tr.get("contours_normalized"), info, shape)
    mask_final = raster_contours_crop(tr.get("contours_final"), info, shape)
    # 覆盖率口径与 scan_missing_parts 对齐：以「clean_ink 掩膜在该 rect 内的墨量」为分母，
    # 看这些墨是否被（膨胀后的）轮廓覆盖；同时记录 rect 面积覆盖率便于调试。
    ink = (tr.get("stages") or {}).get("clean_ink")
    kernel = np.ones((9, 9), np.uint8)
    gd_norm = cv2.dilate(mask_norm.astype(np.uint8), kernel) > 0
    gd_final = cv2.dilate(mask_final.astype(np.uint8), kernel) > 0
    h, w = shape
    xx0, yy0 = max(0, int(x0)), max(0, int(y0))
    xx1, yy1 = min(w, int(x1) + 1), min(h, int(y1) + 1)
    ink_rect = ink[yy0:yy1, xx0:xx1] if ink is not None else None
    denom = int(ink_rect.sum()) if ink_rect is not None else 0
    if denom > 0:
        cov_norm = float((ink_rect & gd_norm[yy0:yy1, xx0:xx1]).sum()) / denom
        cov_final = float((ink_rect & gd_final[yy0:yy1, xx0:xx1]).sum()) / denom
    else:
        cov_norm = cov_final = 0.0
    rec["ink_coverage_normalized"] = round(float(cov_norm), 4)
    rec["ink_coverage_final"] = round(float(cov_final), 4)
    rec["contour_area_coverage_normalized"] = round(float(coverage(mask_norm, x0, y0, x1, y1)), 4)
    rec["contour_area_coverage_final"] = round(float(coverage(mask_final, x0, y0, x1, y1)), 4)
    rec["in_contours_normalized"] = bool(cov_norm >= 0.45)
    rec["in_contours_final"] = bool(cov_final >= 0.45)
    if rec["in_contours_final"]:
        rec["classification"] = "build_chain_ok_scan_flag"  # 构建链保留且 TTF 轮廓覆盖 → scan 误报
    elif rec["in_contours_normalized"]:
        rec["classification"] = "prune_loss"
    else:
        rec["classification"] = "trace_or_normalize_loss"
    return rec


def worker(job):
    page, half, items, man, stats_g = job
    import font_norm as FN
    import font_build as fb
    out = []
    try:
        ctx = page_ctx(page)
    except Exception as e:
        for ch, missing in items:
            m = man.get(ch) or {}
            for comp in missing:
                out.append({"char": ch, "page": page, "half": half, "box": m.get("box"),
                            "component": comp, "classification": "build_error",
                            "build_reason": f"page_ctx:{str(e)[:100]}"})
        return out
    for ch, missing in items:
        m = man.get(ch) or {}
        box = m.get("box")
        st = (stats_g.get(ch) or {})
        pad = int(st.get("pad150") or 6)
        try:
            block = fb.block_for_box(ctx["lat_all"].get(half), box) if ctx["lat_all"].get(half) else None
            if block is not None and ctx["tbb"] is not None:
                block = (max(block[0], ctx["tbb"][0]), max(block[1], ctx["tbb"][1]),
                         min(block[2], ctx["tbb"][2]), min(block[3], ctx["tbb"][3]))
            tr = {}
            res = FN.vectorize_box(page, box, pads=(pad,), block150=block,
                                   content_quad=ctx["quads"].get(half),
                                   frame_mask=ctx["line_mask"],
                                   frame_mask_extra=ctx["band_mask"],
                                   frame_mask_outer=ctx["thin_mask"],
                                   outer_keep_margin150=2.0,
                                   strip_border=(os.environ.get("FONT_STRIP_BORDER", "0") == "1"),
                                   trace=tr)
            tr.setdefault("ok", bool(res.get("ok")))
            if not tr.get("ok") and "reason" not in tr:
                tr["reason"] = res.get("reason")
        except Exception as e:
            tr = {"ok": False, "reason": f"vectorize:{str(e)[:100]}", "stages": {}}
        for comp in missing:
            out.append(analyze_component(tr, comp, pad, page, half, ch, box))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing", default="work/lead/missing_scan_v262.jsonl")
    ap.add_argument("--manifest", default="work/font/build/manifest_v262.json")
    ap.add_argument("--stats", default="work/font/build/KangXiKai-v2.6.2.build_stats.json")
    ap.add_argument("--out", default="work/lead/missing-165-stage-attribution.jsonl")
    ap.add_argument("--summary", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个字（调试）")
    args = ap.parse_args()
    workers = max(1, min(10, args.workers))
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    stats = json.load(open(os.path.join(ROOT, args.stats), encoding="utf-8"))
    stats_g = stats.get("glyphs") or {}
    by_page = defaultdict(list)
    ncomp = 0
    for line in open(os.path.join(ROOT, args.missing), encoding="utf-8"):
        r = json.loads(line)
        ch = r.get("char")
        if not ch or not r.get("missing") or ch not in man:
            continue
        m = man[ch]
        key = (m["page"], m.get("half", "L"))
        by_page[key].append((ch, r["missing"]))
        ncomp += len(r["missing"])
    chars = [ch for items in by_page.values() for ch, _ in items]
    if args.limit:
        ordered = sorted(by_page.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        keep = []
        n = 0
        for key, items in ordered:
            sel = []
            for ch, missing in items:
                if n >= args.limit:
                    break
                sel.append((ch, missing)); n += 1
            if sel:
                keep.append((key, sel))
            if n >= args.limit:
                break
        by_page = dict(keep)
        chars = [ch for items in by_page.values() for ch, _ in items]
        ncomp = sum(len(x) for _, items in by_page.items() for _, x in items)
    jobs = [(p, h, items, man, stats_g) for (p, h), items in sorted(by_page.items())]
    print(json.dumps({"pages": len(jobs), "chars": len(chars), "components": ncomp,
                      "workers": workers}, ensure_ascii=False), flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(worker, jobs, chunksize=1):
            rows.extend(res)
    rows.sort(key=lambda r: (str(r.get("page")), str(r.get("char")),
                             tuple(r.get("component") or [])))
    out = os.path.join(ROOT, args.out)
    with open(out, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    cls = Counter(r.get("classification") for r in rows)
    drops = Counter(r.get("first_drop") for r in rows if r.get("first_drop"))
    by_vol = Counter()
    for r in rows:
        page = str(r.get("page") or "")
        by_vol[page[:2]] += 1
    summary = {
        "missing_file": args.missing, "manifest": args.manifest, "stats": args.stats,
        "n_components": len(rows), "n_chars": len(set(r.get("char") for r in rows)),
        "classification": dict(cls), "first_drop": dict(drops),
        "by_volume_components": dict(sorted(by_vol.items())),
        "unknown": cls.get("unknown", 0),
        "build_errors": cls.get("build_error", 0),
        "stage_order": STAGE_ORDER,
        "gate": "unknown==0 required for T1.3 (BF-06)",
    }
    sp = args.summary or (os.path.splitext(out)[0] + "-summary.json")
    with open(sp, "w", encoding="utf-8") as fo:
        json.dump(summary, fo, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
