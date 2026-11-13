#!/usr/bin/env python3
"""Lead · 部界锚点 v2：用「字头 OCR 读到的字 → 部首」逐页投票，做单调分段 DP。

思路：高置信字头 OCR 文本给出每个框的真实字 → 其正典部首；一页上的投票应当集中在该页所属部。
DP：每卷把 页序列 切成 len(radicals) 个连续段（每部≥1 页），代价 = 每页「与段部首不符的票数」。
输出 work/lead/bu_start_pages_lead3.jsonl
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", default=os.path.join(ROOT, "work/lead/ocr_all3.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead3.jsonl"))
    ap.add_argument("--min-score", type=float, default=0.85)
    ap.add_argument("--prior", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--prior-w", type=float, default=1.2)
    args = ap.parse_args()
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    char_rad = {}
    for e in canon:
        ch = e["char"]
        if ch in char_rad and char_rad[ch] != e["rad"]:
            char_rad[ch] = None      # 同字多部 → 不可用
        else:
            char_rad.setdefault(ch, e["rad"])
    vr = json.load(open(os.path.join(ROOT, "work/seq/volume_radicals.json")))
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    # 逐页投票
    page_votes = collections.defaultdict(collections.Counter)
    for line in open(args.ocr, encoding="utf-8"):
        r = json.loads(line)
        texts = [(r.get("t5", ""), float(r.get("s5", 0))), (r.get("t6", ""), float(r.get("s6", 0))),
                 (r.get("t5e", ""), float(r.get("s5e", 0))), (r.get("t6e", ""), float(r.get("s6e", 0)))]
        best = max([t for t in texts if len(t[0]) == 1], key=lambda x: x[1], default=None)
        if best is None or best[1] < args.min_score:
            continue
        ch = best[0]
        rad = char_rad.get(ch)
        if rad is None:
            continue
        page_votes[r["page"]][rad] += 1
    prior = {}
    for l in open(args.prior, encoding="utf-8"):
        a = json.loads(l)
        prior[(a["vol"], a["radical"])] = a["page"]
    out_rows = []
    for vol in sorted(vr["volumes"]):
        info = vr["volumes"][vol]
        radicals = []
        for j in info["juan"]:
            radicals.extend(j["radicals"])
        pages = sorted(roles[vol])
        n = len(pages)
        m = len(radicals)
        if n < m:
            continue
        # 票矩阵
        V = np.zeros((n, m))
        rad_index = {r: i for i, r in enumerate(radicals)}
        for i, p in enumerate(pages):
            votes = page_votes.get(f"{vol}_{p:04d}")
            if not votes:
                continue
            for rad, c in votes.items():
                j = rad_index.get(rad)
                if j is not None:
                    V[i, j] += c
        total_votes = V.sum(axis=1)
        # dp[i][j] = 前 i 页分给前 j 部 的最小代价（第 j 部最后一页含 i-1）
        INF = 1e18
        dp = np.full((n + 1, m + 1), INF)
        bk = np.zeros((n + 1, m + 1), dtype=np.int32)
        dp[0, 0] = 0
        for j in range(1, m + 1):
            for i in range(j, n - (m - j) + 1):
                # 段 [k, i) 属于第 j 部；代价 = 该段内 总票 - 命中 j 的票
                best = INF; bk_i = -1
                p0 = prior.get((vol, radicals[j - 1]))
                for k in range(j - 1, i):
                    prev = dp[k, j - 1]
                    if prev >= INF / 2:
                        continue
                    seg_total = total_votes[k:i].sum()
                    seg_hit = V[k:i, j - 1].sum()
                    cost = prev + (seg_total - seg_hit) * 1.0
                    if p0 is not None:
                        cost += args.prior_w * abs(pages[k] - p0)
                    if cost < best:
                        best, bk_i = cost, k
                dp[i, j] = best
                bk[i, j] = bk_i
        if dp[n, m] >= INF / 2:
            print("vol", vol, "DP fail")
            continue
        # 回溯段边界
        bounds = []
        i, j = n, m
        while j > 0:
            k = int(bk[i, j])
            bounds.append(k)
            i, j = k, j - 1
        bounds.append(0)
        bounds.reverse()   # bounds[j] = 第 j 部起始页 index
        for idx, rad in enumerate(radicals):
            start = pages[bounds[idx + 1]]
            juan = None
            for jj in info["juan"]:
                if rad in jj["radicals"]:
                    juan = jj["juan"]
            out_rows.append({"vol": vol, "page": start, "radical": rad, "juan": juan,
                             "score": None})
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("anchors", len(out_rows), "->", args.out)


if __name__ == "__main__":
    main()
