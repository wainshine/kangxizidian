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
    from fontTools.ttLib.tables._g_l_y_f import Glyph as _Glyph
    for ch in chars:
        gname = f"uni{ord(ch):04X}"
        contours = glyphs[ch]
        if isinstance(contours, dict) and "__overlay__" in contours:
            rec = contours["__overlay__"]
            g = _Glyph()
            g.numberOfContours = len(rec["endPts"])
            from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
            g.coordinates = GlyphCoordinates([(int(p[0]), int(p[1])) for p in rec["points"]])
            g.flags = bytearray(int(p[2]) for p in rec["points"])
            g.endPtsOfContours = [int(e) for e in rec["endPts"]]
            from fontTools.ttLib.tables.ttProgram import Program as _Program
            g.program = _Program()
            glyf[gname] = g
            xs = [int(p[0]) for p in rec["points"]]
            ys = [int(p[1]) for p in rec["points"]]
            xmin = min(xs) if xs else 0
            metrics[gname] = (EM, xmin)
            per_char[ch] = {"n_contours": g.numberOfContours,
                            "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 0, 0]}
            continue
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
                ulUnicodeRange1=1, ulUnicodeRange2=(1 << 27) | (1 << 28) | (1 << 29),
                ulCodePageRange1=(1 << 18) | (1 << 20))
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


# ---------------------------------------------------------------------------
# 页级预处理（格点 / 正文 bbox / 版框 mask）——make font 的「源头边界」基础设施
# ---------------------------------------------------------------------------
_LAT_CACHE = {}


def get_page_lattice(page_key: str) -> dict:
    """每页/半版拟合格点（节点=小字中心），返回 {half: (px,py,phx,phy)}。"""
    if page_key in _LAT_CACHE:
        return _LAT_CACHE[page_key]
    import numpy as np
    import cv2
    from detect_blocks import page_gray, binarize, fit_axis
    try:
        g = page_gray(page_key[:2], int(page_key[3:]))
        ink = binarize(g)
        h, w = g.shape
        col = ink.sum(axis=0).astype(np.float32)
        lo, hi = int(w * 0.42), int(w * 0.58)
        gx = int(lo + np.argmin(col[lo:hi]))
        out = {}
        n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
        for name, mask in (("L", lambda x, y: x < gx), ("R", lambda x, y: x >= gx)):
            small = []
            for i in range(1, n):
                x, y, ww, hh, a = [int(v) for v in st[i]]
                if not mask(x + ww / 2, y + hh / 2):
                    continue
                if 24 <= hh <= 54 and 9 <= ww <= 60 and 40 <= a <= 1200:
                    small.append((x + ww / 2, y + hh / 2, hh))
            if len(small) < 80:
                out[name] = None
                continue
            h0 = float(np.median([v[2] for v in small]))
            xs = np.array([v[0] for v in small]); ys = np.array([v[1] for v in small])
            _, px, phx = fit_axis(xs, 0.9 * h0, 1.9 * h0)
            _, py, phy = fit_axis(ys, 0.85 * h0, 1.6 * h0)

            def refine(vals, pitch, phase):
                lag = np.mod(vals - phase + pitch / 2, pitch) - pitch / 2
                return phase + float(np.median(lag))
            out[name] = (float(px), float(py), refine(xs, px, phx), refine(ys, py, phy))
        _LAT_CACHE[page_key] = out
    except Exception as e:
        print("[lattice] FAIL", page_key, e, flush=True)
        _LAT_CACHE[page_key] = {}
    return _LAT_CACHE[page_key]


def block_for_box(lat, box):
    """由字框中心求其 2×2 格块（150dpi）。节点=小字中心 => 块左上 = 节点 - 半格。"""
    if not lat:
        return None
    px, py, phx, phy = lat
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    c = int(round((cx - phx) / px - 0.5))
    r = int(round((cy - phy) / py - 0.5))
    m = 3.0  # 块外扩 3px@150 安全余量
    return (phx + (c - 0.5) * px - m, phy + (r - 0.5) * py - m,
            phx + (c + 1.5) * px + m, phy + (r + 1.5) * py + m)


_TEXT_BBOX_CACHE = {}


