#!/usr/bin/env python3
"""T2 · 300dpi 重 OCR（所有者指示：切格已对，OCR 切完的结果与位置对齐）
对 20 页全部 orig_boxes，从 PDF 直接以 300dpi 渲染框邻域（真扫描细节，非 150dpi 插值），
双引擎识别。输出 ocr300_v6.jsonl / ocr300_v5.jsonl，键 (page, src_idx) 与切格框一一对应。
"""
import json, os, sys
import cv2
cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")
import warnings; warnings.filterwarnings("ignore")
import fitz
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T1 = os.path.join(ROOT, "work", "t1")
T2 = os.path.join(ROOT, "work", "t2")


def main():
    from paddleocr import PaddleOCR
    pdf_map = json.load(open(os.path.join(T2, 'pdf_map.json')))
    pages = json.load(open(os.path.join(T2, 't2_pages.json')))['pages']
    docs = {}
    def doc_of(idx):
        if idx not in docs:
            docs[idx] = fitz.open(os.path.join(ROOT, '康熙字典', pdf_map[idx]))
        return docs[idx]
    e6 = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_textline_orientation=False)
    e5 = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                   lang="ch", text_recognition_model_name="PP-OCRv5_server_rec")

    def run(ocr, path):
        try:
            res = ocr.predict(path)
            if res:
                j = res[0].json.get('res', res[0]) if hasattr(res[0], 'json') else res[0]
                t = j.get('rec_texts', []); s = j.get('rec_scores', [])
                bx = j.get('rec_boxes', [])
                return list(zip([str(x) for x in t], [float(x) for x in s],
                                [list(map(int, b)) for b in bx] if len(bx) else []))
        except Exception:
            return [('<err>', 0.0, [])]
        return []

    def central(rs):
        best, bc = "", -1e9
        for t, c, bx in rs:
            d = 1e9
            if len(bx) == 4:
                d = ((bx[0]+bx[2])/2 - W/2)**2 + ((bx[1]+bx[3])/2 - H/2)**2
            sc = c - d/max(W, H) + (0.1 if len(t) == 1 else 0.0)
            if sc > bc:
                bc, best = sc, t
        return best, bc

    tmp = os.path.join(T2, 'tmp'); os.makedirs(tmp, exist_ok=True)
    tp = os.path.join(tmp, 'crop300.png')
    jobs = []
    for p in pages:
        d = json.load(open(os.path.join(T1, 'orig_boxes', p + '.json')))
        for i, b in enumerate(d['boxes']):
            jobs.append((p, i, b))
    out6 = open(os.path.join(T2, 'ocr300_v6.jsonl'), 'w', encoding='utf-8')
    out5 = open(os.path.join(T2, 'ocr300_v5.jsonl'), 'w', encoding='utf-8')
    print('jobs:', len(jobs), flush=True)
    for n, (p, i, box) in enumerate(jobs):
        idx = p[:2]; pg = int(p[3:])
        page = doc_of(idx)[pg - 1]
        Wp, Hp = page.rect.width, page.rect.height
        sx = 72.0 / 150.0  # pt per px@150dpi
        x0, y0, x1, y1 = box
        m = 4.0  # pt
        rect = fitz.Rect(max(0, x0*sx - m), max(0, y0*sx - m),
                         min(Wp, x1*sx + m), min(Hp, y1*sx + m))
        pix = page.get_pixmap(dpi=300, colorspace=fitz.csGRAY, clip=rect)
        if pix.width < 5 or pix.height < 5:
            img = np.full((160, 160), 255, dtype=np.uint8)
        else:
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
        H, W = img.shape
        cv2.imwrite(tp, img)
        t6, c6 = central(run(e6, tp))
        t5, c5 = central(run(e5, tp))
        out6.write(json.dumps({'page': p, 'i': i, 'box': box,
                               'text': t6, 'conf': round(c6, 3)}, ensure_ascii=False) + '\n')
        out5.write(json.dumps({'page': p, 'i': i, 'box': box,
                               'text': t5, 'conf': round(c5, 3)}, ensure_ascii=False) + '\n')
        if (n + 1) % 50 == 0:
            print(f'{n+1}/{len(jobs)}', flush=True)
    out6.close(); out5.close()
    print('done', flush=True)


import numpy as np
if __name__ == '__main__':
    main()
