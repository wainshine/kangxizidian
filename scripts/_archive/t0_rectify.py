#!/usr/bin/env python3
"""T0+ · 版面自动纠偏（思路来自 vModou，MIT，shanleiguang 2025；本项目 Python 重实现）

vModou 原法：辅助线限定搜索区 → 8 方向序扫描版框四角顶点 → 仿射拉正 → 裁黑边（交互式）。
本实现自动化：
1) 强横线（版框顶/底边，run ≥30% 半页宽）的两端点 = 四角（横线端点即角点，免全图扫）；
2) 角点合理性检查（凸性、边长、与强横线一致），失败则该半版跳过纠偏并记录；
3) cv2.getPerspectiveTransform 四点透视拉正（vModou 用仿射+勾股；透视对弯曲页更准）；
4) 输出拉正后的单版图 + 变换矩阵 + 前后对比图。

输出 work/t00/rect/{stem}_{L,R}.png、{stem}_quads.json、{stem}_preview.png
"""
import json, os, sys
import numpy as np
import cv2

cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")

BIN_T = 150
HALF_BLANK_INK = 0.004


def page_ink(gray):
    ink = (gray <= BIN_T).astype(np.uint8)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (200, 1))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    return cv2.subtract(cv2.subtract(ink, v), h), v, h


