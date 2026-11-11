#!/usr/bin/env python3
"""VLM OCR 测试：用视觉语言模型识别单个木刻汉字（并对比传统 OCR）。

用法：
  .venv/bin/python scripts/vlm_ocr_test.py --model work/models/qwen3vl2b --limit 20
"""
import argparse, json, os, sys, time
import numpy as np
import torch
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load_crops(limit, source):
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    if source == "unbiased":
        items = json.load(open(os.path.join(ROOT, "work/lead/bench_unbiased_labels.json")))
        items = [{"page": it["page"], "box": it["box"], "char": it["char"]} for it in items]
    else:
        items = json.load(open(os.path.join(ROOT, "work/lead/verify_candidates.json")))
        items = [{"page": it["page"], "box": it["box"], "char": it.get("char")} for it in items]
    items = items[:limit]
    docs = {}
    from PIL import Image
    out = []
    for it in items:
        vol = it["page"][:2]
        if vol not in docs:
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
        pix = docs[vol][int(it["page"][3:]) - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        b = [int(v) * 2 for v in it["box"]]
        pad = 10
        crop = img[max(0, b[1] - pad):b[3] + pad, max(0, b[0] - pad):b[2] + pad]
        if crop.size == 0:
            continue
        out.append({"page": it["page"], "box": it["box"], "char": it["char"],
                    "image": Image.fromarray(crop).convert("RGB")})
    for d in docs.values():
        d.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--source", default="unbiased", choices=["unbiased", "rare"])
    ap.add_argument("--max-new-tokens", type=int, default=8)
    ap.add_argument("--out", default="")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dtype", default="float32")
    args = ap.parse_args()
    from transformers import AutoProcessor, AutoModelForImageTextToText
    print("loading", args.model, flush=True)
    t0 = time.time()
    dt = {"float32": torch.float32, "float16": torch.float16,
          "bfloat16": torch.bfloat16}[args.dtype]
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, dtype=dt, trust_remote_code=True)
    model = model.to(args.device).eval()
    proc = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    print("loaded in", round(time.time() - t0, 1), "s", flush=True)
    items = load_crops(args.limit, args.source)
    prompt = "识别图片中的单个汉字，只输出这个字本身，不要解释、不要标点。"
    ok = 0; rows = []
    for i, it in enumerate(items):
        messages = [{"role": "user", "content": [
            {"type": "image", "image": it["image"]},
            {"type": "text", "text": prompt}]}]
        inputs = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt")
        inputs = {k: (v.to(args.device) if hasattr(v, "to") else v) for k, v in inputs.items()}
        t1 = time.time()
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
        gen = out[:, inputs["input_ids"].shape[1]:]
        txt = proc.batch_decode(gen, skip_special_tokens=True)[0].strip()
        dt = time.time() - t1
        hit = (txt == it["char"])
        ok += hit
        rows.append({"page": it["page"], "truth": it["char"], "pred": txt,
                     "hit": hit, "sec": round(dt, 1)})
        print(i, it["page"], "truth", it["char"], "pred", repr(txt), "OK" if hit else "X",
              round(dt, 1), "s", flush=True)
    print(f"== {args.model}: {ok}/{len(items)} = {ok / max(1, len(items)):.2f}")
    if args.out:
        json.dump(rows, open(args.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
