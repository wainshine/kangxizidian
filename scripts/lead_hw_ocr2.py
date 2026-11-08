#!/usr/bin/env python3
"""Lead · 补齐字头 OCR：对未覆盖的字头几何候选双模型识别（v5 server + v6 medium）。"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_ROOT = None
_ITEMS = None


def _work(chunk):
    import fitz, cv2, os as _os
    from paddleocr import TextRecognition
    import numpy as np
    mp_ = json.load(open(_os.path.join(ROOT, "work/t2/pdf_map.json")))
    rec5 = TextRecognition(model_name="PP-OCRv5_server_rec")
    rec6 = TextRecognition(model_name="PP-OCRv6_medium_rec")
    out = []
    docs = {}
    for page, cands in chunk:
        vol = page[:2]; pg = int(page[3:])
        if vol not in docs:
            docs[vol] = fitz.open(_os.path.join(ROOT, "康熙字典", mp_[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        for half, box in cands:
            x0, y0, x1, y1 = [int(v) * 2 for v in box]
            crop = img[max(0, y0 - 8):y1 + 8, max(0, x0 - 8):x1 + 8]
            if crop.size == 0 or min(crop.shape) < 10:
                continue
            crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            tmp = "/tmp/ocrfill_%d.png" % _os.getpid()
            cv2.imwrite(tmp, crop)
            for tag, rec in (("v5", rec5), ("v6", rec6)):
                try:
                    o = rec.predict(tmp)
                    r = o[0].json.get("res", {})
                    out.append({"page": page, "half": half, "box": list(box),
                                "model": tag, "text": r.get("rec_text", ""),
                                "score": float(r.get("rec_score") or 0)})
                except Exception as e:
                    out.append({"page": page, "half": half, "box": list(box),
                                "model": tag, "err": str(e)[:100]})
    for d in docs.values():
        d.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--need", default=os.path.join(ROOT, "work/lead/ocr_need.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hw_ocr_fill.jsonl"))
    ap.add_argument("--procs", type=int, default=6)
    args = ap.parse_args()
    import multiprocessing as mp
    need = json.load(open(args.need))
    by_page = collections.defaultdict(list)
    for p, h, b in need:
        by_page[p].append((h, tuple(b)))
    items = sorted(by_page.items())
    print("pages", len(items), "cands", len(need), flush=True)

    chunks = [items[i::args.procs] for i in range(args.procs)]
    with open(args.out, "w", encoding="utf-8") as f, mp.Pool(args.procs) as pool:
        for i, rows in enumerate(pool.imap_unordered(_work, chunks)):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print("chunk", i, "done", flush=True)
    print("done", args.out)


if __name__ == "__main__":
    main()
