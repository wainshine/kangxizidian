#!/usr/bin/env python3
"""Lead · 书眉读数 v2：版心柱定位 + 切格 + 楷体模板匹配（只识别部名/画数，集名/葉码用公式）。

设计（2026-11-08 第二轮）：
- 版心柱 = L 半版左缘 ~ 第一根长竖版框线（x∈[~4, ~95]@300dpi，逐页自适应）
- 切格 = 水平投影（小间隙合并；宽格按竖直投影拆「十+二」粘连）
- 识别 = 楷体模板匹配（GuanGeKai）：候选集 = 214 部首 + 数字 + 部/畫
  * 「部」定位 部名 = 部前一个格；部后解析 数字+畫 字段
- 集名/葉码 不识别：volume_sections.json 给集名；葉码=册内页码−5

用法：
  .venv/bin/python scripts/lead_header_v2.py --vols 01 --eval-gold     # 20 页 owner 真值对账
  .venv/bin/python scripts/lead_header_v2.py --vols 01,02 --workers 8  # 出 headers
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAIFONT = os.path.expanduser("~/Library/Fonts/GuanGeKai-Regular.ttf")
SONG = "/System/Library/Fonts/Supplemental/Songti.ttc"

RAD214 = ("一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山"
          "巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬"
          "玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫"
          "血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟"
          "鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠")
NUM_CH = "一二三四五六七八九十廿卅卌百"
NUMV = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
        "十": 10, "廿": 20, "卅": 30, "卌": 40, "百": 100}

_T = {}


def _norm(m, size=48):
    h, w = m.shape
    s = size / max(h, w)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    mm = cv2.resize(m.astype(np.uint8) * 255, (nw, nh), interpolation=cv2.INTER_AREA)
    c = np.zeros((size, size), np.uint8)
    c[(size - nh) // 2:(size - nh) // 2 + nh, (size - nw) // 2:(size - nw) // 2 + nw] = mm
    return c.astype(np.float32) / 255.0


def _score(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-6 else 0.0


def templates():
    """渲染模板：{char: [norm mask, ...]}，多字号抗尺度。"""
    global _T
    if _T:
        return _T
    from PIL import Image, ImageDraw, ImageFont
    chars = set(RAD214) | set(NUM_CH) | set("部畫")
    for ch in chars:
        masks = []
        for size in (70, 86):
            for path in (KAIFONT, SONG):
                if not os.path.exists(path):
                    continue
                try:
                    f = ImageFont.truetype(path, size)
                except Exception:
                    continue
                im = Image.new("L", (size * 2, size * 2), 255)
                ImageDraw.Draw(im).text((size // 3, size // 4), ch, font=f, fill=0)
                a = np.array(im)
                m = a < 140
                ys, xs = np.where(m)
                if len(ys) < 10:
                    continue
                masks.append(_norm(m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]))
        if masks:
            _T[ch] = masks
    return _T


def best_match(mask, cand_chars):
    q = _norm(mask > 0)
    out = []
    for ch in cand_chars:
        for tm in _T.get(ch, []):
            out.append((_score(q, tm), ch))
    out.sort(reverse=True)
    return out


def find_strip(gray):
    """版心柱 x 范围：L 半版左缘 ~ 第一根长竖框线。"""
    H, W = gray.shape
    raw = (gray <= 150).astype(np.uint8)
    # 去掉页缘黑带（最左 ~6px）
    raw[:, :4] = 0
    v = cv2.morphologyEx(raw, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(H * 0.30))))
    cols = v.sum(axis=0)
    cand = [x for x in range(30, min(260, W - 1)) if cols[x] > H * 0.30]
    frame = None
    if cand:
        groups = [[cand[0]]]
        for x in cand[1:]:
            if x - groups[-1][-1] <= 3:
                groups[-1].append(x)
            else:
                groups.append([x])
        frame = int(np.mean(groups[0]))
    x0 = 4
    x1 = frame - 3 if (frame and frame > 55) else 95
    return x0, int(x1)


def segment_cells(strip):
    """水平投影切格；宽格按竖直投影拆。返回 [(y0,y1,mask)]。"""
    ink = (strip <= 145).astype(np.uint8)
    proj = ink.sum(axis=1)
    thr = 1
    runs = []
    inr = False
    for i, v in enumerate(proj):
        if v > thr and not inr:
            s = i; inr = True
        elif v <= thr and inr:
            runs.append([s, i]); inr = False
    if inr:
        runs.append([s, len(proj)])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 5:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    cells = []
    for a, b in merged:
        h = b - a
        if h < 16:
            continue
        sub = ink[a:b]
        cols = sub.sum(axis=0)
        nz = np.where(cols > 0)[0]
        if len(nz) == 0:
            continue
        x0, x1 = int(nz.min()), int(nz.max())
        w = x1 - x0 + 1
        if w > 1.45 * h:
            # 拆宽格
            cr = []
            inr2 = False
            for i, v in enumerate(cols):
                if v > 0 and not inr2:
                    s2 = i; inr2 = True
                elif v <= 0 and inr2:
                    cr.append([s2, i]); inr2 = False
            if inr2:
                cr.append([s2, len(cols)])
            cm = []
            for c0, c1 in cr:
                if cm and c0 - cm[-1][1] <= 3:
                    cm[-1][1] = c1
                else:
                    cm.append([c0, c1])
            any_added = False
            for c0, c1 in cm:
                if c1 - c0 < 0.25 * h:
                    continue
                m = sub[:, c0:c1]
                ys, xs = np.where(m > 0)
                if len(ys) < 15:
                    continue
                cells.append((a + int(ys.min()), a + int(ys.max()) + 1,
                              m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]))
                any_added = True
            if any_added:
                continue
        cells.append((a, b, sub[:, x0:x1 + 1]))
    # 过滤高度异常
    hs = [b - a for a, b, _ in cells]
    if hs:
        med = float(np.median(hs))
        cells = [c for c in cells if 0.4 * med <= (c[1] - c[0]) <= 2.3 * med]
    return cells


def parse_header(cells):
    """识别 + 固定槽位解析。返回 dict(bu, hua, cells_rec, errors)。"""
    tpl = templates()
    recs = []
    for (a, b, m) in cells:
        top = best_match(m, list(tpl.keys()))[:3]
        recs.append({"pos": [int(a), int(b)], "top": top})
    allc = [r["top"][0] for r in recs]
    errors = []
    # 找「部」（最高分的那个，且足够可信）
    bu_idx, bu_s = None, 0.0
    for i, r in enumerate(recs):
        for s, ch in r["top"]:
            if ch == "部" and s > bu_s:
                bu_idx, bu_s = i, s
    bu = None
    if bu_idx is None or bu_s < 0.50:
        errors.append("no_bu")
        return {"bu": None, "hua": [], "cells_rec": [r["top"][:2] for r in recs],
                "errors": errors}
    # 部名 = 前一个格（对 214 部首单独匹配）
    if bu_idx > 0:
        top = best_match(cells[bu_idx - 1][2], list(RAD214))
        bu = top[0][1] if top and top[0][0] > 0.42 else None
        if bu is None:
            errors.append("rad_low")
    else:
        errors.append("no_rad_cell")
    # 画数字段：部后开始，数字累计，遇 畫 收一个字段
    hua = []
    cur = ""
    for r in recs[bu_idx + 1:]:
        ch, s = r["top"][0]
        if ch == "畫":
            if s < 0.45:
                errors.append("hua_char_low")
            if cur:
                v = parse_num(cur)
                if v is None:
                    errors.append("num_bad:" + cur)
                else:
                    hua.append(v)
                cur = ""
            else:
                errors.append("empty_hua")
            continue
        if ch in NUM_CH and s > 0.38:
            cur += ch
        else:
            if cur:
                errors.append("num_break:" + cur)
            break
    if cur:
        errors.append("tail:" + cur)
    return {"bu": bu, "hua": hua, "cells_rec": [r["top"][:2] for r in recs],
            "errors": errors}


def parse_num(s):
    if not s or any(c not in NUMV for c in s):
        return None
    if len(s) == 1:
        return NUMV[s]
    if len(s) == 2:
        a, b = s
        if a in "廿卅卌" and b in NUMV:
            return NUMV[a] + NUMV[b]
        if a == "十" and b in NUMV:
            return 10 + NUMV[b]
        if b == "十" and a in NUMV:
            return NUMV[a] * 10
        if a in NUMV and b in NUMV:
            return None  # 少见：如 一二
    if len(s) == 3 and s[1] == "十":
        return NUMV[s[0]] * 10 + NUMV[s[2]]
    return None


def section_ji(sections, vol, page):
    info = sections.get(vol)
    if not info:
        return None
    names = ["上", "中", "下"]
    for k, (a, b) in enumerate(info["runs"][:3]):
        if a <= page <= b:
            return info["ji"] + "集" + names[k]
    return None


def process_page(vol, page, sections, dpi):
    import fitz
    global _DOC, _DOC_VOL
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    doc = _DOC
    pix = doc[page - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    gray = img[:, :img.shape[1] // 2]
    x0, x1 = find_strip(gray)
    strip = gray[:, x0:x1]
    cells = segment_cells(strip)
    parsed = parse_header(cells)
    ji = section_ji(sections, vol, page)
    buf = parsed["cells_rec"]
    rec = {"page": f"{vol}_{page:04d}", "half": "L",
           "ji": ji, "bu": (parsed["bu"] + "部") if parsed["bu"] else None,
           "hua": parsed["hua"], "leaf_no": page - 5,
           "conf": round(0.55 + 0.45 * (len(parsed["hua"]) > 0) *
                         (0.6 + 0.4 * (parsed["bu"] is not None)), 3),
           "errors": parsed["errors"], "strip_x": [x0, x1],
           "n_cells": len(cells),
           "cells_top": [[c[0], c[1]] for c in buf]}
    return rec


_DOC = None
_DOC_VOL = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", default="01")
    ap.add_argument("--pages", default="body")
    ap.add_argument("--eval-gold", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/headers_v2.jsonl"))
    ap.add_argument("--debug-dir", default=None)
    args = ap.parse_args()
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        roles[r["vol"]].append((r["page"], r["role"]))
    sections = json.load(open(os.path.join(ROOT, "work/lead/volume_sections.json"),
                             encoding="utf-8"))
    gold = {}
    if args.eval_gold:
        g = json.load(open(os.path.join(ROOT, "work/t2/margin_labels_full.json"),
                          encoding="utf-8"))["pages"]
        for pg, d in g.items():
            gold[pg] = d
    jobs = []
    for vol in args.vols.split(","):
        for page, role in sorted(roles[vol]):
            if args.pages == "body" and role != "body":
                continue
            jobs.append((vol, page))
    if args.eval_gold:
        jobs = [(v, int(p[3:])) for p in gold for v in [p[:2]]]
    print(f"jobs {len(jobs)}")
    import fitz
    docs = {}
    fout = open(args.out, "w", encoding="utf-8")
    stats = collections.Counter()
    # 简单串行（fitz 不能跨进程共享；多进程可后续加）
    cur_vol = None
    for vol, page in jobs:
        if vol != cur_vol:
            if cur_vol and cur_vol in docs:
                docs[cur_vol].close()
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典",
                                               json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"),
                                                              encoding="utf-8"))[vol]))
            cur_vol = vol
        global _DOC
        _DOC = docs[vol]
        try:
            rec = process_page(vol, page, sections, args.dpi)
        except Exception as e:
            rec = {"page": f"{vol}_{page:04d}", "half": "L", "ji": None, "bu": None,
                   "hua": [], "errors": ["exc:" + str(e)[:60]]}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats["n"] += 1
        if rec.get("bu"):
            stats["bu"] += 1
        if rec.get("hua"):
            stats["hua"] += 1
        if args.eval_gold and rec["page"] in gold:
            gd = gold[rec["page"]]
            L = gd.get("L") or {}
            gbu = L.get("bu")
            ghua = L.get("hua") or []
            ghua_n = []
            for h in ghua:
                t = str(h).replace("畫", "")
                v = parse_num(t)
                if v is not None:
                    ghua_n.append(v)
            ok_bu = rec["bu"] is not None and gbu is not None and \
                rec["bu"].rstrip("部") in gbu
            ok_hua = (rec["hua"] == ghua_n) if ghua_n else None
            stats["gold"] += 1
            stats["gold_bu_ok"] += int(bool(ok_bu))
            if ok_hua is not None:
                stats["gold_hua_checked"] += 1
                stats["gold_hua_ok"] += int(bool(ok_hua))
            print(f"{rec['page']} got bu={rec['bu']} hua={rec['hua']} | truth bu={gbu} "
                  f"hua={ghua_n} | {'OK' if ok_bu else 'BU_X'} "
                  f"{'' if ok_hua is None else ('HUA_OK' if ok_hua else 'HUA_X')} "
                  f"{rec['errors']}")
    fout.close()
    for d in docs.values():
        d.close()
    print(dict(stats))


if __name__ == "__main__":
    main()