def get_page_text_bbox(page_key: str, inset: float = 5.0):
    """正文墨迹 bbox 内缩（版框外沿≈bbox；内缩后不含框线）。"""
    if page_key in _TEXT_BBOX_CACHE:
        return _TEXT_BBOX_CACHE[page_key]
    import numpy as np
    from detect_blocks import page_gray, binarize
    out = None
    try:
        g = page_gray(page_key[:2], int(page_key[3:]))
        ink = binarize(g)
        ys, xs = np.nonzero(ink)
        if len(xs):
            h, w = ink.shape
            out = (max(0.0, xs.min() + inset), max(0.0, ys.min() + inset),
                   min(float(w), xs.max() - inset), min(float(h), ys.max() - inset))
    except Exception as e:
        print("[bbox] FAIL", page_key, e, flush=True)
    _TEXT_BBOX_CACHE[page_key] = out
    return out


_FRAME_MASK_CACHE = {}


def get_page_frame_mask(page_key: str):
    """页面版框线 mask（150dpi 页坐标，0/1）。

    形态学开运算提取「连续长横线/长竖线」（框线连续；字是分离的不会形成连续长线）：
      横线核长 0.35×页宽，竖线核长 0.45×页高；先闭运算补 1-2px 断裂；再膨胀 ±2px。
    """
    if page_key in _FRAME_MASK_CACHE:
        return _FRAME_MASK_CACHE[page_key]
    import numpy as np
    import cv2
    from detect_blocks import page_gray, binarize
    mask = None
    try:
        g = page_gray(page_key[:2], int(page_key[3:]))
        ink = binarize(g)
        h, w = ink.shape
        closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        horiz = cv2.morphologyEx(closed, cv2.MORPH_OPEN,
                                 np.ones((1, max(20, int(0.35 * w))), np.uint8))
        vert = cv2.morphologyEx(closed, cv2.MORPH_OPEN,
                                np.ones((max(20, int(0.45 * h)), 1), np.uint8))
        lines = ((horiz > 0) | (vert > 0)).astype(np.uint8)
        if int(lines.sum()) > 0:
            lines = cv2.dilate(lines, np.ones((5, 5), np.uint8))
        mask = lines
    except Exception as e:
        print("[frame] FAIL", page_key, e, flush=True)
        mask = None
    _FRAME_MASK_CACHE[page_key] = mask
    return mask


def _worker_page(args):
    """单页任务：该页所有（cache-miss）字一次性矢量化，页级 lattice/frame mask 只算一次。"""
    page, items = args
    from font_norm import vectorize_box
    out = []
    try:
        lat_all = get_page_lattice(page)
        tbb = get_page_text_bbox(page)
        fms = get_page_frame_mask(page)
    except Exception as e:
        return [(it["idx"], None, {"ok": False, "reason": f"page prepare: {e}"}) for it in items]
    for it in items:
        ch = it["char"]; half = it["half"]; box = it["box"]
        try:
            block = block_for_box(lat_all.get(half), box)
            if block is not None and tbb is not None:
                block = (max(block[0], tbb[0]), max(block[1], tbb[1]),
                         min(block[2], tbb[2]), min(block[3], tbb[3]))
            res = vectorize_box(page, box, enable_edge_strip=False,
                                block150=block, frame_mask=fms)
        except Exception as e:
            res = {"ok": False, "reason": str(e)[:120]}
        out.append((it["idx"], ch, res))
    return out


