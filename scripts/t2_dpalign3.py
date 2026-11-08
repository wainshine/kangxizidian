#!/usr/bin/env python3
"""T2 · 全局单调 DP 对齐 v3（所有者指示：切格→OCR→对齐一体化）

244 个 G′ 幸存框按阅读序（跨页 R→L、列聚类右→左、列内上→下）排成一条观测线，
对 48,708 条正典序列做一次全局单调对齐。书眉标签（所有者核验）只做候选区间约束：
  - 有标签 L 版：band = [S(部,k0), S(部,k_last+1))（S=部外k画首条；书眉画数=部外笔画）
  - 无标签 R 版：band = [前一个有标签版的 band.lo, 同跨页 L 版的 band.hi)
    （R 的内容 ⊆ 前版 band 首条 .. 本版 band 末条——含前版漏检尾部与前部首条带）
  - 備考（13_0163）：数据集无对应条目，band 空，跳过
打分：OCR300 双引擎命中 +4 / 形态先验 +0.5 / 擴展區 +0.2；跳框 -1.2 / 跳条目 -1.0。
DP (n+1)×(N+1) numpy 向量化（逐框行 + cummax 处理跳条目），band 外禁止匹配。
"""
import json, os, sys, collections
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T2 = os.path.join(ROOT, "work", "t2")
T1 = os.path.join(ROOT, "work", "t1")
T00 = os.path.join(ROOT, "work", "t00")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_segment import page_ink, height_mode, raw_blocks

