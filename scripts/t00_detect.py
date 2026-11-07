#!/usr/bin/env python3
"""T0.0 · 字头检测 v2（计数 + 裁剪框）

版面事实（实测，修正 PROMPT 的「每半页 2 列」）：
- 内容页为跨页扫描（约 1900×1640 px @150dpi），左右两个「版」，每版约 8 窄列注文；
- 字头为大字楷体（实测高度约注文 2.2–2.6 倍，每页统计落盘），列内混排；
- 每个版的外侧书眉竖排「康熙字典/集名/部首/页码」；部分半版空白（透印残影）。

方法（形态学，不依赖列切分）：
1) 固定阈值二值化（150）+ 长线剔除（开运算 200px，去版框/栏线）；
2) 半版墨量过低 → 空白半版；
3) 闭运算（11px）填笔画间隙 → 开运算（k = 1.25 × 注文高度众数 h0，数据驱动）
   → 连通域 = 字头核心 → 回映原图取精确 bbox；
4) h0：对原始墨块（无膨胀）高度直方图取众数（15–70px 范围）。

输出：
  work/t00/headwords.jsonl   每个字头一行
  work/t00/page_stats.jsonl  每页统计（h0/开核/空白半版）
  work/t00/crops/*.png       字头裁剪（供 OCR）
  work/t00/margins/*.png     书眉条（供读部首/页码）
  work/t00/overlay/*.png     叠加调试图（--overlay 指定页）
"""
import argparse, json, os, statistics
import numpy as np
import cv2

cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")
PAGES = os.path.join(T00, "pages")

BIN_T = 150
HALF_BLANK_INK = 0.004
LINE_LEN = 200
CLOSE_K = 11
MIN_CS = 14           # 字块最小边


def page_ink(gray):
    ink = (gray <= BIN_T).astype(np.uint8)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, LINE_LEN))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (LINE_LEN, 1))
    vlines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    hlines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    return cv2.subtract(cv2.subtract(ink, vlines), hlines), vlines, hlines


def frame_region(ink, x0, x1, side):
    """内容区 = 半页缩进版：外侧缩进切书眉带（左版书眉在左、右版书眉在右），
    上下切页边黑线/阴影。书眉宽度实测 40–90px，取 80/100 稳妥；
    框内首列字头距外缘 >100px（有书眉的页）或紧贴（裁切紧的页，此时无书眉可切）。"""
    Hh, Wh = ink.shape
    if side == "L":
        cx0, cx1 = x0 + 80, x1 - 12
    else:
        cx0, cx1 = x0 + 12, x1 - 100
    fy0, fy1 = 60, Hh - 65
    return (cx0, fy0, cx1, fy1)


