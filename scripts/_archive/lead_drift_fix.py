#!/usr/bin/env python3
"""Lead · 字头 OCR 漂移校正 v2：每半版估计映射累计偏移 δ，按部平滑拟合（端点强制 0）后修正计数。

δ 定义：canon[ci_mapping + δ] == OCR 字头文本（即真值 ci = 映射 ci + δ）。
部总量由 counts_v5 保证精确 → 部端点 δ=0；部内用加权最小二乘 + 一阶平滑正则解 δ 曲线。
输出 counts_v6.jsonl（page,half,n,n_v5,delta,rule）。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3

MAXD = 90
LAMBDA = 2.0


def thomas(a, b, c, d):
    n = len(d)
    cp = np.zeros(n); dp = np.zeros(n)
    cp[0] = c[0] / b[0]; dp[0] = d[0] / b[0]
    for i in range(1, n):
        m = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / m if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / m
    x = np.zeros(n)
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", default=os.path.join(ROOT, "work/lead/hw_ocr.jsonl"))
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/bu_v5"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--anchors", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v6.jsonl"))
    ap.add_argument("--report", default=os.path.join(ROOT, "work/lead/counts_v6_report.json"))
    args = ap.parse_args()
    canon = [json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"),
                                                 encoding="utf-8")]
    mapping = {}
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        mapping[(r["page"], r["half"])] = r
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = int(r["n"])
    ocr = collections.defaultdict(list)
    for l in open(args.ocr, encoding="utf-8"):
        r = json.loads(l)
        if "err" in r or not r.get("text"):
            continue
        ocr[(r["page"], r["half"])].append(r)
    # 每半版 δ 估计
    est = {}
    for (page, half), obss in ocr.items():
        r = mapping.get((page, half))
        if not r or not r["entries"]:
            continue
        try:
            fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300", page + ".json"),
                                encoding="utf-8"))
        except Exception:
            continue
        sel = [c for c in fj["halves"][half]["cands"] if is_head_v3(c, half)]
        box_to_pos = {tuple(int(v) for v in c["box"]): j for j, c in enumerate(sel)}
        n = len(r["entries"]); ci0 = r["ci_start"]
        well = []
        for o in obss:
            j = box_to_pos.get(tuple(int(v) for v in o["box"]))
            if j is None or j >= n or len(o["text"]) != 1:
                continue
            well.append((ci0 + j, o["text"], max(0.0, o["score"] - 0.35)))
        if len(well) < 2:
            continue
        best, best_d, second = -1.0, 0, -1.0
        for d in range(-MAXD, MAXD + 1):
            sc = 0.0
            for ci, t, s in well:
                if s <= 0:
                    continue
                cc = ci + d
                if 0 <= cc < len(canon) and canon[cc] == t:
                    sc += s
            if sc > best:
                second = best; best, best_d = sc, d
            elif sc > second:
                second = sc
        if best >= 0.9 and best - second >= 0.25:
            est[(page, half)] = (best_d, best - second)
    print("δ 估计的半版数:", len(est))
    # 卷/部结构
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
            segs.append({"vol": vol, "lo": lo, "hi": hi})
    delta_curve = {}
    for seg in segs:
        idxs = [k for k in seq if k[0] == seg["vol"] and seg["lo"] <= k[1] <= seg["hi"]]
        m = len(idxs)
        if m < 2:
            for k in idxs:
                delta_curve[(f"{k[0]}_{k[1]:04d}", k[2])] = 0.0
            continue
        w = np.zeros(m)
        y = np.zeros(m)
        for i, k in enumerate(idxs):
            key = (f"{k[0]}_{k[1]:04d}", k[2])
            if key in est:
                d, conf = est[key]
                w[i] = max(0.3, conf)
                y[i] = d
        # 加权最小二乘 + 平滑：min Σw(δ−y)² + λΣ(δ_{i+1}−δ_i)²，端点 δ=0
        A = np.zeros((m, m))
        b = np.zeros(m)
        for i in range(m):
            A[i, i] += w[i]
            b[i] += w[i] * y[i]
        for i in range(m - 1):
            A[i, i] += LAMBDA; A[i + 1, i + 1] += LAMBDA
            A[i, i + 1] -= LAMBDA; A[i + 1, i] -= LAMBDA
        # 端点强约束（罚）
        A[0, 0] += 1e4; b[0] += 1e4 * 0.0
        A[m - 1, m - 1] += 1e4; b[m - 1] += 1e4 * 0.0
        sol = np.linalg.solve(A, b)
        for i, k in enumerate(idxs):
            delta_curve[(f"{k[0]}_{k[1]:04d}", k[2])] = float(sol[i])
    # 生成 v6
    out = []
    prev = 0.0
    tot = 0
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        d = delta_curve.get(key, 0.0)
        c = counts.get(key, 0)
        dd = int(round(d - prev))
        prev = d
        n = max(0, c + dd)
        tot += n
        out.append({"page": key[0], "half": half, "n": n, "n_v5": c,
                    "delta": dd, "rule": "v6-drift"})
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    import numpy as np2
    deltas = [r["delta"] for r in out]
    print("counts_v6 total", tot, "(目标 42302)  delta 分布 mean",
          round(float(np2.mean(deltas)), 2), "max", max(abs(d) for d in deltas))
    json.dump({"observed_halves": len(est), "total": tot,
               "delta_mean": float(np2.mean(deltas))},
              open(args.report, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
