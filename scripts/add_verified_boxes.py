#!/usr/bin/env python3
"""把 verified mapping 的 tight ink box 写进 block mapping（供 pre-cut keep 区使用）。

背景（E24）：页级直线 mask 能清掉块内「框线/注文框」，但若 line 落在检测块框内部，
需要在单字层面用 **verified tight ink bbox** 作为 keep 区（box±2px），keep 区外才应用细线 mask。
本脚本输出 mapping_block_v272.jsonl：assigned[i] 增加 "verified_box" 字段（原 cand.box 不变）。

用法：
  .venv/bin/python scripts/add_verified_boxes.py \
      --mapping work/lead/mapping_block_v271.jsonl \
      --verified work/lead/mapping_verified_all33.jsonl \
      --out work/lead/mapping_block_v272.jsonl
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rd(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", default="work/lead/mapping_block_v271.jsonl")
    ap.add_argument("--verified", default="work/lead/mapping_verified_all33.jsonl")
    ap.add_argument("--out", default="work/lead/mapping_block_v272.jsonl")
    args = ap.parse_args()
    vb = {}
    for line in open(rd(args.verified), encoding="utf-8"):
        r = json.loads(line)
        for a in r.get("assigned") or []:
            b = (a.get("cand") or {}).get("box") or a.get("box")
            if a.get("char") and b:
                vb[(r["page"], r.get("half", ""), a["char"])] = [float(v) for v in b]
    rows = []
    n = n_missing = 0
    missing = []
    for line in open(rd(args.mapping), encoding="utf-8"):
        r = json.loads(line)
        for a in r.get("assigned") or []:
            k = (r["page"], r.get("half", ""), a["char"])
            if k in vb:
                a["verified_box"] = vb[k]
            else:
                n_missing += 1
                missing.append(a["char"])
            n += 1
        rows.append(r)
    with open(rd(args.out), "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"out": args.out, "rows": len(rows), "assigned": n,
                      "verified_box_added": n - n_missing, "missing": n_missing,
                      "missing_sample": missing[:10]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
