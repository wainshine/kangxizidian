#!/usr/bin/env python3
"""C 流 · 组字体：glyphs.jsonl -> TTF（glyf + cmap + name 等）。

改造自 guangeti scripts/fontbuild.py（来源 commit 见 docs/VENDORED.md）：
  - 家族名 KangXi Kai / 版本 0.1.0 / EM 1000
  - 只映射 manifest 里真实存在的字（不做假覆盖、不 fill）
  - font.recalcTimestamp = False + 固定 SOURCE_DATE_EPOCH => 两次构建字节一致
"""



from __future__ import annotations


# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass
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
import gate_binding as GB  # noqa: E402  （构建归因：git commit/dirty）

EM = 1000
FAMILY = "KangXi Kai"
STYLE = "Regular"
VERSION = "0.1.0"
ASCENT, DESCENT = 880, -120
OFL_TEXT = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
            "This license is available with a FAQ at: https://openfontlicense.org")
COPYRIGHT = ("KangXi Kai — glyphs extracted from the 1716 Kangxi Dictionary "
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
        # BF-43/D20：禁止 restore/overlay 整字拷贝路径（旧字形会把旧框线带回）
        if isinstance(contours, dict):
            raise RuntimeError(f"非法字形数据（overlay/dict 通道已禁用）：{ch}")
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
_GEOM_CACHE = None
_GEOM_PATH = os.path.join(str(ROOT), "work", "lead", "page_geometry.jsonl")

def _sha12(p):
    import hashlib as _h
    try:
        return _h.sha256(open(p, "rb").read()).hexdigest()[:12]
    except Exception:
        return "missing"


def _cache_version():
    """算法+几何联合版本：任何算法脚本或几何缓存变化都会自动失效字形缓存（审计 P0-1/P0-4）。"""
    import hashlib as _h
    algo = _h.sha256()
    for f in ("font_norm.py", "page_frames.py", "detect_blocks.py", "font_build.py"):
        try:
            algo.update(open(os.path.join(str(ROOT), "scripts", f), "rb").read())
        except Exception:
            pass
    tag = os.environ.get("FONT_CACHE_TAG", "")
    bands = os.path.join(str(ROOT), "work", "lead", "page_line_bands.json")
    return f"{algo.hexdigest()[:8]}_{_sha12(_GEOM_PATH)}_{_sha12(bands)}{tag}"


_CACHE_VER = _cache_version()



def _load_geom():
    global _GEOM_CACHE
    if _GEOM_CACHE is not None:
        return _GEOM_CACHE
    _GEOM_CACHE = {}
    try:
        if os.path.exists(_GEOM_PATH):
            for line in open(_GEOM_PATH, encoding="utf-8"):
                r = json.loads(line)
                if "error" not in r:
                    _GEOM_CACHE[r["page"]] = r
            print(f"[geom] loaded {len(_GEOM_CACHE)} pages", flush=True)
    except Exception as e:
        print("[geom] load fail", e, flush=True)
    return _GEOM_CACHE


_LAT_CACHE = {}


def get_page_lattice(page_key: str) -> dict:
    """每页/半版拟合格点（节点=小字中心），返回 {half: (px,py,phx,phy)}。优先读页级几何缓存。"""
    if page_key in _LAT_CACHE:
        return _LAT_CACHE[page_key]
    geom = _load_geom().get(page_key)
    if geom and geom.get("lattice"):
        out = {k: tuple(v) for k, v in geom["lattice"].items() if v}
        _LAT_CACHE[page_key] = out
        return out
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


_QUAD_CACHE = {}


def get_page_content_quads(page_key: str):
    """版框内正文区（每半版）；裁切时直接 clip，框线/黑带不进入裁片。见 scripts/page_frames.py。"""
    if page_key in _QUAD_CACHE:
        return _QUAD_CACHE[page_key]
    geom = _load_geom().get(page_key)
    if geom and geom.get("quads"):
        quads = {}
        for k, q in geom["quads"].items():
            qq = dict(q)
            if qq.get("M") is not None:
                import numpy as _np
                qq["M"] = _np.asarray(qq["M"], dtype=_np.float32)
                qq["Minv"] = _np.asarray(qq["Minv"], dtype=_np.float32)
            quads[k] = qq
        # 兜底：缺半版 → 用 lattice + 小字中心 bbox 估计正文区（类级规则）
        if len(quads) < 2 and geom.get("lattice"):
            try:
                from detect_blocks import page_gray
                from page_frames import fallback_quad_from_lattice
                g = page_gray(page_key[:2], int(page_key[3:]))
                lattice = {k: tuple(v) for k, v in geom["lattice"].items() if v}
                for half in ("L", "R"):
                    if half not in quads:
                        q = fallback_quad_from_lattice(g, lattice.get(half))
                        if q:
                            quads[half] = q
            except Exception:
                pass
        _QUAD_CACHE[page_key] = quads
        return _QUAD_CACHE[page_key]
    try:
        from detect_blocks import page_gray
        from page_frames import detect_content_quads
        g = page_gray(page_key[:2], int(page_key[3:]))
        quads = detect_content_quads(g)
    except Exception as e:
        print("[quads] FAIL", page_key, e, flush=True)
        quads = {}
    _QUAD_CACHE[page_key] = quads
    return quads


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
    """正文墨迹 bbox 内缩（版框外沿≈bbox；内缩后不含框线）。优先读页级几何缓存。"""
    if page_key in _TEXT_BBOX_CACHE:
        return _TEXT_BBOX_CACHE[page_key]
    if inset == 5.0:
        geom = _load_geom().get(page_key)
        if geom and geom.get("text_bbox"):
            out = tuple(geom["text_bbox"])
            _TEXT_BBOX_CACHE[page_key] = out
            return out
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


def get_page_line_mask(page_key: str, dilate: int = 3):
    """页级长直线 mask（版框 / 界行 / 栏线；150dpi 页坐标 0/1）。

    与 get_page_frame_mask 的区别：阈值更低（竖 0.10×页高、横 0.12×页宽），
    专门抓「被大字打断成段」的界行/框线；仍远长于字头笔画（2×2 块 ≈ 0.06 页高），
    所以不会误伤字头笔画。在裁切前（pre-cut）把 mask 像素清零，替代单字层按形状删线。
    """
    import numpy as np
    import cv2
    from detect_blocks import page_gray, binarize
    try:
        g = page_gray(page_key[:2], int(page_key[3:]))
        ink = binarize(g).astype(np.uint8)
        h, w = ink.shape
        closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        lv = max(40, int(0.10 * h))
        lh = max(40, int(0.12 * w))
        vert = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((lv, 1), np.uint8))
        horiz = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((1, lh), np.uint8))
        lines = ((vert > 0) | (horiz > 0)).astype(np.uint8)
        # 第四遍：极细直线（宽 ≤2px@150dpi、长 ≥0.012 页 ≈20px）。
        # 注意不能用 distanceTransform 判「细」——笔画边界 rim 的 dist 也是 1，会削掉所有笔画边缘
        # （E33 实测 961 字掉墨 40–60%）。改用「横向/纵向 opening 去掉宽≥3px 结构后的残渣」，
        # 残渣只含窄结构（细线/亚像素残边），再用长核过滤成长直线，不与笔画边界重叠。
        try:
            if os.environ.get("FONT_LINE_ULTRA", "1") == "0":
                print("[line-mask-ultra] off", page_key) if False else None
            # 竖细线：先用水平 opening (1,3) 去掉宽≥3 的结构，残渣（宽≤2 的竖线）再做竖长 opening
            ink_u8 = ink.astype(np.uint8)
            op_h = cv2.morphologyEx(ink_u8, cv2.MORPH_OPEN, np.ones((1, 3), np.uint8))
            narrow_v = ink_u8 & (~op_h.astype(bool)).astype(np.uint8)
            # 横细线：先用竖直 opening (3,1)，再做横长 opening
            op_v = cv2.morphologyEx(ink_u8, cv2.MORPH_OPEN, np.ones((3, 1), np.uint8))
            narrow_h = ink_u8 & (~op_v.astype(bool)).astype(np.uint8)
            lv3 = max(16, int(0.012 * h))
            lh3 = max(16, int(0.012 * w))
            ultra_v = cv2.morphologyEx(narrow_v, cv2.MORPH_OPEN, np.ones((lv3, 1), np.uint8))
            ultra_h = cv2.morphologyEx(narrow_h, cv2.MORPH_OPEN, np.ones((1, lh3), np.uint8))
            lines = np.maximum(lines, ((ultra_v > 0) | (ultra_h > 0)).astype(np.uint8))
        except Exception as e:
            print("[line-mask-ultra] FAIL", page_key, e, flush=True)
        if int(lines.sum()) == 0:
            return None
        k = max(1, int(dilate))
        lines = cv2.dilate(lines, np.ones((k, k), np.uint8))
        return lines
    except Exception as e:
        print("[line-mask] FAIL", page_key, e, flush=True)
        return None


