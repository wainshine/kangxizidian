"""t1_bu_boundaries.py — 版心部首格「同/不同」判部界（A′：集名3字锚块 + 单字紧裁 + ICM + DP）

数据源：Lead hdr_cells.npz（仅用其 page 列表；字格由本脚本从 300dpi 版心条自切）
流程：
1. 每页 300dpi 渲染左缘条（header_read.render_strip），固定 x 带 [4,110] 取版心；
2. 3 字集名锚块（05_0017 实测 y1263-1523）：ink 归一化大模板 matchTemplate（0.92-1.08 多尺度）→ 锚点 (ax,ay,scale)；
3. 部首格 y = 锚块底 + 0.47×块高（按该页 scale），候选 = 该页自切字格中中心距 y 估计 ≤100px 的格（最多 3 个，高>100 的按字距切分），单字高 cap 64×scale；
4. 部首格紧裁（x 宽仅 52×scale）+ ink-bbox 归一化 48×48；相邻页平移 NCC（±6px）；
5. ICM 3 轮在候选间重选（最大化与左右邻的 NCC 均值）；
6. 每卷 DP：选 k-1 个部界最大化 Σ(1-NCC)；输出 214 行 + QA。
"""
import argparse, json, os, sys, pickle
import numpy as np
import cv2

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import header_read as HR

X0, X1 = 4, 110
TM_Y0, TM_Y1 = 1263, 1523
TM_X0, TM_X1 = 8, 82
GAP_RATIO = 0.47
DS = 0.5
S = 48


def bgsub(gray):
    s = cv2.medianBlur(gray[:, X0:X1], 3)
    bg = cv2.medianBlur(s, 61)
    return (bg.astype(np.float32) - s.astype(np.float32))


def build_tmpl():
    g = HR.render_strip('05', 17, dpi=300, clipw_pt=40.0)
    d = bgsub(g)
    blk = d[TM_Y0:TM_Y1, TM_X0:TM_X1].copy()
    blk = cv2.resize(blk, None, fx=DS, fy=DS, interpolation=cv2.INTER_AREA)
    blk = blk - blk.mean()
    return (blk / blk.std()).astype(np.float32)


