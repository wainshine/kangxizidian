#!/usr/bin/env python3
"""VLM 整页/半页转写测试：检验能否用于版面-文本对齐定位生僻字。"""
import argparse, json, os, sys, time
import numpy as np
import torch
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--page", default="05_0017")
    ap.add_argument("--half", default="R")
    ap.add_argument("--max-new-tokens", type=int, default=700)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    import fitz
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json")))
    vol = args.page[:2]
    doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
    pix = doc[int(args.page[3:]) - 1].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    doc.close()
    w = img.shape[1]
    half = img[:, w // 2:] if args.half == "R" else img[:, :w // 2]
    image = Image.fromarray(half).convert("RGB")
    print("half image", image.size, flush=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, torch_dtype=torch.float32, device_map="cpu", trust_remote_code=True).eval()
    proc = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    prompt = "这是一页中国古籍（康熙字典，木刻版）的竖排文字。请按阅读顺序（先右栏后左栏、每栏自上而下）转写全部文字，只输出文字本身。"
    messages = [{"role": "user", "content": [
        {"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    inputs = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                      return_dict=True, return_tensors="pt")
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
    dt = time.time() - t0
    txt = proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    print("sec", round(dt, 1), "chars", len(txt), flush=True)
    print(txt[:2000])
    if args.out:
        open(args.out, "w").write(txt)


if __name__ == "__main__":
    main()
