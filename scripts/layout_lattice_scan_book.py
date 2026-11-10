#!/usr/bin/env python3
"""全量格点法大字检测（150dpi，8 进程）→ work/lead/layout_lattice_boxes.jsonl"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def job(args):
    from layout_lattice_detect import page_gray, detect
    vol, pno = args
    try:
        r = detect(page_gray(vol, pno))
        if r is None:
            return {"page": f"{vol}_{pno:04d}", "boxes": [], "meta": None}
        r["page"] = f"{vol}_{pno:04d}"
        return r
    except Exception as e:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "err": str(e)}


def main():
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p))
    out = os.path.join(ROOT, "work/lead/layout_lattice_boxes.jsonl")
    print("pages", len(jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out, "w", encoding="utf-8") as fo:
        for res in ex.map(job, jobs, chunksize=16):
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            done += 1
            if done % 500 == 0:
                print("done", done, flush=True)
    print("finished", done, out, flush=True)


if __name__ == "__main__":
    main()
