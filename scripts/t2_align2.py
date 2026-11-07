#!/usr/bin/env python3
"""T2 · 对账 v2：部首×画数窗口（书眉画数）→ 候选集 → 信任分层 + 100 框复核图

- 窗口 = 数据集中 (rad=书眉部首, stroke∈书眉画数集) 的条目（无画数信息→该部全部）
- 匹配：OCR 字 ∈ 候选字集 → matched；否则 suspect（真值=候选之一，OCR 误读）
- 单调性：matched 的序列位置在阅读序下应非降（软信号）
- 复核图：suspect 全收 + matched 随机补足 100；每格 = 裁剪 + v6/v5 读数 + 候选字
"""
import json, os, collections, random
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T2 = os.path.join(ROOT, "work", "t2")
T1 = os.path.join(ROOT, "work", "t1")
T00 = os.path.join(ROOT, "work", "t00")

RAD214 = "一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠"
ALIAS = {'户': '戶', '青': '靑'}
# 书眉读得的部首+画数（AI 人读，个别 None=未辨）
# 书眉画数 = 康熙惯例「部外笔画」；数据集笔画 = 总笔画；桥：dataset = 画数 + 部首自身笔画
MARGIN = {
 '01_0006': ('一', [1]), '01_0027': ('乙', [1, 2]), '01_0110': ('人', [8]),
 '02_0029': ('口', [4, 5]), '02_0155': ('土', [10]), '03_0015': ('八', [2]),
 '03_0027': ('戶', [7]), '04_0017': ('心', [5]), '04_0030': ('心', [6]),
 '05_0017': ('日', [5]), '05_0030': ('日', [6]), '06_0018': ('水', [4]),
 '06_0032': ('水', [5]), '07_0021': ('玉', [6]), '08_0020': ('竹', [5, 6]),
 '09_0017': ('艸', [5]), '10_0023': ('角', [5]), '11_0020': ('金', [5]),
 '12_0017': ('馬', [6]), '13_0163': (None, None),
}
RAD_STROKES = {'一':1,'乙':1,'人':2,'口':3,'土':3,'八':2,'戶':4,'心':4,'日':4,
               '水':4,'玉':5,'竹':6,'艸':6,'角':7,'金':8,'馬':10}


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def main():
    tp = json.load(open(os.path.join(T2, 't2_pages.json')))
    seq = [json.loads(l) for l in open(os.path.join(T2, 'entry_sequence.jsonl'), encoding='utf-8')]
    v6 = {(r['page'], r['i']): (r['text'], r['conf']) for r in
          map(json.loads, open(os.path.join(T2, 'ocr_v6.jsonl'), encoding='utf-8'))}
    v5 = {(r['page'], r['i']): (r['text'], r['conf']) for r in
          map(json.loads, open(os.path.join(T2, 'ocr_v5.jsonl'), encoding='utf-8'))}

    # 候选集：per page
    cand = {}
    for page in tp['pages']:
        rad, strokes = MARGIN.get(page, (None, None))
        if rad is None:
            cand[page] = None
            continue
        ri = RAD214.index(rad)
        rs = RAD_STROKES.get(rad, 0)
        tgt = {x + rs for x in strokes} if strokes else None
        rows = [e for e in seq if e['rad_i'] == ri and
                (tgt is None or e['stroke'] in tgt)]
        cand[page] = rows
        print(page, rad, strokes, '候选', len(rows),
              '样例', ''.join(e['char'] for e in rows[:12]))

    results = []
    for page in tp['pages']:
        d = json.load(open(os.path.join(T1, 'orig_boxes', page + '.json')))
        boxes = d['boxes']
        crows = cand.get(page)
        cchars = collections.Counter(e['char'] for e in crows) if crows else None
        cands = sorted(cchars) if cchars else []
        order = sorted(range(len(boxes)),
                       key=lambda i: (-((boxes[i][0] + boxes[i][2]) / 2), boxes[i][1]))
        prev_pos = -1
        for i in order:
            b = boxes[i]
            t6, c6 = v6.get((page, i), ('', 0))
            t5, c5 = v5.get((page, i), ('', 0))
            ch6 = t6[0] if t6 and is_cjk(t6[0]) else None
            ch5 = t5[0] if t5 and is_cjk(t5[0]) else None
            dual = ch6 and ch6 == ch5
            label = ch6 or ch5
            in_cand = bool(label and cchars and cchars.get(label))
            pos = None
            if crows and in_cand:
                poss = [e['pos'] for e in crows if e['char'] == label]
                mono = [p for p in poss if p >= prev_pos]
                if mono:
                    pos = min(mono)
                    prev_pos = pos
            if crows is None:
                trust = 'no_window'
            elif in_cand and dual:
                trust = 'high'
            elif in_cand:
                trust = 'mid'
            elif dual:
                trust = 'suspect_pair'   # 双引擎一致但不在候选集 → OCR 误读，真值在候选中
            else:
                trust = 'suspect'
            results.append({'page': page, 'i': i, 'box': b, 'v6': t6, 'v5': t5,
                            'label': label, 'in_cand': in_cand, 'trust': trust,
                            'pos': pos, 'candidates': cands if cands else [],
                            'margin': MARGIN.get(page)})
    json.dump(results, open(os.path.join(T2, 'alignment.json'), 'w'),
              ensure_ascii=False, indent=1)
    stats = collections.Counter(r['trust'] for r in results)
    print(dict(stats), 'total', len(results))

    # 100 框复核图
    random.seed(97)
    suspects = [r for r in results if r['trust'].startswith('suspect')]
    others = [r for r in results if not r['trust'].startswith('suspect')]
    n_susp = min(len(suspects), 45)
    pick = random.sample(suspects, n_susp) + random.sample(others, min(100 - n_susp, len(others)))
    json.dump([{'page': r['page'], 'i': r['i']} for r in pick],
              open(os.path.join(T2, 'review100_ids.json'), 'w'), ensure_ascii=False)
    random.shuffle(pick)
    CELL_W, CELL_H, COLS = 240, 310, 8
    rows_n = (len(pick) + COLS - 1) // COLS
    sheet = Image.new('RGB', (COLS * CELL_W, rows_n * CELL_H), 'white')
    d = ImageDraw.Draw(sheet)
    F = ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc', 15)
    FS = ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc', 12)
    for k, r in enumerate(pick):
        gx = cv2.imread(os.path.join(T00, 'pages', r['page'] + '.png'),
                        cv2.IMREAD_GRAYSCALE)
        x0, y0, x1, y1 = r['box']
        pdd = 12
        vis = cv2.cvtColor(gx[max(0, y0 - pdd):y1 + pdd, max(0, x0 - pdd):x1 + pdd],
                           cv2.COLOR_GRAY2RGB)
        cv2.rectangle(vis, (x0 - max(0, x0 - pdd), y0 - max(0, y0 - pdd)),
                      (x1 - max(0, x0 - pdd), y1 - max(0, y0 - pdd)), (0, 180, 0), 2)
        im = Image.fromarray(vis)
        im.thumbnail((CELL_W - 8, CELL_H - 64))
        x = (k % COLS) * CELL_W
        y = (k // COLS) * CELL_H
        sheet.paste(im, (x + 4, y + 4))
        d.text((x + 4, y + CELL_H - 58), f"#{k} {r['page']}", fill='blue', font=FS)
        d.text((x + 4, y + CELL_H - 44), f"v6:{r['v6'][:8]}  v5:{r['v5'][:8]}", fill='black', font=F)
        d.text((x + 4, y + CELL_H - 28), f"trust:{r['trust']}", fill='purple', font=FS)
        cc = ''.join(r['candidates'][:10])
        d.text((x + 4, y + CELL_H - 14), f"候选:{cc}", fill='red', font=FS)
    sheet.save(os.path.join(T2, 'review100.png'))
    print('review100.png:', len(pick), 'boxes; suspects', n_susp)


if __name__ == '__main__':
    import PIL.Image as Image
    from PIL import ImageDraw, ImageFont
    import random
    main()
