#!/usr/bin/env python3
"""类级修复：消除 mapping 的「同 2×2 块多字」冲突（BF-02）。

规则（不按字打补丁）：
  1. 以 (page, half, block_box) 为组，找 assigned 中同一块被多个字占用；
  2. 用 mapping_verified 的**原始 ink box** 面积判定「真字」：面积最大者保留，
     其余视为片段/误标（例如把邻字的局部框标成另一个字），从 mapping 删除；
  3. 删除的字写入 residual 声明（char_diff 需要）与报告，供 CS3 重新定位（不补假字）。

用法：
  .venv/bin/python scripts/fix_mapping_sameblock.py \
      --verified work/lead/mapping_verified_all33.jsonl \
      --mapping  work/lead/mapping_block_v270.jsonl \
      --out      work/lead/mapping_block_v271.jsonl \
      --residual work/lead/v262_dropped_sameblock.json \
      --report   work/lead/sameblock-fix-report.json
"""
import argparse
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def area(b):
    return max(0.0, (b[2] - b[0]) * (b[3] - b[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verified", default="work/lead/mapping_verified_all33.jsonl")
    ap.add_argument("--mapping", default="work/lead/mapping_block_v270.jsonl")
    ap.add_argument("--out", default="work/lead/mapping_block_v271.jsonl")
    ap.add_argument("--residual", default="work/lead/v262_dropped_sameblock.json")
    ap.add_argument("--report", default="work/lead/sameblock-fix-report.json")
    args = ap.parse_args()

    def rd(p):
        return p if os.path.isabs(p) else os.path.join(ROOT, p)

    vb = {}
    for line in open(rd(args.verified), encoding="utf-8"):
        r = json.loads(line)
        for a in r.get("assigned") or []:
            b = (a.get("cand") or {}).get("box") or a.get("box")
            if a.get("char") and b:
                vb[(r["page"], r.get("half", ""), a["char"])] = b

    rows = [json.loads(l) for l in open(rd(args.mapping), encoding="utf-8")]
    groups = defaultdict(list)  # (page,half,block) -> [(row_i, assigned_i, char, vbox)]
    for i, r in enumerate(rows):
        for j, a in enumerate(r.get("assigned") or []):
            b = (a.get("cand") or {}).get("box") or a.get("box")
            if not b:
                continue
            key = (r["page"], r.get("half", ""), tuple(round(float(v), 1) for v in b))
            groups[key].append((i, j, a["char"], b,
                                vb.get((r["page"], r.get("half", ""), a["char"]))))

    drop = set()  # (i, j)
    report = {"n_groups_conflict": 0, "groups": [], "dropped_chars": [],
              "rule": "keep assignment with largest verified ink-box area; drop fragments",
              "verified_missing": []}
    for key, items in groups.items():
        chars = {it[2] for it in items}
        if len(chars) <= 1:
            continue
        report["n_groups_conflict"] += 1
        # 面积：优先 verified box；缺失时用 block box（并单列）
        scored = []
        for i, j, ch, b, vbox in items:
            if vbox is None:
                report["verified_missing"].append(ch)
            scored.append((area(vbox) if vbox else area(b), i, j, ch, b, vbox))
        scored.sort(reverse=True)
        keep = scored[0]
        dropped = []
        for a_, i, j, ch, b, vbox in scored[1:]:
            if (i, j) in drop:
                continue
            # 同组里同一 char 不会重复；全部删除
            drop.add((i, j))
            dropped.append(ch)
        report["groups"].append({
            "page": key[0], "half": key[1], "block": list(key[2]),
            "kept": keep[3], "kept_verified_box": keep[5],
            "kept_area": round(keep[0], 1),
            "dropped": dropped,
            "dropped_detail": [{"char": s[3], "verified_box": s[5],
                                "verified_area": round(s[0], 1)} for s in scored[1:]],
        })
        report["dropped_chars"].extend(dropped)

    out_rows = []
    for i, r in enumerate(rows):
        assigned = [a for j, a in enumerate(r.get("assigned") or []) if (i, j) not in drop]
        if not assigned:
            continue
        row = dict(r)
        row["assigned"] = assigned
        row["n"] = len(assigned)
        out_rows.append(row)
    with open(rd(args.out), "w", encoding="utf-8") as fo:
        for r in out_rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(rd(args.residual), "w", encoding="utf-8") as fo:
        json.dump({"version": "2.6.2", "chars": sorted(report["dropped_chars"]),
                   "reason": "same-block duplicate: fragment label dropped (BF-02); re-acquire in CS3",
                   "groups": report["groups"]}, fo, ensure_ascii=False, indent=1)
    report["mapping_out"] = args.out
    report["n_rows_in"] = len(rows)
    report["n_rows_out"] = len(out_rows)
    report["n_assigned_in"] = sum(len(r.get("assigned") or []) for r in rows)
    report["n_assigned_out"] = sum(len(r["assigned"]) for r in out_rows)
    with open(rd(args.report), "w", encoding="utf-8") as fo:
        json.dump(report, fo, ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in
                      ("n_groups_conflict", "dropped_chars", "n_assigned_in", "n_assigned_out")},
                     ensure_ascii=False))
    print(f"REPORT {args.report}")


if __name__ == "__main__":
    main()
