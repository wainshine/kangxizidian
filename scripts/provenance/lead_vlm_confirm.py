#!/usr/bin/env python3
"""VLM 注文指纹 → 确认字集（固化管线，可复算）。

流程（全部在本脚本内，输入/输出均记录 sha256）：
  1. 读取 work/lead/vlm_fp_full.jsonl（每未确认条目一行，含 vlm 转写、hint、expected_ci）
  2. 2-gram 匹配 kx_full 注文（窗口 ±60）→ top1/top2/margin（top2 为不同字的次优）
  3. 三重过滤：注文以音切标记开头 + score1≥0.3 + margin≥0.05
  4. A 类（top1==hint）/ B 类（top1!=hint）分别入集
  5. 同框唯一性裁决：同一 (page,half,box) 只允许一个字；冲突框两侧标签全部剔除（保守）
  6. 剔除不在 canonical 字头集的字（视觉上不是字头/简繁混淆）
  7. 输出：scored.jsonl / confirmed_union8.json / mapping_verified_all8.jsonl / manifest-v201.json / report.json
"""
import argparse, collections, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPENERS = ("唐韻", "廣韻", "集韻", "正韻", "韻會", "說文", "玉篇", "增韻", "篇海", "字彙",
           "龍龕", "釋名", "廣雅", "爾雅", "揚子", "五音", "類篇", "正字", "佩觿", "六書",
           "干祿", "字林", "古今", "集注", "唐本", "蜀本")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def grams(s, n=2):
    return collections.Counter(s[i:i + n] for i in range(len(s) - n + 1)) if len(s) >= n else collections.Counter()