_LINE_BANDS = None


def get_page_line_bands(page_key: str):
    """页级「已验证线条带」数据（work/lead/page_line_bands.json，150dpi 页坐标）。

    来源：glyph_frame_gate 残线反算到页坐标后人工核对的 rect；只用于这些页，
    在 pre-cut 阶段把 rect 内像素清零。数据驱动（非启发式），页级作用域。
    """
    global _LINE_BANDS
    if os.environ.get("FONT_LINE_BANDS", "1") == "0":
        return []
    if _LINE_BANDS is None:
        _LINE_BANDS = {}
        try:
            p = ROOT / "work" / "lead" / "page_line_bands.json"
            if p.exists():
                _LINE_BANDS = json.loads(p.read_text())
        except Exception as e:
            print("[line-bands] load fail", e, flush=True)
            _LINE_BANDS = {}
    return _LINE_BANDS.get(page_key.replace("_", "_"), []) or []


def get_page_thin_line_mask(page_key: str):
    """页级「细短直线」mask（注文引文小框 / 短界行段；150dpi 页坐标 0/1）。

    厚度由距离变换限制（≤~4px@150dpi），长度下限 0.02 页（~33px）；
    只用于**字身 keep 区之外**（调用方在 vectorize_box 里按 box+margin 清空 keep 区），
    避免误删字头细笔画。
    """
    import numpy as np
    import cv2
    from detect_blocks import page_gray, binarize
    try:
        g = page_gray(page_key[:2], int(page_key[3:]))
        ink = binarize(g)
        h, w = ink.shape
        dist = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 5)
        thin = ((ink > 0) & (dist <= 2.2)).astype(np.uint8)
        lv2 = max(20, int(0.02 * h))
        lh2 = max(20, int(0.02 * w))
        thin_v = cv2.morphologyEx(thin, cv2.MORPH_OPEN, np.ones((lv2, 1), np.uint8))
        thin_h = cv2.morphologyEx(thin, cv2.MORPH_OPEN, np.ones((1, lh2), np.uint8))
        lines = ((thin_v > 0) | (thin_h > 0)).astype(np.uint8)
        if int(lines.sum()) == 0:
            return None
        return cv2.dilate(lines, np.ones((3, 3), np.uint8))
    except Exception as e:
        print("[thin-line-mask] FAIL", page_key, e, flush=True)
        return None