def anchor(g, tmpl):
    d = bgsub(g)
    d2 = cv2.resize(d, None, fx=DS, fy=DS, interpolation=cv2.INTER_AREA)
    best = (-9, None, None)
    for sc in (0.92, 0.96, 1.0, 1.04, 1.08):
        t = cv2.resize(tmpl, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        if t.shape[0] >= d2.shape[0] or t.shape[1] >= d2.shape[1]:
            continue
        r = cv2.matchTemplate(d2, t, cv2.TM_CCOEFF_NORMED)
        mn, mx, _, ml = cv2.minMaxLoc(r)
        if mx > best[0]:
            best = (mx, ml, sc)
    mx, (x, y), sc = best
    return mx, (x / DS, y / DS), sc


def norm_char(gray, y0, y1, x0, x1, pad=3):
    crop = gray[max(0, y0 - pad):min(gray.shape[0], y1 + pad), max(0, x0):min(gray.shape[1], x1)]
    if crop.size == 0 or crop.shape[0] < 12 or crop.shape[1] < 10:
        return None
    sg = cv2.medianBlur(crop, 3)
    bg = cv2.medianBlur(sg, 51)
    ink = (bg.astype(np.int16) - sg.astype(np.int16)) > 28
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    comps = [(st[i, 0], st[i, 1], st[i, 2], st[i, 3], st[i, 4]) for i in range(1, n) if st[i, 4] >= 8]
    if not comps:
        return None
    comps.sort(key=lambda c: -c[4])
    mx_, my, mw, mh, _ = comps[0]
    # 连通分量过滤：只保留与主分量同尺度（面积≥15%、宽高不超 1.6 倍）的分量
    ys, xs = [], []
    for (x, y, w, h, a) in comps:
        if a < 0.12 * comps[0][4]:
            continue
        if w > 1.7 * mw or h > 1.7 * mh:
            continue
        if y + h >= my - 8 and y <= my + mh + 8:
            ys += [y, y + h]; xs += [x, x + w]
    if not ys:
        return None
    y0b, y1b, x0b, x1b = min(ys), max(ys), min(xs), max(xs)
    c = sg[max(0, y0b - 1):y1b + 1, max(0, x0b - 1):x1b + 1].astype(np.float32)
    if c.shape[0] < 8 or c.shape[1] < 6:
        return None
    h, w = c.shape
    sc = min((S - 6) / h, (S - 6) / w)
    nh, nw = max(3, int(round(h * sc))), max(3, int(round(w * sc)))
    r = cv2.resize(c, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((S, S), float(np.median(sg)), np.float32)
    oy, ox = (S - nh) // 2, (S - nw) // 2
    canvas[oy:oy + nh, ox:ox + nw] = r
    v = canvas - canvas.mean()
    sd = v.std()
    return (v / sd).astype(np.float32) if sd > 1e-6 else None


def ncc(a, b, r=6):
    H, W = a.shape
    best = -1.0
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            y0, x0 = max(0, dy), max(0, dx)
            y1, x1 = min(H, H + dy), min(W, W + dx)
            if y1 - y0 < 20 or x1 - x0 < 20:
                continue
            B = np.zeros_like(a)
            B[y0:y1, x0:x1] = b[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
            aa = a - a.mean(); bb = B - B.mean()
            den = aa.std() * bb.std()
            if den < 1e-9:
                continue
            best = max(best, float((aa * bb).mean() / den))
    return best


def process_page(args):
    tmpl, vol, page = args
    try:
        g = HR.render_strip(vol, page, dpi=300, clipw_pt=40.0)
        ascore, (ax, ay), scale = anchor(g, tmpl)
        th = TM_Y1 - TM_Y0
        y0_est = ay + th * scale + GAP_RATIO * th * scale
        geo = HR.page_geometry(g)
        gx0, gx1 = geo[0], geo[1]
        cells = HR.segment_cells(HR.ink_mask(g, gx0, gx1), min_h=5)
        ch = int(round(64 * scale))
        crops = []
        for a, b in cells:
            if b - a < 25:
                continue
            if abs((a + b) / 2 - (y0_est + 20)) > 100:
                continue
            if b - a <= 100:
                crops.append((a, b))
            else:
                y = a
                while y + 40 <= b:
                    crops.append((y, min(b, y + ch)))
                    y += ch
        xa = int(X0 + ax) + int(8 * scale)
        xb = xa + int(52 * scale)
        crops.sort(key=lambda c: abs((c[0] + c[1]) / 2 - (y0_est + 20)))
        out = []
        for a, b in crops[:3]:
            b2 = min(b, a + int(72 * scale))
            v = norm_char(g, a, b2, xa, xb)
            if v is not None:
                out.append({'cell': (int(a), int(b2)), 'v': v})
        return {'vol': vol, 'page': page, 'cands': out, 'anchor_score': float(ascore)}
    except Exception as e:
        return {'vol': vol, 'page': page, 'cands': [], 'err': repr(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--cache', default=os.path.join(ROOT, 'work/seq/bu_anchor_cands.pkl'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'work/seq/bu_start_pages.jsonl'))
    ap.add_argument('--qa', default=os.path.join(ROOT, 'work/seq/bu_boundary_qa.json'))
    ap.add_argument('--refit', action='store_true')
    args = ap.parse_args()
    tmpl = build_tmpl()
    vr = json.load(open(os.path.join(ROOT, 'work/seq/volume_radicals.json')))
    jobs, juan_info = [], []
    for vol, v in vr['volumes'].items():
        for j in v['juan']:
            a, b = j['body_pages']
            pgs = list(range(a, b + 1))
            juan_info.append({'vol': vol, 'juan': j['juan'], 'radicals': j['radicals'],
                              'entries': j['entries'], 'pages': pgs})
            for p in pgs:
                jobs.append((tmpl, vol, p))
    if os.path.exists(args.cache) and not args.refit:
        recs = pickle.load(open(args.cache, 'rb'))
        print('cache', len(recs))
    else:
        from concurrent.futures import ProcessPoolExecutor
        recs = []
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(process_page, jobs, chunksize=8):
                recs.append(r)
        pickle.dump(recs, open(args.cache, 'wb'))
        print('processed', len(recs))
    C = {(r['vol'], int(r['page'])): r['cands'] for r in recs}
    rows = []
    qa = {'rule': 'A-prime anchor+crop+ICM+DP', 'juan': {}, 'gates': {}}
    for info in juan_info:
        vol, juan, pgs = info['vol'], info['juan'], info['pages']
        k = len(info['radicals'])
        cand = {p: C.get((vol, p), []) for p in pgs}
        ch = {p: (cand[p][0]['v'] if cand[p] else None) for p in pgs}

        def sim(a, b):
            return ncc(a, b) if (a is not None and b is not None) else -1.0
        for _ in range(3):
            changed = 0
            for i, p in enumerate(pgs):
                cs = cand[p]
                if len(cs) <= 1:
                    continue
                prev = ch[pgs[i - 1]] if i > 0 else None
                nxt = ch[pgs[i + 1]] if i + 1 < len(pgs) else None
                best = (-9, 0)
                for kk, c in enumerate(cs):
                    s, cnt = 0.0, 0
                    if prev is not None:
                        s += sim(c['v'], prev); cnt += 1
                    if nxt is not None:
                        s += sim(c['v'], nxt); cnt += 1
                    if cnt == 0:
                        continue
                    val = s / cnt - 0.02 * kk
                    if val > best[0]:
                        best = (val, kk)
                if best[1] != 0:
                    ch[p] = cs[best[1]]['v']; changed += 1
            if changed == 0:
                break
        sims = {p: sim(ch[p], ch[p + 1]) if p + 1 <= pgs[-1] else -1.0 for p in pgs[:-1]}
        changes = np.array([1.0 - sims[p] for p in pgs[:-1]])
        n = len(changes)
        m = k - 1
        if m == 0:
            bounds = []
        else:
            NEG = -1e9
            dp = np.full((m + 1, n + 1), NEG)
            prevb = np.full((m + 1, n + 1), -1, dtype=int)
            dp[0, :] = 0.0
            for c in range(1, m + 1):
                for t in range(c, n + 1):
                    seg = dp[c - 1, c - 1:t] + changes[c - 1:t]
                    jj = int(np.argmax(seg))
                    dp[c, t] = seg[jj]
                    prevb[c, t] = c - 1 + jj
            t, c = n, m
            bounds = []
            while c > 0 and t > 0:
                bounds.append(t)
                t = prevb[c, t]
                c -= 1
            bounds = sorted(bounds)
        seg_starts = [0] + bounds
        vals = [s for s in sims.values() if s != -1]
        same = [s for s in vals if s >= 0.55]
        diff = [s for s in vals if s < 0.55]
        qa['juan'][f'{vol}_{juan}'] = {
            'k': k, 'n_pages': len(pgs), 'ncand': sum(1 for p in pgs if cand[p]),
            'sim_median': round(float(np.median(vals)), 3) if vals else None,
            'sim_p10': round(float(np.percentile(vals, 10)), 3) if vals else None,
            'same_est_mean': round(float(np.mean(same)), 3) if same else None,
            'diff_est_mean': round(float(np.mean(diff)), 3) if diff else None,
            'boundaries': [pgs[t] for t in bounds],
            'boundary_scores': [round(float(changes[t - 1]), 2) for t in bounds],
        }
        for si, ridx in enumerate(range(k)):
            if si >= len(seg_starts):
                break
            pstart = pgs[seg_starts[si]]
            conf = float(changes[seg_starts[si] - 1]) if seg_starts[si] > 0 else 1.0
            rows.append({'vol': vol, 'juan': juan, 'page': f'{vol}_{pstart:04d}',
                         'radical_index': ridx + 1, 'radical': info['radicals'][ridx],
                         'conf': round(conf, 3),
                         'evidence': {'n_pages': len(pgs),
                                      'anchor_score': round(float([r for r in recs if r['vol'] == vol and r['page'] == pstart][0]['anchor_score']), 3),
                                      'ncc_prev': round(float(sims.get(pgs[seg_starts[si] - 1], -1)), 3)
                                      if seg_starts[si] > 0 else None}})
    with open(args.out, 'w') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    # gates
    j05 = qa['juan'].get('05_辰集上', {})
    first_ok = True
    for info in juan_info:
        exp = f"{info['vol']}_{info['pages'][0]:04d}"
        got = [r['page'] for r in rows if r['vol'] == info['vol'] and r['juan'] == info['juan'] and r['radical_index'] == 1]
        if not got or got[0] != exp:
            first_ok = False
    mono = True
    for info in juan_info:
        ps = [int(r['page'].split('_')[1]) for r in rows if r['vol'] == info['vol'] and r['juan'] == info['juan']]
        if ps != sorted(ps) or len(set(ps)) != len(ps) or any(ps[i + 1] - ps[i] < 1 for i in range(len(ps) - 1)):
            mono = False
    qa['gates'] = {
        '05_辰集上_boundaries_expected_[37,41]': j05.get('boundaries'),
        '05_pass': [p for p in j05.get('boundaries', [])] == [37, 41],
        'first_bu_page_36vols': first_ok,
        'count_equals_radicals': len(rows) == sum(len(j['radicals']) for v in vr['volumes'].values() for j in v['juan']),
        'monotone_min1page': mono,
    }
    json.dump(qa, open(args.qa, 'w'), ensure_ascii=False, indent=1)
    print('wrote', args.out, len(rows), 'rows')
    print('gates', qa['gates'])


if __name__ == '__main__':
    main()
