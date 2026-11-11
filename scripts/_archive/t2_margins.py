#!/usr/bin/env python3
"""T2 · 书眉解析：从书眉条 OCR 串中提取「集名 + 部名（+页码）」

书眉结构（外缘竖排）：康熙字典 / 子集上 / 一部 / 鱼尾 / 页码
OCR 串带噪声（内文渗入），解析策略：
- 集名：[子丑寅卯辰巳午未申酉戌亥]集[上中下]
- 部名：1-2 字 + 部，且属于 214 部名表（含异体：户→戶、青→靑）
- 取串中「最后一次出现的部名 match」（部名在标签列的下段）
- 页码：部名之后的中文数字串（可选，噪声大时跳过）

输出 work/t2/margin_labels.jsonl：{pdf, page, side, vol, radical, raw}
"""
import json, os, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")
T2 = os.path.join(ROOT, "work", "t2")

RAD214 = "一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠"
ALIAS = {'户': '戶', '青': '靑'}
RAD_NAMES = set(RAD214) | set(ALIAS)
VOLS = set(f'{a}集{b}' for a in '子丑寅卯辰巳午未申酉戌亥' for b in '上中下')


def parse_text(text):
    vol, rad = None, None
    # 集名
    for m in re.finditer(r'([子丑寅卯辰巳午未申酉戌亥]集[上中下])', text):
        vol = m.group(1)
    # 部名：名(1-2字)+部，取最后一次
    for m in re.finditer(r'([一-龥]{1,2})部', text):
        name = m.group(1)[-2:] if len(m.group(1)) >= 2 else m.group(1)
        # 单字部名取「部」前 1 字；两字部名取前 2 字
        cand2 = m.group(1)
        cand1 = m.group(1)[-1]
        if cand2 in RAD_NAMES or ALIAS.get(cand2, cand2) in RAD_NAMES:
            rad = ALIAS.get(cand2, cand2)
        elif cand1 in RAD_NAMES or ALIAS.get(cand1, cand1) in RAD_NAMES:
            rad = ALIAS.get(cand1, cand1)
    return vol, rad


def main():
    rows = [json.loads(l) for l in open(os.path.join(T00, 'margins_ocr.jsonl'), encoding='utf-8')]
    out, stats = [], collections.Counter()
    for r in rows:
        text = r.get('text', '')
        vol, rad = parse_text(text)
        ok = bool(rad)
        stats['total'] += 1
        stats['rad_ok' if ok else 'rad_missing'] += 1
        out.append({'pdf': r['pdf'], 'page': r['page'], 'side': r['side'],
                    'vol': vol, 'radical': rad, 'raw': text[:40]})
    with open(os.path.join(T2, 'margin_labels.jsonl'), 'w', encoding='utf-8') as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    print(stats)
    # 每页合并 L/R：取一致或非空者
    per_page = collections.defaultdict(list)
    for o in out:
        per_page[(o['pdf'], o['page'])].append(o)
    agree = disagree = only_one = none = 0
    samples = []
    for key, lst in sorted(per_page.items()):
        rads = [o['radical'] for o in lst if o['radical']]
        if len(set(rads)) > 1:
            disagree += 1
            if len(samples) < 8:
                samples.append((key, [(o['side'], o['radical']) for o in lst], [o['raw'] for o in lst]))
        elif rads:
            agree += 1
        else:
            none += 1
    print(f'页级: 一致 {agree} | 冲突 {disagree} | 双侧皆缺 {none}')
    for s in samples:
        print('  conflict:', s)


if __name__ == '__main__':
    main()
