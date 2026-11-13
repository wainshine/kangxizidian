#!/usr/bin/env python3
"""A2 · 书眉读数（L 半版左缘版心条）— 快速主流程。

口径（owner 20 页实证标定；docs/_history/TAKEOVER.md §2.D/§5、DECISIONS D14）：
- 扫描页 = 跨页；书眉竖排在 L 半版最左缘（版心，x≈[6, frame_x]），R 半版右缘被裁不读。
- 字段序（自上而下，owner 20 页确认）：
    康熙字典(4 字，左侧常被扫描裁切，不解析)
    → 集名卷(3 字，如「子集中」；由册号+卷界给出，只做校验)
    → 部名(2 字：部首字 + 「部」)
    → 画数(1–2 个字段，每字段 = 数词 + 「畫」；跨分界页两个，语义 = 先 R 后 L)
    → 葉码(1–3 数字字)
- 书眉画数 = 部外笔画数；葉码 = 该册内叶序，PDF01–12 实测 葉码 = 扫描页 − 5。
- **集名以刻本版心为准**：owner 核验 03_0015 版心「寅集上·山部」，而 MIT 数据集路径
  作「寅集中·山字部」→ 数据集集卷划分与 1716 内府刊本不同，不能用数据集集名做校验。

方法：fitz clip 300dpi 渲染左缘条 → 局部背景归一化 + 去长线 → 行投影切字格
（同字碎片合并：缝≤2 且高≤100，或 缝≤34 且高≤62）→ PaddleOCR rec 单字识别
（批量）→「集」「部」OCR 锚点定字段 → 部名取「上/中/下」与「部」之间整段墨迹合并 OCR
（防「山」类碎字）→ 画数/葉码：以「畫」字为界（OCR + 笔画几何双票），数字用 OCR +
扁平数词笔画几何；葉码用页−5 公式复核。

产出：work/seq/headers_raw.jsonl（原始读数，供 header_resolve.py 做序列约束修正）
      work/seq/headers.jsonl（lead solver 口径：page=01_0006, bu 带「部」, hua int 数组）
"""
import argparse
import json
import os
import re
import tempfile

import cv2
import numpy as np

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_MAP = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
OUT_DIR = os.path.join(ROOT, "work", "seq")

RAD214 = ("一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕"
          "大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰"
          "月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢"
          "石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言"
          "谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬"
          "骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠")
RAD_SET = set(RAD214)
JI_CHARS = set("子丑寅卯辰巳午未申酉戌亥")
JI_SUFFIX = set("上中下")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
          "十": 10, "廿": 20, "卅": 30, "百": 100, "千": 1000}
NUM_CHARS = set(CN_NUM)
HUA = "畫"
HUA_ALIAS = set("畫晝画重書")
ALIAS = {"帥": "艸", "帅": "艸", "卄": "艸", "艹": "艸", "王": "玉", "见": "見", "马": "馬",
         "鸟": "鳥", "鱼": "魚", "贝": "貝", "车": "車", "门": "門", "风": "風", "飞": "飛",
         "麦": "麥", "黄": "黃", "齐": "齊", "齿": "齒", "龙": "龍", "龟": "龜", "户": "戶",
         "攵": "攴", "糹": "糸", "罒": "网", "西": "襾", "辶": "辵", "长": "長", "青": "靑",
         "韦": "韋", "页": "頁", "鬥": "鬥", "门": "門", "阜": "阜", "成": "戌", "巴": "巳", "己": "巳", "已": "巳",
         "洒": "酉", "酒": "酉", "□": "口", "◻": "口", "〇": "口", "回": "口"}


# --------------------------------------------------------------------------- #
# 渲染 / 版面几何 / 切格
# --------------------------------------------------------------------------- #
def render_strip(pdf, page, dpi=300, clipw_pt=40.0):
    import fitz
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    try:
        p = doc[page - 1]
        pix = p.get_pixmap(dpi=dpi, clip=fitz.Rect(0, 0, clipw_pt, p.rect.height))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
    finally:
        doc.close()
    return gray


