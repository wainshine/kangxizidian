#!/usr/bin/env python3
"""版面格点法大字检测（按用户提示：大字占 2×2 小字格、面积≈4 小字格）。

步骤：
1) 150dpi 灰度 → 背景归一化 → 二值；
2) 找「小字」连通域（h 26-50）→ 估计字格高 h0、宽 w0、列距、行距，建立格点坐标系；
3) 格点占用：小字中心落入的格子标记为已占；
4) 大字 = 2×2 连续空格，且块内墨量≈2-6 倍小字墨量、四个象限均有墨（跨格）；
5) 大字框 = 2×2 格块边界内的墨迹 bbox（不含格块外任何墨迹 → 无注文/边角料）。
输出 JSONL：page/half/box/h0/cell/ink。
"""
import json, os, sys
import numpy as np, cv2, fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def page_gray(vol, pno, dpi=150):
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def detect(gray):
    bg = cv2.medianBlur(gray, 21)
    norm = np.clip(gray.astype(np.int16) - bg.astype(np.int16) + 200, 0, 255).astype(np.uint8)
    thr, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (norm < min(205, int(thr))).astype(np.uint8)
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n0):
        if s0[i, cv2.CC_STAT_AREA] >= 20:
            keep[l0 == i] = 1
    ink = keep
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if 24 <= h <= 52 and 12 <= w <= 52 and a < 900 and a >= 60:
            small.append((x, y, w, h, a))
    if len(small) < 200:
        return {"boxes": [], "h0": None, "n_small": len(small)}
    h0 = float(np.median([s[3] for s in small]))
    w0 = float(np.median([s[2] for s in small]))
    # 格距：用中心点分列/分行（聚类到 ~h0/2）
    cx = np.array([x + w / 2 for x, y, w, h, a in small])
    cy = np.array([y + h / 2 for x, y, w, h, a in small])
    def peak_pitch(v, binw=6, min_count=3):
        bins = np.round(v / binw) * binw
        vals, counts = np.unique(bins, return_counts=True)
        peaks = vals[counts >= max(min_count, len(v) * 0.01)]
        if len(peaks) < 3:
            return None
        peaks = np.sort(peaks)
        d = np.diff(peaks)
        d = d[(d > 10) & (d < 140)]
        return float(np.median(d)) if len(d) else None
    px = peak_pitch(cx) or w0 * 1.7
    py = peak_pitch(cy) or h0 * 1.05
    # 网格原点（小字左上），限定文本块
    x0 = float(np.percentile([s[0] for s in small], 1))
    y0 = float(np.percentile([s[1] for s in small], 1))
    x1t = float(np.percentile([s[0] + s[2] for s in small], 99))
    y1t = float(np.percentile([s[1] + s[3] for s in small], 99))
    R, C = int((min(gray.shape[0], y1t + 2 * py) - y0) // py) + 1, int((min(gray.shape[1], x1t + 2 * px) - x0) // px) + 1
    occ = np.zeros((R, C), dtype=np.uint8)
    for x, y, w, h, a in small:
        c = int((x + w / 2 - x0) // px); r = int((y + h / 2 - y0) // py)
        if 0 <= r < R and 0 <= c < C:
            occ[r, c] = 1
    small_area = float(np.median([s[4] for s in small]))
    # cells 的空格 (2x2)
    boxes = []
    for r in range(R - 1):
        for c in range(C - 1):
            if occ[r:r + 2, c:c + 2].any():
                continue
            bx0 = int(x0 + c * px); by0 = int(y0 + r * py)
            bx1 = int(x0 + (c + 2) * px); by1 = int(y0 + (r + 2) * py)
            bx0, by0 = max(0, bx0), max(0, by0)
            bx1, by1 = min(gray.shape[1], bx1), min(gray.shape[0], by1)
            if bx1 - bx0 < 40 or by1 - by0 < 40:
                continue
            sub = ink[by0:by1, bx0:bx1]
            a = int(sub.sum())
            if not (1.2 * small_area <= a <= 8 * small_area):
                continue
            # 四象限均有墨（大字跨 2x2）
            H, W = sub.shape
            quads = [sub[:H // 2, :W // 2].sum(), sub[:H // 2, W // 2:].sum(),
                     sub[H // 2:, :W // 2].sum(), sub[H // 2:, W // 2:].sum()]
            if min(quads) < 0.06 * a:
                continue
            # 跨格笔画检验：内部十字界线附近必须有墨（4 个小字各自成格时界线处是空白）
            vb = sub[:, max(0, W // 2 - 2):W // 2 + 3] if W > 10 else sub[:, :1]
            hb = sub[max(0, H // 2 - 2):H // 2 + 3, :] if H > 10 else sub[:1, :]
            cross = max(vb.mean(), hb.mean())
            if cross < 0.06:
                continue
            ys, xs = np.where(sub > 0)
            if len(xs) < 30:
                continue
            boxes.append({"box": [int(bx0 + xs.min()), int(by0 + ys.min()),
                                  int(bx0 + xs.max() + 1), int(by0 + ys.max() + 1)],
                          "ink": a, "cell": [r, c], "px": round(px, 1), "py": round(py, 1)})
    # 去重：IoU>0.5 合并
    out = []
    for b in sorted(boxes, key=lambda x: -x["ink"]):
        dup = False
        for o in out:
            ax0, ay0, ax1, ay1 = b["box"]; bx0, by0, bx1, by1 = o["box"]
            ix = max(0, min(ax1, bx1) - max(ax0, bx0)); iy = max(0, min(ay1, by1) - max(ay0, by0))
            inter = ix * iy
            ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
            if ua and inter / ua > 0.5:
                dup = True; break
        if not dup:
            out.append(b)
    return {"boxes": out, "h0": round(h0, 1), "w0": round(w0, 1), "px": round(px, 1),
            "py": round(py, 1), "n_small": len(small), "small_area": round(small_area, 1)}


def main():
    vol, page = sys.argv[1], int(sys.argv[2])
    res = detect(page_gray(vol, page))
    print(json.dumps({k: v for k, v in res.items() if k != "boxes"}, ensure_ascii=False))
    print("n_boxes", len(res["boxes"]))
    for b in res["boxes"][:20]:
        print(b["box"], "ink", b["ink"], "cell", b["cell"])


if __name__ == "__main__":
    main()
