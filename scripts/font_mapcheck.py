#!/usr/bin/env python3
"""C 流 · mapping.jsonl 体检（联调前置检查，不做任何字体构建）。

用途：Lead 产出全量 mapping 后，先跑本脚本查「格式/坐标/重复/非基本区」类问题，
再喂 `font_build.py --mapping`。只读，不写 mapping。

用法：
  .venv/bin/python scripts/font_mapcheck.py --mapping work/font/mapping/full.jsonl
输出：work/font/build/mapcheck.json + 终端摘要。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"

BASIC_LO, BASIC_HI = 0x4E00, 0x9FFF   # CJK 基本区（D11：只处理基本区）

# 150dpi 页图尺寸（各卷略有差异）；box 越界的粗判阈值
PAGE_W, PAGE_H = 1901, 1642


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", default=str(WORK / "mapping" / "full.jsonl"))
    ap.add_argument("--out", default=str(WORK / "build" / "mapcheck.json"))
    ap.add_argument("--max-show", type=int, default=30)
    args = ap.parse_args()

    path = Path(args.mapping)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise SystemExit(f"mapping 不存在: {path}")
    pdf_map = json.load(open(ROOT / "work" / "t2" / "pdf_map.json"))

    stats = Counter()
    pages = set()
    chars = Counter()
    problems = {"bad_rows": [], "bad_boxes": [], "bad_chars": [], "bad_pages": [],
                "duplicate_chars": [], "out_of_basic": []}
    n_assigned = 0
    for ln, line in enumerate(open(path), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            problems["bad_rows"].append({"line": ln, "error": str(e)})
            continue
        page, half = r.get("page"), r.get("half", "")
        if not page or not isinstance(page, str) or "_" not in page:
            problems["bad_pages"].append({"line": ln, "page": page, "half": half})
        else:
            pages.add(page)
            pdf, pno = page.split("_")
            if pdf not in pdf_map:
                problems["bad_pages"].append({"line": ln, "page": page,
                                              "reason": f"未知 pdf {pdf}"})
        assigned = r.get("assigned")
        if not isinstance(assigned, list):
            problems["bad_rows"].append({"line": ln, "error": "assigned 不是 list"})
            continue
        for a in assigned:
            n_assigned += 1
            if not isinstance(a, dict):
                problems["bad_rows"].append({"line": ln, "error": "assigned 项不是 dict"})
                continue
            ch = a.get("char")
            cand = a.get("cand") or {}
            box = cand.get("box") or a.get("box")
            if not ch or not isinstance(ch, str) or len(ch) != 1:
                problems["bad_chars"].append({"line": ln, "char": ch})
                continue
            chars[ch] += 1
            cp = ord(ch)
            if not (BASIC_LO <= cp <= BASIC_HI):
                problems["out_of_basic"].append({"line": ln, "char": ch,
                                                 "codepoint": f"U+{cp:04X}"})
            if not (isinstance(box, list) and len(box) == 4
                    and all(isinstance(v, (int, float)) for v in box)):
                problems["bad_boxes"].append({"line": ln, "char": ch, "box": box})
                continue
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            bad = (w <= 10 or h <= 10 or w > 300 or h > 300
                   or x0 < 0 or y0 < 0 or x1 > PAGE_W or y1 > PAGE_H
                   or not (0.45 <= w / max(1, h) <= 2.2))
            if bad:
                problems["bad_boxes"].append({"line": ln, "char": ch,
                                              "box": [round(v, 1) for v in box],
                                              "w": round(w, 1), "h": round(h, 1)})
    for ch, n in chars.items():
        if n > 1:
            problems["duplicate_chars"].append({"char": ch, "n": n})

    summary = {
        "mapping": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "lines": sum(1 for _ in open(path)),
        "pages": len(pages), "assigned": n_assigned,
        "unique_chars": len(chars),
        "basic_block": sum(1 for ch in chars if BASIC_LO <= ord(ch) <= BASIC_HI),
        "duplicate_chars": len(problems["duplicate_chars"]),
        "bad_counts": {k: len(v) for k, v in problems.items()},
        "problems": {k: v[: args.max_show] for k, v in problems.items()},
        "ok": all(not v for v in problems.values()),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps({k: summary[k] for k in
                      ("lines", "pages", "assigned", "unique_chars", "basic_block",
                       "duplicate_chars", "bad_counts", "ok")},
                     ensure_ascii=False, indent=1))
    if summary["problems"]["bad_boxes"]:
        print("bad_boxes sample:", summary["problems"]["bad_boxes"][:5])
    if summary["problems"]["out_of_basic"]:
        print("out_of_basic sample:", summary["problems"]["out_of_basic"][:5])
    print("->", out)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
