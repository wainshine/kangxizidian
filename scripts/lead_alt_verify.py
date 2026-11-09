#!/usr/bin/env python3
"""替代框（+alt / qa_retry）内容验证：VLM 注文指纹复核后决定保留/剔除（审计 P0-A 修复）。

对每个挂起字：裁其框下方注文条 → Qwen3-VL 转写 → 与 kx_full 注文中该字（±8 条窗口）匹配，
top1==该字 且 score≥0.25 → 视为通过；否则剔除。
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT = "转写图中竖排文字（古籍注文），保持繁体字形，按自上而下顺序输出文字。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(ROOT, "work/lead/v231_fix_report.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/alt_verify.json"))
    ap.add_argument("--score-min", type=float, default=0.25)
    args = ap.parse_args()
    import collections
    import numpy as np
    import torch
    import fitz
    import openpyxl
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    rep = json.load(open(args.report))
    items = rep["suspended_list"]
    print("suspended", len(items), flush=True)
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"),
                                read_only=True)
    ws = wb["kx"]
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    canon = [json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    pos = {c: i for i, c in enumerate(canon)}

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
        ch = it["char"]; page = it["page"]; box = it["box"]
        vol = page[:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(page[3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in box]
        y0 = b[3] + 8
        strip = img[y0:min(img.shape[0], y0 + 900), b[0]:b[2]]
        txt = ""
        if strip.size and strip.shape[1] >= 20:
            im = Image.fromarray(strip).convert("RGB")
            messages = [{"role": "user", "content": [
                {"type": "image", "image": im}, {"type": "text", "text": PROMPT}]}]
            inputs = proc.apply_chat_template(messages, add_generation_prompt=True,
                                              tokenize=True, return_dict=True,
                                              return_tensors="pt")
            inputs = {k: (v.to("mps") if hasattr(v, "to") else v) for k, v in inputs.items()}
            with torch.no_grad():
                o = model.generate(**inputs, max_new_tokens=260, do_sample=False)
            txt = proc.batch_decode(o[:, inputs["input_ids"].shape[1]:],
                                    skip_special_tokens=True)[0].replace("\n", "")
        ci = pos.get(ch)
        top1, sc = "", 0.0
        if ci is not None:
            cand = canon[max(0, ci - 8):ci + 9]
            best = max(((score(txt, kx.get(c, "")), c) for c in cand), default=(0.0, ""))
            sc, top1 = best
        ok = (top1 == ch and sc >= args.score_min)
        out.append({"char": ch, "page": page, "half": it.get("half"), "box": box,
                    "src": it.get("src", ""), "vlm": txt[:120],
                    "top1": top1, "score": round(sc, 3), "ok": ok})
        print(ch, "->", top1, round(sc, 2), "OK" if ok else "X", flush=True)
    for d in docs.values():
        d.close()
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
    print("passed", sum(1 for x in out if x["ok"]), "/", len(out))


if __name__ == "__main__":
    main()
