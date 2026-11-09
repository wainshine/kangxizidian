#!/usr/bin/env python3
"""候选框墨迹统计：ink_frac / p90 stroke width（判字头 vs 注文合并框）。"""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _work(chunk):
    import fitz, cv2
    import numpy as np
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    docs = {}
    out = []
    for page in chunk:
        vol = page[:2]; pg = int(page[3:])
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        h_page, w_page = img.shape
        try:
            fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300", page + ".json"),
                                encoding="utf-8"))
        except Exception:
            continue
        for half in ("R", "L"):
            for c in fj["halves"][half]["cands"]:
                h = c.get("h", 0); w = c.get("w", 0)
                geo = ((70 <= h <= 112 and 55 <= w <= 118 and 0.62 <= w / max(1, h) <= 1.6)
                       or (10 <= h <= 48 and 50 <= w <= 120 and w / max(1, h) <= 8))
                if not geo:
                    continue
                b = [int(v) * 2 for v in c["box"]]
                b = [max(0, b[0]), max(0, b[1]), min(w_page, b[2]), min(h_page, b[3])]
                crop = img[b[1]:b[3], b[0]:b[2]]
                if crop.size == 0 or min(crop.shape) < 8:
                    continue
                ink = (crop < 140).astype(np.uint8)
                ink = cv2.medianBlur(ink * 255, 3) // 255
                if ink.sum() < 30:
                    continue
                dist = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
                vals = dist[ink > 0]
                out.append({"page": page, "half": half, "box": c["box"],
                            "h": h, "w": w, "y0": c["box"][1],
                            "ink": round(float((ink > 0).mean()), 4),
                            "p90": round(float(np.percentile(vals, 90)), 3),
                            "dt_mean": round(float(vals.mean()), 3)})
    for d in docs.values():
        d.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/cand_stats.jsonl"))
    ap.add_argument("--procs", type=int, default=8)
    args = ap.parse_args()
    import multiprocessing as mp
    pages = sorted(f[:-5] for f in os.listdir(os.path.join(ROOT, "work/lead/boxes300"))
                   if f.endswith(".json"))
    chunks = [pages[i::args.procs] for i in range(args.procs)]
    with open(args.out, "w", encoding="utf-8") as f, mp.Pool(args.procs) as pool:
        n = 0
        for rows in pool.imap_unordered(_work, chunks):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += len(rows)
            f.flush()
            print("cum", n, flush=True)
    print("done", args.out)


if __name__ == "__main__":
    main()
