#!/usr/bin/env python3
"""Lead · 字符级序列对齐 v2：双 OCR 模型 + 字头类奖励 + 位置先验。

改进点（相对 v1）：
1. 候选文本取 PP-OCRv5/v6 双模型共识：一致 → 强锚；只一个 → 中锚；冲突 → 取高分并降权。
2. 匹配分：文本相等强奖 + 字头类(is_head_v3)奖励；空文本按字头类给弱正分。
3. 位置先验：用当前映射（v17）累计位置作参考，匹配偏离大时轻微惩罚。

输出 work/map/charalign2/mapping.jsonl（solver 同格式）。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lead_anchor2 import clean_cands
from t1_count_v3 import is_head_v3


def load_unified(path):
    out = {}
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        key = (r["page"], r["half"], tuple(int(v) for v in r["box"]))
        out[key] = (r.get("t5", ""), float(r.get("s5") or 0.0),
                    r.get("t6", ""), float(r.get("s6") or 0.0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-all", default=os.path.join(ROOT, "work/lead/ocr_all.jsonl"))
    ap.add_argument("--refmap", default=os.path.join(ROOT, "work/map/v17"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map/charalign3"))
    ap.add_argument("--pos-penalty", type=float, default=0.02)
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
    seg_pages = []
    for i, s in enumerate(segs):
        hi_page = segs[i + 1]["page"] - 1 if (i + 1 < len(segs) and segs[i + 1]["vol"] == s["vol"]) else 10 ** 9
        seg_pages.append([p for p in sorted(roles[s["vol"]]) if s["page"] <= p <= hi_page])
    ocr_all = load_unified(args.ocr_all)
    # 参考映射：预测位置
    ref = collections.defaultdict(dict)
    for l in open(os.path.join(args.refmap, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        ref[r["page"]][r["half"]] = r
    out_rows = []
    stats = collections.Counter()
    for si, s in enumerate(segs):
        ent = chars[s["lo"]:s["hi"]]
        n = len(ent)
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
                rref = ref.get(page, {}).get(half)
                for jj, c in enumerate(sel):
                    box = tuple(int(v) for v in c["box"])
                    t5, s5, t6, s6 = ocr_all.get((page, half, box), ("", 0.0, "", 0.0))
                    text = ""; conf = 0.0
                    if len(t6) == 1 and len(t5) == 1 and t5 == t6:
                        text, conf = t6, 1.2 + 0.6 * (s5 + s6) / 2
                    elif len(t6) == 1 and s6 >= 0.85:
                        text, conf = t6, 0.7 + 0.4 * s6
                    elif len(t5) == 1 and s5 >= 0.9:
                        text, conf = t5, 0.5 + 0.4 * s5
                    elif len(t6) == 1:
                        text, conf = t6, 0.45 + 0.2 * s6
                    pred_ci = None
                    if rref and jj < len(rref.get("entries", "")):
                        pred_ci = rref["ci_start"] + jj
                    cands.append({"page": page, "half": half, "box": c["box"],
                                  "text": text, "conf": conf,
                                  "is_head": is_head_v3(c, half), "pred": pred_ci})
        m = len(cands)
        if m < n:
            stats["too_few"] += 1
            continue
        # DP
        NEG = -1e18
        dp = np.full((m + 1, n + 1), NEG, dtype=np.float64)
        bk = np.zeros((m + 1, n + 1), dtype=np.int8)
        dp[0, 0] = 0.0
        for i in range(1, m + 1):
            dp[i, 0] = 0.0
            cd = cands[i - 1]
            t = cd["text"]; conf = cd["conf"]
            for j in range(1, min(i, n) + 1):
                best = dp[i - 1, j]; b = 0
                if t:
                    sc = (1.8 + conf) if t == ent[j - 1] else (-1.4 - 0.2 * conf)
                else:
                    sc = (0.4 if cd["is_head"] else -0.05)
                if cd["pred"] is not None:
                    sc -= args.pos_penalty * min(40, abs((s["lo"] + j - 1) - cd["pred"]))
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
            if c["text"] and c["text"] == ent[ej]:
                stats["ocr_anchor"] += 1
        for (page, half), lst in sorted(by_half.items()):
            lst.sort()
            entries = [ent[ej] for ej, _ in lst]
            assigned = [{"char": ent[ej], "cand": {"box": c["box"]}} for ej, c in lst]
            ci_start = s["lo"] + lst[0][0]
            out_rows.append({"page": page, "half": half, "ci_start": ci_start,
                             "ci_end": ci_start + len(entries), "n": len(entries),
                             "entries": "".join(entries), "assigned": assigned,
                             "in_body": True, "header_ok": None})
        stats["matched"] += n
    with open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows", len(out_rows), dict(stats))


if __name__ == "__main__":
    main()
