#!/usr/bin/env python3
"""注文指纹验证集（可复算）：demo 目检 28 + owner 逐字核实 11 的已知正确字形，
   跑 VLM 注文条转写 → 2-gram 匹配（窗口 ±60）→ 落盘 margin → 输出分阈值精度表。
"""
import json, os, sys, time
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = "转写图中竖排文字（古籍注文），保持繁体字形，按自上而下顺序输出文字。"


def main():
    import torch, fitz, openpyxl
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    demo = [json.loads(l) for l in open(os.path.join(ROOT, "work/font/demo/manifest.jsonl"))]
    owner = json.load(open(os.path.join(ROOT, "work/font/owner_verified_boxes.json")))
    seen = {}
    for g in demo:
        if g.get("page") and g.get("box"):
            seen.setdefault(g["char"], {"char": g["char"], "page": g["page"],
                                        "box": g["box"], "src": "demo"})
    for e in owner:
        seen.setdefault(e["char"], {"char": e["char"], "page": e["page"],
                                    "box": e["box"], "src": "owner"})
    items = list(seen.values())
    print("validation items", len(items), flush=True)
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"),
                                read_only=True)
    ws = wb["kx"]
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    pos = {c: i for i, c in enumerate(chars)}
    import collections

    def grams(s, n=2):
        return collections.Counter(s[i:i + n] for i in range(len(s) - n + 1)) if len(s) >= n else collections.Counter()

    def score(a, b):
        ga, gb = grams(a), grams(b)
        if not ga or not gb:
            return 0.0
        return sum((ga & gb).values()) / min(sum(ga.values()), sum(gb.values()))

    model = AutoModelForImageTextToText.from_pretrained(
        os.path.join(ROOT, "work/models/qwen3vl2b"), dtype=torch.float16,
        trust_remote_code=True).to("mps").eval()
    proc = AutoProcessor.from_pretrained(os.path.join(ROOT, "work/models/qwen3vl2b"),
                                         trust_remote_code=True)
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    docs = {}
    out = []
    for it in items:
        page = it["page"]; vol = page[:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in it["box"]]
        y0 = b[3] + 8
        strip = img[y0:min(img.shape[0], y0 + 900), b[0]:b[2]]
        if strip.size == 0 or strip.shape[1] < 20:
            continue
        im = Image.fromarray(strip).convert("RGB")
        messages = [{"role": "user", "content": [
            {"type": "image", "image": im}, {"type": "text", "text": PROMPT}]}]
        inputs = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt")
        inputs = {k: (v.to("mps") if hasattr(v, "to") else v) for k, v in inputs.items()}
        with torch.no_grad():
            o = model.generate(**inputs, max_new_tokens=260, do_sample=False)
        txt = proc.batch_decode(o[:, inputs["input_ids"].shape[1]:],
                                skip_special_tokens=True)[0].replace("\n", "")
        ci = pos.get(it["char"])
        if ci is None:
            out.append({**it, "vlm": txt, "top1": "", "score1": 0.0, "score2": 0.0,
                        "top2": "", "margin": 0.0, "ok": False, "note": "char not in canonical"})
            continue
        cand = chars[max(0, ci - 60):ci + 61]
        ranked = sorted(((score(txt, kx.get(c, "")), c) for c in cand), reverse=True)
        top1 = ranked[0] if ranked else (0.0, "")
        top2 = next(((s, c) for s, c in ranked[1:] if c != top1[1]), (0.0, ""))
        out.append({**it, "vlm": txt, "top1": top1[1], "score1": round(top1[0], 4),
                    "top2": top2[1], "score2": round(top2[0], 4),
                    "margin": round(top1[0] - top2[0], 4), "ok": top1[1] == it["char"]})
        print(it["char"], "->", top1[1], round(top1[0], 2), "margin", round(top1[0] - top2[0], 2),
              "OK" if top1[1] == it["char"] else "X", flush=True)
    for d in docs.values():
        d.close()
    json.dump(out, open(os.path.join(ROOT, "work/lead/fp_validate_repro.json"), "w"),
              ensure_ascii=False, indent=1)
    valid = [r for r in out if r.get("top1") and r["char"] in pos]
    print("valid rows", len(valid), "raw top1", sum(1 for r in valid if r["ok"]), "/", len(valid))
    for smin in (0.2, 0.3, 0.4, 0.5):
        for mm in (0.0, 0.05, 0.1):
            sel = [r for r in valid if r["score1"] >= smin and r["margin"] >= mm]
            if not sel:
                continue
            prec = sum(1 for r in sel if r["ok"]) / len(sel)
            print(f"score>={smin} margin>={mm}: n={len(sel)} prec={prec:.1%}")


if __name__ == "__main__":
    main()
