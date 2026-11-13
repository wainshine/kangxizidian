#!/usr/bin/env python3
"""类级修复：重建 mapping box（单一真源），消除「字体层修复不回写 mapping」的根因。

对每个字：
 1) 2×2 格块（lattice）→ 裁片（300dpi，pad 6）；
 2) 版框本地规则：trim_crop_frame_edges + strip_crop_frame_bands（只删贯穿裁片边界的框线带）；
 3) 取块内最近主簇（最大组件 + 距其 ≤ 半格的组件）→ 墨迹 bbox 外扩 4px → 新 box（150dpi）；
 4) 新 box 用 content quad 钳制（不越出版框正文区），并做合理性检查（面积/长宽/覆盖）；
 5) 输出 mapping_v270.jsonl（格式同 mapping33，label_source 保留）。
运行：每页一次渲染，页级并行。
"""
import argparse, json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items = args
    import cv2
    import font_build as fb
    import font_norm as FN
    from page_frames import detect_content_quads, clip_mask_page
    from detect_blocks import page_gray
    import fitz
    out = []
    try:
        quads = detect_content_quads(page_gray(page[:2], int(page[3:])))
        lat = fb.get_page_lattice(page).get(half)
        tbb = fb.get_page_text_bbox(page)
        quad = quads.get(half)
        # 渲染整页 300dpi 一次（本半版全部字共用）
        import json as _json
        mp = _json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
        vol = page[:2]
        doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = doc[int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        page300 = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        doc.close()
    except Exception as e:
        return [(it["char"], None, f"prepare:{e}") for it in items]
    for it in items:
        ch, old_box = it["char"], it["box"]
        try:
            block = fb.block_for_box(lat, old_box)
            if block is None:
                out.append((ch, None, "no block")); continue
            if tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            x0, y0, x1, y1 = [int(round(v * 2)) for v in block]
            pad = 12
            sx0, sy0 = max(0, x0 - pad), max(0, y0 - pad)
            sx1, sy1 = min(page300.shape[1], x1 + pad), min(page300.shape[0], y1 + pad)
            crop = page300[sy0:sy1, sx0:sx1]
            ink = FN.binarize(crop)
            ink = FN.trim_crop_frame_edges(ink)
            ink = FN.strip_crop_frame_bands(ink)
            # 只保留 block 内
            bx0, by0 = x0 - sx0, y0 - sy0
            bx1, by1 = x1 - sx0, y1 - sy0
            keep = np.zeros_like(ink); keep[max(0, by0):by1, max(0, bx0):bx1] = True
            ink = ink & keep
            n, lab, st, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
            comps = [(st[i, 0], st[i, 1], st[i, 0] + st[i, 2], st[i, 1] + st[i, 3], int(st[i, 4]))
                     for i in range(1, n) if st[i, 4] >= 15]
            if not comps:
                out.append((ch, None, "no comps")); continue
            main = max(comps, key=lambda c: c[4])
            cell = min(block[2] - block[0], block[3] - block[1]) / 2.0 * 2  # 150dpi
            sel = [c for c in comps
                   if c[4] >= 0.05 * main[4] and
                   not (c[2] < main[0] - cell or c[0] > main[2] + cell or
                        c[3] < main[1] - cell or c[1] > main[3] + cell)]
            bx = [min(c[0] for c in sel), min(c[1] for c in sel),
                  max(c[2] for c in sel), max(c[3] for c in sel)]
            # 换算回 150dpi 页坐标，外扩 4px（300dpi→150dpi: /2）
            nb = [sx0 / 2.0 + bx[0] / 2.0 - 4, sy0 / 2.0 + bx[1] / 2.0 - 4,
                  sx0 / 2.0 + bx[2] / 2.0 + 4, sy0 / 2.0 + bx[3] / 2.0 + 4]
            if quad is not None:
                q = quad["box"]
                nb = [max(nb[0], q[0] + 2), max(nb[1], q[1] + 2),
                      min(nb[2], q[2] - 2), min(nb[3], q[3] - 2)]
            nb = [float(round(v)) for v in nb]
            if nb[2] - nb[0] < 40 or nb[3] - nb[1] < 40:
                out.append((ch, None, "box too small")); continue
            out.append((ch, nb, ""))
        except Exception as e:
            out.append((ch, None, f"err:{e}"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    rows = [json.loads(l) for l in open(os.path.join(ROOT, args.mapping), encoding="utf-8")]
    jobs = {}
    for r in rows:
        items = []
        for a in r.get("assigned", []):
            ch = a.get("char"); cand = a.get("cand") or {}
            box = cand.get("box") or a.get("box")
            if ch and box:
                items.append({"char": ch, "box": box})
        if items:
            jobs.setdefault((r["page"], r.get("half", "")), []).extend(items)
    jl = [(p, h, items) for (p, h), items in jobs.items()]
    newmap, log = {}, []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(worker, jl, chunksize=2):
            for ch, nb, err in res:
                if nb is not None:
                    newmap[ch] = nb
                else:
                    log.append({"char": ch, "error": err})
    changed = 0
    out_rows = []
    for r in rows:
        assigned = []
        for a in r.get("assigned", []):
            a2 = dict(a)
            ch = a.get("char")
            if ch in newmap:
                cand = dict(a.get("cand") or {})
                old = cand.get("box") or a.get("box")
                if old != newmap[ch]:
                    changed += 1
                cand["box"] = newmap[ch]
                a2["cand"] = cand
            assigned.append(a2)
        r2 = dict(r); r2["assigned"] = assigned
        out_rows.append(r2)
    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as fo:
        for r in out_rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(ROOT, args.log), "w", encoding="utf-8") as fo:
        for l in log:
            fo.write(json.dumps(l, ensure_ascii=False) + "\n")
    print(json.dumps({"glyphs": len(newmap), "changed_boxes": changed, "errors": len(log)}))


if __name__ == "__main__":
    main()
