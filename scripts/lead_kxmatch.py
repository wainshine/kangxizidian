#!/usr/bin/env python3
"""Lead · 注文指纹定位：候选字头下方注文小字 → 拼行 OCR → 与 kx_full 注文序列模糊匹配。

用于在不依赖字头识别的情况下确定「这个候选框属于哪一条目」。
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_kx():
    import openpyxl
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"),
                                read_only=True)
    ws = wb["kx"]
    txt = {}
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            txt.setdefault(str(row[0]), str(row[7] or ""))
    return txt


def sw_score(a, b):
    """Smith-Waterman 相似度（返回最佳局部对齐分 / max(len)）"""
    if not a or not b:
        return 0.0
    n, m = len(a), len(b)
    prev = np.zeros(m + 1, dtype=np.int32)
    best = 0
    for i in range(1, n + 1):
        cur = np.zeros(m + 1, dtype=np.int32)
        ai = a[i - 1]
        for j in range(1, m + 1):
            v = prev[j - 1] + (2 if ai == b[j - 1] else -1)
            v = max(v, prev[j] - 1, cur[j - 1] - 1, 0)
            cur[j] = v
            if v > best:
                best = v
        prev = cur
    return best / max(1, max(len(a), min(len(b), 30)))


def column_lines(img, box, strip_h=1100):
    """字头下方区域：先按垂直投影切出注文列，再逐列把小字拼成横排行图（返回候选行图列表）"""
    x0, y0, x1, y1 = [int(v) * 2 for v in box]
    h, w = img.shape
    ya = min(h - 1, y1 + 12)
    yb = min(h, ya + strip_h)
    m = 24
    strip = img[ya:yb, max(0, x0 - m):min(w, x1 + m)]
    if strip.size == 0 or strip.shape[1] < 20:
        return []
    b = (strip < 120).astype(np.uint8)
    b = cv2.medianBlur(b * 255, 3) // 255
    # 垂直投影（平滑）→ 列带（合并小间隙）
    vp = b.sum(axis=0).astype(np.float32)
    thr = max(8.0, 0.18 * float(vp.max()))
    bands = []; start = None
    for i, v in enumerate(vp > thr):
        if v and start is None:
            start = i
        if not v and start is not None:
            bands.append((start, i)); start = None
    if start is not None:
        bands.append((start, len(vp)))
    cols = []
    for band in bands:
        if cols and band[0] - cols[-1][1] <= 4:
            cols[-1] = (cols[-1][0], band[1])
        else:
            cols.append(band)
    cols = [c for c in cols if c[1] - c[0] >= 30]
    cols.sort()
    if not cols:
        return []
    # 按与字头中心的距离排序，取前 2 列
    center = (x1 - max(0, x0 - m)) / 2
    cols.sort(key=lambda c: abs((c[0] + c[1]) / 2 - center))
    out = []
    for (ca, cb) in cols[:2]:
        sub = strip[:, ca:cb]
        sb = b[:, ca:cb]
        proj = sb.sum(axis=1)
        thr2 = max(4, int(np.percentile(proj, 55)))
        rows = proj > thr2
        segs = []; start = None
        for i, v in enumerate(rows):
            if v and start is None:
                start = i
            if not v and start is not None:
                segs.append((start, i)); start = None
        if start is not None:
            segs.append((start, len(rows)))
        segs = [s for s in segs if 16 <= s[1] - s[0] <= 150]
        if len(segs) < 4:
            continue
        H = 96; parts = []
        for a, b2 in segs[:26]:
            g = sub[a:b2]
            if g.shape[0] < 20:
                continue
            g = cv2.resize(g, (max(2, int(round(g.shape[1] * H / g.shape[0]))), H),
                           interpolation=cv2.INTER_CUBIC)
            parts.append(cv2.copyMakeBorder(g, 4, 4, 3, 3, cv2.BORDER_CONSTANT, value=255))
        line = np.hstack(parts)
        out.append(cv2.copyMakeBorder(line, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=os.path.join(ROOT, "work/map/charalign14"))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/kxmatch_test.jsonl"))
    args = ap.parse_args()
    import fitz
    from paddleocr import TextRecognition
    rec = TextRecognition(model_name="PP-OCRv6_medium_rec")
    try:
        rec5 = TextRecognition(model_name="PP-OCRv5_server_rec")
    except Exception:
        rec5 = None
    kx = load_kx()
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    rad_entries = collections.Counter(e["rad"] for e in canon)
    anchors = [json.loads(l) for l in open(os.path.join(
        ROOT, "work/lead/bu_start_pages_lead3.jsonl"), encoding="utf-8")]
    by_vol = collections.defaultdict(list)
    for a in anchors:
        by_vol[a["vol"]].append(a)
    segs = []
    cum = 0
    for vol in sorted(by_vol):
        for a in sorted(by_vol[vol], key=lambda x: x["page"]):
            segs.append({"vol": vol, "rad": a["radical"], "page": a["page"], "lo": cum,
                         "hi": cum + rad_entries[a["radical"]]})
            cum += rad_entries[a["radical"]]
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body" and r["vol"] in [f"{i:02d}" for i in range(1, 13)]:
            roles[r["vol"]].append(r["page"])
    page_seg = {}
    for i, s in enumerate(segs):
        hi_page = segs[i + 1]["page"] - 1 if (i + 1 < len(segs) and segs[i + 1]["vol"] == s["vol"]) else 10 ** 9
        for p in roles[s["vol"]]:
            if s["page"] <= p <= hi_page:
                page_seg[f"{s['vol']}_{p:04d}"] = i
    rows = [json.loads(l) for l in open(os.path.join(args.map, "mapping.jsonl"), encoding="utf-8")]
    conf = []
    for r in rows:
        for a in r["assigned"]:
            if a.get("ocr_ok") and (a.get("ocr_score") or 0) >= 0.9 and r["page"] in page_seg:
                conf.append((r["page"], r["half"], a["char"], a["cand"]["box"]))
    import random
    random.seed(1)
    sample = random.sample(conf, args.limit)
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    docs = {}
    out = []
    for page, half, ch, box in sample:
        vol = page[:2]; pg = int(page[3:])
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][pg - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        lines = column_lines(img, box)
        si = page_seg[page]; s = segs[si]
        cand_entries = chars[s["lo"]:s["hi"]]
        best_all = (0.0, "", "")
        txts = []
        for li, line in enumerate(lines):
            cv2.imwrite(f"/tmp/kxmatch_{li}.png", line)
            o = rec.predict(f"/tmp/kxmatch_{li}.png")
            r = o[0].json.get("res", {})
            t = r.get("rec_text", "") or ""
            t2 = ""
            if rec5 is not None:
                try:
                    o5 = rec5.predict(f"/tmp/kxmatch_{li}.png")
                    r5 = o5[0].json.get("res", {})
                    t2 = r5.get("rec_text", "") or ""
                except Exception:
                    t2 = ""
            tt = (t + "|" + t2).strip("|")
            txts.append(tt)
            for x in (t, t2):
                if not x:
                    continue
                scores = [(sw_score(x, kx.get(c, "")), c) for c in cand_entries]
                scores.sort(reverse=True)
                if scores and scores[0][0] > best_all[0]:
                    best_all = (scores[0][0], scores[0][1], x)
        txt = " / ".join(txts)
        top = (best_all[0], best_all[1])
        hit = top[1] == ch
        out.append({"page": page, "half": half, "truth": ch, "ocr": txt,
                    "top": top[1], "score": round(top[0], 3), "hit": hit})
        print(page, half, "truth", ch, "ocr", txt[:24], "-> top", top[1], round(top[0], 3),
              "OK" if hit else "X", flush=True)
    for d in docs.values():
        d.close()
    ok = sum(1 for r in out if r["hit"])
    print("top1", ok, "/", len(out))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
