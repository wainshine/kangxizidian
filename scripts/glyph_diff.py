#!/usr/bin/env python3
"""精确 glyf 轮廓 diff（audit4 DATA-401 / E39：禁止再用「候选阈值筛集」当变化字）。

比较两个 TTF 的 cmap 字形轮廓（coordinates + endPtsOfContours + flags；复合字形比较组件），
输出 changed / added / removed 字符列表。stdout JSON；--out 写 JSON、--md 写 Markdown 摘要。

用法:
  python scripts/glyph_diff.py --old v2.6.2 --new v2.6.3
  python scripts/glyph_diff.py --old work/font/build/KangXiKai-v2.6.2.ttf \
      --new work/font/build/KangXiKai-v2.6.3.ttf --out work/lead/diff-v262-v263.json \
      --md work/lead/diff-v262-v263.md
版本写法：2.6.2 / v2.6.2 / v262（→ work/font/build/KangXiKai-v2.6.2.ttf）。

验收（v2.6.3 vs v2.6.2）：changed 5（急愈架紉釘）+ added 1（釕）+ removed 0。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def resolve_font(spec):
    if os.path.exists(spec):
        return os.path.abspath(spec)
    p = spec if os.path.isabs(spec) else os.path.join(ROOT, spec)
    if os.path.exists(p):
        return p
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", spec)
    if m:
        ver = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
        cand = os.path.join(ROOT, "work/font/build", f"KangXiKai-v{ver}.ttf")
        if os.path.exists(cand):
            return cand
    m = re.fullmatch(r"v?(\d)(\d)(\d)", spec)
    if m:
        ver = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
        cand = os.path.join(ROOT, "work/font/build", f"KangXiKai-v{ver}.ttf")
        if os.path.exists(cand):
            return cand
    raise SystemExit(f"ABORT: 无法解析字体 {spec!r}（既不是路径也不是版本号）")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def outline_key(g):
    """字形轮廓的精确可比较描述（简单字形 = 点/轮廓端点/标志；复合 = 组件列表）。"""
    from fontTools.ttLib import TTFont  # noqa: F401  (类型提示用)

    if g.isComposite():
        return ("composite", tuple((c.glyphName, c.x, c.y,
                                    tuple(getattr(c, "transform", []) or []))
                                   for c in g.components))
    return ("simple", tuple(g.coordinates), tuple(g.endPtsOfContours), tuple(g.flags))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="旧字体（路径或版本号，如 2.6.2 / v262）")
    ap.add_argument("--new", required=True, help="新字体")
    ap.add_argument("--out", default=None, help="JSON 输出路径")
    ap.add_argument("--md", default=None, help="Markdown 输出路径")
    ap.add_argument("--limit", type=int, default=0, help="列表截断（0=不截断；仅影响输出）")
    args = ap.parse_args()
    from fontTools.ttLib import TTFont

    old_p, new_p = resolve_font(args.old), resolve_font(args.new)
    f_old, f_new = TTFont(old_p), TTFont(new_p)
    cmap_old, cmap_new = f_old.getBestCmap(), f_new.getBestCmap()
    glyf_old, glyf_new = f_old["glyf"], f_new["glyf"]
    common = set(cmap_old) & set(cmap_new)
    changed, added, removed = [], [], []
    for cp in sorted(common):
        ch = chr(cp)
        if outline_key(glyf_old[cmap_old[cp]]) != outline_key(glyf_new[cmap_new[cp]]):
            changed.append(ch)
    for cp in sorted(set(cmap_new) - set(cmap_old)):
        added.append(chr(cp))
    for cp in sorted(set(cmap_old) - set(cmap_new)):
        removed.append(chr(cp))

    def cp_list(chars):
        return [{"char": ch, "codepoint": f"U+{ord(ch):04X}"} for ch in chars]

    lim = args.limit or 0
    result = {
        "old": os.path.relpath(old_p, ROOT) if old_p.startswith(ROOT) else old_p,
        "new": os.path.relpath(new_p, ROOT) if new_p.startswith(ROOT) else new_p,
        "old_sha256": sha256_file(old_p),
        "new_sha256": sha256_file(new_p),
        "n_old": len(cmap_old), "n_new": len(cmap_new), "n_common": len(common),
        "counts": {"changed": len(changed), "added": len(added), "removed": len(removed)},
        "changed": cp_list(changed[:lim] if lim else changed),
        "added": cp_list(added[:lim] if lim else added),
        "removed": cp_list(removed[:lim] if lim else removed),
        "method": "精确 glyf 轮廓比较（coordinates+endPtsOfContours+flags；复合比组件）",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fo:
            json.dump(result, fo, ensure_ascii=False, indent=1)
    if args.md:
        md = ["# 精确 glyf 轮廓 diff", "",
              f"- old: `{result['old']}` (sha `{result['old_sha256'][:12]}…`)",
              f"- new: `{result['new']}` (sha `{result['new_sha256'][:12]}…`)",
              f"- 字形数: {result['n_old']} → {result['n_new']}；共同 {result['n_common']}", "",
              "| 类别 | 数量 | 字符 |", "|---|---|---|",
              f"| changed | **{len(changed)}** | {' '.join(changed) or '—'} |",
              f"| added | **{len(added)}** | {' '.join(added) or '—'} |",
              f"| removed | **{len(removed)}** | {' '.join(removed) or '—'} |", ""]
        os.makedirs(os.path.dirname(os.path.abspath(args.md)) or ".", exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as fo:
            fo.write("\n".join(md))
    print(json.dumps({k: result[k] for k in
                      ("old", "new", "n_old", "n_new", "n_common", "counts",
                       "changed", "added", "removed", "generated_utc")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
