#!/usr/bin/env python3
"""生成 contours_override.json：对矢量化失败/不可靠的字，从 v2.0.1 字体精确复刻轮廓。"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work/font/_pylibs"))


def glyph_from_ttf(ttf_path, ch):
    from fontTools.ttLib import TTFont
    from fontTools.pens.recordingPen import RecordingPen
    f = TTFont(ttf_path)
    cmap = f.getBestCmap()
    if ord(ch) not in cmap:
        return None
    gs = f.getGlyphSet()
    pen = RecordingPen()
    gs[cmap[ord(ch)]].draw(pen)
    contours, cur = [], None
    for op, args in pen.value:
        if op == "moveTo":
            cur = {"start": [float(args[0][0]), float(args[0][1])], "segs": []}
            contours.append(cur)
        elif op == "lineTo":
            x, y = args[0]
            cur["segs"].append(["L", float(x), float(y)])
        elif op == "qCurveTo":
            pts = [None if p is None else (float(p[0]), float(p[1])) for p in args]
            prev = (cur["start"][0], cur["start"][1]) if not cur["segs"] else (
                cur["segs"][-1][-2], cur["segs"][-1][-1])
            i = 0
            while i < len(pts):
                q = pts[i]
                if i == len(pts) - 1:
                    on = q
                    seg = None
                else:
                    nxt = pts[i + 1] if pts[i + 1] is not None else pts[i]
                    on = ((q[0] + nxt[0]) / 2.0, (q[1] + nxt[1]) / 2.0)
                    seg = q
                c1 = (prev[0] + 2.0 / 3.0 * (q[0] - prev[0]), prev[1] + 2.0 / 3.0 * (q[1] - prev[1]))
                c2 = (on[0] + 2.0 / 3.0 * (q[0] - on[0]), on[1] + 2.0 / 3.0 * (q[1] - on[1]))
                cur["segs"].append(["C", c1[0], c1[1], c2[0], c2[1], on[0], on[1]])
                prev = on
                i += 1
        elif op == "curveTo":
            pts = [(float(x), float(y)) for x, y in args]
            cur["segs"].append(["C", pts[0][0], pts[0][1], pts[1][0], pts[1][1],
                                pts[2][0], pts[2][1]])
    return contours


def main():
    ttf = os.path.join(ROOT, "release/KangXiKai-v2.0.1/KangXiKai-Regular-v2.0.1.ttf")
    chars = ["二", "顔"]
    out = {}
    for ch in chars:
        cs = glyph_from_ttf(ttf, ch)
        if cs:
            xs, ys = [], []
            for c in cs:
                for s in c["segs"]:
                    pts = ([(s[1], s[2])] if s[0] == "L"
                           else [(s[1], s[2]), (s[3], s[4]), (s[5], s[6])])
                    for x, y in pts:
                        xs.append(x); ys.append(y)
            out[ch] = {"contours": cs,
                       "bbox": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
                       "source": "v2.0.1 字体轮廓复刻"}
            print(ch, "contours", len(cs), "bbox", out[ch]["bbox"])
        else:
            print(ch, "缺失")
    json.dump(out, open(os.path.join(ROOT, "work/lead/contours_override.json"), "w"),
              ensure_ascii=False)
    print("override chars:", list(out))


if __name__ == "__main__":
    main()