def page_geometry(gray):
    """返回 (x0, x1, frame_x)：书眉字符列带 + 版框左线。

    不同页/册扫描左边距差异大（如 01_0027 内容列在 x≈55–93），且版心顶部常有
    康熙字典四字（被左裁）与墨污/印章。做法：粗切行块 → 按墨迹 x 范围聚类，
    取块数最多的一簇为「内容列」→ 重定 x 带。
    """
    H, W = gray.shape
    dark = (gray[:, : min(60, W)] <= 100)
    colfrac = dark.mean(axis=0)
    border_end = 0
    for x in range(len(colfrac)):
        if colfrac[x] > 0.55:
            border_end = x
    x0 = max(6, border_end + 2)
    ink0 = (gray <= 140).astype(np.uint8)
    v = cv2.morphologyEx(ink0, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 250)))
    cs = v.sum(axis=0)
    cands = [x for x in range(65, min(135, W)) if cs[x] >= 250]
    frame_x = min(cands, key=lambda x: abs(x - 92)) if cands else 92
    x_right = max(x0 + 24, frame_x - 3)

    # 粗切行块并取每块墨迹 x 范围
    strip = cv2.medianBlur(gray[:, x0:x_right], 3)
    bg = cv2.medianBlur(strip, 61)
    mask = ((bg.astype(np.int16) - strip.astype(np.int16)) > 45).astype(np.uint8)
    vert = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 120)))
    mask = mask & (1 - vert)          # 去竖长线（版框/列线），否则 x 范围聚类全糊
    rows = mask.sum(axis=1)
    on = rows >= 2
    runs, s = [], None
    for i, val in enumerate(on):
        if val and s is None:
            s = i
        if not val and s is not None:
            runs.append((s, i))
            s = None
    if s is not None:
        runs.append((s, len(on)))
    extents = []
    for a, b in runs:
        if b - a < 20:
            continue
        cols = np.where(mask[a:b].sum(axis=0) > 0)[0]
        if len(cols) == 0:
            continue
        extents.append((int(cols[0]), int(cols[-1])))
    if extents:
        # 单链聚类（x 范围接近）
        clusters = []
        for ext in extents:
            best, best_iou = None, 0.0
            for c in clusters:
                cxa, cxb = c["x0"], c["x1"]
                inter = min(cxb, ext[1]) - max(cxa, ext[0]) + 1
                if inter <= 0:
                    continue
                union = max(cxb, ext[1]) - min(cxa, ext[0]) + 1
                iou = inter / union
                if iou > best_iou:
                    best, best_iou = c, iou
            if best is not None and best_iou > 0.55:
                best["xs"].append(ext)
                best["x0"] = min(best["x0"], ext[0])
                best["x1"] = max(best["x1"], ext[1])
            else:
                clusters.append({"xs": [ext], "x0": ext[0], "x1": ext[1]})
        clusters.sort(key=lambda c: len(c["xs"]), reverse=True)
        best = clusters[0]
        if len(best["xs"]) >= 4 and best["x1"] - best["x0"] >= 30:
            x0 = x0 + best["x0"]
            x_right = x0 + (best["x1"] - best["x0"] + 1)
    return x0, x_right, frame_x


def ink_mask(gray, x0, x1, delta=45):
    strip = cv2.medianBlur(gray[:, x0:x1], 3)
    bg = cv2.medianBlur(strip, 61)
    ink = ((bg.astype(np.int16) - strip.astype(np.int16)) > delta).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 12:
            keep[lab == i] = 1
    vert = cv2.morphologyEx(keep, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 140)))
    horz = cv2.morphologyEx(keep, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1)))
    return keep & (1 - vert) & (1 - horz)


def segment_cells(mask, min_h=5):
    """行投影切字格 + 同字碎片合并（两档规则，见模块 docstring）。"""
    rows = mask.sum(axis=1)
    on = rows >= 2
    runs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            runs.append([s, i])
            s = None
    if s is not None:
        runs.append([s, len(on)])
    merged = []
    for a, b in runs:
        if merged:
            pa, pb = merged[-1]
            gap, hh = a - pb, b - pa
            if (gap <= 2 and hh <= 100) or (gap <= 34 and hh <= 74):
                merged[-1][1] = b
                continue
        merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= min_h]


def cell_binimg(gray, a, b, x0, x1):
    crop = gray[max(0, a - 3):min(gray.shape[0], b + 3), x0:x1]
    bg = cv2.medianBlur(crop, 51)
    ink = (bg.astype(np.int16) - crop.astype(np.int16)) > 24
    return np.where(ink, 0, 255).astype(np.uint8)


