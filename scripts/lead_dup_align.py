#!/usr/bin/env python3
"""Lead · 重出对 ↔ 正典重出块 的序列对齐（DP）→ 页级锚点。

输入：work/lead/dup_pairs.jsonl（视觉检测）、work/map/<map>/mapping.jsonl（当前映射给位置先验）
输出：work/lead/dup_anchors.jsonl：{page, half, idx, ci, pair_sim, gap_ok}
"""
import argparse, json, os, sys, collections, bisect
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(ROOT, "work/lead/dup_pairs.jsonl"))
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/bu_v5"))
    ap.add_argument("--canonical", default=os.path.join(ROOT, "work/seq/canonical.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/dup_anchors.jsonl"))
    args = ap.parse_args()
    seq = [json.loads(l) for l in open(args.canonical, encoding="utf-8")]
    blocks = [i - 1 for i in range(1, len(seq)) if seq[i]["char"] == seq[i - 1]["char"]]
    m = {}
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        m[(r["page"], r["half"])] = r
    # 书内检测对（带估计 ci）
    book = []
    for l in open(args.pairs, encoding="utf-8"):
        rec = json.loads(l)
        page = rec["page"]
        for h in rec["halves"]:
            r = m.get((page, h["half"]))
            if not r:
                continue
            for p in h["pairs"]:
                book.append({"page": page, "half": h["half"], "i": p["i"],
                             "ci_est": r["ci_start"] + p["i"], "sim": p["sim"]})
    book.sort(key=lambda b: b["ci_est"])
    print("book pairs", len(book), "blocks", len(blocks))
    if not book:
        return
    n, k = len(book), len(blocks)
    BIG = 1e18
    # dp[i][j] = 前 i 个书对匹配到前 j 个块的累计最小代价（i 对 0..j 内，结束于 j-1）
    dp = np.full((n + 1, k + 1), BIG)
    bk = np.zeros((n + 1, k + 1), dtype=np.int32)
    for j in range(k + 1):
        dp[0][j] = 0.0
    for i in range(1, n + 1):
        bi = book[i - 1]["ci_est"]
        for j in range(i, k + 1):
            # 之前 i-1 对匹配到 ≤ j-1
            best = dp[i - 1][j - 1] if dp[i - 1][j - 1] < BIG else BIG
            if best < BIG:
                best = best + abs(blocks[j - 1] - bi) * 0.05
            # 允许跳过块：dp[i][j-1]
            if dp[i][j - 1] < best:
                best = dp[i][j - 1]
            dp[i][j] = best
            bk[i][j] = 1 if (dp[i][j - 1] == best and dp[i][j - 1] < BIG) else 0
    # 回溯
    matches = []
    i, j = n, k
    while i > 0 and j > 0:
        if bk[i][j] == 0:
            matches.append((i - 1, j - 1))
            i -= 1; j -= 1
        else:
            j -= 1
    matches.reverse()
    print("matched", len(matches))
    res = []
    for bi, bj in matches:
        b = book[bi]
        res.append({"page": b["page"], "half": b["half"], "i": b["i"],
                    "ci": int(blocks[bj]), "ci_est": int(b["ci_est"]),
                    "diff": int(blocks[bj] - b["ci_est"]), "sim": b["sim"]})
    with open(args.out, "w", encoding="utf-8") as f:
        for x in res:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    d = np.array([x["diff"] for x in res])
    print("diff mean", round(float(d.mean()), 1), "median", round(float(np.median(d)), 1),
          "|d|<=15:", int((abs(d) <= 15).sum()), "/", len(d))
    # 用 matched 的 diff 做局部校正：输出每 pair 的残差供拟合器用
    by_vol = collections.defaultdict(list)
    for x in res:
        by_vol[x["page"][:2]].append(x)
    for v in sorted(by_vol):
        dd = np.array([x["diff"] for x in by_vol[v]])
        print(f"  vol {v}: n={len(dd)} mean={dd.mean():.1f} median={np.median(dd):.0f} "
              f"|d|<=15:{(abs(dd)<=15).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
