#!/usr/bin/env python3
"""字形质量分类：对每个候选字形框计算笔画宽度（p90 距离变换）与墨量，
用于区分「字头大字」与「注文小字」（审计：小字混入字头字体）。

输出 work/lead/glyph_quality.jsonl: {char,page,half,box,w,h,ink,p90,src}
"""
import argparse, collections, json, os
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--union", default=os.path.join(ROOT, "work/lead/confirmed_union8.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/glyph_quality.jsonl"))
    args = ap.parse_args()
    import cv2
    import fitz
    union = json.load(open(args.union))
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    by_page = collections.defaultdict(list)
    for ch, r in union.items():
        by_page[r["page"]].append((ch, r))
    docs = {}
    out = []
    for pi, (page, items) in enumerate(sorted(by_page.items())):
        vol = page[:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        for ch, r in items:
            b = [int(v) * 2 for v in r["box"]]
            x0, y0 = max(0, b[0]), max(0, b[1])
            x1, y1 = min(img.shape[1], b[2]), min(img.shape[0], b[3])
            crop = img[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            thr, _ = cv2.threshold(cv2.medianBlur(crop, 3), 0, 255,
                                   cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            ink = (cv2.medianBlur(crop, 3) < min(max(int(thr), 100), 210)).astype(np.uint8)
            dt = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
            vals = dt[dt > 0]
            p90 = float(np.percentile(vals, 90)) if vals.size else 0.0
            out.append({"char": ch, "page": page, "half": r["half"], "box": r["box"],
                        "w": int(crop.shape[1]), "h": int(crop.shape[0]),
                        "ink": round(float(ink.mean()), 4), "p90": round(p90, 2),
                        "src": r.get("src", "")})
        if (pi + 1) % 400 == 0:
            print("pages", pi + 1, "glyphs", len(out), flush=True)
    for d in docs.values():
        d.close()
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("done", len(out))


if __name__ == "__main__":
    main()
