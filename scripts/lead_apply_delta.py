#!/usr/bin/env python3
"""Lead · 用「唯一字」锚点 delta 平滑拟合 → 校正逐页计数（counts_v7）。

delta 定义：真值 ci = 映射 ci + delta；部端点 delta=0（部总量精确）。
拟合：每部内 加权最小二乘 + 一阶平滑 + Huber 重加权（3 轮）。
输入：work/lead/delta_est_unique.json（half → [delta, n]）、counts_v5、部界锚点
输出：work/lead/counts_v7.jsonl
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--est", default=os.path.join(ROOT, "work/lead/delta_est_unique.json"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--anchors", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v7.jsonl"))
    ap.add_argument("--lam", type=float, default=1.0)
    args = ap.parse_args()
    est = {tuple(k.split("|")): v for k, v in json.load(open(args.est)).items()}
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = int(r["n"])
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    seq = []
    for vol in sorted(roles):
        for pg in sorted(roles[vol]):
            for half in ("R", "L"):
                seq.append((vol, pg, half))
    anchors = [json.loads(l) for l in open(args.anchors, encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    segs = []
    for vol in sorted(by_vol):
        ast = sorted(by_vol[vol], key=lambda x: x["page"])
        for i, a in enumerate(ast):
            lo = a["page"]
            hi = ast[i + 1]["page"] - 1 if i + 1 < len(ast) else 10 ** 9
            segs.append({"vol": vol, "lo": lo, "hi": hi, "rad": a["radical"]})
    delta = {}
    n_used = 0
    for seg in segs:
        idxs = [k for k in seq if k[0] == seg["vol"] and seg["lo"] <= k[1] <= seg["hi"]]
        m = len(idxs)
        if m < 3:
            for k in idxs:
                delta[(f"{k[0]}_{k[1]:04d}", k[2])] = 0.0
            continue
        y = np.zeros(m); w = np.zeros(m)
        for i, k in enumerate(idxs):
            key = (f"{k[0]}_{k[1]:04d}", k[2])
            if key in est:
                d, nn = est[key]
                y[i] = d
                w[i] = min(3.0, nn)
                n_used += 1
        if w.sum() == 0:
            for i, k in enumerate(idxs):
                delta[(f"{k[0]}_{k[1]:04d}", k[2])] = 0.0
            continue
        # 迭代重加权平滑
        ww = w.copy()
        for it in range(3):
            A = np.zeros((m, m)); b = np.zeros(m)
            for i in range(m):
                A[i, i] += ww[i]; b[i] += ww[i] * y[i]
            for i in range(m - 1):
                A[i, i] += args.lam; A[i + 1, i + 1] += args.lam
                A[i, i + 1] -= args.lam; A[i + 1, i] -= args.lam
            A[0, 0] += 1e4; A[m - 1, m - 1] += 1e4
            sol = np.linalg.solve(A, b)
            if it < 2:
                r = y - sol
                ww = w * np.minimum(1.0, 8.0 / (np.abs(r) + 1e-6))
        for i, k in enumerate(idxs):
            delta[(f"{k[0]}_{k[1]:04d}", k[2])] = float(sol[i])
    # 生成 counts_v7
    out = []
    prev = 0.0
    tot = 0
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        d = delta.get(key, 0.0)
        c = counts.get(key, 0)
        dd = int(round(d - prev)); prev = d
        n = max(0, c + dd)
        tot += n
        out.append({"page": key[0], "half": half, "n": n, "n_v5": c, "delta": dd,
                    "rule": "v7-delta"})
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("est halves used", n_used, "total", tot, "(target", sum(counts.values()), ")")


if __name__ == "__main__":
    main()
