#!/usr/bin/env python3
"""Lead · 版心数字/畫 模板挖掘与画数识别（自监督）。

流程：
1. 读 work/lead/hdr_cells.npz（版心柱切格，40x40 归一化）；
2. 对每页取**最下部**若干格（畫数/葉码 所在区）；
3. PCA + kmeans 聚类 → 输出 clusters.png 供人工标注（cluster→char）；
4. 用标注后的簇做分类器：每页自底向上把格分类成 数字/畫/其他；
   解析「数字*+畫」字段（顶部为第一个字段），底部残余数字串 = 葉码；
5. 输出 work/lead/headers_digits.jsonl {page,half:"L",hua:[..],leaf_digits,conf}
用法：
  .venv/bin/python scripts/lead_hdr_digits.py --cluster          # 生成 clusters.png
  .venv/bin/python scripts/lead_hdr_digits.py --labels work/lead/hdr_cluster_labels.json --out work/lead/headers_digits.jsonl
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2
cv2.setNumThreads(6)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_CH = "一二三四五六七八九十廿卅卌百"
NUMV = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
        "九": 9, "十": 10, "廿": 20, "卅": 30, "卌": 40, "百": 100}


def load_cells(path, bottom_k=8):
    z = np.load(path, allow_pickle=True)
    pages = z["pages"]; boxes = z["boxes"]; imgs = z["imgs"]
    meta = json.loads(str(z["meta"]))
    by_page = collections.defaultdict(list)
    for i, (pi, y0, y1, n) in enumerate(boxes):
        by_page[int(pi)].append((int(y0), int(y1), imgs[i]))
    out = {}
    for pi, page in enumerate(pages):
        cells = sorted(by_page.get(pi, []), key=lambda t: t[0])
        out[str(page)] = cells
    return out


def cluster(cells_by_page, k, bottom_k=8):
    feats, meta = [], []
    for page, cells in cells_by_page.items():
        for idx, (y0, y1, m) in enumerate(cells[-bottom_k:]):
            feats.append(m.ravel())
            meta.append({"page": page, "y0": y0, "y1": y1,
                         "rank_from_bottom": len(cells[-bottom_k:]) - idx - 1})
    X = np.stack(feats)
    Zn = (X > 0.45).astype(np.float32)
    Zn = Zn - Zn.mean(axis=1, keepdims=True)
    Zn /= (np.linalg.norm(Zn, axis=1, keepdims=True) + 1e-6)
    rng = np.random.default_rng(0)
    samp = Zn[rng.choice(len(Zn), min(5000, len(Zn)), replace=False)]
    U, S, Vt = np.linalg.svd(samp, full_matrices=False)
    P = Vt[:48].T
    Xp = Zn @ P
    Xp /= (np.linalg.norm(Xp, axis=1, keepdims=True) + 1e-6)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 80, 1e-4)
    _, labels, centers = cv2.kmeans(Xp.astype(np.float32), k, None, crit, 6,
                                    cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    return X, labels, P, Xp, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default=os.path.join(ROOT, "work/lead/hdr_cells.npz"))
    ap.add_argument("--cluster", action="store_true")
    ap.add_argument("--k", type=int, default=80)
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "work/lead/hdr_digits"))
    ap.add_argument("--labels", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/headers_digits.jsonl"))
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    cells = load_cells(args.cells)
    print("pages", len(cells), "cells", sum(len(v) for v in cells.values()))
    if args.cluster:
        X, labels, P, Xp, meta = cluster(cells, args.k)
        np.savez_compressed(os.path.join(args.out_dir, "cluster.npz"),
                            X=X, labels=labels, P=P, Xp=Xp)
        json.dump(meta, open(os.path.join(args.out_dir, "meta.json"), "w"),
                  ensure_ascii=False)
        cnt = collections.Counter(labels.tolist())
        order = [l for l, _ in cnt.most_common()]
        from PIL import Image, ImageDraw, ImageFont
        try:
            fnt = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", 18)
        except Exception:
            fnt = ImageFont.load_default()
        T = 92
        cols = 12
        rows = (len(order) + cols - 1) // cols
        S = Image.new("L", (cols * (T + 8), rows * (T + 30)), 255)
        d = ImageDraw.Draw(S)
        for k, l in enumerate(order):
            idxs = np.where(labels == l)[0]
            x = (k % cols) * (T + 8)
            y = (k // cols) * (T + 30)
            S.paste(Image.fromarray((X[idxs[0]].reshape(40, 40) * 255).astype(np.uint8))
                    .resize((T, T), Image.LANCZOS), (x, y + 26))
            d.text((x + 2, y + 2), f"c{l}:{cnt[l]}", font=fnt, fill=0)
        S.save(os.path.join(args.out_dir, "clusters.png"))
        print("clusters ->", os.path.join(args.out_dir, "clusters.png"),
              "top", [(l, cnt[l]) for l in order[:15]])
        return
    # 分类 + 解析
    z = np.load(os.path.join(args.out_dir, "cluster.npz"))
    X, labels, P, Xp = z["X"], z["labels"], z["P"], z["Xp"]
    meta = json.load(open(os.path.join(args.out_dir, "meta.json")))
    lab = json.load(open(args.labels, encoding="utf-8"))
    # 每簇的字符（人工标注）；未标注的簇忽略
    Pz = (X > 0.45).astype(np.float32)
    Pz = Pz - Pz.mean(axis=1, keepdims=True)
    Pz /= (np.linalg.norm(Pz, axis=1, keepdims=True) + 1e-6)
    Xp2 = Pz @ P
    Xp2 /= (np.linalg.norm(Xp2, axis=1, keepdims=True) + 1e-6)
    # 用簇中心做分类
    cents = {}
    for l in set(labels.tolist()):
        if str(l) in lab:
            cents[l] = Xp2[labels == l].mean(axis=0)
    import collections as C
    def classify(vec):
        best = (0.0, None)
        for l, c in cents.items():
            s = float(np.dot(vec, c))
            if s > best[0]:
                best = (s, l)
        return best
    # 每页：底部格序列
    recs = []
    for page, cs in cells.items():
        tail = cs[-8:]
        if not tail:
            continue
        chars = []
        for (y0, y1, m) in tail:
            vec = (m.ravel() > 0.45).astype(np.float32)
            vec = vec - vec.mean()
            vec /= (np.linalg.norm(vec) + 1e-6)
            q = vec @ P
            q /= (np.linalg.norm(q) + 1e-6)
            s, l = classify(q)
            ch = lab.get(str(l)) if l is not None else None
            chars.append({"y0": y0, "y1": y1, "ch": ch, "score": round(s, 2)})
        recs.append({"page": page, "cells": chars})
    json.dump(recs, open(os.path.join(args.out_dir, "tail_chars.json"), "w"),
              ensure_ascii=False)
    print("wrote", os.path.join(args.out_dir, "tail_chars.json"))


if __name__ == "__main__":
    main()
