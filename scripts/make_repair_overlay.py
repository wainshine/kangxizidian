#!/usr/bin/env python3
"""【已停用 2026-11-12 / D20·BF-43】生成 repair overlay（历史工具，输出已无消费者）。

overlay/restore 整字拷贝通道已从主链删除（会把旧架构框线带回，AGENTS §1 禁止恢复）。
本脚本现在只做「输入校验后立即退出」，保留文件仅为历史方法与证据说明。


用法:
  python scripts/make_repair_overlay.py --base <重建基座字体> --final <发布字体> \
      --manifest <发布 manifest> --out work/lead/repair_overlay.jsonl

原理：以「mapping 基座字体」与「发布字体」逐字比较 glyf 坐标点集合，
差异字 → 从发布字体提取原始点（endPts/coordinates/flags）写入 overlay；
font_build --repair-overlay 重建时直接使用这些点，保证发布字形可复现。

验收：对 v2.5.6 重跑本脚本，输出 overlay 的 sha256 应与
      work/lead/repair_overlay_v256.meta.json 中记录值一致（1,602 字）。
"""
import argparse, hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="重建基座字体（无 overlay 的 mapping 构建产物）")
    ap.add_argument("--final", required=True, help="发布字体")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raise SystemExit("D20/BF-43: overlay/restore 通道已删除（产物无消费者）；"
                     "修复必须回写 mapping 后重切，禁止整字拷贝旧字形。")
    from fontTools.ttLib import TTFont
    base = TTFont(os.path.join(ROOT, args.base))
    final = TTFont(os.path.join(ROOT, args.final))
    gb = base["glyf"]; gf = final["glyf"]
    cb = base.getBestCmap(); cf = final.getBestCmap()
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    rows = []
    for ch in sorted(man):
        cp = ord(ch)
        if cp not in cb or cp not in cf:
            continue
        a = gb[cb[cp]]; b = gf[cf[cp]]
        ca = list(map(tuple, a.coordinates)) if a.numberOfContours > 0 else []
        cb2 = list(map(tuple, b.coordinates)) if b.numberOfContours > 0 else []
        # 基座=发布 且 点数一致 → 无需 overlay；否则视为修复字
        if ca == cb2 and a.numberOfContours == b.numberOfContours:
            continue
        if b.numberOfContours <= 0:
            continue
        rows.append({"char": ch,
                     "endPts": [int(e) for e in b.endPtsOfContours],
                     "points": [[int(x), int(y), int(fl) & 1]
                                for (x, y), fl in zip(b.coordinates, b.flags)]})
    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    h = hashlib.sha256(open(os.path.join(ROOT, args.out), "rb").read()).hexdigest()
    print(json.dumps({"chars": len(rows), "sha256": h, "out": args.out}))


if __name__ == "__main__":
    main()
