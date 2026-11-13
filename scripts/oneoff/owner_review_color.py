#!/usr/bin/env python3
"""彩色版 owner 核验表（编目文字彩色；字形/裁片灰阶）。版式复用 scripts/review_sheet.py。"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from review_sheet import build_sheet  # noqa: E402

FONT = os.environ.get("OWNER_FONT", os.path.join(ROOT, "work/font/build/KangXiKai-v2.5.8.ttf"))
SRC = os.environ.get("OWNER_JSON", os.path.join(ROOT, "work/review/owner-provenance-100-v258.json"))
OUT = os.environ.get("OWNER_OUT", os.path.join(ROOT, "work/review/owner-provenance-100-v258-color.png"))

rows = json.load(open(SRC, encoding="utf-8"))
build_sheet(rows, FONT, OUT, color=True)
print(json.dumps({"out": OUT, "n": len(rows)}, ensure_ascii=False))
