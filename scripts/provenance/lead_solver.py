#!/usr/bin/env python3
"""Lead · v3 映射求解器（结构标注核心）。

思想（docs/_history/TAKEOVER.md §2 E）：
  正典序 canonical（42,302 条，含组表）+ 每半页字头数 counts → 累计切片 → 每个框一个条目标签。
  书眉（L 半版）给出 (部首, 部外笔画) 校验点；不一致 = 计数错，用局部搜索定位 ±1 修正。

输入接口（文件，缺省可用 mock）：
  --canonical work/lead/canonical_proto.jsonl   （或 seq 正式版 work/seq/canonical.jsonl）
  --groups    work/lead/groups_proto.json
  --counts    JSON: {"01_0006": {"R": 0, "L": 1}, ...}，缺省页用 --default-count
  --headers   JSONL: {"page": "01_0006", "half": "L", "ji": "子集上", "bu": "一部", "hua": [1]}
  --pages     "01:6-" 之类，缺省全部 01:6..12 末页

输出：
  work/map/mapping.jsonl  每半页一条：{page, half, ci_start, ci_end, n, predicted_groups:[[rad,bu],...] ,
                                           header, header_match, entries:[{ci,char}]}
  work/map/solver_report.json  统计 + 不一致窗口 + 修正建议
"""
import json, os, sys, collections, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 卷内顺序（正集）：14 个 PDF，01..12 是正集；13 是補遺/備考（另行处理）
MAIN_VOLS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]


def load_pdf_pages():
    mp = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
    return mp


