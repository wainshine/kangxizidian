#!/usr/bin/env python3
"""全库缺部件批量修复：对扫描出的字扩框重矢量化，并原地替换字体字形。"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items = args[0], args[1], args[2]
    import font_build as FB
    import font_norm as FN
    lat = FB.get_page_lattice(page).get(half)
    tbb = FB.get_page_text_bbox(page)
    fm = FB.get_page_frame_mask(page)
    out = []
    for it in items:
        ch, box, missing = it["char"], it["box"], it["missing"]
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            nb = list(box)
            for (x0, y0, x1, y1, a) in missing:
                nb[0] = min(nb[0], box[0] - 6 + x0 / 2.0 - 2)
                nb[1] = min(nb[1], box[1] - 6 + y0 / 2.0 - 2)
                nb[2] = max(nb[2], box[0] - 6 + x1 / 2.0 + 2)
                nb[3] = max(nb[3], box[1] - 6 + y1 / 2.0 + 2)
            nb = [int(round(v)) for v in nb]
            res = FN.vectorize_box(page, nb, enable_edge_strip=False, char=ch,
                                   block150=block, frame_mask=fm)
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
    from font_build import orient_contours, _contour_points
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    scan = [json.loads(l) for l in open(os.path.join(ROOT, scan_path), encoding="utf-8")]
    scan = [s for s in scan if s.get("missing") and s["char"] in man]
    jobs = {}
    for s in scan:
        jobs.setdefault((s["page"], s.get("half", "L")), []).append(
            {"char": s["char"], "box": man[s["char"]]["box"], "missing": s["missing"]})
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
    print(json.dumps({"candidates": len(scan), "repaired": fixed}))


if __name__ == "__main__":
    main()
