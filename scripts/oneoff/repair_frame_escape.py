#!/usr/bin/env python3
"""框线逃逸修复：对「块内逃逸框线像素≥25」的字，用新版版面元素 mask 重新矢量化并替换字形。

安全闸（逐字）：
  expected_removed = 块内「artifact mask ∩ 源二值墨」像素数（理论应被擦掉的量）
  keep 条件：new_ink >= old_ink - 1.6*expected_removed - 80 且 新旧 IoU >= 0.72
  否则回退旧字形（防误删真笔画）。
输出：新 TTF + 修复台账 JSONL。
"""
import argparse, json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def worker(args):
    page, half, items = args[0], args[1], args[2]
    import cv2
    import font_build as FB
    import font_norm as FN
    from page_artifacts import detect_page_artifacts
    from detect_blocks import page_gray
    from fidelity_eval import glyph_mask_from_font, register_iou
    out = []
    try:
        vol, pno = page.split("_")
        gray = page_gray(vol, int(pno))
        mask, _ = detect_page_artifacts(gray)
        lat = FB.get_page_lattice(page).get(half)
        tbb = FB.get_page_text_bbox(page)
    except Exception as e:
        return [(it["char"], None, f"prepare:{e}") for it in items]
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            # 源墨与理论擦除量（crop 坐标）
            crop = FN.render_pdf_crop(page, box, pad150=6, dpi=300)
            ink = FN.binarize(crop)
            ox = (box[0] - 6) * 2; oy = (box[1] - 6) * 2
            if block is not None:
                br = (int(round(block[0] * 2 - ox)), int(round(block[1] * 2 - oy)),
                      int(round(block[2] * 2 - ox)), int(round(block[3] * 2 - oy)))
            else:
                br = None
            sub = np.zeros_like(mask)
            x0, y0 = max(0, (box[0] - 6)), max(0, (box[1] - 6))
            x1, y1 = min(mask.shape[1], (box[2] + 6)), min(mask.shape[0], (box[3] + 6))
            sub = mask[y0:y1, x0:x1]
            sub = cv2.resize(sub, (ink.shape[1], ink.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            if br is not None:
                keep = np.zeros_like(sub); keep[br[1]:br[3], br[0]:br[2]] = True
                sub = sub & keep
            expected = int((sub & ink).sum())
            res = FN.vectorize_box(page, box, enable_edge_strip=False, char=ch,
                                   block150=block, frame_mask=mask)
            if not res.get("ok"):
                out.append((ch, None, "vectorize_fail")); continue
            old = glyph_mask_from_font(it["font"], ch)
            # 新字形光栅化（用 fontTools 临时字体太重；用轮廓栅格化近似）
            from fidelity_eval import glyph_mask_from_contours
            new = glyph_mask_from_contours(res["contours"])
            old_ink = int(old.sum()); new_ink = int(new.sum())
            iou, _ = register_iou(new, old) if old_ink else (0.0, 1.0)
            loss = old_ink - new_ink
            ok = (loss <= 1.6 * expected + 80) and (iou >= 0.72)
            out.append((ch, res["contours"] if ok else None,
                        {"old_ink": old_ink, "new_ink": new_ink, "expected": expected,
                         "iou": round(float(iou), 3), "ok": bool(ok)}))
        except Exception as e:
            out.append((ch, None, f"err:{e}"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--version", default="2.5.9")
    args = ap.parse_args()
    from fontTools.ttLib import TTFont
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    from font_build import orient_contours
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    scan = [json.loads(l) for l in open(os.path.join(ROOT, args.scan), encoding="utf-8")]
    scan = [s for s in scan if s.get("char") in man]
    jobs = {}
    for s in scan:
        box = man[s["char"]]["box"]
        jobs.setdefault((s["page"], s.get("half", "")), []).append(
            {"char": s["char"], "box": box, "font": os.path.join(ROOT, args.base)})
    jl = [(p, h, items) for (p, h), items in jobs.items()]
    results = {}
    logs = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(worker, jl, chunksize=2):
            for ch, contours, info in res:
                if contours is not None:
                    results[ch] = contours
                if isinstance(info, dict):
                    logs.append({"char": ch, **info})
    fonts = TTFont(os.path.join(ROOT, args.base), recalcTimestamp=False)
    glyf = fonts["glyf"]; cmap = fonts.getBestCmap()
    for ch, contours in results.items():
        gname = cmap[ord(ch)]
        tpen = TTGlyphPen(None); qpen = Cu2QuPen(tpen, max_err=1.0)
        for c, flip in orient_contours(contours):
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
    fonts.save(args.out)
    with open(os.path.join(ROOT, args.log), "w", encoding="utf-8") as fo:
        for l in logs:
            fo.write(json.dumps(l, ensure_ascii=False) + "\n")
    kept = len(results)
    print(json.dumps({"scanned": len(scan), "repaired": kept, "reverted": len(scan) - kept}))


if __name__ == "__main__":
    main()