SPLIT_X = 950
GAP_O, GAP_E, NEG = -1.2, 0.0, -1e9   # 跳条目免费：未采样间隙不是漏检；漏检按 band 事后记账


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def frame_gate_xs(gray):
    raw = (gray <= 150).astype(np.uint8)
    v = cv2.morphologyEx(raw, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(v, connectivity=8)
    H, W = gray.shape
    return [int(s[0]) for i, s in enumerate(stats)
            if i and s[3] >= 300 and 50 < s[0] < W - 50]


def half_blank(gray):
    return {name: (gray[:, sl] <= 150)[120:-120, 120:-120].mean() < 0.10
            for name, sl in (("L", slice(0, SPLIT_X)), ("R", slice(SPLIT_X, None)))}


def page_h0(stem, gray):
    for line in open(os.path.join(T00, "page_stats.jsonl")):
        d = json.loads(line)
        if d.get("file") == stem + ".png":
            return d.get("h0")
    return height_mode(raw_blocks(page_ink(gray))) or 41


def main():
    tp = json.load(open(os.path.join(T2, 't2_pages.json')))
    ml = json.load(open(os.path.join(T2, 'margin_labels_full.json')))
    RAD214 = "一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠"
    ALIAS = {'户': '戶', '青': '靑'}
    rad_idx = {c: i for i, c in enumerate(RAD214)}
    seq = [json.loads(l) for l in open(os.path.join(T2, 'entry_sequence.jsonl'), encoding='utf-8')]
    N = len(seq)
    anchors = {int(k): v for k, v in
               json.load(open(os.path.join(T2, 'foundation.json')))['anchors'].items()}
    v6 = {(r['page'], r['i']): r['text'] for r in
          map(json.loads, open(os.path.join(T2, 'ocr300_v6.jsonl'), encoding='utf-8'))}
    v5 = {(r['page'], r['i']): r['text'] for r in
          map(json.loads, open(os.path.join(T2, 'ocr300_v5.jsonl'), encoding='utf-8'))}
    owner_drop = {tuple(x) for x in
                  json.load(open(os.path.join(T2, 'owner_drop_r10.json')))['owner_drop']}

    rad_self = {}
    for e in seq:
        ri = e['rad_i']
        rad_self[ri] = min(rad_self.get(ri, 99), e['stroke'])
    sec_pts = collections.defaultdict(list)
    for e in seq:
        sec_pts[e['rad_i']].append((e['pos'], e['stroke'] - rad_self[e['rad_i']]))
    def S(ri, k):
        for p, o in sec_pts.get(ri, []):
            if o >= k:
                return p
        return anchors.get(ri + 1, N)

    CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8,
          '九': 9, '十': 10, '廿': 20, '卅': 30}
    def hua_k(f):
        v = 0
        for ch in f.replace('畫', ''):
            if ch in ('十', '廿', '卅'):
                v = v * CN[ch] if v else CN[ch]
            elif ch in CN:
                v += CN[ch]
        return v

    # ---- 版序列与 G′ 过滤 + 列聚类阅读序 ----
    versions = []
    for page in tp['pages']:
        lab = ml['pages'][page]
        gray = cv2.imread(os.path.join(T00, 'pages', page + '.png'), cv2.IMREAD_GRAYSCALE)
        h0 = page_h0(page, gray)
        gate_xs = frame_gate_xs(gray)
        blanks = half_blank(gray)
        d = json.load(open(os.path.join(T1, 'orig_boxes', page + '.json')))
        lri, lks = None, []
        if lab['L']['bu']:
            rk = lab['L']['bu'][:-1]
            lri = rad_idx.get(ALIAS.get(rk, rk))
            lks = [hua_k(h) for h in lab['L']['hua']] if lab['L']['hua'] else []
        for half in ('R', 'L'):
            items = []
            for bi, (b, ef) in enumerate(zip(d['boxes'], d['edge_flags'])):
                cx = (b[0] + b[2]) / 2
                if (half == 'R') != (cx >= SPLIT_X):
                    continue
                w, hh = b[2] - b[0], b[3] - b[1]
                ar = w / max(1, hh)
                kill = []
                if hh < 1.5 * h0: kill.append('h')
                if ef.get('blobs') != 1: kill.append('blobs')
                if not (0.7 <= ar <= 1.4): kill.append('sq')
                if any(b[0] < x < b[2] for x in gate_xs): kill.append('frame')
                if blanks[half]: kill.append('blank')
                if page == '01_0006' and half == 'L' and \
                        545 <= cx <= 800 and 350 <= (b[1]+b[3])/2 <= 735: kill.append('title')
                if (page, bi) in owner_drop: kill.append('owner')
                if kill:
                    continue
                items.append((b, bi, ef.get('edge_flag', False)))
            cands = sorted(items, key=lambda t: -(t[0][0] + t[0][2]) / 2)
            cols = []
            for it in cands:
                cx = (it[0][0] + it[0][2]) / 2
                if cols and cols[-1]['cx'] - cx <= 30:
                    cols[-1]['items'].append(it)
                else:
                    cols.append({'cx': cx, 'items': [it]})
            items = []
            for c in cols:
                items += sorted(c['items'], key=lambda t: t[0][1])
            versions.append({'page': page, 'half': half, 'items': items,
                             'lri': lri if half == 'L' else None,
                             'lks': lks if half == 'L' else []})

    # ---- band：先 labeled L，再回填 R（lo=前一个 labeled 的 lo，hi=同跨页 L 的 hi）----
    bands = [None] * len(versions)
    for vi, v in enumerate(versions):
        if v['lri'] is not None:
            k0 = v['lks'][0] if v['lks'] else 0
            klast = v['lks'][-1] if v['lks'] else 0
            bands[vi] = [S(v['lri'], k0), S(v['lri'], klast + 1)]
    prev_lo = None
    for vi, v in enumerate(versions):
        if bands[vi] is None:
            bands[vi] = [prev_lo if prev_lo is not None else 0, 0]
        else:
            prev_lo = bands[vi][0]
    for vi, v in enumerate(versions):
        if v['lri'] is None:
            for w in versions[vi:]:
                if w['lri'] is not None:
                    bands[vi][1] = bands[versions.index(w)][1]
                    break
    bands = [(int(max(0, a)), int(min(N, b))) for a, b in bands]

    # ---- 全局观测线 ----
    obs = []
    for vi, v in enumerate(versions):
        if bands[vi][1] <= bands[vi][0]:
            continue
        for (b, bi, ef) in v['items']:
            t6 = v6.get((v['page'], bi), '')
            t5 = v5.get((v['page'], bi), '')
            obs.append({'box': b, 'page': v['page'], 'half': v['half'], 'src_idx': bi,
                        'ef': ef, 'blo': bands[vi][0], 'bhi': bands[vi][1],
                        'c6': t6[:1] if t6 and is_cjk(t6[0]) else None,
                        'c5': t5[:1] if t5 and is_cjk(t5[0]) else None})
    n = len(obs)
    print(f'obs={n}', flush=True)

    chars = np.array([ord(e['char'][0]) for e in seq])
    seq_chars = [e['char'] for e in seq]

    # ---- 全局 DP：(n+1)×(N+1) ----
    DP = np.full((n + 1, N + 1), NEG, dtype=np.float64)
    DP[0] = 0.0   # 首框前起点自由（未采样条目不预罚）
    tvec = np.arange(N + 1, dtype=np.float64)
    for i in range(n):
        o = obs[i]
        row = DP[i] + GAP_O                        # 跳框 i
        # 跳条目（复利）：DP[i+1][j] = max_t<=j (row[t] + (j-t)*GAP_E)
        ce = (np.maximum.accumulate(row - tvec * GAP_E) + tvec * GAP_E)
        sc = np.full(N + 1, NEG, dtype=np.float64)
        lo, hi = max(1, o['blo']), min(o['bhi'], N)   # 匹配不可能落在 j=0
        if hi > lo:
            s = np.full(hi - lo, 0.5, dtype=np.float32)
            for k in range(lo, hi):
                if (o['c6'] and seq_chars[k] == o['c6']) or (o['c5'] and seq_chars[k] == o['c5']):
                    s[k - lo] = 4.0
            ext = chars[lo:hi] > 0xFFFF
            s[ext & (s < 0.5)] = 0.2
            sc[lo:hi] = DP[i][lo - 1:hi - 1] + s   # 匹配 entry j 用 DP[i][j-1]
        sc[0] = NEG
        # GAP_E=0 ⇒ 自由跳条目：DP[i+1][j] = running_max(max(row, sc))
        DP[i + 1] = np.maximum.accumulate(np.maximum(row, sc))
    print('DP done', flush=True)

    # ---- 回溯 ----
    i, j = n, int(np.argmax(DP[n]))
    print(f'backtrack start: i={i} j={j} DP[n][j]={DP[n][j]:.2f} DP[n].max={DP[n].max():.2f}', flush=True)
    pairs, fps, misses = [], [], []
    while i > 0:
        o = obs[i - 1]
        lo, hi = o['blo'], min(o['bhi'], N)
        sc = np.full(N + 1, NEG, dtype=np.float64)
        lo = max(1, lo)
        if hi > lo:
            s = np.full(hi - lo, 0.5, dtype=np.float32)
            for k in range(lo, hi):
                if (o['c6'] and seq_chars[k] == o['c6']) or (o['c5'] and seq_chars[k] == o['c5']):
                    s[k - lo] = 4.0
            ext = chars[lo:hi] > 0xFFFF
            s[ext & (s < 0.5)] = 0.2
            sc[lo:hi] = DP[i - 1][lo - 1:hi - 1] + s
        sc[0] = NEG
        eps = 1e-6
        if j > 0 and sc[j] > NEG/2 and abs(DP[i][j] - sc[j]) < eps:
            pairs.append((o, seq[j - 1])); i, j = i - 1, j - 1
        elif abs(DP[i][j] - (DP[i - 1][j] + GAP_O)) < eps:
            fps.append(o); i -= 1
        elif j > 0 and abs(DP[i][j] - (DP[i][j - 1] + GAP_E)) < eps:
            misses.append(seq[j - 1]); j -= 1
        else:
            print(f'  break at i={i} j={j}: sc[j]={sc[j]:.3f} DP[i][j]={DP[i][j]:.3f} '
                  f'DP[i-1][j]+GO={DP[i-1][j]+GAP_O:.3f} DP[i][j-1]+GE={DP[i][j-1]+GAP_E:.3f} '
                  f'band=[{lo},{hi}]', flush=True)
            break
    pairs.reverse()
    pairs.reverse()
    print(f'matched={len(pairs)} fp={len(fps)}', flush=True)
    out = [{'page': o['page'], 'half': o['half'], 'box': o['box'], 'src_idx': o['src_idx'],
            'edge_flag': o['ef'], 'entry_pos': e['pos'], 'char': e['char'],
            'rad': e['rad'], 'stroke': e['stroke'], 'extB': ord(e['char'][0]) > 0xFFFF,
            'ocr_v6': v6.get((o['page'], o['src_idx']), ''),
            'ocr_v5': v5.get((o['page'], o['src_idx']), '')}
           for o, e in pairs]
    json.dump({'pairs': out, 'n_obs': n, 'matched': len(pairs), 'fp': len(fps)},
              open(os.path.join(T2, 'dp_alignment3.json'), 'w'), ensure_ascii=False, indent=1)
    print('saved dp_alignment3.json', flush=True)


if __name__ == '__main__':
    main()
