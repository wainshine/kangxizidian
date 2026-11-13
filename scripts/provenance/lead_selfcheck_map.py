#!/usr/bin/env python3
"""Lead · mapping 自校验：用「重出（相邻同字）」对 + 随机对照，量化映射对齐质量。

原理：正典序里相邻两条同字（重出：刻本同一字头下再出一次）在书页上应相邻；
若映射对齐正确，两条被指派框的字形高度相似；错位时相似度掉到随机水平。
输出分卷/分册相似度（与随机基线的差距）。
"""
import argparse, json, os, collections
import numpy as np
import cv2
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
cv2.setNumThreads(1)


def norm(m, size=40):
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


def crop(img, box, pad=4):
    x0, y0, x1, y1 = [int(v) for v in box]
    H, W = img.shape
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(W, x1 + pad); y1 = min(H, y1 + pad)
    sub = img[y0:y1, x0:x1]
    if sub.size == 0:
        return None
    return (sub < 150).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", default=os.path.join(ROOT, "work/map/v3full/mapping.jsonl"))
    ap.add_argument("--canonical", default=os.path.join(ROOT, "work/seq/canonical.jsonl"))
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--max-pairs", type=int, default=400)
    args = ap.parse_args()
    seq = [json.loads(l) for l in open(args.canonical, encoding="utf-8")]
    # 相邻同字对
    dup = []
    for i in range(1, len(seq)):
        if seq[i]["char"] == seq[i - 1]["char"]:
            dup.append((i - 1, i))
    print("duplicate adjacent pairs:", len(dup))
    # 映射：ci -> (page, half, idx)
    pos = {}
    for line in open(args.mapping, encoding="utf-8"):
        r = json.loads(line)
        for j, a in enumerate(r["assigned"]):
            pos[r["ci_start"] + j] = (r["page"], r["half"], a)
    # 取样本
    rng = np.random.default_rng(0)
    chosen = [d for d in dup if d[0] in pos and d[1] in pos]
    if len(chosen) > args.max_pairs:
        idx = rng.choice(len(chosen), args.max_pairs, replace=False)
        chosen = [chosen[i] for i in idx]
    print("usable pairs:", len(chosen))
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    import fitz
    docs = {}
    cache = {}

    def page_img(page):
        if page in cache:
            return cache[page]
        vol = page[:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=args.dpi,
                                                   colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        cache[page] = img
        return img

    def vec(ci):
        page, half, a = pos[ci]
        img = page_img(page)
        cropped = crop(img, a["cand"]["box"])
        return None if cropped is None else norm(cropped)

    same, rnd = [], []
    byvol = collections.defaultdict(list)
    for i, j in chosen:
        va = vec(i); vb = vec(j)
        if va is None or vb is None:
            continue
        s = float((va * vb).sum())
        same.append(s)
        byvol[pos[i][0][:2]].append(s)
    # 随机对照：打乱配对
    keys = list(pos.keys())
    for _ in range(min(len(same), 300)):
        i = int(rng.choice(keys)); j = int(rng.choice(keys))
        if i == j:
            continue
        va = vec(i); vb = vec(j)
        if va is None or vb is None:
            continue
        rnd.append(float((va * vb).sum()))
    print(f"dup-pair sim mean={np.mean(same):.3f} median={np.median(same):.3f} n={len(same)}")
    print(f"random  sim mean={np.mean(rnd):.3f} median={np.median(rnd):.3f} n={len(rnd)}")
    for vol in sorted(byvol):
        a = np.array(byvol[vol])
        print(f"  vol {vol}: n={len(a)} mean={a.mean():.3f} median={np.median(a):.3f} >0.5:{(a>0.5).mean()*100:.0f}%")
    for d in docs.values():
        d.close()


if __name__ == "__main__":
    main()
