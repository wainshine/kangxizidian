#!/usr/bin/env python3
"""切偏修复：对偏移超阈的字，在 3×3 格块候选里选择「墨迹中心最接近块中心」的块，重切重矢量化。"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items = args[0], args[1], args[2]
    import cv2
    import font_build as FB
    import font_norm as FN
    lat = FB.get_page_lattice(page).get(half)
    tbb = FB.get_page_text_bbox(page)
    fm = FB.get_page_frame_mask(page)
    out = []
    if not lat:
        return out
    px, py, phx, phy = lat
    from detect_blocks import page_gray, binarize
    g = page_gray(page[:2], int(page[3:]))
    ink = binarize(g)
    h, w = g.shape
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            base_block = FB.block_for_box(lat, box)
            if base_block is None:
                continue
            bx0, by0, bx1, by1 = base_block
            bcx, bcy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
            c0 = int(round((bcx - phx) / px)); r0 = int(round((bcy - phy) / py))
            best = None
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    c, r = c0 + dc, r0 + dr
                    X0 = phx + (c - 0.5) * px; Y0 = phy + (r - 0.5) * py
                    X1 = X0 + 2 * px; Y1 = Y0 + 2 * py
                    if X0 < 0 or Y0 < 0 or X1 >= w or Y1 >= h:
                        continue
                    sub = ink[int(Y0):int(Y1), int(X0):int(X1)]
                    a = int(sub.sum())
                    if a < 200:
                        continue
                    n2, l2, s2, _ = cv2.connectedComponentsWithStats(sub, 8)
                    if n2 <= 1:
                        continue
                    main = max(range(1, n2), key=lambda i: s2[i, cv2.CC_STAT_AREA])
                    area = int(s2[main, cv2.CC_STAT_AREA])
                    mx = s2[main, cv2.CC_STAT_LEFT] + s2[main, cv2.CC_STAT_WIDTH] / 2.0
                    my = s2[main, cv2.CC_STAT_TOP] + s2[main, cv2.CC_STAT_HEIGHT] / 2.0
                    off = (max(abs(mx - (X1 - X0) / 2.0), abs(my - (Y1 - Y0) / 2.0))
                           / max(px, py))
                    score = -off + 0.002 * area / max(1.0, px * py)
                    if best is None or score > best[0]:
                        best = (score, [int(round(X0)), int(round(Y0)), int(round(X1)), int(round(Y1))])
            if best is None:
                continue
            nb = best[1]
            res = FN.vectorize_box(page, nb, enable_edge_strip=False, char=ch,
                                   block150=tuple(nb), frame_mask=fm)
            if res.get("ok"):
                out.append({"char": ch, "new_box": nb, "contours": res["contours"],
                            "ink": res["ink_px"]})
        except Exception:
            pass
    return out


def main():
    base, man_path, scan_path, out_ttf = sys.argv[1:5]
    from fontTools.ttLib import TTFont
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    from font_build import orient_contours
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    scan = [json.loads(l) for l in open(os.path.join(ROOT, scan_path), encoding="utf-8")]
    scan = [s for s in scan if s["char"] in man]
    jobs = {}
    for s in scan:
        jobs.setdefault((s["page"], s.get("half", "L")), []).append(
            {"char": s["char"], "box": man[s["char"]]["box"]})
    jl = [(p, h, items) for (p, h), items in jobs.items()]
    results = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for r in ex.map(worker, jl, chunksize=2):
            results.extend(r)
    fonts = TTFont(base, recalcTimestamp=False)
    glyf = fonts["glyf"]; cmap = fonts.getBestCmap()
    fixed = 0
    for r in results:
        ch = r["char"]; gname = cmap[ord(ch)]
        tpen = TTGlyphPen(None); qpen = Cu2QuPen(tpen, max_err=1.0)
        for c, flip in orient_contours(r["contours"]):
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
        fixed += 1
    fonts.save(out_ttf)
    print(json.dumps({"flagged": len(scan), "repaired": fixed}))


if __name__ == "__main__":
    main()
