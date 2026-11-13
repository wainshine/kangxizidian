#!/usr/bin/env python3
"""expand_quads_to_cover_boxes.py — BF-03 类级修复：把 content quad 扩到覆盖所有已指派字头的 box。

背景：page_geometry_gate 的 bad_boxes = manifest box 四角经 quad.M 变换后越出 quad["box"]
（容差 1px；当前 198@1px / 360@0 / max 8.803px）。越界字号的字头可能被 clip mask 裁到，
既是几何残差也是潜在内容缺失来源。类级修法：对每个 (page,half)，把 quad["box"] 在旋转空间
扩到覆盖该半版全部 assigned box 的四角（只扩不缩），并留 --margin px 余量。

用法：
  .venv/bin/python scripts/expand_quads_to_cover_boxes.py \
      --geometry work/lead/page_geometry.jsonl \
      --mapping work/lead/mapping_block_v271.jsonl \
      --manifest work/font/build/manifest_v262.json \
      --out work/lead/page_geometry_v2.jsonl \
      --report work/lead/quad-expand-report.json
"""
import argparse
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rd(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def corners(b):
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry", default="work/lead/page_geometry.jsonl")
    ap.add_argument("--mapping", default="work/lead/mapping_block_v271.jsonl")
    ap.add_argument("--manifest", default="work/font/build/manifest_v262.json")
    ap.add_argument("--out", default="work/lead/page_geometry_v2.jsonl")
    ap.add_argument("--report", default="work/lead/quad-expand-report.json")
    ap.add_argument("--margin", type=float, default=0.5, help="额外余量 px（150dpi）")
    args = ap.parse_args()

    geom = [json.loads(l) for l in open(rd(args.geometry), encoding="utf-8") if l.strip()]
    man = json.load(open(rd(args.manifest), encoding="utf-8"))["chars"]
    # 每个 (page,half) 需要覆盖的 box 四角（rot 空间）
    need = {}
    for ch, rec in man.items():
        page, half, box = str(rec.get("page")), rec.get("half"), rec.get("box")
        if not page or half not in ("L", "R") or not box:
            continue
        need.setdefault((page, half), []).append(box)

    idx = {(r.get("page"), h): (i, r) for i, r in enumerate(geom) for h in ("L", "R")}
    changed = 0
    changed_pages = 0
    max_exp = 0.0
    per_side_max = {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0}
    for (page, half), boxes in sorted(need.items()):
        i, row = idx[(page, half)]
        q = (row.get("quads") or {}).get(half)
        if not isinstance(q, dict):
            continue
        M = q.get("M")
        qb = q.get("box")
        if M is None or qb is None:
            continue
        a, b, c = M[0]
        d, e, f = M[1]
        xs, ys = [], []
        for box in boxes:
            for px, py in corners([float(v) for v in box]):
                xs.append(a * px + b * py + c)
                ys.append(d * px + e * py + f)
        nx0 = min([qb[0]] + xs) - args.margin
        ny0 = min([qb[1]] + ys) - args.margin
        nx1 = max([qb[2]] + xs) + args.margin
        ny1 = max([qb[3]] + ys) + args.margin
        exp = max(qb[0] - nx0, qb[1] - ny0, nx1 - qb[2], ny1 - qb[3])
        if exp <= 1e-9:
            continue
        per_side_max["x0"] = max(per_side_max["x0"], qb[0] - nx0)
        per_side_max["y0"] = max(per_side_max["y0"], qb[1] - ny0)
        per_side_max["x1"] = max(per_side_max["x1"], nx1 - qb[2])
        per_side_max["y1"] = max(per_side_max["y1"], ny1 - qb[3])
        max_exp = max(max_exp, exp)
        q["box"] = [round(nx0, 3), round(ny0, 3), round(nx1, 3), round(ny1, 3)]
        changed += 1
        changed_pages += 1
    with open(rd(args.out), "w", encoding="utf-8") as fo:
        for row in geom:
            fo.write(json.dumps(row, ensure_ascii=False) + "\n")
    rep = {"geometry_in": args.geometry, "geometry_out": args.out,
           "halves_changed": changed, "max_expansion_px": round(max_exp, 3),
           "per_side_max_px": {k: round(v, 3) for k, v in per_side_max.items()},
           "margin_px": args.margin}
    with open(rd(args.report), "w", encoding="utf-8") as fo:
        json.dump(rep, fo, ensure_ascii=False, indent=1)
        fo.write("\n")
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