def region_binimg(gray, y0, y1, x0, x1, trim=True):
    """区域二值图（严格阈值 + 去小块 + 裁白），供整段 OCR / 笔画几何。"""
    crop = gray[max(0, y0):min(gray.shape[0], y1), x0:x1]
    strip = cv2.medianBlur(crop, 3)
    bg = cv2.medianBlur(strip, 61)
    ink = ((bg.astype(np.int16) - strip.astype(np.int16)) > 45).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 10:
            keep[lab == i] = 1
    if trim:
        rows = np.where(keep.sum(axis=1) >= 2)[0]
        cols = np.where(keep.sum(axis=0) >= 1)[0]
        if len(rows) and len(cols):
            keep = keep[max(0, rows[0] - 2):rows[-1] + 3,
                        max(0, cols[0] - 2):cols[-1] + 3]
    return np.where(keep, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# OCR
# --------------------------------------------------------------------------- #
_OCR = None


def get_ocr():
    global _OCR
    if _OCR is None:
        import warnings
        warnings.filterwarnings("ignore")
        from paddleocr import TextRecognition
        _OCR = TextRecognition(model_name="PP-OCRv5_server_rec")
    return _OCR


def _ocr_input(binimg, target_h=80):
    h, w = binimg.shape
    if h < 1 or w < 1:
        return np.full((120, 200), 255, np.uint8)
    sc = target_h / h
    im = cv2.resize(binimg, (max(1, int(w * sc)), target_h), interpolation=cv2.INTER_AREA)
    W = max(200, im.shape[1] + 80)
    canvas = np.full((120, W), 255, np.uint8)
    y0 = (120 - im.shape[0]) // 2
    x0 = (canvas.shape[1] - im.shape[1]) // 2
    canvas[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = im
    return canvas


def ocr_batch(binimgs, tmpdir):
    if not binimgs:
        return []
    ocr = get_ocr()
    paths = []
    for i, bi in enumerate(binimgs):
        fn = os.path.join(tmpdir, f"c{i:04d}.png")
        cv2.imwrite(fn, _ocr_input(bi))
        paths.append(fn)
    out = []
    try:
        res = ocr.predict(paths)
        for r in res:
            d = r.json.get("res", {}) if hasattr(r, "json") else {}
            out.append((d.get("rec_text") or "", float(d.get("rec_score") or 0.0)))
    except Exception:
        for fn in paths:
            try:
                r = ocr.predict(fn)[0]
                d = r.json.get("res", {}) if hasattr(r, "json") else {}
                out.append((d.get("rec_text") or "", float(d.get("rec_score") or 0.0)))
            except Exception:
                out.append(("", 0.0))
    finally:
        for fn in paths:
            try:
                os.remove(fn)
            except OSError:
                pass
    return out


# --------------------------------------------------------------------------- #
# 数字 / 几何
# --------------------------------------------------------------------------- #
def _bands(flags):
    cnt, prev = 0, False
    for f in flags:
        if f and not prev:
            cnt += 1
        prev = f
    return cnt


def stroke_geom(binimg):
    h, w = binimg.shape
    if h < 4 or w < 8:
        return 0, 0
    ink = (binimg < 128).astype(np.uint8)
    return _bands(ink.sum(axis=1) > 0.45 * w), _bands(ink.sum(axis=0) > 0.45 * h)


def numeral_geom(binimg):
    h, w = binimg.shape
    hb, vb = stroke_geom(binimg)
    if hb == 1 and vb == 0 and h <= 26:
        return "一"
    if hb == 2 and vb == 0 and h <= 50:
        return "二"
    if hb == 3 and vb == 0 and h <= 64:
        return "三"
    if hb == 1 and vb == 1 and h <= 85:
        return "十"
    if hb == 2 and vb == 2 and h <= 85:
        return "廿"
    if hb == 2 and vb == 3 and h <= 85:
        return "卅"
    return None


def flat_numeral_value(binimg):
    """扁平数词（一/二/三/十/廿/卅及其组合）整段笔画判定，仅 1–39 范围。"""
    h, w = binimg.shape
    if h < 4 or w < 8:
        return None
    ink = (binimg < 128).astype(np.uint8)
    rs = ink.sum(axis=1)
    cs = ink.sum(axis=0)
    hb = _band_list(rs > 0.45 * w)
    vb = _band_list(cs > 0.45 * h)
    nh, nv = len(hb), len(vb)
    if nv == 0:
        return nh if 1 <= nh <= 3 else None
    if nv == 1:
        x0v, x1v = vb[0]
        vrow = ink[:, x0v:x1v + 1].sum(axis=1) > 0
        vr = _band_list(vrow)
        vy0, vy1 = (vr[0][0], vr[-1][1]) if vr else (0, h - 1)
        cross = None
        for k, (a, b) in enumerate(hb):
            if b >= vy0 and a <= vy1:
                cross = k
                break
        if cross is None:
            return None
        above = cross
        below = nh - cross - 1
        if above == 0:
            return 10 + below
        if below == 0 and above in (2, 3):
            return 10 * above
        return None
    if nv == 2:   # 廿 / 廿X
        if nh >= 2:
            return 20 + (nh - 2)
        return None
    if nv == 3:   # 卅 / 卅X
        if nh >= 2:
            return 30 + (nh - 2)
        return None
    return None


def _band_list(flags):
    out, s = [], None
    for i, v in enumerate(flags):
        if v and s is None:
            s = i
        if not v and s is not None:
            out.append((s, i))
            s = None
    if s is not None:
        out.append((s, len(flags)))
    return out


def cn2int(s):
    if not s:
        return None
    s = "".join(ch for ch in s if ch in NUM_CHARS)
    if not s:
        return None
    if s in CN_NUM:
        return CN_NUM[s]
    total, cur = 0, 0
    for ch in s:
        if ch == "百":
            total += (cur if cur else 1) * 100
            cur = 0
        elif ch == "十":
            total += (cur if cur else 1) * 10
            cur = 0
        elif ch == "廿":
            total += 20
            cur = 0
        elif ch == "卅":
            total += 30
            cur = 0
        else:
            cur = CN_NUM.get(ch, 0)
    return total + cur


def int2cn(v):
    if v is None:
        return ""
    if v == 0:
        return ""
    if v < 10:
        return "一二三四五六七八九"[v - 1]
    if v < 20:
        return "十" + ("" if v == 10 else "一二三四五六七八九"[v - 11])
    if v < 100:
        t, r = divmod(v, 10)
        base = {2: "廿", 3: "卅"}.get(t, "一二三四五六七八九"[t - 1] + "十") if t > 1 else "十"
        if t > 1 and t > 3:
            base = "一二三四五六七八九"[t - 1] + "十"
        return base + ("" if r == 0 else "一二三四五六七八九"[r - 1])
    if v < 1000:
        h, r = divmod(v, 100)
        return ("" if h == 1 else "一二三四五六七八九"[h - 1]) + "百" + int2cn(r)
    return ""


def is_hua_cell(text, score, h, w):
    t = (text or "").strip()
    if t and any(ch in HUA_ALIAS for ch in t) and score >= 0.40:
        return True
    if t and t[-1] in HUA_ALIAS:
        return True
    hb, vb = 0, 0
    return False


def hua_shape(binimg):
    """「畫」类字形几何特征（20 页实测：畫 h≥73,w≥70,竖画带≥2,墨率≥0.20）。"""
    h, w = binimg.shape
    if h < 73 or w < 70 or h > 130:
        return False
    ink = (binimg < 128)
    hb, vb = stroke_geom(binimg)
    return vb >= 2 and ink.mean() >= 0.20


# --------------------------------------------------------------------------- #
# 卷界（work/lead/page_roles.jsonl）：集名卷由册号 + body 段落下标给出
# --------------------------------------------------------------------------- #
_PAGE_ROLES = None
VOL_JI = {"01": "子", "02": "丑", "03": "寅", "04": "卯", "05": "辰", "06": "巳",
          "07": "午", "08": "未", "09": "申", "10": "酉", "11": "戌", "12": "亥"}


def load_page_roles():
    global _PAGE_ROLES
    if _PAGE_ROLES is not None:
        return _PAGE_ROLES
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "work", "lead", "page_roles.jsonl"),
                                        encoding="utf-8")]
    byv = {}
    for r in rows:
        byv.setdefault(r["vol"], []).append((r["page"], r["role"]))
    info = {}
    for vol, rs in byv.items():
        rs.sort()
        runs, start = [], None
        for p, role in rs:
            if role == "body" and start is None:
                start = p
            if role != "body" and start is not None:
                runs.append((start, p - 1))
                start = None
        if start is not None:
            runs.append((start, rs[-1][0]))
        info[vol] = runs
    _PAGE_ROLES = info
    return info


