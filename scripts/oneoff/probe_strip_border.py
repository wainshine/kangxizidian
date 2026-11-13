#!/usr/bin/env python3
"""A/B 量化：主链 `strip_border_lines`（切后擦）在样本上到底删了什么。

背景（BF-13）：pre-cut 不变量要求框线在裁切阶段排除；`font_norm.strip_border_lines`
是主链唯一残留的「切后按形状删线」。摘除前先量化：对 N 个字分别用
  A: strip_border=True （现状）
  B: strip_border=False（纯 pre-cut）
构建轮廓，比较 ink_px / n_contours / n_segs 及被删除像素比例。

输出：work/lead/strip-border-ab.json
用法：.venv/bin/python scripts/probe_strip_border.py --sample 200
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

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items = args
    import font_build as FB
    import font_norm as FN
    out = []
    try:
        lat = FB.get_page_lattice(page).get(half)
        tbb = FB.get_page_text_bbox(page)
        quads = FB.get_page_content_quads(page)
        quad = quads.get(half)
        fmask = FB.get_page_frame_mask(page)  # 页级长线 mask（pre-cut 候选）
    except Exception as e:
        return [{"char": it["char"], "page": page, "half": half, "box": it["box"],
                 "error": f"prepare:{str(e)[:120]}"} for it in items]
    for it in items:
        ch, box = it["char"], it["box"]
        rec = {"char": ch, "page": page, "half": half, "box": box}
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            rep = {}
            a = FN.vectorize_box(page, box, block150=block, content_quad=quad,
                                 strip_border=True, strip_report=rep)
            b = FN.vectorize_box(page, box, block150=block, content_quad=quad,
                                 strip_border=False)
            c = FN.vectorize_box(page, box, block150=block, content_quad=quad,
                                 frame_mask=fmask, strip_border=False)
            d = FN.vectorize_box(page, box, block150=block, content_quad=quad,
                                 strip_border=False, block_edge_band150=3.0)
            rec.update({
                "ok_a": bool(a.get("ok")), "ok_b": bool(b.get("ok")), "ok_c": bool(c.get("ok")),
                "ink_a": a.get("ink_px"), "ink_b": b.get("ink_px"), "ink_c": c.get("ink_px"),
                "contours_a": a.get("n_contours"), "contours_b": b.get("n_contours"),
                "contours_c": c.get("n_contours"),
                "segs_a": a.get("n_segs"), "segs_b": b.get("n_segs"), "segs_c": c.get("n_segs"),
                "ok_d": bool(d.get("ok")), "ink_d": d.get("ink_px"),
                "contours_d": d.get("n_contours"), "segs_d": d.get("n_segs"),
                "reason_d": d.get("reason"),
                "frame_mask": bool(fmask is not None),
                "removed_px": rep.get("removed_px", 0),
                "removed_frac": rep.get("removed_frac", 0.0),
                "reason_a": a.get("reason"), "reason_b": b.get("reason"),
                "reason_c": c.get("reason"),
            })
            rec["strip_changed"] = (bool(rec["removed_px"]) or
                                    rec["ink_a"] != rec["ink_b"] or
                                    rec["contours_a"] != rec["contours_b"])
            rec["c_equals_a"] = (rec["ink_a"] == rec["ink_c"] and
                                 rec["contours_a"] == rec["contours_c"] and
                                 rec["segs_a"] == rec["segs_c"])
            rec["c_equals_b"] = (rec["ink_b"] == rec["ink_c"] and
                                 rec["contours_b"] == rec["contours_c"] and
                                 rec["segs_b"] == rec["segs_c"])
            rec["d_equals_a"] = (rec["ink_a"] == rec["ink_d"] and
                                 rec["contours_a"] == rec["contours_d"] and
                                 rec["segs_a"] == rec["segs_d"])
            rec["d_equals_b"] = (rec["ink_b"] == rec["ink_d"] and
                                 rec["contours_b"] == rec["contours_d"] and
                                 rec["segs_b"] == rec["segs_d"])
        except Exception as e:
            rec["error"] = str(e)[:120]
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", default="work/lead/mapping_block_v270.jsonl")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--out", default="work/lead/strip-border-ab.json")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    rows = []
    for line in open(os.path.join(ROOT, args.mapping), encoding="utf-8"):
        r = json.loads(line)
        for a in r.get("assigned") or []:
            box = (a.get("cand") or {}).get("box") or a.get("box")
            if a.get("char") and box:
                rows.append({"page": r["page"], "half": r.get("half", ""),
                             "char": a["char"], "box": box})
    rows.sort(key=lambda x: (x["page"], x["half"], x["char"]))
    if args.sample and args.sample < len(rows):
        step = max(1, len(rows) // args.sample)
        rows = rows[::step][:args.sample]
    by_page = {}
    for it in rows:
        by_page.setdefault((it["page"], it["half"]), []).append(
            {"char": it["char"], "box": it["box"]})
    jobs = [(p, h, items) for (p, h), items in sorted(by_page.items())]
    workers = max(1, min(10, args.workers))
    results = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(worker, jobs, chunksize=1):
            results.extend(res)
    results.sort(key=lambda r: r["char"])
    ok = [r for r in results if "error" not in r and r.get("ok_a") and r.get("ok_b")
          and r.get("ok_c") and r.get("ok_d")]
    changed = [r for r in ok if r.get("strip_changed")]
    errors = [r for r in results if "error" in r]
    top = sorted(ok, key=lambda r: -r["removed_frac"])[:30]
    summary = {
        "sample_n": len(rows),
        "evaluated": len(results),
        "ok_pairs": len(ok),
        "errors": len(errors),
        "error_sample": errors[:10],
        "changed_n": len(changed),
        "d_equals_a_n": sum(1 for r in ok if r.get("d_equals_a")),
        "d_equals_b_n": sum(1 for r in ok if r.get("d_equals_b")),
        "d_vs_a_sample": [{"char": r["char"], "page": r["page"],
                           "contours": [r["contours_a"], r["contours_d"]],
                           "ink": [r["ink_a"], r["ink_d"]],
                           "segs": [r["segs_a"], r["segs_d"]]}
                          for r in ok if not r.get("d_equals_a")][:40],
        "c_equals_a_n": sum(1 for r in ok if r.get("c_equals_a")),
        "c_equals_b_n": sum(1 for r in ok if r.get("c_equals_b")),
        "c_vs_a_sample": [{"char": r["char"], "page": r["page"],
                           "contours": [r["contours_a"], r["contours_c"]],
                           "ink": [r["ink_a"], r["ink_c"]],
                           "segs": [r["segs_a"], r["segs_c"]]}
                          for r in ok if not r.get("c_equals_a")][:40],
        "c_vs_b_sample": [{"char": r["char"], "page": r["page"],
                           "contours": [r["contours_b"], r["contours_c"]],
                           "ink": [r["ink_b"], r["ink_c"]]}
                          for r in ok if not r.get("c_equals_b")][:40],
        "changed_sample": [{"char": r["char"], "page": r["page"], "half": r["half"],
                            "removed_px": r["removed_px"],
                            "removed_frac": r["removed_frac"],
                            "ink_a": r["ink_a"], "ink_b": r["ink_b"],
                            "contours_a": r["contours_a"], "contours_b": r["contours_b"]}
                           for r in changed[:50]],
        "total_removed_px": sum(r["removed_px"] for r in ok),
        "contour_delta_n": sum(1 for r in ok if r["contours_a"] != r["contours_b"]),
        "ink_delta_n": sum(1 for r in ok if r["ink_a"] != r["ink_b"]),
        "top_removed_frac": [{"char": r["char"], "page": r["page"], "half": r["half"],
                              "removed_frac": r["removed_frac"],
                              "removed_px": r["removed_px"],
                              "contours_a": r["contours_a"], "contours_b": r["contours_b"]}
                             for r in top],
        "rule": "A=strip_border True（现状）；B=False（纯 pre-cut）；removed_px=strip_border_lines 删除的像素",
        "rows": ok,
    }
    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as fo:
        json.dump(summary, fo, ensure_ascii=False, indent=1)
    print(json.dumps({k: summary[k] for k in
                      ("sample_n", "ok_pairs", "errors", "changed_n",
                       "total_removed_px", "contour_delta_n", "ink_delta_n")},
                     ensure_ascii=False))
    print(f"AB_RESULT {args.out}")


if __name__ == "__main__":
    main()
