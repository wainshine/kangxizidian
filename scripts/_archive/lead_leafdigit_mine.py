#!/usr/bin/env python3
"""Lead · 从「葉码=页−5」公式自监督挖掘真迹数字样本（用底部固定高窗，避开合并格问题）。

对每页：在版心 cells 中找到最后一段「画数/部名之后的文字格」= 葉码格；
裁其底部 ~42px（= 末位数字）；标签 = 葉码书写规则的最后一位。
输出 work/lead/leafdigit_samples2.npz
"""
import json, os, sys, collections
import numpy as np
import cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIG = "一二三四五六七八九"


def leaf_last(n):
    if n in (20,):
        return "廿"
    if n in (30,):
        return "卅"
    if n in (40,):
        return "卌"
    if n in (100, 200, 300):
        return "百"
    r = n % 10
    if r == 0:
        return "十"
    return DIG[r - 1]


def norm(m, size=40):
    ys, xs = np.where(m > 0)
    if len(ys) < 20:
        return None
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h, w = m.shape
    if not (10 <= h <= 110 and 4 <= w <= 120):
        return None
    s = size / max(h, w)
    mm = cv2.resize(m, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    c = np.zeros((size, size), np.float32)
    c[(size - mm.shape[0]) // 2:(size - mm.shape[0]) // 2 + mm.shape[0],
      (size - mm.shape[1]) // 2:(size - mm.shape[1]) // 2 + mm.shape[1]] = mm
    return c


def main():
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    raw = []
    for line in open(os.path.join(ROOT, "work/seq/headers_full_raw.jsonl"), encoding="utf-8"):
        raw.append(json.loads(line))
    imgs = {}
    samples = []
    stats = collections.Counter()
    for d in raw:
        cells = d.get("cells") or []
        if not cells:
            continue
        vol = d["pdf"]; pg = d["page"]
        leaf = pg - 5
        if leaf < 1:
            continue
        exp = leaf_last(leaf)
        # 找最后一个「部」或「畫」格，葉码在它之后
        anchor = -1
        for i, c in enumerate(cells):
            if c.get("text") in ("部", "畫") or (c.get("text") or "").endswith("畫"):
                anchor = i
        cand_idx = None
        for i in range(anchor + 1, len(cells)):
            c = cells[i]
            h = c["y1"] - c["y0"]
            if 30 <= h <= 160:
                cand_idx = i
                break
        if cand_idx is None:
            # fallback：最后一个 h 30-160 的格
            for i in range(len(cells) - 1, -1, -1):
                h = cells[i]["y1"] - cells[i]["y0"]
                if 30 <= h <= 160:
                    cand_idx = i
                    break
        if cand_idx is None:
            continue
        c = cells[cand_idx]
        key = (vol, pg)
        if key not in imgs:
            doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            pix = doc[pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            doc.close()
            imgs[key] = img[:, :img.shape[1] // 2]
        g = imgs[key]
        x0 = d.get("x0", 4); x1 = d.get("x1", 90)
        # 底部 42px 窗口（末位数字）
        y1 = c["y1"]; y0 = max(c["y0"], y1 - 46)
        crop = g[y0:y1, x0:x1]
        st = cv2.medianBlur(crop, 3)
        bg = cv2.medianBlur(crop, 51)
        ink = ((bg.astype(np.int16) - st.astype(np.int16)) > 22).astype(np.uint8)
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        v = norm(ink)
        if v is None:
            stats["skip"] += 1
            continue
        samples.append({"page": f"{vol}_{pg:04d}", "label": exp, "img": v,
                        "cell": [c["y0"], c["y1"]], "x": [x0, x1]})
        stats[exp] += 1
    print("samples", len(samples), dict(stats))
    np.savez_compressed(os.path.join(ROOT, "work/lead/leafdigit_samples2.npz"),
                        X=np.stack([s["img"] for s in samples]),
                        y=np.array([s["label"] for s in samples]),
                        pages=np.array([s["page"] for s in samples]))


if __name__ == "__main__":
    main()