def ji_from_roles(pdf, page):
    """由 page_roles 的 body 段推 集名卷（PDF01–12）。PDF13/00 返回 None。"""
    if pdf not in VOL_JI:
        return None
    info = load_page_roles()
    runs = info.get(pdf) or []
    for i, (a, b) in enumerate(runs[:3]):
        if a <= page <= b:
            suffix = "上中下"[i]
            return f"{VOL_JI.get(pdf, '')}集{suffix}"
    return None


# --------------------------------------------------------------------------- #
# 单页解析
# --------------------------------------------------------------------------- #
def extract_page(pdf, page, tmpdir, dpi=300):
    gray = render_strip(pdf, page, dpi=dpi)
    H, W = gray.shape
    x0, x1, frame_x = page_geometry(gray)
    mask = ink_mask(gray, x0, x1)
    cells = [(a, b) for (a, b) in segment_cells(mask) if b - a <= 240]
    if not cells:
        return None
    crops = [cell_binimg(gray, a, b, x0, x1) for (a, b) in cells]
    ocr = ocr_batch(crops, tmpdir)
    rec = [{"i": i, "y0": a, "y1": b, "ctr": (a + b) / 2.0,
            "text": (t or "").strip(), "score": s}
           for i, ((a, b), (t, s)) in enumerate(zip(cells, ocr))]
    out = {"pdf": pdf, "page": page, "frame_x": frame_x, "x0": x0, "x1": x1,
           "cells": rec, "ji": None, "ji_char": None, "ji_score": 0.0, "suffix": None,
           "suffix_score": 0.0, "bu": None, "bu_raw": None, "bu_score": 0.0,
           "hua": None, "hua_raw": None, "leaf_ocr": None,
           "errors": []}

    # ---- 锚点：集 / 部 ----
    def anchor(tok, minscore, contains=False):
        cand = []
        for r in rec:
            t = r["text"] or ""
            hit = tok in t if contains else t == tok
            if hit and r["score"] >= minscore:
                cand.append(r)
        return max(cand, key=lambda r: r["score"]) if cand else None

    ji_a = anchor("集", 0.60, contains=True)
    bu_a = anchor("部", 0.70)
    if bu_a is None:
        bu_a = anchor("部", 0.40, contains=True)
    if ji_a is None:
        out["errors"].append("no_ji")
        return out
    ji_idx = ji_a["i"]
    # 集名前一字（集名卷首字）
    if ji_idx - 1 >= 0:
        c = rec[ji_idx - 1]
        ch = pick_ji_char(c["text"])
        out["ji_char"], out["ji_score"] = ch, c["score"]
        if ch is None:
            out["errors"].append("ji_char_unread")
    if bu_a is None:
        # 可能是補遺/備考页
        after = [r for r in rec[ji_idx + 1:] if r["y1"] - r["y0"] >= 20]
        st = "".join((r["text"] or "")[:1] for r in after[:2])
        if "補" in st and "遺" in st:
            out["suffix"] = "補遺"
            out["section"] = "buqi"
        elif "備" in st and "考" in st:
            out["suffix"] = "備考"
            out["section"] = "beikao"
        else:
            out["errors"].append("no_bu")
        jr = ji_from_roles(pdf, page)
        if jr:
            out["ji"] = jr
        elif out["ji_char"] and out["suffix"] in ("補遺", "備考"):
            out["ji"] = f"{out['ji_char']}集{out['suffix']}"
        elif out["ji_char"]:
            out["ji"] = f"{out['ji_char']}集"
        # 葉码：補遺/備考页「X集補遺/備考」共 4 字，集 anchor 之后还有 2 字
        tail = after[2:] if len(after) >= 2 else []
        parts = []
        for r in tail:
            v, raw = cell_numeral(r, crops[r["i"]])
            if v is not None:
                parts.append(int2cn(v))
            elif raw:
                parts.append(raw)
        lo = "".join(parts) or None
        if lo and not all(ch in NUM_CHARS for ch in lo):
            lo = "".join(ch for ch in lo if ch in NUM_CHARS) or None
        if lo is None or cn2int(lo) is None:
            # 整段 OCR 兜底：从集名末字到文末
            start_y = (after[1]["y1"] + 6) if len(after) >= 2 else (rec[ji_idx]["y1"] + 6)
            bot = hr_last_text_bottom(mask, start_y)
            if bot:
                lr = leaf_region_ocr(gray, start_y, bot + 6, x0, x1, tmpdir)
                if lr:
                    lo = lr
        out["leaf_ocr"] = lo
        return out
    out["section"] = "zheng"
    bu_idx = bu_a["i"]
    out["bu_score"] = bu_a["score"]

    # ---- 集名卷后缀：集之后、部之前的首个正常字格 ----
    suffix_cell = None
    for r in rec[ji_idx + 1:bu_idx]:
        if r["y1"] - r["y0"] >= 20:
            ch = pick_suffix(r["text"])
            if ch:
                out["suffix"], out["suffix_score"] = ch, r["score"]
                suffix_cell = r
                break
    if out["suffix"] is None:
        out["errors"].append("suffix_unread")
        # 仍取第一个正常格作为 rad 段边界
        for r in rec[ji_idx + 1:bu_idx]:
            if r["y1"] - r["y0"] >= 20:
                suffix_cell = r
                break

    # ---- 部名：后缀与「部」之间的整段墨迹合并 OCR ----
    rad_cells = [r for r in rec[ji_idx + 1:bu_idx]
                 if suffix_cell is None or r["i"] > suffix_cell["i"]]
    if rad_cells:
        a = min(r["y0"] for r in rad_cells) - 3
        b = max(r["y1"] for r in rad_cells) + 3
        rad_img = region_binimg(gray, a, b, x0, x1)
        # 同时做整段 OCR 与单格候选
        cand_imgs = [rad_img] + [crops[r["i"]] for r in rad_cells]
        cand_ocr = ocr_batch(cand_imgs, tmpdir)
        best = None
        for (t, s) in cand_ocr:
            ch = pick_rad_char(t)
            if ch and (best is None or s > best[1]):
                best = (ch, s, t)
        if best:
            out["bu"], out["bu_score"], out["bu_raw"] = best[0], best[1], best[2]
        else:
            out["bu_raw"] = cand_ocr[0][0] if cand_ocr else None
            out["errors"].append("rad_unread")

    # ---- 画数 + 葉码：部以下，以「畫」为字段界 ----
    after = []
    prev_bottom = rec[bu_idx]["y1"]
    for r in rec[bu_idx + 1:]:
        if r["y0"] - prev_bottom > 250:   # 版框/空白后噪声，截断
            break
        after.append(r)
        prev_bottom = max(prev_bottom, r["y1"])
    if not after:
        out["errors"].append("no_after")
        out["ji"] = out.get("ji") or ji_from_roles(pdf, page)
        return out

    def is_hua(r):
        bi = crops[r["i"]]
        t, sc = r["text"], r["score"]
        if t and all(ch in NUM_CHARS for ch in t):
            return False
        if t and any(ch in HUA_ALIAS for ch in t) and sc >= 0.42:
            return True
        return hua_shape(bi) and (sc >= 0.4 or not t)

    fields = []          # [(cells_before, hua_cell)]
    cur = []
    for r in after:
        if is_hua(r):
            fields.append((cur, r))
            cur = []
        else:
            cur.append(r)
    leaf_cells = cur

    # 第二遍：字段数>2 视为 畫 误检（画数字段最多 2 个），保留最可信的两个
    if len(fields) > 2:
        fields.sort(key=lambda f: f[1]["score"], reverse=True)
        keep = set(id(f[1]) for f in fields[:2])
        fields = [f for f in fields if id(f[1]) in keep]
        fields.sort(key=lambda f: f[1]["i"])

    hua_vals, hua_raw = [], []
    region_imgs, region_meta = [], []
    prev_bottom = rec[bu_idx]["y1"]
    for cells_f, hua_cell in fields:
        y0 = prev_bottom + 4
        y1 = max(y0 + 8, hua_cell["y0"] - 3)
        region_meta.append((cells_f, hua_cell, y0, y1))
        region_imgs.append(region_binimg(gray, y0, y1, x0, x1))
        prev_bottom = hua_cell["y1"]
    region_ocr = ocr_batch(region_imgs, tmpdir) if region_imgs else []

    hua_basis = []
    for (cells_f, hua_cell, y0, y1), (rt, rs) in zip(region_meta, region_ocr):
        val = None
        raw = None
        basis = None
        # 1) 单格数字拼接（OCR 高置信）
        nums = []
        for c in cells_f:
            v, rr = cell_numeral(c, crops[c["i"]])
            if v is not None:
                nums.append((v, rr, c["score"]))
        if nums and len(nums) == len(cells_f):
            s2 = "".join(int2cn(v) if isinstance(v, int) else str(rr) for v, rr, _sc in nums)
            val = cn2int(s2)
            if val is not None:
                raw = s2
                basis = "ocr" if min(n[2] for n in nums) >= 0.85 else "ocr_weak"
        # 2) 整段 OCR
        if val is None and rt:
            t2 = "".join(ch for ch in rt if ch in NUM_CHARS)
            if t2:
                val = cn2int(t2)
                raw = t2
                basis = "region"
        # 3) 笔画几何兜底
        if val is None:
            rv = flat_numeral_value(region_binimg(gray, y0, y1, x0, x1))
            if rv is not None:
                val = rv
                raw = raw or str(rv)
                basis = "flat"
        hua_vals.append(val)
        hua_raw.append(raw)
        hua_basis.append(basis)
    out["hua_basis"] = hua_basis
    out["hua"] = hua_vals if hua_vals else None
    out["hua_raw"] = hua_raw if hua_raw else None

    # ---- 葉码：01–12 公式 = 页−5；13/00 用尾巴数字格 + 整段 OCR ----
    leaf_ocr = None
    if leaf_cells:
        parts = []
        for r in leaf_cells:
            v, raw = cell_numeral(r, crops[r["i"]])
            if v is not None:
                parts.append(int2cn(v))
            elif raw:
                parts.append(raw)
        leaf_ocr = "".join(parts) or None
        if leaf_ocr and not all(ch in NUM_CHARS for ch in leaf_ocr):
            leaf_ocr = "".join(ch for ch in leaf_ocr if ch in NUM_CHARS) or None
    out["leaf_ocr"] = leaf_ocr
    out["ji"] = ji_from_roles(pdf, page)
    return out

    return out