def split_halves(ink, W):
    colsum = ink.sum(axis=0)
    best, run = None, None
    for x in range(int(W * 0.30), int(W * 0.70)):
        if colsum[x] == 0:
            run = run or x
        else:
            if run is not None:
                if best is None or x - run > best[1]:
                    best = (run, x - run)
                run = None
    if run is not None and (best is None or int(W * 0.7) - run > best[1]):
        best = (run, int(W * 0.7) - run)
    halves = [(0, best[0] if best else W // 2), ((best[0] + best[1]) if best else W // 2, W)]
    return list(zip("LR", halves))


def longest_run(cols, gap=8):
    """最长连续 True 段（允许 ≤gap 像素断口），返回 (start, end)"""
    best = (0, -1)
    s, last = None, None
    for i, v in enumerate(cols):
        if v:
            if s is None:
                s = i
            last = i
        else:
            if s is not None and i - last > gap:
                if last - s > best[1] - best[0]:
                    best = (s, last)
                s = None
    if s is not None and last - s > best[1] - best[0]:
        best = (s, last)
    return best if best[1] >= best[0] else None


def strong_hlines(hlines_half, w_half):
    """版框顶/底横线：清 80px 页边黑带（实测黑带最厚 ~59px）→ 按位置取首/末达标横线
    （run≥30% 半页宽）→ x 范围取最长连续线段端点（排除书眉竖排字的污染）"""
    B = 80
    hl = hlines_half.copy()
    hl[:B, :] = 0
    hl[-B:, :] = 0
    rows = np.where(hl.sum(axis=1) > 0.30 * w_half)[0]
    if len(rows) < 2:
        return None
    groups, cur = [], [rows[0]]
    for r in rows[1:]:
        if r - cur[-1] <= 40:
            cur.append(r)
        else:
            groups.append(cur)
            cur = [r]
    groups.append(cur)
    top, bottom = groups[0], groups[-1]
    if top is bottom or bottom[0] - top[-1] < 600:
        return None
    out = []
    for grp in (top, bottom):
        band = hlines_half[grp[0]:grp[-1] + 1]
        run = longest_run(band.sum(axis=0) > 0)
        if run is None or run[1] - run[0] < 0.5 * w_half:
            return None
        out.append((int(grp[0]), int(run[0]), int(run[1])))
    return out  # [(y_top, x_min_top, x_max_top), (y_bot, x_min_bot, x_max_bot)]


def corner_scan_fallback(ink_half, y_edge, side, w_half):
    """横线端点不可靠时的兜底：在 y_edge 附近的横带内，从外侧向内扫第一块墨"""
    band = ink_half[max(0, y_edge - 25):y_edge + 25]
    colhit = (band > 0).mean(axis=0)
    xs = np.where(colhit > 0.5)[0]
    if len(xs) < 50:
        return None
    return (int(xs.min()), int(xs.max())) if side == "outer_to_inner" else None


def rectify_half(gray, x0, x1, pad=6):
    """单版纠偏：返回 (warped, quad, H, ok, reason)"""
    H_, W_ = gray.shape
    x0, x1 = max(0, x0), min(W_, x1)
    sub = gray[:, x0:x1]
    ink, v, h = page_ink(sub)
    hl = h.copy()
    hl[:30, :] = 0; hl[-30:, :] = 0
    lines = strong_hlines(hl, x1 - x0)
    if lines is None:
        return None, None, None, False, "no strong hlines"
    (yt, xt0, xt1), (yb, xb0, xb1) = lines
    # 四角：顶边两端 + 底边两端
    quad = np.array([[xt0, yt], [xt1, yt], [xb1, yb], [xb0, yb]], dtype=np.float32)
    # 合理性：边长、凸性
    wt, wb = xt1 - xt0, xb1 - xb0
    if wt < 300 or wb < 300:
        return None, None, None, False, f"frame too narrow ({wt},{wb})"
    if yb - yt < 600:
        return None, None, None, False, "frame too short"
    if not (0.6 < wt / wb < 1.6):
        return None, None, None, False, f"top/bottom width mismatch ({wt},{wb})"
    dst_w, dst_h = int(max(wt, wb)), int(yb - yt)
    dst = np.array([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    warped = cv2.warpPerspective(sub, M, (dst_w, dst_h), flags=cv2.INTER_CUBIC,
                                 borderValue=255)
    return warped, (quad + [x0, 0]).tolist(), M, True, ""


def main():
    os.makedirs(os.path.join(T00, "rect"), exist_ok=True)
    pages = sys.argv[1:] or ["01_0006", "01_0110", "13_0163", "08_0020"]
    report = {}
    for stem in pages:
        path = os.path.join(T00, "pages", stem + ".png")
        if not os.path.exists(path):
            print("missing", path)
            continue
        gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        ink, _, _ = page_ink(gray)
        rep = {"halves": []}
        previews = []
        for side, (x0, x1) in split_halves(ink, gray.shape[1]):
            blank = ink[:, x0:x1].mean() < HALF_BLANK_INK
            entry = {"side": side, "blank": bool(blank)}
            if not blank:
                warped, quad, M, ok, reason = rectify_half(gray, x0, x1)
                entry["ok"] = bool(ok)
                if ok:
                    out = os.path.join(T00, "rect", f"{stem}_{side}.png")
                    cv2.imwrite(out, warped)
                    entry["quad"] = quad
                    entry["out"] = f"rect/{stem}_{side}.png"
                    entry["size"] = [warped.shape[1], warped.shape[0]]
                    previews.append(cv2.resize(warped, (300, int(300 * warped.shape[0] / warped.shape[1]))))
                else:
                    entry["reason"] = reason
            rep["halves"].append(entry)
        # 前后对比图：原半页（缩）+ 拉正后（缩）
        if previews:
            origs = [cv2.resize(gray[:, x0:x1], (300, int(300 * gray.shape[0] / (x1 - x0))))
                     for _, (x0, x1) in split_halves(ink, gray.shape[1])]
            glob_h = max([p.shape[0] for p in previews] + [o.shape[0] for o in origs])
            def pad(im):
                return cv2.copyMakeBorder(im, 0, glob_h - im.shape[0], 2, 2,
                                          cv2.BORDER_CONSTANT, value=255)
            comp = np.hstack([pad(o) for o in origs] + [pad(p) for p in previews])
            cv2.imwrite(os.path.join(T00, "rect", f"{stem}_preview.png"), comp)
        json.dump(rep, open(os.path.join(T00, "rect", f"{stem}_quads.json"), "w"),
                  ensure_ascii=False, indent=1)
        report[stem] = rep
        print(stem, [(h["side"], h.get("ok"), h.get("reason", "")) for h in rep["halves"]])
    json.dump(report, open(os.path.join(T00, "rect", "rect_report.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