def ngram_score(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return sum((ga & gb).values()) / min(sum(ga.values()), sum(gb.values()))


def starts_opener(t):
    t = (t or "").lstrip("【〔「『 ")
    return any(t.startswith(o) for o in OPENERS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fp", default=os.path.join(ROOT, "work/lead/vlm_fp_full.jsonl"))
    ap.add_argument("--base", default=os.path.join(ROOT, "work/lead/confirmed_union6.json"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "work/lead"))
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--score-min", type=float, default=0.4)
    ap.add_argument("--margin-min", type=float, default=0.1)
    ap.add_argument("--min-vlen", type=int, default=4)
    args = ap.parse_args()
    import openpyxl
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"),
                                read_only=True)
    ws = wb["kx"]
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    canon_set = set(chars)
    base = json.load(open(args.base))

    scored = []
    for l in open(args.fp, encoding="utf-8"):
        r = json.loads(l)
        ci = int(r["expected_ci"])
        cand = chars[max(0, ci - args.window):ci + args.window + 1]
        ranked = sorted(((ngram_score(r["vlm"], kx.get(c, "")), c) for c in cand), reverse=True)
        if not ranked:
            continue
        top1 = ranked[0]
        top2 = next(((s, c) for s, c in ranked[1:] if c != top1[1]), (0.0, ""))
        scored.append({**r, "score1": round(top1[0], 4), "top1": top1[1],
                       "score2": round(top2[0], 4), "top2": top2[1],
                       "margin": round(top1[0] - top2[0], 4),
                       "opener": starts_opener(r["vlm"])})

    def save_jsonl(path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")

    save_jsonl(os.path.join(args.outdir, "vlm_fp_scored.jsonl"), scored)

    # 三重过滤 → A/B
    passed = [r for r in scored if r["opener"] and r["score1"] >= args.score_min
              and r["margin"] >= args.margin_min and r["top1"]
              and len(r.get("vlm", "")) >= args.min_vlen]
    A = [r for r in passed if r["top1"] == r.get("hint")]
    B = [r for r in passed if r["top1"] != r.get("hint")]

    # 候选字集：base 保留；A 先入（同字取分数最高），B 补充
    union = {ch: {**rec, "src": rec.get("src", "base"), "from_base": True}
             for ch, rec in base.items()}

    def add_rows(rows, tag):
        added = 0
        for r in sorted(rows, key=lambda x: (-(x["score1"] + x["margin"]), x["top1"])):
            ch = r["top1"]
            if ch in union:
                continue
            union[ch] = {"char": ch, "page": r["page"], "half": r["half"], "box": r["box"],
                         "score": r["score1"], "margin": r["margin"], "src": tag,
                         "from_base": False}
            added += 1
        return added

    nA_added = add_rows(A, "vlm_fp_A")
    nB_added = add_rows(B, "vlm_fp_B")

    # 剔除不在 canonical 的字（简繁混淆/非字头）
    non_canon = sorted([ch for ch in union if ch not in canon_set])
    for ch in non_canon:
        union.pop(ch)

    # 同框唯一性：冲突框两侧全部剔除（保守），输出工单
    bybox = collections.defaultdict(list)
    for ch, rec in union.items():
        bybox[(rec["page"], rec["half"], tuple(rec["box"]))].append(ch)
    conflicts = [{"page": p, "half": h, "box": list(b), "chars": sorted(v),
                  "src": {ch: union[ch].get("src") for ch in v}}
                 for (p, h, b), v in bybox.items() if len(v) > 1]
    dropped_conflict = sorted(ch for c in conflicts for ch in c["chars"])
    for ch in dropped_conflict:
        union.pop(ch, None)

    # 输出
    union_path = os.path.join(args.outdir, "confirmed_union8.json")
    json.dump(union, open(union_path, "w"), ensure_ascii=False)
    rows = collections.OrderedDict()
    for ch, rec in sorted(union.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    mapping_path = os.path.join(args.outdir, "mapping_verified_all8.jsonl")
    with open(mapping_path, "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst],
                                "in_body": True, "header_ok": None},
                               ensure_ascii=False) + "\n")
    manifest_path = os.path.join(args.outdir, "manifest-v201.json")
    meta = {"family": "KangXiKai", "style": "Kai", "version": "2.0.1", "upm": 1000,
            "license": "OFL-1.1", "provenance": "real", "n_chars": len(union),
            "chars": {}}
    VERIFIED = {
        "vlm_fp_A": "VLM 注文指纹（与映射一致）+ 音切开头 + margin≥0.05",
        "vlm_fp_B": "VLM 注文指纹（纠正映射错位）+ 音切开头 + margin≥0.05",
    }
    for ch, rec in sorted(union.items()):
        src = rec.get("src", "base")
        meta["chars"][ch] = {"char": ch, "codepoint": f"U+{ord(ch):04X}",
                             "key": f"v201_{rec['page']}_{rec['half']}",
                             "page": rec["page"], "half": rec["half"], "box": rec["box"],
                             "layer": "zhujuan", "label_source": src,
                             "verified_by": VERIFIED.get(src, "OCR/序列对齐（v1.x 基线）")}
    json.dump(meta, open(manifest_path, "w"), ensure_ascii=False)

    def is_basic(c):
        return 0x4E00 <= ord(c) <= 0x9FFF

    basic_canon = sum(1 for c in union if is_basic(c) and c in canon_set)
    report = {
        "inputs": {p: sha256(p) for p in (args.fp, args.base)},
        "outputs": {p: sha256(p) for p in (os.path.join(args.outdir, "vlm_fp_scored.jsonl"),
                                            union_path, mapping_path, manifest_path)},
        "n_scored": len(scored), "n_passed": len(passed),
        "n_A_rows": len(A), "n_B_rows": len(B),
        "n_A_added_union": nA_added, "n_B_added_union": nB_added,
        "n_base": len(base), "n_union_before_clean": len(base) + nA_added + nB_added,
        "dropped_non_canonical": {"n": len(non_canon), "chars": non_canon},
        "same_box_conflicts": {"n_boxes": len(conflicts), "n_chars": len(dropped_conflict),
                               "conflicts": conflicts},
        "final": {"n_chars": len(union),
                  "basic_in_canonical": basic_canon,
                  "basic_coverage_pct": round(basic_canon / 16567 * 100, 2),
                  "target_basic": 16567},
    }
    json.dump(report, open(os.path.join(args.outdir, "vlm_confirm_report.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("n_scored", "n_passed", "n_A_rows", "n_B_rows",
                                             "n_A_added_union", "n_B_added_union",
                                             "final")}, ensure_ascii=False, indent=1))
    print("non-canonical dropped:", len(non_canon), "| conflicts:", len(conflicts),
          "boxes /", len(dropped_conflict), "chars")


if __name__ == "__main__":
    main()
