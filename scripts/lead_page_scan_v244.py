#!/usr/bin/env python3
"""v2.4.4 页面级反查：对指定缺失字，在「正典序邻居页」范围内枚举检测候选框，
VLM 转写框下注文条 → 与 kx_full 该字注文 2-gram 匹配（窗口±60），
条件：top1==target + score>=0.35 + margin>=0.05（二/三 类注文以〔古文〕开头，不强制音切 opener）。

输出 work/lead/v244_page_scan.jsonl（每个命中的字一行，含证据）
"""
import argparse, collections, json, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = "转写图中竖排文字（古籍注文），保持繁体字形，按自上而下顺序输出文字。"
OPENERS = ("唐韻", "廣韻", "集韻", "正韻", "韻會", "說文", "玉篇", "增韻", "篇海", "字彙",
           "龍龕", "釋名", "廣雅", "爾雅", "揚子", "五音", "類篇", "正字", "佩觿", "六書",
           "干祿", "字林", "古今", "集注", "唐本", "蜀本")


def opener_near_start(t, span=12):
    t = (t or "").lstrip("【〔「『 　")
    head = t[:span]
    if "古文" in head:
        return True
    return any(head.startswith(o) or o in head[:6] for o in OPENERS)


def grams(s, n=2):
    return collections.Counter(s[i:i + n] for i in range(max(0, len(s) - n + 1))) if len(s) >= n else collections.Counter()


def score(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return sum((ga & gb).values()) / min(sum(ga.values()), sum(gb.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chars", default="二三四今令王永曰爲與彙相疏縣都春屬徐氣合秦內")
    ap.add_argument("--score-min", type=float, default=0.35)
    ap.add_argument("--margin-min", type=float, default=0.05)
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--per-page", type=int, default=40)
    args = ap.parse_args()

    import numpy as np, fitz, torch, openpyxl
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText

    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8")]
    cindex = {e["char"]: i for i, e in enumerate(canon)}
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v243.json"), encoding="utf-8"))["chars"]
    targets = [c for c in args.chars if c in cindex]
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"), read_only=True)
    for row in wb["kx"].iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    chars = [e["char"] for e in canon]
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    out_path = os.path.join(ROOT, "work/lead/v244_page_scan.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            try: done.add(json.loads(l)["char"])
            except Exception: pass
    fo = open(out_path, "a", encoding="utf-8")

    model = AutoModelForImageTextToText.from_pretrained(
        os.path.join(ROOT, "work/models/qwen3vl2b"), dtype=torch.float16, trust_remote_code=True).to("mps").eval()
    proc = AutoProcessor.from_pretrained(os.path.join(ROOT, "work/models/qwen3vl2b"), trust_remote_code=True)
    docs = {}
    t0 = time.time(); n = 0
    for ch in targets:
        if ch in done:
            print("skip", ch, flush=True); continue
        i = cindex[ch]
        prev = next(((canon[j]["char"], man[canon[j]["char"]]) for j in range(i - 1, max(-1, i - 300), -1)
                     if canon[j]["char"] in man), None)
        nxt = next(((canon[j]["char"], man[canon[j]["char"]]) for j in range(i + 1, min(len(canon), i + 300))
                    if canon[j]["char"] in man), None)
        if not prev or not nxt:
            continue
        p0 = int(prev[1]["page"][3:]); p1 = int(nxt[1]["page"][3:])
        best = None
        for p in range(p0, p1 + 1):
            page = f"{prev[1]['page'][:2]}_{p:04d}"
            vol = page[:2]
            if vol not in docs:
                docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            d = json.load(open(os.path.join(ROOT, "work/lead/boxes300", f"{page}.json"), encoding="utf-8"))
            pix = docs[vol][p - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            # 候选：检测框 + 尺寸放宽（40-210），去重
            cands = []
            seen = set()
            for half, h in d.get("halves", {}).items():
                for cd in h.get("cands", []):
                    bx = tuple(int(v) for v in cd["box"])
                    w, hh = cd["w"], cd["h"]
                    if not (60 <= max(w, hh) <= 220 and min(w, hh) >= 24):
                        continue
                    if bx in seen:
                        continue
                    seen.add(bx)
                    cands.append((half, bx))
            # 页内候选按位置：只保留相邻邻居之间的页（位置过滤在匹配阶段完成）
            for half, bx in cands[: args.per_page]:
                b = [v * 2 for v in bx]
                y0 = b[3] + 8
                strip = gray[y0:min(gray.shape[0], y0 + 1000), b[0]:b[2]]
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
                n += 1
                cc = chars[max(0, i - args.window):i + args.window + 1]
                ranked = sorted(((score(txt, kx.get(c, "")), c) for c in cc), reverse=True)
                (s1, top1), (s2, top2) = ranked[0], ranked[1]
                margin = s1 - s2
                rec = {"char": ch, "page": page, "half": half, "box": list(bx),
                       "vlm": txt[:200], "top1": top1, "score1": round(s1, 3),
                       "top2": top2, "score2": round(s2, 3), "margin": round(margin, 3),
                       "pass": bool(top1 == ch and s1 >= args.score_min and margin >= args.margin_min
                                 and len(txt) >= 4 and opener_near_start(txt, 12))}
                if rec["pass"]:
                    if best is None or rec["score1"] > best["score1"]:
                        best = rec
            if n and n % 100 == 0:
                el = time.time() - t0
                print(f"vlm {n}, {el:.0f}s ({el/n:.2f}s)", flush=True)
        if best:
            fo.write(json.dumps(best, ensure_ascii=False) + "\n"); fo.flush()
            print("HIT", ch, best["page"], best["half"], best["box"], best["score1"], flush=True)
        else:
            print("miss", ch, flush=True)
    fo.close()
    print(json.dumps({"vlm_calls": n, "out": out_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
