"""t1_count_fit.py — 部内逐页计数拟合器（V4）

输入：
  work/lead/bu_start_pages_lead2.jsonl  214 部界页
  work/seq/volume_radicals.json         每部 entries（正典精确）+ 卷 body_pages
  work/lead/canonical_proto.jsonl       逐条目 bu_strokes（按 ci 书序）
  work/lead/headers_hua_seq.jsonl       逐页 hua 观测（L 半版）
  work/lead/counts_v3_dict.json         逐页计数初值（先验）
输出：
  work/lead/counts_v4.jsonl             {page,half,n,rule}
  work/lead/counts_v4_report.json       一致率/残差/差异 Top20

方法：对每部在其页区间内做 DP：
  dp[i][k] = 前 i 页恰放前 k 条的最小代价；
  代价(page i, window [k,k+c)) = w_i * hua 不一致数 + λ * |c - c0_i|
  w_i = hua 观测置信度（无观测/error → 0，即无约束）
  最终 dp[n][m]（m=部 entries，硬约束）。
R/L 拆分：若该页 hua 两个字段且窗口跨两个画数组 → R=第一组条数；否则按 v3 R/L 比例拆。
"""
import argparse, json, os, sys
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_canonical_strokes():
    """rad -> list[bu_strokes]（按 ci 书序）"""
    by = defaultdict(list)
    for line in open(os.path.join(ROOT, 'work/lead/canonical_proto.jsonl')):
        e = json.loads(line)
        by[e['rad']].append(int(e['bu_strokes']))
    return by


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lam', type=float, default=0.4)
    ap.add_argument('--soft', action='store_true', help='hua 软匹配（集合重叠率）')
    ap.add_argument('--hua', default=None, help='hua 观测文件覆盖')
    ap.add_argument('--out', default=os.path.join(ROOT, 'work/lead/counts_v4.jsonl'))
    ap.add_argument('--rep', default=os.path.join(ROOT, 'work/lead/counts_v4_report.json'))
    ap.add_argument('--v3all', default=os.path.join(ROOT, 'work/lead/counts_v3_all.jsonl'))
    args = ap.parse_args()

    vr = json.load(open(os.path.join(ROOT, 'work/seq/volume_radicals.json')))
    bu = [json.loads(l) for l in open(os.path.join(ROOT, 'work/lead/bu_start_pages_lead2.jsonl'))]
    hua = {}
    for line in open(args.hua or os.path.join(ROOT, 'work/lead/headers_hua_seq.jsonl')):
        r = json.loads(line)
        hua[r['page']] = r
    v3dict = json.load(open(os.path.join(ROOT, 'work/lead/counts_v3_dict.json')))
    strokes = load_canonical_strokes()

    # 每卷 juan 的部界序列
    juan_bu = defaultdict(list)
    for r in bu:
        juan_bu[(r['vol'], r['juan'])].append(r)
    for k in juan_bu:
        juan_bu[k].sort(key=lambda r: r['page'])

    # v3 全量 half 结构（用于输出同构）
    v3lines = [json.loads(l) for l in open(args.v3all)]
    v3half = {(r['page'], r['half']): r['n'] for r in v3lines}

    fit = {}            # page -> {'R':n,'L':n}
    fits = []           # 每部拟合明细
    cons_pages = []     # (page, consistent, pred, hua, w)
    cons_pages_v3 = []
    for (vol, juan), starts in juan_bu.items():
        j = next(j for j in vr['volumes'][vol]['juan'] if j['juan'] == juan)
        a, b = j['body_pages']
        rads = j['radicals']
        assert [s['radical'] for s in starts] == rads, (vol, juan)
        for i, st in enumerate(starts):
            rad = st['radical']
            p0 = st['page']
            p1 = starts[i + 1]['page'] - 1 if i + 1 < len(starts) else b
            pages = list(range(p0, p1 + 1))
            s = strokes[rad]
            m = len(s)
            assert m == j['entries'] if len(rads) == 1 else True
            # 该部 entries 数取自 volume_radicals 无法逐部给出（仅总数）→ 用 canonical 计数
            n = len(pages)
            # hua/先验
            obs = []
            for p in pages:
                page = f'{vol}_{p:04d}'
                key = hua.get(page)
                hv = key['hua'] if key else None
                conf = float(key['conf']) if (key and key.get('conf')) else 0.5
                errs = key.get('errors') if key else None
                w = 0.0 if (not hv or errs) else conf
                c0_R = v3dict.get(page, {}).get('R', 0)
                c0_L = v3dict.get(page, {}).get('L', 0)
                obs.append({'page': page, 'hua': list(hv or []), 'w': w,
                            'c0': c0_R + c0_L, 'c0R': c0_R, 'c0L': c0_L})
            # 每 k 的下一组起点（用于快速 distinct）
            nxt = [m] * m
            pos = m
            for k in range(m - 1, -1, -1):
                if k == m - 1:
                    nxt[k] = m
                elif s[k + 1] != s[k]:
                    nxt[k] = k + 1
                else:
                    nxt[k] = nxt[k + 1]

            def pred_groups(k, c):
                out = []
                kk = k
                c = max(0, min(c, m - k))
                end = k + c
                while kk < end and len(out) < 4:
                    v = s[kk]
                    out.append(v)
                    kk = nxt[kk]
                return out

            LAM = args.lam
            NEG = 1e9
            dp = np.full((n + 1, m + 1), NEG)
            bk = np.full((n + 1, m + 1), -1, dtype=int)
            dp[0, 0] = 0.0
            feasible = (m <= 30 * n)
            maxc = min(m, 30)
            for i in range(1, n + 1):
                o = obs[i - 1]
                for k in range(m + 1):
                    if dp[i - 1, k] >= NEG / 2:
                        continue
                    kk = min(maxc, m - k)
                    for c in range(kk + 1):
                        if c == 0:
                            score = (0.0 if not o['hua'] else 0.3 * o['w'])
                        else:
                            pred = pred_groups(k, c)
                            hv = o['hua']
                            if o['w'] > 0 and hv:
                                if args.soft:
                                    inter = len(set(pred) & set(hv))
                                    denom = max(len(set(pred)), len(set(hv)), 1)
                                    score = (1.0 - inter / denom) * o['w'] * 2.0
                                elif len(pred) <= len(hv):
                                    mism = sum(1 for jj in range(len(pred)) if pred[jj] != hv[jj])
                                    score = mism * o['w']
                                else:
                                    mism = sum(1 for jj in range(len(hv)) if pred[jj] != hv[jj])
                                    score = (mism + (len(pred) - len(hv))) * o['w']
                            else:
                                score = 0.0
                        dev = abs(c - o['c0'])
                        score += LAM * dev + 0.25 * max(0, dev - 5)
                        val = dp[i - 1, k] + score
                        if val < dp[i, k + c]:
                            dp[i, k + c] = val
                            bk[i, k + c] = k
            if not feasible or dp[n, m] >= NEG / 2:
                # 边界疑似错误：页数不足以容纳 entries → 按 v3 比例分配（cap 30），并标记
                caps = [30] * n
                base = [max(0, o['c0']) for o in obs]
                tot_base = sum(base) or 1
                raw = [min(caps[i], max(0, int(round(m * base[i] / tot_base)))) for i in range(n)]
                assigned = sum(raw)
                # 补足到 min(m, 30n)
                target = min(m, 30 * n)
                while assigned < target:
                    i = int(np.argmin([raw[j] if raw[j] < caps[j] else 10 ** 9 for j in range(n)]))
                    if raw[i] >= caps[i]:
                        break
                    raw[i] += 1
                    assigned += 1
                counts = raw
                deficit = m - assigned
                fits.append({'vol': vol, 'juan': juan, 'rad': rad, 'pages': pages,
                             'entries': m, 'counts': counts,
                             'hua_pages': sum(1 for o in obs if o['w'] > 0 and o['hua']),
                             'boundary_suspect': True, 'deficit': deficit})
                # 仍写入 fit（R/L 按 v3 比例）
                koff = 0
                for i, p in enumerate(pages):
                    c = counts[i]
                    o = obs[i]
                    tot0 = o['c0R'] + o['c0L']
                    if tot0 > 0:
                        R = int(round(c * o['c0R'] / tot0)); R = max(0, min(c, R))
                    else:
                        R = c // 2
                    fit[o['page']] = {'R': R, 'L': c - R, 'rad': rad, 'juan': juan}
                continue
            assert dp[n, m] < NEG / 2
            # 回溯
            counts = [0] * n
            k = m
            for i in range(n, 0, -1):
                kprev = bk[i, k]
                counts[i - 1] = k - kprev
                k = kprev
            assert sum(counts) == m
            # R/L 拆分
            koff = 0
            for i, p in enumerate(pages):
                c = counts[i]
                o = obs[i]
                R = L = 0
                if c == 0:
                    R = L = 0
                else:
                    pred = pred_groups(koff, c)
                    hv = o['hua']
                    if len(hv) >= 2 and len(pred) >= 2 and pred[0] == hv[0] and pred[1] == hv[1]:
                        # 第一组条目数
                        t = nxt[koff] - koff
                        R = min(t, c)
                        L = c - R
                    else:
                        tot0 = o['c0R'] + o['c0L']
                        if tot0 > 0:
                            R = int(round(c * o['c0R'] / tot0))
                            R = max(0, min(c, R))
                        else:
                            R = c // 2
                        L = c - R
                fit[o['page']] = {'R': R, 'L': L, 'rad': rad, 'juan': juan}
                # 一致性统计（v4 与 v3）
                if o['w'] > 0 and o['hua'] and c > 0:
                    pred = pred_groups(koff, c)
                    ok = (len(pred) <= len(o['hua']) and
                          all(pred[jj] == o['hua'][jj] for jj in range(len(pred))))
                    cons_pages.append({'page': o['page'], 'ok': ok, 'pred': pred,
                                       'hua': o['hua'], 'w': o['w']})
                    # v3 基线
                    pred3 = pred_groups(koff, o['c0'])
                    ok3 = (len(pred3) <= len(o['hua']) and
                           all(pred3[jj] == o['hua'][jj] for jj in range(len(pred3))))
                    cons_pages_v3.append({'page': o['page'], 'ok': ok3, 'pred': pred3,
                                          'hua': o['hua'], 'w': o['w']})
                koff += c
            fits.append({'vol': vol, 'juan': juan, 'rad': rad, 'pages': pages,
                         'entries': m, 'counts': counts,
                         'hua_pages': sum(1 for o in obs if o['w'] > 0 and o['hua']),
                         'boundary_suspect': False, 'deficit': 0})

    # 输出 counts_v4（沿用 v3 半版结构）
    rows = []
    for r in v3lines:
        page, half = r['page'], r['half']
        if page in fit:
            h = fit[page]
            n = h['R'] if half == 'R' else h['L']
        else:
            n = r['n']
        rows.append({'page': page, 'half': half, 'n': int(n),
                     'n_v3': int(r['n']), 'rule': 'v4-fit'})
    with open(args.out, 'w') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 报告
    def rate(lst):
        if not lst:
            return None
        return round(sum(1 for x in lst if x['ok']) / len(lst), 4)
    diffs = sorted(rows, key=lambda r: -abs(r['n'] - r['n_v3']))[:20]
    per_juan = []
    suspects = []
    for f in fits:
        per_juan.append({'vol': f['vol'], 'juan': f['juan'], 'rad': f['rad'],
                         'n_pages': len(f['pages']), 'entries': f['entries'],
                         'sum': int(sum(f['counts'])), 'suspect': f.get('boundary_suspect', False)})
        if f.get('boundary_suspect'):
            suspects.append({'vol': f['vol'], 'juan': f['juan'], 'rad': f['rad'],
                             'page': f['pages'][0], 'n_pages': len(f['pages']),
                             'entries': f['entries'], 'assigned': int(sum(f['counts'])),
                             'deficit': int(f.get('deficit', 0))})
    rep = {
        'rule': 'v4-fit', 'lam': args.lam,
        'total_entries': int(sum(len(strokes[k]) for k in strokes)),
        'v4_total': int(sum(r['n'] for r in rows)),
        'v3_total': int(sum(r['n_v3'] for r in rows)),
        'hua_consistent_v4': rate(cons_pages),
        'hua_consistent_v3': rate(cons_pages_v3),
        'n_hua_constrained_pages': len(cons_pages),
        'diff_top20': [{'page': r['page'], 'half': r['half'], 'v4': r['n'],
                        'v3': r['n_v3'], 'd': r['n'] - r['n_v3']} for r in diffs],
        'juan_fit': per_juan,
        'boundary_suspects': suspects,
        'boundary_suspect_count': len(suspects),
        'assigned_total': int(sum(r['n'] for r in rows)),
        'bad_pages': [x for x in cons_pages if not x['ok']][:40],
    }
    json.dump(rep, open(args.rep, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ('v4_total', 'v3_total', 'hua_consistent_v4',
                                          'hua_consistent_v3', 'n_hua_constrained_pages')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