def load_from_mapping(path: str, limit: int = 0, pages: set | None = None,
                      progress_every: int = 500, src_map: dict | None = None,
                      repair_overlay: str | None = None) -> tuple[dict, dict, list]:
    """全量 mapping（并行版）：按页并行矢量化；缓存读写留在主进程。"""
    import time as _time
    from concurrent.futures import ProcessPoolExecutor
    from font_norm import vectorize_box  # noqa: F401  (worker 内部也会 import)
    override_path = ROOT / "work" / "lead" / "contours_override.json"
    override = json.load(open(override_path)) if override_path.exists() else {}
    src_map = src_map or {}
    if override and not src_map:
        print("[font_build] WARN: 存在 contours_override，但未提供 --src-map；override 将不会生效",
              file=sys.stderr)
    cache_dir = WORK / "build" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    use_cache = "--no-cache" not in sys.argv
    glyphs: dict[str, list] = {}
    src: dict[str, dict] = {}
    skipped = []
    overlay = {}
    if repair_overlay:
        for line in open(repair_overlay, encoding="utf-8"):
            rec = json.loads(line)
            overlay[rec["char"]] = rec
        print(f"[font_build] repair overlay: {len(overlay)} glyphs", flush=True)
    t0 = _time.time()

    # 先按顺序展开 + 去重（重复字只取第一次），并做 cache 命中
    items = []            # 待并行处理
    idx = 0
    seen = set()
    n_seen = n_cached = 0
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
                skipped.append({"page": page, "half": half, "char": ch, "reason": "缺 char 或 box"})
                continue
            if ch in seen:
                skipped.append({"page": page, "half": half, "char": ch,
                                "reason": f"重复字（已用 {src[ch]['page']})"})
                continue
            seen.add(ch)
            if limit and len(seen) >= limit:
                break
            n_seen += 1
            if ch in overlay:
                glyphs[ch] = {"__overlay__": overlay[ch]}
                src[ch] = {"page": page, "half": half, "box": box,
                           "label_source": "repair_overlay", "cached": True}
                n_cached += 1
                continue
            src_tag = str(a.get("label_source") or src_map.get(ch, ""))
            if ch in override and src_tag == "from_v201_glyph":
                glyphs[ch] = override[ch]["contours"]
                src[ch] = {"page": page, "half": half, "box": box, "cached": True,
                           "override": str(override[ch].get("source", ""))}
                n_cached += 1
                continue
            ck = (f"v312_{page}{half}_{ch}_"
                  f"{box[0]}_{box[1]}_{box[2]}_{box[3]}").replace("/", "_")
            cpath = cache_dir / f"{ck}.json"
            if use_cache and cpath.exists():
                try:
                    rec = json.loads(cpath.read_text())
                except Exception:
                    rec = {}
                if rec.get("ok"):
                    glyphs[ch] = rec["contours"]
                    src[ch] = {**rec["src"], "cached": True}
                    n_cached += 1
                    continue
            items.append({"idx": idx, "char": ch, "half": half, "box": box,
                          "page": page, "cpath": str(cpath)})
            idx += 1

    # 按页分组并行
    jobs = {}
    for it in items:
        jobs.setdefault(it["page"], []).append(it)
    job_list = [(pg, its) for pg, its in jobs.items()]
    print(f"[font_build] parallel: pages={len(job_list)} glyphs={len(items)} cached={n_cached}", flush=True)
    results = {}
    done = 0
    max_workers = int(os.environ.get("FONT_BUILD_WORKERS", "8"))
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        for page_res in ex.map(_worker_page, job_list, chunksize=1):
            for (i, ch, res) in page_res:
                results[i] = res
            done += 1
            if done % 50 == 0:
                print(f"  pages done {done}/{len(job_list)}  glyphs={len(results)}  "
                      f"{1000*(_time.time()-t0)/max(1,len(results)):.1f} ms/glyph", flush=True)

    n_new = 0
    for it in items:
        i = it["idx"]; ch = it["char"]; page = it["page"]; half = it["half"]; box = it["box"]
        res = results.get(i) or {"ok": False, "reason": "missing result"}
        if not res.get("ok"):
            skipped.append({"page": page, "half": half, "char": ch, "reason": res.get("reason")})
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
            Path(it["cpath"]).write_text(json.dumps({"ok": True, "char": ch,
                                                             "contours": res["contours"], "src": m},
                                                            ensure_ascii=False))
    print(f"[font_build] vectorized {n_new} new glyphs in {_time.time()-t0:.1f}s "
          f"(cached {n_cached}, skipped {len(skipped)})", flush=True)
    return glyphs, src, skipped


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
    ap.add_argument("--version", default=VERSION, help="字体内部版本号（name 表 / fontRevision）")
    ap.add_argument("--no-cache", action="store_true", default=False, help="禁用字形缓存")
    ap.add_argument("--src-map", default="", help="union JSON（char→label_source），供 override 门禁")
    ap.add_argument("--repair-overlay", default="",
                    help="修复 overlay JSONL（char/endPts/points），优先于缓存使用")
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
        src_map = {}
        if args.src_map:
            raw = json.load(open(args.src_map, encoding="utf-8"))
            for _c, _r in raw.items():
                src_map[_c] = str(_r.get("label_source", "")) if isinstance(_r, dict) else ""
        glyphs, src, extra["mapping"] = load_from_mapping(
            args.mapping, limit=args.limit, pages=pages,
            progress_every=args.progress_every, src_map=src_map,
            repair_overlay=args.repair_overlay or None)
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
    per_char = build_font(glyphs, out, version=args.version,
                          source_date_epoch=args.source_date_epoch)
    digest = sha256(out)
    stats = {
        "input_mapping": (str(Path(args.mapping).resolve().relative_to(ROOT)) if args.mapping else None),
        "input_mapping_sha256": sha256(Path(args.mapping)) if args.mapping else None,
        "input_manifest": (str(Path(args.manifest).resolve().relative_to(ROOT)) if args.manifest else None),
        "font": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
        "file_bytes": out.stat().st_size,
        "family": FAMILY, "style": STYLE, "version": args.version, "upm": EM,
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
