#!/usr/bin/env python3
"""Lead · 版心「画数」真迹模板自监督挖掘：从 seq 版心 OCR 的 cell 定位裁 數字/畫 真迹，
聚类后用「数值多数投票」自动标注（数值初值来自 OCR 解析，允许有噪声）。

输出：work/lead/hua_tpl/clusters.npz + clusters.png + labels.json
"""
import argparse, json, os, sys, collections
import numpy as np, cv2
cv2.setNumThreads(4)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_CH = "一二三四五六七八九十廿卅卌百"
SIZE = 40


def norm40(m):
    m = (m > 0).astype(np.uint8)
    ys, xs = np.where(m > 0)
    if len(ys) < 25:
        return None
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h, w = m.shape
    if not (20 <= h <= 140 and 6 <= w <= 140):
        return None
    s = SIZE / max(h, w)
    mm = cv2.resize(m, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    c = np.zeros((SIZE, SIZE), np.float32)
    c[(SIZE - mm.shape[0]) // 2:(SIZE - mm.shape[0]) // 2 + mm.shape[0],
      (SIZE - mm.shape[1]) // 2:(SIZE - mm.shape[1]) // 2 + mm.shape[1]] = mm
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(ROOT, "work/seq/headers_full_raw.jsonl"))
    ap.add_argument("--parsed", default=os.path.join(ROOT, "work/lead/hdr_parsed.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hua_tpl2"))
    ap.add_argument("--k", type=int, default=24)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    # 每页解析后的 hua（用于投票标签）
    parsed = {}
    for line in open(args.parsed, encoding="utf-8"):
        r = json.loads(line)
        parsed[r["page"]] = r
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    # 候选页：有 hua 且 raw 有 cell 几何
    rows = []
    for line in open(args.raw, encoding="utf-8"):
        d = json.loads(line)
        page = f"{d['pdf']}_{d['page']:04d}"
        p = parsed.get(page) or {}
        hua = p.get("hua") or []
        if not hua:
            continue
        cells = d.get("cells") or []
        # 找最后一个「畫」
        hua_i = None
        for i, c in enumerate(cells):
            if c["text"] == "畫" and c["score"] >= 0.35:
                hua_i = i
        if hua_i is None or hua_i < 1:
            continue
        rows.append((page, d["pdf"], d["page"], d.get("x0", 4), d.get("x1", 90),
                     cells, hua_i, hua[-1]))
    print("candidate pages", len(rows))
    # 裁 數字（畫 上方 1-2 格）
    docs = {}
    feats, metas = [], []
    for page, vol, pg, x0, x1, cells, hua_i, hval in rows:
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        g = img[:, :img.shape[1] // 2]
        # 画数字段：从上往下取 畫 前面连续的数字格（最多 2 个）
        j = hua_i - 1
        num_cells = []
        while j >= 0 and len(num_cells) < 2 and cells[j]["text"] in NUM_CH:
            num_cells.insert(0, cells[j])
            j -= 1
        if not num_cells:
            continue
        # 单位：末位数字格的图形（数值 = hval 的写法由 OCR 已确定；只取最后一个数字格）
        c = num_cells[-1]
        crop = g[max(0, c["y0"]):c["y1"], x0:x1]
        # 更好的预处理：背景归一化 + 自适应阈值 + 开运算去噪
        st = cv2.medianBlur(crop, 3)
        bg = cv2.medianBlur(crop, 51)
        ink = ((bg.astype(np.int16) - st.astype(np.int16)) > 18).astype(np.uint8)
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        m = norm40(ink)
        if m is None:
            continue
        feats.append(m.ravel())
        metas.append({"page": page, "num_cells": len(num_cells), "hval": hval})
    for d in docs.values():
        d.close()
    print("numeral crops", len(feats))
    if len(feats) < 50:
        print("too few"); return
    X = np.stack(feats)
    Zn = (X > 0.45).astype(np.float32)
    Zn -= Zn.mean(axis=1, keepdims=True)
    Zn /= (np.linalg.norm(Zn, axis=1, keepdims=True) + 1e-6)
    rng = np.random.default_rng(0)
    samp = Zn[rng.choice(len(Zn), min(6000, len(Zn)), replace=False)]
    U, S, Vt = np.linalg.svd(samp, full_matrices=False)
    P = Vt[:40].T
    Xp = Zn @ P
    Xp /= (np.linalg.norm(Xp, axis=1, keepdims=True) + 1e-6)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-4)
    _, labels, _ = cv2.kmeans(Xp.astype(np.float32), args.k, None, crit, 6,
                              cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    # 每簇多数票
    votes = collections.defaultdict(collections.Counter)
    for meta, l in zip(metas, labels):
        votes[int(l)][meta["hval"]] += 1
    out_labels = {}
    for l, cnt in votes.items():
        lab, n = cnt.most_common(1)[0]
        tot = sum(cnt.values())
        if tot >= 15 and n / tot >= 0.6:
            out_labels[l] = {"value": lab, "n": tot, "pure": round(n / tot, 2),
                             "dist": cnt.most_common(4)}
    np.savez_compressed(os.path.join(args.out, "mining.npz"),
                        X=X, P=P, Xp=Xp, labels=labels)
    json.dump(out_labels, open(os.path.join(args.out, "labels.json"), "w"),
              ensure_ascii=False)
    print("clusters labeled", len(out_labels), "/", args.k)
    for l in sorted(out_labels):
        print(f"  c{l}: {out_labels[l]}")
    # montage
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", 18)
    cnt = collections.Counter(labels.tolist())
    order = [l for l, _ in cnt.most_common()]
    cols = 12
    rows_n = (len(order) + cols - 1) // cols
    T = 72
    S_ = Image.new("L", (cols * (T + 8), rows_n * (T + 30)), 255)
    d = ImageDraw.Draw(S_)
    for k, l in enumerate(order):
        idx = np.where(labels == l)[0][0]
        x = (k % cols) * (T + 8); y = (k // cols) * (T + 30)
        S_.paste(Image.fromarray((X[idx].reshape(SIZE, SIZE) * 255).astype(np.uint8))
                 .resize((T, T), Image.LANCZOS), (x, y + 26))
        info = out_labels.get(l)
        d.text((x + 1, y + 2), f"c{l}:{cnt[l]} {info['value'] if info else '?'}", font=f, fill=0)
    S_.save(os.path.join(args.out, "clusters.png"))
    print("saved", args.out)


if __name__ == "__main__":
    main()
