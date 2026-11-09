#!/usr/bin/env python3
"""VLM 注文指纹批量：对未确认字的候选框做「注文条转写 → kx_full 匹配 → 反推条目」。

输出 work/lead/vlm_fp_full.jsonl（逐条）：page/half/box/expected_ci/vlm_text/top1/score/hit_hint
"""
import json, os, time, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT = "转写图中竖排文字（古籍注文），保持繁体字形，按自上而下顺序输出文字。"


def main():
    import torch
    import fitz
    import openpyxl
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    conf = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union6.json")))
    # 未确认条目：charalign14 映射中未 OCR 确认的指派
    unconf = []
    seen = set()
    for l in open(os.path.join(ROOT, "work/map/charalign14/mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        ci = r["ci_start"]
        for i, a in enumerate(r["assigned"]):
            ch = a["char"]
            if ch in conf or ch in seen:
                continue
            seen.add(ch)
            unconf.append({"page": r["page"], "half": r["half"], "box": a["cand"]["box"],
                           "char": ch, "expected_ci": ci + i})
    print("unconfirmed entries", len(unconf), flush=True)
    kx = {}
    wb = openpyxl.load_workbook(os.path.join(ROOT, "data/ref/kangxi-dictionary/kx_full.xlsx"),
                                read_only=True)
    ws = wb["kx"]
    for row in ws.iter_rows(values_only=True):
        if row and row[0]:
            kx.setdefault(str(row[0]), str(row[7] or ""))
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"))]
    chars = [e["char"] for e in canon]
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))

    def grams(s, n=2):
        return collections.Counter(s[i:i + n] for i in range(max(0, len(s) - n + 1))) if len(s) >= n else collections.Counter()

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
    docs = {}
    out_path = os.path.join(ROOT, "work/lead/vlm_fp_full.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            try:
                r = json.loads(l)
                done.add((r["page"], r["half"], tuple(int(v) for v in r["box"])))
            except Exception:
                pass
        print("resume, done", len(done), flush=True)
    t0 = time.time()
    n = 0
    with open(out_path, "a", encoding="utf-8") as fo:
        for it in unconf:
            key = (it["page"], it["half"], tuple(int(v) for v in it["box"]))
            if key in done:
                continue
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
            try:
                with torch.no_grad():
                    o = model.generate(**inputs, max_new_tokens=260, do_sample=False)
                txt = proc.batch_decode(o[:, inputs["input_ids"].shape[1]:],
                                        skip_special_tokens=True)[0].replace("\n", "")
            except Exception as e:
                txt = ""
            ci = it["expected_ci"]
            cand = chars[max(0, ci - 60):ci + 61]
            best = max(((score(txt, kx.get(c, "")), c) for c in cand), default=(0.0, ""))
            rec = {"page": page, "half": it["half"], "box": it["box"],
                   "hint": it["char"], "expected_ci": ci,
                   "vlm": txt[:150], "top": best[1], "score": round(best[0], 3),
                   "hit_hint": best[1] == it["char"]}
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fo.flush()
            n += 1
            if n % 50 == 0:
                el = time.time() - t0
                print(f"{n} done, {el:.0f}s, {el / n:.2f}s/entry", flush=True)
    print("finished", n, flush=True)


if __name__ == "__main__":
    main()