def hr_last_text_bottom(mask, y_top):
    """y_top 之后、下一根横贯版框线之前的最后一行有效文字。"""
    rows = mask.sum(axis=1)
    W = mask.shape[1]
    frame = rows > 0.72 * W
    limit = len(rows) - 1
    for i in range(max(0, y_top), len(rows)):
        if frame[i]:
            limit = max(0, i - 3)
            break
    for i in range(limit, max(0, y_top - 1), -1):
        if rows[i] >= 3 and (rows[max(0, i - 1)] >= 3 or rows[min(len(rows) - 1, i + 1)] >= 3):
            return i
    return None


def leaf_region_ocr(gray, y0, y_bot, x0, x1, tmpdir):
    """葉码段整段 OCR（用于 PDF13 / 公式不可用处）。"""
    reg = region_binimg(gray, max(0, y0), min(gray.shape[0], y_bot), x0, x1)
    if reg.shape[0] < 10:
        return None
    t, sc = ocr_batch([reg], tmpdir)[0]
    if not t:
        return None
    t2 = "".join(ch for ch in t if ch in NUM_CHARS)
    if t2 and cn2int(t2) is not None:
        return t2
    # 笔画几何
    return None


def pick_ji_char(t):
    t = t or ""
    for ch in t:
        if ch in JI_CHARS:
            return ch
    for ch in t:
        al = ALIAS.get(ch)
        if al in JI_CHARS:
            return al
    return None


