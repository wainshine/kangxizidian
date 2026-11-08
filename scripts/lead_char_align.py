#!/usr/bin/env python3
"""Lead · 字符级序列对齐：书页候选（按阅读序，带 OCR 文本）× 部内正典条目。

每部：主序列 = 各页候选（清洗后，R→L 阅读序）；目标 = 该部正典 chars（n 条）。
DP：dp[i][j] = 用前 i 个候选匹配前 j 条目标的最大分。
  - 跳过候选：0
  - 匹配：OCR 文本非空且相等 +2.0；非空不等 −1.0；空文本 +0.15
终态必须 j=n（所有条目都落位）。
输出 work/map/charalign/mapping.jsonl（solver 同格式：page,half,ci_start,entries,assigned）
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lead_anchor2 import clean_cands

MATCH_EQ = 2.0
MATCH_NE = -1.0
MATCH_EMPTY = 0.15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", default=os.path.join(ROOT, "work/lead/hw_ocr_v6.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map/charalign"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
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
    ocr = collections.defaultdict(list)
    for l in open(args.ocr, encoding="utf-8"):
        r = json.loads(l)
        if "err" in r or not r.get("text"):
            continue
        ocr[(r["page"], r["half"])].append(r)
    seg_pages = []
    for i, s in enumerate(segs):
        hi_page = segs[i + 1]["page"] - 1 if (i + 1 < len(segs) and segs[i + 1]["vol"] == s["vol"]) else 10 ** 9
        seg_pages.append([p for p in sorted(roles[s["vol"]]) if s["page"] <= p <= hi_page])
    out_rows = []
    stats = collections.Counter()
    for si, s in enumerate(segs):
        ent = chars[s["lo"]:s["hi"]]
        n = len(ent)
        # 候选序列
        cands = []
        for p in seg_pages[si]:
            page = f"{s['vol']}_{p:04d}"
            try:
                fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300", page + ".json"),
                                    encoding="utf-8"))
            except Exception:
                continue
            for half in ("R", "L"):
                sel = clean_cands(fj["halves"][half]["cands"])
                obss = {tuple(int(v) for v in o["box"]): o for o in ocr.get((page, half), [])}
                for c in sel:
                    o = obss.get(tuple(int(v) for v in c["box"]))
                    txt = o["text"] if o and len(o.get("text", "")) == 1 and o["score"] >= 0.75 else ""
                    cands.append({"page": page, "half": half, "box": c["box"], "text": txt,
                                  "score": (o["score"] if o else 0.0)})
        m = len(cands)
        if m < n:
            stats["too_few_cands"] += 1
            continue
        # DP
        NEG = -1e18
        dp = np.full((m + 1, n + 1), NEG, dtype=np.float32)
        bk = np.zeros((m + 1, n + 1), dtype=np.int8)  # 0=skip cand, 1=match
        dp[0, 0] = 0.0
        for i in range(1, m + 1):
            dp[i, 0] = 0.0
            for j in range(1, min(i, n) + 1):
                best = dp[i - 1, j]  # skip candidate
                b = 0
                t = cands[i - 1]["text"]
                sc = MATCH_EQ if (t and t == ent[j - 1]) else (MATCH_EMPTY if not t else MATCH_NE)
                prev = dp[i - 1, j - 1]
                if prev > NEG / 2:
                    v = prev + sc
                    if v > best:
                        best, b = v, 1
                dp[i, j] = best
                bk[i, j] = b
        if dp[m, n] <= NEG / 2:
            stats["dp_fail"] += 1
            continue
        # 回溯
        matches = {}
        i, j = m, n
        while i > 0 and j > 0:
            if bk[i, j] == 1:
                matches[i - 1] = j - 1
                i -= 1; j -= 1
            else:
                i -= 1
        # 组行：每 (page,half) 的 entries 与 assigned
        by_half = collections.defaultdict(list)
        for ci_local, ej in matches.items():
            c = cands[ci_local]
            by_half[(c["page"], c["half"])].append((ej, c))
        import collections as C
        for (page, half), lst in sorted(by_half.items()):
            lst.sort()
            entries = [ent[ej] for ej, _ in lst]
            assigned = [{"char": ent[ej], "cand": {"box": c["box"]}} for ej, c in lst]
            ci_start = s["lo"] + lst[0][0]
            out_rows.append({"page": page, "half": half, "ci_start": ci_start,
                             "ci_end": ci_start + len(entries),
                             "n": len(entries), "entries": "".join(entries),
                             "assigned": assigned, "in_body": True,
                             "header_ok": None})
            stats["matched"] += len(entries)
    with open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("segments", len(segs), "rows", len(out_rows), "matched", stats["matched"],
          "too_few", stats["too_few_cands"], "dp_fail", stats["dp_fail"])


if __name__ == "__main__":
    main()
