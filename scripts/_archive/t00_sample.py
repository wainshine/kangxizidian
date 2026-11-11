#!/usr/bin/env python3
"""T0.0 语料盘点 · 抽样清单

规则（可复现，无随机数）：
- PDF 01–12（子集…亥集）：每集均匀抽 20 页，跳过每册开头 3 页与结尾 3 页（卷首题名/卷尾）。
- PDF 13（补遗/备考）：均匀抽 40 页，同样跳头尾 3 页。
- PDF 00（总目/检字/辨似/等韵）不参与字头抽样（索引册，另作对账参考）。
- 页码从 1 起，与 PyMuPDF 的 page_no+1 一致。

输出 work/t00/sample_manifest.json：
  [{"pdf": "01", "file": "...", "npages": N, "page": p}, ...]
"""
import json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "康熙字典")
OUT_DIR = os.path.join(ROOT, "work", "t00")

import fitz  # PyMuPDF


def sample_pages(npages: int, want: int, skip_head: int = 3, skip_tail: int = 3):
    lo, hi = skip_head, npages - 1 - skip_tail  # 0-based inclusive
    span = hi - lo + 1
    if span <= 0:
        raise ValueError(f"npages={npages} too small")
    picks = []
    for i in range(want):
        idx = lo + math.floor(i * span / want)
        if idx > hi:
            idx = hi
        if picks and idx == picks[-1]:
            idx = min(hi, idx + 1)
        picks.append(idx)
    return sorted(set(picks))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pdfs = sorted(f for f in os.listdir(SRC) if f.endswith(".pdf"))
    manifest = []
    for f in pdfs:
        num = f.split(".")[1]  # 00/01/.../13
        doc = fitz.open(os.path.join(SRC, f))
        n = doc.page_count
        doc.close()
        if num == "00":
            continue
        want = 40 if num == "13" else 20
        for p0 in sample_pages(n, want):
            manifest.append({"pdf": num, "file": f, "npages": n, "page0": p0, "page": p0 + 1})
    with open(os.path.join(OUT_DIR, "sample_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    from collections import Counter
    c = Counter(m["pdf"] for m in manifest)
    print("sampled pages:", len(manifest))
    print("by pdf:", dict(sorted(c.items())))
    print("manifest ->", os.path.join(OUT_DIR, "sample_manifest.json"))


if __name__ == "__main__":
    sys.exit(main())
