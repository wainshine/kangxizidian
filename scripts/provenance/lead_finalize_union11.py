#!/usr/bin/env python3
"""v2.3.1 最终字集：union10 再剔除圈号字形（circle_marks.json），输出 union11/mapping/manifest/报告。"""
import collections, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    union = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union10.json")))
    marks = json.load(open(os.path.join(ROOT, "work/lead/circle_marks.json")))
    circle_chars = sorted({m["char"] for m in marks})
    removed = []
    for ch in circle_chars:
        if ch in union:
            removed.append({"char": ch, "page": union[ch]["page"], "box": union[ch]["box"],
                            "src": union[ch].get("src", "")})
            union.pop(ch)
    # 挂起的 +alt/qa_retry 字：用 v2.0.1 原框重新矢量化回填（含 二/冬/張 等常用字）
    import numpy as np
    import cv2
    import font_norm as FN
    fix = json.load(open(os.path.join(ROOT, "work/lead/v231_fix_report.json")))
    prev = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union8.json")))
    suspended = fix.get("suspended_list", [])
    def glyph_ok(contours):
        mask = np.zeros((256, 256), np.uint8)
        for c in contours:
            pts = [(c["start"][0], c["start"][1])]
            for sg in c["segs"]:
                if sg[0] == "L":
                    pts.append((sg[1], sg[2]))
                else:
                    pts += [(sg[1], sg[2]), (sg[3], sg[4]), (sg[5], sg[6])]
            poly = np.array([[int(x / 1000 * 256), int((1000 - y) / 1000 * 256)]
                             for x, y in pts], np.int32)
            if len(poly) >= 3:
                cv2.fillPoly(mask, [poly], 1)
        ncomp = cv2.connectedComponents(mask)[0] - 1
        ys_, xs_ = np.nonzero(mask)
        if ncomp > 14 or len(xs_) == 0:
            return False
        w = xs_.max() - xs_.min(); h = ys_.max() - ys_.min()
        # 允许扁平字（一/二/三 类少笔画字头）：长边够大且短边 >=18
        return min(w, h) >= 60 or (max(w, h) >= 600 and min(w, h) >= 18)
    reverted = []
    for it in suspended:
        ch = it["char"]
        if ch in union or ch not in prev:
            continue
        rec = prev[ch]
        try:
            res = FN.vectorize_box(rec["page"], rec["box"])
        except Exception:
            continue
        if res.get("ok") and glyph_ok(res["contours"]):
            union[ch] = {**rec, "src": "restored_v231"}
            reverted.append({"char": ch, "page": rec["page"], "box": rec["box"]})
    json.dump(union, open(os.path.join(ROOT, "work/lead/confirmed_union11.json"), "w"),
              ensure_ascii=False)
    print("suspended reverted", len(reverted), "".join(x["char"] for x in reverted[:40]))
    rows = collections.OrderedDict()
    for ch, rec in sorted(union.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    mapping = os.path.join(ROOT, "work/lead/mapping_verified_all11.jsonl")
    with open(mapping, "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst],
                                "in_body": True, "header_ok": None},
                               ensure_ascii=False) + "\n")
    man = {"family": "KangXiKai", "style": "Kai", "version": "2.3.1", "upm": 1000,
           "license": "OFL-1.1", "provenance": "real", "n_chars": len(union), "chars": {}}
    VERIFIED = {
        "restored_v231": "v2.1 误删字回填（重新矢量化 + 字形级 QA）",
        "vlm_fp_A": "VLM 注文指纹（与映射一致）+ 音切开头 + margin≥0.05",
        "vlm_fp_B": "VLM 注文指纹（纠正映射错位）+ 音切开头 + margin≥0.05",
    }
    for ch, rec in sorted(union.items()):
        src = rec.get("src", "base")
        man["chars"][ch] = {"char": ch, "codepoint": f"U+{ord(ch):04X}",
                            "key": f"v231_{rec['page']}_{rec['half']}",
                            "page": rec["page"], "half": rec["half"], "box": rec["box"],
                            "layer": "zhujuan", "label_source": src,
                            "verified_by": VERIFIED.get(src, "OCR/序列对齐（v1.x 基线）")}
    mp = os.path.join(ROOT, "work/lead/manifest-v231.json")
    json.dump(man, open(mp, "w"), ensure_ascii=False)
    canon = set(json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl")))
    def is_basic(c): return 0x4E00 <= ord(c) <= 0x9FFF
    b = sum(1 for c in union if is_basic(c) and c in canon)
    report = {"circle_removed": len(removed), "circle_removed_list": removed,
              "final": {"n_chars": len(union), "basic_in_canonical": b,
                        "basic_coverage_pct": round(b / 16567 * 100, 2)}}
    json.dump(report, open(os.path.join(ROOT, "work/lead/v231_final_report.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report["final"], ensure_ascii=False), "| circle removed", len(removed))


if __name__ == "__main__":
    main()
