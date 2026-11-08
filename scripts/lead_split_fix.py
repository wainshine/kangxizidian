#!/usr/bin/env python3
"""Lead · 用「双画数页 R/L 分组规则」修正逐页 R/L 拆分。

规则：版心 双画数字段 hua=[gR,gL] ⇒ R 半版=当前部内 group gR 的剩余条目（到该组末），L=其余。
迭代：用当前映射的 ci_start 推期望 R 数 → 修正 counts → 重建映射 → 重复。
"""
import argparse, json, os, sys, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/v17"))
    ap.add_argument("--counts", default=os.path.join(ROOT, "work/lead/counts_v5.jsonl"))
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v19.jsonl"))
    args = ap.parse_args()
    seq = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    bs = [e["bu_strokes"] for e in seq]
    obs = {}
    for l in open(os.path.join(ROOT, "work/seq/hdr_page_obs.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        obs[r["page"]] = r
    counts = {}
    for l in open(args.counts, encoding="utf-8"):
        r = json.loads(l)
        counts[(r["page"], r["half"])] = r["n"]
    mapdir = args.map
    stats = collections.Counter()
    for rd in range(args.rounds):
        mapping = collections.defaultdict(dict)
        for l in open(os.path.join(mapdir, "mapping.jsonl"), encoding="utf-8"):
            r = json.loads(l)
            mapping[r["page"]][r["half"]] = r
        fixed = dict(counts)
        nfix = 0
        for page, halfs in mapping.items():
            r = halfs.get("R")
            if not r:
                continue
            o = obs.get(page) or {}
            hua = o.get("hua") or []
            if len(hua) < 2:
                continue
            gR, gL = hua[0], hua[1]
            ci0 = r["ci_start"]
            if not (0 <= ci0 < len(bs)) or not (0 <= gR <= 30) or not (0 <= gL <= 30):
                continue
            if gL < gR:      # OCR 噪声
                continue
            end = ci0
            while end < len(bs) and bs[end] <= gR:
                end += 1
            exp_R = end - ci0
            total = counts.get((page, "R"), 0) + counts.get((page, "L"), 0)
            if exp_R > total or exp_R < 0:
                continue
            if counts.get((page, "R")) != exp_R:
                fixed[(page, "R")] = exp_R
                fixed[(page, "L")] = total - exp_R
                nfix += 1
        print(f"round {rd}: R/L 拆分修正 {nfix} 页")
        nfix = 0
        # 写 counts 并重建映射
        tmp = os.path.join(ROOT, "work/lead", f"counts_split{rd}.json")
        cd = collections.defaultdict(dict)
        for (pg, half), n in fixed.items():
            cd[pg][half] = n
        json.dump(cd, open(tmp, "w"), ensure_ascii=False)
        import subprocess
        outdir = os.path.join(ROOT, "work/map", f"split{rd}")
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
            f.write(json.dumps({"page": pg, "half": half, "n": n, "rule": "v19-split"},
                               ensure_ascii=False) + "\n")
    print("final map:", mapdir)


if __name__ == "__main__":
    main()
