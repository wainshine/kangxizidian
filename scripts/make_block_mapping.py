#!/usr/bin/env python3
"""生成 block-based mapping（类级修复）：box = 2×2 格块（页级 lattice），
再与版框内正文区（content quad）求交；**不再使用字内墨迹紧框**。

并行：按页分组，进程池（默认 8 workers；FONT_BUILD_WORKERS 可调）。
输出 mapping_block_v<ver>.jsonl（格式同 mapping33）。
"""

# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass



import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


import numpy as _np


def _box_corners(b):
    x0, y0, x1, y1 = [float(v) for v in b]
    return _np.array([[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], dtype=_np.float32)


def _transform_box(b, mat):
    """2x3 仿射变换 box 的 4 角，返回新 box。"""
    if mat is None:
        return list(b)
    pts = _cv2.transform(_box_corners(b), _np.asarray(mat, dtype=_np.float32))[0]
    xs, ys = pts[:, 0], pts[:, 1]
    return [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]


def _inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def worker(args):
    page, half, items = args
    import font_build as fb
    try:
        # 统一入口（含页级几何缓存 + lattice fallback；审计 P0-3）
        quads = fb.get_page_content_quads(page)
        lat = fb.get_page_lattice(page).get(half)
        q = quads.get(half)
    except Exception:
        return []
    out = []
    for it in items:
        ch, old = it["char"], it["box"]
        block = fb.block_for_box(lat, old) if lat else None
        if block is None:
            continue
        nb = [float(v) for v in block]
        if q is not None:
            # BF-61/BUILD-404：block 在 150dpi 原图坐标，quad.box 在旋转空间。
            # 若 block（经 M 变到旋转空间后）已在 quad 内，保持原 block（避免全库 1px 漂移）；
            # 只有压到 quad 边界的块才做 M 空间求交、Minv 变回，确保 box⊆quad。
            qb = list(q["box"])
            rot = _transform_box(nb, q.get("M"))
            inside = (rot[0] >= qb[0] + 2 and rot[1] >= qb[1] + 2
                      and rot[2] <= qb[2] - 2 and rot[3] <= qb[3] - 2)
            if not inside:
                inter = _inter(rot, qb)
                if inter is None:
                    continue
                nb = _transform_box(inter, q.get("Minv"))
        nb = [float(round(v)) for v in nb]
        if nb[2] - nb[0] < 60 or nb[3] - nb[1] < 60:
            continue
        out.append((it.get("rid"), ch, nb))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计改动/越界，不写 mapping（BF-61 验证）")
    args = ap.parse_args()
    rows = [json.loads(l) for l in open(os.path.join(ROOT, args.mapping), encoding="utf-8")]
    jobs = {}
    for r in rows:
        items, seen = [], set()
        for idx_a, a in enumerate(r.get("assigned", [])):
            ch = a.get("char"); cand = a.get("cand") or {}
            box = cand.get("box") or a.get("box")
            if ch and box and ch not in seen:
                seen.add(ch)
                items.append({"char": ch, "box": box,
                              "rid": f"{r.get('page')}|{idx_a}|{ch}"})
        # 注意：重复字跨页时按行处理（rid 唯一），不再用 newmap[ch] 全局覆盖
        if items:
            jobs.setdefault((r["page"], r.get("half", "")), []).extend(items)
    jl = [(p, h, items) for (p, h), items in jobs.items()]
    newmap = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(worker, jl, chunksize=2):
            for rid, ch, nb in res:
                newmap[(rid, ch)] = nb
    changed = 0
    for r in rows:
        for idx_a, a in enumerate(r.get("assigned", [])):
            ch = a.get("char")
            rid = f"{r.get('page')}|{idx_a}|{ch}"
            if (rid, ch) in newmap:
                cand = dict(a.get("cand") or {})
                old = cand.get("box") or a.get("box")
                _oldv = [float(round(v)) for v in old]
                if _oldv != newmap[(rid, ch)]:
                    changed += 1
                cand["box"] = newmap[(rid, ch)]
                a["cand"] = cand
    stats = {"pages": len(jl), "boxed": len(newmap), "changed": changed,
             "dry_run": bool(args.dry_run), "out": args.out}
    if args.dry_run:
        print(json.dumps(stats, ensure_ascii=False))
        return
    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