def pick_suffix(t):
    t = t or ""
    for ch in t:
        if ch in JI_SUFFIX:
            return ch
    return None


def pick_rad_char(t):
    t = t or ""
    if len(t) == 1 and t in RAD_SET:
        return t
    for ch in t:
        if ch in RAD_SET:
            return ch
    for ch in t:
        al = ALIAS.get(ch)
        if al in RAD_SET:
            return al
    return None


def cell_numeral(rec_cell, binimg):
    """单格 → 数字值；返回 (int|None, raw)。"""
    t = rec_cell["text"] or ""
    if t and all(ch in NUM_CHARS for ch in t):
        return cn2int(t), t
    g = numeral_geom(binimg)
    if g:
        return CN_NUM[g], g
    return None, (t or None)


def combine_numerals(pending, crops):
    """把一串数词格合并成一个数值。pending: [(v, idx, raw)]。"""
    if not pending:
        return None
    # 优先用 OCR 原文拼接
    s_ocr = "".join(p[2] for p in pending if p[2])
    if s_ocr and all(ch in NUM_CHARS for ch in s_ocr):
        v = cn2int(s_ocr)
        if v is not None:
            return v
    # 用数值拼接（int2cn）
    s2 = "".join(int2cn(p[0]) if isinstance(p[0], int) else (p[2] or "") for p in pending)
    if s2 and all(ch in NUM_CHARS for ch in s2):
        v = cn2int(s2)
        if v is not None:
            return v
    return None


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def _worker_init():
    get_ocr()


