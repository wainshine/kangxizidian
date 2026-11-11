#!/usr/bin/env python3
"""Lead · 部内唯一字 OCR 锚点 → δ 估计 → 计数校正（v21）。

对每个候选框（solver 同款清洗顺序）：
  OCR 文本 score≥0.85 且该字在其部内正典唯一 → 锚点 δ = ci(字) − (ci_start + j)
每部内按页聚合 δ（中位数/离群剔除），部内平滑拟合（端点 δ=0），转成逐页计数修正。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3


def clean_cands(cands):
    cl = [c for c in cands if not (c.get("w", 0) < 30 and c.get("h", 0) > 45)]
    def iou(a, b):
        x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
        x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
        inter = max(0, x1 - x0) * max(0, y1 - y0)
        ua = (a[2] - a[0]) * (a[3] - a[1]); ub = (b[2] - b[0]) * (b[3] - b[1])
        return inter / max(1, ua + ub - inter)
    keep = []
    for x in sorted(cl, key=lambda c: -(c.get("h", 0) * c.get("w", 0))):
        if any(iou(x["box"], y["box"]) > 0.25 for y in keep):
            continue
        keep.append(x)
    order = {id(c): i for i, c in enumerate(cl)}
    keep.sort(key=lambda c: order.get(id(c), 10 ** 9))
    out = []
    for c in keep:
        h = c.get("h", 0); w = c.get("w", 0)
        if not ((50 <= h <= 135 and 30 <= w <= 140) or (h <= 40 and w >= 45)):
            continue
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/v17"))
    ap.add_argument("--ocr", default=os.path.join(ROOT, "work/lead/hw_ocr_v6.jsonl"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--avail", default=os.path.join(ROOT, "work/lead/avail_cands.json"))
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v21.jsonl"))
    args = ap.parse_args()
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    rad_entries = collections.Counter(e["rad"] for e in canon)
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead2.jsonl"), encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    segs = []
    cum = 0
    for vol in sorted(by_vol):
        for a in sorted(by_vol[vol], key=lambda x: x["page"]):
            lo, hi = cum, cum + rad_entries[a["radical"]]
            segs.append({"vol": vol, "rad": a["radical"], "lo_ci": lo, "hi_ci": hi,
                         "page": a["page"]})
            cum += rad_entries[a["radical"]]
    # 部内唯一字
    uniq = {}
    for s in segs:
        occ = collections.Counter(chars[s["lo_ci"]:s["hi_ci"]])
        uniq[(s["vol"], s["rad"])] = {c: s["lo_ci"] + i for i, e in enumerate(chars[s["lo_ci"]:s["hi_ci"]])
                                      for c in [e] if occ[e] == 1}
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    # OCR
    ocr = collections.defaultdict(list)
    for l in open(args.ocr, encoding="utf-8"):
        r = json.loads(l)
        if "err" in r or not r.get("text"):
            continue
        ocr[(r["page"], r["half"])].append(r)
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = r["n"]
    mapdir = args.map
    cand_cache = {}
    for rd in range(args.rounds):
        mapping = collections.defaultdict(dict)
        for l in open(os.path.join(mapdir, "mapping.jsonl"), encoding="utf-8"):
            r = json.loads(l)
            mapping[r["page"]][r["half"]] = r
        # 页→部
        page_seg = {}
        for s in segs:
            vol = s["vol"]
            ps = [p for p in sorted(roles[vol]) if p >= s["page"]]
            # 下一部起点
            pass
        seg_pages = []
        for i, s in enumerate(segs):
            vol = s["vol"]
            hi_page = segs[i + 1]["page"] - 1 if (i + 1 < len(segs) and segs[i + 1]["vol"] == vol) else 10 ** 9
            ps = [p for p in sorted(roles[vol]) if s["page"] <= p <= hi_page]
            seg_pages.append(ps)
            for p in ps:
                page_seg[f"{vol}_{p:04d}"] = i
        # 锚点
        est_pages = collections.defaultdict(list)
        n_anch = 0
        for (page, half), obss in ocr.items():
            si = page_seg.get(page)
            if si is None:
                continue
            s = segs[si]
            uniq_map = uniq[(s["vol"], s["rad"])]
            r = mapping.get(page, {}).get(half)
            if not r:
                continue
            if page not in cand_cache:
                try:
                    fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300",
                                                     page + ".json"), encoding="utf-8"))
                    cand_cache[page] = clean_cands(fj["halves"][half]["cands"])
                except Exception:
                    cand_cache[page] = []
        # 上面缓存按 (page,half) 需要，重来：直接循环
        cand_cache2 = {}
        est_pages = collections.defaultdict(list)
        n_anch = 0
        for page, halves in mapping.items():
            si = page_seg.get(page)
            if si is None:
                continue
            s = segs[si]
            uniq_map = uniq[(s["vol"], s["rad"])]
            for half in ("R", "L"):
                r = halves.get(half)
                if not r:
                    continue
                key = (page, half)
                if key not in cand_cache2:
                    try:
                        fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300",
                                                         page + ".json"), encoding="utf-8"))
                        cand_cache2[key] = clean_cands(fj["halves"][half]["cands"])
                    except Exception:
                        cand_cache2[key] = []
                sel = cand_cache2[key]
                box_pos = {tuple(int(v) for v in c["box"]): j for j, c in enumerate(sel)}
                ci0 = r["ci_start"]
                for o in ocr.get((page, half), []):
                    if o["score"] < 0.85 or len(o["text"]) != 1:
                        continue
                    j = box_pos.get(tuple(int(v) for v in o["box"]))
                    if j is None:
                        continue
                    ci = uniq_map.get(o["text"])
                    if ci is None:
                        continue
                    d = ci - (ci0 + j)
                    if abs(d) <= 60:
                        est_pages[page].append(d)
                        n_anch += 1
        print(f"round {rd}: 锚点 {n_anch}，覆盖页 {len(est_pages)}")
        # 每部平滑
        delta_page = {}
        for si, s in enumerate(segs):
            ps = seg_pages[si]
            if len(ps) < 2:
                for p in ps:
                    delta_page[f"{s['vol']}_{p:04d}"] = 0.0
                continue
            y = np.zeros(len(ps)); w = np.zeros(len(ps))
            for i, p in enumerate(ps):
                page = f"{s['vol']}_{p:04d}"
                if page in est_pages:
                    ds = np.array(est_pages[page])
                    med = float(np.median(ds))
                    keep = ds[np.abs(ds - med) <= 5]
                    y[i] = float(np.median(keep))
                    w[i] = min(4.0, len(keep))
            w[0] = max(w[0], 1.0); y[0] = 0.0
            w[-1] = max(w[-1], 1.0); y[-1] = 0.0
            ww = w.copy(); sol = np.zeros(len(ps))
            for it in range(3):
                A = np.zeros((len(ps), len(ps))); b = np.zeros(len(ps))
                for i in range(len(ps)):
                    A[i, i] += ww[i]; b[i] += ww[i] * y[i]
                for i in range(len(ps) - 1):
                    A[i, i] += 1.0; A[i + 1, i + 1] += 1.0
                    A[i, i + 1] -= 1.0; A[i + 1, i] -= 1.0
                sol = np.linalg.solve(A, b)
                if it < 2:
                    res = y - sol
                    ww = w * np.minimum(1.0, 6.0 / (np.abs(res) + 1e-6))
            sol = np.nan_to_num(sol, nan=0.0, posinf=0.0, neginf=0.0)
            for i, p in enumerate(ps):
                delta_page[f"{s['vol']}_{p:04d}"] = float(sol[i])
        # 应用
        fixed = {}
        for vol in sorted(roles):
            prev = 0.0
            for pg in sorted(roles[vol]):
                page = f"{vol}_{pg:04d}"
                d = delta_page.get(page, 0.0)
                mid = (prev + d) / 2.0
                for half in ("R", "L"):
                    k2 = (page, half)
                    cur = prev if half == "R" else mid
                    nxt = mid if half == "R" else d
                    dd = int(round(nxt - cur))
                    dd = max(-4, min(4, dd))
                    fixed[k2] = max(0, counts.get(k2, 0) + dd)
                prev = d
        # 写 counts、重建映射
        tmp = os.path.join(ROOT, "work/lead", f"counts_a2_{rd}.json")
        cd = collections.defaultdict(dict)
        for (pg, half), n in fixed.items():
            cd[pg][half] = n
        json.dump(cd, open(tmp, "w"), ensure_ascii=False)
        import subprocess
        outdir = os.path.join(ROOT, "work/map", f"a2_{rd}")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts/lead_solver2.py"),
                        "--canonical", os.path.join(ROOT, "work/seq/canonical.jsonl"),
                        "--groups", os.path.join(ROOT, "work/seq/groups.json"),
                        "--boxes-dir", os.path.join(ROOT, "work/lead/boxes300"),
                        "--counts", tmp, "--roles",
                        os.path.join(ROOT, "work/lead/page_roles.jsonl"),
                        "--bu-anchors", os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"),
                        "--out", outdir], capture_output=True)
        mapdir = outdir
        counts = fixed
    with open(args.out, "w", encoding="utf-8") as f:
        for (pg, half), n in sorted(counts.items()):
            f.write(json.dumps({"page": pg, "half": half, "n": n, "rule": "v21-anchor2"},
                               ensure_ascii=False) + "\n")
    print("final map:", mapdir)


if __name__ == "__main__":
    main()
