#!/usr/bin/env python3
"""Lead · mapping 验收闸（一条命令出结论）。

检查项：
1) owner 金标：work/font/owner_verified_boxes.json 里 10 个逐字核实框，映射是否把该字指派到同 box（IoU≥0.5）；
2) dup-pair 自校验：相邻同字（重出）对被指派框的字形相似度（应显著高于随机）；
3) 卷级残差：report.json 的 juan_residuals（应全 0）；
4) 覆盖率：assigned / 42,302。
通过标准：owner ≥9/10、dup 相似度 mean ≥0.5、卷残差全 0、覆盖率 ≥98%。
用法：.venv/bin/python scripts/lead_mapping_check.py --map work/map/xxx
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def iou(a, b):
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1])
    ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1, ua + ub - inter)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, help="solver 输出目录")
    ap.add_argument("--dup-sample", type=int, default=150)
    args = ap.parse_args()
    mapping_path = os.path.join(args.map, "mapping.jsonl")
    recs = [json.loads(l) for l in open(mapping_path, encoding="utf-8")]
    by = collections.defaultdict(dict)
    for r in recs:
        by[r["page"]][r["half"]] = r
    ok = True
    # 1) owner 金标
    ov = json.load(open(os.path.join(ROOT, "work/font/owner_verified_boxes.json"), encoding="utf-8"))
    hits = 0
    detail = []
    for e in ov:
        ch = e["char"]; pg = e["page"]; half = e["half"]
        r = by.get(pg, {}).get(half)
        if not r:
            detail.append((ch, "no-half", None)); continue
        best = None
        for j, a in enumerate(r["assigned"]):
            if a["char"] == ch:
                v = iou(a["cand"]["box"], e["box"])
                best = max(best or 0, v)
        if best is not None and best >= 0.5:
            hits += 1
            detail.append((ch, "OK", round(best, 2)))
        else:
            detail.append((ch, "MISS", None if best is None else round(best, 2)))
    print(f"[1] owner 金标: {hits}/{len(ov)}")
    for d in detail:
        print("    ", d)
    if hits < 9:
        ok = False
    # 2) dup-pair
    sys.argv = [sys.argv[0], "--mapping", mapping_path, "--max-pairs", str(args.dup_sample)]
    try:
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/lead_selfcheck_map.py"),
                              "--mapping", mapping_path, "--max-pairs", str(args.dup_sample)],
                             capture_output=True, text=True, timeout=900)
        lines = [l for l in out.stdout.splitlines() if "dup-pair" in l or "random" in l]
        print("[2] dup-pair:", " | ".join(lines))
        mean_line = [l for l in out.stdout.splitlines() if l.startswith("dup-pair")]
        mean = 0.0
        if mean_line:
            try:
                mean = float(mean_line[0].split("mean=")[1].split()[0])
            except Exception:
                pass
        if mean < 0.5:
            ok = False
    except Exception as e:
        print("[2] dup-pair: SKIP", e)
        ok = False
    # 3) 卷残差
    rep = json.load(open(os.path.join(args.map, "report.json"), encoding="utf-8"))
    jr = rep.get("juan_residuals") or []
    bad = [x for x in jr if x.get("resid")]
    print(f"[3] 卷残差: {len(jr)} 卷，非 0 {len(bad)}")
    if bad:
        for x in bad[:5]:
            print("    ", x)
        ok = False
    # 4) 覆盖率
    assigned = sum(len(r["assigned"]) for r in recs)
    ratio = assigned / 42302
    print(f"[4] 覆盖率: {assigned}/42302 = {ratio*100:.1f}%")
    if ratio < 0.98:
        ok = False
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
