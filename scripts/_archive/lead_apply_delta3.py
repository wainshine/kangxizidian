#!/usr/bin/env python3
"""Lead · 页级 δ 稳健估计 → 部内平滑 → 计数校正 → 可行性投影（counts_v15）。

δ 来自 unique-char OCR 锚点：每页取中位数（先剔除 |δ|>40 的离群），按页数锚点拟合
部内 δ 曲线（端点 δ=0，Huber 重加权），再转成半版计数修正。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchors_json", default=os.path.join(ROOT, "work/lead/unique_anchors.json"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--avail", default=os.path.join(ROOT, "work/lead/avail_cands.json"))
    ap.add_argument("--bus", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--radicals", default=os.path.join(ROOT, "work/seq/volume_radicals.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v15.jsonl"))
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/v14"))
    args = ap.parse_args()
    # 映射取每页预测 ci（用于 δ 定义：真值 ci = 预测 ci + δ）
    mapping = {}
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        mapping.setdefault(r["page"], {})[r["half"]] = r
    anch = json.load(open(args.anchors_json))
    # 页级 δ
    bypage = collections.defaultdict(list)
    for a in anch:
        if a["delta"] is None or abs(a["delta"]) > 40:
            continue
        bypage[a["page"]].append(a["delta"])
    page_delta = {}
    for page, ds in bypage.items():
        ds = np.array(ds, dtype=float)
        med = float(np.median(ds))
        keep = ds[np.abs(ds - med) <= 6]
        if len(keep) >= 1:
            page_delta[page] = (float(np.median(keep)), len(keep))
    print("pages with δ:", len(page_delta))
    # 部段
    anchors = [json.loads(l) for l in open(args.bus, encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    rad_entries = collections.Counter()
    for line in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8"):
        e = json.loads(line); rad_entries[e["rad"]] += 1
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = int(r["n"])
    avail = {tuple(k.split("|")): v for k, v in json.load(open(args.avail)).items()}
    # 页级 δ → 半版 δ：同页 R/L 同 δ（用页 δ），部端点 0
    seq = []
    for vol in sorted(roles):
        for pg in sorted(roles[vol]):
            for half in ("R", "L"):
                seq.append((vol, pg, half))
    delta_half = {}
    for vol in sorted(by_vol):
        ast = sorted(by_vol[vol], key=lambda x: x["page"])
        for i, a in enumerate(ast):
            lo = a["page"]
            hi = ast[i + 1]["page"] - 1 if i + 1 < len(ast) else 10 ** 9
            pages = [p for p in sorted(roles[vol]) if lo <= p <= hi]
            if len(pages) < 2:
                for p in pages:
                    for h in ("R", "L"):
                        delta_half[(f"{vol}_{p:04d}", h)] = 0.0
                continue
            x = np.arange(len(pages), dtype=float)
            y = np.zeros(len(pages)); w = np.zeros(len(pages))
            for j, p in enumerate(pages):
                key = f"{vol}_{p:04d}"
                if key in page_delta:
                    y[j] = page_delta[key][0]
                    w[j] = min(4.0, page_delta[key][1])
            # 端点 0
            w[0] = max(w[0], 1.0); y[0] = 0.0
            w[-1] = max(w[-1], 1.0); y[-1] = 0.0
            ww = w.copy()
            sol = np.zeros(len(pages))
            for it in range(3):
                A = np.zeros((len(pages), len(pages))); b = np.zeros(len(pages))
                for j in range(len(pages)):
                    A[j, j] += ww[j]; b[j] += ww[j] * y[j]
                for j in range(len(pages) - 1):
                    A[j, j] += 1.2; A[j + 1, j + 1] += 1.2
                    A[j, j + 1] -= 1.2; A[j + 1, j] -= 1.2
                sol = np.linalg.solve(A, b)
                if it < 2:
                    res = y - sol
                    ww = w * np.minimum(1.0, 6.0 / (np.abs(res) + 1e-6))
            for j, p in enumerate(pages):
                for h in ("R", "L"):
                    delta_half[(f"{vol}_{p:04d}", h)] = float(sol[j])
    # 应用：半版内 R 前半、L 后半（同页 δ 均分）
    out = {}
    for vol in sorted(roles):
        for pg in sorted(roles[vol]):
            key_r = (f"{vol}_{pg:04d}", "R")
            key_l = (f"{vol}_{pg:04d}", "L")
            d = delta_half.get(key_r, 0.0)
            # R 与 L 各承担 d/2 的漂移变化：
            # δ_page 是「页级累计漂移」；R/L 两个半版之间用 0 与 d 分界
            out[key_r] = counts.get(key_r, 0)
            out[key_l] = counts.get(key_l, 0)
    # 修正：跨页 δ 差分
    prev = 0.0
    fixed = {}
    for vol in sorted(roles):
        prev = 0.0
        for pg in sorted(roles[vol]):
            key = f"{vol}_{pg:04d}"
            d = delta_half.get((key, "R"), 0.0)
            # 本页两半版的漂移从 prev 过渡到 d：R 承担一半
            mid = (prev + d) / 2.0
            for half in ("R", "L"):
                k2 = (key, half)
                cur = prev if half == "R" else mid
                nxt = mid if half == "R" else d
                dd = int(round(nxt - cur))
                dd = max(-4, min(4, dd))
                fixed[k2] = max(0, counts.get(k2, 0) + dd)
            prev = d
    # 可行性投影（可关闭：--no-proj）
    for vol in sorted(by_vol) if not os.environ.get("NO_PROJ") else []:
        ast = sorted(by_vol[vol], key=lambda x: x["page"])
        for i, a in enumerate(ast):
            lo = a["page"]
            hi = ast[i + 1]["page"] - 1 if i + 1 < len(ast) else 10 ** 9
            keys = [k for k in fixed if k[0][:2] == vol and lo <= int(k[0][3:]) <= hi]
            if not keys:
                continue
            for k in keys:
                fixed[k] = min(fixed[k], avail.get(k, 0))
            total = sum(fixed[k] for k in keys)
            target = rad_entries[a["radical"]]
            guard = 0
            while total != target and guard < 30000:
                guard += 1
                if total < target:
                    cand = [k for k in keys if fixed[k] < avail.get(k, 0)]
                    if not cand:
                        break
                    cand.sort(key=lambda k: -(avail.get(k, 0) - fixed[k]))
                    for k in cand:
                        if total >= target:
                            break
                        fixed[k] += 1; total += 1
                else:
                    cand = [k for k in keys if fixed[k] > 0]
                    if not cand:
                        break
                    cand.sort(key=lambda k: -fixed[k])
                    for k in cand:
                        if total <= target:
                            break
                        fixed[k] -= 1; total -= 1
    tot = sum(fixed.values())
    print("fixed counts total", tot, "(target 42302)")
    with open(args.out, "w", encoding="utf-8") as f:
        for (vol, pg, half) in seq:
            key = (f"{vol}_{pg:04d}", half)
            f.write(json.dumps({"page": key[0], "half": half, "n": fixed.get(key, 0),
                                "n_v5": counts.get(key, 0), "rule": "v15-pagedelta"},
                               ensure_ascii=False) + "\n")
    d = collections.defaultdict(dict)
    for (vol, pg, half) in seq:
        key = (f"{vol}_{pg:04d}", half)
        d[key[0]][half] = fixed.get(key, 0)
    json.dump(d, open(args.out.replace(".jsonl", "_dict.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
