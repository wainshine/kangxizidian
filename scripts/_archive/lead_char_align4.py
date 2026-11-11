#!/usr/bin/env python3
"""Lead · 字符级序列对齐 v4：严格字头几何 + 全量双模型 OCR + 停用词过滤。

候选过滤器（严格）：
  - 方形字头：70≤h≤112, 55≤w≤118, 0.62≤w/h≤1.6
  - 扁平字头：10≤h≤48, 50≤w≤120, w/h≤8
  - 排除版心/扉页词（OCR 单字命中的 康熙字典子集上中下部畫 等，且位于页面边缘带）
DP 同 v2/v3：文本相等强奖、字头类奖励、位置先验。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3

# 版心/扉页常见单字（只有当候选位于页面左右边缘带时才过滤）
TITLE_CHARS = set("康熙字典子集上中下丑寅卯辰巳午未申酉戌亥部畫元亨利贞")


def cand_loose(c):
    h = c.get("h", 0); w = c.get("w", 0)
    return h >= 25 and w >= 20 and h <= 160 and w <= 170


def cand_ok(c):
    h = c.get("h", 0); w = c.get("w", 0)
    if h < 10 or w < 10:
        return False
    if 70 <= h <= 112 and 55 <= w <= 118:
        return 0.62 <= w / h <= 1.6
    if 10 <= h <= 48 and 50 <= w <= 120:
        return w / h <= 8
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-all", default=os.path.join(ROOT, "work/lead/ocr_all2.jsonl"))
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/v17"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map/charalign4"))
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
    ocr = {}
    for l in open(args.ocr_all, encoding="utf-8"):
        r = json.loads(l)
        ocr[(r["page"], r["half"], tuple(int(v) for v in r["box"]))] = r
    ref = collections.defaultdict(dict)
    for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        ref[r["page"]][r["half"]] = r
    out_rows = []
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
                rref = ref.get(page, {}).get(half)
                for c in fj["halves"][half]["cands"]:
                    if not cand_ok(c):
                        if cand_loose(c):
                            loose.append((page, half, c))
                        continue
                    box = tuple(int(v) for v in c["box"])
                    o = ocr.get((page, half, box))
                    text = ""; conf = 0.0
                    if o:
                        t5, s5, t6, s6 = o["t5"], o["s5"], o["t6"], o["s6"]
                        if len(t6) == 1 and len(t5) == 1 and t5 == t6:
                            text, conf = t6, 1.2 + 0.6 * (s5 + s6) / 2
                        elif len(t6) == 1 and s6 >= 0.85:
                            text, conf = t6, 0.75 + 0.4 * s6
                        elif len(t5) == 1 and s5 >= 0.85:
                            text, conf = t5, 0.6 + 0.4 * s5
                    pred_ci = None
                    if rref:
                        pred_ci = rref["ci_start"] + len(rref.get("entries", "")) // 2
                    cands.append({"page": page, "half": half, "box": list(box),
                                  "text": text, "conf": conf, "is_head": is_head_v3(c, half),
                                  "pred": pred_ci})
        # 嵌套去重：被更大候选包含 ≥85% 面积的丢弃（检测器会把字头组件再报一次）
        def contained(a, b):
            ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
            ix = max(0, min(ax1, bx1) - max(ax0, bx0))
            iy = max(0, min(ay1, by1) - max(ay0, by0))
            inter = ix * iy
            area = max(1, (ax1 - ax0) * (ay1 - ay0))
            return inter / area >= 0.85 and (ax1 - ax0) * (ay1 - ay0) < 0.9 * (bx1 - bx0) * (by1 - by0)
        cands.sort(key=lambda cd: -((cd["box"][2] - cd["box"][0]) * (cd["box"][3] - cd["box"][1])))
        kept = []
        for cd in cands:
            if any(contained(cd["box"], k["box"]) for k in kept):
                continue
            kept.append(cd)
        kept.sort(key=lambda cd: (cd["page"], cd["half"], cd["box"][1]))
        cands = kept
        # 恢复阅读序：按 (page,half) 分组 → 列聚类（x 中心相近）→ 列从右到左、列内从上到下
        ordered = []
        for (pg, hf) in sorted(set((cd["page"], cd["half"]) for cd in cands),
                               key=lambda t: (t[0], 0 if t[1] == "R" else 1)):
            group = [cd for cd in cands if cd["page"] == pg and cd["half"] == hf]
            cols = []
            for cd in sorted(group, key=lambda z: (z["box"][0] + z["box"][2]) / 2):
                xc = (cd["box"][0] + cd["box"][2]) / 2
                w = cd["box"][2] - cd["box"][0]
                placed = False
                for col in cols:
                    if abs(xc - col["xc"]) < 0.55 * max(w, col["w"]):
                        col["items"].append(cd)
                        col["xc"] = (col["xc"] * (len(col["items"]) - 1) + xc) / len(col["items"])
                        col["w"] = max(col["w"], w)
                        placed = True
                        break
                if not placed:
                    cols.append({"xc": xc, "w": w, "items": [cd]})
            cols.sort(key=lambda col: -col["xc"])
            for col in cols:
                ordered.extend(sorted(col["items"], key=lambda z: z["box"][1]))
        cands = ordered
        if len(cands) < n:
            for (page, half, c) in loose:
                box = tuple(int(v) for v in c["box"])
                o = ocr.get((page, half, box))
                text = ""; conf = 0.0
                if o:
                    t5, s5, t6, s6 = o["t5"], o["s5"], o["t6"], o["s6"]
                    if len(t6) == 1 and len(t5) == 1 and t5 == t6:
                        text, conf = t6, 1.2 + 0.6 * (s5 + s6) / 2
                    elif len(t6) == 1 and s6 >= 0.85:
                        text, conf = t6, 0.75 + 0.4 * s6
                    elif len(t5) == 1 and s5 >= 0.85:
                        text, conf = t5, 0.6 + 0.4 * s5
                cands.append({"page": page, "half": half, "box": list(box),
                              "text": text, "conf": conf, "is_head": is_head_v3(c, half),
                              "pred": None})
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
            t = cd["text"]; conf = cd["conf"]
            for j in range(1, min(i, n) + 1):
                best = dp[i - 1, j]; b = 0
                if t:
                    sc = (1.8 + conf) if t == ent[j - 1] else (-1.5 - 0.2 * conf)
                else:
                    sc = (0.35 if cd["is_head"] else -0.1)
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
