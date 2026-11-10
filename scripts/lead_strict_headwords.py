#!/usr/bin/env python3
"""v2.4.0 严格字头级字表：剔除一切注文级小字（owner 原则：真字不要小字，缺了由后续 GAN 补全）。

判据（任一命中即剔）：
  A) label_source 含 smallsrc（v2.1 误删字回填时引入的注文级小框）；
  B) 源框 max 边 < 65（150dpi）——注文字级；
  C) 来源为 small / small_loose（小字层直采）。
输出 union13 / mapping / manifest / 剔除清单 / 缺口（GAN 补全目标）清单。
"""
import collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    union = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union12.json")))
    prev = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union8.json")))
    dropped, keep = [], {}
    for ch, rec in union.items():
        src = str(rec.get("src", ""))
        b = rec.get("box") or [0, 0, 0, 0]
        mx = max(b[2] - b[0], b[3] - b[1])
        reason = None
        if "smallsrc" in src:
            reason = "smallsrc-marked"
        elif mx < 65:
            reason = f"box max {mx}<65 (annotation-level)"
        elif src in ("small", "small_loose") or src.startswith("small"):
            reason = f"source {src} (small layer)"
        if reason:
            dropped.append({"char": ch, "page": rec.get("page"), "half": rec.get("half"),
                            "box": rec.get("box"), "label_source": src,
                            "reason": reason})
        else:
            keep[ch] = rec
    json.dump(keep, open(os.path.join(ROOT, "work/lead/confirmed_union13.json"), "w"),
              ensure_ascii=False)
    rows = collections.OrderedDict()
    for ch, rec in sorted(keep.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    mapping = os.path.join(ROOT, "work/lead/mapping_verified_all13.jsonl")
    with open(mapping, "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst],
                                "in_body": True, "header_ok": None},
                               ensure_ascii=False) + "\n")
    VERIFIED = {
        "restored_v231": "v2.1 误删字回填（字头级尺寸，重新矢量化+QA）",
        "from_v201_glyph": "从 v2.0.1 字体精确复刻轮廓（字头级）",
        "vlm_fp_A": "VLM 注文指纹 + 音切开头 + margin≥0.05",
        "vlm_fp_B": "VLM 注文指纹（纠正映射错位）+ 音切开头 + margin≥0.05",
    }
    man = {"family": "KangXiKai", "style": "Kai", "version": "2.4.0", "upm": 1000,
           "license": "OFL-1.1", "provenance": "real",
           "standard": "headword-only：仅收字头级真迹，注文小字一律不收（缺口留给后续 GAN 补全）",
           "n_chars": len(keep), "chars": {}}
    for ch, rec in sorted(keep.items()):
        src = rec.get("src", "base")
        man["chars"][ch] = {"char": ch, "codepoint": f"U+{ord(ch):04X}",
                            "key": f"v240_{rec['page']}_{rec['half']}",
                            "page": rec["page"], "half": rec["half"], "box": rec["box"],
                            "layer": "zhujuan", "label_source": src,
                            "verified_by": VERIFIED.get(src, "OCR/序列对齐（v1.x 基线）")}
    mpath = os.path.join(ROOT, "work/lead/manifest-v240.json")
    json.dump(man, open(mpath, "w"), ensure_ascii=False)
    canon = [json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    canon_set = set(canon)
    def is_basic(c): return 0x4E00 <= ord(c) <= 0x9FFF
    b = sum(1 for c in keep if is_basic(c) and c in canon_set)
    target = list(dict.fromkeys(c for c in canon if is_basic(c)))  # 去重（canonical 含重出条目）
    missing = [c for c in target if c not in keep]
    report = {
        "standard": "headword-only (no annotation/small glyphs)",
        "dropped": len(dropped), "dropped_list": dropped,
        "final": {"n_chars": len(keep), "basic_in_canonical": b,
                  "basic_coverage_pct": round(b / 16567 * 100, 2),
                  "target_basic": 16567},
        "gan_fill_targets": {"n_missing_basic": len(missing),
                             "missing_sample": missing[:80]},
    }
    json.dump(report, open(os.path.join(ROOT, "work/lead/v240_strict_report.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"dropped": len(dropped), **report["final"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
