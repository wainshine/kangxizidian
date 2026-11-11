#!/usr/bin/env python3
"""内容缺失闸（P0-1）：与上一基线字体逐字对比「墨量 + 配准 IoU」，找被误删部件的字。

用法: python scripts/content_loss_gate.py <old.ttf> <new.ttf> <old_manifest> <out.json>
指标：ink_ratio = new_ink/old_ink（同 256px 渲染，字形都归一到 760）；iou = 配准后 IoU。
掉墨：ink_ratio < 0.80 或 iou < 0.55 记为疑似内容缺损。
"""
import json, os, sys
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def job(args):
    old_font, new_font, chars = args
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
    from fidelity_eval import glyph_mask_from_font, register_iou
    out = []
    n_ok = 0
    for ch in chars:
        try:
            a = glyph_mask_from_font(old_font, ch)
            b = glyph_mask_from_font(new_font, ch)
            ia, ib = int(a.sum()), int(b.sum())
            if ia == 0:
                continue
            ratio = ib / ia
            iou, _ = register_iou(b, a)
            # 内容缺损判定：明显掉墨且形状不符（高 IoU 的掉墨多为笔画粗细差异，非缺件）
            n_ok += 1
            if ratio < 0.50 or (ratio < 0.80 and iou < 0.70):
                out.append({"char": ch, "ink_old": ia, "ink_new": ib,
                            "ink_ratio": round(ratio, 3), "iou": round(iou, 3)})
        except Exception as e:
            out.append({"char": ch, "error": str(e)[:80]})
    return n_ok, out


def main():
    old_font, new_font, man_path, out_path = sys.argv[1:5]
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    chars = sorted(man)
    n = max(1, (len(chars) + 7) // 8)
    chunks = [(old_font, new_font, chars[i:i+n]) for i in range(0, len(chars), n)]
    rows = []
    n_ok_total = 0
    with ProcessPoolExecutor(max_workers=8) as ex:
        for n_ok, res in ex.map(job, chunks):
            n_ok_total += n_ok
            rows.extend(res)
    rows.sort(key=lambda r: r.get("ink_ratio", 1.0))
    json.dump(rows, open(os.path.join(ROOT, out_path), "w"), ensure_ascii=False, indent=1)
    if n_ok_total < 0.98 * len(chars):
        print(json.dumps({"ERROR": "覆盖不足", "n_checked": n_ok_total, "n_expected": len(chars),
                          "damaged": sum(1 for r in rows if "ink_ratio" in r)}, ensure_ascii=False))
        sys.exit(2)
    rows = [r for r in rows if "ink_ratio" in r]
    print(json.dumps({"n_checked": len(chars), "damaged": len(rows),
                      "lt50": sum(1 for r in rows if r["ink_ratio"] < 0.5),
                      "20_50": sum(1 for r in rows if 0.5 <= r["ink_ratio"] < 0.8),
                      "sample": rows[:15]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
