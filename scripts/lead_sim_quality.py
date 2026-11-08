#!/usr/bin/env python3
"""Lead · 检测器质量 → 标注正确率 可行性仿真（决定 detector v2 验收门）。

模型：
- 真实：每半版条数 ~ N(6,3) 截断，不跨部首；组大小来自 canonical。
- detector：每半版输出有序候选；真字头有 fn_rate 概率漏检，另有 fp_rate×n 个 FP 候选；
  真字头分数 ~N(0.88,0.10)，FP 分数 ~N(0.45,0.20)（截断 0..1）。
- 求解：分数阈值初判 → 全局顺序配对 → 书眉不一致处局部修补（在窗口内增/删候选）。
- 指标：真字头的标签正确率；未解严重度（第一个不可修位置）。
"""
import json, os, sys, random, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lead_solver import ROOT, MAIN_VOLS, build_sequence, Canon


def make_truth(canon, seq, rng, mean=6.0, sd=3.0):
    counts, spans = {}, []
    ci = 0
    for (vol, page, half) in seq:
        if ci >= canon.n:
            n = 0
        else:
            rad = canon.group_of_ci(ci)[0]
            limit = ci
            while limit < canon.n and canon.group_of_ci(limit)[0] == rad:
                limit += 1
            n = min(limit - ci, max(0, int(rng.gauss(mean, sd))))
        pkey = f"{vol}_{page:04d}"
        counts.setdefault(pkey, {})[half] = n
        spans.append((pkey, half, ci, ci + n))
        ci += n
    return counts, spans


def gen_headers(canon, spans):
    headers = {}
    for (pkey, half, a, b) in spans:
        if half != "L" or b == a:
            continue
        groups = []
        for k in range(a, b):
            g = canon.group_of_ci(k)
            if not groups or groups[-1] != g:
                groups.append(g)
        headers[f"{pkey}:L"] = {"bu": groups[0][0],
                                "hua": sorted({g[1] for g in groups})}
    return headers


def gen_detector(canon, spans, rng, fp_rate=0.10, fn_rate=0.01):
    """返回 det[(pkey,half)] = [ {'score', 'ci'} ]，按阅读顺序（FP 的 ci=None 随机插位）。"""
    det = {}
    for (pkey, half, a, b) in spans:
        items = []
        for k in range(a, b):
            if rng.random() < fn_rate:
                continue
            items.append({"score": min(0.999, max(0.001, rng.gauss(0.88, 0.10))),
                          "ci": k, "true": True, "pos": rng.random()})
        n = b - a
        n_fp = sum(1 for _ in range(max(1, n)) if rng.random() < fp_rate)
        for _ in range(n_fp):
            items.append({"score": min(0.99, max(0.001, rng.gauss(0.45, 0.20))),
                          "ci": None, "true": False, "pos": rng.random()})
        items.sort(key=lambda x: x["pos"])
        det[(pkey, half)] = items
    return det


def solve(canon, seq, det, headers, thr=0.6, window=8, max_rounds=3000):
    """顺序配对 + 书眉不一致处爬山修补。

    操作：删除窗口内某半版的一个 kept 候选（优先低分）/ 加入一个 reserve 候选（优先高分）。
    接受准则：书眉不一致总数下降（hill climbing），直到 0。
    """
    halves = []
    for (vol, page, half) in seq:
        pkey = f"{vol}_{page:04d}"
        items = det.get((pkey, half), [])
        kept = [x for x in items if x["score"] >= thr]
        reserve = [x for x in items if x["score"] < thr]
        halves.append({"pkey": pkey, "half": half, "kept": kept, "reserve": reserve,
                       "ci": 0})

    def recompute():
        ci = 0
        for h in halves:
            h["ci"] = ci
            ci += len(h["kept"])

    def bad_list():
        bad = []
        for i, h in enumerate(halves):
            if h["half"] != "L":
                continue
            hdr = headers.get(f"{h['pkey']}:L")
            if not hdr or not h["kept"]:
                continue
            allowed = {(hdr["bu"], x) for x in hdr["hua"]}
            used = {canon.group_of_ci(k) for k in range(h["ci"], h["ci"] + len(h["kept"]))}
            if not used <= allowed:
                bad.append(i)
        return bad

    recompute()
    repairs = 0
    for _ in range(max_rounds):
        bad = bad_list()
        if not bad:
            return halves, {"solved": True, "repairs": repairs}
        nbad = len(bad)
        first = bad[0]
        lo = max(0, first - window)
        best = None  # (nbad_after, op, idx, cand)
        for idx in range(lo, first + 1):
            h = halves[idx]
            # 删除：窗口内最低分
            for j, c in enumerate(sorted(h["kept"], key=lambda x: x["score"])[:2]):
                old = h["kept"]
                h["kept"] = [x for x in old if x is not c]
                recompute()
                nb = len(bad_list())
                if nb < nbad and (best is None or nb < best[0]):
                    best = (nb, "del", idx, c)
                h["kept"] = old
                recompute()
            # 加入：窗口内 reserve 最高分
            for c in sorted(h["reserve"], key=lambda x: -x["score"])[:2]:
                old = h["reserve"]
                h["reserve"] = [x for x in old if x is not c]
                h["kept"] = h["kept"] + [c]
                recompute()
                nb = len(bad_list())
                if nb < nbad and (best is None or nb < best[0]):
                    best = (nb, "add", idx, c)
                h["kept"] = [x for x in h["kept"] if x is not c]
                h["reserve"] = old
                recompute()
        if best is None:
            return halves, {"solved": False, "repairs": repairs, "stuck_at": first,
                            "page": halves[first]["pkey"], "half": halves[first]["half"],
                            "nbad": nbad}
        nb, op, idx, c = best
        h = halves[idx]
        if op == "del":
            h["kept"] = [x for x in h["kept"] if x is not c]
        else:
            h["reserve"] = [x for x in h["reserve"] if x is not c]
            h["kept"] = h["kept"] + [c]
        repairs += 1
        recompute()
    return halves, {"solved": False, "repairs": repairs, "timeout": True}


def score(canon, halves):
    total = correct = 0
    for h in halves:
        for k, c in enumerate(h["kept"]):
            if not c["true"]:
                continue
            total += 1
            if h["ci"] + k == c["ci"]:
                correct += 1
    return correct, total


def main():
    canon = Canon(os.path.join(ROOT, "work/lead/canonical_proto.jsonl"),
                  os.path.join(ROOT, "work/lead/groups_proto.json"))
    seq = build_sequence(MAIN_VOLS, first_page=6)[:400]
    print(f"canonical {canon.n}  groups {len(canon.groups)}  halves {len(seq)}")
    for fp in [0.05, 0.10, 0.20, 0.35]:
        for fn in [0.0, 0.005, 0.02]:
            rows = []
            for seed in [1, 2, 3]:
                rng = random.Random(seed * 1000 + int(fp * 100) + int(fn * 1000))
                _, spans = make_truth(canon, seq, rng)
                headers = gen_headers(canon, spans)
                det = gen_detector(canon, spans, rng, fp_rate=fp, fn_rate=fn)
                halves, rep = solve(canon, seq, det, headers)
                correct, total = score(canon, halves)
                rows.append((correct / max(1, total), total - correct, rep))
            acc = statistics.mean(r[0] for r in rows)
            miss = statistics.mean(r[1] for r in rows)
            solved = sum(1 for r in rows if r[2]["solved"])
            print(f"FP={fp:.2f} FN={fn:.3f}: 标注正确率={acc:.4%} 错标均={miss:.1f} "
                  f"解出={solved}/3")


if __name__ == "__main__":
    main()