def page_counts():
    """每个 PDF 的页数（惰性：用一个已缓存文件，否则用 fitz 现场数并缓存）。"""
    cache = os.path.join(ROOT, "work", "lead", "pdf_pagecounts.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    import fitz
    mp = load_pdf_pages()
    out = {}
    for k, v in mp.items():
        d = fitz.open(os.path.join(ROOT, "康熙字典", v))
        out[k] = d.page_count
        d.close()
    json.dump(out, open(cache, "w", encoding="utf-8"))
    return out


def build_sequence(vols, first_page=None):
    """返回 [(vol, page, half)] 按阅读序：每跨页先 R 后 L。page 为 1-based 页号。"""
    pc = page_counts()
    seq = []
    for v in vols:
        start = 1
        if first_page and v == vols[0]:
            start = first_page
        for p in range(start, pc[v] + 1):
            seq.append((v, p, "R"))
            seq.append((v, p, "L"))
    return seq


class Canon:
    def __init__(self, path, groups_path):
        self.entries = []
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                self.entries.append(json.loads(line))
        self.groups = json.load(open(groups_path, encoding="utf-8"))
        # gi -> group
        self.gi = {g["gi"]: g for g in self.groups}
        for e in self.entries:
            g = self.gi.get(e.get("gi"))
            e["_rad"] = g["rad"] if g else e.get("rad")
            e["_bu"] = g["bu_strokes"] if g else e.get("bu_strokes")
        self.n = len(self.entries)

    def group_of_ci(self, ci):
        e = self.entries[ci]
        return (e["_rad"], e["_bu"])

    def groups_between(self, a, b):
        """[a,b) 涉及的组集合（有序）"""
        out = []
        for ci in range(a, min(b, self.n)):
            k = self.group_of_ci(ci)
            if not out or out[-1] != k:
                out.append(k)
        return out


def key(page, half):
    return f"{page}:{half}"


def solve(seq, counts, headers, canon, default_count=0, half_max=80):
    """累计切片 + 校验。返回 mapping 列表和 report。"""
    ci = 0
    mapping = []
    problems = []
    last_good = None  # (seq_idx, ci_after)
    for si, (vol, page, half) in enumerate(seq):
        pkey = f"{vol}_{page:04d}"
        c = counts.get(pkey, {}).get(half)
        if c is None:
            c = default_count
        c = int(c)
        n_before = ci
        ci = min(canon.n, ci + max(0, min(c, half_max)))
        groups = canon.groups_between(n_before, ci)
        hdr = headers.get(key(pkey, half))
        rec = {
            "seq": si, "page": pkey, "half": half, "ci_start": n_before, "ci_end": ci,
            "n": ci - n_before,
            "predicted_groups": [[g[0], g[1]] for g in groups],
            "header": hdr,
            "header_match": None,
            "entries": [canon.entries[k]["char"] for k in range(n_before, ci)],
        }
        if hdr and hdr.get("bu") and half == "L":
            hb = norm_bu(hdr.get("bu"))
            hua = norm_hua(hdr.get("hua"))
            pred = set()
            for (rad, bu) in groups:
                pred.add((norm_bu(rad), bu))
            if not groups:  # 累计点恰在组边界（本半页 0 条）
                if n_before < canon.n:
                    r0, b0 = canon.group_of_ci(n_before)
                    pred.add((norm_bu(r0), b0))
            ok = any((hb == rad) and (not hua or bu in hua) for (rad, bu) in pred)
            rec["header_match"] = ok
            if not ok:
                problems.append({"seq": si, "page": pkey, "half": half, "ci": n_before,
                                 "groups": rec["predicted_groups"], "header": hdr,
                                 "last_good_seq": last_good[0] if last_good else None})
            else:
                last_good = (si, ci)
        mapping.append(rec)
    report = {
        "n_halves": len(seq),
        "n_entries_consumed": ci,
        "n_canonical": canon.n,
        "remainder": canon.n - ci,
        "header_checks": sum(1 for r in mapping if r["header_match"] is not None),
        "header_mismatches": sum(1 for r in mapping if r["header_match"] is False),
        "problems": problems[:200],
    }
    return mapping, report


def norm_bu(bu):
    """书眉部名 -> 部首字：去「部」后缀 + 异体归一。"""
    if not bu:
        return None
    b = str(bu).strip()
    if b.endswith("部"):
        b = b[:-1]
    return rad_alias(b)


_HUA_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
            "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
            "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20, "廿": 20}


def norm_hua(hua):
    """书眉画数字段 -> int 列表。支持 ["一畫"] / [1] / "一畫二畫" 等形式。"""
    if not hua:
        return []
    if isinstance(hua, (int, float)):
        return [int(hua)]
    if isinstance(hua, str):
        hua = [hua]
    out = []
    for h in hua:
        if isinstance(h, (int, float)):
            out.append(int(h))
            continue
        t = str(h).strip().replace("畫", "").replace("画", "")
        if t.isdigit():
            out.append(int(t))
        elif t in _HUA_NUM:
            out.append(_HUA_NUM[t])
        elif t:
            # "五畫六畫" -> 拆
            import re as _re
            for m in _re.findall(r"[一二三四五六七八九十廿]+", t):
                if m in _HUA_NUM:
                    out.append(_HUA_NUM[m])
    return out


def rad_alias(rad):
    # 书眉可能有异体：户/戶、青/靑 等
    alias = {"户": "戶", "青": "靑", "兌": "儿", "旡": "无"}
    return alias.get(rad, rad)


def simulate_counts(canon, seq, headers=None, noise=0, seed=1):
    """产生「平均每半页 ~n 字」的模拟 counts，可选注入 ±1 噪声，用于验证 solver 逻辑。"""
    import random
    rng = random.Random(seed)
    counts = {}
    ci = 0
    for si, (vol, page, half) in enumerate(seq):
        # 模拟：每半页大致 6-14 条，最长组边界自洽（用 canonical 组大小驱动）
        base = 8
        if ci >= canon.n:
            n = 0
        else:
            n = max(0, min(base, canon.n - ci))
        if noise and rng.random() < 0.05:
            n = max(0, n + rng.choice([-1, 1]))
        counts[f"{vol}_{page:04d}"] = counts.get(f"{vol}_{page:04d}", {})
        counts[f"{vol}_{page:04d}"][half] = n
        ci += n
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", default=os.path.join(ROOT, "work/lead/canonical_proto.jsonl"))
    ap.add_argument("--groups", default=os.path.join(ROOT, "work/lead/groups_proto.json"))
    ap.add_argument("--counts", default=None)
    ap.add_argument("--headers", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/map"))
    ap.add_argument("--default-count", type=int, default=0)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="truncate sequence length (debug)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    canon = Canon(args.canonical, args.groups)
    print(f"canonical: {canon.n} entries, {len(canon.groups)} groups")

    if args.self_test:
        seq = build_sequence(MAIN_VOLS, first_page=6)
        seq = seq[:1200]
        counts = simulate_counts(canon, seq)
        mapping, report = solve(seq, counts, {}, canon)
        print("[self-test] no-noise:", {k: report[k] for k in
                                        ("n_halves", "n_entries_consumed", "remainder",
                                         "header_checks", "header_mismatches")})
        counts2 = simulate_counts(canon, seq, noise=1)
        deltas = sum(1 for h, d in counts2.items() for half, n in d.items()
                     if counts.get(h, {}).get(half, 0) != n)
        mapping2, report2 = solve(seq, counts2, {}, canon)
        print(f"[self-test] +noise({deltas} bad halves): consumed",
              report2["n_entries_consumed"], "vs", report["n_entries_consumed"])
        return

    seq = build_sequence(MAIN_VOLS, first_page=6)
    if args.limit:
        seq = seq[:args.limit]
    counts = {}
    if args.counts:
        counts = json.load(open(args.counts, encoding="utf-8"))
    headers = {}
    if args.headers:
        for line in open(args.headers, encoding="utf-8"):
            d = json.loads(line)
            headers[key(d["page"], d["half"])] = d
    mapping, report = solve(seq, counts, headers, canon, default_count=args.default_count)
    json.dump(mapping, open(os.path.join(args.out, "mapping.jsonl"), "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump(report, open(os.path.join(args.out, "solver_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in
                      ("n_halves", "n_entries_consumed", "n_canonical", "remainder",
                       "header_checks", "header_mismatches")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