def _worker_run(args):
    chunk, tmpbase, dpi, part_i = args
    tmpdir = tempfile.mkdtemp(prefix="hdr_", dir=tmpbase)
    part = os.path.join(tmpbase, f"_part_{part_i:02d}.jsonl")
    n = 0
    with open(part, "w", encoding="utf-8") as f:
        for pdf, page in chunk:
            try:
                rec = extract_page(pdf, page, tmpdir, dpi=dpi)
            except Exception as e:
                rec = {"pdf": pdf, "page": page, "errors": [f"exception:{e}"]}
            if rec is None:
                rec = {"pdf": pdf, "page": page, "errors": ["no_cells"]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
    return part, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--pdfs", default=None, help="逗号分隔多册，如 01,02")
    ap.add_argument("--pages", default=None)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "headers_raw.jsonl"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--eval-gold", action="store_true")
    ap.add_argument("--strips", default=None, help="保存裁剪后 strip（[0,frame_x]）")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    if args.eval_gold:
        pages_sel = [(k.split("_")[0], int(k.split("_")[1])) for k in load_owner_gold()]
    else:
        if args.pdfs:
            pdfs = [x.strip() for x in args.pdfs.split(",") if x.strip()]
        else:
            pdfs = [args.pdf] if args.pdf else list(PDF_MAP.keys())
        pages_sel = []
        for pdf in pdfs:
            n = pdf_page_count(pdf)
            rng = parse_ranges(args.pages) if args.pages else None
            if rng is None:
                pages_sel += [(pdf, p) for p in range(1, n + 1)]
            else:
                pages_sel += [(pdf, p) for p in range(1, n + 1) if p in rng]
    if args.limit:
        pages_sel = pages_sel[:args.limit]

    # 可选：顺手存 strip（仅单进程路径）
    if args.strips:
        os.makedirs(args.strips, exist_ok=True)
        tmpdir = tempfile.mkdtemp(prefix="hdr_", dir=OUT_DIR)
        for pdf, page in pages_sel:
            g = render_strip(pdf, page, dpi=args.dpi)
            x0, x1, fx = page_geometry(g)
            cv2.imwrite(os.path.join(args.strips, f"{pdf}_{page:04d}_L.png"),
                        g[:, :max(x1 + 3, fx)])

    tmpbase = os.path.join(OUT_DIR, "parts")
    os.makedirs(tmpbase, exist_ok=True)
    for f in os.listdir(tmpbase):
        if f.startswith("_part_"):
            os.remove(os.path.join(tmpbase, f))
    workers = max(1, args.workers)
    # 连续分块：每个 worker 处理连续页段，part 文件即连续区段，可增量使用
    n = len(pages_sel)
    bounds = [round(i * n / workers) for i in range(workers + 1)]
    chunks = [pages_sel[bounds[i]:bounds[i + 1]] for i in range(workers)]
    parts = []
    if workers == 1:
        parts = [_worker_run((pages_sel, tmpbase, args.dpi, 0))]
    else:
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers, initializer=_worker_init) as pool:
            for res in pool.imap_unordered(
                    _worker_run, [(c, tmpbase, args.dpi, i)
                                  for i, c in enumerate(chunks) if c]):
                parts.append(res)
                print(f"part done {res[0]} ({res[1]} pages)", flush=True)
    results = []
    for path, _cnt in parts:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            results.append(json.loads(line))
    results = [r for r in results if r is not None]
    results.sort(key=lambda r: (r["pdf"], r["page"]))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(results)} rows -> {args.out}")
    if args.eval_gold:
        evaluate(results, load_owner_gold())


