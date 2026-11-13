#!/usr/bin/env python3
"""参考闸 v2 全量扫描：①配准后小碎片（cov<0.25 且面积<6%）；②结构失配（长宽比/面积比与参考差>1.8x）→ major。"""
import json, os, sys, math
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from refgate2 import masks, _comps
import numpy as np, cv2


def analyze_glyph(o, r):
    lab_o, co = _comps(o); lab_r, cr = _comps(r)
    if not co or not cr:
        return [], False
    # 结构失配
    def wh(bbox): return (bbox[2]-bbox[0], bbox[3]-bbox[1])
    wo, ho = wh(co[0]["bbox"]) if False else (0, 0)
    all_o = _all_bbox(o); all_r = _all_bbox(r)
    w1, h1 = wh(all_o); w2, h2 = wh(all_r)
    a1, a2 = w1*h1, w2*h2
    ar1, ar2 = w1/max(1, h1), w2/max(1, h2)
    major = False
    if max(ar1/ar2, ar2/ar1) > 1.8 or max(a1/a2, a2/a1) > 2.5:
        major = True
    # 配准（最大组件）
    mo = co[0]; mr = max(cr, key=lambda c: c["area"])
    cc = lambda b: ((b[0]+b[2])/2, (b[1]+b[3])/2)
    c1, c2 = cc(mo["bbox"]), cc(mr["bbox"])
    l1 = max(wh(mo["bbox"])); l2 = max(wh(mr["bbox"]))
    s = l2 / max(1.0, l1)
    M = np.array([[s, 0, c2[0]-s*c1[0]], [0, s, c2[1]-s*c1[1]]], np.float32)
    rd = cv2.dilate(r.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0
    total = int(o.sum())
    sus = []
    for c in co:
        comp = (lab_o == c["id"]).astype(np.uint8)
        w = cv2.warpAffine(comp, M, (o.shape[1], o.shape[0]), flags=cv2.INTER_NEAREST)
        a = int(w.sum())
        if a < 12:
            continue
        cov = float((w & rd).sum()) / a
        if cov < 0.25 and c["area"] < 0.06 * total:
            sus.append({"bbox": list(c["bbox"]), "area": c["area"], "cov": round(cov, 3)})
    return sus, major


def _all_bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return (0, 0, 1, 1)
    return (int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1)


def job(items):
    font, chars = items
    out = []
    for ch in chars:
        try:
            o, r = masks(font, ch)
            if r is None:
                continue
            sus, major = analyze_glyph(o, r)
            if sus or major:
                out.append({"char": ch, "major": major, "suspects": sus})
        except Exception:
            pass
    return out


def main():
    font, man, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    chars = sorted(json.load(open(man, encoding="utf-8"))["chars"].keys())
    n = max(1, (len(chars)+7)//8)
    chunks = [(font, chars[i:i+n]) for i in range(0, len(chars), n)]
    rows = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(job, chunks):
            rows.extend(res)
    rows.sort(key=lambda r: r["char"])
    with open(out_path, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False)+"\n")
    print(json.dumps({"flagged": len(rows), "major": sum(1 for r in rows if r["major"]),
                      "minor": sum(1 for r in rows if not r["major"])}), flush=True)


if __name__ == "__main__":
    main()
