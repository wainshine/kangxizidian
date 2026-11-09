#!/usr/bin/env python3
"""注文指纹 v2（VLM）：字头下方注文条 → VLM 转写 → 与 kx_full 注文序列匹配 → 反推字头字。

用途：为「未确认字」的候选框做独立证据（不依赖单字识别）。
"""
import argparse, json, os, sys, time, collections
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT = "转写图中竖排文字（古籍注文），保持繁体字形，按自上而下顺序输出文字。"


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


def ngram_score(a, b, n=2):
    if len(a) < n or len(b) < n:
        return 0.0
    ga = collections.Counter(a[i:i + n] for i in range(len(a) - n + 1))
    gb = collections.Counter(b[i:i + n] for i in range(len(b) - n + 1))
    inter = sum((ga & gb).values())
    return inter / max(1, min(sum(ga.values()), sum(gb.values())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(ROOT, "work/models/qwen3vl2b"))
    ap.add_argument("--cands", default=os.path.join(ROOT, "work/lead/verify_candidates.json"))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--strip-h", type=int, default=900)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/vlm_fingerprint_sample.jsonl"))
    args = ap.parse_args()
    import torch
    import fitz
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
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
        hi = segs[i + 1]["page"] - 1 if (i + 1 < len(segs) and segs[i + 1]["vol"] == s["vol"]) else 10 ** 9
        for p in roles[s["vol"]]:
            if s["page"] <= p <= hi:
                page_seg[f"{s['vol']}_{p:04d}"] = i
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, dtype=torch.float16, trust_remote_code=True).to("mps").eval()
    proc = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    items = json.load(open(args.cands))[: args.limit]
    docs = {}
    out = []
    for it in items:
        page = it["page"]; box = it["box"]; hint = it.get("char")
        vol = page[:2]
        si = page_seg.get(page)
        if si is None:
            continue
        s = segs[si]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in box]
        y0 = b[3] + 8
        strip = img[y0:min(img.shape[0], y0 + args.strip_h), b[0]:b[2]]
        if strip.size == 0 or strip.shape[1] < 20:
            continue
        im = Image.fromarray(strip).convert("RGB")
        messages = [{"role": "user", "content": [
            {"type": "image", "image": im}, {"type": "text", "text": PROMPT}]}]
        inputs = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt")
        inputs = {k: (v.to("mps") if hasattr(v, "to") else v) for k, v in inputs.items()}
        t0 = time.time()
        with torch.no_grad():
            o = model.generate(**inputs, max_new_tokens=260, do_sample=False)
        dt = time.time() - t0
        txt = proc.batch_decode(o[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        txt = txt.replace("\n", "")
        # 候选层：该部内 ±80 条
        lo = max(s["lo"], s["lo"])
        ent_chars = chars[s["lo"]:s["hi"]]
        scores = [(ngram_score(txt, kx.get(c, "")), c) for c in ent_chars]
        scores.sort(reverse=True)
        top1 = scores[0] if scores else (0.0, "")
        out.append({"page": page, "box": box, "hint": hint, "vlm": txt[:120],
                    "top": top1[1], "score": round(top1[0], 3),
                    "hit": top1[1] == hint, "sec": round(dt, 1)})
        print(page, "hint", hint, "-> top", top1[1], round(top1[0], 2),
              "OK" if top1[1] == hint else "X", round(dt, 1), "s", flush=True)
    for d in docs.values():
        d.close()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ok = sum(1 for r in out if r["hit"])
    print("hit", ok, "/", len(out))


if __name__ == "__main__":
    main()
