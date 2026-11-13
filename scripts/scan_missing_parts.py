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
            pad = int(it.get("spad") or 6)
            gray = FN.render_pdf_crop(page, box, pad150=pad, dpi=300)
            src = FN.binarize(gray)
            # 与构建同一口径：content clip + 裁片框线带排除；只比较 block 区域
            if quad is not None:
                from page_frames import clip_mask_page
                cm = clip_mask_page(gray.shape, (box[0] - pad, box[1] - pad), quad)
                src = src & cm
            src = FN.trim_crop_frame_edges(src)
            src = FN.strip_crop_frame_bands(src)
            # E32：与构建同口径 pre-cut（页级长线/细线 mask + 已验证线条带），避免把已排除框线当缺件
            from precut_masks import apply_precut_masks
            src = apply_precut_masks(src, page, box, pad150=pad, block150=block)
            bx0 = int(round((block[0] - (box[0] - pad)) * 2)) if block else 0
            by0 = int(round((block[1] - (box[1] - pad)) * 2)) if block else 0
            bx1 = int(round((block[2] - (box[0] - pad)) * 2)) if block else src.shape[1]
            by1 = int(round((block[3] - (box[1] - pad)) * 2)) if block else src.shape[0]
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
            # 配准（E36）：复刻构建的最终墨迹链（block 掩膜 -> remove_specks -> clean_cluster ->
            # clean_ink），得到与 normalize 完全相同的像素 bbox，再把字形 mask 精确对齐。
            gys, gxs = np.nonzero(gm)
            if len(gxs) == 0:
                continue
            gx0, gy0, gx1, gy1 = int(gxs.min()), int(gys.min()), int(gxs.max()), int(gys.max())
            block_rect = (bx0, by0, bx1, by1)
            pad_px = pad * 2  # 300dpi：box 在 crop 中的矩形（build 的 center 口径）
            center = (pad_px, pad_px, src.shape[1] - pad_px, src.shape[0] - pad_px)
            ink_final = FN.mask_to_block(src, block_rect)
            ink_final = FN.remove_specks(ink_final)
            ink_final = FN.clean_cluster(ink_final, box=center)
            ink_final = FN.clean_ink(ink_final, center=center)
            tys, txs = np.nonzero(ink_final)
            if len(txs) == 0:
                continue
            tsx0, tsy0, tsx1, tsy1 = int(txs.min()), int(tys.min()), int(txs.max()) + 1, int(tys.max()) + 1
            sw = max(1, tsx1 - tsx0); sh = max(1, tsy1 - tsy0)
            gw0 = max(1, gx1 - gx0); gh0 = max(1, gy1 - gy0)
            tb_font = it.get("tbbox"); sb_em = it.get("sbbox")
            if tb_font and sb_em and (tb_font[2] - tb_font[0]) > 0:
                # 画布变换：font units -> 256 画布（由 TTF bbox 与画布 mask bbox 反推）
                sc = (gx1 - gx0) / float(max(1, tb_font[2] - tb_font[0]))
                def fx_canvas(x): return gx0 + (x - tb_font[0]) * sc
                def fy_canvas(y): return gy1 - (y - tb_font[1]) * sc
                scx0, scx1 = fx_canvas(sb_em[0]), fx_canvas(sb_em[2])
                scy0, scy1 = fy_canvas(sb_em[3]), fy_canvas(sb_em[1])  # top,bottom
                if scx1 - scx0 > 5 and scy1 - scy0 > 5:
                    msx = (tsx1 - tsx0) / (scx1 - scx0)
                    msy = (tsy1 - tsy0) / (scy1 - scy0)
                    M = np.array([[msx, 0, tsx0 - msx * scx0],
                                  [0, msy, tsy0 - msy * scy0]], np.float32)
                else:
                    M = np.array([[sw / float(gw0), 0, tsx0 - (sw / float(gw0)) * gx0],
                                  [0, sh / float(gh0), tsy0 - (sh / float(gh0)) * gy0]], np.float32)
            else:
                sx = sw / float(gw0); sy = sh / float(gh0)
                M = np.array([[sx, 0, tsx0 - sx * gx0], [0, sy, tsy0 - sy * gy0]], np.float32)
            gw = cv2.warpAffine(gm.astype(np.uint8), M, (src.shape[1], src.shape[0]),
                               flags=cv2.INTER_NEAREST) > 0
            gd = cv2.dilate(gw.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
            # 参考字体（霞鹜文楷 OFL）同口径对齐：整字 bbox -> 主簇 bbox
            ref_ok = True
            try:
                from reffont import raster as _ref_raster
                ref = _ref_raster(ch, 256)
                rys, rxs = np.nonzero(ref)
                if len(rxs) == 0:
                    ref_ok = False
                else:
                    rx0, ry0, rx1, ry1 = int(rxs.min()), int(rys.min()), int(rxs.max()), int(rys.max())
                    rw0 = max(1, rx1 - rx0); rh0 = max(1, ry1 - ry0)
                    rsx = sw / float(rw0); rsy = sh / float(rh0)
                    RM = np.array([[rsx, 0, tsx0 - rsx * rx0], [0, rsy, tsy0 - rsy * ry0]], np.float32)
                    _ = (rx1, ry0)  # ref 配准只用于 refcov 粗判，保持 bbox 口径
                    rwarp = cv2.warpAffine(ref.astype(np.uint8), RM, (src.shape[1], src.shape[0]),
                                           flags=cv2.INTER_NEAREST) > 0
                    rd = cv2.dilate(rwarp.astype(np.uint8), np.ones((11, 11), np.uint8)) > 0
            except Exception:
                ref_ok = False
            block_ink = int(src[by0:by1, bx0:bx1].sum())
            total = max(1, block_ink)
            miss = []
            ref_unavailable = 0
            for (x0, y0, x1, y1, a) in cs:
                if a < 0.010 * total:
                    continue
                mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                if not (bx0 - 6 <= mx <= bx1 + 6 and by0 - 6 <= my <= by1 + 6):
                    continue
                ww, hh = x1 - x0 + 1, y1 - y0 + 1
                if min(ww, hh) < 8:
                    continue
                dxg = max(0, max(tsx0, x0) - min(tsx1, x1))
                dyg = max(0, max(tsy0, y0) - min(tsy1, y1))
                if dxg > 18 or dyg > 18:
                    continue
                reg = src[y0:y1 + 1, x0:x1 + 1]
                cov = float((reg & gd[y0:y1 + 1, x0:x1 + 1]).sum()) / max(1, int(reg.sum()))
                # E36：只有「被构建管线保留为字身墨（ink_final）」的组件才算缺件；
                # 管线按设计丢弃的块内邻墨/注文残片不算（否则会把注释当缺笔）。
                reg_fin = ink_final[y0:y1 + 1, x0:x1 + 1]
                fin_frac = float(reg_fin.sum()) / max(1, int(reg.sum()))
                if fin_frac < 0.60:
                    continue
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
    # E36：用 build_stats 的逐字「管线最终墨迹 bbox（build crop 像素坐标）」做精确配准，
    # 避免最大组件/主簇 bbox 配准的歧义（E35 后仍有大量误报）。
    stats_path = sys.argv[4] if len(sys.argv) > 4 else os.path.splitext(font)[0] + ".build_stats.json"
    stats_g = {}
    if stats_path and os.path.exists(stats_path):
        try:
            stats_g = json.load(open(stats_path, encoding="utf-8")).get("glyphs") or {}
        except Exception:
            stats_g = {}
    # E36：加载 TTF 字形 bbox（font units），用于「字形在 256 画布中的精确位置」
    # 与 stats bbox（normalize 口径，prune 前）配合，处理 prune_edge_contours 造成的 bbox 差。
    font_bbox = {}
    try:
        sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
        from fontTools.ttLib import TTFont
        _f = TTFont(font if os.path.isabs(font) else os.path.join(ROOT, font))
        _cmap = _f.getBestCmap()
        for _cp, _gname in _cmap.items():
            try:
                _gl = _f["glyf"][_gname]
                font_bbox[chr(_cp)] = (_gl.xMin, _gl.yMin, _gl.xMax, _gl.yMax)
            except Exception:
                pass
        _f.close()
    except Exception:
        font_bbox = {}
    by_page = {}
    for ch, r in man.items():
        st = stats_g.get(ch) or {}
        by_page.setdefault((r["page"], r.get("half", "L")), []).append(
            {"char": ch, "box": r["box"], "sbbox": st.get("bbox"), "spad": st.get("pad150"),
             "tbbox": font_bbox.get(ch)})
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
        files={"font": font, "manifest": man_path,
               "geometry": "work/lead/page_geometry.jsonl",
               "page_line_bands": "work/lead/page_line_bands.json",
               "build_stats": stats_path if (stats_path and os.path.exists(stats_path)) else None},
        scripts=["scan_missing_parts.py", "precut_masks.py", "reffont.py", "refgate.py",
                 "font_build.py", "font_norm.py", "page_frames.py", "fidelity_eval.py"],
        include_reffont=True)
    GB.write_sidecar(out_abs, binding)
    n_missing = sum(1 for r in rows if r.get("missing"))
    n_error = sum(1 for r in rows if r.get("error"))
    print(json.dumps({"pages": len(jobs), "flagged": n_missing, "error": n_error,
                      "rows": len(rows), "binding": GB.sidecar_path(out_abs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
