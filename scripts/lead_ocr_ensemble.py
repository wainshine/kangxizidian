#!/usr/bin/env python3
"""多引擎集成 OCR：对指定候选框用多个模型识别，输出逐框投票。"""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", os.path.join(ROOT, "work/paddlex_cache"))

MODELS = ["PP-OCRv6_medium_rec", "PP-OCRv6_small_rec", "PP-OCRv6_tiny_rec",
          "PP-OCRv5_server_rec", "PP-OCRv5_mobile_rec",
          "PP-OCRv4_server_rec_doc", "ch_SVTRv2_rec", "chinese_cht_PP-OCRv3_mobile_rec"]


def _work(chunk):
    import numpy as np
    import cv2
    import fitz
    from paddleocr import TextRecognition
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    recs = []
    for m in MODELS:
        try:
            recs.append((m, TextRecognition(model_name=m)))
        except Exception:
            pass
    docs = {}
    out = []
    for it in chunk:
        page = it["page"]
        vol = page[:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in it["box"]]
        pad = 8
        crop = img[max(0, b[1] - pad):b[3] + pad, max(0, b[0] - pad):b[2] + pad]
        if crop.size == 0 or min(crop.shape) < 16:
            continue
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        tmp = "/tmp/ens_%d.png" % os.getpid()
        cv2.imwrite(tmp, crop)
        rows = {}
        for m, rec in recs:
            try:
                o = rec.predict(tmp)
                r = (o[0].json.get("res", {}) or {})
                rows[m] = [r.get("rec_text", "") or "", round(float(r.get("rec_score") or 0), 3)]
            except Exception:
                rows[m] = ["", 0.0]
        out.append({"page": page, "half": it.get("half"), "box": it["box"],
                    "truth_hint": it.get("char"), "models": rows})
    for d in docs.values():
        d.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(ROOT, "work/lead/verify_candidates.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/ocr_ensemble.jsonl"))
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    import multiprocessing as mp
    items = json.load(open(args.inp))
    if args.limit:
        items = items[: args.limit]
    print("items", len(items), flush=True)
    chunks = [items[i::args.procs] for i in range(args.procs)]
    with open(args.out, "w", encoding="utf-8") as f, mp.Pool(args.procs) as pool:
        n = 0
        for rows in pool.imap_unordered(_work, chunks):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += len(rows)
            f.flush()
            print("cum", n, flush=True)
    print("done", args.out)


if __name__ == "__main__":
    main()
