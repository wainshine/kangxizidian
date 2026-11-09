#!/usr/bin/env python3
"""Lead · 字符级序列对齐 v16：在 v14 基础上加「字头判别」候选过滤。

新增过滤（回应审计 0007L 类误指派）：
  - ink_frac ≥ 0.17（注文合并框 ~0.12 被剔除）
  - p90 笔画宽 ≥ 4.0（注文框 ~2.8 被剔除）
  - 扁平字头：h≥22 且 y0≥6（剔除页顶 19px 碎片）
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-all", default=os.path.join(ROOT, "work/lead/ocr_all5.jsonl"))
    ap.add_argument("--stats", default=os.path.join(ROOT, "work/lead/cand_stats.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map/charalign16"))
    ap.add_argument("--ink-min", type=float, default=0.17)
    ap.add_argument("--p90-min", type=float, default=4.0)
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
            segs.append({"vol": vol, "rad": a["radical"], "page": a["page"], "lo": cum,
                         "hi": cum + rad_entries[a["radical"]]})
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
    stats = {}
    for l in open(args.stats, encoding="utf-8"):
        r = json.loads(l)
        stats[(r["page"], r["half"], tuple(int(v) for v in r["box"]))] = r

    def ok(c, page, half, box):
        st = stats.get((page, half, box))
        if st is None:
            return False
        h = c.get("h", 0); w = c.get("w", 0)
        # 剔除「注文合并框」：笔画细 + 墨量低（实测 headword p90>=5、ink>=0.2）
        if st["p90"] < args.p90_min and st["ink"] < args.ink_min:
            return False
        if 70 <= h <= 112 and 55 <= w <= 118 and 0.62 <= w / max(1, h) <= 1.6:
            return True
        # 扁平字头：排除页顶碎片
        return (22 <= h <= 48 and 50 <= w <= 120 and w / max(1, h) <= 8 and st["y0"] >= 6)

    rows = []
    stats_c = collections.Counter()
    cache = {}
    for si, s in enumerate(segs):
        ent = chars[s["lo"]:s["hi"]]
        n = len(ent)
        cands = []
        extras = []
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
                    if not ok(c, page, half, box):
                        h0 = c.get("h", 0); w0 = c.get("w", 0)
                        if ((70 <= h0 <= 112 and 55 <= w0 <= 118 and 0.62 <= w0 / max(1, h0) <= 1.6)
                                or (22 <= h0 <= 48 and 50 <= w0 <= 120 and w0 / max(1, h0) <= 8)):
                            extras.append((page, half, c, box))
                        continue
                    o = ocr.get((page, half, box), {})
                    ev = []
                    for tk, sk in (("t5", "s5"), ("t6", "s6"), ("t5e", "s5e"), ("t6e", "s6e"),
                                   ("t5e2", "s5e2"), ("t6e2", "s6e2"), ("t5e3", "s5e3"), ("t6e3", "s6e3")):
                        t = o.get(tk, "") or ""
                        if len(t) == 1:
                            ev.append((t, float(o.get(sk, 0.0) or 0.0)))
                    st = stats[(page, half, box)]
                    strong = 1.0 if (st["p90"] >= 4.0 and st["ink"] >= 0.17) else 0.0
                    cands.append({"page": page, "half": half, "box": list(box), "ev": ev,
                                  "strong": strong, "is_head": is_head_v3(c, half)})
        if len(cands) < n:
            stats_c["weak_fallback"] += 1
            for page, half, c, box in extras:
                o = ocr.get((page, half, box), {})
                ev = []
                for tk, sk in (("t5", "s5"), ("t6", "s6"), ("t5e", "s5e"), ("t6e", "s6e"),
                               ("t5e2", "s5e2"), ("t6e2", "s6e2"), ("t5e3", "s5e3"), ("t6e3", "s6e3")):
                    t = o.get(tk, "") or ""
                    if len(t) == 1:
                        ev.append((t, float(o.get(sk, 0.0) or 0.0)))
                st = stats.get((page, half, box))
                cands.append({"page": page, "half": half, "box": list(box), "ev": ev,
                              "strong": 0.0, "is_head": is_head_v3(c, half)})
        m = len(cands)
        if m < n:
            stats_c["too_few"] += 1
            continue
        NEG = -1e18
        dp = np.full((m + 1, n + 1), NEG)
        bk = np.zeros((m + 1, n + 1), dtype=np.int8)
        dp[0, 0] = 0.0
        for i in range(1, m + 1):
            dp[i, 0] = 0.0
            cd = cands[i - 1]
            ev = cd["ev"]
            for j in range(1, min(i, n) + 1):
                best = dp[i - 1, j]; b = 0
                ch = ent[j - 1]
                hits = [(1.6 + 0.6 * sc) for t, sc in ev if t == ch]
                if hits:
                    sc_ = max(hits) + 0.2 * (len(hits) - 1) + 0.5 * cd.get("strong", 0.0)
                elif ev:
                    sc_ = max(-(1.2 + 0.1 * sc) for t, sc in ev) + 0.5 * cd.get("strong", 0.0)
                else:
                    sc_ = (0.45 * cd.get("strong", 0.0) - 0.25 * (1 - cd.get("strong", 0.0))) \
                        if cd["is_head"] else (-0.15 + 0.3 * cd.get("strong", 0.0))
                prev = dp[i - 1, j - 1]
                if prev > NEG / 2:
                    v = prev + sc_
                    if v > best:
                        best, b = v, 1
                dp[i, j] = best; bk[i, j] = b
        if dp[m, n] <= NEG / 2:
            stats_c["dp_fail"] += 1
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
                stats_c["ocr_anchor"] += 1
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
        stats_c["matched"] += n
    with open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows", len(rows), dict(stats_c))


if __name__ == "__main__":
    main()
