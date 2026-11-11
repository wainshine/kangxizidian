#!/usr/bin/env python3
"""Lead · 逐半版 δ 估计 v2：OCR 观测序列 vs 正典局部窗口的带约束 DP 对齐。

对每个半版：取该半版所有（位置已知的）OCR 单字观测，在正典 [pred_start-90, pred_end+90]
窗口内做单调对齐 DP：匹配字符得分=OCR置信度，跳过正典位置低成本，观测不匹配惩罚。
对齐后 δ_obs = canon_pos - pred_pos → 取中位数 = δ_half（若匹配数≥2 且一致性高）。
输出 work/lead/delta_dp.json：half -> [delta, n_match, consistency]
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3

W = 90


def align(obs, cwin, cstart):
    """obs: [(pred_ci, text, score)]；cwin: 该窗口的 canonical 字符；cstart: 窗口起始 ci。
    返回 [(obs_idx, canon_idx, delta)]。
    """
    k = len(obs); m = len(cwin)
    if k == 0 or m == 0:
        return []
    NEG = -1e9
    # dp[i][j] = 前 i 个 obs 匹配到前 j 个 canon 的最大分
    dp = np.full((k + 1, m + 1), NEG)
    bk = np.zeros((k + 1, m + 1), dtype=np.int8)  # 0=match,1=skip canon
    dp[0, :] = 0.0
    for i in range(1, k + 1):
        pc, t, s = obs[i - 1]
        for j in range(1, m + 1):
            # 跳过该 canon 位置
            best = dp[i, j - 1]
            b = 1
            # 匹配
            match = s if cwin[j - 1] == t else -0.35
            prev = dp[i - 1, j - 1]
            if prev > NEG / 2:
                sc = prev + match
                # 位置先验：|ci - pred| 大的略微惩罚
                dev = abs((cstart + j - 1) - pc)
                sc -= 0.01 * max(0, dev - 25)
                if sc > best:
                    best = sc; b = 0
            dp[i, j] = best
            bk[i, j] = b
    # 回溯
    i, j = k, m
    res = []
    while i > 0 and j > 0:
        if bk[i, j] == 0:
            res.append((i - 1, j - 1))
            i -= 1; j -= 1
        else:
            j -= 1
    res.reverse()
    out = []
    for oi, cj in res:
        pc = obs[oi][0]
        out.append((oi, cj, (cstart + cj) - pc))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/v12"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/delta_dp.json"))
    args = ap.parse_args()
    canon = [json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"),
                                                 encoding="utf-8")]
    mapping = {}
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        mapping[(r["page"], r["half"])] = r
    ocr = collections.defaultdict(list)
    for l in open(os.path.join(ROOT, "work/lead/hw_ocr.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        if "err" in r or not r.get("text"):
            continue
        ocr[(r["page"], r["half"])].append(r)
    out = {}
    cache = {}
    for (page, half), obss in ocr.items():
        r = mapping.get((page, half))
        if not r or not r["entries"]:
            continue
        if page not in cache:
            try:
                cache[page] = json.load(open(os.path.join(ROOT, "work/lead/boxes300",
                                                          page + ".json"), encoding="utf-8"))
            except Exception:
                cache[page] = None
        fj = cache[page]
        if fj is None:
            continue
        sel = [c for c in fj["halves"][half]["cands"] if is_head_v3(c, half)]
        b2p = {tuple(int(v) for v in c["box"]): j for j, c in enumerate(sel)}
        n = len(r["entries"]); ci0 = r["ci_start"]
        obs = []
        for o in obss:
            j = b2p.get(tuple(int(v) for v in o["box"]))
            if j is None or j >= n or len(o["text"]) != 1 or o["score"] < 0.35:
                continue
            obs.append((ci0 + j, o["text"], o["score"]))
        if len(obs) < 2:
            continue
        lo = max(0, ci0 - W)
        hi = min(len(canon), ci0 + n + W)
        cwin = canon[lo:hi]
        matches = align(obs, cwin, lo)
        # 只保留正匹配（字相同）
        ds = []
        for oi, cj, d in matches:
            if cwin[cj] == obs[oi][1] and obs[oi][2] >= 0.4:
                ds.append(d)
        if len(ds) >= 2:
            med = float(np.median(ds))
            cons = float(np.mean([abs(d - med) <= 3 for d in ds]))
            out[f"{page}|{half}"] = [med, len(ds), round(cons, 2)]
    json.dump(out, open(args.out, "w"), ensure_ascii=False)
    print("halves with δ:", len(out))
    vals = np.array([v[0] for v in out.values()])
    cons = np.array([v[2] for v in out.values()])
    print("δ mean", round(float(vals.mean()), 1), "median", float(np.median(vals)),
          "p10", float(np.percentile(vals, 10)), "p90", float(np.percentile(vals, 90)))
    print("consistent(≥0.8) halves:", int((cons >= 0.8).sum()))


if __name__ == "__main__":
    main()
