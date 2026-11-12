#!/usr/bin/env python3
"""生成本轮人工复核包（复用 owner-provenance 版式库 scripts/review_sheet.py）。

用法：
  python scripts/make_round_pack.py --font work/font/build/KangXiKai-v2.6.1.ttf \
    --manifest work/font/build/manifest_v261.json \
    --ledger work/lead/round2_ledger.jsonl --outdir work/review/round-002

输出（只有 3 样，少即是多）：
  01-changes-*.png   本轮变更字（owner-provenance 版式）——用于逐字标记 ✗/?
  02-random100.png   全字体盲抽 100 字——用于查回归
  ledger.tsv         编号→字/页/框/类别——用于把编号翻回具体字
"""
import argparse, json, os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from review_sheet import build_sheet, write_tsv  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--random100", type=int, default=100)
    ap.add_argument("--no-color", action="store_true", help="输出灰度版（默认彩色编目文字）")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)
    font = os.path.join(ROOT, args.font)
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    rows = [json.loads(l) for l in open(os.path.join(ROOT, args.ledger), encoding="utf-8") if l.strip()]
    for i, r in enumerate(rows, 1):
        r["no"] = i
        if "page" not in r or "box" not in r:
            m = man[r["char"]]; r.update({"page": m["page"], "half": m.get("half", ""), "box": m["box"]})
    color = not args.no_color
    build_sheet(rows, font, os.path.join(outdir, "01-changes-{:03d}.png"), color=color)
    # 全字体盲抽回归（固定种子）
    rng = random.Random(20261112)
    pick = rng.sample(sorted(man), min(args.random100, len(man)))
    rr = []
    for i, ch in enumerate(pick, 1):
        m = man[ch]
        rr.append({"no": i, "char": ch, "page": m["page"], "half": m.get("half", ""),
                   "box": m["box"], "class": "random"})
    build_sheet(rr, font, os.path.join(outdir, "02-random100.png"), color=color)
    write_tsv(rows, os.path.join(outdir, "ledger.tsv"))
    print(json.dumps({"outdir": args.outdir, "rows": len(rows),
                      "pages": (len(rows) + 99) // 100, "random100": len(rr),
                      "outputs": ["01-changes-*.png", "02-random100.png", "ledger.tsv"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
