#!/usr/bin/env python3
"""T0+ · 纠偏收益量化：原版 vs 拉正版

指标：
1) 栏线垂直度：界栏（长竖线）在 5 个 y 带内的 x 位置标准差（弯曲页大，拉正后应骤降）
2) 检出质量：原型检测器（提议+紧化）vs 金标（经同一 H 映射到拉正空间）
   - 金标召回（best-IoU ≥0.5）
   - 匹配框 IoU 中位数
   - FP 数（无金标 IoU ≥0.3 的检出）
"""
import json, os
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")

import importlib.util
spec = importlib.util.spec_from_file_location("det", os.path.join(ROOT, "scripts", "t00_detect.py"))
det = importlib.util.module_from_spec(spec)
spec.loader.exec_module(det)


def iou(a, b):
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    ix = max(0, min(ax1, bx1) - max(ax0, bx0)); iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua else 0.0


def warp_box(box, M):
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
    w = cv2.perspectiveTransform(pts[None, :, :], M)[0]
    return [int(w[:, 0].min()), int(w[:, 1].min()), int(w[:, 0].max()) + 1, int(w[:, 1].max()) + 1]


def rule_verticality(ink):
    """界栏垂直度：长竖线在每个 y 带内的 x 中位的标准差（跨 5 带）"""
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    Hh = ink.shape[0]
    bands = [(int(Hh * f), int(Hh * (f + 0.18))) for f in (0.08, 0.28, 0.48, 0.68, 0.82)]
    stds = []
    for b0, b1 in bands:
        cols = np.where(v[b0:b1].sum(axis=0) > 0.5 * (b1 - b0))[0]
        stds.append(cols)
    # 用最长的公共规则集：以第 3 带（中部）的栏线为基准，追其在各带的 x
    if len(stds[2]) == 0:
        return None
    base = stds[2]
    xs_at_bands = []
    for b0, b1 in bands:
        cols = np.where(v[b0:b1].sum(axis=0) > 0.5 * (b1 - b0))[0]
        vals = []
        for bx in base:
            near = cols[np.abs(cols - bx) <= 12]
            vals.append(float(near.mean()) if len(near) else np.nan)
        xs_at_bands.append(vals)
    arr = np.array(xs_at_bands, dtype=float)
    per_rule = []
    for j in range(arr.shape[1]):
        col = arr[:, j]
        if np.isnan(col).sum() <= 1:
            per_rule.append(float(np.nanstd(col)))
    return round(float(np.median(per_rule)), 2) if per_rule else None


def detect_boxes(gray):
    ink, _, _ = det.page_ink(gray)
    h0 = det.height_mode(det.raw_blocks(ink))
    if h0 is None:
        return [], None
    boxes, _ = det.headword_boxes(ink, h0)
    return boxes, h0


def eval_half(gray, gold_boxes, tag):
    boxes, h0 = detect_boxes(gray)
    matched_ious, n_fp = [], 0
    for b in boxes:
        bb = (b["x0"], b["y0"], b["x1"], b["y1"])
        best = max((iou(bb, g) for g in gold_boxes), default=0.0)
        if best >= 0.3:
            if best >= 0.5:
                matched_ious.append(best)
        else:
            n_fp += 1
    recall = sum(1 for g in gold_boxes
                 if max((iou(g, (b["x0"], b["y0"], b["x1"], b["y1"])) for b in boxes),
                        default=0) >= 0.5) / max(1, len(gold_boxes))
    ink = (gray <= 150).astype(np.uint8)
    return {"tag": tag, "n_gold": len(gold_boxes), "n_det": len(boxes),
            "gold_recall": round(recall, 3),
            "matched_iou_med": round(float(np.median(matched_ious)), 3) if matched_ious else None,
            "fp": n_fp,
            "rule_vert_std_px": rule_verticality(ink)}


def main():
    gold = json.load(open(os.path.join(T00, "gold50.json")))["boxes"]
    report = {}
    for stem in ["01_0006", "01_0110", "13_0163", "08_0020"]:
        rep = {}
        gray = cv2.imread(os.path.join(T00, "pages", stem + ".png"), cv2.IMREAD_GRAYSCALE)
        quads = json.load(open(os.path.join(T00, "rect", f"{stem}_quads.json")))
        for hentry in quads["halves"]:
            side = hentry["side"]
            if not hentry.get("ok"):
                continue
            # 该侧的金标
            gx0 = min(q[0] for q in hentry["quad"]); gx1 = max(q[0] for q in hentry["quad"])
            gb = [g["box"] for g in gold
                  if g["page"] == stem and gx0 - 20 <= (g["box"][0] + g["box"][2]) / 2 <= gx1 + 20]
            # 原图侧（金框平移到切片坐标）
            x0, x1 = int(min(q[0] for q in hentry["quad"])), int(max(q[0] for q in hentry["quad"]))
            x0, x1 = max(0, x0 - 130), min(gray.shape[1], x1 + 130)   # 含书眉带（复现原条件）
            gb_local = [[b[0] - x0, b[1], b[2] - x0, b[3]] for b in gb]
            rep[f"{side}_orig"] = eval_half(gray[:, x0:x1], gb_local, "orig")
            # 拉正侧
            quad = np.array([[q[0] - x0, q[1]] for q in hentry["quad"]], dtype=np.float32)
            dst_w, dst_h = hentry["size"]
            dst = np.array([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]], dtype=np.float32)
            M = cv2.getPerspectiveTransform(quad, dst)
            warped = cv2.warpPerspective(gray[:, x0:x1], M, (dst_w, dst_h),
                                         flags=cv2.INTER_CUBIC, borderValue=255)
            gb_rect = [warp_box(g, M) for g in gb_local]
            rep[f"{side}_rect"] = eval_half(warped, gb_rect, "rect")
        report[stem] = rep
        print(stem)
        for k, v in rep.items():
            print("  ", k, v)
    json.dump(report, open(os.path.join(T00, "rect", "rect_eval.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
