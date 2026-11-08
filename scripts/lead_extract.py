#!/usr/bin/env python3
"""Lead · 字形抽取：mapping（框级指派）→ work/glyphs/ 字形库 + 索引。

输入 mapping JSONL（lead_solver2 输出）：每行 {page, half, assigned:[{char, cand:{box,...}}]}
box 为 150dpi 页坐标（与 work/t00/pages/*.png 一致；T1 约定），本脚本重新以 300dpi 渲染 PDF
裁切，保证字形质量。

输出：
  work/glyphs/<shard>/<char>_<src>.png   300dpi 灰度裁切（四周留 6px 白边）
  work/glyphs/index.jsonl                每行一条来源记录
  work/glyphs/stats.json                 覆盖统计（unique 基本区/扩展区等）

去重：同一 char 多条来源全部保留（下游选优）；记录来源 page/half/box/provenance=real。
"""
import json, os, sys, argparse, collections
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/glyphs"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--max-pages", type=int, default=0)
    args = ap.parse_args()
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, "_cache"), exist_ok=True)
    idx = open(os.path.join(args.out, "index.jsonl"), "w", encoding="utf-8")
    page_cache = {}
    n = 0
    doc_cache = {}
    stats = collections.Counter()
    for line in open(args.mapping, encoding="utf-8"):
        rec = json.loads(line)
        page = rec["page"]  # e.g. 01_0110
        vol = page[:2]
        pg = int(page[3:])
        for a in rec.get("assigned", []):
            ch = a["char"]
            box = a["cand"]["box"]  # 150dpi coords
            if not is_cjk(ch):
                continue
            k = (vol, pg)
            if k != page_cache.get("key"):
                if k not in doc_cache:
                    doc_cache[k] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
                doc = doc_cache[k]
                pix = doc[pg - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
                page_cache["key"] = k
                page_cache["img"] = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width)
            img = page_cache["img"]
            scale = args.dpi / 150.0
            x0, y0, x1, y1 = [int(round(v * scale)) for v in box]
            x0 = max(0, x0 - 8); y0 = max(0, y0 - 8)
            x1 = min(img.shape[1], x1 + 8); y1 = min(img.shape[0], y1 + 8)
            if x1 - x0 < 20 or y1 - y0 < 20:
                continue
            crop = img[y0:y1, x0:x1]
            shard = f"{ord(ch) % 100:02d}"
            d = os.path.join(args.out, shard)
            os.makedirs(d, exist_ok=True)
            src = f"{page}_{rec['half']}_{box[0]}_{box[1]}"
            fn = os.path.join(d, f"{ch}_{src}.png")
            # 用 PIL 存（cv2 对空数组会段错误）
            from PIL import Image
            Image.fromarray(crop).save(fn)
            idx.write(json.dumps({"char": ch, "file": os.path.relpath(fn, args.out),
                                  "page": page, "half": rec["half"], "box150": box,
                                  "provenance": "real", "dpi": args.dpi},
                                 ensure_ascii=False) + "\n")
            n += 1
            stats["glyphs"] += 1
            stats["unique_chars"] += 1
    idx.close()
    # 统计（unique 需要二次统计）
    chars = set()
    for line in open(os.path.join(args.out, "index.jsonl"), encoding="utf-8"):
        chars.add(json.loads(line)["char"])
    basic = set(chr(c) for c in range(0x4E00, 0xA000))
    st = {"glyphs": n, "unique_chars": len(chars),
          "unique_basic_cjk": len(chars & basic),
          "coverage_basic_20992": f"{len(chars & basic)/20992:.2%}"}
    json.dump(st, open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(st, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
