#!/usr/bin/env python3
"""Lead · 迭代 δ 精修：unique-char OCR 锚点 → 逐半版 δ → 部内平滑 → 校正计数 → 重建 mapping → 重复。

用法：--map <当前 map> --rounds 2
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3


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


def load_anchors():
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead2.jsonl"), encoding="utf-8")]
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
    return segs


def estimate_delta(canon, mapping, ocr, maxd=60):
    occ = collections.defaultdict(list)
    for i, c in enumerate(canon):
        occ[c].append(i)
    boxcache = {}
    est = {}
    for (page, half), obss in ocr.items():
        r = mapping.get((page, half))
        if not r or not r["entries"]:
            continue
        if page not in boxcache:
            try:
                boxcache[page] = json.load(open(os.path.join(
                    ROOT, "work/lead/boxes300", page + ".json"), encoding="utf-8"))
            except Exception:
                boxcache[page] = None
        fj = boxcache[page]
        if fj is None:
            continue
        sel = [c for c in fj["halves"][half]["cands"] if is_head_v3(c, half)]
        b2p = {tuple(int(v) for v in c["box"]): j for j, c in enumerate(sel)}
        n = len(r["entries"]); ci0 = r["ci_start"]
        ds = []
        for o in obss:
            if o["score"] < 0.8 or len(o["text"]) != 1:
                continue
            j = b2p.get(tuple(int(v) for v in o["box"]))
            if j is None or j >= n:
                continue
            p = ci0 + j
            pos = occ.get(o["text"]) or []
            if not pos:
                continue
            # 唯一出现，或多出现时取最近的
            if len(pos) == 1:
                ci = pos[0]
            else:
                ci = min(pos, key=lambda x: abs(x - p))
                if len(pos) > 2 and abs(ci - p) > 40:
                    continue
            d = ci - p
            if abs(d) <= maxd:
                ds.append(d)
        if ds:
            est[(page, half)] = (float(np.median(ds)), len(ds))
    return est


def smooth_counts(seq, est, segs, counts, lam=1.0, huber=True):
    delta = {}
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
                y[i] = est[key][0]; w[i] = min(3.0, est[key][1])
        if w.sum() == 0:
            for i, k in enumerate(idxs):
                delta[(f"{k[0]}_{k[1]:04d}", k[2])] = 0.0
            continue
        ww = w.copy()
        sol = np.zeros(m)
        for it in range(3 if huber else 1):
            A = np.zeros((m, m)); b = np.zeros(m)
            for i in range(m):
                A[i, i] += ww[i]; b[i] += ww[i] * y[i]
            for i in range(m - 1):
                A[i, i] += lam; A[i + 1, i + 1] += lam
                A[i, i + 1] -= lam; A[i + 1, i] -= lam
            A[0, 0] += 1e4; A[m - 1, m - 1] += 1e4
            sol = np.linalg.solve(A, b)
            if it < 2:
                res = y - sol
                ww = w * np.minimum(1.0, 6.0 / (np.abs(res) + 1e-6))
        for i, k in enumerate(idxs):
            delta[(f"{k[0]}_{k[1]:04d}", k[2])] = float(sol[i])
    # 更新 counts：保证段内和不变（端点 δ=0）
    out = {}
    prev = 0.0
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        d = delta.get(key, 0.0)
        dd = int(round(d - prev)); prev = d
        dd = max(-3, min(3, dd))   # 单页修正上限 ±3
        out[key] = max(0, counts.get(key, 0) + dd)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--counts", required=True)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out-counts", required=True)
    args = ap.parse_args()
    canon = load_canon()
    ocr = load_ocr()
    seq = build_seq()
    segs = load_anchors()
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = int(r["n"])
    mapdir = args.map
    for rd in range(args.rounds):
        mapping = {}
        for l in open(os.path.join(mapdir, "mapping.jsonl"), encoding="utf-8"):
            r = json.loads(l)
            mapping[(r["page"], r["half"])] = r
        est = estimate_delta(canon, mapping, ocr)
        print(f"round {rd}: δ-half estimates {len(est)}")
        counts = smooth_counts(seq, est, segs, counts)
        # 写 counts，调 solver 重建 mapping
        tmp = os.path.join(ROOT, "work/lead", f"counts_iter{rd}.json")
        cd = collections.defaultdict(dict)
        for (vol, pg, half) in seq:
            key = (f"{vol}_{pg:04d}", half)
            cd[key[0]][half] = counts[key]
        json.dump(cd, open(tmp, "w"), ensure_ascii=False)
        import subprocess
        outdir = os.path.join(ROOT, "work/map", f"iter{rd}")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts/lead_solver2.py"),
                        "--canonical", os.path.join(ROOT, "work/seq/canonical.jsonl"),
                        "--groups", os.path.join(ROOT, "work/seq/groups.json"),
                        "--boxes-dir", os.path.join(ROOT, "work/lead/boxes300"),
                        "--counts", tmp, "--roles",
                        os.path.join(ROOT, "work/lead/page_roles.jsonl"),
                        "--bu-anchors", os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"),
                        "--out", outdir], capture_output=True)
        mapdir = outdir
    # 最终 counts 落盘
    with open(args.out_counts, "w", encoding="utf-8") as f:
        for (vol, pg, half) in seq:
            key = (f"{vol}_{pg:04d}", half)
            f.write(json.dumps({"page": key[0], "half": half, "n": counts[key]},
                               ensure_ascii=False) + "\n")
    print("final map:", mapdir, "counts:", args.out_counts)


if __name__ == "__main__":
    main()
