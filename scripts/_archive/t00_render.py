#!/usr/bin/env python3
"""T0.0 · 渲染抽样页为 150 dpi 灰度 PNG（检测与 OCR 都够用）。

输入 work/t00/sample_manifest.json
输出 work/t00/pages/{pdf}_{page:04d}.png + work/t00/render_log.json
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "康熙字典")
T00 = os.path.join(ROOT, "work", "t00")
DPI = 150

import fitz

# 并发硬约束（AGENTS 精神：≤10 线程）
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


def main():
    man = json.load(open(os.path.join(T00, "sample_manifest.json"), encoding="utf-8"))
    out_dir = os.path.join(T00, "pages")
    os.makedirs(out_dir, exist_ok=True)
    log = []
    t0 = time.time()
    by_pdf = {}
    for m in man:
        by_pdf.setdefault(m["pdf"], m["file"])
    for i, m in enumerate(man):
        path = os.path.join(out_dir, f"{m['pdf']}_{m['page']:04d}.png")
        if os.path.exists(path):
            log.append({"page": m["page"], "pdf": m["pdf"], "status": "cached"})
            continue
        doc = fitz.open(os.path.join(SRC, by_pdf[m["pdf"]]))
        page = doc[m["page0"]]
        pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
        pix.save(path)
        log.append({"pdf": m["pdf"], "page": m["page"],
                    "w": pix.width, "h": pix.height, "status": "ok"})
        doc.close()
        if (i + 1) % 40 == 0:
            print(f"{i+1}/{len(man)} rendered, {time.time()-t0:.0f}s", flush=True)
    with open(os.path.join(T00, "render_log.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=1)
    print(f"done: {len(log)} pages in {time.time()-t0:.0f}s -> {out_dir}")


if __name__ == "__main__":
    sys.exit(main())
