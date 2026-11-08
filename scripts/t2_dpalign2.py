#!/usr/bin/env python3
"""T2 · DP 重对齐 v2（T2-EXP30 裁定后）：书眉自标窗口 + G′ 过滤 + 阅读序 R→L

与 v1 (t2_dpalign.py) 的差异：
1. 窗口不再用「整部±锚点」，改用书眉自标（margin_labels_full.json，所有者核验）：
   S(部,k) = 正典序列中该部部外笔画=k 的首条 pos（书眉画数=部外笔画，桥=部首自身笔画）。
   单画数字段 → 整版内容 ⊂ [S(部,k), S(部,k+1))；双字段（跨分界页）→ [S(部,k), S(部,k2+1))。
2. 版顺序 = 每跨页先 R 后 L（T2-EXP30 §5 实证）；R 版书眉被裁无标签，
   窗口 = [max(cur, S(部_L,k0)−n_R), S(部_L,k_last+1))，n_R=R 版框数（ principled band）。
3. cur 顺序推进：采样页之间的未采样内容由画数分界自动闭合（S 跳变）。
4. 检出框过 G′ 闸（T2-EXP30 §4）：严格四闸 + 原墨框缘线跨越 + 标题块 + 透印半版；
   触边降为标记不杀。
5. 13_0163=備考：数据集无備考条目，不进 DP，单独记账。
"""
import json, os, collections, sys
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


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def frame_gate_xs(gray):
    """原墨 ≥300px 竖线段（排除页缘）——版框缘候选"""
    raw = (gray <= 150).astype(np.uint8)
    v = cv2.morphologyEx(raw, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(v, connectivity=8)
    H, W = gray.shape
    return [int(s[0]) for i, s in enumerate(stats)
            if i and s[3] >= 300 and 50 < s[0] < W - 50]


def half_blank(gray):
    kinds = {}
    for name, sl in (("L", slice(0, SPLIT_X)), ("R", slice(SPLIT_X, None))):
        ink = (gray[:, sl] <= 150)
        kinds[name] = ink[120:-120, 120:-120].mean() < 0.10
    return kinds


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
    anchors = {int(k): v for k, v in
               json.load(open(os.path.join(T2, 'foundation.json')))['anchors'].items()}
    def load_ocr(fn):
        f = os.path.join(T2, fn)
        if os.path.exists(f):
            return {(r['page'], r['i']): r['text'] for r in
                    map(json.loads, open(f, encoding='utf-8'))}
        return None
    v6 = load_ocr('ocr300_v6.jsonl') or load_ocr('ocr_v6.jsonl')
    v5 = load_ocr('ocr300_v5.jsonl') or load_ocr('ocr_v5.jsonl')
    print('OCR 源:', '300dpi' if v6 else '150dpi')
    owner_drop = [(p, i) for p, i in
                  json.load(open(os.path.join(T2, 'owner_drop_r10.json')))['owner_drop']]

    # 部首自身笔画 = 该部最小 stroke（部首自字）；S(部,k) = 部外笔画≥k 的首条 pos
    rad_self = {}
    for e in seq:
        ri = e['rad_i']
        rad_self[ri] = min(rad_self.get(ri, 99), e['stroke'])
    # sec_start[(ri,k)] = 首条 outer>=k 的 pos；outer = stroke - self
    sec_pts = collections.defaultdict(list)
    for e in seq:
        sec_pts[e['rad_i']].append((e['pos'], e['stroke'] - rad_self[e['rad_i']]))
    def S(ri, k):
        pts = sec_pts.get(ri, [])
        for p, o in pts:
            if o >= k:
                return p
        return anchors.get(ri + 1, len(seq))  # 部末

    CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8,
              '九': 9, '十': 10, '廿': 20, '卅': 30}
    def hua_to_k(f):  # 「十二畫」→ 12
        f = f.replace('畫', '')
        v = 0
        for ch in f:
            if ch in CN_NUM:
                if ch in ('十', '廿', '卅'):
                    v = v * CN_NUM[ch] if v else CN_NUM[ch]
                else:
                    v += CN_NUM[ch]
        return v

    # ---- 逐页构建「版」序列（阅读序 R→L）与 G′ 过滤 ----
    versions = []   # {page,half,boxes:[(box,src_idx)],label:(ri,[k0,k1?]...)} 
    stats = collections.Counter()
    for page in tp['pages']:
        lab = ml['pages'][page]
        gray = cv2.imread(os.path.join(T00, 'pages', page + '.png'), cv2.IMREAD_GRAYSCALE)
        h0 = page_h0(page, gray)
        gate_xs = frame_gate_xs(gray)
        blanks = half_blank(gray)
        d = json.load(open(os.path.join(T1, 'orig_boxes', page + '.json')))
        boxes, flags = d['boxes'], d['edge_flags']
        drop = {(p, i) for p, i in owner_drop}
        # L 标签 → (ri, [k...])
        lri, lks = None, []
        if lab['L']['bu']:
            rk = lab['L']['bu'][:-1]
            lri = rad_idx.get(ALIAS.get(rk, rk))
            lks = [hua_to_k(h) for h in lab['L']['hua']] if lab['L']['hua'] else []
        for half in ('R', 'L'):
            bl = blanks[half]
            items = []
            for bi, (b, ef) in enumerate(zip(boxes, flags)):
                cx = (b[0] + b[2]) / 2
                if (half == 'R') != (cx >= SPLIT_X):
                    continue
                w, hh = b[2] - b[0], b[3] - b[1]
                ar = w / max(1, hh)
                kill = []
                if hh < 1.5 * h0:
                    kill.append('h')
                if ef.get('blobs') != 1:
                    kill.append('blobs')
                if not (0.7 <= ar <= 1.4):
                    kill.append('sq')
                if any(b[0] < x < b[2] for x in gate_xs):
                    kill.append('frame')
                if bl:
                    kill.append('blank')
                if page == '01_0006' and half == 'L' and \
                        545 <= (b[0]+b[2])/2 <= 800 and 350 <= (b[1]+b[3])/2 <= 735:
                    kill.append('title')
                if (page, bi) in drop:
                    kill.append('owner')
                if kill:
                    stats['g_kill_' + kill[0]] += 1
                    continue
                stats['g_keep'] += 1
                items.append((b, bi, ef.get('edge_flag', False)))
            # 阅读序：列聚类（同列 cx 摆动 ≤30px 合并）→ 列右→左 → 列内上→下
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
                             'blank': bl, 'lri': lri if half == 'L' else None,
                             'lks': lks if half == 'L' else []})
        print(f'{page}: L标签={lab["L"]["bu"]}{lks} R空白={blanks["R"]} L空白={blanks["L"]}')

    # ---- 注文音切通道：字头下方（或左列顶）注文带 → 竖列 OCR → 常用字指纹 ----
    from paddleocr import PaddleOCR
    import warnings; warnings.filterwarnings("ignore")
    import fitz
    pdf_map = json.load(open(os.path.join(T2, 'pdf_map.json')))
    docs = {}
    def doc_of(idx):
        if idx not in docs:
            docs[idx] = fitz.open(os.path.join(ROOT, '康熙字典', pdf_map[idx]))
        return docs[idx]
    e6 = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_textline_orientation=False)
    e5 = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                   lang="ch", text_recognition_model_name="PP-OCRv5_server_rec")
    def ocr_frag(img):
        import tempfile
        tp = os.path.join(T2, 'tmp', 'frag2.png')
        cv2.imwrite(tp, img)
        out = []
        try:
            res = e6.predict(tp)
            if res:
                j = res[0].json.get('res', res[0]) if hasattr(res[0], 'json') else res[0]
                t = j.get('rec_texts', []); bx = j.get('rec_boxes', [])
                for k, txt in enumerate(t):
                    ytop = bx[k][1] if k < len(bx) and len(bx[k]) == 4 else 0
                    out.append((float(ytop), str(txt)))
        except Exception:
            pass
        out.sort()
        s = ''.join(t for _, t in out)
        return ''.join(ch for ch in s if is_cjk(ch))[:10]

    import openpyxl, glob as _glob
    wb = openpyxl.load_workbook(_glob.glob('data/ref/**/*.xls*', recursive=True)[0], read_only=True)
    ws = wb.active
    xrows = list(ws.iter_rows(values_only=True))
    defn = {}
    for ri_, r in enumerate(xrows[1:]):
        d_ = str(r[7]) if r[7] else ''
        defn[ri_] = ''.join(ch for ch in d_[:46] if is_cjk(ch))

    def frag_below(g, b):
        x0, y0, x1, y1 = b
        H, W = g.shape
        return g[y1+2:min(H, y1+140), max(0, x0-4):min(W, x1+4)]

    def frag_leftcol(g, b, frame_top):
        x0, y0, x1, y1 = b
        cx = (x0 + x1) / 2
        return g[frame_top+12:frame_top+150, max(0, int(cx-47-26)):int(cx-47+26)]

    frag_read = {}
    n_frag = 0
    for v in versions:
        g = cv2.imread(os.path.join(T00, 'pages', v['page'] + '.png'), cv2.IMREAD_GRAYSCALE)
        ft = 330
        for line in open(os.path.join(T00, 'page_stats.jsonl')):
            dd = json.loads(line)
            if dd.get('file') == v['page'] + '.png':
                fr = dd.get('halves', [])
                ft = (fr[0].get('frame') or [0, 330, 0, 0])[1] if fr else 330
                break
        for (b, bi, ef) in v['items']:
            fb = frag_below(g, b)
            img = fb
            if (fb < 150).mean() < 0.02:
                img = frag_leftcol(g, b, ft)
            txt = ocr_frag(img)
            if txt:
                frag_read[(v['page'], bi)] = txt
                n_frag += 1
    print(f'注文读数: {n_frag}/{sum(len(v["items"]) for v in versions)}', flush=True)

    # ---- 窗口计算 + 顺序 DP ----
    out_all, vers_meta = [], []
    cur = 0
    for vi, v in enumerate(versions):
        n_r = len(v['items'])
        if v['blank'] and n_r == 0:
            vers_meta.append({**{k: v[k] for k in ('page', 'half')}, 'skip': 'blank'})
            continue
        page, half = v['page'], v['half']
        if page == '13_0163':
            vers_meta.append({**{k: v[k] for k in ('page', 'half')}, 'skip': '備考(无数据集条目)'})
            continue
        if v['lri'] is not None:      # labeled L
            k0 = v['lks'][0] if v['lks'] else 0
            klast = v['lks'][-1] if v['lks'] else 0
            lo = max(cur, S(v['lri'], k0))
            hi = S(v['lri'], klast + 1)
        else:                          # unlabeled R： principled band
            nxt = None
            for w in versions[vi:]:
                if w['lri'] is not None:
                    nxt = w   # 只看标签是否可用，不看框数（obs=0 的版仍约束窗口）
                    break
            if nxt is None:
                vers_meta.append({**{k: v[k] for k in ('page', 'half')}, 'skip': '无后续标签'})
                continue
            k0 = nxt['lks'][0] if nxt['lks'] else 0
            klast = nxt['lks'][-1] if nxt['lks'] else 0
            lo = max(cur, S(nxt['lri'], k0) - n_r)
            hi = S(nxt['lri'], klast + 1)
        lo = max(0, lo)
        hi = max(lo + 1, min(hi, len(seq)))
        exp = seq[lo:hi]
        obs = v['items']
        # 注文指纹：band 内候选 × 释义头有序命中
        for oi_, x in enumerate(obs):
            b_, bi_, ef_ = x[0], x[1], x[2]
            f = frag_read.get((v['page'], bi_))
            best_k = None
            if f and len(exp) > 1:
                best_s, second = 0.0, 0.0
                for k in range(len(exp)):
                    head = defn.get(exp[k]['i'], '')
                    if len(head) < 3:
                        continue
                    jj = 0; hits = 0
                    for ch in f:
                        while jj < len(head) and head[jj] != ch:
                            jj += 1
                        if jj < len(head):
                            hits += 1; jj += 1
                    s = hits / max(1, len(f))
                    if s > best_s:
                        second = best_s; best_s, best_k = s, k
                    elif s > second:
                        second = s
                if not (best_s >= 0.6 and (len(f) >= 3 and best_s - second >= 0.2 or best_s >= 0.9)):
                    best_k = None
            obs[oi_] = (b_, bi_, ef_, best_k)
        n_anchor = sum(1 for x in obs if x[3] is not None)
        print(f'  注文锚 {n_anchor}/{len(obs)}', flush=True)
        # OCR 锚点
        def ocr_of(it):
            return (v6.get((page, it[1]), ''), v5.get((page, it[1]), ''))
        anch = {}
        for oi, it in enumerate(obs):
            t6, t5 = ocr_of(it)
            for ch in {t6[:1] if t6 and is_cjk(t6[0]) else None,
                       t5[:1] if t5 and is_cjk(t5[0]) else None}:
                if not ch:
                    continue
                hits = [e['pos'] for e in exp if e['char'] == ch]
                if len(hits) == 1:
                    anch.setdefault(oi, set()).add(hits[0])
        # DP（NW 变体，锚点加分）
        n, m = len(obs), len(exp)
        GAP_O, GAP_E, NEG = -1.2, -1.0, -1e9
        dp = np.full((n + 1, m + 1), NEG)
        bt = np.zeros((n + 1, m + 1), dtype=np.int8)
        dp[0, 0] = 0
        aset = {oi: ps for oi, ps in anch.items()}
        for i in range(n + 1):
            for j in range(m + 1):
                if i > 0 and dp[i - 1, j] > NEG:
                    vv = dp[i - 1, j] + GAP_O
                    if vv > dp[i, j]:
                        dp[i, j], bt[i, j] = vv, 2
                if j > 0 and dp[i, j - 1] > NEG:
                    vv = dp[i, j - 1] + GAP_E
                    if vv > dp[i, j]:
                        dp[i, j], bt[i, j] = vv, 3
                if i > 0 and j > 0 and dp[i - 1, j - 1] > NEG:
                    it, e = obs[i - 1], exp[j - 1]
                    score = 0.5
                    t6, t5 = ocr_of(it)
                    c6 = t6[:1] if t6 and is_cjk(t6[0]) else None
                    c5 = t5[:1] if t5 and is_cjk(t5[0]) else None
                    if e['char'] in (c6, c5):
                        score = 4.0
                    elif ord(e['char'][0]) > 0xFFFF:
                        score = 0.2
                    anc = obs[i - 1][3] if len(obs[i - 1]) == 4 else None
                    if anc is not None and exp[j - 1]['pos'] == exp[anc]['pos']:
                        score = max(score, 6.0)   # 注文指纹锚
                    # 锚点矛盾惩罚：oi 有唯一锚 p，匹配 pos≠p → 减分
                    if i - 1 in aset and aset[i - 1] and e['pos'] not in aset[i - 1]:
                        score -= 3.0
                    vv = dp[i - 1, j - 1] + score
                    if vv > dp[i, j]:
                        dp[i, j], bt[i, j] = vv, 1
        i, j = n, m
        pairs, fps, misses = [], [], []
        while i > 0 or j > 0:
            t = bt[i, j]
            if t == 1:
                pairs.append((obs[i - 1], exp[j - 1])); i, j = i - 1, j - 1
            elif t == 2:
                fps.append(obs[i - 1]); i -= 1
            elif t == 3:
                misses.append(exp[j - 1]); j -= 1
            else:
                break
        pairs.reverse(); misses.reverse()
        last = pairs[-1][1]['pos'] if pairs else None
        if last is not None:
            cur = max(cur, last + 1)
        stats['matched'] += len(pairs)
        stats['fp'] += len(fps)
        stats['miss'] += len(misses)
        stats['extB'] += sum(1 for _, e in pairs if ord(e['char'][0]) > 0xFFFF)
        print(f'  {page}{half}: obs={n} win=[{lo},{hi}) exp={m} matched={len(pairs)} '
              f'fp={len(fps)} miss={len(misses)} cur→{cur}')
        vers_meta.append({'page': page, 'half': half, 'win': [lo, hi],
                          'obs': n, 'matched': len(pairs), 'fp': len(fps), 'miss': len(misses)})
        for (b, bi, ef, ak), e in pairs:
            t6, t5 = ocr_of((b, bi, ef))
            out_all.append({'page': page, 'half': half, 'box': b, 'src_idx': bi,
                            'edge_flag': ef, 'entry_pos': e['pos'], 'char': e['char'],
                            'rad': e['rad'], 'stroke': e['stroke'],
                            'extB': ord(e['char'][0]) > 0xFFFF,
                            'anchor': exp[ak]['pos'] if ak is not None else None,
                            'ocr_v6': t6, 'ocr_v5': t5})
    json.dump({'versions': vers_meta, 'pairs': out_all},
              open(os.path.join(T2, 'dp_alignment2.json'), 'w'), ensure_ascii=False, indent=1)
    print(dict(stats))


if __name__ == '__main__':
    main()
