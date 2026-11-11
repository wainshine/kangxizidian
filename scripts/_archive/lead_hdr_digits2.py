#!/usr/bin/env python3
"""Lead · 版心数字模板自监督挖掘 v2（用 葉码=页−5 公式做真值标注）。

1. 每页取最底部格（= 葉码末字）；用「葉码书写规则」给每页一个已知末字；
2. 对这些格聚类 → 每簇按已知末字投票 → 得到数字模板（自监督）；
3. 再用模板分类**所有**底部格，自底向上解析「数字*+畫」字段（畫 簇由人工/结构确认）；
4. 输出 headers_digits.jsonl（page,half:L,hua,leaf_digits,conf）。
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2
cv2.setNumThreads(6)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_CH = "一二三四五六七八九十廿卅卌百"
DIGITS = list("一二三四五六七八九")


def leaf_last_char(n):
    """葉码书写规则（内府本实测：22=廿二、105=百五）→ 末字。"""
    if n in (20,):
        return "廿"
    if n in (30,):
        return "卅"
    if n in (40,):
        return "卌"
    if n == 100 or n == 200 or n == 300:
        return "百"
    r = n % 10
    if r == 0:
        return "十"
    return DIGITS[r - 1]


def load(path, bottom_k=10):
    z = np.load(path, allow_pickle=True)
    pages = [str(p) for p in z["pages"]]
    boxes = z["boxes"]; imgs = z["imgs"]
    by = collections.defaultdict(list)
    for i, (pi, y0, y1, n) in enumerate(boxes):
        by[int(pi)].append((int(y0), int(y1), imgs[i]))
    out = {}
    for pi, page in enumerate(pages):
        out[page] = sorted(by.get(pi, []), key=lambda t: t[0])
    return out


def feat(m):
    v = m.ravel()
    z = (v > 0.45).astype(np.float32)
    z = z - z.mean()
    return z / (np.linalg.norm(z) + 1e-6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default=os.path.join(ROOT, "work/lead/hdr_cells.npz"))
    ap.add_argument("--k", type=int, default=60)
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "work/lead/hdr_digits2"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/headers_digits.jsonl"))
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    cells = load(args.cells)
    # 1) 底格 + 已知末字
    rows = []
    for page, cs in cells.items():
        leaf = int(page[3:]) - 5
        if leaf < 1 or not cs:
            continue
        exp = leaf_last_char(leaf)
        rows.append((page, cs[-1][2], exp, leaf))
    print("pages with bottom cell:", len(rows))
    X = np.stack([feat(m) for _, m, _, _ in rows])
    # 2) 聚类 + 投票
    rng = np.random.default_rng(0)
    samp = X[rng.choice(len(X), min(6000, len(X)), replace=False)]
    U, S, Vt = np.linalg.svd(samp, full_matrices=False)
    P = Vt[:48].T
    Xp = X @ P
    Xp /= (np.linalg.norm(Xp, axis=1, keepdims=True) + 1e-6)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-4)
    _, labels, centers = cv2.kmeans(Xp.astype(np.float32), args.k, None, crit, 6,
                                    cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    votes = collections.defaultdict(collections.Counter)
    for (page, m, exp, leaf), l in zip(rows, labels):
        votes[int(l)][exp] += 1
    cluster_label = {}
    for l, cnt in votes.items():
        ch, n = cnt.most_common(1)[0]
        tot = sum(cnt.values())
        if n / tot >= 0.70 and n >= 8:
            cluster_label[l] = ch
    print("labeled clusters:", len(cluster_label), "of", len(votes))
    for l in sorted(cluster_label):
        print(f"  c{l}: {cluster_label[l]}  n={sum(votes[l].values())} pure={votes[l][cluster_label[l]]/sum(votes[l].values()):.2f}")
    # 保存模板（簇中心在 PCA 空间 + 原始均值图）
    cent = {l: Xp[labels == l].mean(axis=0) for l in cluster_label}
    np.savez_compressed(os.path.join(args.out_dir, "templates.npz"),
                        P=P, cent=np.stack([cent[l] for l in sorted(cent)]),
                        cent_labels=np.array(sorted(cent)))
    json.dump({str(k): v for k, v in cluster_label.items()},
              open(os.path.join(args.out_dir, "cluster_labels.json"), "w"),
              ensure_ascii=False)
    # 3) 分类全部底部格
    all_feat = {}
    for page, cs in cells.items():
        tail = cs[-9:]
        all_feat[page] = [feat(m) for _, _, m in tail]
    # 4) 解析：自下而上 数字串→畫 字段
    recs = []
    for page, vecs in all_feat.items():
        chars = []
        for v in vecs:
            q = v @ P
            q /= (np.linalg.norm(q) + 1e-6)
            best = (0.0, None)
            for l in sorted(cent):
                s = float(np.dot(q, cent[l]))
                if s > best[0]:
                    best = (s, l)
            sc, l = best
            chars.append((cluster_label.get(l), round(sc, 3)))
        recs.append({"page": page, "tail": chars})
    json.dump(recs, open(os.path.join(args.out_dir, "tail_labeled.json"), "w"),
              ensure_ascii=False)
    print("wrote", os.path.join(args.out_dir, "tail_labeled.json"))


if __name__ == "__main__":
    main()
