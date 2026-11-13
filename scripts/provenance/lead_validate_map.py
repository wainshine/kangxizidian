#!/usr/bin/env python3
"""Lead · 映射验证：owner 金标框 / demo 字形 / (可选) dup-pair。"""
import argparse, json, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def iou(a, b):
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]); ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1, ua + ub - inter)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()
    m = collections.defaultdict(dict)
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        m[r["page"]][r["half"]] = r
    owner = json.load(open(os.path.join(ROOT, "work/font/owner_verified_boxes.json"), encoding="utf-8"))
    ok = 0; det = []
    for e in owner:
        ch = e["char"]; pg = e["page"]; half = e["half"]; box = e["box"]
        r = m.get(pg, {}).get(half)
        hit = None
        if r:
            for a in r["assigned"]:
                if iou(a["cand"]["box"], box) >= args.iou:
                    hit = a["char"]; break
        det.append((ch, hit)); ok += (hit == ch)
    print(f"owner 金标框命中 {ok}/{len(owner)}")
    for d in det: print("   ", d)
    man = [json.loads(l) for l in open(os.path.join(ROOT, "work/font/demo/manifest.jsonl"), encoding="utf-8")]
    ok2 = 0; tot = 0; det2 = []
    for g in man:
        ch = g["char"]; page = g.get("page"); box = g.get("box"); half = g.get("half", "R")
        if not page or not box:
            continue
        r = m.get(page, {}).get(half)
        if not r:
            continue
        hit = None
        for a in r["assigned"]:
            if iou(a["cand"]["box"], box) >= args.iou:
                hit = a["char"]; break
        tot += 1; ok2 += (hit == ch); det2.append((ch, hit))
    print(f"demo 字形同位命中 {ok2}/{tot}")
    print("   miss:", [d for d in det2 if d[0] != d[1]])
    tot_ent = sum(len(r["assigned"]) for rows in m.values() for r in rows.values())
    print("rows", sum(len(v) for v in m.values()), "assigned entries", tot_ent)


if __name__ == "__main__":
    main()
