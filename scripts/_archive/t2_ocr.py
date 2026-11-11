#!/usr/bin/env python3
"""T2 · 双引擎 OCR（v6 主 / v5 副）——切格框逐一识别"""
import json, os, sys
import cv2
cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")
T1 = os.path.join(ROOT, "work", "t1")
T2 = os.path.join(ROOT, "work", "t2")

def main():
    from paddleocr import PaddleOCR
    os.chdir(ROOT)
    pages = json.load(open(os.path.join(T2, 't2_pages.json')))['pages']
    jobs = []
    for p in pages:
        d = json.load(open(os.path.join(T1, 'orig_boxes', p + '.json')))
        for i, b in enumerate(d['boxes']):
            jobs.append({'page': p, 'i': i, 'box': b,
                         'crop': (p, b)})
    print('crops:', len(jobs), flush=True)
    e6 = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_textline_orientation=False)
    e5 = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_textline_orientation=False, lang="ch",
                   text_recognition_model_name="PP-OCRv5_server_rec")
    def run(ocr, path):
        try:
            res = ocr.predict(path)
            if res:
                j = res[0].json.get('res', res[0]) if hasattr(res[0], 'json') else res[0]
                t = j.get('rec_texts', [])
                s = j.get('rec_scores', [])
                bx = j.get('rec_boxes', [])
                return list(zip([str(x) for x in t],
                                [float(x) for x in s],
                                [list(map(int, b)) for b in bx] if len(bx) else []))
        except Exception as e:
            return [('<err>', 0.0, [])]
        return []
    import glob
    out6 = open(os.path.join(T2, 'ocr_v6.jsonl'), 'w', encoding='utf-8')
    out5 = open(os.path.join(T2, 'ocr_v5.jsonl'), 'w', encoding='utf-8')
    gray_cache = {}
    def img_of(page):
        if page not in gray_cache:
            gray_cache[page] = cv2.imread(os.path.join(T00, 'pages', page + '.png'),
                                          cv2.IMREAD_GRAYSCALE)
        return gray_cache[page]
    import tempfile
    tmp = os.path.join(T2, 'tmp'); os.makedirs(tmp, exist_ok=True)
    tp = os.path.join(tmp, 'crop.png')
    for n, job in enumerate(jobs):
        page, box = job['crop']
        g = img_of(page)
        x0, y0, x1, y1 = box
        crop = g[max(0,y0-6):y1+6, max(0,x0-6):x1+6]
        cv2.imwrite(tp, crop)
        img = cv2.imread(tp, cv2.IMREAD_GRAYSCALE)
        W, H = img.shape[1], img.shape[0]
        def central(rs):
            best, bc = "", -1e9
            for t, c, bx in rs:
                d = 1e9
                if len(bx) == 4:
                    d = ((bx[0]+bx[2])/2 - W/2)**2 + ((bx[1]+bx[3])/2 - H/2)**2
                sc = c - d/max(W,H) + (0.1 if len(t) == 1 else 0.0)
                if sc > bc:
                    bc, best = sc, t
            return best, bc
        t6, c6 = central(run(e6, tp))
        t5, c5 = central(run(e5, tp))
        out6.write(json.dumps({'page': page, 'i': job['i'], 'box': box,
                               'text': t6, 'conf': round(c6, 3)}, ensure_ascii=False) + '\n')
        out5.write(json.dumps({'page': page, 'i': job['i'], 'box': box,
                               'text': t5, 'conf': round(c5, 3)}, ensure_ascii=False) + '\n')
        if (n+1) % 100 == 0:
            print(f'{n+1}/{len(jobs)}', flush=True)
    out6.close(); out5.close()
    print('done', flush=True)

if __name__ == '__main__':
    main()
