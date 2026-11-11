#!/usr/bin/env python3
"""T2 · 标签对账：书眉部首窗口 + 阅读序单调性 + 双引擎一致性 → 信任分层

阅读序：竖排右→左列，列内上→下。
窗口：书眉部首 ∪ 下一部首（跨部页容错）。
信任：
  high   v6==v5 且字在窗口内且单调位置成立
  mid    双引擎一致但位置不单调，或单引擎可解释
  suspect 两引擎不一致且都无法纳入窗口单调序
"""
import json, os, re, collections
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T2 = os.path.join(ROOT, "work", "t2")
T1 = os.path.join(ROOT, "work", "t1")

RAD214 = "一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠"
ALIAS = {'户': '戶', '青': '靑'}


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def main():
    tp = json.load(open(os.path.join(T2, 't2_pages.json')))
    found = json.load(open(os.path.join(T2, 'foundation.json')))
    anchors = {int(k): v for k, v in found['anchors'].items()}
    seq = [json.loads(l) for l in open(os.path.join(T2, 'entry_sequence.jsonl'), encoding='utf-8')]
    v6 = {(r['page'], r['i']): (r['text'], r['conf']) for r in
          map(json.loads, open(os.path.join(T2, 'ocr_v6.jsonl'), encoding='utf-8'))}
    v5 = {(r['page'], r['i']): (r['text'], r['conf']) for r in
          map(json.loads, open(os.path.join(T2, 'ocr_v5.jsonl'), encoding='utf-8'))}

    # 部名 → 部首序号
    rad_i = {c: i for i, c in enumerate(RAD214)}
    rad_i.update({k: rad_i[v] for k, v in ALIAS.items()})

    out = []
    stats = collections.Counter()
    for page in tp['pages']:
        vol, rad = tp['margin_labels'].get(page, (None, None))
        d = json.load(open(os.path.join(T1, 'orig_boxes', page + '.json')))
        boxes = d['boxes']
        # 阅读序：列聚类（x 中心），列右→左，列内 y↑
        cands = [(b, (b[0] + b[2]) / 2, b[1]) for b in boxes]
        cands.sort(key=lambda t: -t[1])
        cols = []
        for b, cx, cy in cands:
            if cols and abs(cx - cols[-1]['cx']) < 55:
                cols[-1]['items'].append((b, cy))
                cols[-1]['cx'] = (cols[-1]['cx'] * cols[-1]['n'] + cx) / (cols[-1]['n'] + 1)
                cols[-1]['n'] += 1
            else:
                cols.append({'cx': cx, 'n': 1, 'items': [(b, cy)]})
        order = []
        for c in cols:
            for b, cy in sorted(c['items'], key=lambda t: t[1]):
                order.append(b)
        # 窗口（书眉「X部」→ 部首序号；補遺页用其集所辖部的范围）
        win = None
        radkey = rad[:-1] if rad and rad.endswith('部') else rad
        if radkey in rad_i:
            ri = rad_i[radkey]
            lo = anchors.get(ri, None)
            hi = anchors.get(ri + 1, len(seq))
            if lo is not None:
                win = (lo, hi)
        elif vol and vol.startswith('戌'):
            ris = sorted({e['rad_i'] for e in seq if (e.get('vol') or '').startswith('戌')}
                         if False else
                         [seq[i]['rad_i'] for i in range(len(seq))
                          if seq[i]['path'].startswith('【戌集')])
            if ris:
                win = (anchors.get(min(ris), 0), anchors.get(max(ris) + 1, len(seq)))
        # 逐框标签
        prev_pos = -1
        for b in order:
            key = (page, boxes.index(b))
            t6, c6 = v6.get(key, ('', 0))
            t5, c5 = v5.get(key, ('', 0))
            ch6 = t6[0] if t6 and is_cjk(t6[0]) else None
            ch5 = t5[0] if t5 and is_cjk(t5[0]) else None
            def find(ch):
                if not ch:
                    return None
                hits = [e['pos'] for e in seq[win[0]:win[1]] if e['char'] == ch] if win else []
                return hits
            h6 = find(ch6)
            h5 = find(ch5)
            def mono_ok(hits):
                return any(h >= prev_pos for h in hits) if hits else False
            if ch6 and ch6 == ch5 and h6 and mono_ok(h6):
                pos = min([h for h in h6 if h >= prev_pos])
                trust = 'high'
                label = ch6
            elif ch6 and ch6 == ch5 and h6:
                pos = min(h6)
                trust = 'mid_mono'
                label = ch6
            elif ch6 and h6 and mono_ok(h6):
                pos = min([h for h in h6 if h >= prev_pos])
                trust = 'mid_single'
                label = ch6
            elif ch5 and h5 and mono_ok(h5):
                pos = min([h for h in h5 if h >= prev_pos])
                trust = 'mid_single5'
                label = ch5
            elif ch6 and ch6 == ch5:
                trust = 'suspect_pair'
                pos = None
                label = ch6
            else:
                trust = 'suspect'
                pos = None
                label = ch6 or ch5 or ''
            if pos is not None:
                prev_pos = pos
            stats[trust] += 1
            out.append({'page': page, 'box': b, 'v6': t6, 'v5': t5,
                        'label': label, 'trust': trust,
                        'match_pos': pos, 'window': win,
                        'margin_rad': rad})
    json.dump(out, open(os.path.join(T2, 'alignment.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(dict(stats))
    print('total:', len(out))
    # 每页概览
    per = collections.defaultdict(collections.Counter)
    for o in out:
        per[o['page']][o['trust']] += 1
    for p in sorted(per):
        print(' ', p, tp['margin_labels'].get(p, ('?', '?'))[1], dict(per[p]))


if __name__ == '__main__':
    main()
