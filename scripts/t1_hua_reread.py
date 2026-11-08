"""t1_hua_reread.py — 用 Lead 的真迹数字模板重读画数字段（woodblock-to-woodblock）

输入：work/seq/headers_full_raw.jsonl（cells: y0/y1/text/score）
      work/lead/hua_tpl/templates_digits.json（24 簇人工标注：char/n/mean_img 40x40）
      work/lead/hua_tpl/mining.npz（X 样本，用于 NCC 比较，可加）
输出：work/lead/hua_reread.jsonl（page,hua:[v1,v2],fields,conf,conf_tpl）

方法：每页 300dpi 渲染版心条（header_read.render_strip）→ 用 raw 的 x0:x1、cells 的 y 范围裁格；
  以 OCR=「部」的 cell 为锚，其后含「畫」的 cell 即各画数字段终点；
  数字格 = 畫格向上的 1-2 格，按 Lead norm40 归一化 → 与 24 模板 NCC；
  值 = 单字数字 or 十/廿/卅 + 末位；阈值 0.72（低于则该字段退回 OCR 值）。
"""
import argparse, json, os, sys
import numpy as np
import cv2

os.environ.setdefault('OMP_NUM_THREADS', '1')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import header_read as HR

SIZE = 40
TPL = json.load(open(os.path.join(ROOT, 'work/lead/hua_tpl/templates_digits.json')))
MINING = np.load(os.path.join(ROOT, 'work/lead/hua_tpl/mining.npz'), allow_pickle=True)


def prep(img):
    b = (img > 0.45).astype(np.float32).ravel()
    b = b - b.mean()
    n = np.linalg.norm(b)
    return b / n if n > 1e-9 else b


TM = []
for k, v in TPL.items():
    im = np.array(v['mean_img'], dtype=np.float32).reshape(SIZE, SIZE)
    TM.append((prep(im), v['char'], int(k), int(v['n'])))
# 也用 mining X 样本（归一化后）增强模板
X = MINING['X'].astype(np.float32)
LB = MINING['labels'].astype(int)
Xb = (X > 0.45).astype(np.float32)
Xb = Xb - Xb.mean(axis=1, keepdims=True)
Xb = Xb / np.maximum(np.linalg.norm(Xb, axis=1, keepdims=True), 1e-9)
LAB2CHAR = {int(k): v['char'] for k, v in TPL.items()}


def norm40(m):
    m = (m > 0).astype(np.uint8)
    ys, xs = np.where(m > 0)
    if len(ys) < 25:
        return None
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h, w = m.shape
    if not (20 <= h <= 140 and 6 <= w <= 140):
        return None
    s = SIZE / max(h, w)
    mm = cv2.resize(m, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    c = np.zeros((SIZE, SIZE), np.float32)
    oy = (SIZE - mm.shape[0]) // 2
    ox = (SIZE - mm.shape[1]) // 2
    c[oy:oy + mm.shape[0], ox:ox + mm.shape[1]] = mm
    return c


def classify(gray, y0, y1, x0, x1):
    crop = gray[max(0, y0 - 2):min(gray.shape[0], y1 + 2), x0:x1]
    if crop.size == 0:
        return None, 0.0
    v = norm40((crop < 150).astype(np.uint8))
    if v is None:
        return None, 0.0
    q = prep(v)
    # 模板 NCC
    best_t = (-9, None)
    for tv, ch, ki, n in TM:
        s = float(q @ tv)
        if s > best_t[0]:
            best_t = (s, ch)
    # mining 样本 NCC（取最高）
    sims = Xb @ q
    imax = int(np.argmax(sims))
    best_x = (float(sims[imax]), LAB2CHAR.get(int(LB[imax])))
    if best_x[0] >= best_t[0]:
        return best_x[1], round(best_x[0], 3)
    return best_t[1], round(best_t[0], 3)


MAPV = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
TENS = {'十': 10, '廿': 20, '卅': 30}


def cn_value(chars):
    if not chars:
        return None
    if len(chars) == 1:
        return MAPV.get(chars[0]) or TENS.get(chars[0])
    a, b = chars[-2], chars[-1]
    if a in TENS and b in MAPV:
        return TENS[a] + MAPV[b]
    if b in TENS and a in MAPV:
        return MAPV[a] * 10
    if a in MAPV and b in MAPV:
        return MAPV[a] * 10 + MAPV[b]
    return None


def process_page(args):
    pdf, page, x0, x1, cells = args
    try:
        g = HR.render_strip(pdf, page, dpi=300, clipw_pt=40.0)
        img = g[:, x0:x1]
        bu_idx = None
        for c in cells:
            t = c.get('text') or ''
            if '部' in t and c.get('score', 0) > 0.4:
                bu_idx = c['i']
        if bu_idx is None:
            return {'page': f'{pdf}_{page:04d}', 'hua': None, 'why': 'no_bu'}
        chua = [c for c in cells if c['i'] > bu_idx and '畫' in (c.get('text') or '')]
        if not chua:
            return {'page': f'{pdf}_{page:04d}', 'hua': None, 'why': 'no_hua_cell'}
        fields = []
        for hc in chua:
            hi = hc['i']
            digits = []
            j = hi - 1
            prev_y0 = hc['y0']
            while j > bu_idx:
                cc = [x for x in cells if x['i'] == j]
                if not cc:
                    break
                cc = cc[0]
                if cc['y1'] > prev_y0 + 10:
                    break
                ch, sc = classify(img, cc['y0'], cc['y1'], 0, x1 - x0)
                if ch is None or sc < 0.72:
                    break
                digits.append((ch, sc))
                prev_y0 = cc['y0']
                j -= 1
                if len(digits) >= 2:
                    break
            digits = digits[::-1]
            val = cn_value([d[0] for d in digits])
            fields.append({'chars': [d[0] for d in digits],
                           'scores': [d[1] for d in digits],
                           'value': val, 'hua_cell_y': hc['y0']})
        vals = [f['value'] for f in fields if f['value'] is not None]
        scores = [s for f in fields for s in f['scores']]
        return {'page': f'{pdf}_{page:04d}', 'hua': vals,
                'fields': fields, 'conf': round(min(scores), 3) if scores else 0.0,
                'why': None}
    except Exception as e:
        return {'page': f'{pdf}_{page:04d}', 'hua': None, 'why': repr(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'work/lead/hua_reread.jsonl'))
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    raw = [json.loads(l) for l in open(os.path.join(ROOT, 'work/seq/headers_full_raw.jsonl'))]
    jobs = [(r['pdf'], r['page'], r['x0'], r['x1'], r['cells'])
            for r in raw if r.get('cells')]
    from concurrent.futures import ProcessPoolExecutor
    out = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(process_page, jobs, chunksize=8):
            out.append(r)
    with open(args.out, 'w') as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    n_ok = sum(1 for r in out if r['hua'])
    n_fail = sum(1 for r in out if not r['hua'])
    print('pages', len(out), 'hua_ok', n_ok, 'fail', n_fail)


if __name__ == '__main__':
    main()
