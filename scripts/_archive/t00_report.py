#!/usr/bin/env python3
"""T0.0 · 覆盖盘点对账 → docs/HEADWORD-COVERAGE.md

双引擎口径：v6 (ocr.jsonl) 为主，v5 (ocr_v5.jsonl) 补漏（同一 crop 各取一个识别，
CJK 有效者并入候选集；同一 crop 两引擎不一致时 v6 优先并记 conflict）。

输入 work/t00/{headwords,ocr,ocr_v5,page_stats,margins_ocr}.jsonl + 参照数据
输出 docs/HEADWORD-COVERAGE.md + work/t00/t00_stats.json
"""
import json, os, collections, statistics
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")
DOCS = os.path.join(ROOT, "docs")


def is_cjk(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0x20000 <= o <= 0x2AFFF) or (0xF900 <= o <= 0xFAFF)


def load_unihan():
    kk, tv = set(), {}
    p = os.path.join(ROOT, "data", "unihan", "Unihan_DictionaryIndices.txt")
    for line in open(p, encoding="utf-8"):
        if line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        if len(f) >= 3 and f[1] == "kKangXi":
            kk.add(int(f[0][2:], 16))
    p = os.path.join(ROOT, "data", "unihan", "Unihan_Variants.txt")
    for line in open(p, encoding="utf-8"):
        if line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        if len(f) >= 3 and f[1] == "kTraditionalVariant":
            # 该简体码点对应的繁体（可能有多个，取全部）
            tv.setdefault(int(f[0][2:], 16), []).extend(
                int(x.strip()[2:], 16) for x in f[2].split())
    return kk, tv


def load_dataset():
    wb = openpyxl.load_workbook(
        os.path.join(ROOT, "data", "ref", "kangxi-dictionary", "kx_full.xlsx"),
        read_only=True)
    ws = wb["kx"]
    rows = ws.iter_rows(values_only=True)
    next(rows)
    D = set()
    for r in rows:
        if isinstance(r[0], str) and len(r[0]) == 1:
            D.add(r[0])
    return D


def main():
    kk, tv = load_unihan()
    D = load_dataset()
    basic = lambda c: 0x4E00 <= ord(c) <= 0x9FFF

    def load_engine(path):
        out = {}
        if not os.path.exists(path):
            return out
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            t = (r.get("text") or "").strip()
            out[r["crop"]] = (t, r.get("conf", 0.0))
        return out

    E6 = load_engine(os.path.join(T00, "ocr.jsonl"))
    E5 = load_engine(os.path.join(T00, "ocr_v5.jsonl"))

    heads = [json.loads(l) for l in open(os.path.join(T00, "headwords.jsonl"), encoding="utf-8")]
    per_page = collections.Counter()
    label_of = {}          # crop -> 最终标签（可含 latin/空）
    conflicts = []
    for h in heads:
        crop = h["crop"]
        per_page[(h["pdf"], h["page"])] += 1
        t6, c6 = E6.get(crop, ("", 0.0))
        t5, c5 = E5.get(crop, ("", 0.0))
        v6_ok = t6 and is_cjk(t6[0])
        v5_ok = t5 and is_cjk(t5[0])
        if v6_ok:
            label_of[crop] = t6[0]
            if v5_ok and t5[0] != t6[0]:
                conflicts.append((crop, t6[0], t5[0]))
        elif v5_ok:
            label_of[crop] = t5[0]
        else:
            label_of[crop] = t6 or t5

    recognized = {c: t for c, t in label_of.items() if t and is_cjk(t[0])}
    uniq = collections.Counter(recognized.values())
    n_unrec = sum(1 for t in label_of.values() if not (t and is_cjk(t[0])))

    uniq_basic = {c for c in uniq if basic(c)}
    uniq_nonbasic = {c for c in uniq if not basic(c)}

    D_basic = {c for c in D if basic(c)}
    K_basic = {chr(cp) for cp in kk if 0x4E00 <= cp <= 0x9FFF}

    hits_D = uniq_basic & D_basic
    miss_D = uniq_basic - D_basic
    # 简体输出映射：miss_D 中有 kTraditionalVariant 且繁体在 D 中
    simp_mapped, really_missing = set(), set()
    for c in miss_D:
        cp = ord(c)
        trads = [chr(x) for x in tv.get(cp, []) if basic(chr(x)) or ord(chr(x)) > 0xFFFF]
        if trads and any(t in D for t in trads):
            simp_mapped.add(c)
        else:
            really_missing.add(c)

    main_pages = [v for (p, _), v in per_page.items() if p != "13"]
    p13 = [v for (p, _), v in per_page.items() if p == "13"]

    stats = {
        "sampled_pages": len(per_page),
        "headword_boxes": len(heads),
        "recognized_cjk": len(recognized),
        "unrecognized": n_unrec,
        "engine_conflicts": len(conflicts),
        "uniq_all": len(uniq),
        "uniq_basic": len(uniq_basic),
        "uniq_nonbasic": len(uniq_nonbasic),
        "uniq_nonbasic_sample": "".join(sorted(uniq_nonbasic)[:60]),
        "dup_headwords": sum(v for v in uniq.values() if v > 1),
        "mean_main": round(sum(main_pages) / max(1, len(main_pages)), 2),
        "mean_13": round(sum(p13) / max(1, len(p13)), 2),
        "extrap_main": round(sum(main_pages) / max(1, len(main_pages)) * 3541),
        "extrap_13": round(sum(p13) / max(1, len(p13)) * 178),
        "sample_hits_D": len(hits_D),
        "sample_hits_D_rate": round(len(hits_D) / max(1, len(uniq_basic)), 3),
        "sample_miss_D": len(miss_D),
        "sample_miss_D_simpmap": len(simp_mapped),
        "sample_miss_D_real": len(really_missing),
        "sample_miss_D_real_chars": "".join(sorted(really_missing)[:80]),
        "D_total": len(D), "D_basic": len(D_basic), "K_basic": len(K_basic),
    }
    json.dump(stats, open(os.path.join(T00, "t00_stats.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))

    # 冲突明细抽样
    print("conflict sample:", conflicts[:12])


if __name__ == "__main__":
    main()
