#!/usr/bin/env python3
"""页级几何缓存（并行一次算好，所有阶段复用）：
每页一行：{page, lattice:{L/R:(px,py,phx,phy)}, text_bbox, quads:{L/R:(x0,y0,x1,y1,theta)}}
输出 work/lead/page_geometry.jsonl
"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(page):
    import font_build as fb
    from page_frames import detect_content_quads
    from detect_blocks import page_gray
    try:
        g = page_gray(page[:2], int(page[3:]))
        lat = fb.get_page_lattice(page)
        tbb = fb.get_page_text_bbox(page)
        quads = detect_content_quads(g)
        return {"page": page,
                "lattice": {k: (list(v) if v else None) for k, v in (lat or {}).items()},
                "text_bbox": list(tbb) if tbb else None,
                "quads": {k: {"box": list(q["box"]), "theta": q.get("theta", 0.0),
                               "M": np.asarray(q["M"]).tolist() if "M" in q else None,
                               "Minv": np.asarray(q["Minv"]).tolist() if "Minv" in q else None}
                          for k, q in (quads or {}).items()}}
    except Exception as e:
        return {"page": page, "error": str(e)[:120]}


def main():
    pages = []
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    import fitz
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count
        doc.close()
        for i in range(1, n + 1):
            pages.append(f"{vol}_{i:04d}")
    out = os.path.join(ROOT, "work/lead/page_geometry.jsonl")
    done = 0
    with ProcessPoolExecutor(max_workers=10) as ex, open(out, "w", encoding="utf-8") as fo:
        for r in ex.map(worker, pages, chunksize=8):
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            done += 1
            if done % 500 == 0:
                print("pages", done, "/", len(pages), flush=True)
    print(json.dumps({"pages": len(pages), "out": out}))


if __name__ == "__main__":
    main()
