#!/usr/bin/env python3
"""检测每页（跨页）左右半版的「版框」矩形（最外圈黑色边框），用于排除页框/页边页码等非正文区。"""
import json, os, sys
import numpy as np, cv2, fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render(vol, pno, dpi=150):
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def binarize(g):
    bg = cv2.medianBlur(g, 21)
    diff = bg.astype(np.int16) - g.astype(np.int16)
    return (diff > 40).astype(np.uint8) * 255


def detect_frame(g):
    h, w = g.shape
    ink = binarize(g)
    lines = cv2.HoughLinesP(ink, 1, np.pi / 360, threshold=80,
                            minLineLength=int(0.28 * max(h, w)), maxLineGap=25)
    if lines is None:
        return None
    arr = lines.reshape(-1, 4)
    hs, vs = [], []
    for xa, ya, xb, yb in arr:
        dx, dy = xb - xa, yb - ya
        L = float(np.hypot(dx, dy))
        if abs(dy) <= max(2, 0.006 * L) and L > 0.30 * w:
            hs.append((min(xa, xb), max(xa, xb), (ya + yb) // 2, L))
        if abs(dx) <= max(2, 0.006 * L) and L > 0.35 * h:
            vs.append((min(ya, yb), max(ya, yb), (xa + xb) // 2, L))
    if len(hs) < 2 or len(vs) < 2:
        return None
    # 取最长且靠边缘的线：上下（y 最小/最大）、左右（x 最小/最大）
    hs.sort(key=lambda t: -t[3]); vs.sort(key=lambda t: -t[3])
    top = min(hs, key=lambda t: t[2]); bot = max(hs, key=lambda t: t[2])
    left = min(vs, key=lambda t: t[2]); right = max(vs, key=lambda t: t[2])
    # 排除扫描边缘阴影（离图边 <2%）
    def okline(pos, dim):
        return 0.015 * dim < pos < 0.985 * dim
    if not (okline(top[2], h) and okline(bot[2], h) and okline(left[2], w) and okline(right[2], w)):
        return None
    return {"frame": [int(left[2]), int(top[2]), int(right[2]), int(bot[2])],
            "n_h": len(hs), "n_v": len(vs)}


if __name__ == "__main__":
    vol, page = sys.argv[1], int(sys.argv[2])
    g = render(vol, page)
    r = detect_frame(g)
    print(json.dumps({"page": f"{vol}_{page:04d}", **(r or {"frame": None})}, ensure_ascii=False))
