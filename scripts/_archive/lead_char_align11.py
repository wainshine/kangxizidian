#!/usr/bin/env python3
"""Lead · 字符级序列对齐 v9：四路 OCR 证据（v5/v6 + 增强 v5e/v6e）+ 共识加成。"""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-all", default=os.path.join(ROOT, "work/lead/ocr_all4.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map/charalign11"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    rad_entries = collections.Counter(e["rad"] for e in canon)
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead3.jsonl"), encoding="utf-8")]
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
    rows = []
    stats = collections.Counter()
    cache = {}
    for si, s in enumerate(segs):
        ent = chars[s["lo"]:s["hi"]]
        n = len(ent)
        cands = []
        loose = []
        for p in seg_pages[si]:
            page = f"{s['vol']}_{p:04d}"
            if page not in cache:
                try:
                    cache[page] = json.load(open(os.path.join(
                        ROOT, "work/lead/boxes300", page + ".json"), encoding="utf-8"))
                except Exception:
                    cache[page] = None
            fj = cache[page]
            if fj is None:
                continue
            for half in ("R", "L"):
                for c in fj["halves"][half]["cands"]:
                    box = tuple(int(v) for v in c["box"])
                    o = ocr.get((page, half, box), {})
                    ev = []
                    for tk, sk in (("t5", "s5"), ("t6", "s6"), ("t5e", "s5e"), ("t6e", "s6e"),
                                   ("t5e2", "s5e2"), ("t6e2", "s6e2")):
                        t = o.get(tk, "") or ""
                        if len(t) == 1:
                            ev.append((t, float(o.get(sk, 0.0) or 0.0)))
                    rec = {"page": page, "half": half, "box": list(box), "ev": ev,
                           "is_head": is_head_v3(c, half)}
                    if cand_ok(c):
                        cands.append(rec)
                    elif cand_loose(c):
                        loose.append(rec)
        if len(cands) < n:
            cands.extend(loose)
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
            ev = cd["ev"]
            best_hit = None
            n_hits = 0
            worst = None
            for t, sc in ev:
                if t == ent[0]:  # 无需预判，逐 j 计算
                    pass
            for j in range(1, min(i, n) + 1):
                best = dp[i - 1, j]; b = 0
                ch = ent[j - 1]
                hits = [(1.6 + 0.6 * sc) for t, sc in ev if t == ch]
                if hits:
                    sc_ = max(hits) + 0.2 * (len(hits) - 1)
                elif ev:
                    sc_ = max(-(1.2 + 0.1 * sc) for t, sc in ev)
                else:
                    sc_ = 0.45 if cd["is_head"] else -0.15
                prev = dp[i - 1, j - 1]
                if prev > NEG / 2:
                    v = prev + sc_
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
            if any(t == ent[ej] for t, sc in c["ev"]):
                stats["ocr_anchor"] += 1
        for (page, half), lst in sorted(by_half.items()):
            lst.sort()
            entries = [ent[ej] for ej, _ in lst]
            assigned = []
            for ej, c in lst:
                hit_scores = [sc for t, sc in c["ev"] if t == ent[ej]]
                assigned.append({"char": ent[ej], "cand": {"box": c["box"]},
                                 "ocr_ok": bool(hit_scores),
                                 "ocr_score": max(hit_scores) if hit_scores else 0.0,
                                 "ev": c["ev"]})
            ci_start = s["lo"] + lst[0][0]
            rows.append({"page": page, "half": half, "ci_start": ci_start,
                         "ci_end": ci_start + len(entries), "n": len(entries),
                         "entries": "".join(entries), "assigned": assigned,
                         "in_body": True, "header_ok": None})
        stats["matched"] += n
    with open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows", len(rows), dict(stats))


if __name__ == "__main__":
    main()
