#!/usr/bin/env python3
"""T0.0 · 字头 OCR（PP-OCRv5，单字 rec）+ 书眉条读字（部首/页码）

- 读 work/t00/headwords.jsonl 的 crop 路径，逐个识别（单字符裁剪）；
- 书眉条 work/t00/margins/*_L.png / _R.png：连通域切出单字，逐字识别，
  拼成「康熙字典/集名/部首/页码」串（供对账，不作为标签真源）；
- 并发：单进程顺序（crops 约 3–4k 个，CPU rec 每 30–60ms，几分钟内完成）。

输出 work/t00/ocr.jsonl / margins_ocr.jsonl
"""
import json, os, sys

import cv2
import numpy as np

cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def main():
    from paddleocr import PaddleOCR
    os.chdir(ROOT)  # 模型缓存目录落在仓库内（.paddlex 已 gitignore）
    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )  # 默认 PP-OCRv6_medium（原生支持繁体）

    def pick_central(res, img_w, img_h):
        """多候选时取框中心最靠近裁剪中心的 CJK 结果（裁剪 padding 会带进邻字）；
        返回 (text, 该候选的原始置信度)"""
        j = res[0].json.get("res", res[0]) if hasattr(res[0], "json") else res[0]
        texts = j.get("rec_texts", []) if isinstance(j, dict) else getattr(j, "rec_texts", [])
        scores = j.get("rec_scores", []) if isinstance(j, dict) else getattr(j, "rec_scores", [])
        boxes = j.get("rec_boxes", []) if isinstance(j, dict) else getattr(j, "rec_boxes", [])
        best, bc, bconf = "", -1e9, 0.0
        cx0, cy0 = img_w / 2, img_h / 2
        for i in range(len(texts)):
            t = str(texts[i])
            c = float(scores[i]) if i < len(scores) else 0.0
            d = 1e9
            if i < len(boxes) and len(boxes[i]) == 4:
                bx = (boxes[i][0] + boxes[i][2]) / 2
                by = (boxes[i][1] + boxes[i][3]) / 2
                d = ((bx - cx0) ** 2 + (by - cy0) ** 2) ** 0.5
            sc = c - d / max(img_w, img_h) + (0.1 if len(t) == 1 else 0.0)
            if sc > bc:
                bc, best, bconf = sc, t, c
        return best, bconf

    # 1) 字头裁剪
    margins_only = "--margins-only" in sys.argv
    n_in = n_ok = 0
    if not margins_only:
        with open(os.path.join(T00, "headwords.jsonl"), encoding="utf-8") as fh, \
             open(os.path.join(T00, "ocr.jsonl"), "w", encoding="utf-8") as fo:
            for line in fh:
                r = json.loads(line)
                n_in += 1
                path = os.path.join(T00, r["crop"])
                text, conf = "", 0.0
                try:
                    res = ocr.predict(path)
                    if res:
                        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                        text, conf = pick_central(res, img.shape[1], img.shape[0])
                except Exception as e:  # noqa: BLE001
                    text, conf = f"<err:{type(e).__name__}>", 0.0
                if text and not text.startswith("<err"):
                    n_ok += 1
                fo.write(json.dumps({"crop": r["crop"], "pdf": r["pdf"], "page": r["page"],
                                     "side": r["side"], "x0": r["x0"], "y0": r["y0"],
                                     "text": text, "conf": round(conf, 3)},
                                    ensure_ascii=False) + "\n")
                if n_in % 200 == 0:
                    print(f"headword crops {n_in}, ok {n_ok}", flush=True)
        print(f"headwords OCR done: {n_in} crops, {n_ok} recognized", flush=True)

    # 2) 书眉条：连通域切单字 → 逐字识别
    def strip_chars(img):
        ink = (img <= 150).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
        boxes = []
        H = img.shape[0]
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < 40 or h < 14 or w < 8 or h > 0.5 * H:
                continue
            boxes.append((y, x, w, h))
        boxes.sort()
        return boxes

    def rec_char(img, tmpdir):
        # PaddleOCR 对 2D 灰度 ndarray 静默失败——落盘为临时 PNG 走文件路径
        p = os.path.join(tmpdir, "c.png")
        cv2.imwrite(p, img)
        try:
            res = ocr.predict(p)
            if res:
                j = res[0].json.get("res", res[0]) if hasattr(res[0], "json") else res[0]
                texts = j.get("rec_texts", []) if isinstance(j, dict) else getattr(j, "rec_texts", [])
                scores = j.get("rec_scores", []) if isinstance(j, dict) else getattr(j, "rec_scores", [])
                if texts:
                    return str(texts[0]), float(scores[0]) if scores else 0.0
        except Exception:  # noqa: BLE001
            pass
        return "", 0.0

    margin_dir = os.path.join(T00, "margins")
    tmpdir = os.path.join(T00, "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    n_m = 0
    with open(os.path.join(T00, "margins_ocr.jsonl"), "w", encoding="utf-8") as fm:
        for f in sorted(os.listdir(margin_dir)):
            if not f.endswith(".png"):
                continue
            img = cv2.imread(os.path.join(margin_dir, f), cv2.IMREAD_GRAYSCALE)
            chars = []
            for (y, x, w, h) in strip_chars(img):
                if x + w > 0.75 * img.shape[1]:   # 排除内文渗入（条右侧）
                    continue
                pad = 6
                crop = img[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
                t, c = rec_char(crop, tmpdir)
                chars.append({"y": int(y), "t": t, "conf": round(c, 2)})
            stem = f[:-4]
            pdf, page, side = stem.split("_")[0], int(stem.split("_")[1]), stem.split("_")[2]
            fm.write(json.dumps({"pdf": pdf, "page": page, "side": side,
                                 "text": "".join(c["t"] for c in chars),
                                 "chars": chars}, ensure_ascii=False) + "\n")
            n_m += 1
            if n_m % 100 == 0:
                print(f"margins {n_m}", flush=True)
    print(f"margins OCR done: {n_m} strips", flush=True)


if __name__ == "__main__":
    sys.exit(main())
