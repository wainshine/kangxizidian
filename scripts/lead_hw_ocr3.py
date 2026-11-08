#!/usr/bin/env python3
"""Lead · 二次 OCR（增强预处理）：对确认率低的字头框重识别。

预处理：裁切加 12% padding → 灰度 → 中值去噪 → 对比度归一化 → ×3 放大 → 白边。
模型：PP-OCRv5_server_rec + PP-OCRv6_medium_rec。
输出 work/lead/hw_ocr_enh.jsonl
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _work(chunk):
    import fitz, cv2
    from paddleocr import TextRecognition
    mp_ = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    rec5 = TextRecognition(model_name="PP-OCRv5_server_rec")
    rec6 = TextRecognition(model_name="PP-OCRv6_medium_rec")
    out = []
    docs = {}
    for page, half, box in chunk:
        vol = page[:2]; pg = int(page[3:])
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp_[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        x0, y0, x1, y1 = [int(v) * 2 for v in box]
        w = x1 - x0; h = y1 - y0
        px = max(6, int(w * 0.12)); py = max(6, int(h * 0.12))
        crop = img[max(0, y0 - py):y1 + py, max(0, x0 - px):x1 + px]
        if crop.size == 0 or min(crop.shape) < 12:
            continue
        # 增强
        g = cv2.medianBlur(crop, 3)
        g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
        g = cv2.resize(g, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        g = cv2.copyMakeBorder(g, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
        tmp = "/tmp/ocrenh_%d.png" % os.getpid()
        cv2.imwrite(tmp, g)
        rec = {"page": page, "half": half, "box": list(box)}
        for tag, model in (("v5e", rec5), ("v6e", rec6)):
            try:
                o = model.predict(tmp)
                r = o[0].json.get("res", {})
                rec[tag] = r.get("rec_text", "")
                rec[tag + "_score"] = float(r.get("rec_score") or 0)
            except Exception as e:
                rec[tag] = ""
                rec[tag + "_score"] = 0.0
        out.append(rec)
    for d in docs.values():
        d.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--need", default=os.path.join(ROOT, "work/lead/ocr_need3.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hw_ocr_enh.jsonl"))
    ap.add_argument("--procs", type=int, default=8)
    args = ap.parse_args()
    import multiprocessing as mp
    need = [tuple(x) for x in json.load(open(args.need))]
    print("need", len(need), flush=True)
    chunks = [need[i::args.procs] for i in range(args.procs)]
    with open(args.out, "w", encoding="utf-8") as f, mp.Pool(args.procs) as pool:
        done = 0
        for i, rows in enumerate(pool.imap_unordered(_work, chunks)):
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            done += len(rows)
            print("chunk", i, "cum", done, flush=True)
    print("done", args.out)


if __name__ == "__main__":
    main()