def _worker_page(args):
    """单页任务：该页所有（cache-miss）字一次性矢量化，页级 lattice/frame mask 只算一次。"""
    page, items = args
    from font_norm import vectorize_box
    out = []
    try:
        lat_all = get_page_lattice(page)
        tbb = get_page_text_bbox(page)
        quads = get_page_content_quads(page)
        line_mask = get_page_line_mask(page) if os.environ.get("FONT_PAGE_LINE_MASK", "1") != "0" else None
        _bands = get_page_line_bands(page)
        band_mask = None
        if _bands:
            try:
                from detect_blocks import page_gray as _pg
                _g = _pg(page[:2], int(page[3:]))
                band_mask = _g.copy()
                band_mask[:] = 0
                for rec in _bands:
                    x0, y0, x1, y1 = [int(round(v)) for v in rec["rect"]]
                    band_mask[max(0, y0):max(0, y1) + 1, max(0, x0):max(0, x1) + 1] = 1
            except Exception:
                band_mask = None
        thin_mask = get_page_thin_line_mask(page) if os.environ.get("FONT_PAGE_THIN_MASK", "1") != "0" else None
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
                                block150=block, content_quad=quads.get(half),
                                frame_mask=line_mask, frame_mask_extra=band_mask,
                                frame_mask_outer=thin_mask,
                                outer_keep_margin150=2.0,
                                keep_box150=tuple(it["vbox"]) if it.get("vbox") else None,
                                # D22：pre-cut（页 mask/线条带）已验证可独立做到 glyph_frame=0（E29），
                                # 切后形状删线 strip_border_lines 已从主链移除（默认关；env 仅留 A/B 复现）。
                                strip_border=(os.environ.get("FONT_STRIP_BORDER", "0") == "1"))
        except Exception as e:
            res = {"ok": False, "reason": str(e)[:120]}
        out.append((it["idx"], ch, res))
    return out


