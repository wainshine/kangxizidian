#!/usr/bin/env python3
"""v2.4.6 重定位：在正典序邻居区间内，用 300dpi 墨迹聚类生成「字头候选框」
（含 二/三 类横画分离字的竖向堆叠合并），再用 VLM 注文指纹验证内容。

输出 work/lead/v246_relocated.jsonl
用法：.venv/bin/python scripts/lead_relocate_v246.py --limit 24 --per-char 8
"""
import argparse, collections, json, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENERS = ("唐韻", "廣韻", "集韻", "正韻", "韻會", "說文", "玉篇", "增韻", "篇海", "字彙",
           "龍龕", "釋名", "廣雅", "爾雅", "揚子", "五音", "類篇", "正字", "佩觿", "六書",
           "干祿", "字林", "古今", "集注", "唐本", "蜀本")
PROMPT = "转写图中竖排文字（古籍注文），保持繁体字形，按自上而下顺序输出文字。"


def grams(s, n=2):
    return collections.Counter(s[i:i + n] for i in range(max(0, len(s) - n + 1))) if len(s) >= n else collections.Counter()


def score(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return sum((ga & gb).values()) / min(sum(ga.values()), sum(gb.values()))


def starts_opener(t):
    t = (t or "").lstrip("【〔「『 ")
    return any(t.startswith(o) for o in OPENERS)


def gutter_split(gray):
    """检测跨页中缝（白色竖带）位置（300dpi x 坐标）；失败回退图像中心。"""
    import cv2
    import numpy as np
    h, w = gray.shape
    small = cv2.resize(gray, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    ink = (small < 150).astype(np.uint8)
    colsum = ink.sum(axis=0)
    lo, hi = int(len(colsum) * 0.36), int(len(colsum) * 0.64)
    seg = colsum[lo:hi]
    if len(seg) == 0:
        return w // 2
    # 找最长的低墨窗口（>2% 宽度）
    thr = max(2, int(seg.min() + 2))
    best = None
    run = 0
    for i, v in enumerate(seg):
        if v <= thr:
            run += 1
            if best is None or run > best[1]:
                best = (i - run + 1, run)
        else:
            run = 0
    if best and best[1] >= max(4, len(colsum) // 60):
        center = (lo + best[0] + best[1] // 2) * 4
        if abs(center - w // 2) < w * 0.18:
            return center
    return w // 2


def ink_groups(gray, half_x):
    """返回 150dpi 当量的字头候选框（聚类 + 竖向堆叠合并）。"""
    import cv2
    import numpy as np
    # 背景归一化（扫描页明暗不均）+ 去斑噪声
    bg = cv2.medianBlur(gray, 41)
    g = np.clip(gray.astype(np.int16) - bg.astype(np.int16) + 200, 0, 255).astype(np.uint8)
    g = cv2.medianBlur(g, 3)
    thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (g < max(110, int(thr) - 5)).astype(np.uint8)
    # 去斑噪声
    n0, lab0, st0, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n0):
        if st0[i, cv2.CC_STAT_AREA] >= 60:
            keep[lab0 == i] = 1
    ink = keep
    # 去长线（版框/栏线）
    h, w = ink.shape
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(300, w // 8), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(400, h // 8)))
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk)
    vl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk)
    ink2 = cv2.subtract(ink, cv2.bitwise_or(hl, vl))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink2, 8)
    comps = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if area < 120 or cw < 8 or ch < 8:
            continue
        comps.append([x, y, cw, ch, area])
    # 聚类：相邻（gap<=14px@300）合并
    def near(a, b, gap=16):
        ax0, ay0, aw, ah = a[:4]; bx0, by0, bw, bh = b[:4]
        return not (ax0 + aw + gap < bx0 or bx0 + bw + gap < ax0 or
                    ay0 + ah + gap < by0 or by0 + bh + gap < ay0)
    changed = True
    groups = [c[:] for c in comps]
    while changed:
        changed = False
        out = []
        used = [False] * len(groups)
        for i in range(len(groups)):
            if used[i]:
                continue
            gi = groups[i][:]
            for j in range(i + 1, len(groups)):
                if used[j]:
                    continue
                if near(gi, groups[j]):
                    gj = groups[j]
                    x0 = min(gi[0], gj[0]); y0 = min(gi[1], gj[1])
                    x1 = max(gi[0] + gi[2], gj[0] + gj[2]); y1 = max(gi[1] + gi[3], gj[1] + gj[3])
                    if (x1 - x0) > 430 or (y1 - y0) > 430:
                        continue
                    gi = [x0, y0, x1 - x0, y1 - y0, gi[4] + gj[4]]
                    used[j] = True; changed = True
            out.append(gi)
        groups = out
    # 竖向堆叠合并（二/三/亖：同列、横画独立）——只对扁平横画生效，避免注文列被并成大块
    groups = [c for c in groups]
    groups.sort(key=lambda c: (c[1], c[0]))
    merged = []
    used = [False] * len(groups)
    for i in range(len(groups)):
        if used[i]:
            continue
        gi = groups[i][:]
        for j in range(len(groups)):
            if i == j or used[j]:
                continue
            gj = groups[j]
            # 同列（x 重叠 >=60%）
            ox = max(0, min(gi[0] + gi[2], gj[0] + gj[2]) - max(gi[0], gj[0]))
            if ox < 0.55 * min(gi[2], gj[2]):
                continue
            # 仅当两个成分都是扁平横画（h < 0.6*w）才做竖向堆叠合并
            if not (gi[3] < 0.6 * gi[2] and gj[3] < 0.6 * gj[2]):
                continue
            gap = max(gi[1], gj[1]) - min(gi[1] + gi[3], gj[1] + gj[3])
            if gap <= 90:
                x0 = min(gi[0], gj[0]); y0 = min(gi[1], gj[1])
                x1 = max(gi[0] + gi[2], gj[0] + gj[2]); y1 = max(gi[1] + gi[3], gj[1] + gj[3])
                if (y1 - y0) <= 330 and (x1 - x0) <= 430:
                    gi = [x0, y0, x1 - x0, y1 - y0, gi[4] + gj[4]]
                    used[j] = True
        merged.append(gi)
    outs = []
    for x, y, cw, ch, area in merged:
        w150, h150 = cw / 2.0, ch / 2.0
        if not (max(w150, h150) >= 58 and max(w150, h150) <= 175):
            continue
        if w150 < 26 or h150 < 20:
            continue
        if area < 2600:
            continue
        outs.append([int(round(x / 2)), int(round(y / 2)), int(round((x + cw) / 2)), int(round((y + ch) / 2))])
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--force", default="三二今令王永四曰爲與彙相疏縣都春屬徐氣合秦內")
    ap.add_argument("--per-char", type=int, default=8)
    ap.add_argument("--score-min", type=float, default=0.4)
    ap.add_argument("--margin-min", type=float, default=0.1)
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    import numpy as np, fitz, torch, openpyxl
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText

    ana = json.load(open(os.path.join(ROOT, "work/lead/v244_missing_analysis.json"), encoding="utf-8"))
    missing = set(ana["missing"])
    forced = [c for c in args.force if c in missing]
    prio = forced + [c for c in ana["priority"][: args.limit] if c not in forced and c in missing]
    prio = list(dict.fromkeys(prio))

    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8")]
    cindex = {e["char"]: i for i, e in enumerate(canon)}
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v243.json"), encoding="utf-8"))["chars"]
    used = collections.defaultdict(set)
    for c, r in man.items():
        used[(r["page"], r["half"])].add(tuple(r["box"]))
    # 已重定位（含先前 v245）
    out_path = os.path.join(ROOT, "work/lead/v246_relocated.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            try: done.add(json.loads(l)["char"])
            except Exception: pass
    fo = open(out_path, "a", encoding="utf-8")

    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"), read_only=True)
    for row in wb["kx"].iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    chars = [e["char"] for e in canon]
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))

    model = AutoModelForImageTextToText.from_pretrained(
        os.path.join(ROOT, "work/models/qwen3vl2b"), dtype=torch.float16, trust_remote_code=True).to("mps").eval()
    proc = AutoProcessor.from_pretrained(os.path.join(ROOT, "work/models/qwen3vl2b"), trust_remote_code=True)
    docs = {}
    t0 = time.time(); n_try = 0; n_ok = 0
    for ch in prio:
        if ch in done:
            continue
        i = cindex[ch]
        prev = next(((canon[j]["char"], man[canon[j]["char"]]) for j in range(i - 1, max(-1, i - 300), -1)
                     if canon[j]["char"] in man), None)
        nxt = next(((canon[j]["char"], man[canon[j]["char"]]) for j in range(i + 1, min(len(canon), i + 300))
                    if canon[j]["char"] in man), None)
        if not prev or not nxt:
            continue
        p0 = int(prev[1]["page"][3:]); p1 = int(nxt[1]["page"][3:])
        pages = range(p0, p1 + 1)
        cands = []
        for p in pages:
            page = f"{prev[1]['page'][:2]}_{p:04d}"
            vol = page[:2]
            if vol not in docs:
                docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            pix = docs[vol][p - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            gx = gutter_split(gray)
            # R 半版 = 中缝右侧（阅读序先 R 后 L）
            for half, (x0, x1) in (("R", (gx, gray.shape[1])), ("L", (0, gx))):
                sub = gray[:, x0:x1]
                for bx150 in ink_groups(sub, x0):
                    bx = [bx150[0] + x0 // 2, bx150[1], bx150[2] + x0 // 2, bx150[3]]
                    if tuple(bx) in used[(page, half)]:
                        continue
                    cands.append((page, half, bx))
        # 阅读序过滤 + 距离排序
        def rkey(page, half, bx):
            return (int(page[3:]), 0 if half == "R" else 1, -bx[0], bx[1])
        kp = rkey(prev[1]["page"], prev[1]["half"], prev[1]["box"])
        kn = rkey(nxt[1]["page"], nxt[1]["half"], nxt[1]["box"])
        frac = (i - cindex[prev[0]]) / max(1, cindex[nxt[0]] - cindex[prev[0]])
        # 页内 y 位置弱约束：跨页时不做 y 过滤
        scored = []
        for page, half, bx in cands:
            k = rkey(page, half, bx)
            if not (kp < k < kn):
                continue
            pos = (k[0] * 2 + k[1]) * 1000 + (-k[2])
            posp = (kp[0] * 2 + kp[1]) * 1000 + (-kp[2])
            posn = (kn[0] * 2 + kn[1]) * 1000 + (-kn[2])
            exp = posp + (posn - posp) * frac
            scored.append((abs(pos - exp), page, half, bx))
        scored.sort()
        for dist, page, half, bx in scored[: args.per_char]:
            vol = page[:2]
            pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            bb = [int(v) * 2 for v in bx]
            y0 = bb[3] + 8
            strip = gray[y0:min(gray.shape[0], y0 + 900), bb[0]:bb[2]]
            if strip.size == 0 or strip.shape[1] < 20:
                continue
            im = Image.fromarray(strip).convert("RGB")
            messages = [{"role": "user", "content": [{"type": "image", "image": im},
                                                    {"type": "text", "text": PROMPT}]}]
            inputs = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                              return_dict=True, return_tensors="pt")
            inputs = {k: (v.to("mps") if hasattr(v, "to") else v) for k, v in inputs.items()}
            try:
                with torch.no_grad():
                    o = model.generate(**inputs, max_new_tokens=260, do_sample=False)
                txt = proc.batch_decode(o[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0].replace("\n", "")
            except Exception:
                txt = ""
            n_try += 1
            cc = chars[max(0, i - args.window):i + args.window + 1]
            ranked = sorted(((score(txt, kx.get(c, "")), c) for c in cc), reverse=True)
            (s1, top1), (s2, top2) = ranked[0], ranked[1]
            margin = s1 - s2
            ok = (top1 == ch and s1 >= args.score_min and margin >= args.margin_min
                  and len(txt) >= 4 and starts_opener(txt))
            if ok:
                rec = {"char": ch, "page": page, "half": half, "box": list(bx),
                       "vlm": txt[:200], "top1": top1, "score1": round(s1, 3),
                       "top2": top2, "score2": round(s2, 3), "margin": round(margin, 3),
                       "dist": round(dist, 1)}
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
                n_ok += 1
                break
        if n_try and n_try % 50 == 0:
            el = time.time() - t0
            print(f"try {n_try}, ok {n_ok}, {el:.0f}s ({el/n_try:.2f}s)", flush=True)
    fo.close()
    print(json.dumps({"tried": n_try, "passed": n_ok, "out": out_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
