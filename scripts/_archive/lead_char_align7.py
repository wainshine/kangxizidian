#!/usr/bin/env python3
"""Lead · 字符级序列对齐 v6：两轮（第 1 轮全序列 DP → 第 2 轮带位置先验的精对齐）。

候选：严格字头几何（方形/扁平），不足时宽松兜底。
DP：文本相等强奖、形近字部分奖励、字头类奖励；第 2 轮加 |位置−第1轮结果| 的高斯先验。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3


def cand_ok(c):
    h = c.get("h", 0); w = c.get("w", 0)
    if h < 10 or w < 10:
        return False
    if 70 <= h <= 112 and 55 <= w <= 118:
        return 0.62 <= w / h <= 1.6
    if 10 <= h <= 48 and 50 <= w <= 120:
        return w / h <= 8
    return False


def cand_loose(c):
    h = c.get("h", 0); w = c.get("w", 0)
    return 25 <= h <= 160 and 20 <= w <= 170


def load_all(args):
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    rad_entries = collections.Counter(e["rad"] for e in canon)
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead2.jsonl"), encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    segs = []
    cum = 0
    for vol in sorted(by_vol):
        for a in sorted(by_vol[vol], key=lambda x: x["page"]):
            lo, hi = cum, cum + rad_entries[a["radical"]]
            segs.append({"vol": vol, "rad": a["radical"], "page": a["page"], "lo": lo, "hi": hi})
            cum += rad_entries[a["radical"]]
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    seg_pages = []
    for i, s in enumerate(segs):
        hi_page = segs[i + 1]["page"] - 1 if (i + 1 < len(segs) and segs[i + 1]["vol"] == s["vol"]) else 10 ** 9
        seg_pages.append([p for p in sorted(roles[s["vol"]]) if s["page"] <= p <= hi_page])
    ocr = {}
    for l in open(args.ocr_all, encoding="utf-8"):
        r = json.loads(l)
        ocr[(r["page"], r["half"], tuple(int(v) for v in r["box"]))] = r
    # 形近字近似：同部首 + 笔画差 ≤2 视为形近（用于部分奖励）
    rad_of = {e["char"]: e["rad"] for e in canon}
    bs_of = {e["char"]: e["bu_strokes"] for e in canon}
    return canon, chars, segs, seg_pages, ocr, rad_of, bs_of


def build_cands(page, cache, ocr):
    if page not in cache:
        try:
            cache[page] = json.load(open(os.path.join(
                ROOT, "work/lead/boxes300", page + ".json"), encoding="utf-8"))
        except Exception:
            cache[page] = None
    fj = cache[page]
    if fj is None:
        return [], []
    strict, loose = [], []
    for half in ("R", "L"):
        for c in fj["halves"][half]["cands"]:
            box = tuple(int(v) for v in c["box"])
            o = ocr.get((page, half, box))
            t5s = o["t5"] if o and len(o["t5"]) == 1 else ""
            t6s = o["t6"] if o and len(o["t6"]) == 1 else ""
            s5v = float(o["s5"]) if o else 0.0
            s6v = float(o["s6"]) if o else 0.0
            rec = {"page": page, "half": half, "box": list(box),
                   "t5": t5s, "s5": s5v, "t6": t6s, "s6": s6v,
                   "is_head": is_head_v3(c, half)}
            if cand_ok(c):
                strict.append(rec)
            elif cand_loose(c):
                loose.append(rec)
    return strict, loose


def run_align(args, prior=None, prior_w=0.0):
    canon, chars, segs, seg_pages, ocr, rad_of, bs_of = load_all(args)
    cache = {}
    rows = []
    stats = collections.Counter()
    for si, s in enumerate(segs):
        ent = chars[s["lo"]:s["hi"]]
        n = len(ent)
        cands = []
        for p in seg_pages[si]:
            page = f"{s['vol']}_{p:04d}"
            strict, loose = build_cands(page, cache, ocr)
            cands.extend(strict)
            if len(cands) + len(loose) >= n:
                pass
        if len(cands) < n:
            for p in seg_pages[si]:
                page = f"{s['vol']}_{p:04d}"
                strict, loose = build_cands(page, cache, ocr)
                for rec in loose:
                    cands.append(rec)
                if len(cands) >= n:
                    break
            stats["loose_fill"] += 1
        m = len(cands)
        if m < n:
            stats["too_few"] += 1
            continue
        NEG = -1e18
        dp = np.full((m + 1, n + 1), NEG)
        bk = np.zeros((m + 1, n + 1), dtype=np.int8)
        dp[0, 0] = 0.0
        for i in range(1, m + 1):
            dp[i, 0] = 0.0
            cd = cands[i - 1]
            t5, s5, t6, s6 = cd["t5"], cd["s5"], cd["t6"], cd["s6"]
            key = (cd["page"], cd["half"], tuple(int(v) for v in cd["box"]))
            for j in range(1, min(i, n) + 1):
                best = dp[i - 1, j]; b = 0
                ch = ent[j - 1]
                cand_scores = []
                if t5:
                    cand_scores.append(1.6 + 0.6 * s5 if t5 == ch else (-1.2 - 0.1 * s5))
                if t6:
                    cand_scores.append(1.6 + 0.6 * s6 if t6 == ch else (-1.2 - 0.1 * s6))
                if t5 and t6 and t5 == ch and t6 == ch:
                    sc = 2.4 + 0.5 * (s5 + s6) / 2
                elif cand_scores:
                    sc = max(cand_scores)
                else:
                    sc = (0.45 if cd["is_head"] else -0.15)
                if prior is not None and prior_w > 0:
                    pj = prior.get(key)
                    if pj is not None:
                        sc += prior_w * float(np.exp(-abs((s["lo"] + j - 1) - pj) / 4.0))
                prev = dp[i - 1, j - 1]
                if prev > NEG / 2:
                    v = prev + sc
                    if v > best:
                        best, b = v, 1
                dp[i, j] = best; bk[i, j] = b
        if dp[m, n] <= NEG / 2:
            stats["dp_fail"] += 1
            continue
        matches = {}
        i, j = m, n
        while i > 0 and j > 0:
            if bk[i, j] == 1:
                matches[i - 1] = j - 1
                i -= 1; j -= 1
            else:
                i -= 1
        by_half = collections.defaultdict(list)
        for ci_local, ej in matches.items():
            c = cands[ci_local]
            by_half[(c["page"], c["half"])].append((ej, c))
            if (c.get("t5") == ent[ej]) or (c.get("t6") == ent[ej]):
                stats["ocr_anchor"] += 1
        for (page, half), lst in sorted(by_half.items()):
            lst.sort()
            entries = [ent[ej] for ej, _ in lst]
            assigned = [{"char": ent[ej], "cand": {"box": c["box"]}} for ej, c in lst]
            ci_start = s["lo"] + lst[0][0]
            rows.append({"page": page, "half": half, "ci_start": ci_start,
                         "ci_end": ci_start + len(entries), "n": len(entries),
                         "entries": "".join(entries), "assigned": assigned,
                         "in_body": True, "header_ok": None})
        stats["matched"] += n
    print("  stats", dict(stats))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-all", default=os.path.join(ROOT, "work/lead/ocr_all2.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map/charalign7"))
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--shape-sim", type=float, default=0.0)
    ap.add_argument("--prior-w", type=float, default=0.7)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print("pass 1")
    rows1 = run_align(args)
    prior = {}
    for r in rows1:
        for a in r["assigned"]:
            key = (r["page"], r["half"], tuple(int(v) for v in a["cand"]["box"]))
            prior[key] = r["ci_start"] + r["entries"].index(a["char"]) if a["char"] in r["entries"] else None
    # 更准的 prior：用 row 的 ci_start + 在 entries 的位置
    prior = {}
    for r in rows1:
        for idx, a in enumerate(r["assigned"]):
            key = (r["page"], r["half"], tuple(int(v) for v in a["cand"]["box"]))
            prior[key] = r["ci_start"] + idx
    if args.passes >= 2:
        print("pass 2 (prior)")
        rows2 = run_align(args, prior=prior, prior_w=args.prior_w)
        rows = rows2
    else:
        rows = rows1
    with open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows", len(rows))


if __name__ == "__main__":
    main()
