#!/usr/bin/env python3
"""读康熙字典刻本 集/卷 扉页的部首清单（A2b）。

方法：fitz 300dpi 渲染扉页半版 → 用竖栏线切列 → 列内按 y 切大字（h≥80px）
→ PaddleOCR rec 单字 → 组装「部首+部」对；按「跨页先 R 后 L、版内列右→左」读序。
输出 work/seq/frontmatter_pages.jsonl（逐半版读数）+ work/seq/volume_radicals_raw.json。
"""
import fitz, json, os, sys, warnings
import cv2
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from header_read import get_ocr, _ocr_input, RAD214, RAD_SET, ALIAS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_MAP = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "work", "seq")


def render_half(pdf, page, half, dpi=300):
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    try:
        p = doc[page - 1]
        r = p.rect
        x0 = 0 if half == "L" else r.width / 2
        pix = p.get_pixmap(dpi=dpi, clip=fitz.Rect(x0, 0, x0 + r.width / 2, r.height))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
    finally:
        doc.close()
    return gray


def column_rules(g, thr=140, min_run=700):
    """竖栏线（要求贯穿大半版高，排除印章/污点造成的短线）。"""
    ink = (g <= thr).astype(np.uint8)
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_run)))
    colsum = v.sum(axis=0)
    centers, s = [], None
    for x in range(len(colsum)):
        z = colsum[x] >= min_run * 0.9
        if z and s is None:
            s = x
        if not z and s is not None:
            centers.append((s + x - 1) // 2)
            s = None
    if s is not None:
        centers.append((s + len(colsum) - 1) // 2)
    return centers, colsum


def chars_in_column(g, x0, x1, thr=140, min_h=80, gap=8):
    col = g[:, x0:x1]
    ink = (col <= thr).astype(np.uint8)
    # 去横长线（版框/栏线），否则 y 投影被整行墨迹连通
    horz = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (min(60, max(8, x1 - x0 - 6)), 1)))
    ink = ink & (1 - horz)
    rows = ink.sum(axis=1)
    runs, s = [], None
    for i, val in enumerate(rows > 4):
        if val and s is None:
            s = i
        if not val and s is not None:
            runs.append([s, i])
            s = None
    if s is not None:
        runs.append([s, len(rows)])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= min_h]


_ocr = None


def ocr_gray(g, tag):
    global _ocr
    if _ocr is None:
        _ocr = get_ocr()
    fn = os.path.join(OUT, "structure", f"_ocr_{tag}.png")
    cv2.imwrite(fn, _ocr_input(g))
    try:
        res = _ocr.predict(fn)[0]
        d = res.json.get("res", {})
        return d.get("rec_text") or "", float(d.get("rec_score") or 0.0)
    finally:
        try:
            os.remove(fn)
        except OSError:
            pass


def read_half(g, pdf, page, half):
    """读一个半版的列/字。返回 [{x0,x1,chars:[{y0,y1,text,score}]}]（列右→左）。"""
    lines, colsum = column_rules(g)
    H, W = g.shape
    # 去掉页边（<60 或 >W-60）
    lines = [l for l in lines if 40 < l < W - 40]
    # 确保首尾边界（页面外框可能被裁）
    if not lines or lines[0] > 120:
        lines = [max(0, min(lines) - 190)] + lines if lines else [40]
    if lines[-1] < W - 120:
        lines = lines + [min(W - 1, lines[-1] + 190)]
    cols = []
    for a, b in zip(lines, lines[1:]):
        if b - a < 60:
            continue
        chars = chars_in_column(g, a + 4, b - 4)
        items = []
        for (y0, y1) in chars:
            crop = g[max(0, y0 - 8):y1 + 8, a + 4:b - 4]
            t, s = ocr_gray(crop, f"{pdf}{page}{half}{y0}")
            items.append({"y0": y0, "y1": y1, "text": t, "score": round(s, 3)})
        cols.append({"x0": a, "x1": b, "chars": items})
    cols.sort(key=lambda c: c["x0"], reverse=True)   # 版内列右→左
    return cols


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--pages", default=None, help="逗号分隔页号，如 5,49,128,129")
    ap.add_argument("--out", default=os.path.join(OUT, "frontmatter_pages.jsonl"))
    args = ap.parse_args()
    os.makedirs(os.path.join(OUT, "structure"), exist_ok=True)
    pdfs = [args.pdf] if args.pdf else [f"{i:02d}" for i in range(1, 13)]
    pages = {int(x) for x in args.pages.split(",")} if args.pages else None
    rows = []
    for pdf in pdfs:
        if pages is None:
            continue
        for p in sorted(pages):
            for half in ("R", "L"):
                g = render_half(pdf, p, half)
                cols = read_half(g, pdf, p, half)
                rows.append({"pdf": pdf, "page": p, "half": half, "cols": cols})
                print(f"{pdf}_{p:04d}{half}: cols={len(cols)} "
                      f"chars={[c['text'] for col in cols for c in col['chars']]}", flush=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote", len(rows), "->", args.out)


if __name__ == "__main__":
    main()
