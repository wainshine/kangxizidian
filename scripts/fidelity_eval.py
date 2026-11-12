#!/usr/bin/env python3
"""保真度评测：字形 vs 原书墨迹（box+pad 裁片的二值墨）的配准 IoU。
用于衡量「类级修复」（主簇归一 + 像素级参考过滤 + 细线删除）是否真的让字形更贴近原书墨迹。"""
import json, os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work/font/_pylibs"))
import font_norm as FN


def flatten_contour(c, samples=8):
    """把 ['start' + segs(L/C)] 展平成像素点（C 为三次贝塞尔，de Casteljau 采样）。"""
    pts = [tuple(c["start"])]
    cur = pts[0]
    for s in c["segs"]:
        if s[0] == "L":
            cur = (s[1], s[2]); pts.append(cur)
            continue
        p0 = cur
        p1 = (s[1], s[2]); p2 = (s[3], s[4]); p3 = (s[5], s[6])
        for i in range(1, samples + 1):
            t = i / samples
            u = 1 - t
            x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
            y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
            pts.append((x, y))
        cur = p3
    return pts


def glyph_mask_from_contours(contours, size=256):
    SCALE = size / 1000.0
    BASELINE = int(0.88 * size)
    canvas = np.zeros((size, size), np.uint8)
    for c in contours:
        pts = flatten_contour(c)
        px = [(x * SCALE, BASELINE - y * SCALE) for x, y in pts]
        poly = np.array([[int(round(a)), int(round(b))] for a, b in px], np.int32)
        cv2.fillPoly(canvas, [poly], 1)
    return canvas.astype(bool)


from functools import lru_cache


@lru_cache(maxsize=64)
def _font_obj(path, size):
    from PIL import ImageFont
    return ImageFont.truetype(path, size)


def glyph_mask_from_font(font_path, ch, size=256):
    from PIL import Image, ImageDraw
    f = _font_obj(font_path, size)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def source_ink(page, box, pad=6, size=256):
    gray = FN.render_pdf_crop(page, box, pad150=pad, dpi=300)
    ink = FN.remove_specks(FN.binarize(gray))
    ink = FN.strip_border_lines(ink)
    return ink


def register_iou(a, b):
    """把 a 按主组件配准到 b 后计算 IoU（返回 (iou, scale)）。"""
    def comps(m):
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        out = [{"id": i, "bbox": (st[i, 0], st[i, 1], st[i, 0] + st[i, 2], st[i, 1] + st[i, 3]),
                "area": int(st[i, 4])} for i in range(1, n) if st[i, 4] >= 12]
        return lab, out
    la, ca = comps(a); lb, cb = comps(b)
    if not ca or not cb:
        return 0.0, 1.0
    ma = max(ca, key=lambda c: c["area"]); mb = max(cb, key=lambda c: c["area"])
    cc = lambda bb: ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
    c1, c2 = cc(ma["bbox"]), cc(mb["bbox"])
    l1 = max(ma["bbox"][2] - ma["bbox"][0], ma["bbox"][3] - ma["bbox"][1])
    l2 = max(mb["bbox"][2] - mb["bbox"][0], mb["bbox"][3] - mb["bbox"][1])
    s = l2 / max(1.0, l1)
    M = np.array([[s, 0, c2[0] - s * c1[0]], [0, s, c2[1] - s * c1[1]]], np.float32)
    aw = cv2.warpAffine(a.astype(np.uint8), M, (b.shape[1], b.shape[0]), flags=cv2.INTER_NEAREST) > 0
    inter = int((aw & b).sum()); union = int((aw | b).sum())
    return inter / max(1, union), s


def clean_target(page, box, ch):
    """污染无关的目标墨迹：原书墨 ∩ 参考结构支持域（参考无对应墨迹的碎片被剔除）。"""
    import numpy as np, cv2
    from refgate import ref_has
    src = source_ink(page, box)
    if not ref_has(ch):
        return src
    ref = None
    try:
        from refgate import SONGTI
        from PIL import Image, ImageDraw, ImageFont
        f = ImageFont.truetype(SONGTI, 256, index=7)
        im = Image.new("L", (256, 256), 0)
        ImageDraw.Draw(im).text((128, int(0.88 * 256)), ch, fill=255, font=f, anchor="ms")
        ref = np.array(im) > 127
    except Exception:
        return src

    def comps(m):
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        out = [{"bbox": (st[i, 0], st[i, 1], st[i, 0] + st[i, 2], st[i, 1] + st[i, 3]),
                "area": int(st[i, 4])} for i in range(1, n) if st[i, 4] >= 12]
        return out

    cs = comps(src); cr = comps(ref)
    if not cs or not cr:
        return src
    ma = max(cs, key=lambda c: c["area"]); mr = max(cr, key=lambda c: c["area"])
    cc = lambda b: ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    c1, c2 = cc(ma["bbox"]), cc(mr["bbox"])
    l1 = max(ma["bbox"][2] - ma["bbox"][0], ma["bbox"][3] - ma["bbox"][1])
    l2 = max(mr["bbox"][2] - mr["bbox"][0], mr["bbox"][3] - mr["bbox"][1])
    sc = l2 / max(1.0, l1)
    M = np.array([[sc, 0, c2[0] - sc * c1[0]], [0, sc, c2[1] - sc * c1[1]]], np.float32)
    rw = cv2.warpAffine(ref.astype(np.uint8), M, (src.shape[1], src.shape[0]),
                        flags=cv2.INTER_NEAREST)
    support = cv2.dilate(rw, np.ones((11, 11), np.uint8)) > 0
    target = src & support
    if target.sum() < 0.3 * src.sum():
        return src
    return target


def main():
    font = sys.argv[1]
    pos_path = sys.argv[2] if len(sys.argv) > 2 else "work/review/owner-marks-compare.json"
    out = sys.argv[3] if len(sys.argv) > 3 else "work/review/fidelity-eval.json"
    rows = [r for r in json.load(open(os.path.join(ROOT, pos_path), encoding="utf-8")) if r["in_current"]]
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]
    import random as _r
    _r.seed(11)
    neg = _r.sample([c for c in sorted(man) if c not in {r["char"] for r in rows}], 200)
    res = {"positives": [], "negatives": []}
    for grp, chars in (("positives", [r["char"] for r in rows]), ("negatives", neg)):
        for ch in chars:
            r = man[ch]
            src = source_ink(r["page"], r["box"])
            g = glyph_mask_from_font(font, ch)
            iou, s = register_iou(g, src)
            res[grp].append({"char": ch, "page": r["page"], "box": r["box"],
                             "iou": round(iou, 3), "scale": round(s, 3)})
    for grp in ("positives", "negatives"):
        ious = [x["iou"] for x in res[grp]]
        res[grp + "_summary"] = {"n": len(ious), "mean": round(float(np.mean(ious)), 3),
                                 "median": round(float(np.median(ious)), 3),
                                 "p10": round(float(np.percentile(ious, 10)), 3)}
    json.dump(res, open(os.path.join(ROOT, out), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("positives_summary", "negatives_summary")}))


if __name__ == "__main__":
    main()
