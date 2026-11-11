#!/usr/bin/env python3
"""Lead · 给全部字头几何候选打「字头概率」（复用 lead_hw_clf.py 的模型）。"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lead_hw_clf import feat


def _work(args):
    chunk, w, b, mu, sd = args
    import fitz, cv2
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    docs = {}
    out = []
    for page in chunk:
        vol = page[:2]; pg = int(page[3:])
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        try:
            fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300", page + ".json"),
                                encoding="utf-8"))
        except Exception:
            continue
        for half in ("R", "L"):
            for c in fj["halves"][half]["cands"]:
                h = c.get("h", 0); wid = c.get("w", 0)
                if not ((70 <= h <= 112 and 55 <= wid <= 118 and 0.62 <= wid / max(1, h) <= 1.6)
                        or (10 <= h <= 48 and 50 <= wid <= 120 and wid / max(1, h) <= 8)):
                    continue
                box = [int(v) * 2 for v in c["box"]]
                crop = img[box[1]:box[3], box[0]:box[2]]
                if crop.size == 0 or min(crop.shape) < 20:
                    continue
                f = (feat(crop) - np.array(mu)) / np.array(sd)
                z = float(np.dot(f, np.array(w)) + b)
                p = 1.0 / (1.0 + np.exp(-z))
                out.append({"page": page, "half": half, "box": c["box"], "p": round(p, 4)})
    for d in docs.values():
        d.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(ROOT, "work/lead/hw_clf.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hw_prob.jsonl"))
    ap.add_argument("--procs", type=int, default=8)
    args = ap.parse_args()
    import multiprocessing as mp
    model = json.load(open(args.model))
    # 页列表
    pages = []
    for f in sorted(os.listdir(os.path.join(ROOT, "work/lead/boxes300"))):
        if f.endswith(".json"):
            pages.append(f[:-5])
    print("pages", len(pages), flush=True)
    chunks = [pages[i::args.procs] for i in range(args.procs)]
    jobs = [(c, model["w"], model["b"], model["mu"], model["sd"]) for c in chunks]
    with open(args.out, "w", encoding="utf-8") as fo, mp.Pool(args.procs) as pool:
        n = 0
        for rows in pool.imap_unordered(_work, jobs):
            for r in rows:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += len(rows)
            fo.flush()
            print("cum", n, flush=True)
    print("done", args.out)


if __name__ == "__main__":
    main()
