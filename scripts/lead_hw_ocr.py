#!/usr/bin/env python3
"""Lead · 字头大字 PP-OCR（用于映射漂移校正）。

对每个正文页，取 v3-big 规则判定的字头候选框，300dpi 裁剪 → PP-OCRv5 rec 识别 → 文本+分数。
输出 work/lead/hw_ocr.jsonl: {page, half, idx, box, text, score}
"""
import argparse, json, os, sys, collections
import numpy as np, cv2
cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _job(args):
    vol, pages = args
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    from paddleocr import TextRecognition
    rec = TextRecognition(model_name="PP-OCRv5_server_rec")
    from t1_count_v3 import is_head_v3
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    out = []
    for pg in pages:
        page = f"{vol}_{pg:04d}"
        try:
            fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300", page + ".json"),
                                encoding="utf-8"))
            pix = doc[pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            crops, metas = [], []
            for half in ("R", "L"):
                for k, c in enumerate(fj["halves"][half]["cands"]):
                    if not is_head_v3(c, half):
                        continue
                    x0, y0, x1, y1 = [int(v * 2) for v in c["box"]]
                    cr = img[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6]
                    if cr.size == 0 or cr.shape[0] < 20 or cr.shape[1] < 15:
                        continue
                    cr = cv2.resize(cr, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
                    crops.append(np.stack([cr] * 3, -1))
                    metas.append({"page": page, "half": half, "idx": k, "box": c["box"]})
            if crops:
                res = rec.predict(crops)
                for m, o in zip(metas, res):
                    try:
                        r = o.json.get("res", {}) if hasattr(o, "json") else {}
                    except Exception:
                        r = {}
                    m["text"] = r.get("rec_text") or ""
                    m["score"] = round(float(r.get("rec_score") or 0), 3)
                    out.append(m)
        except Exception as e:
            out.append({"page": page, "err": str(e)[:80]})
    doc.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hw_ocr.jsonl"))
    ap.add_argument("--vols", default="01,02,03,04,05,06,07,08,09,10,11,12")
    args = ap.parse_args()
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in args.vols.split(","):
            roles[r["vol"]].append(r["page"])
    jobs = []
    for vol in sorted(roles):
        ps = sorted(roles[vol])
        k = max(1, len(ps) // args.workers + 1)
        for i in range(0, len(ps), k):
            jobs.append((vol, ps[i:i + k]))
    from multiprocessing import Pool
    allres = []
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(_job, jobs):
            allres.extend(res)
    allres.sort(key=lambda x: (x.get("page", ""), x.get("half", ""), x.get("idx", 0)))
    with open(args.out, "w", encoding="utf-8") as f:
        for x in allres:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("rows", len(allres), "->", args.out)


if __name__ == "__main__":
    main()
