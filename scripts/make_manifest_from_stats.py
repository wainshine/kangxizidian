#!/usr/bin/env python3
"""从 build_stats.json 生成候选版 manifest（候选流程标准步骤）。

背景：构建只产出 TTF + build_stats；闸/复核包/发布材料需要 manifest
（{version, chars:{char:{page,half,box,label_source}}}）。此前每次手写，容易漏/错。
本脚本把 build_stats.glyphs 的 page/half/box/label_source 转成 manifest。

用法：
  .venv/bin/python scripts/make_manifest_from_stats.py \
      --stats work/font/build/KangXiKai-v2.6.3.build_stats.json \
      --out   work/font/build/manifest_v263.json --version 2.6.3
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", required=True, help="<font>.build_stats.json")
    ap.add_argument("--out", required=True, help="输出 manifest JSON")
    ap.add_argument("--version", required=True)
    args = ap.parse_args()

    sp = args.stats if os.path.isabs(args.stats) else os.path.join(ROOT, args.stats)
    st = json.load(open(sp, encoding="utf-8"))
    glyphs = st.get("glyphs") or {}
    if not glyphs:
        raise SystemExit(f"ABORT: {sp} 无 glyphs 记录")
    chars = {}
    bad = []
    for ch, g in glyphs.items():
        rec = {k: g.get(k) for k in ("page", "half", "box", "label_source")}
        if not rec["page"] or not rec["box"]:
            bad.append(ch)
            continue
        chars[ch] = rec
    if bad:
        raise SystemExit(f"ABORT: {len(bad)} 字缺 page/box：{bad[:8]}")
    out = {"version": args.version, "chars": chars}
    op = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(op) or ".", exist_ok=True)
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"manifest": op, "version": args.version, "chars": len(chars),
                      "source_stats": sp, "stats_font_sha256": st.get("sha256")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