def clamp_workers(raw: int) -> int:
    """AGENTS §1：同时最多 10 个 worker；--workers/env 都不能绕过上限。"""
    n = max(1, min(10, int(raw or 10)))
    if int(raw or 10) > 10:
        print(f"[font_build] WARN: workers={raw} 超过上限 10，按 {n} 执行", file=sys.stderr, flush=True)
    return n


def load_from_mapping(path: str, limit: int = 0, pages: set | None = None,
                      progress_every: int = 500, workers: int = 0) -> tuple[dict, dict, list]:
    """全量 mapping（并行版）：按页并行矢量化；缓存读写留在主进程。"""
    import time as _time
    from concurrent.futures import ProcessPoolExecutor
    from font_norm import vectorize_box  # noqa: F401  (worker 内部也会 import)
    # BF-43/D20：override/overlay 旧字形拷贝通道已删除（不存在任何读取入口）
    cache_dir = WORK / "build" / "cache" / _CACHE_VER
    cache_dir.mkdir(parents=True, exist_ok=True)
    use_cache = "--no-cache" not in sys.argv
    glyphs: dict[str, list] = {}
    src: dict[str, dict] = {}
    skipped = []
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
            if limit and len(seen) >= limit:
                skipped.append({"page": page, "half": half, "char": ch, "reason": "limit"})
                break
            seen.add(ch)
            n_seen += 1
            ck = (f"{_CACHE_VER}_{page}{half}_{ch}_"
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
            # verified tight box keep 区：实验通道（E25），默认关闭。
            # 原因：verified box 对部分字是片段框/不完整（去/蘇/緅），用作 keep 会删真笔画；
            # 待「由字形自身 ink 反推 ROI（二次 pass）」方案验证后再启用。
            vbox = a.get("verified_box") if os.environ.get("FONT_VERIFIED_KEEP", "0") == "1" else None
            if vbox:
                ba = max(1.0, (box[2] - box[0]) * (box[3] - box[1]))
                va = (vbox[2] - vbox[0]) * (vbox[3] - vbox[1])
                if va < 0.6 * ba:
                    vbox = None
            items.append({"idx": idx, "char": ch, "half": half, "box": box,
                          "page": page, "cpath": str(cpath), "vbox": vbox})
            idx += 1

    # 按页分组并行
    jobs = {}
    for it in items:
        jobs.setdefault(it["page"], []).append(it)
    job_list = [(pg, its) for pg, its in jobs.items()]
    print(f"[font_build] parallel: pages={len(job_list)} glyphs={len(items)} cached={n_cached}", flush=True)
    results = {}
    done = 0
    max_workers = clamp_workers(workers or int(os.environ.get("FONT_BUILD_WORKERS", "10") or 10))
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
    # 硬失败分类：limit 是显式调试截断（合法）；其余（构字失败/重复字/缺字段）都算失败
    hard_failed = [x for x in skipped if x.get("reason") != "limit"]
    if hard_failed:
        print(f"[font_build] ERROR: {len(hard_failed)} 字失败/跳过（skipped 已落盘；"
              f"--allow-partial 才可放行）", flush=True)
    print(f"[font_build] vectorized {n_new} new glyphs in {_time.time()-t0:.1f}s "
          f"(cached {n_cached}, skipped {len(skipped)})", flush=True)
    return glyphs, src, skipped


def _rel_path(p):
    """仓库内路径写相对；仓库外返回绝对串（不能 relative_to 崩溃，审计 BUILD-10）。"""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except Exception:
        return str(p)


def load_from_manifest_jsonl(path: str, workers: int = 0) -> tuple[dict, dict, list]:
    """--manifest 入口（审计 BUILD-09：原函数未定义，必 NameError）。

    manifest chars 记录自带 page/half/box；转成 mapping 形态的临时 JSONL 复用并行/缓存主链。
    """
    import tempfile
    man = json.load(open(path, encoding="utf-8"))["chars"]
    rows = {}
    for ch, r in man.items():
        if not (r.get("page") and r.get("box")):
            raise SystemExit(f"manifest 记录缺 page/box: {ch}")
        rows.setdefault((r["page"], r.get("half", "")), []).append(
            {"char": ch, "cand": {"box": r["box"]}})
    fd, tmp = tempfile.mkstemp(suffix=".jsonl", prefix="_manifest_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fo:
            for (page, half), assigned in rows.items():
                fo.write(json.dumps({"page": page, "half": half, "assigned": assigned},
                                    ensure_ascii=False) + "\n")
        return load_from_mapping(tmp, workers=workers)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


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
    ap.add_argument("--workers", type=int, default=0, help="并行 worker 数（硬上限 10）")
    ap.add_argument("--allow-partial", action="store_true",
                    help="调试用：允许有失败字仍写出字体（会写失败清单，禁止用于候选）")
    # BF-43/D20：--src-map（旧 override）与 --repair-overlay（整字拷贝）入口已删除
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
        glyphs, src, extra["skipped"] = load_from_mapping(
            args.mapping, limit=args.limit, pages=pages,
            progress_every=args.progress_every, workers=args.workers)
    elif args.manifest:
        glyphs, src, extra["skipped"] = load_from_manifest_jsonl(args.manifest,
                                                                 workers=args.workers)
    else:
        for line in open(args.glyphs):
            r = json.loads(line)
            if r["char"] in glyphs:
                raise SystemExit(f"duplicate char {r['char']} in {args.glyphs}")
            glyphs[r["char"]] = r["contours"]
            src[r["char"]] = {k: r.get(k) for k in ("key", "page", "box", "layer",
                                                    "label_source", "verified_by",
                                                    "n_contours", "n_segs", "ink_px")}
    skipped_list = extra.get("skipped") or []
    failed = [x for x in skipped_list if x.get("reason") != "limit"]
    out = Path(args.out)
    stats_path0 = Path(args.stats) if args.stats else out.with_suffix(".build_stats.json")
    if failed and not args.allow_partial:
        stats_path0.parent.mkdir(parents=True, exist_ok=True)
        stats_path0.write_text(json.dumps({"aborted": True, "reason": "build failures",
                                           "failed_n": len(failed), "failed": failed,
                                           "skipped": skipped_list,
                                           "input": _rel_path(args.mapping or args.manifest)},
                                          ensure_ascii=False, indent=1))
        raise SystemExit(f"ABORT: {len(failed)} 字构建失败/跳过（失败清单已写入 {stats_path0}；"
                         f"调试可用 --allow-partial）")
    if not glyphs:
        stats_path0.parent.mkdir(parents=True, exist_ok=True)
        stats_path0.write_text(json.dumps({"aborted": True, "reason": "no glyphs",
                                           "skipped": skipped_list,
                                           "input": _rel_path(args.mapping or args.manifest)},
                                          ensure_ascii=False, indent=1))
        raise SystemExit("ABORT: no glyphs（空输入；已写失败报告）")
    if not out.is_absolute():
        out = ROOT / out
    per_char = build_font(glyphs, out, version=args.version,
                          source_date_epoch=args.source_date_epoch)
    digest = sha256(out)
    cache_dir_now = WORK / "build" / "cache" / _CACHE_VER
    cache_files = len(list(cache_dir_now.glob("*.json"))) if cache_dir_now.exists() else 0
    stats = {
        "cache": {"dir": _rel_path(cache_dir_now), "files": cache_files,
                  "n_chars": len(glyphs),
                  "note": "缓存按 _CACHE_VER 分子目录；files 应等于 n_chars（旧 flat 目录不再读取）"},
        "input_mapping": (_rel_path(args.mapping) if args.mapping else None),
        "input_mapping_sha256": sha256(Path(args.mapping)) if args.mapping else None,
        "input_manifest": (_rel_path(args.manifest) if args.manifest else None),
        "input_manifest_sha256": sha256(Path(args.manifest)) if args.manifest else None,
        "cache_ver": _CACHE_VER,
        "geometry": {"path": _rel_path(_GEOM_PATH), "sha256": sha256(Path(_GEOM_PATH))
                     if Path(_GEOM_PATH).exists() else None},
        "git": GB.git_state(),
        "workers": clamp_workers(args.workers or int(os.environ.get("FONT_BUILD_WORKERS", "10") or 10)),
        "font": (_rel_path(out) if out.is_absolute() else str(out)),
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
    stats_path = stats_path0
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"built {out}  chars={len(glyphs)}  sha256={digest}")


if __name__ == "__main__":
    sys.exit(main())
