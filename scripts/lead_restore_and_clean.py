#!/usr/bin/env python3
"""v2.3.1 数据修复：
1) 回填 v2.1 误删字（含「一」等少笔画字头）——重新矢量化 + 字形级 QA；
2) 剔除圈注序号字形（◯内三/四 这类版面记号）；
3) 挂起无内容校验的 +alt / qa_retry 替代字（审计 P0-A）；
4) 输出 union10 / mapping / manifest / 修复报告（含各清单）。
"""
import argparse, collections, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--union", default=os.path.join(ROOT, "work/lead/confirmed_union9.json"))
    ap.add_argument("--prev-union", default=os.path.join(ROOT, "work/lead/confirmed_union8.json"))
    ap.add_argument("--prev-font", default=os.path.join(
        ROOT, "release/KangXiKai-v2.0.1/KangXiKai-Regular-v2.0.1.ttf"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "work/lead"))
    args = ap.parse_args()
    import numpy as np
    import cv2
    import font_norm as FN

    sys.path.insert(0, os.path.join(ROOT, "work/font/_pylibs"))
    from fontTools.ttLib import TTFont
    canon = [json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    canon_set = set(canon)
    union = json.load(open(args.union))
    prev = json.load(open(args.prev_union))
    fm = TTFont(args.prev_font)
    prev_cmap = set(fm.getBestCmap())
    union_cps = {ord(c) for c in union}

    # ---------- 1) 回填候选 ----------
    restore_cands = [chr(cp) for cp in sorted(prev_cmap - union_cps)
                     if chr(cp) in canon_set]

    def glyph_ok(contours):
        # 渲染 256px → 连通域 ≤14（与 font_qa 同口径）；bbox 短边 ≥60
        mask = np.zeros((256, 256), np.uint8)
        xs, ys = [], []
        for c in contours:
            pts = [(c["start"][0], c["start"][1])]
            for s in c["segs"]:
                if s[0] == "L":
                    pts.append((s[1], s[2]))
                else:
                    pts += [(s[1], s[2]), (s[3], s[4]), (s[5], s[6])]
            poly = np.array([[int(x / 1000 * 256), int((1000 - y) / 1000 * 256)] for x, y in pts],
                            np.int32)
            if len(poly) >= 3:
                cv2.fillPoly(mask, [poly], 1)
        ncomp = cv2.connectedComponents(mask)[0] - 1
        if ncomp > 14:
            return False, f"components {ncomp}"
        ys_, xs_ = np.nonzero(mask)
        if len(xs_) == 0:
            return False, "empty"
        w, h = xs_.max() - xs_.min(), ys_.max() - ys_.min()
        if min(w, h) < 60 and not (max(w, h) >= 600 and min(w, h) >= 18):
            return False, f"tiny {w}x{h}"
        return True, ""

    restored, restore_fail = [], []
    for ch in restore_cands:
        rec = prev[ch]
        try:
            res = FN.vectorize_box(rec["page"], rec["box"])
        except Exception as e:
            restore_fail.append({"char": ch, "reason": f"exc {e!r}"[:80]})
            continue
        if not res.get("ok"):
            restore_fail.append({"char": ch, "reason": res.get("reason", "vectorize fail")})
            continue
        ok, why = glyph_ok(res["contours"])
        if not ok:
            restore_fail.append({"char": ch, "reason": why})
            continue
        union[ch] = {**rec, "src": "restored_v231"}
        restored.append({"char": ch, "page": rec["page"], "half": rec["half"],
                         "box": rec["box"]})

    # ---------- 2) 圈注序号剔除 ----------
    def circle_marker(rec):
        """两段式圈注序号检测：
        A) 快速预筛：crop 内存在「不接触边框的封闭背景区」占 bbox ≥25%（圈内空白）；
        B) Hough 圆 + 环覆盖率 + 内部墨密度 复核。
        方形字框（回/口/田）预筛会通过但 Hough 圆复核不通过。"""
        gray = FN.render_pdf_crop(rec["page"], rec["box"], pad150=6)
        ink = FN.binarize(gray).astype(np.uint8)
        H, W = ink.shape
        if H < 60 or W < 60:
            return False
        # A) 封闭背景区
        bg = (ink == 0).astype(np.uint8)
        nb, lb, sb, cb = cv2.connectedComponentsWithStats(bg, 4)
        max_hole = 0
        for i in range(1, nb):
            x, y, w, h, a = sb[i]
            if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
                continue      # 接触边框 = 外部背景
            max_hole = max(max_hole, a)
        if max_hole < 0.20 * W * H:
            return False
        # B) Hough 圆 + 环覆盖
        g = cv2.GaussianBlur(gray, (5, 5), 0)
        scale = 180.0 / max(H, W)
        if scale < 1:
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            ink_r = cv2.resize(ink, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        else:
            ink_r = ink
        h2, w2 = g.shape
        s2 = min(h2, w2)
        cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=s2 * 0.5,
                              param1=140, param2=58,
                              minRadius=int(0.32 * s2), maxRadius=int(0.58 * s2))
        if cs is None:
            return False
        for c in cs[0]:
            cx, cy, r = float(c[0]), float(c[1]), float(c[2])
            if abs(cx - w2 / 2) > 0.25 * w2 or abs(cy - h2 / 2) > 0.25 * h2:
                continue
            th = np.linspace(0, 2 * np.pi, 360)
            hit = 0
            for t in th:
                x = int(round(cx + r * np.cos(t))); y = int(round(cy + r * np.sin(t)))
                if 0 <= y < h2 and 0 <= x < w2 and ink_r[max(0, y - 3):y + 4,
                                                       max(0, x - 3):x + 4].any():
                    hit += 1
            if hit / 360 >= 0.52:
                return True
        return False

    circles = []
    for ch in list(union.keys()):
        try:
            if circle_marker(union[ch]):
                circles.append({"char": ch, "page": union[ch]["page"],
                                "box": union[ch]["box"], "src": union[ch].get("src", "")})
                union.pop(ch)
        except Exception:
            continue

    # ---------- 3) 挂起 +alt / qa_retry ----------
    suspended = []
    for ch in list(union.keys()):
        src = union[ch].get("src", "")
        if "+alt" in src or src == "qa_retry":
            suspended.append({"char": ch, "page": union[ch]["page"], "half": union[ch]["half"],
                              "box": union[ch]["box"], "src": src})
            union.pop(ch)

    # ---------- 4) 输出 ----------
    union_path = os.path.join(args.outdir, "confirmed_union10.json")
    json.dump(union, open(union_path, "w"), ensure_ascii=False)
    rows = collections.OrderedDict()
    for ch, rec in sorted(union.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    mapping_path = os.path.join(args.outdir, "mapping_verified_all10.jsonl")
    with open(mapping_path, "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst],
                                "in_body": True, "header_ok": None},
                               ensure_ascii=False) + "\n")
    manifest_path = os.path.join(args.outdir, "manifest-v231.json")
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
    json.dump(man, open(manifest_path, "w"), ensure_ascii=False)

    def is_basic(c):
        return 0x4E00 <= ord(c) <= 0x9FFF
    b = sum(1 for c in union if is_basic(c) and c in canon_set)
    report = {
        "inputs": {p: sha256(p) for p in (args.union, args.prev_union, args.prev_font)},
        "restore_candidates": len(restore_cands), "restored": len(restored),
        "restore_failed": len(restore_fail),
        "restored_list": restored, "restore_failed_list": restore_fail,
        "circles_removed": len(circles), "circles": circles,
        "suspended": len(suspended), "suspended_list": suspended,
        "final": {"n_chars": len(union), "basic_in_canonical": b,
                  "basic_coverage_pct": round(b / 16567 * 100, 2), "target_basic": 16567},
        "outputs": {p: sha256(p) for p in (union_path, mapping_path, manifest_path)},
    }
    json.dump(report, open(os.path.join(args.outdir, "v231_fix_report.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("restore_candidates", "restored",
                                             "restore_failed", "circles_removed",
                                             "suspended", "final")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
