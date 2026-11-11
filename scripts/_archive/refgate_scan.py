#!/usr/bin/env python3
"""全量参考结构闸扫描：逐字找出「参考字体无对应墨迹」的悬浮小组件。"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from refgate import glyph_masks, analyze


def job(items):
    font, chars = items
    out = []
    for ch in chars:
        try:
            ours, ref = glyph_masks(font, ch)
            sus = [] if ref is None else analyze(ours, ref)
        except Exception as e:
            sus = []
        if sus:
            out.append({"char": ch, "suspects": sus})
    return out


def main():
    font = sys.argv[1]
    man = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, "work/lead/refgate_scan.jsonl")
    chars = sorted(json.load(open(man, encoding="utf-8"))["chars"].keys())
    n = max(1, (len(chars) + 7) // 8)
    chunks = [(font, chars[i:i + n]) for i in range(0, len(chars), n)]
    print("chars", len(chars), "chunks", len(chunks), flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(job, chunks):
            rows.extend(res)
    rows.sort(key=lambda r: r["char"])
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("flagged glyphs", len(rows), "->", out_path, flush=True)


if __name__ == "__main__":
    main()
