#!/usr/bin/env python3
"""把 manifest 中每个字映射到其 2×2 格块（新切分框）；按页并行。"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]); ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1, ua + ub - inter)


def job(items):
    from block_cut import lattice_for_page, block_for_box
    page, half, chars = items
    lat = lattice_for_page(page, half)
    out = []
    if lat is None:
        for ch, box in chars:
            out.append({"char": ch, "page": page, "half": half, "old": box, "block": None, "iou": None})
        return out
    ink = lat["ink"]
    for ch, box in chars:
        blk, cell = block_for_box(lat, box)
        v = iou(box, blk)
        sub = ink[max(0, blk[1]):blk[3], max(0, blk[0]):blk[2]]
        ys, xs = np.nonzero(sub)
        if len(xs):
            bb = [blk[0] + int(xs.min()), blk[1] + int(ys.min()), blk[0] + int(xs.max()), blk[1] + int(ys.max())]
            margins = [bb[0] - blk[0], bb[1] - blk[1], blk[2] - bb[2], blk[3] - bb[3]]
        else:
            bb = None; margins = None
        out.append({"char": ch, "page": page, "half": half, "old": box, "block": blk,
                    "cell": cell, "iou": round(v, 3), "ink_bb": bb, "margins": margins,
                    "block_size": [blk[2] - blk[0], blk[3] - blk[1]]})
    return out


def main():
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]
    by_page = {}
    for ch, r in man.items():
        by_page.setdefault((r["page"], r.get("half", "L")), []).append((ch, r["box"]))
    jobs = [(p, h, items) for (p, h), items in by_page.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(job, jobs, chunksize=4):
            rows.extend(res)
    rows.sort(key=lambda r: r["char"])
    with open(os.path.join(ROOT, "work/lead/block_map.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(rows)
    ok = sum(1 for r in rows if r["iou"] is not None and r["iou"] >= 0.5)
    low = sum(1 for r in rows if r["iou"] is not None and r["iou"] < 0.3)
    nolat = sum(1 for r in rows if r["iou"] is None)
    print(json.dumps({"n": n, "ok_iou>=0.5": ok, "low_iou<0.3": low, "no_lattice": nolat}))


if __name__ == "__main__":
    main()
