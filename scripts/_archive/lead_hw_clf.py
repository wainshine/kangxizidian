#!/usr/bin/env python3
"""Lead · 字头判别器：用已 OCR 确认的字形做正样本，训练逻辑回归，给候选框打分。

特征：32x32 归一化灰度 → 8x8 池化 + 梯度方向直方图（4 bin×2x2 网格）+ 几何特征。
输出 work/lead/hw_clf.json（每个候选框的 headword 概率）
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def feat(crop):
    g = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    g = g - g.mean()
    pool = cv2.resize(g, (8, 8), interpolation=cv2.INTER_AREA).ravel()
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    ang = (np.arctan2(gy, gx) + np.pi) / (2 * np.pi)
    hog = []
    for by in range(2):
        for bx in range(2):
            m = mag[by * 16:(by + 1) * 16, bx * 16:(bx + 1) * 16]
            a = ang[by * 16:(by + 1) * 16, bx * 16:(bx + 1) * 16]
            hh, _ = np.histogram(a, bins=4, range=(0, 1), weights=m)
            hog.extend((hh / (hh.sum() + 1e-6)).tolist())
    return np.concatenate([pool, np.array(hog, np.float32)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pos", default=os.path.join(ROOT, "work/lead/clf_pos.jsonl"))
    ap.add_argument("--neg", default=os.path.join(ROOT, "work/lead/clf_neg.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hw_clf.json"))
    args = ap.parse_args()
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    pos = [json.loads(l) for l in open(args.pos, encoding="utf-8")]
    neg = [json.loads(l) for l in open(args.neg, encoding="utf-8")]
    print("pos", len(pos), "neg", len(neg), flush=True)
    import fitz, collections
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    docs = {}
    pages_need = sorted(set([p["page"] for p in pos] + [q["page"] for q in neg]))
    feats = {}
    def load(page):
        vol = page[:2]; pg = int(page[3:])
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    cache = {}
    for page in pages_need:
        cache[page] = load(page)
    def gather2(items, label):
        out = []
        for it in items:
            img = cache[it["page"]]
            b = [int(v) * 2 for v in it["box"]]
            crop = img[b[1]:b[3], b[0]:b[2]]
            if crop.size == 0 or min(crop.shape) < 20:
                continue
            out.append((it["page"], feat(crop), label))
        return out
    for d in docs.values():
        d.close()
    # 按页划分训练/测试
    import random
    random.seed(0)
    pages = sorted(set([p["page"] for p in pos] + [n["page"] for n in neg]))
    test_pages = set(random.sample(pages, max(1, len(pages) // 5)))
    Xtr, ytr, Xte, yte = [], [], [], []
    allp = gather2(pos, 1); alln = gather2(neg, 0)
    for page, f, lab in allp + alln:
        (Xte if page in test_pages else Xtr).append(f)
        (yte if page in test_pages else ytr).append(lab)
    Xtr = np.stack(Xtr); ytr = np.array(ytr, np.float32)
    Xte = np.stack(Xte); yte = np.array(yte, np.float32)
    mu = Xtr.mean(axis=0); sd = Xtr.std(axis=0) + 1e-6
    Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd
    # 逻辑回归（numpy，L2，Adam）
    w = np.zeros(Xtr.shape[1], np.float32); b = 0.0
    lr = 0.05; m_w = np.zeros_like(w); v_w = np.zeros_like(w); m_b = 0.0; v_b = 0.0
    for it in range(800):
        z = Xtr @ w + b
        p = 1 / (1 + np.exp(-z))
        grad_w = Xtr.T @ (p - ytr) / len(ytr) + 1e-3 * w
        grad_b = float((p - ytr).mean())
        m_w = 0.9 * m_w + 0.1 * grad_w; v_w = 0.999 * v_w + 0.001 * grad_w ** 2
        m_b = 0.9 * m_b + 0.1 * grad_b; v_b = 0.999 * v_b + 0.001 * grad_b ** 2
        w -= lr * (m_w / (1 - 0.9 ** (it + 1))) / (np.sqrt(v_w / (1 - 0.999 ** (it + 1))) + 1e-8)
        b -= lr * (m_b / (1 - 0.9 ** (it + 1))) / (np.sqrt(v_b / (1 - 0.999 ** (it + 1))) + 1e-8)
    zte = Xte @ w + b
    pte = 1 / (1 + np.exp(-zte))
    acc = float(((pte > 0.5) == (yte > 0.5)).mean())
    print("held-out acc", round(acc, 3), "n", len(yte))
    json.dump({"w": w.tolist(), "b": b, "mu": mu.tolist(), "sd": sd.tolist(), "acc": acc},
              open(args.out, "w"))
    print("saved", args.out)


if __name__ == "__main__":
    main()
