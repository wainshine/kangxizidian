#!/usr/bin/env python3
"""像素级参考过滤（类级修复）：在矢量化之前，用「参考字体同字」把 crop 里
「参考结构没有对应墨迹」的组件删除；主簇 bbox 用于配准与归一化。

这是一类问题的统一解：碎片/邻墨/框线残片（参考无对应）→ 像素级删除；
缺笔（参考有、crop 无）→ 记为 box 错误类，交重定位。
"""
import os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work/font/_pylibs"))
from refgate import ref_has, SONGTI
import font_norm as FN


def ref_mask_for(ch, size=256):
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(SONGTI, size, index=7)
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(0.88 * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127


def comps(mask, min_area=12):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = [int(v) for v in st[i]]
        if a < min_area:
            continue
        out.append({"id": i, "bbox": (x, y, x + w, y + h), "area": a})
    return lab, out


def filter_crop_ink(ink, ch):
    """返回 (filtered_ink, report)。ink: bool mask（crop 坐标，y 向下）。"""
    report = {"kept": 0, "dropped": 0, "missing_ref": 0}
    if not ref_has(ch):
        return ink, {"skip": "no_ref"}
    lab, cs = comps(ink)
    if not cs:
        return ink, {"skip": "no_ink"}
    main = max(cs, key=lambda c: c["area"])
    ref = ref_mask_for(ch)
    rlab, rcs = comps(ref)
    if not rcs:
        return ink, {"skip": "no_ref_ink"}
    rmain = max(rcs, key=lambda c: c["area"])

    def ctr(b):
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)

    c1, c2 = ctr(main["bbox"]), ctr(rmain["bbox"])
    l1 = max(main["bbox"][2] - main["bbox"][0], main["bbox"][3] - main["bbox"][1])
    l2 = max(rmain["bbox"][2] - rmain["bbox"][0], rmain["bbox"][3] - rmain["bbox"][1])
    s = l2 / max(1.0, l1)
    M = np.array([[s, 0, c2[0] - s * c1[0]], [0, s, c2[1] - s * c1[1]]], np.float32)
    ref_warp = cv2.warpAffine(ref.astype(np.uint8), M, (ink.shape[1], ink.shape[0]),
                              flags=cv2.INTER_NEAREST)
    ref_d = cv2.dilate(ref_warp, np.ones((15, 15), np.uint8)) > 0
    out = ink.copy()
    for c in cs:
        comp = (lab == c["id"])
        a = c["area"]
        cov = float((comp & ref_d).sum()) / a
        # 保留：与参考覆盖高、或面积大（主结构的一部分）、或是主组件
        if c["id"] == main["id"] or cov >= 0.35 or a >= 0.25 * main["area"]:
            report["kept"] += 1
            continue
        out[comp] = False
        report["dropped"] += 1
    return out, report


if __name__ == "__main__":
    # 自测：对 owner 标记字跑 crop 级过滤，输出前后 ink 组件数
    import json
    font = "release/KangXiKai-v2.4.15/KangXiKai-Regular-v2.4.15.ttf"
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]
    pos = json.load(open(os.path.join(ROOT, "work/review/owner-marks-compare.json"), encoding="utf-8"))
    chars = [r["char"] for r in pos if r["in_current"]][:12]
    for ch in chars:
        r = man[ch]
        gray = FN.render_pdf_crop(r["page"], r["box"], pad150=6, dpi=300)
        ink = FN.binarize(gray)
        ink = FN.remove_specks(ink)
        ink = FN.strip_border_lines(ink)
        filtered, rep = filter_crop_ink(ink, ch)
        print(ch, rep)
