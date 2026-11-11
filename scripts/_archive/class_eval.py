#!/usr/bin/env python3
"""类级缺陷评测：对「owner 标记的缺陷字（阳性）」与「随机字（阴性）」逐字判类，
输出每类 detector 的命中/误报（用于标定阈值与衡量管线类级修复效果）。"""
import json, os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from refgate2 import raster, SONGTI
from refgate import ref_has
from refgate2 import _comps as comps2


def register(o, r):
    lab_o, co = comps2(o); lab_r, cr = comps2(r)
    if not co or not cr:
        return None
    def cc(b):
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    mo = co[0]; mr = max(cr, key=lambda c: c["area"])
    c1, c2 = cc(mo["bbox"]), cc(mr["bbox"])
    l1 = max(mo["bbox"][2] - mo["bbox"][0], mo["bbox"][3] - mo["bbox"][1])
    l2 = max(mr["bbox"][2] - mr["bbox"][0], mr["bbox"][3] - mr["bbox"][1])
    s = l2 / max(1.0, l1)
    M = np.array([[s, 0, c2[0] - s * c1[0]], [0, s, c2[1] - s * c1[1]]], np.float32)
    return lab_o, co, lab_r, cr, M


def analyze_glyph(font, ch):
    """返回该字命中的缺陷类集合 + 细节。"""
    o = raster(font, ch)
    classes = {}
    # D3 line
    lines = []
    n, lab, st, _ = cv2.connectedComponentsWithStats(o.astype(np.uint8), 8)
    for i in range(1, n):
        x, y, w, h, a = [int(v) for v in st[i]]
        if a < 40 or a > 0.3 * int(o.sum()):
            continue
        comp = (lab == i); ys, xs = np.nonzero(comp)
        pts = np.column_stack([xs, ys]).astype(np.float32)
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        dev = np.abs((pts[:, 0] - x0) * vy - (pts[:, 1] - y0) * vx)
        L = max(w, h); thick = a / max(1.0, L)
        if L > 0.30 * 256 and thick <= 8 and float(dev.max()) < 5.0:
            lines.append((x, y, w, h, a))
    if lines:
        classes["line"] = lines
    if not ref_has(ch):
        return classes
    r = raster(SONGTI, ch, index=7)
    reg = register(o, r)
    if reg is None:
        return classes
    lab_o, co, lab_r, cr, M = reg
    # D1 extra ink（参考无对应的小组件）
    rd = cv2.dilate(r.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0
    total = int(o.sum())
    extra = []
    for c in co:
        comp = (lab_o == c["id"]).astype(np.uint8)
        w = cv2.warpAffine(comp, M, (256, 256), flags=cv2.INTER_NEAREST)
        a = int(w.sum())
        if a < 12:
            continue
        cov = float((w & rd).sum()) / a
        if cov < 0.25 and c["area"] < 0.06 * total:
            extra.append({"bbox": list(c["bbox"]), "area": c["area"], "cov": round(cov, 2)})
    if extra:
        classes["extra"] = extra
    # D2 missing ink（参考有、我们没有）
    od = cv2.dilate(o.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    Minv = cv2.invertAffineTransform(M)
    rt = int(max(1, r.sum()))
    missing = []
    for c in cr:
        comp = (lab_r == c["id"]).astype(np.uint8)
        w = cv2.warpAffine(comp, Minv, (256, 256), flags=cv2.INTER_NEAREST)
        a = int(w.sum())
        if a < 0.02 * 256 * 256:
            continue
        cov = float((w & od).sum()) / max(1, a)
        if cov < 0.55 and c["area"] < 0.35 * rt:
            missing.append({"bbox": list(c["bbox"]), "area": c["area"], "cov": round(cov, 2)})
    if missing:
        classes["missing"] = missing
    # D4 layout/shape mismatch
    ob = (min(p["bbox"][0] for p in co), min(p["bbox"][1] for p in co),
          max(p["bbox"][2] for p in co), max(p["bbox"][3] for p in co))
    rb = (min(c["bbox"][0] for c in cr), min(c["bbox"][1] for c in cr),
          max(c["bbox"][2] for c in cr), max(c["bbox"][3] for c in cr))
    ow, oh = ob[2] - ob[0], ob[3] - ob[1]
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    ar_o = ow / max(1, oh); ar_r = rw / max(1, rh)
    if max(ar_o / max(0.01, ar_r), ar_r / max(0.01, ar_o)) > 1.8:
        classes["layout"] = {"ar": round(ar_o, 2), "ref_ar": round(ar_r, 2)}
    return classes


def main():
    font = sys.argv[1]
    pos_path = sys.argv[2] if len(sys.argv) > 2 else "work/review/owner-marks-compare.json"
    out_path = sys.argv[3] if len(sys.argv) > 3 else "work/review/class-eval.json"
    pos = [r["char"] for r in json.load(open(os.path.join(ROOT, pos_path), encoding="utf-8")) if r["in_current"]]
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v2415.json"), encoding="utf-8"))["chars"]
    import random as _r
    _r.seed(7)
    pool = [c for c in sorted(man) if c not in set(pos)]
    neg = _r.sample(pool, 300)
    res = {"font": font, "positives": {}, "negatives": {}}
    class_hits = {k: 0 for k in ("line", "extra", "missing", "layout")}
    for ch in pos:
        try:
            cl = analyze_glyph(font, ch)
        except Exception as e:
            cl = {"error": str(e)}
        res["positives"][ch] = cl
        for k in cl:
            if k in class_hits:
                class_hits[k] += 1
    fp = {k: 0 for k in class_hits}
    for ch in neg:
        try:
            cl = analyze_glyph(font, ch)
        except Exception:
            cl = {}
        res["negatives"][ch] = cl
        for k in cl:
            if k in fp:
                fp[k] += 1
    res["summary"] = {"pos_n": len(pos), "neg_n": len(neg),
                      "pos_class_hits": class_hits, "neg_class_fp": fp}
    json.dump(res, open(os.path.join(ROOT, out_path), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
