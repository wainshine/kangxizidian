#!/usr/bin/env python3
"""v2.4.4 重定位 + 内容验证：对缺失字在 charalign14 替代框中搜「字头级尺寸 + 空闲」候选，
用 VLM 注文指纹判定候选框内容是否真为该字，输出可回收清单。

判据（与生产确认链一致）：
  - 候选框空闲（不在当前字体占用）；尺寸 65<=w,h<=145 @150dpi（字头级）
  - 候选框下方注文条 VLM 转写 → 2-gram 匹配 kx_full 注文（窗口±60，含该字自身）
  - 通过：opener（音切开头） + score>=0.4 + margin>=0.1 + top1==target + 转写>=4 字

输出 work/lead/v244_relocated.jsonl（可回收字，含证据）/ v244_relocate_report.json
用法：.venv/bin/python scripts/lead_relocate_v244.py --limit 600
"""
import argparse, collections, json, os, sys, time

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=600)
    ap.add_argument("--force", default="三二今令王永四曰爲與彙")
    ap.add_argument("--score-min", type=float, default=0.4)
    ap.add_argument("--margin-min", type=float, default=0.1)
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    import numpy as np, fitz, torch, openpyxl
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText

    ana = json.load(open(os.path.join(ROOT, "work/lead/v244_missing_analysis.json"), encoding="utf-8"))
    missing = ana["missing"]; avail = ana["avail"]
    forced = [c for c in args.force if c in missing]
    prio = forced + [c for c in ana["priority"][: args.limit] if c not in forced]
    prio = [c for c in prio if avail.get(c, 0) > 0]

    # 当前字体占用
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v243.json"), encoding="utf-8"))["chars"]
    used = collections.defaultdict(set)
    for c, r in man.items():
        used[(r["page"], r["half"])].add(tuple(r["box"]))

    # c14 候选
    cands = collections.defaultdict(list)
    for l in open(os.path.join(ROOT, "work/map/charalign14/mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        ci = r["ci_start"]
        for i, a in enumerate(r.get("assigned", [])):
            ch = a.get("char"); box = (a.get("cand") or {}).get("box")
            if not ch or not box:
                continue
            box = tuple(int(v) for v in box)
            w, h = box[2] - box[0], box[3] - box[1]
            if not (65 <= w <= 145 and 65 <= h <= 145):
                continue
            if box in used[(r["page"], r["half"])]:
                continue
            cands[ch].append({"page": r["page"], "half": r["half"], "box": box, "ci": ci + i})

    # kx 注文
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"), read_only=True)
    ws = wb["kx"]
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8")]
    chars = [e["char"] for e in canon]
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))

    out_path = os.path.join(ROOT, "work/lead/v244_relocated.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            try:
                r = json.loads(l); done.add((r["char"], r["page"], r["half"], tuple(r["box"])))
            except Exception:
                pass
    fo = open(out_path, "a", encoding="utf-8")

    def p90_of(gray, box, pad=6):
        import cv2
        b = [int(v) * 2 for v in box]
        crop = gray[max(0, b[1] - pad * 2):b[3] + pad * 2, max(0, b[0] - pad * 2):b[2] + pad * 2]
        if crop.size == 0 or min(crop.shape) < 20:
            return 0.0
        g = cv2.medianBlur(crop, 3)
        thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        ink = (g < min(max(int(thr), 90), 215)).astype(np.uint8)
        dt = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
        vals = dt[dt > 0]
        return float(np.percentile(vals, 90)) if vals.size else 0.0

    model = AutoModelForImageTextToText.from_pretrained(
        os.path.join(ROOT, "work/models/qwen3vl2b"), dtype=torch.float16, trust_remote_code=True).to("mps").eval()
    proc = AutoProcessor.from_pretrained(os.path.join(ROOT, "work/models/qwen3vl2b"), trust_remote_code=True)
    docs = {}
    t0 = time.time(); n_acc = 0; n_try = 0
    for ch in prio:
        best = None
        for cd in cands.get(ch, [])[:3]:
            page = cd["page"]; vol = page[:2]
            if vol not in docs:
                docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            b = [int(v) * 2 for v in cd["box"]]
            y0 = b[3] + 8
            strip = gray[y0:min(gray.shape[0], y0 + 900), b[0]:b[2]]
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
            ci = cd["ci"]
            cand_chars = chars[max(0, ci - args.window):ci + args.window + 1]
            ranked = sorted(((score(txt, kx.get(c, "")), c) for c in cand_chars), reverse=True)
            (s1, top1), (s2, top2) = ranked[0], ranked[1]
            margin = s1 - s2
            p90 = p90_of(gray, cd["box"])
            ok = (top1 == ch and s1 >= args.score_min and margin >= args.margin_min
                  and len(txt) >= 4 and starts_opener(txt))
            rec = {"char": ch, "page": cd["page"], "half": cd["half"], "box": list(cd["box"]),
                   "ci": ci, "vlm": txt[:200], "top1": top1, "score1": round(s1, 3),
                   "top2": top2, "score2": round(s2, 3), "margin": round(margin, 3),
                   "p90": round(p90, 2), "pass": bool(ok)}
            if ok:
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush(); n_acc += 1
                break
            best = rec
        if n_try % 25 == 0 and n_try:
            el = time.time() - t0
            print(f"try {n_try}, pass {n_acc}, {el:.0f}s ({el/n_try:.2f}s/entry)", flush=True)
    fo.close()
    print(json.dumps({"tried": n_try, "passed": n_acc, "out": out_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
