#!/usr/bin/env python3
"""描迹保真度实验：vector 轮廓光栅化 vs 源二值墨迹 的 IoU，比较不同 tracing 变体。"""
import json, os, sys
import numpy as np, cv2
sys.path.insert(0, "scripts"); sys.path.insert(0, "work/font/_pylibs")
import font_norm as FN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rasterize(contours, shape):
    """把像素坐标轮廓（y 向下）填充成 mask。"""
    mask = np.zeros(shape, np.uint8)
    for c in contours:
        pts = [tuple(c["start"])]
        for s in c["segs"]:
            if s[0] == "L":
                pts.append((s[1], s[2]))
            else:
                pts.extend([(s[1], s[2]), (s[3], s[4]), (s[5], s[6])])
        poly = np.array([[int(round(x)), int(round(y))] for x, y in pts], np.int32)
        cv2.fillPoly(mask, [poly], 1)
    return mask


def prep_ink(page, box, pad=6):
    gray = FN.render_pdf_crop(page, box, pad150=pad, dpi=300)
    ink = FN.binarize(gray)
    ink = FN.remove_specks(ink)
    ink = FN.strip_border_lines(ink)
    h, w = ink.shape
    p = pad * 2
    center = (p, p, w - p, h - p)
    ink = FN.clean_cluster(ink, box=center)
    ink = FN.clean_ink(ink, center=center)
    return ink, center


def trace_variant(ink, variant):
    if variant == "base":
        cs = FN.trace(ink)
    elif variant == "dilate1":
        k = np.ones((3, 3), np.uint8)
        cs = FN.trace(cv2.dilate(ink.astype(np.uint8), k).astype(bool))
    elif variant == "upscale2":
        up = cv2.resize(ink.astype(np.uint8), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST).astype(bool)
        cs = FN.trace(up, turdsize=12)
        for c in cs:
            c["start"] = [v / 2 for v in c["start"]]
            for s in c["segs"]:
                if s[0] == "L":
                    s[1] /= 2; s[2] /= 2
                else:
                    for k in range(1, 7):
                        s[k] /= 2
    elif variant == "upscale3":
        up = cv2.resize(ink.astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST).astype(bool)
        cs = FN.trace(up, turdsize=27)
        for c in cs:
            c["start"] = [v / 3 for v in c["start"]]
            for s in c["segs"]:
                if s[0] == "L":
                    s[1] /= 3; s[2] /= 3
                else:
                    for k in range(1, 7):
                        s[k] /= 3
    else:
        raise ValueError(variant)
    return cs


def main():
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2410.json"), encoding="utf-8"))["chars"]
    chars = sorted(man)[:60]
    print("chars", len(chars))
    stats = {}
    for variant in ("base", "dilate1", "upscale2", "upscale3"):
        ious = []
        for ch in chars:
            r = man[ch]
            try:
                ink, center = prep_ink(r["page"], r["box"])
                cs = trace_variant(ink, variant)
                if not cs:
                    continue
                mask = rasterize(cs, ink.shape)
                inter = int((mask & ink).sum()); union = int((mask | ink).sum())
                ious.append(inter / max(1, union))
            except Exception as e:
                print("err", ch, e)
        stats[variant] = {"mean_iou": round(float(np.mean(ious)), 4),
                          "median": round(float(np.median(ious)), 4),
                          "n": len(ious)}
        print(variant, stats[variant], flush=True)
    json.dump(stats, open(os.path.join(ROOT, "work/lead/v2411_trace_fidelity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
