#!/usr/bin/env python3
"""A3-1 · 自监督部首模板池：从 36 个刻本卷扉页挖 214 个部首字字形。

方法（不依赖 OCR）：
1. 扉页每列「上=部首字，下=部字」；「部」字形重复出现 → 在连通域上做模板聚类，
   取最大近似簇 = 「部」模板（自监督，无人工标注）；
2. 用「部」模板定位同一扉页半版的所有「部」字（含与部首字粘连的合并块，取下半）；
3. 每个「部」字正上方（同列）的紧 bbox = 部首字形；按 x 从右到左 = 扉页部首顺序；
4. 与 volume_radicals.json 的已知部首清单逐位对齐；150dpi 定位、300dpi 取字形；
5. 归一化 48×48 二值/灰度模板 + 96×96 png + index.json。
"""
import json, os, sys, warnings
import cv2
import fitz
import numpy as np

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_MAP = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "work", "seq", "radical_templates")
SIZE = 48

# 36 个卷扉页的半版列表（A2b 实测；阅读序；最后一个半版之后正文开始）
FM = {
    "01": {"上": [("5", "L"), ("6", "R")], "中": [("49", "L")], "下": [("128", "L"), ("129", "R"), ("129", "L")]},
    "02": {"上": [("4", "L")], "中": [("127", "L")], "下": [("185", "L")]},
    "03": {"上": [("4", "L"), ("5", "R")], "中": [("80", "L")], "下": [("161", "L"), ("162", "R")]},
    "04": {"上": [("4", "L")], "中": [("90", "L")], "下": [("221", "L"), ("222", "R")]},
    "05": {"上": [("4", "L")], "中": [("55", "L")], "下": [("189", "L"), ("190", "R")]},
    "06": {"上": [("4", "L")], "中": [("151", "L"), ("152", "R")], "下": [("230", "L")]},
    "07": {"上": [("4", "L"), ("5", "R")], "中": [("113", "L"), ("114", "R")], "下": [("252", "L"), ("253", "R")]},
    "08": {"上": [("4", "L")], "中": [("97", "L"), ("98", "R")], "下": [("238", "L"), ("239", "R")]},
    "09": {"上": [("4", "L")], "中": [("138", "L")], "下": [("220", "L"), ("221", "R")]},
    "10": {"上": [("4", "L")], "中": [("138", "L"), ("139", "R")], "下": [("261", "L"), ("262", "R")]},
    "11": {"上": [("4", "L")], "中": [("122", "L"), ("123", "R")], "下": [("253", "L"), ("254", "R")]},
    "12": {"上": [("4", "L"), ("5", "R")], "中": [("83", "L")], "下": [("183", "L"), ("184", "R"), ("184", "L")]},
}


def render_half(pdf, page, half, dpi=150):
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    try:
        p = doc[page - 1]
        r = p.rect
        x0 = 0 if half == "L" else r.width / 2
        pix = p.get_pixmap(dpi=dpi, clip=fitz.Rect(x0, 0, x0 + r.width / 2, r.height))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
    finally:
        doc.close()
    return gray


def clean_comps(g, thr=140):
    ink = (g <= thr).astype(np.uint8)
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 300)))
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (300, 1)))
    cl = ink & (1 - v) & (1 - h)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cl, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, hh, a = stats[i]
        if hh >= 40 and w >= 15 and a >= 200:
            comps.append([int(x), int(y), int(x + w), int(y + hh)])
    return comps, cl


