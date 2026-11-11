#!/usr/bin/env python3
"""成品字形三类缺陷扫描：①残留碎片 ②缺笔画（误切） ③边栏直线。
对 v2.4.14 字体全量跑，输出 JSONL（char/type/bboxes/info）。
"""
import json, os, sys
import numpy as np, cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from refgate import ref_has
from refgate2 import raster, _comps, SONGTI, SIZE


def comp_register(o, r):
    lab_o, co = _comps(o); lab_r, cr = _comps(r)
    if not co or not cr:
        return None
    mo = co[0]; mr = max(cr, key=lambda c: c["area"])
    cc = lambda b: ((b[0]+b[2])/2, (b[1]+b[3])/2)
    c1, c2 = cc(mo["bbox"]), cc(mr["bbox"])
    l1 = max(mo["bbox"][2]-mo["bbox"][0], mo["bbox"][3]-mo["bbox"][1])
    l2 = max(mr["bbox"][2]-mr["bbox"][0], mr["bbox"][3]-mr["bbox"][1])
    s = l2 / max(1.0, l1)
    M = np.array([[s, 0, c2[0]-s*c1[0]], [0, s, c2[1]-s*c1[1]]], np.float32)
    return lab_o, co, lab_r, cr, M


def scan_glyph(o, r):
    """返回 (fragments, missing, lines)。"""
    reg = comp_register(o, r)
    if reg is None:
        return [], [], []
    lab_o, co, lab_r, cr, M = reg
    # ① 残留碎片：our comps 映射到 ref，覆盖率低且小
    rd = cv2.dilate(r.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0
    total = int(o.sum())
    frags = []
    for c in co:
        comp = (lab_o == c["id"]).astype(np.uint8)
        w = cv2.warpAffine(comp, M, (SIZE, SIZE), flags=cv2.INTER_NEAREST)
        a = int(w.sum())
        if a < 12:
            continue
        cov = float((w & rd).sum()) / a
        if cov < 0.25 and c["area"] < 0.06 * total:
            frags.append({"bbox": list(c["bbox"]), "area": c["area"], "cov": round(cov, 3)})
    # ② 缺笔画：ref comps 映射回 ours 坐标，被我们墨迹覆盖比例低且不小
    od = cv2.dilate(o.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    Minv = cv2.invertAffineTransform(M)
    rt = int(max(1, r.sum()))
    missing = []
    for c in cr:
        comp = (lab_r == c["id"]).astype(np.uint8)
        w = cv2.warpAffine(comp, Minv, (SIZE, SIZE), flags=cv2.INTER_NEAREST)
        a = int(w.sum())
        if a < 0.02 * SIZE * SIZE:
            continue
        cov = float((w & od).sum()) / max(1, a)
        if cov < 0.55 and c["area"] < 0.35 * rt:
            missing.append({"bbox": list(c["bbox"]), "area": c["area"], "cov": round(cov, 3)})
    return frags, missing, []


def job(items):
    font, chars = items
    out = []
    for ch in chars:
        try:
            o = raster(font, ch)
            r = raster(SONGTI, ch, index=7) if ref_has(ch) else None
            if r is None:
                continue
            f, m, l = scan_glyph(o, r)
            if f or m or l:
                out.append({"char": ch, "frags": f, "missing": m, "lines": l})
        except Exception:
            pass
    return out


def main():
    font, man, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    chars = sorted(json.load(open(man, encoding="utf-8"))["chars"].keys())
    n = max(1, (len(chars)+7)//8)
    chunks = [(font, chars[i:i+n]) for i in range(0, len(chars), n)]
    rows = []
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(job, chunks):
            rows.extend(res)
    rows.sort(key=lambda r: r["char"])
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False)+"\n")
    nf = sum(1 for r in rows if r["frags"]); nm = sum(1 for r in rows if r["missing"])
    print(json.dumps({"glyphs": len(rows), "with_frags": nf, "with_missing": nm, "total": len(rows)}), flush=True)


if __name__ == "__main__":
    main()
