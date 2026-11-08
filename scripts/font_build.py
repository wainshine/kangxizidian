#!/usr/bin/env python3
"""C 流 · 组字体：glyphs.jsonl -> TTF（glyf + cmap + name 等）。

改造自 guangeti scripts/fontbuild.py（来源 commit 见 docs/VENDORED.md）：
  - 家族名 KangXi Kai / 版本 0.1.0 / EM 1000
  - 只映射 manifest 里真实存在的字（不做假覆盖、不 fill）
  - font.recalcTimestamp = False + 固定 SOURCE_DATE_EPOCH => 两次构建字节一致
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"
sys.path.insert(0, str(WORK / "_pylibs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 本仓库 scripts/（不跨目录 import）

EM = 1000
FAMILY = "KangXi Kai"
STYLE = "Regular"
VERSION = "0.1.0"
ASCENT, DESCENT = 880, -120
OFL_TEXT = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
            "This license is available with a FAQ at: https://openfontlicense.org")
COPYRIGHT = ("KangXi Kai demo v0 — glyphs extracted from the 1716 Kangxi Dictionary "
             "(内府刊本) scans. SIL OFL 1.1. No third-party font outlines used.")
DEFAULT_SOURCE_DATE_EPOCH = 1792713600  # 2026-10-23T00:00:00Z


# --------------------------------------------------------------------------- #
# 轮廓方向（TrueType：外轮廓顺时针，孔洞逆时针；以 y-up 有符号面积判负/正）
# 逻辑沿用 guangeti fontbuild.py（审计 P0：必须用「曲线上的点」而非控制多边形判嵌套）
# --------------------------------------------------------------------------- #
def _sample_curve(c: dict, n: int = 6) -> list[tuple[float, float]]:
    pts = [tuple(c["start"])]
    cur = (c["start"][0], c["start"][1])
    for s in c["segs"]:
        if s[0] == "L":
            cur = (s[1], s[2])
            pts.append(cur)
        else:
            p0, p1, p2, p3 = cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])
            for k in range(1, n + 1):
                t = k / n
                mt = 1.0 - t
                x = (mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0]
                     + 3 * mt * t * t * p2[0] + t ** 3 * p3[0])
                y = (mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1]
                     + 3 * mt * t * t * p2[1] + t ** 3 * p3[1])
                pts.append((x, y))
            cur = p3
    return pts


def _signed_area(pts) -> float:
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _inside(pt, pts) -> bool:
    x, y = pt
    inside = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if ((y0 > y) != (y1 > y)) and (x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-12) + x0):
            inside = not inside
    return inside


def orient_contours(contours: list[dict]) -> list[tuple[dict, bool]]:
    polys = [_sample_curve(c) for c in contours]
    reps = [(p, _signed_area(p)) for p in polys]
    out = []
    for i, c in enumerate(contours):
        pts = reps[i][0]
        step = max(1, len(pts) // 7)
        probes = pts[::step]
        depth = 0
        for j, (p2, _) in enumerate(reps):
            if i == j:
                continue
            votes = sum(1 for q in probes if _inside(q, p2))
            if votes * 2 > len(probes):
                depth += 1
        want_negative = (depth % 2 == 0)   # 外轮廓在 y-up 下面积为负（顺时针）
        area = reps[i][1]
        flip = (area > 0) if want_negative else (area < 0)
        out.append((c, flip))
    return out


def _contour_points(c: dict):
    for s in c["segs"]:
        if s[0] == "L":
            yield s[1], s[2]
        else:
            yield s[1], s[2]
            yield s[3], s[4]
            yield s[5], s[6]


# --------------------------------------------------------------------------- #
# 组字体
# --------------------------------------------------------------------------- #
def build_font(glyphs: dict[str, list], out_path: Path, copyright_text: str = COPYRIGHT,
               version: str = VERSION, source_date_epoch: int | None = None) -> dict:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen

    chars = sorted(glyphs)
    order = [".notdef"] + [f"uni{ord(ch):04X}" for ch in chars]
    fb = FontBuilder(EM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({ord(ch): f"uni{ord(ch):04X}" for ch in chars})

    # .notdef：空心方块
    pen = TTGlyphPen(None)
    outer = [(40, -120), (40, 880), (960, 880), (960, -120)]
    inner = [(100, -60), (900, -60), (900, 820), (100, 820)]
    for pts in (outer, inner):
        pen.moveTo(pts[0])
        for p in pts[1:]:
            pen.lineTo(p)
        pen.closePath()
    glyf = {".notdef": pen.glyph()}
    metrics = {".notdef": (EM, 40)}

    per_char = {}
    for ch in chars:
        gname = f"uni{ord(ch):04X}"
        contours = glyphs[ch]
        tpen = TTGlyphPen(None)
        qpen = Cu2QuPen(tpen, max_err=1.0)
        xmin = ymin = 10 ** 9
        xmax = ymax = -10 ** 9
        for c, flip in orient_contours(contours):
            rec = RecordingPen()
            rec.moveTo(tuple(c["start"]))
            for s in c["segs"]:
                if s[0] == "L":
                    rec.lineTo((s[1], s[2]))
                else:
                    rec.curveTo((s[1], s[2]), (s[3], s[4]), (s[5], s[6]))
            rec.closePath()
            if flip:
                rec.replay(ReverseContourPen(qpen))
            else:
                rec.replay(qpen)
            for x, y in _contour_points(c):
                xmin, xmax = min(xmin, x), max(xmax, x)
                ymin, ymax = min(ymin, y), max(ymax, y)
        glyf[gname] = tpen.glyph()
        lsb = int(xmin) if xmin < 10 ** 8 else 0
        metrics[gname] = (EM, lsb)
        per_char[ch] = {"n_contours": len(contours), "bbox": [int(xmin), int(ymin),
                                                              int(xmax), int(ymax)]}

    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupNameTable({
        "familyName": FAMILY,
        "styleName": STYLE,
        "uniqueFontIdentifier": f"{FAMILY} {STYLE} {version}",
        "fullName": f"{FAMILY} {STYLE}",
        "psName": f"{FAMILY.replace(' ', '')}-{STYLE}",
        "version": f"Version {version}",
        "copyright": copyright_text,
        "licenseDescription": OFL_TEXT,
        "licenseInfoURL": "https://openfontlicense.org",
    })
    fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=DESCENT, sTypoLineGap=0,
                usWinAscent=ASCENT, usWinDescent=-DESCENT, sxHeight=500, sCapHeight=700,
                usWeightClass=400, usWidthClass=5, fsType=0,
                achVendID="KXKF", fsSelection=64,
                ulUnicodeRange1=1 | (1 << 28), ulCodePageRange1=(1 << 18) | (1 << 20))
    fb.setupPost(keepGlyphNames=False)
    fb.setupMaxp()
    fb.font["head"].macStyle = 0
    try:
        parts = (version.split(".") + ["0", "0"])[:3]
        fb.font["head"].fontRevision = (int(parts[0]) + int(parts[1]) / 10.0
                                        + int(parts[2]) / 100.0)
    except Exception:
        pass
    fb.font["head"].flags = 0b00000011
    # 可复现：固定时间戳
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", source_date_epoch or
                               DEFAULT_SOURCE_DATE_EPOCH))
    stamp = epoch + 2082844800  # fontTools: seconds since 1904-01-01
    fb.font["head"].created = stamp
    fb.font["head"].modified = stamp
    fb.font.recalcTimestamp = False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out_path))
    return per_char


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_from_mapping(path: str, limit: int = 0, pages: set | None = None,
                      progress_every: int = 500) -> tuple[dict, dict, list]:
    """全量 mapping：每行 {page, half, assigned:[{char, cand:{box}}]}，box=150dpi 页坐标。

    直接 PDF 300dpi 渲染 + 共用 norm/vectorize 链路；同字重复只取第一次。
    """
    import time as _time
    from font_norm import vectorize_box
    cache_dir = WORK / "build" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    use_cache = "--no-cache" not in sys.argv
    glyphs: dict[str, list] = {}
    src: dict[str, dict] = {}
    skipped = []
    t0 = _time.time()
    n_seen = n_cached = n_new = 0
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        page, half = r.get("page"), r.get("half", "")
        if pages and page not in pages:
            continue
        for a in r.get("assigned", []):
            ch = (a or {}).get("char")
            cand = (a or {}).get("cand") or {}
            box = cand.get("box") or (a or {}).get("box")
            if not ch or not box:
                skipped.append({"page": page, "half": half, "char": ch,
                                "reason": "缺 char 或 box"})
                continue
            n_seen += 1
            if limit and len(glyphs) >= limit:
                break
            if ch in glyphs:
                skipped.append({"page": page, "half": half, "char": ch,
                                "reason": f"重复字（已用 {src[ch]['page']}）"})
                continue
            ck = f"{page}{half}_{ch}_{box[0]}_{box[1]}".replace("/", "_")
            cpath = cache_dir / f"{ck}.json"
            if use_cache and cpath.exists():
                rec = json.loads(cpath.read_text())
                if rec.get("ok"):
                    glyphs[ch] = rec["contours"]
                    src[ch] = {**rec["src"], "cached": True}
                    n_cached += 1
                    continue
            res = vectorize_box(page, box)
            if not res["ok"]:
                skipped.append({"page": page, "half": half, "char": ch,
                                "reason": res["reason"]})
                continue
            m = {"page": page, "half": half, "box": box, "key": f"{page}{half}",
                 "label_source": "mapping", "verified_by": "",
                 "n_contours": res["n_contours"], "n_segs": res["n_segs"],
                 "ink_px": res["ink_px"], "pad150": res.get("pad150"),
                 "clipped": res.get("clipped")}
            glyphs[ch] = res["contours"]
            src[ch] = m
            n_new += 1
            if use_cache:
                cpath.write_text(json.dumps({"ok": True, "char": ch,
                                             "contours": res["contours"], "src": m},
                                            ensure_ascii=False))
            if progress_every and n_new and n_new % progress_every == 0:
                print(f"  vectorized {n_new} new glyphs (seen {n_seen}, "
                      f"{1000*(_time.time()-t0)/n_seen:.1f} ms/char)", flush=True)
        if limit and len(glyphs) >= limit:
            break
    dt = _time.time() - t0
    return glyphs, src, [{"batches_seen": n_seen, "cached": n_cached, "new": n_new,
                          "skipped": skipped, "seconds": round(dt, 2),
                          "ms_per_char": round(1000 * dt / max(1, n_seen), 1)}]


def load_from_manifest_jsonl(path: str) -> tuple[dict, dict, list]:
    """{char, crop_png} 每行一个字的现成 crop。"""
    from font_norm import vectorize_crop
    glyphs, src, skipped = {}, {}, []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        ch = r.get("char")
        crop = r.get("crop_png") or r.get("crop")
        if not ch or not crop:
            skipped.append({"char": ch, "reason": "缺 char/crop_png"})
            continue
        if ch in glyphs:
            skipped.append({"char": ch, "reason": "重复字"})
            continue
        p = Path(crop)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            skipped.append({"char": ch, "reason": f"crop 不存在 {p}"})
            continue
        center = None
        if r.get("crop_w") and r.get("crop_h"):
            pad_px = int(round(r.get("pad150", 18) * r.get("scale", 2.0)))
            center = (pad_px, pad_px, int(r["crop_w"]) - pad_px, int(r["crop_h"]) - pad_px)
        res = vectorize_crop(p, center=center)
        if not res["ok"]:
            skipped.append({"char": ch, "reason": res["reason"]})
            continue
        glyphs[ch] = res["contours"]
        src[ch] = {"key": r.get("key", ""), "page": r.get("page", ""),
                   "box": r.get("box"), "crop": str(p.relative_to(ROOT))
                   if p.is_relative_to(ROOT) else str(p),
                   "label_source": r.get("label_source", ""),
                   "verified_by": r.get("verified_by", ""),
                   "n_contours": res["n_contours"], "n_segs": res["n_segs"],
                   "ink_px": res["ink_px"]}
    return glyphs, src, [{"skipped": skipped}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glyphs", default="", help="预归一化 glyphs.jsonl（demo 快路径）")
    ap.add_argument("--mapping", default="",
                    help="全量 mapping.jsonl: {page,half,assigned:[{char,cand:{box}}]}")
    ap.add_argument("--manifest", default="",
                    help="字表 jsonl: {char, crop_png[, page, box]}")
    ap.add_argument("--out", default=str(WORK / "demo" / f"KangXiKai-demo-v{VERSION}.ttf"))
    ap.add_argument("--stats", default="", help="默认 <out 去后缀>.build_stats.json")
    ap.add_argument("--source-date-epoch", type=int, default=None)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个字（调试/压测）")
    ap.add_argument("--pages", default="", help="只处理这些页，逗号分隔，如 01_0110,08_0020")
    ap.add_argument("--progress-every", type=int, default=500, help="每 N 字打印一次进度")
    args = ap.parse_args()
    if not (args.glyphs or args.mapping or args.manifest):
        raise SystemExit("one of --glyphs/--mapping/--manifest required")
    if not args.out:
        args.out = str((WORK / "build" / f"KangXiKai-full-v{VERSION}.ttf")
                       if (args.mapping or args.manifest)
                       else (WORK / "demo" / f"KangXiKai-demo-v{VERSION}.ttf"))

    glyphs = {}
    src = {}
    extra = {}
    if args.mapping:
        pages = {p.strip() for p in args.pages.split(",") if p.strip()} or None
        glyphs, src, extra["mapping"] = load_from_mapping(
            args.mapping, limit=args.limit, pages=pages,
            progress_every=args.progress_every)
    elif args.manifest:
        glyphs, src, extra["manifest"] = load_from_manifest_jsonl(args.manifest)
    else:
        for line in open(args.glyphs):
            r = json.loads(line)
            if r["char"] in glyphs:
                raise SystemExit(f"duplicate char {r['char']} in {args.glyphs}")
            glyphs[r["char"]] = r["contours"]
            src[r["char"]] = {k: r.get(k) for k in ("key", "page", "box", "layer",
                                                    "label_source", "verified_by",
                                                    "n_contours", "n_segs", "ink_px")}
    if not glyphs:
        raise SystemExit("ABORT: no glyphs")
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    per_char = build_font(glyphs, out, source_date_epoch=args.source_date_epoch)
    digest = sha256(out)
    stats = {
        "font": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
        "file_bytes": out.stat().st_size,
        "family": FAMILY, "style": STYLE, "version": VERSION, "upm": EM,
        "ascent": ASCENT, "descent": DESCENT,
        "n_glyphs": len(glyphs) + 1, "n_chars": len(glyphs),
        "sha256": digest,
        "source_date_epoch": int(os.environ.get("SOURCE_DATE_EPOCH",
                                                args.source_date_epoch or DEFAULT_SOURCE_DATE_EPOCH)),
        "glyphs": {ch: {**src[ch], **per_char[ch]} for ch in sorted(glyphs)},
        **extra,                      # mapping/manifest 批处理统计（耗时/缓存/跳过）
    }
    stats_path = Path(args.stats) if args.stats else out.with_suffix(".build_stats.json")
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"built {out}  chars={len(glyphs)}  sha256={digest}")


if __name__ == "__main__":
    sys.exit(main())
