#!/usr/bin/env python3
"""扫描每个字框裁图，检测「版框/注文引用框」长直线残片（贴边、近轴、长）。
输出 work/lead/v248_frame_line_chars.json（char/page/half/box/line 位置）
"""
import json, os, sys
import numpy as np, cv2, fitz
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def analyze_crop(gray, box, pad=8):
    H, W = gray.shape
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    x1, y1 = min(W, box[2] + pad), min(H, box[3] + pad)
    sub = gray[y0:y1, x0:x1]
    if sub.size == 0:
        return None
    bg = cv2.medianBlur(sub, 15)
    diff = bg.astype(np.int16) - sub.astype(np.int16)
    ink = (diff > 40).astype(np.uint8) * 255
    lines = cv2.HoughLinesP(ink, 1, np.pi / 180, threshold=45,
                            minLineLength=int(0.55 * max(sub.shape)),
                            maxLineGap=4)
    if lines is None:
        return None
    h, w = sub.shape
    arr = lines.reshape(-1, 4)
    for ln in arr[:8]:
        xa, ya, xb, yb = [int(v) for v in ln]
        dx, dy = xb - xa, yb - ya
        L = float(np.hypot(dx, dy))
        if L < 0.5 * max(w, h):
            continue
        ang = abs(np.degrees(np.arctan2(dy, dx))) % 90
        near_axis = min(ang, 90 - ang) < 6
        if not near_axis:
            continue
        cx, cy = (xa + xb) / 2 / w, (ya + yb) / 2 / h
        # 残片线：位置贴边（中心在边带）或贯穿 75% 以上
        edge = cx < 0.18 or cx > 0.82 or cy < 0.18 or cy > 0.82
        if edge or L > 0.8 * max(w, h):
            return {"line": [xa + x0, ya + y0, xb + x0, yb + y0], "len": round(L, 1)}
    return None


def job(args):
    vol, page, items = args
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[int(page) - 1].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    out = []
    for it in items:
        r = analyze_crop(g, it["box"])
        if r:
            out.append({**it, **r})
    return out


def main():
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v247.json"), encoding="utf-8"))
    bypage = {}
    for ch, r in man["chars"].items():
        bypage.setdefault((r["page"][:2], r["page"][3:]), []).append(
            {"char": ch, "page": r["page"], "half": r.get("half", "R"), "box": r["box"]})
    jobs = [(k[0], k[1], v) for k, v in bypage.items()]
    out = os.path.join(ROOT, "work/lead/v248_frame_line_chars.jsonl")
    print("pages", len(jobs), "chars", sum(len(v) for _, _, v in jobs), flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex, open(out, "w", encoding="utf-8") as fo:
        for rows in ex.map(job, jobs, chunksize=4):
            for r in rows:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            done += 1
    print("finished", done, out, flush=True)


if __name__ == "__main__":
    main()
