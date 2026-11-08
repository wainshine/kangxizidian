#!/usr/bin/env python3
"""Lead · 书眉（版心）读数 v1：结构解析 + 模板匹配（楷体模板，GuanGeKai）。

不读「康熙字典」「集名」「葉码」——它们分别由固定长度/卷表/公式给定：
  集名 <= work/lead/volume_sections.json（卷界表）;  葉码 <= 扫描页 − 5（PDF01-12，seq 实测）
只识别：部名（部首字符）+ 画数（数字 + 畫）。

版心柱 = 页面左缘到第一根竖版框线之间；字符按水平投影切格（宽格再按竖直投影拆）。
输出：work/lead/headers_lead.jsonl
"""
import json, os, sys, argparse, collections
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
NUMS = "一二三四五六七八九十廿卅卌百"


def render_templates():
    """渲染候选字符模板（64x64 归一化 ink mask）。"""
    from PIL import Image, ImageDraw, ImageFont
    fonts = []
    for path in (KAIFONT, SONG):
        if os.path.exists(path):
            fonts.append(path)
    chars = set(RAD214) | set(NUMS) | set("部畫康熙字典")
    out = {}
    for ch in chars:
        masks = []
        for fp in fonts[:1]:
            try:
                f = ImageFont.truetype(fp, 80)
            except Exception:
                continue
            im = Image.new("L", (120, 120), 255)
            d = ImageDraw.Draw(im)
            d.text((15, 10), ch, font=f, fill=0)
            a = np.array(im)
            m = a < 140
            ys, xs = np.where(m)
            if len(ys) == 0:
                continue
            m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            masks.append(norm_mask(m))
        if masks:
            out[ch] = masks
    return out


