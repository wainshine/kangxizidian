#!/usr/bin/env python3
"""A3-3 · 从部界锚点页抽「部首自字」字形，做 214 部首模板池（png + index）。

优先级：① 该页「X部」标签检测的 radical_box（最准）→ ② 该页首字候选（rightmost column top，
dark）→ ③ 跳过（记录缺失）。300dpi 取形，归一化 48×48 二值 + 96×96 png。
"""
import json, os, collections, warnings
import cv2
import fitz
import numpy as np

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_MAP = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "work", "seq")
TROOT = os.path.join(OUT, "radical_templates2")
SIZE = 48


_DOCS = {}


def _doc(pdf):
    if pdf not in _DOCS:
        _DOCS[pdf] = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    return _DOCS[pdf]


def render_half(pdf, page, half="L", dpi=300):
    doc = _doc(pdf)
    p = doc[page - 1]
    r = p.rect
    x0 = 0 if half == "L" else r.width / 2
    pix = p.get_pixmap(dpi=dpi, clip=fitz.Rect(x0, 0, x0 + r.width / 2, r.height))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
    return gray


def norm(ink, size=SIZE, pad=4):
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return None
    bb = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = bb.shape
    side = max(h, w) + 2 * pad
    c = np.zeros((side, side), np.uint8)
    c[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = bb
    return (cv2.resize(c, (size, size), interpolation=cv2.INTER_AREA) > 0).astype(np.float32)


def crop_glyph(g, box):
    x0, y0, x1, y1 = [int(v) for v in box]
    H, W = g.shape
    pad = 10
    sub = g[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
    if sub.size == 0 or sub.shape[0] < 3 or sub.shape[1] < 3:
        return np.zeros((1, 1), np.uint8)
    ink = np.ascontiguousarray((sub <= 145).astype(np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 30:
            keep[lab == i] = 1
    return keep


def main():
    os.makedirs(TROOT, exist_ok=True)
    anchors = json.load(open(os.path.join(OUT, "bu_start_pages.jsonl")))["anchors"]
    label = collections.defaultdict(dict)
    lp = os.path.join(OUT, "bu_home_candidates.jsonl")
    if os.path.exists(lp):
        for line in open(lp, encoding="utf-8"):
            r = json.loads(line)
            key = (r["vol"], r["page"])
            if key not in label[key[0]] or r["bu_iou"] > label[key[0]][key[1]]["bu_iou"]:
                label[r["vol"]][r["page"]] = r
    # 首字候选（boxes300）
    def first_cand(vol, page):
        try:
            d = json.load(open(os.path.join(ROOT, "work", "lead", "boxes300",
                                            f"{vol}_{page:04d}.json")))
        except FileNotFoundError:
            return None
        cs = [c for c in d["halves"]["L"]["cands"] if c["feat"]["half"] == "L"
              and not c["feat"]["margin_strip"] and not c["feat"]["outside_band"]
              and 40 <= c["feat"]["cy"] < 1250 and c["argmax"] != "margin"]
        if not cs:
            return None
        cs = [c for c in cs if 45 <= c["feat"]["h"] <= 200]
        if not cs:
            return None
        cs.sort(key=lambda c: (-c["feat"]["cx"], c["feat"]["cy"]))
        right = cs[0]["feat"]["cx"]
        col = [c for c in cs if right - c["feat"]["cx"] < 50]
        col.sort(key=lambda c: c["feat"]["cy"])
        return col[0]
    index, missing = [], []
    for a in sorted(anchors, key=lambda x: (x["vol"], x["page"])):
        vol, page, rad = a["vol"], a["page"], a["radical"]
        src = None
        box = None
        lab = label.get(vol, {}).get(page)
        if lab and lab.get("radical_box"):
            box = lab["radical_box"]
            src = "label"
        else:
            c = first_cand(vol, page)
            if c is not None:
                box = [int(v) for v in c["box"]]
                src = "first_cand"
        if box is None:
            missing.append(a)
            continue
        g = render_half(vol, page, "L", 300)
        ink = crop_glyph(g, [v * 2 for v in box])
        t = norm(ink)
        if t is None:
            missing.append(a)
            continue
        png = cv2.resize((ink * 255).astype(np.uint8), (96, 96), interpolation=cv2.INTER_AREA)
        fn = f"{rad}_u{ord(rad):04x}_{vol}_{page:04d}.png"
        cv2.imwrite(os.path.join(TROOT, fn), png)
        index.append({"radical": rad, "vol": vol, "page": page, "juan": a["juan"],
                      "box150": box, "src": src, "file": fn,
                      "ink_sum48": round(float(t.sum()), 1)})
    json.dump({"templates": index, "n": len(index), "missing": len(missing),
               "missing_list": [{"vol": m["vol"], "page": m["page"], "radical": m["radical"]}
                                for m in missing],
               "method": "锚点页部首自字：优先标签检测 radical_box，否则首字候选；300dpi 取形"},
              open(os.path.join(TROOT, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("templates", len(index), "missing", len(missing))
    print("src dist", dict(collections.Counter(t["src"] for t in index)))


if __name__ == "__main__":
    main()
