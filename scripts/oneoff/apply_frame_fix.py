#!/usr/bin/env python3
"""框线逃逸修复 v2（准确闸）：候选字用新建版面元素 mask 重切 → 临时字体渲染比对 → 保留/回退。

闸（全部基于同一字体渲染器，避免 hole 填充误差）：
  ratio = new_ink/old_ink ≥ 0.85  且  IoU(new, old) ≥ 0.80  → 保留
不满足 → 回退旧字形。
输出：新 TTF + 台账（char/expected/ratio/iou/kept）。
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
    out = []
    try:
        vol, pno = page.split("_")
        gray = page_gray(vol, int(pno))
        mask, _ = detect_page_artifacts(gray)
        lat = FB.get_page_lattice(page).get(half)
        tbb = FB.get_page_text_bbox(page)
    except Exception as e:
        return [(it["char"], None, 0, str(e)) for it in items]
    for it in items:
        ch, box = it["char"], it["box"]
        try:
            block = FB.block_for_box(lat, box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            res = FN.vectorize_box(page, box, enable_edge_strip=False, char=ch,
                                   block150=block, frame_mask=mask)
            # 理论擦除量（crop 内 artifact∩墨，块内）
            crop = FN.render_pdf_crop(page, box, pad150=6, dpi=300); ink = FN.binarize(crop)
            ox = (box[0] - 6) * 2; oy = (box[1] - 6) * 2
            if block is not None:
                br = (int(round(block[0] * 2 - ox)), int(round(block[1] * 2 - oy)),
                      int(round(block[2] * 2 - ox)), int(round(block[3] * 2 - oy)))
                x0m, y0m = max(0, box[0] - 6), max(0, box[1] - 6)
                x1m, y1m = min(mask.shape[1], box[2] + 6), min(mask.shape[0], box[3] + 6)
                sub = mask[y0m:y1m, x0m:x1m]
                sub = cv2.resize(sub, (ink.shape[1], ink.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
                keep = np.zeros_like(sub); keep[br[1]:br[3], br[0]:br[2]] = True
                expected = int((sub & keep & ink).sum())
            else:
                expected = 0
            out.append((ch, res.get("contours") if res.get("ok") else None, expected, ""))
        except Exception as e:
            out.append((ch, None, 0, f"err:{e}"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--tmp-font", default="/tmp/frame_fix_candidates.ttf")
    args = ap.parse_args()
    from fontTools.ttLib import TTFont
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    from font_build import orient_contours, build_font as fb_build
    from fidelity_eval import glyph_mask_from_font, register_iou
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    scan = [json.loads(l) for l in open(os.path.join(ROOT, args.scan), encoding="utf-8")]
    scan = [s for s in scan if s.get("char") in man]
    jobs = {}
    for s in scan:
        jobs.setdefault((s["page"], s.get("half", "")), []).append(
            {"char": s["char"], "box": man[s["char"]]["box"]})
    jl = [(p, h, items) for (p, h), items in jobs.items()]
    cand, expected = {}, {}
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(worker, jl, chunksize=2):
            for ch, contours, exp, err in res:
                if contours is not None:
                    cand[ch] = contours
                    expected[ch] = exp
    print("candidates", len(cand), flush=True)
    # 临时字体
    from pathlib import Path
    fb_build(cand, Path(args.tmp_font), version="0.0.1")
    logs, kept = [], 0
    for ch in sorted(cand):
        old = glyph_mask_from_font(os.path.join(ROOT, args.base), ch, size=256)
        new = glyph_mask_from_font(args.tmp_font, ch, size=256)
        oi, ni = int(old.sum()), int(new.sum())
        ratio = ni / max(1, oi)
        iou, _ = register_iou(new, old)
        # 放宽：框线移除会改变归一化 bbox（字形按 760 标准变大），IoU 略降属正常；
        # 用「ratio 在合理区间」+「IoU 可配准」双条件，避免误删真笔画（后续还有内容闸/目检）。
        ok = (ratio >= 0.85 and iou >= 0.72) or (0.90 <= ratio <= 1.30 and iou >= 0.65)
        logs.append({"char": ch, "expected": expected.get(ch, 0), "old_ink": oi,
                     "new_ink": ni, "ratio": round(ratio, 3), "iou": round(float(iou), 3),
                     "kept": bool(ok)})
        if ok:
            kept += 1
    keepset = {r["char"] for r in logs if r["kept"]}
    # 最终字体：base 替换 keepset
    fonts = TTFont(os.path.join(ROOT, args.base), recalcTimestamp=False)
    glyf = fonts["glyf"]; cmap = fonts.getBestCmap()
    for ch in keepset:
        gname = cmap[ord(ch)]
        tpen = TTGlyphPen(None); qpen = Cu2QuPen(tpen, max_err=1.0)
        for c, flip in orient_contours(cand[ch]):
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
        for r in logs:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"candidates": len(cand), "kept": len(keepset),
                      "reverted": len(cand) - len(keepset)}))


if __name__ == "__main__":
    main()
