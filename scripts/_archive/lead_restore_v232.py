#!/usr/bin/env python3
"""v2.3.2 修补：
1) 从 v2.0.1 字体精确复刻「二」字形（quadratic→cubic，直接取轮廓，避免小框矢量化失败）；
2) 回填 泚/𧭅（v2.0.1 原框重新矢量化通过）；
3) 回填字打 smallsrc 标记（源框 max 边 <65px@150dpi 的注文级小框，共 ~355）；
4) 输出 union12 / mapping / manifest / 披露清单（含 known_missing 全量、圈号处置账目）。
"""
import collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def glyph_from_ttf(ttf_path, ch):
    """从 TTF 取字形轮廓，转为本项目 contours 格式（y-up, 函数曲线 → 三次贝塞尔）。"""
    sys.path.insert(0, os.path.join(ROOT, "work/font/_pylibs"))
    from fontTools.ttLib import TTFont
    from fontTools.pens.recordingPen import RecordingPen
    f = TTFont(ttf_path)
    cmap = f.getBestCmap()
    if ord(ch) not in cmap:
        return None
    gs = f.getGlyphSet()
    pen = RecordingPen()
    gs[cmap[ord(ch)]].draw(pen)
    contours = []
    cur = None

    def ensure():
        nonlocal cur
        if cur is None:
            cur = {"start": None, "segs": []}
            contours.append(cur)

    for op, args in pen.value:
        if op == "moveTo":
            cur = {"start": [float(args[0][0]), float(args[0][1])], "segs": []}
            contours.append(cur)
        elif op == "lineTo":
            ensure()
            x, y = args[0]
            cur["segs"].append(["L", float(x), float(y)])
        elif op == "qCurveTo":
            ensure()
            pts = [(float(x), float(y)) for x, y in args]
            # 处理隐含 on-curve 点
            if pts[-1] is None:  # TrueType 全 off-curve 情况（少见）
                continue
            prev = (cur["start"][0], cur["start"][1]) if not cur["segs"] else (
                cur["segs"][-1][-2], cur["segs"][-1][-1])
            for i in range(len(pts)):
                on = pts[-1] if i == len(pts) - 1 else ((pts[i][0] + pts[i + 1][0]) / 2,
                                                       (pts[i][1] + pts[i + 1][1]) / 2)
                q = pts[i]
                c1 = (prev[0] + 2.0 / 3.0 * (q[0] - prev[0]), prev[1] + 2.0 / 3.0 * (q[1] - prev[1]))
                c2 = (on[0] + 2.0 / 3.0 * (q[0] - on[0]), on[1] + 2.0 / 3.0 * (q[1] - on[1]))
                cur["segs"].append(["C", c1[0], c1[1], c2[0], c2[1], on[0], on[1]])
                prev = on
        elif op == "curveTo":
            ensure()
            pts = [(float(x), float(y)) for x, y in args]
            cur["segs"].append(["C", pts[0][0], pts[0][1], pts[1][0], pts[1][1],
                                pts[2][0], pts[2][1]])
        elif op == "closePath":
            pass
    return contours


