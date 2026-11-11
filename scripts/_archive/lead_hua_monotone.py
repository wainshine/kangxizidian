#!/usr/bin/env python3
"""Lead · 部内 hua 单调回归（PAVA）修正 → 更可靠的画数观测文件。

同一部内版心画数应随页单调不减（部外笔画递增）；OCR 偶发离群（如 20/17）用单调回归压回。
输出 work/lead/headers_hua_mono.jsonl（格式同 headers_hua_seq.jsonl）
"""
import json, os, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pava(y, w):
    """加权单调不减回归（pool adjacent violators）。"""
    n = len(y)
    vals = [y[i] for i in range(n)]
    wts = [w[i] for i in range(n)]
    starts = list(range(n))
    i = 0
    while i < len(vals) - 1:
        if vals[i] <= vals[i + 1] + 1e-9:
            i += 1
            continue
        # 合并 i 与 i+1
        nv = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / (wts[i] + wts[i + 1])
        nw = wts[i] + wts[i + 1]
        vals[i:i + 2] = [nv]
        wts[i:i + 2] = [nw]
        i = max(0, i - 1)
    # 展开
    out = []
    for v, ww in zip(vals, wts):
        out.extend([v] * int(round(ww)))
    return out


def main():
    obs = {}
    for l in open(os.path.join(ROOT, "work/seq/hdr_page_obs.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        obs[r["page"]] = r
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead2.jsonl"), encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    out = open(os.path.join(ROOT, "work/lead/headers_hua_mono.jsonl"), "w", encoding="utf-8")
    n_corr = 0
    n_tot = 0
    for vol in sorted(by_vol):
        ast = sorted(by_vol[vol], key=lambda x: x["page"])
        for i, a in enumerate(ast):
            lo = a["page"]
            hi = ast[i + 1]["page"] - 1 if i + 1 < len(ast) else 10 ** 9
            pages = [p for p in sorted(roles[vol]) if lo <= p <= hi]
            if not pages:
                continue
            ys = []
            for p in pages:
                r = obs.get(f"{vol}_{p:04d}") or {}
                hua = r.get("hua") or []
                v = hua[-1] if hua else None
                ys.append(v)
            # 已知点做单调回归；缺失点用相邻插值后不输出
            known = [i2 for i2, v in enumerate(ys) if v is not None]
            if len(known) >= 2:
                vals = np.array([ys[i2] for i2 in known], dtype=float)
                # 用相邻间隔作为权重
                wts = np.ones(len(vals))
                fit = pava(list(vals), list(wts))
            else:
                fit = None
            for i2, p in enumerate(pages):
                page = f"{vol}_{p:04d}"
                r = obs.get(page) or {}
                hua = r.get("hua") or []
                if not hua or fit is None:
                    continue
                j = known.index(i2) if i2 in known else None
                if j is None:
                    continue
                newv = int(round(fit[j]))
                newhua = [newv] if len(hua) == 1 else [min(newv, hua[0]), newv]
                if newhua != hua:
                    n_corr += 1
                n_tot += 1
                out.write(json.dumps({"page": page, "half": "L", "bu": None,
                                      "hua": newhua, "leaf_no": None, "conf": 0.75,
                                      "errors": []}, ensure_ascii=False) + "\n")
    out.close()
    print("hua mono obs:", n_tot, "corrected:", n_corr)


if __name__ == "__main__":
    main()