def load_owner_gold():
    d = json.load(open(os.path.join(ROOT, "work", "t2", "margin_labels_full.json"),
                       encoding="utf-8"))
    return d["pages"]


def gold_hua(hs):
    if not hs:
        return None
    out = []
    for h in hs:
        v = cn2int(h.rstrip("?"))
        if v is None:
            return None
        out.append(v)
    return out


def gold_leaf(leaf):
    if not leaf:
        return None
    s = re.sub(r"[（(].*?[)）]", "", leaf).rstrip("?")
    return cn2int(s)


def evaluate(rows, gold):
    import collections
    n = 0
    cnt = collections.Counter()
    print("\n== owner 20 页评测（OCR 原始读数，未做序列修正）==")
    for r in rows:
        key = f"{r['pdf']}_{r['page']:04d}"
        g = gold.get(key)
        if not g:
            continue
        n += 1
        L = g["L"]
        ji_e = L.get("ji")
        bu_e = (L.get("bu") or "").rstrip("?").replace("部", "") if L.get("bu") else None
        hua_e = gold_hua(L.get("hua"))
        leaf_e = gold_leaf(g.get("leaf"))
        passed = []
        ji_got = r.get("ji") or (f"{r.get('ji_char')}集{r.get('suffix')}"
                                 if r.get("ji_char") and r.get("suffix") else None)
        if ji_e:
            cnt["ji_n"] += 1
            if ji_got == ji_e:
                cnt["ji"] += 1
                passed.append("ji")
        if bu_e:
            cnt["bu_n"] += 1
            if r.get("bu") == bu_e:
                cnt["bu"] += 1
                passed.append("bu")
        if hua_e is not None:
            cnt["hua_n"] += 1
            if r.get("hua") == hua_e:
                cnt["hua"] += 1
                passed.append("hua")
        if leaf_e is not None:
            cnt["leaf_n"] += 1
            if (r["pdf"] not in ("00", "13")) and r["page"] - 5 == leaf_e:
                cnt["leaf"] += 1
                passed.append("leaf")
        print(f" {key}: ji={r.get('ji') or (str(r.get('ji_char'))+'集'+str(r.get('suffix')))} vs {ji_e} | "
              f"bu={r.get('bu')}({r.get('bu_raw')}) vs {bu_e} | "
              f"hua={r.get('hua')} vs {hua_e} | leaf5={r['page']-5 if r['pdf'] not in ('00','13') else None} vs {leaf_e} | {passed}")
    print(f"\n集名 {cnt['ji']}/{cnt['ji_n']}  部名 {cnt['bu']}/{cnt['bu_n']}  "
          f"画数 {cnt['hua']}/{cnt['hua_n']}  葉码(公式) {cnt['leaf']}/{cnt['leaf_n']}")


def parse_ranges(s):
    out = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            a = int(a) if a else 1
            b = int(b) if b else 10 ** 6
            out.update(range(a, b + 1))
        else:
            out.add(int(part))
    return out


def pdf_page_count(pdf):
    import fitz
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    n = doc.page_count
    doc.close()
    return n


if __name__ == "__main__":
    main()
