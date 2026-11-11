#!/usr/bin/env python3
"""Lead · 「重出对」视觉检测：每页相邻字头框的归一化 NCC（与标签无关）。

正典有 1,886 对「相邻同字」（重出），书页上相邻印刷、字形高度相似。
输出 work/lead/dup_pairs.jsonl：{page, half, pairs:[{i,j,sim,box_i,box_j,ci_pred}]}
ci_pred 由当前 mapping 给出（仅参考，不参与检测）。
"""
import argparse, json, os, sys, collections
import numpy as np, cv2
cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def norm40(m, size=40):
    m = (m > 0).astype(np.uint8)
    ys, xs = np.where(m > 0)
    if len(ys) < 30:
        return None
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h, w = m.shape
    s = size / max(h, w)
    mm = cv2.resize(m, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    c = np.zeros((size, size), np.float32)
    c[(size - mm.shape[0]) // 2:(size - mm.shape[0]) // 2 + mm.shape[0],
      (size - mm.shape[1]) // 2:(size - mm.shape[1]) // 2 + mm.shape[1]] = mm
    c = c - c.mean()
    return c / (np.linalg.norm(c) + 1e-6)


def _job(args):
    vol, pages = args
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    out = []
    for pg in pages:
        try:
            fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300",
                                             f"{vol}_{pg:04d}.json"), encoding="utf-8"))
            pix = doc[pg - 1].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            recs = []
            for half in ("R", "L"):
                cands = [c for c in fj["halves"][half]["cands"]
                         if c["cls"]["headword"] >= 0.5 and c["h"] >= 55
                         and c["w"] >= 35 and c["feat"].get("squareness", 0) > 0.6]
                vecs = []
                for c in cands:
                    x0, y0, x1, y1 = [int(v) for v in c["box"]]
                    crop = img[max(0, y0 - 3):y1 + 3, max(0, x0 - 3):x1 + 3]
                    v = norm40((crop < 150)) if crop.size else None
                    vecs.append(v)
                pairs = []
                for i in range(len(cands) - 1):
                    if vecs[i] is None or vecs[i + 1] is None:
                        continue
                    s = float((vecs[i] * vecs[i + 1]).sum())
                    if s >= 0.60:
                        pairs.append({"i": i, "j": i + 1, "sim": round(s, 3),
                                      "box_i": cands[i]["box"], "box_j": cands[i + 1]["box"]})
                recs.append({"half": half, "n": len(cands), "pairs": pairs})
            out.append((f"{vol}_{pg:04d}", recs))
        except Exception:
            out.append((f"{vol}_{pg:04d}", []))
    doc.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/dup_pairs.jsonl"))
    args = ap.parse_args()
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    jobs = []
    for vol in sorted(roles):
        ps = sorted(roles[vol])
        k = max(1, len(ps) // args.workers + 1)
        for i in range(0, len(ps), k):
            jobs.append((vol, ps[i:i + k]))
    from multiprocessing import Pool
    allres = []
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(_job, jobs):
            allres.extend(res)
    allres.sort()
    npg = 0
    npair = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for page, recs in allres:
            if not recs:
                continue
            npg += 1
            npair += sum(len(r["pairs"]) for r in recs)
            f.write(json.dumps({"page": page, "halves": recs}, ensure_ascii=False) + "\n")
    print("pages", npg, "pairs", npair, "->", args.out)


if __name__ == "__main__":
    main()
