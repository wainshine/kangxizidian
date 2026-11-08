#!/usr/bin/env python3
"""Lead · δ(DP 估计) 平滑 → 计数校正 → 可行性投影（≤候选可用数）→ counts_v13。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", default=os.path.join(ROOT, "work/lead/delta_dp.json"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--avail", default=os.path.join(ROOT, "work/lead/avail_cands.json"))
    ap.add_argument("--anchors", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v13.jsonl"))
    args = ap.parse_args()
    est = {tuple(k.split("|")): v for k, v in json.load(open(args.delta)).items()}
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = int(r["n"])
    avail = {tuple(k.split("|")): v for k, v in json.load(open(args.avail)).items()}
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
            segs.append({"vol": vol, "lo": lo, "hi": hi, "entries": None})
    rad_entries = collections.Counter()
    for line in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8"):
        e = json.loads(line); rad_entries[e["rad"]] += 1
    for seg, anc in zip(segs, [a for v in sorted(by_vol) for a in sorted(by_vol[v],
                                                                       key=lambda x: x["page"])]):
        seg["entries"] = rad_entries[anc["radical"]]
    # 1) δ 平滑
    delta = {}
    used = 0
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
                d, nm, cons = est[key]
                if cons >= 0.6:
                    y[i] = d; w[i] = min(3.0, 0.5 + nm * 0.5); used += 1
        if w.sum() == 0:
            for i, k in enumerate(idxs):
                delta[(f"{k[0]}_{k[1]:04d}", k[2])] = 0.0
            continue
        ww = w.copy(); sol = np.zeros(m)
        for it in range(3):
            A = np.zeros((m, m)); b = np.zeros(m)
            for i in range(m):
                A[i, i] += ww[i]; b[i] += ww[i] * y[i]
            for i in range(m - 1):
                A[i, i] += 1.0; A[i + 1, i + 1] += 1.0
                A[i, i + 1] -= 1.0; A[i + 1, i] -= 1.0
            A[0, 0] += 1e4; A[m - 1, m - 1] += 1e4
            sol = np.linalg.solve(A, b)
            if it < 2:
                res = y - sol
                ww = w * np.minimum(1.0, 6.0 / (np.abs(res) + 1e-6))
        for i, k in enumerate(idxs):
            delta[(f"{k[0]}_{k[1]:04d}", k[2])] = float(sol[i])
    # 2) 校正计数
    out = {}
    prev = 0.0
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        d = delta.get(key, 0.0)
        dd = int(round(d - prev)); prev = d
        dd = max(-4, min(4, dd))
        out[key] = max(0, counts.get(key, 0) + dd)
    # 3) 可行性投影（每部 Σ=entries 且 n_h ≤ avail_h，多退少补）
    for seg in segs:
        keys = [k for k in out if k[0][:2] == seg["vol"] and seg["lo"] <= int(k[0][3:]) <= seg["hi"]]
        if not keys:
            continue
        # 先压到 avail
        for k in keys:
            out[k] = min(out[k], avail.get(k, 0))
        total = sum(out[k] for k in keys)
        target = seg["entries"]
        guard = 0
        while total != target and guard < 20000:
            guard += 1
            if total < target:
                cand = [k for k in keys if out[k] < avail.get(k, 0)]
                if not cand:
                    break
                cand.sort(key=lambda k: -(avail.get(k, 0) - out[k]))
                for k in cand:
                    if total >= target:
                        break
                    out[k] += 1; total += 1
            else:
                cand = [k for k in keys if out[k] > 0]
                if not cand:
                    break
                cand.sort(key=lambda k: -out[k])
                for k in cand:
                    if total <= target:
                        break
                    out[k] -= 1; total -= 1
    tot = sum(out.values())
    print("δ used halves:", used, "counts total:", tot, "(target 42302)")
    with open(args.out, "w", encoding="utf-8") as f:
        for (vol, pg, half) in seq:
            key = (f"{vol}_{pg:04d}", half)
            f.write(json.dumps({"page": key[0], "half": half, "n": out[key],
                                "n_v5": counts.get(key, 0), "rule": "v13-dpdelta"},
                               ensure_ascii=False) + "\n")
    d = collections.defaultdict(dict)
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        d[key[0]][half] = out[key]
    json.dump(d, open(args.out.replace(".jsonl", "_dict.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
