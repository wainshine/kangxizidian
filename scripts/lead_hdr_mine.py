#!/usr/bin/env python3
"""Lead · 书眉模板自监督挖掘：把版心柱切成字格 → 归一化 → 聚类 → 人工标注簇 → 真迹模板。
（书眉字是同一副活字反复印，同字字形极相似；真迹模板匹配应远强于字体渲染模板）
用法: .venv/bin/python scripts/lead_hdr_mine.py --vols 01 --out work/lead/hdr_mine01
"""
import argparse, json, os, sys, collections
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cv2.setNumThreads(2)
SIZE = 40


def border_end(gray, xmax=40):
    dark = (gray[:, :xmax] <= 100)
    cf = dark.mean(axis=0)
    be = 0
    for x in range(xmax):
        if cf[x] > 0.55:
            be = x
    return be


def find_frame(gray, lo=40, hi=230):
    H = gray.shape[0]
    ink = (gray <= 150).astype(np.uint8)
    ink[:, :3] = 0
    cs = ink.sum(axis=0)
    cand = [x for x in range(lo, min(hi, gray.shape[1])) if cs[x] > 0.40 * H]
    groups = []
    for x in cand:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    narrow = [gp for gp in groups if len(gp) <= 6]
    return int(round(sum(narrow[0]) / len(narrow[0]))) if narrow else None


def strip_mask(gray, x0, x1):
    strip = gray[:, x0:x1]
    st = cv2.medianBlur(strip, 3)
    bg = cv2.medianBlur(st, 61)
    ink = ((bg.astype(np.int16) - st.astype(np.int16)) > 45).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 15:
            keep[lab == i] = 1
    vert = cv2.morphologyEx(keep, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 140)))
    return keep & (1 - vert)


def segment_cells(mask):
    rows = mask.sum(axis=1)
    on = rows >= 2
    runs = []
    s = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            runs.append([s, i]); s = None
    if s is not None:
        runs.append([s, len(on)])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 10:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        if b - a < 24:
            continue
        sub = mask[a:b]
        cols = sub.sum(axis=0)
        nz = np.where(cols > 0)[0]
        if len(nz) == 0:
            continue
        m = sub[:, nz.min():nz.max() + 1]
        ys, xs = np.where(m > 0)
        if len(ys) < 40:
            continue
        m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h, w = m.shape
        if not (30 <= h <= 130 and 10 <= w <= 110):
            continue
        out.append((int(a), int(b), m))
    return out


def norm40(m):
    h, w = m.shape
    s = SIZE / max(h, w)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    mm = cv2.resize(m.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
    c = np.zeros((SIZE, SIZE), np.float32)
    c[(SIZE - nh) // 2:(SIZE - nh) // 2 + nh, (SIZE - nw) // 2:(SIZE - nw) // 2 + nw] = mm
    return c


def header_cells(gray):
    x0 = border_end(gray) + 3
    fr = find_frame(gray)
    x1 = (fr - 4) if (fr and fr - 4 > x0 + 30) else min(gray.shape[1], x0 + 76)
    mask = strip_mask(gray, x0, x1)
    cells = segment_cells(mask)
    return cells, x0, x1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", default="01")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=70)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hdr_mine01"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        roles[r["vol"]].append((r["page"], r["role"]))
    jobs = []
    for vol in args.vols.split(","):
        for page, role in sorted(roles[vol]):
            if role == "body":
                jobs.append((vol, page))
    if args.limit:
        jobs = jobs[:args.limit]
    feats, meta = [], []
    cur = None
    doc = None
    for vol, page in jobs:
        if vol != cur:
            if doc:
                doc.close()
            doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            cur = vol
        pix = doc[page - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        gray = img[:, :img.shape[1] // 2]
        cells, x0, x1 = header_cells(gray)
        for (a, b, m) in cells:
            feats.append(norm40(m).ravel())
            meta.append({"vol": vol, "page": page, "y0": a, "y1": b,
                         "h": b - a, "w": m.shape[1], "x0": x0, "x1": x1})
    if doc:
        doc.close()
    X = np.stack(feats)
    print("cells", X.shape)
    Z = (X > 0.45).astype(np.float32)
    # 归一化（零均值）便于相关距离
    Zn = Z - Z.mean(axis=1, keepdims=True)
    Zn = Zn / (np.linalg.norm(Zn, axis=1, keepdims=True) + 1e-6)
    # 用 PCA 降维加速 kmeans：随机采样 4000 做 SVD
    rng = np.random.default_rng(0)
    samp = Zn[rng.choice(len(Zn), min(4000, len(Zn)), replace=False)]
    U, S, Vt = np.linalg.svd(samp, full_matrices=False)
    P = Vt[:40].T  # 40 维
    Xp = Zn @ P
    Xp = Xp / (np.linalg.norm(Xp, axis=1, keepdims=True) + 1e-6)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 1e-3)
    _, labels, centers = cv2.kmeans(Xp.astype(np.float32), args.k, None, crit, 4,
                                    cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    cnt = collections.Counter(labels.tolist())
    order = [l for l, _ in cnt.most_common()]
    print("top clusters", [(l, cnt[l]) for l in order[:20]])
    # 保存
    np.save(os.path.join(args.out, "X.npy"), X)
    np.save(os.path.join(args.out, "labels.npy"), labels)
    np.save(os.path.join(args.out, "P.npy"), P)
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8"))
    # 每个簇取 8 个样本（离中心最近的）做拼图
    from PIL import Image, ImageDraw, ImageFont
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", 16)
    except Exception:
        fnt = ImageFont.load_default()
    T = 48
    cols = 8
    rows = (len(order) + cols - 1) // cols
    S_ = Image.new("L", (cols * (T + 6), rows * (T + 26)), 255)
    dr = ImageDraw.Draw(S_)
    for k, l in enumerate(order):
        # 该簇最近的样本
        idxs = np.where(labels == l)[0]
        d = np.linalg.norm(Xp[idxs] - Xp[idxs].mean(axis=0), axis=1)
        best = idxs[np.argsort(d)[:4]]
        x0_ = (k % cols) * (T + 6)
        y0_ = (k // cols) * (T + 26)
        S_.paste(Image.fromarray((X[best[0]].reshape(SIZE, SIZE) * 255).astype(np.uint8)),
                 (x0_, y0_ + 22))
        dr.text((x0_ + 2, y0_ + 2), f"c{l}:{cnt[l]}", font=fnt, fill=0)
    S_.save(os.path.join(args.out, "clusters.png"))
    print("saved", args.out)


if __name__ == "__main__":
    main()
