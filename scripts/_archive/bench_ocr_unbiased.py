#!/usr/bin/env python3
"""无偏基准：demo 目检 28 + owner 核实 11 字号（29 个唯一字），比较各 OCR 模型 top-1。"""
import json, os, sys
import numpy as np
import cv2
import fitz
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", os.path.join(ROOT, "work/paddlex_cache"))

MODELS = ["PP-OCRv6_medium_rec", "PP-OCRv6_small_rec", "PP-OCRv6_tiny_rec",
          "PP-OCRv5_server_rec", "PP-OCRv5_mobile_rec",
          "PP-OCRv4_server_rec", "PP-OCRv4_server_rec_doc",
          "ch_SVTRv2_rec", "ch_RepSVTR_rec", "chinese_cht_PP-OCRv3_mobile_rec"]


def main():
    items = json.load(open(os.path.join(ROOT, "work/lead/bench_unbiased.json")))
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    crops = []
    docs = {}
    for it in items:
        vol = it["page"][:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(it["page"][3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in it["box"]]
        pad = 8
        crop = img[max(0, b[1] - pad):b[3] + pad, max(0, b[0] - pad):b[2] + pad]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        crops.append((it["char"], crop, it.get("src")))
    for d in docs.values():
        d.close()
    from paddleocr import TextRecognition
    results = {}
    for model in MODELS:
        try:
            rec = TextRecognition(model_name=model)
        except Exception as e:
            print(model, "load fail", repr(e)[:120])
            continue
        ok = 0; preds = {}
        for ch, crop, src in crops:
            cv2.imwrite("/tmp/_b.png", crop)
            try:
                o = rec.predict("/tmp/_b.png")
                pred = (o[0].json.get("res", {}) or {}).get("rec_text", "") or ""
            except Exception:
                pred = ""
            preds[ch] = pred
            if pred == ch:
                ok += 1
        results[model] = {"n": len(crops), "top1": ok,
                          "acc": round(ok / max(1, len(crops)), 3), "preds": preds}
        print(model, "acc", results[model]["acc"], ok, "/", len(crops), flush=True)
    json.dump(results, open(os.path.join(ROOT, "work/lead/bench_unbiased.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
