#!/usr/bin/env python3
"""C 流 · 字形候选策展（crop 渲染 → 候选标签 → 目检图 → 字表 manifest）。

本脚本只做「证据准备」：从 150dpi 页面坐标出发，用 PDF 原生分辨率（300dpi）重渲染
字头 crop，汇总各条已标注来源的候选字标签（dp_alignment / dp_alignment2 /
t2_review_ids / OCR），并生成：
  * work/font/crops300/{key}.png        300dpi 灰度 crop（已扩边）
  * work/font/sheets/read_*.png         纯 crop 目检图（供人工逐字读数）
  * work/font/sheets/card_*.png         候选标签并排对照图（crop + 候选字渲染）
  * work/font/demo/manifest.json        由人工裁定文件 verdicts.json 生成的字表

重要口径（docs/TAKEOVER.md §1.1）：work/t2/dp_alignment*.json 的配对基于错误条目序，
除 owner 明确验证过的条目外**不得直接采信**；本脚本把一切来源都只当候选，
最终 label 必须来自人工目检（verdicts.json，字段 verified_by="font:目检"）。

用法：
  .venv/bin/python scripts/font_curate.py crops  --boxes gold
  .venv/bin/python scripts/font_curate.py read   --boxes gold --per-sheet 15
  .venv/bin/python scripts/font_curate.py cards  --boxes gold
  .venv/bin/python scripts/font_curate.py manifest --verdicts work/font/demo/verdicts.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"
sys.path.insert(0, str(WORK / "_pylibs"))  # fontTools / potracer（不改 .venv）

PDF_DIR = ROOT / "康熙字典"
PDF_MAP = json.load(open(ROOT / "work" / "t2" / "pdf_map.json"))
DPI150_TO_PT = 72.0 / 150.0          # 150dpi 页面像素 -> PDF pt
GOLD = ROOT / "data" / "gold-certified" / "gold50.json"

# 目检对照用的系统字体（只用于「渲染候选字做视觉比对」，不进入发布字体）
FONT_SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
FONT_KAI = str(Path.home() / "Library/Fonts" / "GuanGeKai-Regular.ttf")
FALLBACK_FONTS = [FONT_SONGTI, FONT_KAI]

# crop 扩边（150dpi 像素）：只留 6px（=300dpi 12px）——刻本注文离框 15px+，
# 大 pad 会把版框线和邻字注文带进来；小 pad + 贴边成分剔除更干净（Lead 建议）
PAD150 = 6
SCALE150 = 72.0 / 150.0


# --------------------------------------------------------------------------- #
# 数据源
# --------------------------------------------------------------------------- #
def load_json_any(path: Path):
    if not path.exists():
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in open(path) if line.strip()]
    obj = json.load(open(path))
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        return []
    return obj


def gold_boxes() -> list[dict]:
    """60 框金标 -> 统一 box 记录（150dpi 坐标）。"""
    obj = json.load(open(GOLD))
    out = []
    for b in obj["boxes"]:
        out.append({
            "key": f"gold{b['id']:02d}_{b['page']}",
            "id": b["id"],
            "page": b["page"],
            "box": list(b["box"]),
            "layer": b.get("layer", ""),
            "note": b.get("note", ""),
        })
    return out


def load_box_list(kind: str) -> list[dict]:
    if kind == "gold":
        return gold_boxes()
    # 额外候选框：work/font/demo/extra_boxes.json（人工从 t2 未入金标的标注框里挑）
    p = WORK / "demo" / "extra_boxes.json"
    if not p.exists():
        raise SystemExit(f"missing {p}")
    return json.load(open(p))


CANDIDATE_SOURCES = [
    ("dp_alignment", ROOT / "work/t2/dp_alignment.json"),
    ("dp_alignment2", ROOT / "work/t2/dp_alignment2.json"),
    ("t2_review_ids", ROOT / "data/gold-certified/t2_review_ids.json"),
    ("dp_review_ids", ROOT / "work/t2/dp_review_ids.json"),
    ("ocr300_v6", ROOT / "work/t2/ocr300_v6.jsonl"),
    ("ocr300_v5", ROOT / "work/t2/ocr300_v5.jsonl"),
    ("ocr150_v6", ROOT / "work/t2/ocr_v6.jsonl"),
]


def iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def candidates_for(box: dict) -> dict:
    """返回该框在各来源里的候选（同页 + box IoU>0.6 视为同框）。"""
    out = {}
    for name, path in CANDIDATE_SOURCES:
        rows = load_json_any(path)
        best, bi = None, 0.0
        for r in rows:
            if r.get("page") != box["page"]:
                continue
            rb = r.get("box")
            if not rb or len(rb) != 4:
                continue
            v = iou(box["box"], rb)
            if v > bi:
                best, bi = r, v
        if best is not None and bi > 0.6:
            if name.startswith("ocr"):
                out[name] = {"text": best.get("text", ""), "iou": round(bi, 3)}
            else:
                out[name] = {"char": best.get("char", ""), "pos": best.get("entry_pos"),
                             "iou": round(bi, 3),
                             "anchor": best.get("anchor")}
    return out


# --------------------------------------------------------------------------- #
# 300dpi crop
# --------------------------------------------------------------------------- #
def render_crops(boxes: list[dict], force: bool = False) -> list[dict]:
    import fitz
    out_dir = WORK / "crops300"
    out_dir.mkdir(parents=True, exist_ok=True)
    by_page: dict[str, list[dict]] = {}
    for b in boxes:
        by_page.setdefault(b["page"], []).append(b)
    metas = []
    for pagekey, blist in sorted(by_page.items()):
        pdf, pnum = pagekey.split("_")
        doc = fitz.open(PDF_DIR / PDF_MAP[pdf])
        page = doc[int(pnum) - 1]
        for b in blist:
            fn = out_dir / f"{b['key']}.png"
            x0, y0, x1, y1 = b["box"]
            clip = fitz.Rect((x0 - PAD150) * DPI150_TO_PT, (y0 - PAD150) * DPI150_TO_PT,
                             (x1 + PAD150) * DPI150_TO_PT, (y1 + PAD150) * DPI150_TO_PT)
            crop_box = [int(round(v)) for v in (x0, y0, x1, y1)]
            meta = dict(b, crop=str(fn.relative_to(ROOT)), crop_box=crop_box,
                        scale=2.0, pad150=PAD150)
            if fn.exists() and not force:
                metas.append(meta)
                continue
            pix = page.get_pixmap(dpi=300, clip=clip, colorspace=fitz.csGRAY)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            Image.fromarray(arr).save(fn)
            meta.update(crop_w=pix.width, crop_h=pix.height)
            metas.append(meta)
        doc.close()
    # 合并已有 crops.json（不同 box 列表分批渲染时保留各自的 crop 记录）
    merged_path = WORK / "crops.json"
    by_key = {}
    if merged_path.exists() and not force:
        for old in json.load(open(merged_path)):
            by_key[old["key"]] = old
    for m in metas:
        by_key[m["key"]] = m
    metas = list(by_key.values())
    merged_path.write_text(json.dumps(metas, ensure_ascii=False, indent=1))
    print(f"crops: {len(metas)} -> {out_dir}")
    return metas


def load_crops() -> list[dict]:
    p = WORK / "crops.json"
    if not p.exists():
        raise SystemExit("run `crops` first")
    return json.load(open(p))


# --------------------------------------------------------------------------- #
# 目检图
# --------------------------------------------------------------------------- #
def _font(size: int):
    for p in FALLBACK_FONTS:
        try:
            if p.endswith(".ttc"):
                return ImageFont.truetype(p, size, index=7)  # Songti TC Regular
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def read_sheets(crops: list[dict], per_sheet: int = 15, cols: int = 5,
                cell: int = 300, out_tag: str = "read") -> list[Path]:
    out_dir = WORK / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    lab = _font(18)
    paths = []
    for si in range(0, len(crops), per_sheet):
        chunk = crops[si:si + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 26)), "white")
        d = ImageDraw.Draw(sheet)
        for i, c in enumerate(chunk):
            im = Image.open(ROOT / c["crop"]).convert("L")
            k = (cell - 24) / max(im.width, im.height)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))),
                           Image.LANCZOS).convert("RGB")
            x, y = (i % cols) * cell, (i // cols) * (cell + 26)
            sheet.paste(im, (x + (cell - im.width) // 2, y + 6))
            d.text((x + 6, y + cell - 16), f"#{c['id']:02d} {c['page']}", font=lab, fill="black")
        p = out_dir / f"{out_tag}_{si // per_sheet:02d}.png"
        sheet.save(p)
        paths.append(p)
    print(f"read sheets: {len(paths)} rows/sheet cols={cols} cell={cell}")
    for p in paths:
        print(" ", p)
    return paths


# --------------------------------------------------------------------------- #
# 候选标签对照图（crop + 候选字渲染）
# --------------------------------------------------------------------------- #
def _render_char_mask(ch: str, size: int = 160) -> np.ndarray | None:
    for p in FALLBACK_FONTS:
        try:
            if p.endswith(".ttc"):
                f = ImageFont.truetype(p, size, index=7)
            else:
                f = ImageFont.truetype(p, size)
            im = Image.new("L", (size, size), 255)
            ImageDraw.Draw(im).text((size // 2, size // 2), ch, font=f, fill=0, anchor="mm")
            a = np.array(im) < 128
            if a.sum() > 30:
                return a
        except Exception:
            continue
    return None


def _norm_mask(ink: np.ndarray, size: int = 128, pad: int = 8) -> np.ndarray:
    ys, xs = np.where(ink)
    if len(xs) == 0:
        return np.zeros((size, size), bool)
    sub = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape
    s = (size - 2 * pad) / max(h, w)
    nh, nw = max(1, int(round(h * s))), max(1, int(round(w * s)))
    import cv2
    sub = cv2.resize(sub.astype(np.uint8), (nw, nh), interpolation=cv2.INTER_AREA) > 0.5
    canvas = np.zeros((size, size), bool)
    cy, cx = (size - nh) // 2, (size - nw) // 2
    canvas[cy:cy + nh, cx:cx + nw] = sub
    return canvas


def crop_ink(crop_path: Path) -> np.ndarray:
    import cv2
    g = np.array(Image.open(crop_path).convert("L"))
    gb = cv2.medianBlur(g, 3)
    thr, _ = cv2.threshold(gb, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = min(max(thr, 100), 210)
    ink = gb < thr
    # 去掉贴边的邻字碎片：只保留与中心区域相连的成分
    n, labels, stats, cent = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    h, w = ink.shape
    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        cx, cy = cent[i]
        if area < 30:
            continue
        if x <= 1 or y <= 1 or x + ww >= w - 1 or y + hh >= h - 1:
            continue
        if 0.12 * w < cx < 0.88 * w and 0.12 * h < cy < 0.88 * h:
            keep[i] = True
    # 若中心区域无成分（贴边字），退回最大成分
    if not keep.any():
        keep[1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))] = True
    return keep[labels]


def _dilate(a: np.ndarray, r: int) -> np.ndarray:
    import cv2
    if r <= 0:
        return a
    k = np.ones((2 * r + 1, 2 * r + 1), np.uint8)
    return cv2.dilate(a.astype(np.uint8), k) > 0


def char_similarity(ink: np.ndarray, ch: str, tol: int = 6) -> float:
    """容差 IoU：两侧各膨胀 tol 像素后再取交集（对笔画刻工差异更宽容）。"""
    cm = _render_char_mask(ch)
    if cm is None:
        return -1.0
    a = _norm_mask(ink)
    b = _norm_mask(cm)
    ad, bd = _dilate(a, tol), _dilate(b, tol)
    inter = (ad & bd).sum()
    union = (ad | bd).sum()
    return float(inter) / max(1, union)


def card_sheets(crops: list[dict], per_sheet: int = 12, cols: int = 4,
                cell_w: int = 460, cell_h: int = 330) -> list[Path]:
    out_dir = WORK / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    lab = _font(17)
    lab_small = _font(14)
    paths = []
    for si in range(0, len(crops), per_sheet):
        chunk = crops[si:si + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
        d = ImageDraw.Draw(sheet)
        for i, c in enumerate(chunk):
            x0 = (i % cols) * cell_w
            y0 = (i // cols) * cell_h
            # crop
            im = Image.open(ROOT / c["crop"]).convert("L")
            k = 210 / max(im.width, im.height)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))),
                           Image.LANCZOS).convert("RGB")
            sheet.paste(im, (x0 + 6, y0 + 20))
            d.rectangle([x0 + 4, y0 + 18, x0 + 4 + im.width, y0 + 18 + im.height],
                        outline="gray")
            d.text((x0 + 6, y0 + 2), f"#{c['id']:02d} {c['page']}", font=lab, fill="black")
            # candidates
            cands = c.get("candidates", {})
            grouped: dict[str, list[str]] = {}
            ocr_votes: dict[str, list[str]] = {}
            for src, v in cands.items():
                if "char" in v:
                    if v["char"]:
                        grouped.setdefault(v["char"], []).append(src)
                elif "text" in v and v["text"]:
                    ocr_votes.setdefault(v["text"], []).append(src)
            ranked = []
            ink = crop_ink(ROOT / c["crop"])
            for ch in sorted(set(grouped) | set(ocr_votes)):
                s = char_similarity(ink, ch)
                ranked.append((s, ch, grouped.get(ch, []), ocr_votes.get(ch, [])))
            ranked.sort(reverse=True)
            yy = y0 + 26
            xx = x0 + 236
            for s, ch, srcs, ocrs in ranked[:6]:
                try:
                    gf = _font(34)
                    gm = Image.new("RGB", (46, 46), "white")
                    ImageDraw.Draw(gm).text((23, 23), ch, font=gf, fill="black", anchor="mm")
                    sheet.paste(gm, (xx, yy))
                except Exception:
                    pass
                tag = ch
                if s >= 0:
                    tag += f"  sim={s:.2f}"
                d.text((xx + 40, yy + 2), tag, font=lab, fill="black")
                srcs_txt = ",".join(srcs + [f"ocr:{o}" for o in ocrs])
                d.text((xx + 40, yy + 20), srcs_txt[:40], font=lab_small, fill="gray")
                yy += 46
            if not ranked:
                d.text((xx, yy), "(无候选)", font=lab, fill="red")
        p = out_dir / f"card_{si // per_sheet:02d}.png"
        sheet.save(p)
        paths.append(p)
    print(f"card sheets: {len(paths)}")
    for p in paths:
        print(" ", p)
    return paths


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def emit_manifest_jsonl(out_path: str = "") -> Path:
    """把 demo manifest.json + crops.json 导出为 font_build.py --manifest 用的 jsonl。"""
    m = json.load(open(WORK / "demo" / "manifest.json"))
    crops = {c["key"]: c for c in load_crops()}
    out = Path(out_path) if out_path else WORK / "demo" / "manifest.jsonl"
    n = 0
    with open(out, "w") as fh:
        for ch, rec in sorted(m["chars"].items()):
            c = crops.get(rec["key"])
            if not c:
                continue
            fh.write(json.dumps({
                "char": ch, "crop_png": c["crop"], "key": rec["key"],
                "page": rec["page"], "box": rec["box"],
                "label_source": rec.get("label_source", ""),
                "verified_by": rec.get("verified_by", ""),
                "crop_w": c.get("crop_w"), "crop_h": c.get("crop_h"),
                "pad150": c.get("pad150", 18), "scale": c.get("scale", 2.0),
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"manifest.jsonl: {n} chars -> {out}")
    return out


def build_manifest(verdicts_path: str) -> dict:
    """verdicts.json: {key: {"char": "...", "status": "accept"|"reject", "note": "..."}}
    只有 status=accept 且 char 非空的记录进入字体。"""
    verdicts = json.load(open(verdicts_path))
    crops = {c["key"]: c for c in load_crops()}
    chars: dict[str, dict] = {}
    dropped = []
    for key, v in verdicts.items():
        ch = v.get("char", "")
        status = v.get("status", "")
        if status != "accept" or not ch:
            dropped.append({"key": key, "char": ch, "status": status,
                            "note": v.get("note", "")})
            continue
        if ch in chars:
            # 同字多框：保留第一个，其余记录为重复
            dropped.append({"key": key, "char": ch, "status": "dup",
                            "note": f"重复字，已用 {chars[ch]['key']}"})
            continue
        c = crops.get(key)
        if c is None:
            raise SystemExit(f"verdicts 里的 key {key} 没有对应 crop；先跑 crops")
        chars[ch] = {
            "char": ch, "codepoint": f"U+{ord(ch):04X}",
            "key": key, "page": c["page"], "box": c["box"],
            "crop": c["crop"], "layer": c.get("layer", ""),
            "label_source": v.get("source", "candidate+目检"),
            "verified_by": "font:目检",
            "note": v.get("note", ""),
        }
    manifest = {
        "family": "KangXi Kai",
        "style": "Regular",
        "version": "0.1.0",
        "upm": 1000,
        "license": "OFL-1.1",
        "provenance": "real",
        "n_chars": len(chars),
        "chars": chars,
        "dropped": dropped,
        "note": ("demo v0：字头真迹矢量化。全部 label 经 font:目检（crop 与候选标签"
                 "并排比对），未经目检的候选一律未入表。"),
    }
    out = WORK / "demo" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"manifest: {len(chars)} chars, {len(dropped)} dropped -> {out}")
    return manifest


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["crops", "read", "cards", "manifest", "candidates",
                                    "verify", "priors", "emit-jsonl"])
    ap.add_argument("--boxes", default="gold", help="gold | extra")
    ap.add_argument("--verdicts", default=str(WORK / "demo" / "verdicts.json"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--per-sheet", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--manual", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.cmd == "crops":
        boxes = load_box_list(args.boxes)
        render_crops(boxes, force=args.force)
    elif args.cmd == "candidates":
        boxes = load_box_list(args.boxes)
        crops = load_crops()
        for c in crops:
            c["candidates"] = candidates_for(c)
        (WORK / "crops.json").write_text(json.dumps(crops, ensure_ascii=False, indent=1))
        print("candidates attached ->", WORK / "crops.json")
    elif args.cmd == "read":
        crops = load_crops()
        read_sheets(crops, per_sheet=args.per_sheet or 15)
    elif args.cmd == "cards":
        crops = load_crops()
        if not any(c.get("candidates") for c in crops):
            for c in crops:
                c["candidates"] = candidates_for(c)
            (WORK / "crops.json").write_text(json.dumps(crops, ensure_ascii=False, indent=1))
        card_sheets(crops, per_sheet=args.per_sheet or 12)
    elif args.cmd == "priors":
        prev_candidates()
    elif args.cmd == "manifest":
        build_manifest(args.verdicts)
    elif args.cmd == "emit-jsonl":
        emit_manifest_jsonl(args.out)
    elif args.cmd == "verify":
        crops = load_crops()
        if not any(c.get("candidates") for c in crops):
            for c in crops:
                c["candidates"] = candidates_for(c)
            (WORK / "crops.json").write_text(json.dumps(crops, ensure_ascii=False, indent=1))
        ids = [int(x) for x in args.ids.split(",")] if args.ids else None
        verify_sheets(ids, args.manual)




# --------------------------------------------------------------------------- #
# 目检放大图（单字 crop 大幅 + 候选渲染；供逐字裁定）
# --------------------------------------------------------------------------- #
def verify_sheets(ids: list[int] | None = None, manual_path: str | None = None,
                  per_sheet: int = 4, crop_px: int = 480) -> list[Path]:
    crops = load_crops()
    if ids:
        crops = [c for c in crops if c["id"] in set(ids)]
    manual = {}
    mp = Path(manual_path) if manual_path else WORK / "tmp" / "manual_candidates.json"
    if mp.exists():
        manual = {int(k): v for k, v in json.load(open(mp)).items()}
    out_dir = WORK / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    lab = _font(20)
    paths = []
    cols = 2
    for si in range(0, len(crops), per_sheet):
        chunk = crops[si:si + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        cell_w, cell_h = 1260, 660
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
        d = ImageDraw.Draw(sheet)
        for i, c in enumerate(chunk):
            x0 = (i % cols) * cell_w
            y0 = (i // cols) * cell_h
            im = Image.open(ROOT / c["crop"]).convert("L")
            k = crop_px / max(im.width, im.height)
            im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS).convert("RGB")
            sheet.paste(im, (x0 + 10, y0 + 30))
            d.text((x0 + 10, y0 + 4), f"#{c['id']:02d} {c['page']} box={c['box']}", font=lab, fill="black")
            cands = c.get("candidates", {})
            distinct = []
            for src, v in cands.items():
                ch = v.get("char") or v.get("text")
                if ch and ch not in distinct:
                    distinct.append(ch)
            for _s, ch in c.get("prior_top", []):
                if ch not in distinct:
                    distinct.append(ch)
            for ch in manual.get(c["id"], []):
                if ch not in distinct:
                    distinct.insert(0, ch)
            ink = crop_ink(ROOT / c["crop"])
            ranked = sorted(((char_similarity(ink, ch), ch) for ch in distinct), reverse=True)
            xx = x0 + crop_px + 30
            d.text((xx, y0 + 34), "候选（sim 高→低）:", font=lab, fill="black")
            yy = y0 + 60
            for s, ch in ranked[:10]:
                cp = f"U+{ord(ch):04X}"
                tag = f"{ch} {cp} ".replace(" ", "")
                if s >= 0:
                    tag += f" sim={s:.2f}"
                d.text((xx, yy), tag, font=lab, fill="black")
                srcs = [k for k, v in cands.items() if (v.get("char") or v.get("text")) == ch]
                d.text((xx + 2, yy + 22), ",".join(srcs)[:40], font=_font(13), fill="gray")
                cm = _render_char_mask(ch, 160)
                if cm is not None:
                    gm = Image.fromarray((~cm * 255).astype("uint8")).convert("RGB")
                    sheet.paste(gm.resize((56, 56), Image.LANCZOS), (xx + 390, yy - 4))
                yy += 56
        p = out_dir / f"verify_{si // per_sheet:02d}.png"
        sheet.save(p)
        paths.append(p)
    print(f"verify sheets: {len(paths)}")
    for p in paths:
        print(" ", p)
    return paths




# --------------------------------------------------------------------------- #
# 部首/画数先验候选（owner 核验的书眉 + Unihan kRSUnicode）
# --------------------------------------------------------------------------- #
# 金标 6 页的书眉（work/t2/margin_labels_full.json，owner 核验）：部名 -> Unihan 部首号
PAGE_PRIOR = {
    "01_0006": {"rad": [1], "strokes": None, "note": "子集上 一部 部首页"},
    "01_0027": {"rad": [5], "strokes": [0, 1], "note": "子集上 乙部 一畫/二畫"},
    "01_0110": {"rad": [9], "strokes": [12], "note": "子集中 人部 十二畫"},
    "02_0155": {"rad": [32], "strokes": [10], "note": "丑集中 土部 十畫(低置信)"},
    "08_0020": {"rad": [118], "strokes": [6], "note": "未集上 竹部 六畫(低置信)"},
    # 13_0163 = 戌集備考（含酉集/戌集交界）；部首未知，用 備考 页可能覆盖的部作池
    "13_0163": {"rad": [149, 159, 177, 178, 179, 180, 181], "strokes": None,
                "note": "戌集備考（酉集/戌集交界），部名不可靠，多部候选池"},
}
RAD_NAME = {1: "一", 5: "乙", 9: "人", 32: "土", 118: "竹", 149: "言", 159: "車",
            177: "革", 178: "韋", 179: "韭", 180: "音", 181: "頁"}


def _load_unihan_rad():
    """radical -> [(char, 部外画数)]（BMP only，kRSUnicode）。"""
    import re
    cache = WORK / "tmp" / "unihan_rad.json"
    if cache.exists():
        raw = json.load(open(cache))
        return {int(k): v for k, v in raw.items()}
    rads: dict[int, list] = {}
    for line in open(ROOT / "data" / "unihan" / "Unihan_IRGSources.txt"):
        if "kRSUnicode" not in line or line.startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        cp, field, val = parts[0], parts[1], parts[2]
        if field != "kRSUnicode" or not cp.startswith("U+"):
            continue
        ch = chr(int(cp[2:], 16))
        if ord(ch) > 0xFFFF:
            continue
        v = val.split()[0].replace("'", "")
        m = re.match(r"(\d+)\.(-?\d+)", v)
        if not m:
            continue
        rads.setdefault(int(m.group(1)), []).append([ch, int(m.group(2))])
    for r in rads:
        rads[r].sort(key=lambda x: (x[1], ord(x[0])))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rads, ensure_ascii=False))
    return rads


def prev_candidates(pool_size: int = 12) -> None:
    """为每个 crop 生成「部首+画数先验」候选并按形似度排序，写入 crops.json。"""
    crops = load_crops()
    radmap = _load_unihan_rad()
    for c in crops:
        prior = PAGE_PRIOR.get(c["page"])
        if not prior:
            continue
        pool = []
        for r in prior["rad"]:
            for ch_st in radmap.get(r, []):
                ch, st = ch_st
                if prior["strokes"] is not None and st not in prior["strokes"]:
                    continue
                pool.append(ch)
        ink = crop_ink(ROOT / c["crop"])
        scored = []
        for ch in pool:
            s = char_similarity(ink, ch)
            if s >= 0:
                scored.append((round(s, 3), ch))
        scored.sort(reverse=True)
        c["prior_pool"] = len(pool)
        c["prior_top"] = scored[:pool_size]
        print(f"#{c['id']:02d} {c['page']} pool={len(pool)} top={[(ch,s) for s,ch in scored[:5]]}")
    (WORK / "crops.json").write_text(json.dumps(crops, ensure_ascii=False, indent=1))
    print("priors ->", WORK / "crops.json")


if __name__ == "__main__":
    sys.exit(main())
