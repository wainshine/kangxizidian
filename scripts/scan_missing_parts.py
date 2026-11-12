#!/usr/bin/env python3
"""全库缺部件扫描（类级）：源块墨迹中未被成品字形覆盖的「字身部件」。

判据（与 repair_missing_chars 一致）：面积≥1% 块墨量、最短边≥8px、距主组件≤18px、覆盖率<0.45。
输出 work/lead/missing_parts_scan.jsonl
"""

# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass



import json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items = args[0], args[1], args[2]
    font = args[3]
    import cv2
    import font_build as FB
    import font_norm as FN
    from fidelity_eval import glyph_mask_from_font
    out = []
    try:
        lat = FB.get_page_lattice(page).get(half)
        tbb = FB.get_page_text_bbox(page)
        quads = FB.get_page_content_quads(page)
        quad = quads.get(half)
    except Exception as e:
        # fail-closed：页级准备失败要落成 error 行（release_gate 计入 flagged），不能静默丢样
        return [{"char": it["char"], "page": page, "half": half, "box": it["box"],
                 "error": f"prepare:{str(e)[:100]}"} for it in items]
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            gray = FN.render_pdf_crop(page, box, pad150=6, dpi=300)
            src = FN.binarize(gray)
            # 与构建同一口径：content clip + 裁片框线带排除；只比较 block 区域
            if quad is not None:
                from page_frames import clip_mask_page
                cm = clip_mask_page(gray.shape, (box[0] - 6, box[1] - 6), quad)
                src = src & cm
            src = FN.trim_crop_frame_edges(src)
            src = FN.strip_crop_frame_bands(src)
            bx0 = int(round((block[0] - (box[0] - 6)) * 2)) if block else 0
            by0 = int(round((block[1] - (box[1] - 6)) * 2)) if block else 0
            bx1 = int(round((block[2] - (box[0] - 6)) * 2)) if block else src.shape[1]
            by1 = int(round((block[3] - (box[1] - 6)) * 2)) if block else src.shape[0]
            bx0, by0 = max(0, bx0), max(0, by0)
            bx1, by1 = min(src.shape[1], bx1), min(src.shape[0], by1)
            gm = glyph_mask_from_font(font, ch)
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
            # 参考字体（霞鹜文楷 OFL）对齐到源图：用于判断「缺失组件是否属于该字」
            ref_ok = True
            try:
                from reffont import raster as _ref_raster
                ref = _ref_raster(ch, 256)
                rn, rl, rst, _ = cv2.connectedComponentsWithStats(ref.astype(np.uint8), 8)
                rc = [(rst[i, 0], rst[i, 1], rst[i, 0] + rst[i, 2], rst[i, 1] + rst[i, 3], int(rst[i, 4]))
                      for i in range(1, rn) if rst[i, 4] >= 20]
                if rc:
                    rm = max(rc, key=lambda c: c[4])
                    rc1, rc2 = cc(rm), cc(ms)
                    rl1 = max(rm[2] - rm[0], rm[3] - rm[1]); rl2 = max(ms[2] - ms[0], ms[3] - ms[1])
                    rsc = rl2 / max(1.0, rl1)
                    RM = np.array([[rsc, 0, rc2[0] - rsc * rc1[0]], [0, rsc, rc2[1] - rsc * rc1[1]]], np.float32)
                    rwarp = cv2.warpAffine(ref.astype(np.uint8), RM, (src.shape[1], src.shape[0]),
                                           flags=cv2.INTER_NEAREST) > 0
                    rd = cv2.dilate(rwarp.astype(np.uint8), np.ones((11, 11), np.uint8)) > 0
                else:
                    ref_ok = False
            except Exception:
                ref_ok = False
            block_ink = int(src[by0:by1, bx0:bx1].sum())
            total = max(1, block_ink)
            miss = []
            for (x0, y0, x1, y1, a) in cs:
                if a < 0.010 * total:
                    continue
                mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                if not (bx0 - 6 <= mx <= bx1 + 6 and by0 - 6 <= my <= by1 + 6):
                    continue
                ww, hh = x1 - x0 + 1, y1 - y0 + 1
                if min(ww, hh) < 8:
                    continue
                dxg = max(0, max(ms[0], x0) - min(ms[2], x1))
                dyg = max(0, max(ms[1], y0) - min(ms[3], y1))
                if dxg > 18 or dyg > 18:
                    continue
                reg = src[y0:y1 + 1, x0:x1 + 1]
                cov = float((reg & gd[y0:y1 + 1, x0:x1 + 1]).sum()) / max(1, int(reg.sum()))
                if cov < 0.45:
                    if not ref_ok:
                        # 参考字体不可用：fail-closed，不把组件算作缺件（单列披露）
                        ref_unavailable += 1
                        continue
                    reg = rd[y0:y1 + 1, x0:x1 + 1]
                    refcov = float(reg.sum()) / max(1, reg.size)
                    if refcov < 0.25:   # 参考字体在此处也没有墨 → 邻字/注文，不是字身部件
                        continue
                    miss.append([int(x0), int(y0), int(x1), int(y1), int(a)])
            if miss:
                row = {"char": ch, "page": page, "half": half, "box": box, "missing": miss}
                if ref_unavailable:
                    row["ref_unavailable"] = ref_unavailable
                out.append(row)
        except Exception as e:
            out.append({"char": ch, "error": str(e)[:80]})
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
    rows.sort(key=lambda r: str(r.get("char")))
    out_abs = out_path if os.path.isabs(out_path) else os.path.join(ROOT, out_path)
    with open(out_abs, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    # 输入绑定 sidecar：复用前必须校验（参考字体/几何/脚本变化都会让旧扫描失效）
    import gate_binding as GB
    binding = GB.build_binding(
        files={"font": font, "manifest": man_path},
        scripts=["scan_missing_parts.py", "reffont.py", "refgate.py", "font_build.py",
                 "font_norm.py", "page_frames.py", "fidelity_eval.py"],
        include_reffont=True)
    GB.write_sidecar(out_abs, binding)
    n_missing = sum(1 for r in rows if r.get("missing"))
    n_error = sum(1 for r in rows if r.get("error"))
    print(json.dumps({"pages": len(jobs), "flagged": n_missing, "error": n_error,
                      "rows": len(rows), "binding": GB.sidecar_path(out_abs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
