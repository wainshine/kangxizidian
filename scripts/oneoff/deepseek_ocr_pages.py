#!/usr/bin/env python3
"""DeepSeek OCR 在线识别一轮（body 页）——一次性工具，结果仅供 role/古文标签审计。

- Key 从项目外 `guangeti/.env` 的 VISION_API_KEY 本地读取，不写入仓库/日志。
- 页面渲染 300dpi → 逆时针旋转 90°（竖排变横排）→ JPEG q88 → rich_layout_recognition。
- 逐页保存原始 JSON 到 work/lead/deepseek_ocr/<vol>/<vol>_<page>.json，可断点续跑。
- 质量差（finish_reason=length / 文本重复）自动重试 2 次，保留最佳结果；只记录元数据。
"""
import argparse, json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, cv2, fitz, requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KEY_ENV = "/Users/wainshine/newAI/guangeti/.env"
OUTDIR = os.path.join(ROOT, "work", "lead", "deepseek_ocr")
METRICS = os.path.join(ROOT, "work", "lead", "deepseek_ocr-metrics.json")
LOCK = threading.Lock()
PDF_MAP = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))


def load_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    for ln in open(KEY_ENV, encoding="utf-8"):
        if ln.startswith("VISION_API_KEY="):
            key = ln.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("no DeepSeek key")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return key, base.rstrip("/")


def body_pages():
    out = []
    for ln in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(ln)
        if r.get("role") == "body":
            out.append((r["vol"], int(r["page"])))
    return sorted(out)


def bad_text(txt):
    if not txt:
        return True
    # 重复退化：最常见字占全文 > 25%
    from collections import Counter
    c = Counter(ch for ch in txt if '\u4e00' <= ch <= '\u9fff')
    if not c:
        return True
    return c.most_common(1)[0][1] / max(1, len(txt)) > 0.25


def one_attempt(session, key, base, img):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    r = session.post(base + "/v1/tools/ocr",
                     headers={"Authorization": "Bearer " + key},
                     files={"file": ("page.jpg", buf.tobytes(), "image/jpeg")},
                     data={"purpose": "rich_layout_recognition"}, timeout=300)
    r.raise_for_status()
    return r.json(), len(buf.tobytes())


def process(item, dpi=300, retries=0):
    vol, pg = item
    path = os.path.join(OUTDIR, vol, f"{vol}_{pg:04d}.json")
    if os.path.exists(path):
        return {"vol": vol, "page": pg, "status": "skip"}
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[vol]))
    try:
        page = doc[pg - 1]
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    finally:
        doc.close()
    key, base = load_key()
    best = None
    errs = []
    with requests.Session() as session:
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                d, nbytes = one_attempt(session, key, base, img)
                pg_res = (d.get("pages") or [{}])[0]
                txt = pg_res.get("text") or ""
                rec = {"vol": vol, "page": pg, "attempt": attempt,
                       "http": round(time.time() - t0, 2), "bytes": nbytes,
                       "finish_reason": pg_res.get("finish_reason"),
                       "text_len": len(txt), "bad_text": bad_text(txt),
                       "usage": d.get("usage"), "response": d}
                if best is None or (not rec["bad_text"] and not best["bad_text"]) and rec["text_len"] > best["text_len"]:
                    best = rec
                if not rec["bad_text"] and rec.get("finish_reason") == "stop":
                    break
            except Exception as e:
                errs.append(str(e)[:120])
                if attempt >= retries:
                    return {"vol": vol, "page": pg, "status": "error", "errors": errs}
                time.sleep(1.5 * (attempt + 1))
    if best is None:
        return {"vol": vol, "page": pg, "status": "error", "errors": errs}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        json.dump({"vol": vol, "page": pg, "saved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "attempts": best["attempt"] + 1, "http": best["http"], "bytes": best["bytes"],
                   "finish_reason": best["finish_reason"], "text_len": best["text_len"],
                   "bad_text": best["bad_text"], "usage": best["usage"], "response": best["response"]},
                  fo, ensure_ascii=False)
    os.replace(tmp, path)
    return {"vol": vol, "page": pg, "status": "ok", "bad": best["bad_text"],
             "finish": best["finish_reason"], "text_len": best["text_len"],
             "http": best["http"], "attempts": best["attempt"] + 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--vols", default="")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--retries", type=int, default=0)
    args = ap.parse_args()
    pages = body_pages()
    if args.vols:
        want = set(args.vols.split(","))
        pages = [p for p in pages if p[0] in want]
    if args.limit:
        pages = pages[:args.limit]
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = time.time(); done = 0; ok = 0; bad = 0; err = 0; skip = 0
    print(f"[deepseek-ocr] pages={len(pages)} workers={args.workers} dpi={args.dpi}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, p, args.dpi, args.retries): p for p in pages}
        for f in as_completed(futs):
            r = f.result(); done += 1
            if r["status"] == "skip":
                skip += 1
            elif r["status"] == "error":
                err += 1
            else:
                ok += 1; bad += 1 if r.get("bad") else 0
            if done % 25 == 0 or done == len(pages):
                rate = done / max(1e-6, time.time() - t0)
                print(json.dumps({"done": done, "ok": ok, "bad": bad, "err": err, "skip": skip,
                                  "rate_pages_min": round(rate * 60, 1),
                                  "eta_min": round((len(pages) - done) / max(1e-6, rate) / 60, 1)},
                                 ensure_ascii=False), flush=True)
                with open(METRICS, "w", encoding="utf-8") as fo:
                    json.dump({"python": sys.version.split()[0], "workers": args.workers,
                               "total": len(pages), "done": done, "ok": ok, "bad": bad,
                               "err": err, "skip": skip, "elapsed_min": round((time.time()-t0)/60, 2)},
                              fo, ensure_ascii=False, indent=1)
    print(json.dumps({"done": done, "ok": ok, "bad": bad, "err": err, "skip": skip,
                      "elapsed_min": round((time.time()-t0)/60, 2)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
