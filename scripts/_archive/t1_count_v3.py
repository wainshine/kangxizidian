"""t1_count_v3.py — 半版字头计数（大字优先规则）

输入：<boxes-dir>/<vol>_<page:04d>.json（t1_v2 检测输出，含 cands + 40 维特征）
输出：JSONL（page,half,n,rule）——供 Lead solver 使用。

规则（v3-big）：
1) 大字候选：size_ratio ∈ [1.70,2.80] 且 squareness ∈ [0.65,1.35]；
2) 强结构证据排除：argmax∈{guwen,title}、强圈字(ring_score≥0.62 & ring_r≥0.82)；
3) 注文块排除：n_comp≥4 且 (dom_frac<0.30 且 n_comp_ge32≥3) → 块；
   n_comp≥4 且无「最大分量占比≥0.55 或 dom_frac≥0.60」→ 仅当 hw≥0.45 且
   (n_comp_ge32≤2 或 dom_frac≥0.45) 时保留（治版刻碎片字头）；
4) 墨量 ink_ratio ≥ 0.12；
5) hw≥0.45，或 hw≥0.30 且 dom_frac≥0.60 且 n_ink_bands≤2（大字优先复核通道）；
6) 扁平字头（一/乙/亅 类）：sr≤0.85 且 w_ratio≥1.40 且 col_top 且 hw≥0.80；
7) L 半版版心柱（box 起点 x<10 且宽≥30）排除。
半版范围按 docs/STRUCTURE.md：36 卷 body_pages；卷首跨页 R 半版=卷扉页尾（不计），
卷末 L 半版留白按 volume_layout.json 置 0。
"""
import json, os, sys, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def is_head_v3(c, side='R'):
    """单候选判定（v3-big 规则），供 count 与 solver 框选择共用。"""
    f = c['feat']; sr = c['size_ratio']; ar = c['squareness']; hw = c['cls']['headword']
    am = c.get('argmax') or max(c['cls'], key=lambda k: c['cls'][k])
    if am in ('guwen', 'title'):
        return False
    if f.get('ring_score', 0) >= 0.62 and f.get('ring_r', 0) >= 0.82:
        return False
    box = c['box']
    if side == 'L' and box[0] < 10 and (box[2] - box[0]) >= 30:
        return False
    flat = (0.10 <= sr <= 0.85 and hw >= 0.80 and f.get('col_top')
            and f.get('w_ratio', 0) >= 1.40)
    if flat:
        return True
    if not (1.70 <= sr <= 2.80 and 0.65 <= ar <= 1.35):
        return False
    nc, nc32, df, mch, nb = (f['n_comp'], f['n_comp_ge32'], f['dom_frac'],
                             f['max_comp_h_ratio'], f['n_ink_bands'])
    if nc >= 4 and df < 0.30 and nc32 >= 3:
        return False
    if nc >= 4 and not (mch >= 0.55 or df >= 0.60):
        if not (hw >= 0.45 and (nc32 <= 2 or df >= 0.45)):
            return False
    if c['ink_ratio'] < 0.12:
        return False
    return hw >= 0.45 or (hw >= 0.30 and df >= 0.60 and nb <= 2)


def count_half(rec, side):
    return sum(1 for c in rec['halves'][side]['cands'] if is_head_v3(c, side))

def count_half_strict(rec, side):
    n = 0
    for c in rec['halves'][side]['cands']:
        am = c.get('argmax') or max(c['cls'], key=lambda k: c['cls'][k])
        if am == 'headword' and c['cls']['headword'] >= 0.80:
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--boxes', required=True, help='boxes300 dir (per-page JSON)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--radicals', default=os.path.join(ROOT, 'work/seq/volume_radicals.json'))
    ap.add_argument('--layout', default=os.path.join(ROOT, 'work/seq/volume_layout.json'))
    ap.add_argument('--stats', default=None)
    args = ap.parse_args()
    vr = json.load(open(args.radicals))
    vl = json.load(open(args.layout))
    rows = []
    stats = {'by_juan': {}, 'missing': [], 'rule': 'v3-big'}
    for vol, v in vr['volumes'].items():
        for j in v['juan']:
            a, b = j['body_pages']
            juan = j['juan']
            key = f"{vol}_{juan}"
            layout = (vl.get('juan') or {}).get(key, {})
            # 卷首跨页 R = 扉页尾；卷末 L 依实测
            endL = layout.get('end_page_L_is_content', True)
            det = 0
            for p in range(a, b + 1):
                fp = os.path.join(args.boxes, f"{vol}_{p:04d}.json")
                if not os.path.exists(fp):
                    stats['missing'].append(f"{vol}_{p:04d}")
                    rec = None
                else:
                    rec = json.load(open(fp))
                sides = []
                if p == a:
                    sides = ['L']
                elif p == b:
                    sides = ['R', 'L'] if endL else ['R', 'L']
                else:
                    sides = ['R', 'L']
                for side in sides:
                    if rec is None:
                        n = 0
                    elif side == 'L' and p == b and not endL:
                        n = 0
                    else:
                        n = count_half(rec, side)
                    n2 = 0 if (rec is None or (side == 'L' and p == b and not endL)) else count_half_strict(rec, side)
                    rows.append({'page': f"{vol}_{p:04d}", 'half': side, 'n': int(n),
                                 'n_strict_v2': int(n2), 'rule': 'v3-big'})
                    det += n
            stats['by_juan'][key] = {'entries': j['entries'], 'det': det,
                                     'ratio': round(det / j['entries'], 4) if j['entries'] else 0}
    with open(args.out, 'w') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    stats['n_halves'] = len(rows)
    stats['total_det'] = sum(r['n'] for r in rows)
    stats['total_entries'] = sum(v['entries'] for v in stats['by_juan'].values())
    stats['ratio_overall'] = round(stats['total_det'] / stats['total_entries'], 4)
    if args.stats:
        json.dump(stats, open(args.stats, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: stats[k] for k in ('n_halves', 'total_det', 'total_entries',
                                            'ratio_overall', 'missing')}, ensure_ascii=False))
    print('by_juan:')
    for k, x in stats['by_juan'].items():
        print(f"  {k:8s} entries={x['entries']:5d} det={x['det']:5d} ratio={x['ratio']:+.3f}")

if __name__ == '__main__':
    main()
