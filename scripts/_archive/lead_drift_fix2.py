#!/usr/bin/env python3
"""Lead · 漂移校正 v3（EM 两轮）：字头 OCR δ 估计 + 部内平滑 + 迭代。

轮 1：用当前 mapping 的 ci_start 做预测 → 估计每半版 δ（高置信）→ 部内平滑 → counts_v6
轮 2：用 counts_v6 重建 mapping（solver）→ 重估 δ（范围更小、接受率更高）→ counts_v7
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3

MAXD = 90


def load_canon():
    return [json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"),
                                                encoding="utf-8")]


def load_ocr():
    ocr = collections.defaultdict(list)
    for l in open(os.path.join(ROOT, "work/lead/hw_ocr.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        if "err" in r or not r.get("text"):
            continue
        ocr[(r["page"], r["half"])].append(r)
    return ocr


def estimate_delta(canon, mapping, ocr, maxd=MAXD):
    est = {}
    box_cache = {}
    for (page, half), obss in ocr.items():
        r = mapping.get((page, half))
        if not r or not r["entries"]:
            continue
        if page not in box_cache:
            try:
                box_cache[page] = json.load(open(os.path.join(ROOT, "work/lead/boxes300",
                                                              page + ".json"), encoding="utf-8"))
            except Exception:
                box_cache[page] = None
        fj = box_cache[page]
        if fj is None:
            continue
        sel = [c for c in fj["halves"][half]["cands"] if is_head_v3(c, half)]
        box_to_pos = {tuple(int(v) for v in c["box"]): j for j, c in enumerate(sel)}
        n = len(r["entries"]); ci0 = r["ci_start"]
        well = []
        for o in obss:
            j = box_to_pos.get(tuple(int(v) for v in o["box"]))
            if j is None or j >= n or len(o["text"]) != 1:
                continue
            well.append((ci0 + j, o["text"], o["score"]))
        if len(well) < 1:
            continue
        best, best_d, second = -1.0, 0, -1.0
        for d in range(-maxd, maxd + 1):
            sc = 0.0
            for ci, t, s in well:
                if s < 0.35:
                    continue
                cc = ci + d
                if 0 <= cc < len(canon) and canon[cc] == t:
                    sc += s
            if sc > best:
                second = best; best, best_d = sc, d
            elif sc > second:
                second = sc
        if best >= 0.55 and best - second >= 0.15:
            est[(page, half)] = (best_d, max(0.05, best - second))
    return est


def build_seq():
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
    return seq


def smooth_delta(seq, est, segs, lam=2.0):
    delta = {}
    for seg in segs:
        idxs = [k for k in seq if k[0] == seg["vol"] and seg["lo"] <= k[1] <= seg["hi"]]
        m = len(idxs)
        if m < 2:
            for k in idxs:
                delta[(f"{k[0]}_{k[1]:04d}", k[2])] = 0.0
            continue
        w = np.zeros(m); y = np.zeros(m)
        for i, k in enumerate(idxs):
            key = (f"{k[0]}_{k[1]:04d}", k[2])
            if key in est:
                d, conf = est[key]
                w[i] = max(0.15, conf)
                y[i] = d
        A = np.zeros((m, m)); b = np.zeros(m)
        for i in range(m):
            A[i, i] += w[i]; b[i] += w[i] * y[i]
        for i in range(m - 1):
            A[i, i] += lam; A[i + 1, i + 1] += lam
            A[i, i + 1] -= lam; A[i + 1, i] -= lam
        A[0, 0] += 1e4; A[m - 1, m - 1] += 1e4
        sol = np.linalg.solve(A, b)
        for i, k in enumerate(idxs):
            delta[(f"{k[0]}_{k[1]:04d}", k[2])] = float(sol[i])
    return delta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/bu_v5"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--anchors", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v6.jsonl"))
    args = ap.parse_args()
    canon = load_canon()
    ocr = load_ocr()
    seq = build_seq()
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = int(r["n"])
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
            segs.append({"vol": vol, "lo": lo, "hi": hi})
    # EM 两轮
    mapping = {}
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        mapping[(r["page"], r["half"])] = r
    total = sum(counts.values())
    for it in range(2):
        est = estimate_delta(canon, mapping, ocr)
        print(f"iter {it}: δ 半版数", len(est))
        delta = smooth_delta(seq, est, segs)
        # 更新 counts 并重建 mapping 预测（仅 ci_start 平移）
        prev = 0.0
        new_counts = {}
        for (vol, pg, half) in seq:
            key = (f"{vol}_{pg:04d}", half)
            d = delta.get(key, 0.0)
            c = counts.get(key, 0)
            dd = int(round(d - prev)); prev = d
            new_counts[key] = max(0, c + dd)
        # 重建 mapping 的 ci_start（累计）
        cum = 0
        for (vol, pg, half) in seq:
            key = (f"{vol}_{pg:04d}", half)
            r = mapping.get(key)
            if r is not None:
                r["ci_start"] = cum
            cum += new_counts.get(key, 0)
        counts = new_counts
    # 输出
    out = []
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        c = counts.get(key, 0)
        out.append({"page": key[0], "half": half, "n": c, "rule": "v6-drift"})
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tot = sum(r["n"] for r in out)
    print("counts_v6 total", tot, "target", total)


if __name__ == "__main__":
    main()
