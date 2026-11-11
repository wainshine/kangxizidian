#!/usr/bin/env python3
"""切偏体检：成品字形墨迹中心 vs 2×2 格块中心的偏移（以格距为单位）。"""
import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items, font = args[0], args[1], args[2], args[3]
    import cv2
    import font_build as FB
    import font_norm as FN
    from fidelity_eval import glyph_mask_from_font
    lat = FB.get_page_lattice(page).get(half)
    tbb = FB.get_page_text_bbox(page)
    out = []
    if not lat:
        return out
    px, py, phx, phy = lat
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            gray = FN.render_pdf_crop(page, box, pad150=6, dpi=300)
            src = FN.binarize(gray)
            gm = glyph_mask_from_font(font, ch)
            def comps(m):
                n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
                return [(st[i, 0], st[i, 1], st[i, 0] + st[i, 2], st[i, 1] + st[i, 3], int(st[i, 4]))
                        for i in range(1, n) if st[i, 4] >= 20]
            cs = comps(src); cg = comps(gm)
            if not cs or not cg:
                continue
            ms = max(cs, key=lambda c: c[4]); mg = max(cg, key=lambda c: c[4])
            cc = lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            c1, c2 = cc(mg), cc(ms)
            l1 = max(mg[2] - mg[0], mg[3] - mg[1]); l2 = max(ms[2] - ms[0], ms[3] - ms[1])
            sc = l2 / max(1.0, l1)
            M = np.array([[sc, 0, c2[0] - sc * c1[0]], [0, sc, c2[1] - sc * c1[1]]], np.float32)
            gys, gxs = np.nonzero(gm)
            gw = cv2.warpAffine(gm.astype(np.uint8), M, (src.shape[1], src.shape[0]),
                               flags=cv2.INTER_NEAREST) > 0
            ys, xs = np.nonzero(gw)
            if len(xs) == 0:
                continue
            # 统一用 crop 坐标（300dpi）：crop 原点 = (box[0]-6, box[1]-6)@150dpi
            gcx = xs.mean()
            gcy = ys.mean()
            b_cx = (block[2] + block[0]) - 2 * (box[0] - 6)
            b_cy = (block[3] + block[1]) - 2 * (box[1] - 6)
            # b_cx 单位：150dpi*2 = 300dpi? block 是 150dpi；crop 坐标 = (page150 - box0+6)*2
            b_cx = ((block[2] + block[0]) / 2.0 - (box[0] - 6)) * 2
            b_cy = ((block[3] + block[1]) / 2.0 - (box[1] - 6)) * 2
            dx = (gcx - b_cx) / (px * 2)     # 单位：格宽（crop 是 300dpi，1 格=2*px）
            dy = (gcy - b_cy) / (py * 2)
            off = max(abs(dx), abs(dy))
            if off > 0.18:
                out.append({"char": ch, "page": page, "half": half, "box": box,
                            "dx": round(float(dx), 3), "dy": round(float(dy), 3),
                            "off": round(float(off), 3)})
        except Exception:
            pass
    return out


def main():
    font, man_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    by_page = {}
    for ch, r in man.items():
        by_page.setdefault((r["page"], r.get("half", "L")), []).append({"char": ch, "box": r["box"]})
    jobs = [(p, h, items, font) for (p, h), items in by_page.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(worker, jobs, chunksize=2):
            rows.extend(res)
    rows.sort(key=lambda r: -r["off"])
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"offset_gt_0.18cell": len(rows),
                      "gt_0.35cell": sum(1 for r in rows if r["off"] > 0.35),
                      "top": [f"{r['char']}:{r['off']}" for r in rows[:12]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
