#!/usr/bin/env python3
"""Lead · 书眉读数 v4：滑窗模板匹配（不做切格）+ 畫锚点解析。

动机：v3 切格在「五畫/六畫」这类紧贴双字处失败（字间间隙 5-10px，与 二/三 字内间隙混淆）。
改为：
1. 版心柱内做**灰度归一化**（减去本地背景），
2. 对「数字」和「畫」的模板做**滑窗 matchTemplate**（多字体×多字号），取峰值（NMS），
3. 用「畫」峰做锚点：每个畫正上方 1-2 字高内的数字峰 = 该字段的画数（数字按 y 排序）；
   最下方畫之上的数字串 = 一个字段；若上方还有畫 = 第二个字段。
4. 部名/集名不识别（集名由卷表、部由 solver 预测后与画数比对）。
"""
import argparse, json, os, sys, collections
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_CH = "一二三四五六七八九十廿卅卌百"
NUMV = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
        "九": 9, "十": 10, "廿": 20, "卅": 30, "卌": 40, "百": 100}
FONTS = [os.path.expanduser("~/Library/Fonts/GuanGeKai-Regular.ttf"),
         "/System/Library/Fonts/Supplemental/Songti.ttc"]

_T = {}


def render_templates():
    """{char: [(mask_gray, h, w)]} 多字体×多字号，供 matchTemplate。"""
    from PIL import Image, ImageDraw, ImageFont
    chars = list(NUM_CH) + ["畫"]
    # 版心字高约 70-110px @300dpi：用 60/72/84/96 四档
    for ch in chars:
        arrs = []
        for path in FONTS:
            if not os.path.exists(path):
                continue
            for size in (60, 72, 84, 96):
                try:
                    f = ImageFont.truetype(path, size)
                except Exception:
                    continue
                im = Image.new("L", (size * 2, size * 2), 255)
                ImageDraw.Draw(im).text((size // 4, size // 5), ch, font=f, fill=0,
                                        stroke_width=1)
                a = np.array(im).astype(np.float32)
                ys, xs = np.where(a < 170)
                if len(ys) < 10:
                    continue
                t = a[max(0, ys.min() - 3):ys.max() + 4, max(0, xs.min() - 3):xs.max() + 4]
                arrs.append(t)
        if arrs:
            _T[ch] = arrs
    return _T


def normalize_strip(gray):
    st = cv2.medianBlur(gray, 3).astype(np.float32)
    bg = cv2.medianBlur(gray, 61).astype(np.float32)
    return (bg - st)  # 墨为正


def find_peaks(nz, tpl, thr=0.30):
    res = cv2.matchTemplate(nz, tpl, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= thr)
    peaks = []
    for y, x in zip(ys, xs):
        peaks.append((float(res[y, x]), int(y), int(x), tpl.shape[0], tpl.shape[1]))
    peaks.sort(reverse=True)
    # NMS
    out = []
    for s, y, x, h, w in peaks:
        ok = True
        for s2, y2, x2, h2, w2 in out:
            if abs(y - y2) < 0.55 * max(h, h2) and abs(x - x2) < 0.7 * max(w, w2):
                ok = False
                break
        if ok:
            out.append((s, y, x, h, w))
        if len(out) > 40:
            break
    return out


def parse_hua(peaks_by_char, strip_h):
    """返回 (hua, debug)。peaks_by_char: {char: [(score,y,x,h,w)]}"""
    hua_peaks = sorted(peaks_by_char.get("畫", []), key=lambda p: p[1])  # 从上到下
    # 只保留「上方有数字」的畫；且分布合理
    fields = []
    for s, y, x, h, w in hua_peaks:
        # 该畫上方的数字峰（1-2个）
        cand = []
        for ch in NUM_CH:
            for s2, y2, x2, h2, w2 in peaks_by_char.get(ch, []):
                dy = y - y2
                if -5 <= dy <= 2.4 * h and s2 > 0.30:
                    cand.append((s2, ch, y2, h2))
        if not cand:
            continue
        cand.sort(key=lambda t: t[2])  # 从下往上
        picked = []
        prev_y = y
        for s2, ch, y2, h2 in cand:
            if prev_y - y2 > 1.55 * h:  # 跳太远（属于别的字段/葉码）
                continue
            picked.append((ch, y2, s2))
            prev_y = y2
            if len(picked) >= 3:
                break
        if not picked:
            continue
        # 数字按上→下排列 = 书写顺序（十 在上、二 在下 => 十二）
        picked_sorted = sorted(picked, key=lambda t: t[1])
        s_ = "".join(t[0] for t in picked_sorted)
        v = numval(s_)
        if v is not None:
            fields.append((y, v, s_, round(s, 2)))
    fields.sort()
    return [f[1] for f in fields][:2], fields


def numval(s):
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
        if a == "百" and b in NUMV:
            return 100 + NUMV[b]
    if len(s) == 3 and s[1] == "十":
        return NUMV[s[0]] * 10 + NUMV[s[2]]
    return None


def border_end(gray, xmax=40):
    dark = (gray[:, :xmax] <= 100)
    cf = dark.mean(axis=0)
    be = 0
    for x in range(xmax):
        if cf[x] > 0.55:
            be = x
    return be


def find_frame(gray, lo=45, hi=210):
    H = gray.shape[0]
    ink = (gray <= 150).astype(np.uint8)
    ink[:, :3] = 0
    cs = ink.sum(axis=0)
    cand = [x for x in range(lo, min(hi, gray.shape[1])) if cs[x] > 0.42 * H]
    groups = []
    for x in cand:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    narrow = [gp for gp in groups if len(gp) <= 6]
    return int(round(sum(narrow[0]) / len(narrow[0]))) if narrow else None


def section_ji(sections, vol, page):
    info = sections.get(vol)
    if not info:
        return None
    names = ["上", "中", "下"]
    for k, (a, b) in enumerate(info["runs"][:3]):
        if a <= page <= b:
            return info["ji"] + "集" + names[k]
    return None


def process(vol, page, gray, sections):
    x0 = border_end(gray) + 3
    fr = find_frame(gray)
    x1 = (fr - 4) if (fr and fr > 55) else min(gray.shape[1], 100)
    # 版心上下都有空白/黑区：把条带限制在文本带内（墨量>阈）
    sub = gray[:, x0:x1]
    nz = normalize_strip(sub)
    # 去掉左右 2px（可能含框线残迹）
    nz[:, :2] = 0
    nz[:, -2:] = 0
    peaks = {}
    for ch, tpls in _T.items():
        allp = []
        for tpl in tpls:
            th, tw = tpl.shape
            if th > nz.shape[0] or tw > nz.shape[1]:
                continue
            allp += find_peaks(nz, tpl, thr=0.28)
        # 跨模板 NMS
        allp.sort(reverse=True)
        keep = []
        for p in allp:
            ok = True
            for q in keep:
                if abs(p[1] - q[1]) < 0.5 * max(p[3], q[3]) and abs(p[2] - q[2]) < 0.7 * max(p[4], q[4]):
                    ok = False
                    break
            if ok:
                keep.append(p)
        peaks[ch] = keep[:38]
    hua, fields = parse_hua(peaks, nz.shape[0])
    conf = 0.35
    if hua:
        conf = 0.5 + 0.1 * len(hua)
    return {"page": f"{vol}_{page:04d}", "half": "L",
            "ji": section_ji(sections, vol, page), "bu": None,
            "hua": hua, "leaf_no": page - 5, "conf": round(conf, 2),
            "errors": [] if hua else ["no_hua"],
            "strip_x": [x0, x1], "fields": fields,
            "n_peaks": {k: len(v) for k, v in peaks.items() if v}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", default="01")
    ap.add_argument("--pages", default="body")
    ap.add_argument("--eval-gold", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/headers_v4.jsonl"))
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
        gold = dict(g)
    if args.eval_gold:
        jobs = [(p[:2], int(p[3:])) for p in sorted(gold)]
    else:
        jobs = []
        for vol in args.vols.split(","):
            for page, role in sorted(roles[vol]):
                if args.pages == "body" and role != "body":
                    continue
                jobs.append((vol, page))
    render_templates()
    print(f"jobs {len(jobs)} templates {len(_T)}")
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    docs = {}
    fout = open(args.out, "w", encoding="utf-8")
    stats = collections.Counter()
    cur_vol = None
    for vol, page in jobs:
        if vol != cur_vol:
            if cur_vol and cur_vol in docs:
                docs[cur_vol].close()
            docs[vol] = fitz.open(os.path.join(ROOT, "康熙字典", mp[vol]))
            cur_vol = vol
        pix = docs[vol][page - 1].get_pixmap(dpi=args.dpi, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        gray = img[:, :img.shape[1] // 2]
        try:
            rec = process(vol, page, gray, sections)
        except Exception as e:
            rec = {"page": f"{vol}_{page:04d}", "half": "L", "ji": None, "bu": None,
                   "hua": [], "errors": ["exc:" + str(e)[:80]], "fields": []}
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats["n"] += 1
        if rec.get("hua"):
            stats["hua_ok"] += 1
        if args.eval_gold and rec["page"] in gold:
            gd = gold[rec["page"]].get("L") or {}
            ghua = []
            for h in (gd.get("hua") or []):
                v = numval(str(h).replace("畫", ""))
                if v is not None:
                    ghua.append(v)
            ok = rec["hua"] == ghua
            stats["gold"] += 1
            stats["gold_hua_ok"] += int(ok)
            print(f"{rec['page']} got {rec['hua']} fields={rec['fields']} | truth {ghua} | "
                  f"{'OK' if ok else 'X'} {rec['errors']}")
    fout.close()
    for d in docs.values():
        d.close()
    print(dict(stats))


if __name__ == "__main__":
    main()
