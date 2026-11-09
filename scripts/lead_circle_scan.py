#!/usr/bin/env python3
"""圈注序号全量扫描：从字形缓存轮廓光栅化 160px → Hough 圆 + 环覆盖率检测。

输出 work/lead/circle_marks.json: {char, cx, cy, r, ring_cov}
"""
import json, os, sys, glob
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def raster(contours, size=160):
    mask = np.zeros((size, size), np.uint8)
    for c in contours:
        pts = [(c["start"][0], c["start"][1])]
        for s in c["segs"]:
            if s[0] == "L":
                pts.append((s[1], s[2]))
            else:
                pts += [(s[1], s[2]), (s[3], s[4]), (s[5], s[6])]
        poly = np.array([[int(x / 1000 * size), int((1000 - y) / 1000 * size)] for x, y in pts],
                        np.int32)
        if len(poly) >= 3:
            cv2.fillPoly(mask, [poly], 255)
    return mask


def main():
    cache = glob.glob(os.path.join(ROOT, "work/font/build/cache/*.json"))
    print("cache files", len(cache), flush=True)
    marks = []
    for i, p in enumerate(cache):
        try:
            rec = json.load(open(p))
        except Exception:
            continue
        if not rec.get("ok"):
            continue
        # 文件名: page+half_char_x0_y0_x1_y1.json
        base = os.path.basename(p).rsplit(".", 1)[0]
        parts = base.split("_")
        ch = parts[2] if len(parts) > 2 else ""
        img = raster(rec["contours"])
        g = cv2.GaussianBlur(img, (5, 5), 0)
        s2 = img.shape[0]
        cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=s2 * 0.5,
                              param1=140, param2=58,
                              minRadius=int(0.32 * s2), maxRadius=int(0.58 * s2))
        if cs is None:
            continue
        ink = img > 127
        for c in cs[0]:
            cx, cy, r = float(c[0]), float(c[1]), float(c[2])
            if abs(cx - s2 / 2) > 0.25 * s2 or abs(cy - s2 / 2) > 0.25 * s2:
                continue
            th = np.linspace(0, 2 * np.pi, 360)
            hit = 0
            for t in th:
                x = int(round(cx + r * np.cos(t))); y = int(round(cy + r * np.sin(t)))
                if 0 <= y < s2 and 0 <= x < s2 and ink[max(0, y - 3):y + 4, max(0, x - 3):x + 4].any():
                    hit += 1
            cov = hit / 360
            if cov >= 0.52:
                marks.append({"char": ch, "file": base, "cx": round(cx, 1),
                              "cy": round(cy, 1), "r": round(r, 1),
                              "ring_cov": round(cov, 2)})
                break
        if (i + 1) % 2000 == 0:
            print("scanned", i + 1, "marks", len(marks), flush=True)
    json.dump(marks, open(os.path.join(ROOT, "work/lead/circle_marks.json"), "w"),
              ensure_ascii=False, indent=1)
    print("done", len(marks))


if __name__ == "__main__":
    main()
