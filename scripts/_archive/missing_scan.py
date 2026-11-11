#!/usr/bin/env python3
"""缺笔画（类 B）检测：源块墨迹中「成品字形没有覆盖」的组件 = 被删/被切掉的真笔画。"""
import json, os, sys
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def job(items):
    from font_norm import render_pdf_crop, binarize
    from fidelity_eval import glyph_mask_from_font
    font, rows = items
    out = []
    for ch, page, box in rows:
        try:
            gray = render_pdf_crop(page, box, pad150=4, dpi=300)
            src = binarize(gray)
            g = glyph_mask_from_font(font, ch)
            # 配准 glyph -> src（主组件）
            def comps(m):
                n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
                return lab, [(st[i, 0], st[i, 1], st[i, 0]+st[i, 2], st[i, 1]+st[i, 3], int(st[i, 4]))
                             for i in range(1, n) if st[i, 4] >= 20]
            _, cs = comps(src); _, cg = comps(g)
            if not cs or not cg:
                continue
            ms = max(cs, key=lambda c: c[4]); mg = max(cg, key=lambda c: c[4])
            cc = lambda b: ((b[0]+b[2])/2, (b[1]+b[3])/2)
            c1, c2 = cc(mg), cc(ms)
            l1 = max(mg[2]-mg[0], mg[3]-mg[1]); l2 = max(ms[2]-ms[0], ms[3]-ms[1])
            sc = l2 / max(1.0, l1)
            M = np.array([[sc, 0, c2[0]-sc*c1[0]], [0, sc, c2[1]-sc*c1[1]]], np.float32)
            gw = cv2.warpAffine(g.astype(np.uint8), M, (src.shape[1], src.shape[0]),
                                flags=cv2.INTER_NEAREST) > 0
            gd = cv2.dilate(gw.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
            lab, cs2 = comps(src)
            total = int(src.sum())
            missing = 0
            for (x0, y0, x1, y1, a) in cs:
                if a < 0.004 * total:
                    continue
                comp = np.zeros_like(src, bool)
                comp[y0:y1+1, x0:x1+1] = src[y0:y1+1, x0:x1+1] > 0
                # 精确用组件 id 更稳，这里用 bbox 近似即可
                cov = float((comp & gd).sum()) / max(1, a)
                if cov < 0.5:
                    missing += 1
            if missing:
                out.append({"char": ch, "missing": missing})
        except Exception:
            pass
    return out


def main():
    font = sys.argv[1]
    man_path = sys.argv[2]
    sample_n = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    out_path = sys.argv[4]
    import random
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    extra = "嵇癡輘黯馻蜟聾儢糈峸貔滯襲刲意"
    chars = list(extra) + list(man.keys())
    seen = set(); rows = []
    for c in chars:
        if c in seen or c not in man:
            continue
        seen.add(c)
        r = man[c]
        rows.append((c, r["page"], r["box"]))
        if len(rows) >= sample_n:
            break
    n = max(1, (len(rows) + 7) // 8)
    chunks = [(font, rows[i:i+n]) for i in range(0, len(rows), n)]
    out = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(job, chunks):
            out.extend(res)
    json.dump(out, open(os.path.join(ROOT, out_path), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"n": len(rows), "missing_glyphs": len(out),
                      "sample": out[:12]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
