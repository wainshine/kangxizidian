#!/usr/bin/env python3
"""Lead · 部内计数联合拟合（DP：hua 约束 + 字头 OCR 证据 + 初值先验）。

对每个部：
  页序列 p1..pk，每页候选（去重+字头几何）带 OCR 文本；
  DP 状态 (i, k) = 前 i 页恰消耗 k 条的最小代价；页 i 放 c 条 → 窗口 [k,k+c)
  代价 = hua 不一致罚 + OCR 字匹配罚 + λ·|c − c0|
  硬约束 Σc = 部 entries。
输出 work/lead/counts_v20.jsonl（page,half,n）。
"""
import argparse, json, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_count_v3 import is_head_v3

MAXC = 28


def load_ocr():
    ocr = collections.defaultdict(list)
    for l in open(os.path.join(ROOT, "work/lead/hw_ocr.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        if "err" in r or not r.get("text"):
            continue
        ocr[(r["page"], r["half"])].append(r)
    return ocr


def half_cands(page, half):
    try:
        fj = json.load(open(os.path.join(ROOT, "work/lead/boxes300", page + ".json"),
                            encoding="utf-8"))
    except Exception:
        return []
    cl = fj["halves"][half]["cands"]
    # 与 solver 一致的清洗
    cl = [c for c in cl if not (c.get("w", 0) < 30 and c.get("h", 0) > 45)]
    keep = []
    for x in sorted(cl, key=lambda c: -(c.get("h", 0) * c.get("w", 0))):
        def iou(a, b):
            x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
            x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
            inter = max(0, x1 - x0) * max(0, y1 - y0)
            ua = (a[2] - a[0]) * (a[3] - a[1])
            ub = (b[2] - b[0]) * (b[3] - b[1])
            return inter / max(1, ua + ub - inter)
        if any(iou(x["box"], y["box"]) > 0.25 for y in keep):
            continue
        keep.append(x)
    order = {id(c): i for i, c in enumerate(cl)}
    keep.sort(key=lambda c: order.get(id(c), 10 ** 9))
    out = []
    for c in keep:
        h = c.get("h", 0); w = c.get("w", 0)
        if not ((50 <= h <= 135 and 30 <= w <= 140) or (h <= 40 and w >= 45)):
            continue
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/counts_v20.jsonl"))
    ap.add_argument("--lam", type=float, default=0.35)
    ap.add_argument("--hua_w", type=float, default=1.2)
    ap.add_argument("--ocr_w", type=float, default=0.9)
    args = ap.parse_args()
    seq = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in seq]
    bstrokes = [e["bu_strokes"] for e in seq]
    rad_of = [e["rad"] for e in seq]
    obs = {}
    for l in open(os.path.join(ROOT, "work/seq/hdr_page_obs.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        obs[r["page"]] = r
    ocr = load_ocr()
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead2.jsonl"), encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    # 初值 v5
    c0 = {}
    for l in open(os.path.join(ROOT, "work/lead/counts_v5.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        c0[(r["page"], r["half"])] = r["n"]
    out_rows = []
    # 部段
    for vol in sorted(by_vol):
        ast = sorted(by_vol[vol], key=lambda x: x["page"])
        for i, a in enumerate(ast):
            lo = a["page"]
            hi = ast[i + 1]["page"] - 1 if i + 1 < len(ast) else 10 ** 9
            pages = [p for p in sorted(roles[vol]) if lo <= p <= hi]
            if not pages:
                continue
            # 正典该部条目（按 rad 连续）
            rad = a["radical"]
            cis = [ci for ci in range(len(chars)) if rad_of[ci] == rad]
            if not cis:
                continue
            ent = len(cis)
            ci0 = cis[0]
            chars_rad = chars[ci0:ci0 + ent]
            bs_rad = bstrokes[ci0:ci0 + ent]
            # 每页候选与观测
            P = []
            for p in pages:
                page = f"{vol}_{p:04d}"
                cands = half_cands(page, "R") + half_cands(page, "L")
                texts = []
                for c in cands:
                    m = ocr.get((page, "R"), []) + ocr.get((page, "L"), [])
                    t = ""
                    best = -1
                    for o in m:
                        if tuple(int(v) for v in o["box"]) == tuple(int(v) for v in c["box"]):
                            if o["score"] > best:
                                best = o["score"]; t = o["text"]
                    texts.append((t, max(0.0, best)))
                hua = (obs.get(page) or {}).get("hua") or []
                c0p = c0.get((page, "R"), 0) + c0.get((page, "L"), 0)
                P.append({"page": page, "cands": cands, "texts": texts,
                          "hua": hua, "c0": c0p})
            n_pages = len(P)
            NEG = 1e18
            dp = np.full((n_pages + 1, ent + 1), NEG)
            bk = np.zeros((n_pages + 1, ent + 1), dtype=np.int16)
            dp[0, 0] = 0.0
            for pi in range(1, n_pages + 1):
                P0 = P[pi - 1]
                for k in range(ent + 1):
                    best = NEG; bcont = -1
                    for c in range(0, min(MAXC, ent - k) + 1):
                        kk = k + c
                        prev = dp[pi - 1][k]
                        if prev >= NEG / 2:
                            cost = prev
                        elif pi - 1 > 0:
                            continue
                        else:
                            continue
                        # hua 罚
                        if P0["hua"]:
                            allowed = set(P0["hua"]) | {max(P0["hua"]) + 1}
                            bs = bs_rad[k:kk]
                            bad = sum(1 for b in bs if b not in allowed)
                            cost += args.hua_w * bad * 0.6
                        # OCR 罚/奖
                        for j in range(min(c, len(P0["texts"]))):
                            t, s = P0["texts"][j]
                            if s < 0.5 or len(t) != 1:
                                continue
                            cc = chars_rad[k + j] if k + j < ent else ""
                            cost += (-args.ocr_w * s) if t == cc else (args.ocr_w * s * 0.5)
                        # 初值先验
                        cost += args.lam * abs(c - P0["c0"])
                        if cost < best:
                            best, bcont = cost, c
                    dp[pi][k] = best
                    bk[pi][k] = bcont
            # 回溯
            counts = [0] * n_pages
            k = ent
            ok = True
            for pi in range(n_pages, 0, -1):
                c = int(bk[pi][k])
                if c < 0:
                    ok = False
                    break
                counts[pi - 1] = c
                k -= c
            if not ok or abs(k) > 0:
                for P0 in P:
                    counts[P.index(P0)] = P0["c0"]
            # R/L 拆分：双画数用分组规则，否则按比例
            for pi, P0 in enumerate(P):
                c = counts[pi]
                page = P0["page"]
                R = c; L = 0
                if len(P0["hua"]) >= 2 and c > 0:
                    gR = P0["hua"][0]
                    # 当前 k（页起点）
                    kstart = sum(counts[:pi])
                    end = kstart
                    while end < ent and bs_rad[end] <= gR:
                        end += 1
                    R = max(0, min(c, end - kstart))
                    L = c - R
                elif c > 0:
                    R = max(0, min(c, int(round(c * 0.5))))
                    L = c - R
                # 若候选可用数限制
                availR = len(half_cands(page, "R")); availL = len(half_cands(page, "L"))
                if R > availR:
                    L += R - availR; R = availR
                if L > availL:
                    L = availL
                out_rows.append({"page": page, "half": "R", "n": R})
                out_rows.append({"page": page, "half": "L", "n": L})
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tot = sum(r["n"] for r in out_rows)
    print("pages", len(out_rows) // 2, "total", tot, "(target 42302)")


if __name__ == "__main__":
    main()
