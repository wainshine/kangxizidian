#!/usr/bin/env python3
"""Lead · 版心柱切格导出（多进程）：为「书眉数字模板自监督挖掘」准备数据。

输出 work/lead/hdr_cells.npz：
  pages : 页 key 数组
  boxes : (N,4) [page_idx, y0, y1, n_in_page]  —— 每次导出按页内 y 升序
  imgs  : (N,40,40) float32 归一化字格
  meta  : json 串（vol/page/half 映射）
算法沿用 lead_header_v3：border/frame 定位 → bg 相减二值 → 去竖线 → 行投影切格。
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2
cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE = 40


def border_end(gray, xmax=40):
    dark = (gray[:, :xmax] <= 100)
    cf = dark.mean(axis=0)
    be = 0
    for x in range(xmax):
        if cf[x] > 0.55:
            be = x
    return be


def find_frame(gray, lo=40, hi=230):
    H = gray.shape[0]
    ink = (gray <= 150).astype(np.uint8)
    ink[:, :3] = 0
    cs = ink.sum(axis=0)
    cand = [x for x in range(lo, min(hi, gray.shape[1])) if cs[x] > 0.40 * H]
    groups = []
    for x in cand:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    narrow = [gp for gp in groups if len(gp) <= 6]
    return int(round(sum(narrow[0]) / len(narrow[0]))) if narrow else None


def strip_mask(gray, x0, x1):
    strip = gray[:, x0:x1]
    st = cv2.medianBlur(strip, 3)
    bg = cv2.medianBlur(st, 61)
    ink = ((bg.astype(np.int16) - st.astype(np.int16)) > 45).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 15:
            keep[lab == i] = 1
    vert = cv2.morphologyEx(keep, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 140)))
    return keep & (1 - vert)


def segment_cells(mask):
    rows = mask.sum(axis=1)
    on = rows >= 2
    runs = []
    s = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            runs.append([s, i]); s = None
    if s is not None:
        runs.append([s, len(on)])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 6:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        if b - a < 26:
            continue
        sub = mask[a:b]
        cols = sub.sum(axis=0)
        nz = np.where(cols > 0)[0]
        if len(nz) == 0:
            continue
        m = sub[:, nz.min():nz.max() + 1]
        ys, xs = np.where(m > 0)
        if len(ys) < 40:
            continue
        m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h, w = m.shape
        if not (30 <= h <= 130 and 8 <= w <= 110):
            continue
        out.append((int(a), int(b), m))
    return out


def norm40(m):
    h, w = m.shape
    s = SIZE / max(h, w)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    mm = cv2.resize(m.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
    c = np.zeros((SIZE, SIZE), np.float32)
    c[(SIZE - nh) // 2:(SIZE - nh) // 2 + nh, (SIZE - nw) // 2:(SIZE - nw) // 2 + nw] = mm
    return c


def full_cells(gray):
    """返回 [(y0,y1,norm40)]，按 y 升序。"""
    x0 = border_end(gray) + 3
    fr = find_frame(gray)
    x1 = (fr - 4) if (fr and fr - 4 > x0 + 30) else min(gray.shape[1], x0 + 76)
    mask = strip_mask(gray, x0, x1)
    return [(a, b, norm40(m)) for a, b, m in segment_cells(mask)]


def _job(args):
    vol, pages = args
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    out = []
    for pg in pages:
        try:
            pix = doc[pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            g = img[:, :img.shape[1] // 2]
            cells = full_cells(g)
            out.append((vol, pg, cells))
        except Exception:
            out.append((vol, pg, []))
    doc.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hdr_cells.npz"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    jobs = []
    for vol in sorted(roles):
        ps = sorted(roles[vol])
        if args.limit:
            ps = ps[:args.limit]
        # 分片
        k = max(1, len(ps) // args.workers + 1)
        for i in range(0, len(ps), k):
            jobs.append((vol, ps[i:i + k]))
    print("jobs", len(jobs), "pages", sum(len(p) for _, p in jobs))
    from multiprocessing import Pool
    allcells = []
    with Pool(args.workers) as pool:
        for res in pool.imap_unordered(_job, jobs):
            allcells.extend(res)
    allcells.sort(key=lambda t: (t[0], t[1]))
    boxes = []
    imgs = []
    page_keys = []
    meta = {}
    for pi, (vol, pg, cells) in enumerate(allcells):
        page_keys.append(f"{vol}_{pg:04d}")
        meta[f"{vol}_{pg:04d}"] = pi
        for k, (a, b, m) in enumerate(cells):
            boxes.append([pi, a, b, len(cells)])
            imgs.append(m)
    np.savez_compressed(args.out, pages=np.array(page_keys),
                        boxes=np.array(boxes, dtype=np.int32),
                        imgs=np.stack(imgs).astype(np.float32),
                        meta=json.dumps(meta))
    print("saved", args.out, "pages", len(page_keys), "cells", len(imgs))


if __name__ == "__main__":
    main()
