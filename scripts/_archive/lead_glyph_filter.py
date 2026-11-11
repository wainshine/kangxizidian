#!/usr/bin/env python3
"""字形质量过滤（审计 P0-2 延伸）：剔除注文小字混入，并为被剔除的常用字找替代字形。

判定「字头级」：p90 笔画宽 ≥4.5（300dpi 距离变换）或短边 ≥130px；
  small/small_loose 来源一律剔除（按构造即小字层）；
  不合格字 → 在 charalign14 映射中找同字的其它候选框，逐框算 p90，取最佳（≥4.5）；
  仍找不到 → 丢弃并记录。
输出：confirmed_union9.json / mapping_verified_all9.jsonl / manifest-v21.json / glyph_filter_report.json
"""
import argparse, collections, json, os
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--union", default=os.path.join(ROOT, "work/lead/confirmed_union8.json"))
    ap.add_argument("--quality", default=os.path.join(ROOT, "work/lead/glyph_quality.jsonl"))
    ap.add_argument("--mapping", default=os.path.join(ROOT, "work/map/charalign14/mapping.jsonl"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "work/lead"))
    ap.add_argument("--p90-min", type=float, default=4.5)
    ap.add_argument("--side-min", type=int, default=130)
    args = ap.parse_args()
    import cv2
    import fitz
    union = json.load(open(args.union))
    qual = {}
    for l in open(args.quality, encoding="utf-8"):
        r = json.loads(l)
        qual[r["char"]] = r
    canon = set(json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl")))
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))

    # 同字其它候选框
    alt = collections.defaultdict(list)
    for l in open(args.mapping, encoding="utf-8"):
        r = json.loads(l)
        for a in r.get("assigned", []):
            ch = a.get("char")
            box = (a.get("cand") or {}).get("box")
            if ch and box:
                alt[ch].append((r["page"], r["half"], tuple(int(v) for v in box)))

    docs = {}

    def stats(page, half, box):
        vol = page[:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in box]
        crop = img[max(0, b[1]):b[3], max(0, b[0]):b[2]]
        if crop.size == 0 or min(crop.shape) < 24:
            return None
        g = cv2.medianBlur(crop, 3)
        thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        ink = (g < min(max(int(thr), 100), 210)).astype(np.uint8)
        dt = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
        vals = dt[dt > 0]
        return {"w": int(crop.shape[1]), "h": int(crop.shape[0]),
                "ink": round(float(ink.mean()), 4),
                "p90": round(float(np.percentile(vals, 90)) if vals.size else 0.0, 2)}

    def head_grade(ch, rec):
        q = qual.get(ch)
        if q is None:
            return False, None
        if q["src"] in ("small", "small_loose"):
            return False, q
        ok = q["p90"] >= args.p90_min or min(q["w"], q["h"]) >= args.side_min
        return ok, q

    final, replaced, dropped = {}, [], []
    used_boxes = set()
    # 先登记所有「直接保留」的框，避免替代框与它们撞车
    for ch, rec in union.items():
        ok0, _ = head_grade(ch, rec)
        if ok0:
            used_boxes.add((rec["page"], rec["half"], tuple(rec["box"])))
    for ch, rec in union.items():
        ok, q = head_grade(ch, rec)
        if ok:
            final[ch] = {**rec, "quality": q}
            continue
        # 找替代
        best = None
        for (page, half, box) in alt.get(ch, []):
            if (page, half, box) == (rec["page"], rec["half"], tuple(rec["box"])):
                continue
            st = stats(page, half, box)
            if (page, half, box) in used_boxes:
                continue
            if st and (st["p90"] >= args.p90_min or min(st["w"], st["h"]) >= args.side_min):
                score = st["p90"] + min(st["w"], st["h"]) / 100.0
                if best is None or score > best[0]:
                    best = (score, page, half, box, st)
        if best:
            _, page, half, box, st = best
            final[ch] = {**rec, "page": page, "half": half, "box": list(box),
                         "src": rec.get("src", "") + "+alt", "quality": st}
            used_boxes.add((page, half, box))
            replaced.append({"char": ch, "old": [rec["page"], rec["half"], rec["box"]],
                             "new": [page, half, list(box)], "p90": st["p90"]})
        else:
            dropped.append({"char": ch, "page": rec["page"], "half": rec["half"],
                            "box": rec["box"], "src": rec.get("src", ""),
                            "quality": q})
    for d in docs.values():
        d.close()
    union_path = os.path.join(args.outdir, "confirmed_union9.json")
    json.dump(final, open(union_path, "w"), ensure_ascii=False)
    rows = collections.OrderedDict()
    for ch, rec in sorted(final.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    mapping_path = os.path.join(args.outdir, "mapping_verified_all9.jsonl")
    with open(mapping_path, "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst],
                                "in_body": True, "header_ok": None},
                               ensure_ascii=False) + "\n")
    manifest_path = os.path.join(args.outdir, "manifest-v21.json")
    man = json.load(open(os.path.join(args.outdir, "manifest-v201.json")))
    chars = {}
    for ch, rec in sorted(final.items()):
        chars[ch] = {"char": ch, "codepoint": f"U+{ord(ch):04X}",
                     "key": f"v21_{rec['page']}_{rec['half']}",
                     "page": rec["page"], "half": rec["half"], "box": rec["box"],
                     "layer": "zhujuan", "label_source": rec.get("src", "base"),
                     "verified_by": "字头级尺寸/笔画宽(p90≥4.5)过滤" if "alt" in rec.get("src", "")
                     else man["chars"].get(ch, {}).get("verified_by", "")}
    man["version"] = "2.1.0"
    man["n_chars"] = len(chars)
    man["chars"] = chars
    json.dump(man, open(manifest_path, "w"), ensure_ascii=False)

    def is_basic(c):
        return 0x4E00 <= ord(c) <= 0x9FFF
    b = sum(1 for c in final if is_basic(c) and c in canon)
    report = {"n_in": len(union), "n_final": len(final),
              "n_replaced": len(replaced), "n_dropped": len(dropped),
              "replaced": replaced, "dropped": dropped,
              "basic_in_canonical": b,
              "basic_coverage_pct": round(b / 16567 * 100, 2),
              "outputs": [os.path.abspath(p) for p in (union_path, mapping_path, manifest_path)]}
    json.dump(report, open(os.path.join(args.outdir, "glyph_filter_report.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("n_in", "n_final", "n_replaced", "n_dropped",
                                             "basic_in_canonical", "basic_coverage_pct")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