def norm(ink, size=SIZE, pad=4):
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return np.zeros((size, size), np.float32)
    bb = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = bb.shape
    side = max(h, w) + 2 * pad
    c = np.zeros((side, side), np.uint8)
    c[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = bb
    r = cv2.resize(c, (size, size), interpolation=cv2.INTER_AREA)
    return (r > 0).astype(np.float32)


def iou(a, b):
    return float((a * b).sum()) / max(1e-6, float(((a + b) > 0).sum()))


def cluster_comps(comps, cl, iou_thr=0.5):
    tiles = [norm(cl[y0:y1, x0:x1]) for x0, y0, x1, y1 in comps]
    used = [False] * len(comps)
    clusters = []
    for i in range(len(comps)):
        if used[i]:
            continue
        grp = [i]
        used[i] = True
        wi = comps[i][2] - comps[i][0]
        hi = comps[i][3] - comps[i][1]
        for j in range(i + 1, len(comps)):
            if used[j]:
                continue
            wj = comps[j][2] - comps[j][0]
            hj = comps[j][3] - comps[j][1]
            if abs(wi - wj) > 25 or abs(hi - hj) > 25:
                continue
            if iou(tiles[i], tiles[j]) >= iou_thr:
                grp.append(j)
                used[j] = True
        clusters.append(grp)
    return clusters, tiles


def radical_above(cl, bu_box):
    """部字正上方的墨迹 bbox = 部首字形。"""
    x0, y0, x1, y1 = bu_box
    yy0 = max(0, y0 - 155)
    strict = cl[yy0:max(0, y0 - 2), max(0, x0 - 18):x1 + 18]
    ys, xs = np.where(strict > 0)
    if len(xs) == 0:
        return None
    return (int(x0 - 18 + xs.min()), int(yy0 + ys.min()),
            int(x0 - 18 + xs.max() + 1), int(yy0 + ys.max() + 1))


def extract_half(pdf, page, half, bank):
    """返回该半版定位到的部首字形（150dpi 页面坐标），右→左。"""
    g = render_half(pdf, page, half, 150)
    H = g.shape[0]
    comps, cl = clean_comps(g)
    if not comps:
        return []
    clusters, tiles = cluster_comps(comps, cl)
    # 部字行 y 带（150dpi 扉页固定版式：部字约在 0.36–0.45H）
    lo, hi = int(H * 0.30), int(H * 0.50)
    cand = []
    for grp in clusters:
        if len(grp) < 2:
            continue
        ys = [comps[k][1] for k in grp]
        if lo <= float(np.median(ys)) <= hi:
            cand.append((len(grp), grp))
    cand.sort(key=lambda z: -z[0])
    bu_idx = []
    if cand:
        bu_idx = cand[0][1]
    else:
        # 回退：用全局部模板库匹配（1–2 个部首的小卷）
        for i, b in enumerate(comps):
            x0, y0, x1, y1 = b
            if not (lo <= y0 <= hi):
                continue
            t = tiles[i]
            best = max((iou(t, bt) for bt in bank), default=0.0)
            if best >= 0.42:
                bu_idx.append(i)
    out = []
    for k in bu_idx:
        rb = radical_above(cl, comps[k])
        if rb is None:
            continue
        out.append({"radical_box_150": rb, "bu_box_150": [int(v) for v in comps[k]],
                    "iou": 1.0})
    out.sort(key=lambda o: -o["radical_box_150"][0])  # 右→左
    return out


def crop_300(pdf, page, half, box150):
    """按 150dpi 坐标在 300dpi 上切字形紧 bbox 二值图。"""
    x0, y0, x1, y1 = [int(v * 2) for v in box150]
    pad = 6
    g = render_half(pdf, page, half, 300)
    H, W = g.shape
    sub = g[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
    ink = (sub <= 140).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 25:
            keep[lab == i] = 1
    ys, xs = np.where(keep)
    if len(xs) == 0:
        return None
    return keep[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def main():
    os.makedirs(OUT, exist_ok=True)
    vol = json.load(open(os.path.join(ROOT, "work", "seq", "volume_radicals.json"),
                         encoding="utf-8"))
    bank = []
    index = []
    problems = []
    retry = []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        for j in vol["volumes"][v]["juan"]:
            juan = j["juan"]
            rads = j["radicals"]
            parts = FM[v][juan[-1]]
            got = []
            for page_s, half in parts:
                page_s = int(page_s)
                boxes = extract_half(v, page_s, half, bank)
                # 累积部模板库（每个半版最大簇的前 3 个实例）
                g150 = render_half(v, page_s, half, 150)
                comps, cl = clean_comps(g150)
                if comps:
                    clusters, tiles = cluster_comps(comps, cl)
                    clusters.sort(key=len, reverse=True)
                    for grp in clusters[:1]:
                        for k in grp[:3]:
                            bank.append(tiles[k])
                got.extend([(page_s, half, b) for b in boxes])
            ok = len(got) == len(rads)
            if not ok:
                retry.append((v, juan, rads, parts))
            # 对齐：右→左 = 部首清单顺序；若数量不符，按位置比例对齐
            for k in range(min(len(got), len(rads))):
                page_s, half, b = got[k]
                rad = rads[k]
                img = crop_300(v, page_s, half, b["radical_box_150"])
                if img is None:
                    continue
                tile = norm(img)
                png = cv2.resize((img * 255).astype(np.uint8), (96, 96),
                                 interpolation=cv2.INTER_AREA)
                fn = f"{rad}_u{ord(rad):04x}_{v}_{page_s}{half}.png"
                cv2.imwrite(os.path.join(OUT, fn), png)
                index.append({"radical": rad, "vol": v, "juan": juan, "page": int(page_s),
                              "half": half, "box150": b["radical_box_150"],
                              "iou_bu": b["iou"], "file": fn,
                              "ink_sum48": float(tile.sum())})
    # 第二轮：用完整部模板库重试失败卷
    for v, juan, rads, parts in retry:
        got = []
        for page_s, half in parts:
            page_s = int(page_s)
            got.extend([(page_s, half, b) for b in extract_half(v, page_s, half, bank)])
        if len(got) == len(rads):
            for k in range(len(rads)):
                page_s, half, b = got[k]
                img = crop_300(v, page_s, half, b["radical_box_150"])
                if img is None:
                    continue
                tile = norm(img)
                png = cv2.resize((img * 255).astype(np.uint8), (96, 96),
                                 interpolation=cv2.INTER_AREA)
                fn = f"{rads[k]}_u{ord(rads[k]):04x}_{v}_{page_s}{half}.png"
                cv2.imwrite(os.path.join(OUT, fn), png)
                index.append({"radical": rads[k], "vol": v, "juan": juan, "page": page_s,
                              "half": half, "box150": b["radical_box_150"],
                              "iou_bu": b["iou"], "file": fn,
                              "ink_sum48": float(tile.sum())})
        else:
            problems.append({"juan": juan, "expected": len(rads), "got": len(got),
                             "parts": parts})
    json.dump({"templates": index, "n": len(index), "problems": problems,
               "method": "扉页「部」字聚类自监督定位 → 部首字形 = 部字正上方；150dpi 定位/300dpi 取形"},
              open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("templates", len(index), "problems", len(problems), flush=True)
    for p in problems:
        print("  PROBLEM", p, flush=True)


if __name__ == "__main__":
    main()
