#!/usr/bin/env python3
"""Lead · 全量页角色预分类（60dpi 轻量）。

目的：确定每卷正文起始页、识别封面/空白/集扉页/部首页等非正文页，供 solver 强制零计数与
生产流水线跳过。特征（60dpi 下 h0≈14.8px，字头≈31px）：
  - ink_frac：内区墨量占比
  - n_small：注文小字连通域数（h 8..22）
  - n_big：大字连通域数（h 24..48）
  - frame_lines：强横/竖线
角色：
  blank      墨量 < 0.02
  cover      墨量很高但无小字（书衣/深色页）
  title_page 少小字 + 若干大字（集扉页/部首页/目录）
  body       大量小字（注文）
输出 work/lead/page_roles.jsonl
"""
import json, os, sys, argparse
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def features(img60):
    g = img60
    H, W = g.shape
    inner = g[int(0.08 * H):int(0.95 * H), int(0.03 * W):int(0.97 * W)]
    ink = (inner <= 150).astype(np.uint8)
    ink_frac = float(ink.mean())
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    hs = stats[1:, 3]
    ws = stats[1:, 2]
    areas = stats[1:, 4]
    n_small = int(((hs >= 8) & (hs <= 22) & (ws >= 4) & (ws <= 22) & (areas >= 15)).sum())
    n_big = int(((hs >= 24) & (hs <= 48) & (areas >= 250)).sum())
    # 长线
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25)))
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1)))
    frame = int(v.sum() > 0) + int(h.sum() > 0)
    return dict(ink_frac=round(ink_frac, 4), n_small=n_small, n_big=n_big, frame=frame)


def role(f):
    if f["ink_frac"] < 0.02:
        return "blank"
    if f["n_small"] < 30:
        if f["ink_frac"] > 0.25:
            return "cover"
        return "title_page"
    return "body"


def worker(args):
    pdf_path, pages = args
    import fitz
    doc = fitz.open(pdf_path)
    out = []
    for pg in pages:
        p = doc[pg - 1]
        pix = p.get_pixmap(dpi=60, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        f = features(img)
        f.update(pdf=os.path.basename(pdf_path), page=pg, role=role(f),
                 w=pix.width, h=pix.height)
        out.append(f)
    doc.close()
    return out


def _run_job(job):
    vol, path, pages = job
    rows = worker((path, pages))
    for r in rows:
        r["vol"] = vol
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/page_roles.jsonl"))
    args = ap.parse_args()
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    # 先拿页数
    import fitz
    jobs = []
    for vol in sorted(mp):
        path = os.path.join(ROOT, "康熙字典", mp[vol])
        d = fitz.open(path)
        n = d.page_count
        d.close()
        # 分块
        chunks = [list(range(i, min(i + 40, n + 1))) for i in range(1, n + 1, 40)]
        for c in chunks:
            jobs.append((vol, path, c))
    print("jobs", len(jobs))
    from multiprocessing import Pool

    allrows = []
    with Pool(args.workers) as pool:
        for i, rows in enumerate(pool.imap_unordered(_run_job, jobs)):
            allrows.extend(rows)
            if i % 10 == 0:
                print("done jobs", i, "/", len(jobs), flush=True)
    allrows.sort(key=lambda r: (r["vol"], r["page"]))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in allrows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    import collections
    print(collections.Counter(r["role"] for r in allrows))


if __name__ == "__main__":
    main()
