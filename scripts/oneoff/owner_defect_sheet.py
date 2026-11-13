#!/usr/bin/env python3
"""缺陷历史台账 → 100 字/页 核验表（owner-provenance 样式，最新字体渲染）。

输入：work/lead/defect-ledger-v258.jsonl（char/page/half/box/status/categories/mark_rounds）
输出：work/review/defect-history-v258/page-NNN.png（10×10）+ defect-ledger.tsv + summary.json
"""
import argparse, json, os, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))

CELL_W, CELL_H = 190, 330
# 参考字体：霞鹜文楷（OFL，唯一来源 scripts/reffont.py）；标签也用同一 OFL 字体。
from reffont import path as _ref_font_path, index as _ref_font_index  # noqa: E402
REF_FONT = _ref_font_path()
REF_INDEX = _ref_font_index()
COLS, ROWS = 10, 10
PER_PAGE = COLS * ROWS


def render_crop(args):
    idx, page, box, outdir = args
    import font_norm as FN
    from PIL import Image
    path = os.path.join(outdir, f"{idx:05d}.png")
    if os.path.exists(path):
        return idx, path
    try:
        if page and box:
            gray = FN.render_pdf_crop(page, box, pad150=6, dpi=150)
            Image.fromarray(gray).save(path)
        else:
            Image.new("L", (180, 180), 255).save(path)
    except Exception:
        Image.new("L", (180, 180), 255).save(path)
    return idx, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--font", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    crops_dir = os.path.join(args.outdir, "crops")
    os.makedirs(crops_dir, exist_ok=True)
    from PIL import Image, ImageDraw, ImageFont
    rows = [json.loads(l) for l in open(os.path.join(ROOT, args.ledger), encoding="utf-8")]
    man = set(json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"])
    crops = {}
    jobs = [(i, r.get("page"), r.get("box"), crops_dir) for i, r in enumerate(rows)]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for idx, path in ex.map(render_crop, jobs, chunksize=8):
            crops[idx] = path

    font_glyph = ImageFont.truetype(os.path.join(ROOT, args.font), 76)
    font_ref = ImageFont.truetype(REF_FONT, 72, index=REF_INDEX)
    f_label = ImageFont.truetype(REF_FONT, 13, index=REF_INDEX)
    f_small = ImageFont.truetype(REF_FONT, 11, index=REF_INDEX)
    n_pages = (len(rows) + PER_PAGE - 1) // PER_PAGE
    summary = {"chars": len(rows), "pages": n_pages,
               "status": {}, "categories": {},
               "page_files": []}
    tsv = open(os.path.join(args.outdir, "defect-ledger.tsv"), "w", encoding="utf-8")
    tsv.write("no\tchar\tpage\thalf\tbox\tstatus\tcategories\tmarks\n")
    for pi in range(n_pages):
        page = Image.new("RGB", (CELL_W * COLS, CELL_H * ROWS), (255, 255, 255))
        d = ImageDraw.Draw(page)
        chunk = rows[pi * PER_PAGE:(pi + 1) * PER_PAGE]
        for k, r in enumerate(chunk):
            idx = pi * PER_PAGE + k
            x0 = (k % COLS) * CELL_W
            y0 = (k // COLS) * CELL_H
            # 原书裁片
            try:
                src = Image.open(crops[idx]).convert("L")
                src.thumbnail((182, 162))
                page.paste(src, (x0 + 4, y0 + 2))
            except Exception:
                pass
            # 最新字体字形（缺失/隔离用 OFL 参考字体灰字占位）
            ch = r["char"]
            if ch in man:
                g = Image.new("L", (118, 100), 255)
                ImageDraw.Draw(g).text((59, 92), ch, font=font_glyph, fill=0, anchor="ms")
                page.paste(g, (x0 + 2, y0 + 166))
                status = "在字体"
            else:
                g = Image.new("L", (118, 100), 250)
                ImageDraw.Draw(g).text((59, 88), ch, font=font_ref, fill=155, anchor="ms")
                page.paste(g, (x0 + 2, y0 + 166))
                status = "隔离" if r.get("status") == "quarantined" else "缺口"
            summary["status"][status] = summary["status"].get(status, 0) + 1
            cats = r.get("categories", [])
            for c in cats:
                summary["categories"][c] = summary["categories"].get(c, 0) + 1
            cat_color = {"owner": (200, 0, 0), "v2419_loss": (200, 90, 0),
                         "missing_scan": (0, 90, 200), "offset_scan": (120, 0, 160),
                         "repair_overlay": (0, 130, 0), "residual": (150, 100, 0),
                         "audit_named": (0, 120, 120), "anchors": (90, 90, 90)}
            color = cat_color.get(cats[0] if cats else "", (0, 0, 0))
            d.text((x0 + 4, y0 + 268), f"#{idx+1} {ch}", font=f_label, fill=color)
            pageinfo = f'{r.get("page") or "-"} {r.get("half") or ""} {r.get("box") or ""}'
            d.text((x0 + 4, y0 + 284), pageinfo[:30], font=f_small, fill=(60, 60, 60))
            d.text((x0 + 4, y0 + 298), f'状态:{status} 标记:{len(r.get("mark_rounds", []))}次', font=f_small, fill=(60, 60, 60))
            d.text((x0 + 4, y0 + 312), ("/".join(cats))[:34], font=f_small, fill=color)
            tsv.write(f'{idx+1}\t{ch}\t{r.get("page") or ""}\t{r.get("half") or ""}\t{r.get("box") or ""}\t{status}\t{",".join(cats)}\t{",".join(r.get("mark_rounds", []))}\n')
        out = os.path.join(args.outdir, f"page-{pi+1:03d}.png")
        page.save(out)
        summary["page_files"].append(os.path.relpath(out, ROOT))
        print("page", pi + 1, "/", n_pages, flush=True)
    tsv.close()
    json.dump(summary, open(os.path.join(args.outdir, "summary.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"pages": n_pages, "chars": len(rows), "summary": summary["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