def norm_mask(m, size=48):
    h, w = m.shape
    s = size / max(h, w)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    mm = cv2.resize(m.astype(np.uint8) * 255, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((size, size), np.uint8)
    x0 = (size - nw) // 2
    y0 = (size - nh) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = mm
    return canvas.astype(np.float32) / 255.0


def score_mask(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    if d < 1e-6:
        return 0.0
    return float((a * b).sum() / d)


def find_strip(gray):
    """定位版心柱：L 半版左缘 ~ 第一根长竖线。返回 (x0, x1)。"""
    H, W = gray.shape
    raw = (gray <= 150).astype(np.uint8)
    # 竖线：纵向开运算
    v = cv2.morphologyEx(raw, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(H * 0.35))))
    cols = v.sum(axis=0)
    cand = [x for x in range(20, min(W // 3, 500)) if cols[x] > H * 0.35]
    frame = None
    if cand:
        # 取最左的一段（连续线），避免正文内竖线
        groups = []
        cur = [cand[0]]
        for x in cand[1:]:
            if x - cur[-1] <= 2:
                cur.append(x)
            else:
                groups.append(cur); cur = [x]
        groups.append(cur)
        frame = int(np.mean(groups[0]))
    x0 = 12
    if frame is not None and frame > 60:
        x1 = frame - 4
    else:
        x1 = 165
    return x0, min(x1, W - 1)


def segment_cells(strip):
    """水平投影切格；返回 [(y0,y1,mask)]。"""
    ink = (strip <= 150).astype(np.uint8)
    # 去掉版心右侧可能的框线残迹
    proj = ink.sum(axis=1)
    thr = max(2, int(strip.shape[1] * 0.02))
    runs = []
    inr = False
    for i, v in enumerate(proj):
        if v > thr and not inr:
            start = i; inr = True
        elif v <= thr and inr:
            runs.append([start, i]); inr = False
    if inr:
        runs.append([start, len(proj)])
    # 合并小间隙（同一字被笔划分开）
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 4:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    cells = []
    for a, b in merged:
        if b - a < 12:
            continue
        sub = ink[a:b]
        # 竖直投影拆宽格（多字粘连）
        cols = sub.sum(axis=0)
        nz = np.where(cols > 0)[0]
        if len(nz) == 0:
            continue
        colruns = []
        inr2 = False
        for i, v in enumerate(cols):
            if v > 0 and not inr2:
                s2 = i; inr2 = True
            elif v <= 0 and inr2:
                colruns.append([s2, i]); inr2 = False
        if inr2:
            colruns.append([s2, len(cols)])
        # 合并列间隙 <=2
        cm = []
        for x0, x1 in colruns:
            if cm and x0 - cm[-1][1] <= 2:
                cm[-1][1] = x1
            else:
                cm.append([x0, x1])
        h = b - a
        # 若某列块宽 < 0.3h 且不是唯一块，可能是散点 -> 先做整体
        xs = nz.min(), nz.max()
        w = xs[1] - xs[0] + 1
        if w > 1.45 * h and len(cm) >= 2:
            # 多字粘连：按列块拆（只保留宽 > 0.35h 的）
            for x0, x1 in cm:
                if x1 - x0 < 0.30 * h:
                    continue
                m = sub[:, max(0, x0 - 1):x1 + 1]
                ys2, xs2 = np.where(m > 0)
                if len(ys2) < 10:
                    continue
                cells.append((a + int(ys2.min()), a + int(ys2.max()) + 1,
                              m[ys2.min():ys2.max() + 1, xs2.min():xs2.max() + 1]))
        else:
            cells.append((a, b, sub[:, xs[0]:xs[1] + 1]))
    # 按高度过滤异常（标题/污渍）
    hs = [b - a for a, b, _ in cells]
    if hs:
        med = float(np.median(hs))
        cells = [c for c in cells if 0.45 * med <= (c[1] - c[0]) <= 2.2 * med]
    return cells


def recognize(cells, tpl, cands):
    """对 cells 逐一与 cands 模板匹配，返回 [(char, score, cell)]。"""
    out = []
    for (a, b, m) in cells:
        q = norm_mask((m > 0))
        best = (None, -1.0)
        for ch in cands:
            for tm in tpl.get(ch, []):
                s = score_mask(q, tm)
                if s > best[1]:
                    best = (ch, s)
        out.append((best[0], best[1], (a, b, m)))
    return out


def parse_header(cells, tpl):
    """返回 (bu, hua_list, errors)。"""
    recs = recognize(cells, tpl, list(tpl.keys()))
    errors = []
    # 找「部」
    bu_idx = None
    for i, (ch, s, _) in enumerate(recs):
        if ch == "部" and s > 0.55:
            bu_idx = i
            break
    bu = None
    if bu_idx is not None and bu_idx > 0:
        # 部名 = 前一个格
        ch, s, _ = recs[bu_idx - 1]
        if s > 0.45 and ch in RAD214:
            bu = ch
        else:
            # 对部首再匹配一次（限定 RAD214）
            r2 = recognize([recs[bu_idx - 1][2]], tpl, list(RAD214))
            bu = r2[0][0]
            if r2[0][1] < 0.42:
                errors.append("rad_low")
                bu = None
    elif bu_idx is None:
        errors.append("no_bu")
    start = (bu_idx + 1) if bu_idx is not None else 4
    # 画数字段：从 start 起，遇到 畫 收一个字段
    hua = []
    cur = ""
    for ch, s, _ in recs[start:]:
        if ch == "畫" and s > 0.5:
            if cur:
                v = numval(cur)
                if v is not None:
                    hua.append(v)
                else:
                    errors.append("num_bad:" + cur)
                cur = ""
            else:
                errors.append("empty_hua")
            continue
        if ch in NUMS and s > 0.4:
            cur += ch
        else:
            if cur:
                errors.append("num_break:" + cur)
            cur = ""
            break  # 进入葉码区
    if cur:
        errors.append("tail:" + cur)
    return bu, hua, errors


def numval(s):
    """一..二十 / 廿二 / 卅 等。"""
    M = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
         "九": 9, "十": 10, "廿": 20, "卅": 30, "卌": 40, "百": 100}
    if not s:
        return None
    if all(c in M for c in s):
        if len(s) == 1:
            return M[s]
        if len(s) == 2 and s[0] in "廿卅卌" and s[1] in M:
            return M[s[0]] + M[s[1]]
        if len(s) == 2 and s[0] == "十" and s[1] in M:
            return 10 + M[s[1]]
        if len(s) == 2 and s[1] == "十" and s[0] in M:
            return M[s[0]] * 10
        if len(s) == 3 and s[1] == "十":
            return M[s[0]] * 10 + M[s[2]]
    return None


def section_ji(sections, vol, page):
    for v, info in sections.items():
        if v != vol:
            continue
        runs = info["runs"]
        names = ["上", "中", "下"]
        for k, (a, b) in enumerate(runs[:3]):
            if a <= page <= b:
                return info["ji"] + names[k]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", default="01")
    ap.add_argument("--pages", default="body")
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/headers_lead.jsonl"))
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    sections = json.load(open(os.path.join(ROOT, "work/lead/volume_sections.json"),
                             encoding="utf-8"))
    roles = collections.defaultdict(list)
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        roles[r["vol"]].append((r["page"], r["role"]))
    jobs = []
    for vol in args.vols.split(","):
        for page, role in sorted(roles[vol]):
            if args.pages == "body" and role != "body":
                continue
            jobs.append((vol, page))
    tpl = render_templates()
    print("templates", len(tpl))
    fout = open(args.out, "w", encoding="utf-8")
    doc = None
    cur_vol = None
    stats = collections.Counter()
    for vol, page in jobs:
        if vol != cur_vol:
            if doc:
                doc.close()
            doc = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            cur_vol = vol
        pix = doc[page - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        W = img.shape[1]
        gray = img[:, :W // 2]
        x0, x1 = find_strip(gray)
        strip = gray[:, x0:x1]
        cells = segment_cells(strip)
        bu, hua, errors = parse_header(cells, tpl)
        rec = {"page": f"{vol}_{page:04d}", "half": "L", "bu": bu, "hua": hua,
               "ji": section_ji(sections, vol, page), "leaf_no": page - 5,
               "errors": errors, "strip_x": [x0, x1], "n_cells": len(cells),
               "conf": (0.8 if bu and hua else (0.5 if bu or hua else 0.0))}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats["n"] += 1
        if bu:
            stats["bu_ok"] += 1
        if hua:
            stats["hua_ok"] += 1
    fout.close()
    if doc:
        doc.close()
    print(dict(stats))


if __name__ == "__main__":
    main()
