#!/usr/bin/env python3
"""T1 · 门槛评估（分层 + 硬判据，docs/DECISIONS.md D9）

对切格器输出（work/t1/{mode}_boxes/*.json）vs 金标（gold50.json, provisional）：
- 分层（主卷 zhujuan / 补遗 buyi）：precision、recall、matched IoU 中位、IoU≥0.85 占比
- 门：主卷 ≥30 框、补遗 ≥15 框；任一层 IoU≥0.85 占比 <85% 即 FAIL
用法：t1_gate.py --mode orig|rect
"""
import argparse, json, os
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T00 = os.path.join(ROOT, "work", "t00")
T1 = os.path.join(ROOT, "work", "t1")


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def gold_in_space(mode):
    """返回 [(stem, layer, box)]，坐标与切格器输出同空间"""
    gold = json.load(open(os.path.join(T00, "gold50.json")))
    out = []
    if mode == "orig":
        for g in gold["boxes"]:
            out.append((g["page"], g["layer"], g["box"]))
        return out
    # rect：按所属半版把金框经 H 映射到拉正坐标
    quads_cache = {}
    for g in gold["boxes"]:
        stem = g["page"]
        if stem not in quads_cache:
            qp = os.path.join(T00, "rect", f"{stem}_quads.json")
            quads_cache[stem] = json.load(open(qp)) if os.path.exists(qp) else None
        quads = quads_cache[stem]
        if not quads:
            continue
        bx = g["box"]
        cx = (bx[0] + bx[2]) / 2
        for hentry in quads["halves"]:
            if not hentry.get("ok"):
                continue
            xs = [q[0] for q in hentry["quad"]]
            if not (min(xs) - 20 <= cx <= max(xs) + 20):
                continue
            x0c = max(0, min(xs) - 130)
            x1c = x0c  # 占位；透视只需 quad 相对坐标
            gray = cv2.imread(os.path.join(T00, "pages", stem + ".png"), cv2.IMREAD_GRAYSCALE)
            quad = np.array([[q[0] - x0c, q[1]] for q in hentry["quad"]], dtype=np.float32)
            dst_w, dst_h = hentry["size"]
            dst = np.array([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]], dtype=np.float32)
            M = cv2.getPerspectiveTransform(quad, dst)
            pts = np.array([[bx[0] - x0c, bx[1]], [bx[2] - x0c, bx[1]],
                            [bx[2] - x0c, bx[3]], [bx[0] - x0c, bx[3]]], dtype=np.float32)
            wpts = cv2.perspectiveTransform(pts[None], M)[0]
            out.append((stem, g["layer"],
                        [int(wpts[:, 0].min()), int(wpts[:, 1].min()),
                         int(wpts[:, 0].max()) + 1, int(wpts[:, 1].max()) + 1]))
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["orig", "rect"], default="orig")
    args = ap.parse_args()
    golds = gold_in_space(args.mode)
    report = {"mode": args.mode, "layers": {}}
    for layer, quota in (("zhujuan", 30), ("buyi", 15)):
        gl = [(s, b) for s, l, b in golds if l == layer]
        tp = fp = fn = 0
        matched = []
        for stem, g in gl:
            bf = os.path.join(T1, f"{args.mode}_boxes", stem + ".json")
            if not os.path.exists(bf):
                fn += 1
                continue
            det = json.load(open(bf))["boxes"]
            best = max((iou(g, d) for d in det), default=0.0)
            if best >= 0.5:
                tp += 1
                matched.append(best)
            else:
                fn += 1
        # FP：与任何金标 IoU<0.3 的检出框（仅统计有金标的页）
        gold_pages = {s for s, _ in gl}
        for stem in gold_pages:
            bf = os.path.join(T1, f"{args.mode}_boxes", stem + ".json")
            if not os.path.exists(bf):
                continue
            det = json.load(open(bf))["boxes"]
            gl_boxes = [b for s, b in gl if s == stem]
            for d in det:
                if max((iou(d, g) for g in gl_boxes), default=0.0) < 0.3:
                    fp += 1
        n_det = tp + fp
        prec = round(tp / n_det, 3) if n_det else 0.0
        rec = round(tp / len(gl), 3) if gl else 0.0
        iou85 = round(sum(1 for v in matched if v >= 0.85) / len(matched), 3) if matched else 0.0
        report["layers"][layer] = {
            "n_gold": len(gl), "n_det": n_det, "precision": prec, "recall": rec,
            "iou_med": round(float(np.median(matched)), 3) if matched else None,
            "iou85_frac": iou85,
            "quota_ok": len(gl) >= quota,
            "pass": bool(iou85 >= 0.85 and len(gl) >= quota),
        }
    report["verdict"] = "PASS" if all(l["pass"] for l in report["layers"].values()) else "FAIL"
    print(json.dumps(report, ensure_ascii=False, indent=1))
    json.dump(report, open(os.path.join(T1, f"gate_{args.mode}.json"), "w"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
