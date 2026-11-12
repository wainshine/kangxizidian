#!/usr/bin/env python3
"""版面元素统一检测（框线/界行/页边黑带/角部）→ 擦除 mask。

针对「块边界压线」类问题（audit/FRAME-ESCAPE-TRIAGE.md），覆盖:
  ① 四边内框线（上/下/左/右，含断线）
  ② 列界行（版内竖线，四边/中部都可能）
  ③ 四角 L 形厚框（由 ①② union + 页边黑带覆盖）
  ④ 页边黑带/装订阴影（扫描黑边）
方法：文本块 bbox + 剪切搜索（±1.5°，步长 0.25°）下的**投影线检测**（列/行墨占比 >0.55 且连续），
再按最优剪切角反投影画 5px 带；另加页边黑带投影。所有阈值按页尺寸比例，不写死像素。
"""
import math
import numpy as np
import cv2


def _ink(gray):
    from detect_blocks import binarize
    return binarize(gray)


def _text_bbox(ink):
    h, w = ink.shape
    col = ink.sum(axis=0); row = ink.sum(axis=1)
    bx0 = int(np.argmax(col > 50)); bx1 = int(len(col) - np.argmax(col[::-1] > 50))
    by0 = int(np.argmax(row > 50)); by1 = int(len(row) - np.argmax(row[::-1] > 50))
    return max(0, bx0), max(0, by0), min(w, bx1), min(h, by1)


def _shear_band(band, sx, sy):
    """按 shear 采样：第 y 行右移 round(sx*(y-cy))；第 x 列下移 round(sy*(x-cx))。"""
    h, w = band.shape
    cy = h / 2.0; cx = w / 2.0
    ys = np.arange(h)
    out = np.zeros_like(band)
    for y in range(h):
        d = int(round(sx * (y - cy)))
        if d == 0:
            out[y] = band[y]
        elif d > 0:
            out[y, d:] = band[y, :-d]
        else:
            out[y, :d] = band[y, -d:]
    if abs(sy) > 1e-6:
        out2 = np.zeros_like(out)
        for x in range(w):
            d = int(round(sy * (x - cx)))
            if d == 0:
                out2[:, x] = out[:, x]
            elif d > 0:
                out2[d:, x] = out[:-d, x]
            else:
                out2[:d, x] = out[-d:, x]
        out = out2
    return out


def _best_shear(band, axis, range_deg=1.5, step_deg=0.25):
    """返回 (best_shear, candidates_frac) —— 以「线候选数与强度」为评分。"""
    h, w = band.shape
    best = (0.0, -1.0, None)
    vals = np.arange(-range_deg, range_deg + 1e-9, step_deg)
    for deg in vals:
        s = math.tan(math.radians(deg))
        sh = _shear_band(band, s, 0.0) if axis == 0 else _shear_band(band, 0.0, s)
        prof = sh.mean(axis=0) if axis == 0 else sh.mean(axis=1)
        prof = np.convolve(prof, np.ones(3) / 3, mode="same")
        strong = prof[prof > 0.7]
        score = float(len(strong)) + float(strong.sum() if len(strong) else 0) * 0.001
        if score > best[1]:
            best = (s, score, prof)
    return best[0], best[2]


def detect_page_artifacts(gray):
    ink = _ink(gray)
    h, w = ink.shape
    bx0, by0, bx1, by1 = _text_bbox(ink)
    band = ink[by0:by1, bx0:bx1].astype(np.uint8)
    H, W = band.shape
    mask = np.zeros((h, w), dtype=np.uint8)

    # ① 竖线（列界行/竖框线）
    sx, vprof = _best_shear(band, axis=0) if W > 20 else (0.0, None)
    if vprof is not None:
        cands = np.where(vprof > 0.55)[0]
        cy = H / 2.0
        for x in cands:
            x0 = int(round(bx0 + x - sx * (0 - cy)))
            x1 = int(round(bx0 + x - sx * (H - cy)))
            cv2.line(mask, (x0, by0), (x1, by1), 1, 5)
    # ② 横线（上下框线）
    sy2, hprof = _best_shear(band, axis=1) if H > 20 else (0.0, None)
    if hprof is not None:
        cands = np.where(hprof > 0.55)[0]
        cx = W / 2.0
        for y in cands:
            y0 = int(round(by0 + y - sy2 * (0 - cx)))
            y1 = int(round(by0 + y - sy2 * (W - cx)))
            cv2.line(mask, (bx0, y0), (bx1, y1), 1, 5)

    # ③ 页边黑带（外缘 12% 内、整行/列墨占比 ≥0.45 且连续 ≥4px）
    outer_y = max(6, int(0.12 * h)); outer_x = max(6, int(0.12 * w))
    def _runs(idx):
        return np.split(idx, np.where(np.diff(idx) > 1)[0] + 1) if len(idx) else []
    for band_name, sl, axis in (("top", slice(0, outer_y), 1), ("bot", slice(h - outer_y, h), 1),
                                ("left", slice(0, outer_x), 0), ("right", slice(w - outer_x, w), 0)):
        sub = ink[sl, :] if axis == 1 else ink[:, sl]
        prof = sub.mean(axis=axis)
        for r in _runs(np.where(prof >= 0.45)[0]):
            if len(r) < 4:
                continue
            if axis == 1:
                base = 0 if band_name == "top" else h - outer_y
                mask[base + r[0]:base + r[-1] + 1, :] = 1
            else:
                base = 0 if band_name == "left" else w - outer_x
                mask[:, base + r[0]:base + r[-1] + 1] = 1

    # 细线保护：线带内只擦「薄」像素（DT <= 6），保住与线相交的粗笔画
    if mask.sum():
        dist = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 3)
        thin = (dist <= 6.0)
        edge_like = mask.copy()  # 页边黑带单独保留（它们天然厚，但在文本区外缘）
        mask = (mask & thin.astype(np.uint8))
        # 页边黑带重新并回（外缘 12% 内）
        outer_y = max(6, int(0.12 * h)); outer_x = max(6, int(0.12 * w))
        mask[0:outer_y, :] |= edge_like[0:outer_y, :]
        mask[h - outer_y:h, :] |= edge_like[h - outer_y:h, :]
        mask[:, 0:outer_x] |= edge_like[:, 0:outer_x]
        mask[:, w - outer_x:w] |= edge_like[:, w - outer_x:w]
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    return mask, {"px": int(mask.sum()), "ink_px": int(ink.sum()),
                  "v_lines": int((vprof > 0.55).sum()) if vprof is not None else 0,
                  "h_lines": int((hprof > 0.55).sum()) if hprof is not None else 0,
                  "shear_x": round(float(sx), 5), "shear_y": round(float(sy2), 5)}
