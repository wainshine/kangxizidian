#!/usr/bin/env python3
"""按「注文小字格点阵」切大字（2×2 小字格 = 1 个大字，康熙字典刻本版式）。

步骤（每页，150dpi）：
 1) 背景相减二值 → 小字连通域（h≈h0）→ 估计字高 h0；
 2) 分 R/L 半版（中缝=白色竖带）；各自拟合 x/y 格距与相位（组件中心残差最小化）；
 3) 小字占用网格：格内有小字中心=占用；2×2 连续空格 = 大字候选；
 4) 校验：块内墨量 ≈ 2~7 倍小字墨量、四象限有墨、内部十字界线有跨格笔画；
 5) 大字框 = 2×2 格块边界（整块，不缩放、不 trim）。
输出 work/lead/grid_cells_boxes.jsonl（page/half/box/cell）
"""
import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def page_gray(vol, pno, dpi=150):
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[pno - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return g


def binarize(g):
    bg = cv2.medianBlur(g, 21)
    diff = bg.astype(np.int16) - g.astype(np.int16)
    ink = (diff > 40).astype(np.uint8)
    n0, l0, s0, _ = cv2.connectedComponentsWithStats(ink, 8)
    allow = (s0[:, cv2.CC_STAT_AREA] >= 15); allow[0] = False
    return allow[l0].astype(np.uint8)


def fit_lattice_1d(vals, lo, hi, tol_frac=0.18):
    """在 [lo,hi] 内找周期 pitch 与相位 phase，使 vals 落在格点±tol 内最多。"""
    best = None
    for pitch in range(int(lo), int(hi) + 1):
        tol = max(1.0, tol_frac * pitch)
        # 相位：让 mod 后分布集中
        res = np.mod(vals, pitch)
        # 用圆周均值法得快相位估计
        ang = res / pitch * 2 * np.pi
        ph = (np.angle(np.mean(np.exp(1j * ang))) / (2 * np.pi)) % 1.0 * pitch
        d = np.minimum(np.abs(res - ph), pitch - np.abs(res - ph))
        score = int((d < tol).sum())
        if best is None or score > best[0]:
            best = (score, pitch, ph)
    return best  # score, pitch, phase


def detect_half(gray, half_mask):
    h, w = gray.shape
    ink = binarize(gray)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    small = []
    for i in range(1, n):
        x, y, ww, hh, a = st[i]
        if not half_mask(x + ww / 2, y + hh / 2):
            continue
        if 24 <= hh <= 52 and 10 <= ww <= 56 and 50 <= a <= 1000:
            small.append((x + ww / 2, y + hh / 2, hh, a))
    if len(small) < 120:
        return None
    h0 = float(np.median([s[2] for s in small]))
    sa = float(np.median([s[3] for s in small]))
    xs = np.array([s[0] for s in small]); ys = np.array([s[1] for s in small])
    resx = fit_lattice_1d(xs, 0.9 * h0, 1.9 * h0)
    resy = fit_lattice_1d(ys, 0.85 * h0, 1.6 * h0)
    if not resx or not resy:
        return None
    _, px, phx = resx
    _, py, phy = resy
    # 拟合优度
    def resid(vals, pitch, phase):
        r = np.mod(vals - phase, pitch)
        return np.minimum(r, pitch - r) / pitch
    rx = resid(xs, px, phx); ry = resid(ys, py, phy)
    if np.median(rx) > 0.20 or np.median(ry) > 0.20:
        return None
    # 文本块范围（限制在正文版心内）
    tx0 = int(np.percentile([s[0] for s in small], 1)) - px
    tx1 = int(np.percentile([s[0] for s in small], 99)) + px
    ty0 = int(np.percentile([s[1] for s in small], 1)) - py
    ty1 = int(np.percentile([s[1] for s in small], 99)) + py
    # 占用网格
    gx0 = phx - px; gy0 = phy - py
    nx = int((w - gx0) / px) + 2; ny = int((h - gy0) / py) + 2
    occ = np.zeros((ny, nx), dtype=np.uint8)
    for (cx, cy, hh, a) in small:
        c = int(round((cx - gx0) / px)); r = int(round((cy - gy0) / py))
        if 0 <= r < ny and 0 <= c < nx:
            occ[r, c] = 1
    boxes = []
    seen = set()
    for r in range(ny - 1):
        for c in range(nx - 1):
            if occ[r:r + 2, c:c + 2].any():
                continue
            if any((r + dr, c + dc) in seen for dr in (0, 1) for dc in (0, 1)):
                continue
            x0 = int(round(gx0 + c * px)); y0 = int(round(gy0 + r * py))
            x1 = int(round(x0 + 2 * px)); y1 = int(round(y0 + 2 * py))
            x0c, y0c = max(0, x0), max(0, y0)
            x1c, y1c = min(w, x1), min(h, y1)
            if x1c - x0c < 40 or y1c - y0c < 40:
                continue
            sub = ink[y0c:y1c, x0c:x1c]
            a = int(sub.sum())
            if not (1.0 * sa <= a <= 8 * sa):
                continue
            H, W = sub.shape
            quads = [sub[:H // 2, :W // 2].sum(), sub[:H // 2, W // 2:].sum(),
                     sub[H // 2:, :W // 2].sum(), sub[H // 2:, W // 2:].sum()]
            if min(quads) < 0.05 * a:
                continue
            # 跨格笔画：内部十字界线附近有墨
            vb = sub[:, max(0, W // 2 - 2):W // 2 + 3]
            hb = sub[max(0, H // 2 - 2):H // 2 + 3, :]
            if max(vb.mean(), hb.mean()) < 0.05:
                continue
            if x0 < tx0 or y0 < ty0 or x1 > tx1 or y1 > ty1:
                continue
            if x0 < 0 or y0 < 0:
                continue
            for dr in (0, 1):
                for dc in (0, 1):
                    seen.add((r + dr, c + dc))
            boxes.append({"box": [x0, y0, x1, y1], "ink": a, "cell": [r, c]})
    return {"boxes": boxes, "h0": round(h0, 1), "px": round(px, 2), "py": round(py, 2),
            "phx": round(phx, 1), "phy": round(phy, 1), "n_small": len(small)}


def detect_page(args):
    vol, pno = args
    try:
        g = page_gray(vol, pno)
    except Exception as e:
        return {"page": f"{vol}_{pno:04d}", "boxes": [], "err": str(e)}
    h, w = g.shape
    mid = w // 2
    # 中缝：中央 30% 内墨量最少的列
    ink = binarize(g)
    col = ink.sum(axis=0).astype(np.float32)
    lo, hi = int(w * 0.42), int(w * 0.58)
    gx = int(lo + np.argmin(col[lo:hi]))
    out = {"page": f"{vol}_{pno:04d}", "gutter": gx, "halves": {}}
    for name, mask in (("L", lambda x, y: x < gx), ("R", lambda x, y: x >= gx)):
        r = detect_half(g, mask)
        if r:
            out["halves"][name] = r
    return out


def main():
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    jobs = []
    for vol, fn in sorted(mp.items()):
        doc = fitz.open(os.path.join(ROOT, "康熙字典", fn))
        n = doc.page_count; doc.close()
        for p in range(1, n + 1):
            jobs.append((vol, p))
    out = os.path.join(ROOT, "work/lead/grid_cells_boxes.jsonl")
    print("pages", len(jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out, "w", encoding="utf-8") as fo:
        for res in ex.map(detect_page, jobs, chunksize=8):
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            done += 1
            if done % 500 == 0:
                print("done", done, flush=True)
    print("finished", done, out, flush=True)


if __name__ == "__main__":
    main()
