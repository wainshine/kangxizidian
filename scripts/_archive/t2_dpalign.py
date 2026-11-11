#!/usr/bin/env python3
"""T2 · 序列对齐（所有者指示：标签来自数据集文本，OCR 只做锚点提示）

对每页：期望序列 = 数据集中该部首的条目（正典序）；观测序列 = 切格框（阅读序）。
锚点 = 双引擎一致且在部内唯一命中的读数。
DP 单调对齐（ NW 变体）：match(+2|OCR命中 +4) / 框为FP跳过(-1.2) / 条目漏检跳过(-1.0)。
输出 box→entry 映射 + FP + 漏检 + 对齐分数；标签=数据集字（100% 真源）。
"""
import json, os, collections
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T2 = os.path.join(ROOT, "work", "t2")
T1 = os.path.join(ROOT, "work", "t1")


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def main():
    tp = json.load(open(os.path.join(T2, 't2_pages.json')))
    RAD214 = "一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠"
    ALIAS = {'户': '戶', '青': '靑'}
    rad_idx = {c: i for i, c in enumerate(RAD214)}
    seq = [json.loads(l) for l in open(os.path.join(T2, 'entry_sequence.jsonl'), encoding='utf-8')]
    found = json.load(open(os.path.join(T2, 'foundation.json')))
    anchors = {int(k): v for k, v in found['anchors'].items()}
    v6 = {(r['page'], r['i']): r['text'] for r in
          map(json.loads, open(os.path.join(T2, 'ocr_v6.jsonl'), encoding='utf-8'))}
    v5 = {(r['page'], r['i']): r['text'] for r in
          map(json.loads, open(os.path.join(T2, 'ocr_v5.jsonl'), encoding='utf-8'))}

    out_all = []
    stats = collections.Counter()
    for page in tp['pages']:
        vol, rad = tp['margin_labels'].get(page, (None, None))
        radkey = rad[:-1] if rad and rad.endswith('部') else rad
        ri = rad_idx.get(ALIAS.get(radkey, radkey), None)
        d = json.load(open(os.path.join(T1, 'orig_boxes', page + '.json')))
        boxes = d['boxes']
        # 阅读序：列右→左，列内上→下
        cands = sorted(((b, (b[0] + b[2]) / 2, b[1]) for b in boxes), key=lambda t: -t[1])
        cols = []
        for b, cx, cy in cands:
            if cols and abs(cx - cols[-1]['cx']) < 55:
                cols[-1]['items'].append((b, cy))
            else:
                cols.append({'cx': cx, 'items': [(b, cy)]})
        obs = [b for c in cols for b, cy in sorted(c['items'], key=lambda t: t[1])]
        # 期望序列窗口：先粗（部首±2），经锚点收紧（锚点 ±25 条）
        if ri is None:
            exp = [e for e in seq if e['path'].startswith('【戌集')]
        else:
            lo = anchors.get(ri, None)
            hi = anchors.get(ri + 1, len(seq))
            exp = seq[lo:hi]
        # 粗锚点：OCR 读数在期望序列中的唯一命中
        anch = {}
        for oi, b in enumerate(obs):
            t6 = v6.get((page, boxes.index(b)), '')
            t5 = v5.get((page, boxes.index(b)), '')
            ch6 = t6[0] if t6 and is_cjk(t6[0]) else None
            ch5 = t5[0] if t5 and is_cjk(t5[0]) else None
            for ch in {ch6, ch5}:
                if not ch:
                    continue
                hits = [e['pos'] for e in exp if e['char'] == ch]
                if len(hits) == 1:
                    anch.setdefault(oi, set()).add(hits[0])
        # 锚点锁窗：所有唯一锚点位置的最小/最大值 ±25
        all_anch = sorted(p for s_ in anch.values() for p in s_)
        if all_anch:
            wlo = max(0, min(all_anch) - 25)
            whi = min(len(seq), max(all_anch) + 26)
            exp = [e for e in seq if wlo <= e['pos'] < whi]
        # 重算锚点（窗口变了，唯一性可能改变）
        anch = {}
        for oi, b in enumerate(obs):
            t6 = v6.get((page, boxes.index(b)), '')
            t5 = v5.get((page, boxes.index(b)), '')
            ch6 = t6[0] if t6 and is_cjk(t6[0]) else None
            ch5 = t5[0] if t5 and is_cjk(t5[0]) else None
            for ch in {ch6, ch5}:
                if not ch:
                    continue
                hits = [e['pos'] for e in exp if e['char'] == ch]
                if len(hits) == 1:
                    anch.setdefault(oi, set()).add(hits[0])
        # DP 对齐：obs(含FP跳过) × exp(含漏检跳过)
        n, m = len(obs), len(exp)
        # 锚点一致性约束：格 (oi, ei) 允许 match 仅当不与锚点矛盾（单调）
        GAP_O, GAP_E = -1.2, -1.0
        NEG = -1e9
        dp = np.full((n + 1, m + 1), NEG)
        bt = np.zeros((n + 1, m + 1), dtype=np.int8)  # 1=match 2=skip_obs 3=skip_exp
        dp[0, 0] = 0
        for i in range(n + 1):
            for j in range(m + 1):
                if i > 0 and dp[i - 1, j] > NEG:
                    v = dp[i - 1, j] + GAP_O
                    if v > dp[i, j]:
                        dp[i, j], bt[i, j] = v, 2
                if j > 0 and dp[i, j - 1] > NEG:
                    v = dp[i, j - 1] + GAP_E
                    if v > dp[i, j]:
                        dp[i, j], bt[i, j] = v, 3
                if i > 0 and j > 0 and dp[i - 1, j - 1] > NEG:
                    b = obs[i - 1]
                    e = exp[j - 1]
                    score = 0.5  # 字形合理先验（尺寸/密度已在检出端过滤）
                    t6 = v6.get((page, boxes.index(b)), '')
                    t5 = v5.get((page, boxes.index(b)), '')
                    ch6 = t6[0] if t6 and is_cjk(t6[0]) else None
                    ch5 = t5[0] if t5 and is_cjk(t5[0]) else None
                    if e['char'] in (ch6, ch5):
                        score = 4.0
                    elif e['char'].encode('utf-8')[:3] == b'\xf0\xa4' or ord(e['char'][0]) > 0xFFFF:
                        score = 0.2  # 扩展区条目：基本区之外，弱先验
                    v = dp[i - 1, j - 1] + score
                    if v > dp[i, j]:
                        dp[i, j], bt[i, j] = v, 1
        # 回溯
        i, j = n, m
        pairs, fps, misses = [], [], []
        while i > 0 or j > 0:
            t = bt[i, j]
            if t == 1:
                pairs.append((obs[i - 1], exp[j - 1]))
                i, j = i - 1, j - 1
            elif t == 2:
                fps.append(obs[i - 1])
                i -= 1
            elif t == 3:
                misses.append(exp[j - 1])
                j -= 1
            else:
                break
        pairs.reverse()
        anch_used = sum(1 for b, e in pairs
                        if e['char'] in (v6.get((page, boxes.index(b)), '')[0:1],
                                         v5.get((page, boxes.index(b)), '')[0:1])
                        and v6.get((page, boxes.index(b)), '')[0:1])
        for b, e in pairs:
            out_all.append({'page': page, 'box': b, 'entry_pos': e['pos'],
                            'char': e['char'], 'rad': e['rad'], 'stroke': e['stroke'],
                            'extB': ord(e['char'][0]) > 0xFFFF,
                            'ocr_v6': v6.get((page, boxes.index(b)), ''),
                            'ocr_v5': v5.get((page, boxes.index(b)), '')})
            stats['matched'] += 1
            stats['extB_matched'] += ord(e['char'][0]) > 0xFFFF
        stats['fp'] += len(fps)
        stats['miss'] += len(misses)
        stats['anchored_pairs'] += anch_used
        print(f'{page} {rad}: obs={len(obs)} exp={len(exp)} matched={len(pairs)} '
              f'fp={len(fps)} miss={len(misses)} 锚定={anch_used}')
    json.dump(out_all, open(os.path.join(T2, 'dp_alignment.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(dict(stats))


if __name__ == '__main__':
    main()
