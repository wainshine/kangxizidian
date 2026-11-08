#!/usr/bin/env python3
"""C 流 · 字形归一化：300dpi crop -> 轮廓 -> EM1000 字面框（y 向上）。

链路（与 guangeti 06_norm.py / glyphvec.py 等价，去「写本」术语）：
  灰度 crop -> Otsu 二值化 -> 去碎片/贴边邻字 -> potrace 矢量化 ->
  等比缩放（最长边 = 760 units）-> 平移到 (500, 400) -> 写 glyph 记录

输出：
  work/font/glyphs.jsonl   每行 {char, contours, src, ...}
  work/font/glyphs/<char>.json

依赖 work/font/_pylibs（fontTools/potracer），不改 .venv。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"
sys.path.insert(0, str(WORK / "_pylibs"))

PDF_DIR = ROOT / "康熙字典"
PDF_MAP = json.load(open(ROOT / "work" / "t2" / "pdf_map.json"))
DPI150_TO_PT = 72.0 / 150.0          # 150dpi 页面像素 -> PDF pt

EM = 1000
ASCENT = 880
DESCENT = -120
INK_LONG_SIDE = 760.0     # 字面框最长边 -> font units
INK_CX, INK_CY = 500.0, 400.0   # 字面框中心（基线 y=0 之上）
MIN_INK_PX = 120          # 太小/空 crop 直接拒
MIN_INK_AREA_RATIO = 0.02


# --------------------------------------------------------------------------- #
# 位图处理
# --------------------------------------------------------------------------- #
def binarize(gray: np.ndarray) -> np.ndarray:
    """Otsu 二值化（刻本：字黑底白），返回 bool ink mask。"""
    import cv2
    g = cv2.medianBlur(gray, 3)
    thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = min(max(int(thr), 100), 210)
    return g < thr


def clean_ink(ink: np.ndarray, min_area: int = 40,
              center: tuple[int, int, int, int] | None = None,
              border_margin: int = 1) -> np.ndarray:
    """去掉版框/栏线/邻字残片，保留字身成分（v11：solid-bbox 规则）。

    1) 主成分（面积最大）永远保留；
    2) 贴 crop 边的成分 -> 版框/栏线/邻字残片，丢；
    3) 「实心成分」= 短边 > thin_thr(14px) 的成分；取它们并集 bbox；
       细线成分（短边 <= thin_thr）若中心落在 solid bbox 外扩 8px 之外 -> 栏线/杂线，丢；
       落在 solid bbox 内 -> 字身细笔（撇/点/挑），保留；
    4) 极小碎片：落在主成分 bbox 内才留。
    """
    import cv2
    n, lab, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    if n <= 1:
        return ink
    h, w = ink.shape
    X, Y, WW, HH, AR = 0, 1, 2, 3, 4
    thin_thr = 14
    main = 1 + int(np.argmax(stats[1:, AR]))
    mx, my = stats[main, X], stats[main, Y]
    mw, mh = stats[main, WW], stats[main, HH]

    box = None
    if center is not None:
        bx0, by0, bx1, by1 = center
        bw, bh = max(1, bx1 - bx0), max(1, by1 - by0)
        ex, ey = int(0.25 * bw), int(0.25 * bh)
        box = (bx0 - ex, by0 - ey, bx1 + ex, by1 + ey)

    solid = [i for i in range(1, n)
             if stats[i, AR] >= min_area and min(stats[i, WW], stats[i, HH]) > thin_thr]
    if main not in solid:
        solid.append(main)
    sx0 = min(stats[i, X] for i in solid)
    sy0 = min(stats[i, Y] for i in solid)
    sx1 = max(stats[i, X] + stats[i, WW] for i in solid)
    sy1 = max(stats[i, Y] + stats[i, HH] for i in solid)
    m = 8
    sx0, sy0, sx1, sy1 = sx0 - m, sy0 - m, sx1 + m, sy1 + m

    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y = stats[i, X], stats[i, Y]
        ww, hh, area = stats[i, WW], stats[i, HH], stats[i, AR]
        if i == main:
            keep[i] = True
            continue
        border = (x <= border_margin or y <= border_margin
                  or x + ww >= w - border_margin or y + hh >= h - border_margin)
        if border:
            continue
        cx, cy = x + ww / 2.0, y + hh / 2.0
        if box is not None and not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
            continue          # 字身框外扩 25% 之外：邻字/栏线残片
        thin = min(ww, hh) <= thin_thr
        if thin and not (sx0 <= cx <= sx1 and sy0 <= cy <= sy1):
            continue
        if area < min_area:
            inside_main = (mx <= x and x + ww <= mx + mw and my <= y and y + hh <= my + mh)
            if inside_main:
                keep[i] = True
            continue
        keep[i] = True
    if not keep.any():
        keep[main] = True
    return keep[lab]


def trace(ink: np.ndarray, turdsize: int = 2, alphamax: float = 1.0,
          opttol: float = 0.25) -> list[dict]:
    """potrace 矢量化（位图 y 向下，像素坐标）。返回 [{start:[x,y], segs:[...]}]。"""
    import potrace
    try:
        p = potrace.Bitmap(~ink).trace(turdsize=turdsize, alphamax=alphamax,
                                       opticurve=True, opttolerance=opttol)
    except ValueError:
        p = potrace.Bitmap(~ink).trace(turdsize=turdsize, alphamax=alphamax,
                                       opticurve=False, opttolerance=opttol)
    contours = []
    for curve in p:
        segs = []
        for seg in curve:
            if type(seg).__name__ == "CornerSegment":
                segs.append(["L", float(seg.end_point.x), float(seg.end_point.y)])
            else:
                segs.append(["C", float(seg.c1.x), float(seg.c1.y),
                             float(seg.c2.x), float(seg.c2.y),
                             float(seg.end_point.x), float(seg.end_point.y)])
        if len(segs) >= 3:
            contours.append({"start": [float(curve.start_point.x), float(curve.start_point.y)],
                             "segs": segs})
    return contours


def contour_points(c: dict) -> list[tuple[float, float]]:
    pts = [tuple(c["start"])]
    for s in c["segs"]:
        if s[0] == "L":
            pts.append((s[1], s[2]))
        else:
            pts.append((s[1], s[2]))
            pts.append((s[3], s[4]))
            pts.append((s[5], s[6]))
    return pts


# --------------------------------------------------------------------------- #
# 归一化到 EM
# --------------------------------------------------------------------------- #
def normalize(contours: list[dict], em: int = EM, long_side: float = INK_LONG_SIDE,
              cx: float = INK_CX, cy: float = INK_CY) -> tuple[list[dict], dict]:
    """像素坐标（y 向下）-> EM units（y 向上）：等比缩放 + 居中。

    v0 口径：所有字共用「最长边 760 units」的字面框（无 base 字体逐字光学校正，
    见 docs/FONT-BUILD.md 已知缺陷）；扁平字（一/乙）按宽度归一，不会被拉高。
    """
    xs, ys = [], []
    for c in contours:
        for x, y in contour_points(c):
            xs.append(x)
            ys.append(y)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    scale = long_side / max(w, h)
    # 位图中心（像素，y 向下）-> 目标中心（EM，y 向上）
    mx = (x0 + x1) / 2.0
    my = (y0 + y1) / 2.0

    def fx(px: float) -> float:
        return (px - mx) * scale + cx

    def fy(py: float) -> float:
        return (my - py) * scale + cy

    out = []
    for c in contours:
        segs = []
        for s in c["segs"]:
            if s[0] == "L":
                segs.append(["L", fx(s[1]), fy(s[2])])
            else:
                segs.append(["C", fx(s[1]), fy(s[2]), fx(s[3]), fy(s[4]),
                             fx(s[5]), fy(s[6])])
        out.append({"start": [fx(c["start"][0]), fy(c["start"][1])], "segs": segs})
    info = {"scale": scale, "bbox_px": [x0, y0, x1, y1],
            "bbox_em": [fx(x0), fy(y1), fx(x1), fy(y0)]}
    return out, info


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
_DOC_CACHE: dict[str, object] = {}


def _open_pdf(pdf: str):
    """按 PDF 缓存 fitz.Document（16k 字构建时避免反复 open 14GB 文档）。"""
    import fitz
    doc = _DOC_CACHE.get(pdf)
    if doc is None:
        doc = fitz.open(PDF_DIR / PDF_MAP[pdf])
        _DOC_CACHE[pdf] = doc
    return doc


def render_pdf_crop(page_key: str, box: list, pad150: int = 6, dpi: int = 300) -> np.ndarray:
    """150dpi 页面坐标 box -> 300dpi 灰度 crop（PDF 原生分辨率直渲染，不插值放大）。"""
    import fitz
    pdf, pnum = page_key.split("_")
    x0, y0, x1, y1 = box
    doc = _open_pdf(pdf)
    page = doc[int(pnum) - 1]
    clip = fitz.Rect((x0 - pad150) * DPI150_TO_PT, (y0 - pad150) * DPI150_TO_PT,
                     (x1 + pad150) * DPI150_TO_PT, (y1 + pad150) * DPI150_TO_PT)
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def vectorize_gray(gray: np.ndarray, long_side: float = INK_LONG_SIDE,
                   center: tuple[int, int, int, int] | None = None) -> dict:
    """灰度图 -> 归一化轮廓（font_norm 主链路）。center=crop 内字身框像素坐标。"""
    ink = binarize(gray)
    ink = clean_ink(ink, center=center)
    n_ink = int(ink.sum())
    if n_ink < MIN_INK_PX or n_ink < MIN_INK_AREA_RATIO * gray.size:
        return {"ok": False, "reason": f"ink too small ({n_ink})", "ink_px": n_ink}
    contours_px = trace(ink)
    if not contours_px:
        return {"ok": False, "reason": "potrace returned no contour", "ink_px": n_ink}
    contours, info = normalize(contours_px, long_side=long_side)
    n_segs = sum(len(c["segs"]) for c in contours)
    if n_segs < 4:
        return {"ok": False, "reason": f"degenerate contour ({n_segs} segs)", "ink_px": n_ink}
    return {"ok": True, "contours": contours, "n_contours": len(contours),
            "n_segs": n_segs, "ink_px": n_ink, "norm": info}


def vectorize_crop(crop_path: Path, long_side: float = INK_LONG_SIDE,
                   center: tuple[int, int, int, int] | None = None) -> dict:
    gray = np.array(Image.open(crop_path).convert("L"))
    return vectorize_gray(gray, long_side=long_side, center=center)


def vectorize_box(page_key: str, box: list, pads=(6, 18), long_side: float = INK_LONG_SIDE,
                  dpi: int = 300) -> dict:
    """150dpi box -> 灰度 crop -> 归一化轮廓（自适应 pad）。

    先按小 pad（6px@150dpi）渲染；若最大连通域触 crop 边界（说明框偏紧、
    字身被裁），自动加大 pad 重渲一次，避免丢字身笔画。
    """
    import cv2
    last = None
    for pad150 in pads:
        gray = render_pdf_crop(page_key, box, pad150=pad150, dpi=dpi)
        ink = binarize(gray)
        n, lab, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
        X, Y, WW, HH, AR = 0, 1, 2, 3, 4
        if n > 1:
            h, w = ink.shape
            big = [i for i in range(1, n) if stats[i, AR] >= 0.15 * stats[1:, AR].max()]
            clipped = False
            for i in big:
                x, y = stats[i, X], stats[i, Y]
                ww, hh = stats[i, WW], stats[i, HH]
                if x <= 1 or y <= 1 or x + ww >= w - 1 or y + hh >= h - 1:
                    clipped = True
                    break
        else:
            clipped = True
        pad_px = pad150 * 2      # 300dpi
        center = (pad_px, pad_px, gray.shape[1] - pad_px, gray.shape[0] - pad_px)
        res = vectorize_gray(gray, long_side=long_side, center=center)
        res["pad150"] = pad150
        res["clipped"] = bool(clipped)
        last = res
        if not clipped:
            return res
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(WORK / "demo" / "manifest.json"),
                    help="字表 manifest（只处理 status=accept 的字）")
    ap.add_argument("--crops", default=str(WORK / "crops.json"),
                    help="crop 索引（font_curate.py crops 产出）")
    ap.add_argument("--out", default=str(WORK / "glyphs.jsonl"))
    ap.add_argument("--long-side", type=float, default=INK_LONG_SIDE)
    args = ap.parse_args()

    manifest = json.load(open(args.manifest))
    crops = {c["key"]: c for c in json.load(open(args.crops))}
    rows, bad = [], []
    for ch, m in sorted(manifest["chars"].items()):
        c = crops.get(m["key"])
        if c is None:
            bad.append({"char": ch, "key": m["key"], "reason": "crop 索引缺失"})
            continue
        crop_path = ROOT / c["crop"]
        if not crop_path.exists():
            bad.append({"char": ch, "key": m["key"], "reason": f"crop 不存在 {crop_path}"})
            continue
        center = None
        if c.get("crop_w") and c.get("crop_h"):
            pad_px = int(round(c.get("pad150", 18) * c.get("scale", 2.0)))
            center = (pad_px, pad_px, c["crop_w"] - pad_px, c["crop_h"] - pad_px)
        r = vectorize_crop(crop_path, long_side=args.long_side, center=center)
        if not r["ok"]:
            bad.append({"char": ch, "key": m["key"], "reason": r["reason"],
                        "ink_px": r.get("ink_px")})
            continue
        rows.append({"char": ch, "codepoint": f"U+{ord(ch):04X}",
                     "key": m["key"], "page": m["page"], "box": m["box"],
                     "layer": m.get("layer", ""), "label_source": m.get("label_source", ""),
                     "verified_by": m.get("verified_by", ""),
                     "n_contours": r["n_contours"], "n_segs": r["n_segs"],
                     "ink_px": r["ink_px"], "norm": r["norm"],
                     "contours": r["contours"]})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # 单字文件，便于人工抽查
    gdir = out.parent / "glyphs"
    gdir.mkdir(exist_ok=True)
    for r in rows:
        (gdir / f"{r['char']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    stats = {"n_ok": len(rows), "n_bad": len(bad), "bad": bad,
             "n_contours_total": sum(r["n_contours"] for r in rows),
             "n_segs_total": sum(r["n_segs"] for r in rows)}
    (out.parent / "norm_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"normalized: {len(rows)} ok, {len(bad)} bad -> {out}")
    for b in bad:
        print("  BAD", b)


if __name__ == "__main__":
    sys.exit(main())
