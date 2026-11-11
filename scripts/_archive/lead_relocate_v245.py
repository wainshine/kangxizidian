#!/usr/bin/env python3
"""v2.4.5 重定位：在「正典序已确认邻居之间」的检测候选框中找缺失字的真字头框，
再用 VLM 注文指纹做内容验证（候选必须落在 prev 与 next 的阅读序之间）。

输出 work/lead/v245_relocated.jsonl（通过者，含证据）
用法：.venv/bin/python scripts/lead_relocate_v245.py --limit 150 --per-char 6
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--force", default="三二今令王永四曰爲與彙相疏縣都春屬徐氣合秦內")
    ap.add_argument("--per-char", type=int, default=6)
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
    # 阅读序 key：页*2 + 半版(R=0,L=1)，同一半版内按列 x 降序、y 升序
    def rkey(page, half, box):
        return (int(page[3:]), 0 if half == "R" else 1, -box[0], box[1])
    # 邻居（正典序前后各 200 内已确认）
    def neighbors(i):
        prev = next(((canon[j]["char"], man[canon[j]["char"]]) for j in range(i - 1, max(-1, i - 300), -1)
                     if canon[j]["char"] in man), None)
        nxt = next(((canon[j]["char"], man[canon[j]["char"]]) for j in range(i + 1, min(len(canon), i + 300))
                    if canon[j]["char"] in man), None)
        return prev, nxt

    # 每页检测候选（字头级尺寸、方形度、空闲）
    boxes = collections.defaultdict(list)
    bd = os.path.join(ROOT, "work/lead/boxes300")
    pages_all = sorted(os.listdir(bd))
    for fn in pages_all:
        page = fn[:-5]
        d = json.load(open(os.path.join(bd, fn), encoding="utf-8"))
        for half, h in d.get("halves", {}).items():
            if h.get("blank"):
                continue
            for cd in h.get("cands", []):
                bx = cd.get("box"); w = cd.get("w"); hh = cd.get("h")
                if not bx or not w or not hh:
                    continue
                if not (65 <= w <= 145 and 65 <= hh <= 145):
                    continue
                sq = cd.get("feat", {}).get("squareness", 1)
                if not (0.6 <= sq <= 1.8):
                    continue
                key = (page, half, tuple(int(v) for v in bx))
                if key[2] in used[(page, half)]:
                    continue
                boxes[page].append((page, half, key[2], cd.get("feat", {})))

    # kx 注文
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"), read_only=True)
    for row in wb["kx"].iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    chars = [e["char"] for e in canon]
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))

    out_path = os.path.join(ROOT, "work/lead/v245_relocated.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            try:
                r = json.loads(l); done.add(r["char"])
            except Exception:
                pass
    fo = open(out_path, "a", encoding="utf-8")

    model = AutoModelForImageTextToText.from_pretrained(
        os.path.join(ROOT, "work/models/qwen3vl2b"), dtype=torch.float16, trust_remote_code=True).to("mps").eval()
    proc = AutoProcessor.from_pretrained(os.path.join(ROOT, "work/models/qwen3vl2b"), trust_remote_code=True)
    docs = {}
    t0 = time.time(); n_try = 0; n_ok = 0
    for ch in prio:
        if ch in done:
            continue
        i = cindex[ch]
        prev, nxt = neighbors(i)
        if not prev or not nxt:
            continue
        # 候选页范围：prev 页 .. next 页
        p0 = int(prev[1]["page"][3:]); p1 = int(nxt[1]["page"][3:])
        kp = rkey(prev[1]["page"], prev[1]["half"], prev[1]["box"])
        kn = rkey(nxt[1]["page"], nxt[1]["half"], nxt[1]["box"])
        frac = (i - cindex[prev[0]]) / max(1, cindex[nxt[0]] - cindex[prev[0]])
        cands = []
        for p in range(p0, p1 + 1):
            page = f"{prev[1]['page'][:2]}_{p:04d}"
            for page_, half, bx, feat in boxes.get(page, []):
                k = rkey(page, half, bx)
                if not (kp < k < kn):
                    continue
                # 粗略线性位置：页序 + 半版
                pos = (k[0] * 2 + k[1]) + (0.5 - k[2] / 4000.0) * 0.3
                posp = (kp[0] * 2 + kp[1]); posn = (kn[0] * 2 + kn[1])
                exp = posp + (posn - posp) * frac
                cands.append((abs(pos - exp), page_, half, bx, feat))
        cands.sort()
        tried = 0
        for dist, page, half, bx, feat in cands[: args.per_char]:
            vol = page[:2]
            if vol not in docs:
                docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
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
            tried += 1; n_try += 1
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
                       "dist": round(dist, 3), "feat": feat}
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
                n_ok += 1
                break
        if n_try and n_try % 25 == 0:
            el = time.time() - t0
            print(f"try {n_try}, ok {n_ok}, {el:.0f}s ({el/n_try:.2f}s)", flush=True)
    fo.close()
    print(json.dumps({"tried": n_try, "passed": n_ok, "out": out_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