def main():
    import numpy as np
    import cv2
    import font_norm as FN
    union = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union11.json")))
    prev = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union8.json")))
    fix = json.load(open(os.path.join(ROOT, "work/lead/v231_fix_report.json")))
    fin = json.load(open(os.path.join(ROOT, "work/lead/v231_final_report.json")))

    def glyph_ok(contours):
        mask = np.zeros((256, 256), np.uint8)
        for c in contours:
            pts = [(c["start"][0], c["start"][1])]
            for s in c["segs"]:
                if s[0] == "L":
                    pts.append((s[1], s[2]))
                else:
                    pts += [(s[1], s[2]), (s[3], s[4]), (s[5], s[6])]
            poly = np.array([[int(x / 1000 * 256), int((1000 - y) / 1000 * 256)]
                             for x, y in pts], np.int32)
            if len(poly) >= 3:
                cv2.fillPoly(mask, [poly], 1)
        ys_, xs_ = np.nonzero(mask)
        if len(xs_) == 0:
            return False
        w = xs_.max() - xs_.min(); h = ys_.max() - ys_.min()
        return min(w, h) >= 60 or (max(w, h) >= 600 and min(w, h) >= 18)

    added = []
    # 1) 二：v2.0.1 字体轮廓复刻
    contours = glyph_from_ttf(os.path.join(ROOT, "release/KangXiKai-v2.0.1/"
                                                 "KangXiKai-Regular-v2.0.1.ttf"), "二")
    if contours and glyph_ok(contours):
        union["二"] = {"char": "二", "page": prev["二"]["page"], "half": prev["二"]["half"],
                       "box": prev["二"]["box"], "src": "from_v201_glyph"}
        added.append("二")
    # 2) 泚/𧭅：原框重新矢量化
    for ch in ("泚", "𧭅"):
        if ch in union or ch not in prev:
            continue
        rec = prev[ch]
        res = FN.vectorize_box(rec["page"], rec["box"])
        if res.get("ok") and glyph_ok(res["contours"]):
            union[ch] = {**rec, "src": "restored_v231"}
            added.append(ch)

    # 3) 回填字打 smallsrc 标记
    small = 0
    for ch, rec in union.items():
        if "restored" not in str(rec.get("src", "")) and rec.get("src") != "from_v201_glyph":
            continue
        b = rec["box"]
        if max(b[2] - b[0], b[3] - b[1]) < 65:
            rec["src"] = rec["src"] if "smallsrc" in rec["src"] else rec["src"] + "_smallsrc"
            small += 1

    # 4) 输出
    json.dump(union, open(os.path.join(ROOT, "work/lead/confirmed_union12.json"), "w"),
              ensure_ascii=False)
    rows = collections.OrderedDict()
    for ch, rec in sorted(union.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    mapping = os.path.join(ROOT, "work/lead/mapping_verified_all12.jsonl")
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
        "restored_v231_smallsrc": "v2.1 误删字回填（源框为注文级小框，非字头级；见 README 披露）",
        "restored_v231": "v2.1 误删字回填（重新矢量化 + 字形级 QA）",
        "from_v201_glyph": "从 v2.0.1 字体精确复刻轮廓",
        "vlm_fp_A": "VLM 注文指纹 + 音切开头 + margin≥0.05",
        "vlm_fp_B": "VLM 注文指纹（纠正映射错位）+ 音切开头 + margin≥0.05",
    }
    man = {"family": "KangXiKai", "style": "Kai", "version": "2.3.2", "upm": 1000,
           "license": "OFL-1.1", "provenance": "real", "n_chars": len(union), "chars": {}}
    for ch, rec in sorted(union.items()):
        src = rec.get("src", "base")
        man["chars"][ch] = {"char": ch, "codepoint": f"U+{ord(ch):04X}",
                            "key": f"v232_{rec['page']}_{rec['half']}",
                            "page": rec["page"], "half": rec["half"], "box": rec["box"],
                            "layer": "zhujuan", "label_source": src,
                            "verified_by": VERIFIED.get(src, "OCR/序列对齐（v1.x 基线）")}
    mpath = os.path.join(ROOT, "work/lead/manifest-v232.json")
    json.dump(man, open(mpath, "w"), ensure_ascii=False)

    circles_removed = fin["circle_removed_list"]
    known_missing = [
        {"char": "三", "reason": "原映射框为版面圈号(◯内三)，真字头框待重定位"},
        {"char": "四", "reason": "原映射框为版面圈号(◯内四)，真字头框待重定位"},
        {"char": "顔", "reason": "v2.0.1 原框落在注文区(「韻會」)，无法回填；真字头框待重定位"},
        {"char": "㿪", "reason": "原映射框为圈号，已剔除；真字头框待重定位"},
        {"char": "𥃇", "reason": "原映射框为圈号，已剔除；真字头框待重定位"},
    ]
    lists = {
        "v232_added": added,
        "restored_smallsrc_count": small,
        "known_missing_common_chars": known_missing,
        "circles_account": {
            "v230_circle_candidates_from_cache_scan": 10,
            "v231_removed": [x["char"] for x in circles_removed],
            "v231_false_positive_reverted": ["罍", "贐", "凳", "勸", "曳", "彙"],
            "note": "缓存扫描的 10 个候选中 6 个是旧框假阳性（已回退原框修复），4 个为真圈号已剔除；"
                    "顔 因挂起 alt 而离线，非圈号剔除。",
        },
        "v231_undisclosed_removed": ["泚", "顔", "𧭅"],
    }
    json.dump(lists, open(os.path.join(ROOT, "work/lead/v232_fix_lists.json"), "w"),
              ensure_ascii=False, indent=1)
    canon = set(json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl")))
    def is_basic(c): return 0x4E00 <= ord(c) <= 0x9FFF
    b = sum(1 for c in union if is_basic(c) and c in canon)
    print(json.dumps({"added": added, "smallsrc": small, "final": len(union),
                      "basic_in_canonical": b,
                      "basic_coverage_pct": round(b / 16567 * 100, 2)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
