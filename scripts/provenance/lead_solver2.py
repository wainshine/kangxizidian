#!/usr/bin/env python3
"""Lead · v3 求解器 v2：带书眉约束的计数纠错 + 框↔条目指派。

与 lead_solver.py 的区别：
- 用**书眉硬约束**（L 半版的 部 + 画数字段 ⊆ 预测组集合）做校验；
- 计数不一致时做**局部搜索纠错**（±1/±2 的组合，窗口内），不静默漂移；
- 输出**框级**指派（candidates 提供有序候选框）。

接口：
  canonical/groups 同 lead_solver.py
  --counts   {"01_0006": {"R": 3, "L": 5}, ...}（detector 的字头计数）
  --cands    JSONL: 每行 {page, half, cands:[{id, box, score}]}（按阅读序，score=p_headword）
  --headers  JSONL: {page, half:"L", bu, hua:[int], conf}
  --body     JSON: {"01": {"start_page": 6}, "02": {"start_page": 5}, ...} 卷体起始页（此前页计数强制 0）
  --out      work/map/

输出：
  work/map/mapping.jsonl   每半版一条，含 entries 与 box 指派
  work/map/report.json     统计/不一致窗口/纠错记录
  work/map/needs_review.jsonl  未解决的半版
"""
import json, os, sys, argparse, itertools, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lead_solver import (ROOT, MAIN_VOLS, build_sequence, Canon, norm_bu, norm_hua, key)


def build_body_sequence(roles_path, vols=MAIN_VOLS):
    """从页角色表构造正文半版序列（跳过封面/空白/集扉页/卷界页）。"""
    roles = {}
    for line in open(roles_path, encoding="utf-8"):
        r = json.loads(line)
        roles[(r["vol"], r["page"])] = r["role"]
    seq = []
    for v in vols:
        ps = sorted(p for (vv, p) in roles if vv == v)
        for p in ps:
            if roles[(v, p)] != "body":
                continue
            seq.append((v, p, "R"))
            seq.append((v, p, "L"))
    return seq


def load_boxes_dir(boxdir, role_filter=None):
    """读取 t1_v2 输出的每页 JSON → counts + cands（有序）。
    约定：cands 已按阅读序；选择 = cls.headword >= thr 的候选。
    """
    import glob
    counts = {}
    cands = {}
    for f in sorted(glob.glob(os.path.join(boxdir, "*.json"))):
        r = json.load(open(f, encoding="utf-8"))
        page = r["page"]
        for half in ("R", "L"):
            h = r["halves"].get(half) or {}
            cl = h.get("cands") or []
            counts.setdefault(page, {})[half] = int(h.get("count_headword", 0) or 0)
            cands[(page, half)] = cl
    return counts, cands


