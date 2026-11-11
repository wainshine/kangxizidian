#!/usr/bin/env python3
"""缺部件外科修复：对指定字（owner 标记）检查「源块墨迹中未被成品字形覆盖的组件」，
若有 → 扩大字框重矢量化，并原地替换字体中的该字形（其余字形不动）。

用法: python scripts/repair_missing_chars.py --base <ttf> --out <ttf> --chars-file <json> --version 2.5.2
"""
import argparse, json, os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--chars-file", required=True)
    ap.add_argument("--version", default="2.5.2")
    args = ap.parse_args()
    import font_build as FB
    import font_norm as FN
    from fontTools.ttLib import TTFont
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.recordingPen import RecordingPen

    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    marks = json.load(open(os.path.join(ROOT, args.chars_file), encoding="utf-8"))
    targets = [m["char"] for m in marks if m["char"] in man]
    fonts = TTFont(args.base, recalcTimestamp=False)
    glyf = fonts["glyf"]; cmap = fonts.getBestCmap()
    fixed = []
    for ch in targets:
        r = man[ch]
        page, box = r["page"], r["box"]
        lat = FB.get_page_lattice(page).get(r.get("half", "L"))
        block = FB.block_for_box(lat, box)
        tbb = FB.get_page_text_bbox(page)
        if block is not None and tbb is not None:
            block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                     min(block[2], tbb[2]), min(block[3], tbb[3]))
        # 源块墨迹（300dpi block 区域）
        g = FB.get_page_frame_mask(page)
        b2 = [int(round(v * 2)) for v in block] if block else None
        # 用 render_pdf_crop 渲染覆盖 block 的裁片
        cropbox = [int(v) for v in box]
        gray = FN.render_pdf_crop(page, cropbox, pad150=6, dpi=300)
        src = FN.binarize(gray)
        # 成品字形
        from fidelity_eval import glyph_mask_from_font
        gm = glyph_mask_from_font(args.base, ch)
        # 配准 glyph -> src（主组件）
        def comps(mask):
            n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
            return lab, [(st[i, 0], st[i, 1], st[i, 0] + st[i, 2], st[i, 1] + st[i, 3], int(st[i, 4]))
                         for i in range(1, n) if st[i, 4] >= 20]
        lab_s, cs = comps(src); _, cg = comps(gm)
        if not cs or not cg:
            continue
        ms = max(cs, key=lambda c: c[4]); mg = max(cg, key=lambda c: c[4])
        cc = lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        c1, c2 = cc(mg), cc(ms)
        l1 = max(mg[2] - mg[0], mg[3] - mg[1]); l2 = max(ms[2] - ms[0], ms[3] - ms[1])
        sc = l2 / max(1.0, l1)
        M = np.array([[sc, 0, c2[0] - sc * c1[0]], [0, sc, c2[1] - sc * c1[1]]], np.float32)
        gw = cv2.warpAffine(gm.astype(np.uint8), M, (src.shape[1], src.shape[0]),
                            flags=cv2.INTER_NEAREST) > 0
        gd = cv2.dilate(gw.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        total = int(src.sum())
        missing = []
        for idx, (x0, y0, x1, y1, a) in enumerate(cs):
            if a < 0.010 * total:      # 太小 → 极可能是残片/戳记，跳过
                continue
            ww, hh = x1 - x0 + 1, y1 - y0 + 1
            if min(ww, hh) < 8:        # 细长 → 框线/栏线，不是字身部件
                continue
            # 到主组件 bbox 的间距（单位：crop 像素）
            dxg = max(0, max(ms[0], x0) - min(ms[2], x1))
            dyg = max(0, max(ms[1], y0) - min(ms[3], y1))
            if dxg > 18 or dyg > 18:   # 离字身太远 → 邻字/注文
                continue
            reg = src[y0:y1 + 1, x0:x1 + 1]
            cov = float((reg & gd[y0:y1 + 1, x0:x1 + 1]).sum()) / max(1, int(reg.sum()))
            if cov < 0.45:
                missing.append((x0, y0, x1, y1, a))
        if not missing:
            continue
        # 新框 = 旧框 ∪ 缺失组件（150dpi 坐标：crop 坐标 + (box0-6) 换算回 150dpi）
        nb = list(cropbox)
        for (x0, y0, x1, y1, a) in missing:
            ax0 = cropbox[0] - 6 + x0 / 2.0; ay0 = cropbox[1] - 6 + y0 / 2.0
            ax1 = cropbox[0] - 6 + x1 / 2.0; ay1 = cropbox[1] - 6 + y1 / 2.0
            nb[0] = min(nb[0], ax0 - 2); nb[1] = min(nb[1], ay0 - 2)
            nb[2] = max(nb[2], ax1 + 2); nb[3] = max(nb[3], ay1 + 2)
        res = FN.vectorize_box(page, [int(round(v)) for v in nb], enable_edge_strip=False,
                               char=ch, block150=block, frame_mask=g)
        if not res.get("ok"):
            continue
        # 写回字形
        gname = cmap[ord(ch)]
        tpen = TTGlyphPen(None)
        qpen = Cu2QuPen(tpen, max_err=1.0)
        from font_build import orient_contours, _contour_points
        flip_map = orient_contours(res["contours"])
        from fontTools.pens.reverseContourPen import ReverseContourPen
        for c, flip in flip_map:
            rec = RecordingPen()
            rec.moveTo(tuple(c["start"]))
            for seg in c["segs"]:
                if seg[0] == "L":
                    rec.lineTo((seg[1], seg[2]))
                else:
                    rec.curveTo((seg[1], seg[2]), (seg[3], seg[4]), (seg[5], seg[6]))
            rec.closePath()
            rec.replay(ReverseContourPen(qpen) if flip else qpen)
        glyf[gname] = tpen.glyph()
        fixed.append({"char": ch, "old_box": box, "new_box": [int(round(v)) for v in nb],
                      "missing": [list(map(int, mm)) for mm in missing]})
    fonts.save(args.out)
    print(json.dumps({"fixed": len(fixed), "detail": fixed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
