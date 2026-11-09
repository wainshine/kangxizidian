#!/usr/bin/env python3
"""繁体 OCR 引擎基准：在「已确认字形」上比较各识别模型 top-1 准确率。"""
import json, os, random, sys
import numpy as np
import cv2
import fitz
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", os.path.join(ROOT, "work/paddlex_cache"))


def main():
    ap_models = sys.argv[1:] or ["PP-OCRv5_server_rec", "PP-OCRv6_medium_rec",
                                 "chinese_cht_PP-OCRv3_mobile_rec"]
    conf = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union6.json")))
    items = list(conf.items())
    random.seed(11)
    sample = random.sample(items, 300)
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    # 预处理 crops
    crops = []
    docs = {}
    for ch, rec in sample:
        vol = rec["page"][:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(rec["page"][3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in rec["box"]]
        pad = 8
        crop = img[max(0, b[1] - pad):b[3] + pad, max(0, b[0] - pad):b[2] + pad]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        crops.append((ch, crop))
    for d in docs.values():
        d.close()
    print("benchmark crops", len(crops))
    from paddleocr import TextRecognition
    results = {}
    for model in ap_models:
        try:
            rec = TextRecognition(model_name=model)
        except Exception as e:
            print(model, "load fail:", repr(e)[:160])
            continue
        ok = 0; n = 0; costs = 0.0
        import time
        for ch, crop in crops:
            cv2.imwrite("/tmp/_bench.png", crop)
            t0 = time.time()
            try:
                o = rec.predict("/tmp/_bench.png")
                r = o[0].json.get("res", {})
                pred = r.get("rec_text", "") or ""
            except Exception:
                pred = ""
            costs += time.time() - t0
            n += 1
            if pred == ch:
                ok += 1
        results[model] = {"n": n, "top1": ok, "acc": round(ok / max(1, n), 4),
                          "sec_per": round(costs / max(1, n), 4)}
        print(model, results[model], flush=True)
    json.dump(results, open(os.path.join(ROOT, "work/lead/bench_ocr.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