def load_jsonl(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def header_ok(canon, ci_start, ci_end, hdr, half="L"):
    """书眉约束（seq 2026-11-08 口径）：
    - 双画数字段 hua=[v_R, v_L]：R 半版 ∈ v_R 组；L 半版 ∈ v_L 组（若 L 跨到下一组则 hua 会有第三个字段）。
    - 单画数 hua=[v]：R/L 都在该组。
    - hua 为空但 bu 有值（部首页）：只校验部名。
    - 无法校验 → None。
    """
    bu = norm_bu(hdr.get("bu"))
    made = norm_hua(hdr.get("hua"))
    if not bu:
        # 画数-only 模式：预测组（bu_strokes）必须落在书眉画数覆盖范围内
        if not made:
            return None
        used = []
        for ci in range(ci_start, ci_end):
            if ci >= canon.n:
                break
            r, b = canon.group_of_ci(ci)
            used.append(b)
        if not used:
            return None
        if half == "R":
            allowed = {made[0]}
        else:
            allowed = set(made) | {max(made) + 1}
        return set(used) <= allowed
    used = []
    for ci in range(ci_start, ci_end):
        if ci >= canon.n:
            break
        r, b = canon.group_of_ci(ci)
        used.append((norm_bu(r), b))
    if not used:
        return None
    if not made:
        return all(r == bu for r, _ in used)
    if half == "R":
        allowed = {(bu, made[0])}      # R 半版更早，只可能在叶覆盖组的第一个
    else:
        allowed = {(bu, h) for h in made}   # L 半版可能跨到后续组
    return set(used) <= allowed


def rebuild(seq, counts, body_start, force_zero_before_body=True):
    """按 counts 累计，返回每 half 的 (ci_start, ci_end)。"""
    out = []
    ci = 0
    for (vol, page, half) in seq:
        pkey = f"{vol}_{page:04d}"
        c = 0
        if force_zero_before_body:
            bs = body_start.get(vol, 1)
            in_body = page >= bs
        else:
            in_body = True
        if in_body:
            c = int(counts.get(pkey, {}).get(half, 0) or 0)
        out.append((pkey, half, ci, min(ci + c, 10 ** 9), c, in_body))
        ci += c
    return out


def check_all(canon, rows, headers):
    """返回 [ok/None]；R 和 L 半版都用同一页 L 书眉校验（半版参数不同）。"""
    res = []
    for i, (pkey, half, a, b, c, in_body) in enumerate(rows):
        if not in_body:
            res.append(None)
            continue
        hdr = headers.get(key(pkey, "L"))
        if not hdr:
            res.append(None)
            continue
        res.append(header_ok(canon, a, b, hdr, half=half))
    return res


def local_fix(canon, rows, headers, start_idx, max_edits=2, window=24, max_delta=1):
    """从第一个失败点往回搜窗口，找最小计数修正让所有校验通过。

    返回 [(seq_idx, delta)] 或 None。
    """
    n = len(rows)
    lo = max(0, start_idx - window)
    # 当前位置（start_idx 的 ci_start）之后所有 L 校验
    def run(edits):
        """只校验到 first 之后 6 个半版（增量纠错；不要求修好全书所有后续错误）。"""
        counts = collections.defaultdict(int)
        for idx, d in edits:
            counts[idx] += d
        ci = rows[lo][2]
        upto = min(n, start_idx + 1)   # 只要求修好「第一个失败校验」（含）之前
        for i in range(lo, upto):
            pkey, half, a0, b0, c0, in_body = rows[i]
            c = c0 + counts.get(i, 0)
            if c < 0:
                return None
            a, b = ci, ci + c
            ci = b
            if half == "L" and in_body:
                hdr = headers.get(key(pkey, "L"))
                if hdr:
                    ok = header_ok(canon, a, b, hdr)
                    if ok is False:
                        return None
        return ci

    # 先确认从 lo 开始无修正时到失败点之前都 ok（调用方保证）
    cand_idxs = list(range(lo, min(n, start_idx + 2)))
    for k in range(1, max_edits + 1):
        for idxs in itertools.combinations(cand_idxs, k):
            for deltas in itertools.product(range(1, max_delta + 1), repeat=k):
                for signs in itertools.product([-1, 1], repeat=k):
                    edits = [(i, s * d) for i, d, s in zip(idxs, deltas, signs)]
                    if run(edits) is not None:
                        return edits
    return None


def load_volumes(path):
    """36 卷 -> [{vol, juan, a, b, entries}]，按书序；返回 (order_list, cum_offsets)."""
    v = json.load(open(path, encoding="utf-8"))
    out = []
    for vol in sorted(v["volumes"]):
        for j in v["volumes"][vol]["juan"]:
            a, b = j["body_pages"]
            out.append({"vol": vol, "juan": j["juan"], "a": a, "b": b,
                        "entries": int(j["entries"])})
    cum = 0
    for o in out:
        o["ci0"] = cum
        cum += o["entries"]
    return out, cum


def load_bu_segments(volumes_path, bu_pages_path, canon_path):
    """卷结构 + 部界页 → 部段列表。
    bu_pages_path: JSONL {vol,page,...}，按书序 214 行（每个部首页一行）。
    返回 [{"vol","rad","a","b","entries"}...]；entries 由正典按 rad 统计。
    """
    vr = json.load(open(volumes_path, encoding="utf-8"))
    bus = [json.loads(l) for l in open(bu_pages_path, encoding="utf-8") if l.strip()]
    rad_order = []
    for vol in sorted(vr["volumes"]):
        for j in vr["volumes"][vol]["juan"]:
            for r in j["radicals"]:
                rad_order.append((vol, r))
    if len(bus) != len(rad_order):
        print(f"[warn] bu-anchors {len(bus)} 行 vs 214 部 {len(rad_order)}", file=sys.stderr)
    # 正典每 rad entries
    import collections as _C
    by_rad = _C.Counter()
    for line in open(canon_path, encoding="utf-8"):
        e = json.loads(line)
        by_rad[e["rad"]] += 1
    # 卷末页
    vol_end = {}
    for vol in sorted(vr["volumes"]):
        js = vr["volumes"][vol]["juan"]
        vol_end[vol] = max(j["body_pages"][1] for j in js)
    segs = []
    for k, (vol, rad) in enumerate(rad_order):
        if k >= len(bus):
            break
        a = int(bus[k]["page"])
        # 下一部起点（同卷内），否则卷末
        nxt = None
        if k + 1 < len(rad_order) and rad_order[k + 1][0] == vol and k + 1 < len(bus):
            nxt = int(bus[k + 1]["page"])
        b = (nxt - 1) if nxt else vol_end[vol]
        segs.append({"vol": vol, "rad": rad, "a": a, "b": b,
                     "entries": int(by_rad.get(rad, 0)), "label": f"{vol}/{rad}"})
    return segs


def reconcile_segments(seq, counts, segs):
    """按任意段列表（部/卷）精确配平计数：段内按「当前最大格」逐单位增减。
    segs: [{"vol","a","b","entries","label"}...]（页区间闭区间）。"""
    keys = [(f"{v}_{p:04d}", h) for (v, p, h) in seq]
    assign = []
    for pkey, half in keys:
        vol = pkey[:2]
        pg = int(pkey[3:])
        idx = None
        for k, o in enumerate(segs):
            if o["vol"] == vol and o["a"] <= pg <= o["b"]:
                idx = k
                break
        assign.append(idx)
    recon = []
    for k, o in enumerate(segs):
        idxs = [i for i, a in enumerate(assign) if a == k]
        if not idxs:
            recon.append({"label": o["label"], "canon": o["entries"],
                          "raw": 0, "delta": o["entries"]})
            continue
        cur = [int((counts.get(keys[i][0]) or {}).get(keys[i][1], 0) or 0) for i in idxs]
        S = sum(cur)
        delta = o["entries"] - S
        recon.append({"label": o["label"], "canon": o["entries"], "raw": S, "delta": delta})
        if delta == 0:
            continue
        while delta > 0:
            j = max(range(len(cur)), key=lambda t: cur[t])
            cur[j] += 1
            delta -= 1
        while delta < 0:
            j = max(range(len(cur)), key=lambda t: cur[t])
            if cur[j] <= 0:
                break
            cur[j] -= 1
            delta += 1
        for j, i in enumerate(idxs):
            pkey, half = keys[i]
            counts.setdefault(pkey, {})
            counts[pkey][half] = cur[j]
    return counts, recon


def reconcile_volumes(seq, counts, vols, canon_n):
    """按 36 卷 entries 精确配平逐页计数。
    做法：先按卷求和，与卷 entries 求差；差额逐单位增减到「当前计数最大」的半版上
    （近似按比例，整数、不越界）。seq 元素 = (vol, page, half)。"""
    keys = [(f"{v}_{p:04d}", h) for (v, p, h) in seq]
    assign = []
    for pkey, half in keys:
        vol = pkey[:2]
        pg = int(pkey[3:])
        idx = None
        for k, o in enumerate(vols):
            if o["vol"] == vol and o["a"] <= pg <= o["b"]:
                idx = k
                break
        assign.append(idx)
    recon = []
    for k, o in enumerate(vols):
        idxs = [i for i, a in enumerate(assign) if a == k]
        if not idxs:
            continue
        cur = [int((counts.get(keys[i][0]) or {}).get(keys[i][1], 0) or 0) for i in idxs]
        S = sum(cur)
        delta = o["entries"] - S
        recon.append({"vol": o["vol"], "juan": o["juan"], "canon": o["entries"],
                      "raw": S, "delta": delta})
        if delta == 0:
            continue
        # 逐单位增减：正差加到当前最大的；负差从当前最大的减（>0 才减）
        import heapq
        while delta > 0:
            j = max(range(len(cur)), key=lambda t: cur[t])
            cur[j] += 1
            delta -= 1
        while delta < 0:
            j = max(range(len(cur)), key=lambda t: cur[t])
            if cur[j] <= 0:
                break
            cur[j] -= 1
            delta += 1
        for j, i in enumerate(idxs):
            pkey, half = keys[i]
            counts.setdefault(pkey, {})
            counts[pkey][half] = cur[j]
    return counts, recon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", default=os.path.join(ROOT, "work/lead/canonical_proto.jsonl"))
    ap.add_argument("--groups", default=os.path.join(ROOT, "work/lead/groups_proto.json"))
    ap.add_argument("--counts", default=None)
    ap.add_argument("--cands", default=None)
    ap.add_argument("--boxes-dir", default=None)
    ap.add_argument("--headers", default=None)
    ap.add_argument("--body", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--roles", default=os.path.join(ROOT, "work/lead/page_roles.jsonl"))
    ap.add_argument("--volumes", default=os.path.join(ROOT, "work/seq/volume_radicals.json"))
    ap.add_argument("--no-reconcile", action="store_true")
    ap.add_argument("--bu-anchors", default=None, help="部界页 JSONL（vol,page,radical）")
    ap.add_argument("--report-only", action="store_true", help="只用书眉做统计，不改计数")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--noise-rate", type=float, default=0.10)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    canon = Canon(args.canonical, args.groups)
    print(f"canonical: {canon.n} entries, {len(canon.groups)} groups")

    if args.roles and os.path.exists(args.roles):
        seq = build_body_sequence(args.roles)
        print(f"正文半版序列: {len(seq)}（来自 {args.roles}）")
    else:
        seq = build_sequence(MAIN_VOLS, first_page=6)
    if args.limit:
        seq = seq[:args.limit]

    if args.self_test:
        self_test(canon, seq, args.noise_rate)
        return

    counts = json.load(open(args.counts, encoding="utf-8")) if args.counts else {}
    body = json.load(open(args.body, encoding="utf-8")) if args.body else {}
    body_start = {v: body.get(v, {}).get("start_page", 1) for v in MAIN_VOLS}
    headers = {}
    if args.headers:
        for d in load_jsonl(args.headers):
            headers[key(d["page"], d.get("half", "L"))] = d
    cands = {}
    box_dir = None
    if args.boxes_dir:
        box_dir = args.boxes_dir
        counts_b, cands_b = load_boxes_dir(box_dir)
        counts = counts_b
        cands = cands_b
    # --counts 显式给定时覆盖（用于人工 truth 校正）
    if args.counts:
        counts = json.load(open(args.counts, encoding="utf-8"))
    if args.cands:
        for d in load_jsonl(args.cands):
            cands[(d["page"], d.get("half"))] = d.get("cands", [])

    use_body = not (args.roles and os.path.exists(args.roles))
    vols, canon_sum = load_volumes(args.volumes) if args.volumes and os.path.exists(args.volumes) else ([], 0)
    recon = []
    if args.bu_anchors and os.path.exists(args.bu_anchors):
        segs = load_bu_segments(args.volumes, args.bu_anchors, args.canonical)
        if not args.no_reconcile:
            counts, recon = reconcile_segments(seq, counts, segs)
            print("部段配平:", len(recon), "部；残差非0部数",
                  sum(1 for r in recon if r["delta"]))
    elif vols and not args.no_reconcile:
        counts, recon = reconcile_volumes(seq, counts, vols, canon.n)
        print("卷级配平:", " ".join(f"{r['vol']}/{r['juan']}:{r['raw']}->{r['canon']}({r['delta']:+d})"
                                  for r in recon if r["delta"]))
    rows = rebuild(seq, counts, body_start, force_zero_before_body=use_body)
    report = {"n_halves": len(seq), "n_entries": canon.n,
              "consumed": rows[-1][2] + rows[-1][4] if rows else 0,
              "fixes": [], "unresolved": [], "checks": 0, "mismatch": 0}
    # 分卷统计
    volstats = {}
    # 迭代纠错
    max_rounds = 0 if args.report_only else 200
    for _ in range(max_rounds):
        checks = check_all(canon, rows, headers)
        fails = [i for i, ok in enumerate(checks) if ok is False]
        report["checks"] = sum(1 for ok in checks if ok is not None)
        report["mismatch"] = len(fails)
        volstats = {}
        for i, ok in enumerate(checks):
            v = rows[i][0][:2]
            st = volstats.setdefault(v, {"halves": 0, "checks": 0, "mismatch": 0, "entries": 0})
            st["halves"] += 1
            st["entries"] += rows[i][4]
            if ok is not None:
                st["checks"] += 1
                if ok is False:
                    st["mismatch"] += 1
        report["volstats"] = volstats
        if not fails:
            break
        first = fails[0]
        edits = local_fix(canon, rows, headers, first)
        if edits is None:
            report["unresolved"].append({"seq": first, "page": rows[first][0],
                                         "half": rows[first][1],
                                         "header": headers.get(key(rows[first][0], "L")),
                                         "ci": rows[first][2]})
            break
        # 应用修正：直接改 counts 再重建
        for idx, d in edits:
            pkey, half, *_ = rows[idx]
            counts.setdefault(pkey, {})
            counts[pkey][half] = int(counts[pkey].get(half, 0) or 0) + d
        report["fixes"].append({"at_seq": first, "edits": edits})
        use_body = not (args.roles and os.path.exists(args.roles))
        # 纠错后重配平（部段/卷段），保证段总数不变
        if args.bu_anchors and os.path.exists(args.bu_anchors) and not args.no_reconcile:
            segs2 = load_bu_segments(args.volumes, args.bu_anchors, args.canonical)
            counts, _ = reconcile_segments(seq, counts, segs2)
        elif vols and not args.no_reconcile:
            counts, _ = reconcile_volumes(seq, counts, vols, canon.n)
    rows = rebuild(seq, counts, body_start, force_zero_before_body=use_body)
    # 记录修复后的书眉一致性
    checks_after = check_all(canon, rows, headers)
    report["checks_after"] = sum(1 for ok in checks_after if ok is not None)
    report["mismatch_after"] = sum(1 for ok in checks_after if ok is False)
    # 输出
    mapping = []
    checks = check_all(canon, rows, headers)
    from t1_count_v3 import is_head_v3
    def _iou(a, b):
        x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
        x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
        inter = max(0, x1 - x0) * max(0, y1 - y0)
        ua = (a[2] - a[0]) * (a[3] - a[1])
        ub = (b[2] - b[0]) * (b[3] - b[1])
        return inter / max(1, ua + ub - inter)

    def dedupe(cl):
        """重叠/包含的候选只保留面积大者（同字重复检测去重）；
        另剔除窄条碎片（w<30 且 h>45，多为版框/竖线残片）。"""
        cl = [c for c in cl if not (c.get("w", 0) < 30 and c.get("h", 0) > 45)]
        keep = []
        for x in sorted(cl, key=lambda c: -(c.get("h", 0) * c.get("w", 0))):
            if any(_iou(x["box"], y["box"]) > 0.25 for y in keep):
                continue
            keep.append(x)
        order = {id(c): i for i, c in enumerate(cl)}
        keep.sort(key=lambda c: order.get(id(c), 10 ** 9))
        return keep

    for i, (pkey, half, a, b, c, in_body) in enumerate(rows):
        ents = [canon.entries[k]["char"] for k in range(a, min(b, canon.n))]
        cl = dedupe(cands.get((pkey, half), []))
        # 有序候选：与计数同规则（v3-big）选字头；若不足 n 按 hw 补，若超出取 hw 最高 n 个
        sel = []
        for x in cl:
            sc = float((x.get("cls") or {}).get("headword", x.get("score", 0.0)))
            if is_head_v3(x, half):
                sel.append((x, sc))
        n_ents = len(ents)
        # 候选不足时：用其余候选（大字优先）按阅读序补齐，保证 n_ents 个都有框
        if len(sel) < n_ents:
            used = {id(x[0]) for x in sel}
            def _geo_ok(c):
                h = c.get("h", 0); w = c.get("w", 0)
                if 50 <= h <= 135 and 30 <= w <= 140:
                    return True
                return h <= 40 and w >= 45   # 扁平字头（一/乙/亅 类）
            rest = [(x, float((x.get("cls") or {}).get("headword", 0.0)))
                    for x in cl if id(x) not in used and _geo_ok(x)]
            rest.sort(key=lambda t: -t[1])
            sel = sel + rest[:max(0, n_ents - len(sel))]
            # 按原始阅读序（cl 顺序）恢复
            order = {id(c): i for i, c in enumerate(cl)}
            sel.sort(key=lambda t: order.get(id(t[0]), 10 ** 9))
        if len(sel) > n_ents and n_ents > 0:
            scored = sorted(range(len(sel)), key=lambda j: -sel[j][1])[:n_ents]
            keep = set(scored)
            sel = [t for j, t in enumerate(sel) if j in keep]
        assigned = []
        k = min(n_ents, len(sel))
        for j in range(k):
            assigned.append({"char": ents[j], "cand": sel[j][0], "score": sel[j][1]})
        rec = {"page": pkey, "half": half, "in_body": in_body, "ci_start": a, "ci_end": b,
               "n": len(ents), "entries": "".join(ents),
               "n_cand": len(sel), "n_cand_all": len(cl),
               "boxes": [x for x, _ in sel],
               "assigned": assigned,
               "unassigned_entries": ents[k:],
               "unassigned_cands": [x for x, _ in sel[k:]],
               "header": headers.get(key(pkey, "L")),
               "header_ok": (None if half != "L" else checks[i])}
        mapping.append(rec)
    with open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8") as f:
        for rec in mapping:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    volstats = {}
    for i, ok in enumerate(check_all(canon, rows, headers)):
        v = rows[i][0][:2]
        st = volstats.setdefault(v, {"halves": 0, "checks": 0, "mismatch": 0, "entries": 0})
        st["halves"] += 1
        st["entries"] += rows[i][4]
        if ok is not None:
            st["checks"] += 1
            if ok is False:
                st["mismatch"] += 1
    report["volstats"] = volstats
    # 卷级累计残差（卷末累计 consumed vs 正典累计）
    if vols:
        cum = 0
        jrows = []
        for o in vols:
            cum += o["entries"]
            # 找到该卷最后一个半版
            last_i = None
            for i, r in enumerate(rows):
                vol = r[0][:2]; pg = int(r[0][3:])
                if vol == o["vol"] and o["a"] <= pg <= o["b"]:
                    last_i = i
            cons = rows[last_i][2] + rows[last_i][4] if last_i is not None else None
            jrows.append({"vol": o["vol"], "juan": o["juan"], "canon_cum": cum,
                          "consumed_cum": cons,
                          "resid": (cons - cum) if cons is not None else None})
        report["juan_residuals"] = jrows
    report["reconcile"] = recon
    json.dump(report, open(os.path.join(args.out, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("n_halves", "consumed", "checks", "mismatch",
                                             "fixes", "unresolved")}, ensure_ascii=False, indent=1))


def self_test(canon, seq, noise_rate):
    """模拟：真实 counts 由 canonical 组结构驱动；注入 ±1 噪声；书眉真值来自真实窗；验证纠错。"""
    import random
    rng = random.Random(7)
    # 真实 counts：每半版随机 4-10 条，但不超过剩余
    true_counts = {}
    true_ci = []
    ci = 0
    for (vol, page, half) in seq:
        if ci >= canon.n:
            c = 0
        else:
            # 不跨部首边界（真实刻本每个部首另起一面；若跨部则该模型需改）
            rad = canon.group_of_ci(ci)[0]
            limit = ci
            while limit < canon.n and canon.group_of_ci(limit)[0] == rad:
                limit += 1
            c = min(rng.choice([3, 4, 5, 6, 7, 8, 9, 10]), limit - ci)
            if c <= 0:
                c = min(1, canon.n - ci)
        pkey = f"{vol}_{page:04d}"
        true_counts.setdefault(pkey, {})[half] = c
        true_ci.append((pkey, half, ci, ci + c))
        ci += c
    # 书眉真值：L 半版 = 该窗内组的 (部, 画数) 集合
    headers = {}
    for (pkey, half, a, b) in true_ci:
        if half != "L":
            continue
        groups = []
        for k in range(a, b):
            g = canon.group_of_ci(k)
            if not groups or groups[-1] != g:
                groups.append(g)
        if not groups:
            continue
        headers[key(pkey, "L")] = {"page": pkey, "half": "L", "bu": groups[0][0] + "部",
                                   "hua": sorted({g[1] for g in groups})}
    # 注入噪声
    bad = 0
    noisy = json.loads(json.dumps(true_counts))
    for pkey, d in noisy.items():
        for half in d:
            if rng.random() < noise_rate:
                d[half] = max(0, d[half] + rng.choice([-1, 1]))
                bad += 1
    body_start = {v: 1 for v in MAIN_VOLS}
    rows = rebuild(seq, noisy, body_start)
    checks = check_all(canon, rows, headers)
    fails0 = [i for i, ok in enumerate(checks) if ok is False]
    print(f"[self-test] 半版 {len(seq)} 注入噪声 {bad}，初始书眉不一致 {len(fails0)}")
    # 纠错
    fixes = 0
    unresolved = 0
    for _ in range(300):
        checks = check_all(canon, rows, headers)
        fails = [i for i, ok in enumerate(checks) if ok is False]
        if not fails:
            break
        first = fails[0]
        edits = local_fix(canon, rows, headers, first)
        if edits is None:
            unresolved += 1
            # 跳过该点继续（把该 half 标记为不可解）
            break
        for idx, d in edits:
            pkey, half, *_ = rows[idx]
            noisy.setdefault(pkey, {})
            noisy[pkey][half] = int(noisy[pkey].get(half, 0) or 0) + d
        fixes += 1
        rows = rebuild(seq, noisy, body_start)
    # 最终一致性 + 与真值对比
    checks = check_all(canon, rows, headers)
    fails = [i for i, ok in enumerate(checks) if ok is False]
    pos_err = sum(1 for i in range(len(seq)) if rows[i][2] != true_ci[i][2])
    print(f"[self-test] 纠错轮次 {fixes}，未解 {unresolved}，最终书眉不一致 {len(fails)}，"
          f"半版起点错位 {pos_err}/{len(seq)} ({pos_err/len(seq):.2%})")
    if fails:
        i = fails[0]
        print("[self-test] 首个残留:", rows[i][:2], "true", true_ci[i][2:], "got", rows[i][2:4],
              headers.get(key(rows[i][0], "L")))


if __name__ == "__main__":
    main()