def split_halves(ink, W):
    colsum = ink.sum(axis=0)
    cx0, cx1 = int(W * 0.30), int(W * 0.70)
    best, run = None, None
    for x in range(cx0, cx1):
        if colsum[x] == 0:
            if run is None:
                run = x
        else:
            if run is not None:
                if best is None or x - run > best[1]:
                    best = (run, x - run)
                run = None
    if run is not None and (best is None or cx1 - run > best[1]):
        best = (run, cx1 - run)
    if best is None:
        halves = [(0, W // 2), (W // 2, W)]
    else:
        gx, gw = best
        halves = [(0, max(0, gx - 8)), (min(W, gx + gw + 8), W)]
    out = []
    for side, (x0, x1) in zip("LR", halves):
        blank = ink[:, x0:x1].mean() < HALF_BLANK_INK
        out.append((side, x0, x1, bool(blank)))
    return out


def raw_blocks(sub):
    """未膨胀墨块（供 h0 统计）：过滤 <14px 边与 <30px² 面积"""
    n, _, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    hs = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area >= 30 and min(w, h) >= 10:
            hs.append(int(h))
    return hs


def height_mode(hs):
    hs = [h for h in hs if 15 <= h <= 70]
    if len(hs) < 20:
        return None
    bins = np.bincount([(h - 15) // 4 for h in hs], minlength=15)
    return 15 + int(np.argmax(bins)) * 4 + 2


def headword_boxes(sub, h0):
    """笔画粗细判据：erode(6) 只留字头笔画芯 → dilate(18) 归并同字笔画 → 连通域 →
    回映原图取精确 bbox。
    过滤：①细长条（框线残段 aspect≥12，「一」类横扁字 aspect~6 不受伤）；
          ②贴边（页边黑线/中缝阴影）；
          ③邻域墨密度（字头嵌在密排注文中，邻域密度高；书眉字/孤立污点周围空白）。"""
    ERODE_K, DIL_K, MIN_SIZE, ASP_MAX, EDGE = 6, 18, 45, 12, 8
    DENS_MIN = 0.08
    ke = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ERODE_K, ERODE_K))
    kd = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (DIL_K, DIL_K))
    cores = cv2.erode(sub, ke)
    blobs = cv2.dilate(cores, kd)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(blobs, connectivity=8)
    Hh, Ww = sub.shape
    boxes = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if max(w, h) < MIN_SIZE:
            continue
        if w >= ASP_MAX * h or h >= ASP_MAX * w:   # 框线/栏线残段
            continue
        pad = max(12, max(w, h) // 5)
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(Ww, x + w + pad), min(Hh, y + h + pad)
        region = sub[y0:y1, x0:x1]
        ys, xs = np.where(region > 0)
        if len(xs) == 0:
            continue
        bx0, bx1 = int(x0 + xs.min()), int(x0 + xs.max()) + 1
        by0, by1 = int(y0 + ys.min()), int(y0 + ys.max()) + 1
        bw, bh = bx1 - bx0, by1 - by0
        if max(bw, bh) < MIN_SIZE:
            continue
        if bw >= ASP_MAX * bh or bh >= ASP_MAX * bw:
            continue
        if not (0.5 <= bw / bh <= 1.9):   # 方正度：杀反切小字粘连对（~2.2:1）
            continue
        if bx0 < EDGE or by0 < EDGE or bx1 > Ww - EDGE or by1 > Hh - EDGE:
            continue
        s = max(bw, bh)  # 邻域：字外一圈等宽环
        nx0, ny0 = max(0, bx0 - s), max(0, by0 - s)
        nx1, ny1 = min(Ww, bx1 + s), min(Hh, by1 + s)
        ring = np.zeros((ny1 - ny0, nx1 - nx0), dtype=np.uint8)
        ring[by0 - ny0:by1 - ny0, bx0 - nx0:bx1 - nx0] = 1
        nb = sub[ny0:ny1, nx0:nx1]
        outside = nb[ring == 0]
        dens = float(outside.mean() > 0) if outside.size else 0.0
        dens = float((outside > 0).mean()) if outside.size else 0.0
        if dens < DENS_MIN:
            continue
        ink_px = int(sub[by0:by1, bx0:bx1].sum())
        boxes.append({"x0": bx0, "y0": by0, "x1": bx1, "y1": by1,
                      "h": bh, "w": bw, "ink": ink_px, "nb_dens": round(dens, 3)})
    return boxes, ERODE_K


def process(png_path, overlay_out=None):
    gray = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
    H, W = gray.shape
    ink, vlines, hlines = page_ink(gray)
    halves = split_halves(ink, W)
    boxes, halves_out = [], []
    h0s = []
    for side, x0, x1, blank in halves:
        half = {"side": side, "x0": int(x0), "x1": int(x1), "blank": blank, "n_big": 0}
        if not blank:
            fr = frame_region(ink, x0, x1, side)
            half["frame"] = list(fr)
            fx0, fy0, fx1, fy1 = fr
            sub = ink[fy0:fy1, fx0:fx1].copy()
            ox, oy = fx0, fy0
            h0 = height_mode(raw_blocks(sub))
            half["h0"] = h0
            if h0 is not None:
                h0s.append(h0)
                bb, k = headword_boxes(sub, h0)
                half["erode_k"] = k
                half["n_big"] = len(bb)
                for b in bb:
                    b["side"] = side
                    b["x0"] += ox
                    b["x1"] += ox
                    b["y0"] += oy
                    b["y1"] += oy
                    boxes.append(b)
        halves_out.append(half)
    h0_page = statistics.median(h0s) if h0s else None
    result = {"W": int(W), "H": int(H), "h0": h0_page,
              "halves": halves_out, "n_big": len(boxes)}
    if overlay_out is not None:
        vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        for b in boxes:
            cv2.rectangle(vis, (b["x0"], b["y0"]), (b["x1"], b["y1"]), (0, 0, 255), 4)
        for half in halves_out:
            cv2.line(vis, (half["x0"], 0), (half["x0"], H), (255, 0, 0), 2)
        cv2.imwrite(overlay_out, vis)
    return result, boxes


def margin_stems(gray, W):
    lw = int(W * 0.05)
    return gray[:, 0:lw], gray[:, W - lw:W]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--overlay", default="")
    args = ap.parse_args()
    overlay_set = set(s for s in args.overlay.split(",") if s)

    for d in ("crops", "margins", "overlay"):
        os.makedirs(os.path.join(T00, d), exist_ok=True)
    files = sorted(f for f in os.listdir(PAGES) if f.endswith(".png"))
    if args.only:
        files = [f for f in files if args.only in f]
    n_hw = 0
    suffix = "_debug" if args.only else ""
    with open(os.path.join(T00, f"headwords{suffix}.jsonl"), "w", encoding="utf-8") as fh, \
         open(os.path.join(T00, f"page_stats{suffix}.jsonl"), "w", encoding="utf-8") as fs:
        for f in files:
            stem = f[:-4]
            pdf, page = stem.split("_")[0], int(stem.split("_")[1])
            gray = cv2.imread(os.path.join(PAGES, f), cv2.IMREAD_GRAYSCALE)
            ov = os.path.join(T00, "overlay", stem + ".png") if stem in overlay_set else None
            res, boxes = process(os.path.join(PAGES, f), ov)
            n_hw += len(boxes)
            L, R = margin_stems(gray, res["W"])
            cv2.imwrite(os.path.join(T00, "margins", f"{stem}_L.png"), L)
            cv2.imwrite(os.path.join(T00, "margins", f"{stem}_R.png"), R)
            for i, b in enumerate(boxes):
                x0, y0, x1, y1 = b["x0"], b["y0"], b["x1"], b["y1"]
                pad = max(4, b["h"] // 16)
                crop = gray[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
                b["crop"] = f"crops/{stem}_{b['side']}_{i:03d}.png"
                cv2.imwrite(os.path.join(T00, b["crop"]), crop)
                fh.write(json.dumps({"pdf": pdf, "page": page, **b}, ensure_ascii=False) + "\n")
            res["file"] = f
            fs.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(f"pages: {len(files)}, headwords: {n_hw}")


if __name__ == "__main__":
    main()
