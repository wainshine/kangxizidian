#!/usr/bin/env python3
"""QA 剔除字的重试：对 render_bad/tiny 字，在 charalign14 映射中找替代候选框，
   选字头级（p90≥4.5 或短边≥130）且未被占用的最佳框，写回 union/mapping/manifest。"""
import argparse, json, os
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--union", default=os.path.join(ROOT, "work/lead/confirmed_union9.json"))
    ap.add_argument("--excluded", required=True)
    ap.add_argument("--mapping", default=os.path.join(ROOT, "work/map/charalign14/mapping.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/glyph_retry_report.json"))
    ap.add_argument("--p90-min", type=float, default=4.5)
    args = ap.parse_args()
    import cv2, fitz
    sys_path = os.path.join(ROOT, "scripts")
    import sys as _sys
    if sys_path not in _sys.path:
        _sys.path.insert(0, sys_path)
    import font_norm
    union = json.load(open(args.union))
    exc = json.load(open(args.excluded))
    target = set(exc.get("render_bad", [])) | set(exc.get("tiny", []))
    canon = set(json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl")))
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    alt = {}
    for l in open(args.mapping, encoding="utf-8"):
        r = json.loads(l)
        for a in r.get("assigned", []):
            ch = a.get("char"); box = (a.get("cand") or {}).get("box")
            if ch and box:
                alt.setdefault(ch, []).append((r["page"], r["half"], tuple(int(v) for v in box)))
    used = {(r["page"], r["half"], tuple(r["box"])) for r in union.values()}
    docs = {}
    added = []
    for ch in sorted(target):
        if ch not in canon:
            continue
        best = None
        for (page, half, box) in alt.get(ch, []):
            if (page, half, box) in used:
                continue
            vol = page[:2]
            if vol not in docs:
                docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            b = [int(v) * 2 for v in box]
            crop = img[max(0, b[1]):b[3], max(0, b[0]):b[2]]
            if crop.size == 0 or min(crop.shape) < 60:
                continue
            g = cv2.medianBlur(crop, 3)
            thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            ink = (g < min(max(int(thr), 100), 210)).astype(np.uint8)
            dt = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
            vals = dt[dt > 0]
            p90 = float(np.percentile(vals, 90)) if vals.size else 0.0
            if p90 >= args.p90_min or min(crop.shape) >= 130:
                # 渲染近似检查：矢量化后渲染 256px，连通域必须 ≤14（与 font_qa render_bad 同口径）
                try:
                    res = font_norm.vectorize_gray(crop)
                except Exception:
                    res = {"ok": False}
                if not res.get("ok"):
                    continue
                S = 256
                mask = np.zeros((S, S), np.uint8)
                for c in res["contours"]:
                    pts = [(-y / 760 * S + S / 2, x / 760 * S + S / 2) for x, y in
                           [(c["start"][0], c["start"][1])] + [(seg[-2], seg[-1]) for seg in c["segs"]]]
                    pts = np.array([[int(px), int(py)] for px, py in pts], np.int32)
                    cv2.fillPoly(mask, [pts], 1)
                ncomp = cv2.connectedComponents(mask)[0] - 1
                if ncomp > 14:
                    continue
                score = p90 + min(crop.shape) / 100.0
                if best is None or score > best[0]:
                    best = (score, page, half, box, {"w": int(crop.shape[1]), "h": int(crop.shape[0]),
                                                     "p90": round(p90, 2)})
        if best:
            _, page, half, box, st = best
            union[ch] = {"char": ch, "page": page, "half": half, "box": list(box),
                         "src": "qa_retry", "quality": st}
            used.add((page, half, box))
            added.append({"char": ch, "page": page, "half": half, "box": list(box), "p90": st["p90"]})
    for d in docs.values():
        d.close()
    json.dump(union, open(args.union, "w"), ensure_ascii=False)
    rows = {}
    for ch, rec in sorted(union.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    with open(os.path.join(ROOT, "work/lead/mapping_verified_all9.jsonl"), "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst], "in_body": True,
                                "header_ok": None}, ensure_ascii=False) + "\n")
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v21.json")))
    for ch in target:
        man["chars"].pop(ch, None)
    for a in added:
        man["chars"][a["char"]] = {"char": a["char"], "codepoint": f"U+{ord(a['char']):04X}",
                                   "key": f"v21r_{a['page']}_{a['half']}",
                                   "page": a["page"], "half": a["half"], "box": a["box"],
                                   "layer": "zhujuan", "label_source": "qa_retry",
                                   "verified_by": "QA 重试替代字形（p90≥4.5）"}
    man["n_chars"] = len(man["chars"])
    json.dump(man, open(os.path.join(ROOT, "work/lead/manifest-v21.json"), "w"), ensure_ascii=False)
    json.dump({"n_target": len(target), "n_added": len(added), "added": added},
              open(args.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"n_target": len(target), "n_added": len(added)}))


if __name__ == "__main__":
    main()
