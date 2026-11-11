#!/usr/bin/env python3
"""Lead · 书眉读数 v3（只认「画数」+ 底锚定解析）。

思路（省掉最难的部首识别）：
- 从版心底向上：先按公式对齐 葉码（= 册内页 − 5，数字串已知），吃掉底部 1-3 个格；
- 然后向上交替读 「数字+畫」 字段（1-2 个），直到数字/畫 匹配不上 → 停止；
- 部名/集名不做 OCR：集名由 `volume_sections.json` 给，部由 solver 用累计计数预测后与画数比对。
这样只需识别 11 个数字 + 畫（12 类小字符集），模板匹配可行。

输出（solver 口径，bu=null 由 solver 用 hua-only 模式）：
  {"page","half":"L","ji","bu":null,"hua":[int,...],"leaf_no","conf","errors":[]}
用法：
  .venv/bin/python scripts/lead_header_v3.py --eval-gold       # 20 页真值对账
  .venv/bin/python scripts/lead_header_v3.py --vols 01,02 --out work/lead/headers_v3.jsonl
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
# 可选：本机下载的文楷（若存在）
_wk = os.path.join(ROOT, "data/base/LXGWWenKai-Regular.ttf")
if os.path.exists(_wk) and os.path.getsize(_wk) > 1000:
    FONTS.append(_wk)

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
    """数字 + 畫 的模板（多字体 × 多字号 × 笔画加粗变体）。"""
    global _T
    if _T:
        return _T
    from PIL import Image, ImageDraw, ImageFont
    chars = set(NUM_CH) | {"畫"}
    for ch in chars:
        masks = []
        for size in (64, 78):
            for path in FONTS:
                try:
                    f = ImageFont.truetype(path, size)
                except Exception:
                    continue
                im = Image.new("L", (size * 2, size * 2), 255)
                ImageDraw.Draw(im).text((size // 3, size // 4), ch, font=f, fill=0)
                a = np.array(im)
                m = (a < 140).astype(np.uint8)
                ys, xs = np.where(m)
                if len(ys) < 10:
                    continue
                for dil in (0, 1):
                    mm = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                    if dil:
                        mm = cv2.dilate(mm, np.ones((2, 2), np.uint8), iterations=1)
                    masks.append(_norm(mm))
        if masks:
            _T[ch] = masks
    return _T


def classify(mask):
    """返回 [(score, char)] 降序。"""
    q = _norm((mask > 0).astype(np.uint8))
    out = []
    for ch, ms in _T.items():
        for tm in ms:
            out.append((_score(q, tm), ch))
    out.sort(reverse=True)
    return out


# --------------------------------------------------------------------------- #
# 几何：版心柱定位（复用 seq 的 border/frame 思路 + 局部修正）
# --------------------------------------------------------------------------- #
def border_end(gray, xmax=40):
    dark = (gray[:, :xmax] <= 100)
    cf = dark.mean(axis=0)
    be = 0
    for x in range(xmax):
        if cf[x] > 0.55:
            be = x
    return be


def find_frame(gray, lo=45, hi=200):
    H = gray.shape[0]
    ink = (gray <= 150).astype(np.uint8)
    ink[:, :3] = 0
    cs = ink.sum(axis=0)
    cand = [x for x in range(lo, min(hi, gray.shape[1])) if cs[x] > 0.45 * H]
    groups = []
    for x in cand:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    narrow = [gp for gp in groups if len(gp) <= 6]
    return int(round(sum(narrow[0]) / len(narrow[0]))) if narrow else None


def strip_mask(gray, x0, x1):
    """自适应二值（背景中值相减）+ 去竖长线。"""
    strip = gray[:, x0:x1]
    st = cv2.medianBlur(strip, 3)
    bg = cv2.medianBlur(st, 61)
    ink = ((bg.astype(np.int16) - st.astype(np.int16)) > 45).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, 4] >= 15:
            keep[lab == i] = 1
    vert = cv2.morphologyEx(keep, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 140)))
    # 注意：不要用水平开运算去线——会削掉汉字主横画（五/畫/日…），导致切格破碎。
    # 横线（版心鱼尾/框线）在切格阶段按「厚度<12px」过滤即可。
    return keep & (1 - vert)


def segment_cells(mask):
    rows = mask.sum(axis=1)
    on = rows >= 2
    runs = []
    s = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            runs.append([s, i]); s = None
    if s is not None:
        runs.append([s, len(on)])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= 12:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    cells = []
    for a, b in merged:
        if b - a < 16:
            continue
        sub = mask[a:b]
        cols = sub.sum(axis=0)
        nz = np.where(cols > 0)[0]
        if len(nz) == 0:
            continue
        m = sub[:, nz.min():nz.max() + 1]
        ys, xs = np.where(m > 0)
        cells.append((int(a + ys.min()), int(a + ys.max()) + 1,
                      m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]))
    # 过滤：高宽比合理（数字/畫都是竖排单字，h 40-110）
    out = []
    for a, b, m in cells:
        h, w = b - a, m.shape[1]
        if h < 26 or w < 8:
            continue
        if h <= 125:
            out.append((a, b, m))
            continue
        # 过高格：按行投影再拆分（多字粘连），剔薄线
        sub = mask[a:b]
        proj = sub.sum(axis=1)
        on = proj >= 2
        runs = []
        s0 = None
        for i, v in enumerate(on):
            if v and s0 is None:
                s0 = i
            if not v and s0 is not None:
                runs.append([s0, i]); s0 = None
        if s0 is not None:
            runs.append([s0, len(on)])
        merged = []
        for c0, c1 in runs:
            if merged and c0 - merged[-1][1] <= 10:
                merged[-1][1] = c1
            else:
                merged.append([c0, c1])
        for c0, c1 in merged:
            if c1 - c0 < 26:
                continue
            mm = sub[c0:c1]
            ys, xs = np.where(mm > 0)
            if len(ys) < 30:
                continue
            out.append((a + c0, a + c1, mm[ys.min():ys.max() + 1, xs.min():xs.max() + 1]))
    return out


# --------------------------------------------------------------------------- #
# 解析：底锚定
# --------------------------------------------------------------------------- #
def numval(s):
    if not s:
        return None
    if all(c in NUMV for c in s):
        if len(s) == 1:
            return NUMV[s]
        if len(s) == 2 and s[0] in "廿卅卌" and s[1] in NUMV:
            return NUMV[s[0]] + NUMV[s[1]]
        if len(s) == 2 and s[0] == "十" and s[1] in NUMV:
            return 10 + NUMV[s[1]]
        if len(s) == 2 and s[1] == "十" and s[0] in NUMV:
            return NUMV[s[0]] * 10
        if len(s) == 3 and s[1] == "十":
            return NUMV[s[0]] * 10 + NUMV[s[2]]
    return None


def leaf_digits(leaf_no):
    """葉码 -> 数字序列（按书写顺序）。1..99: 廿二、百五、十二 …"""
    n = leaf_no
    if n <= 0:
        return []
    if n < 10:
        return [list(NUMV.keys())[list(NUMV.values()).index(n)]]
    if n < 20:
        return ["十"] + ([ch for ch, v in NUMV.items() if v == n - 10] if n > 10 else [])
    if n < 100:
        tens = n // 10
        ones = n % 10
        out = [ch for ch, v in NUMV.items() if v == tens * 10] or \
              (["廿"] if tens == 2 else ["卅"] if tens == 3 else ["卌"] if tens == 4 else [])
        if ones:
            out += [ch for ch, v in NUMV.items() if v == ones]
        return out
    # 100+: 百 + ...
    return ["百"] + (leaf_digits(n - 100) if n > 100 else [])


def parse_from_bottom(cells_rec, leaf_no):
    """从底部锚定解析：返回 (hua list, used_cells, errors, detail)。"""
    errors = []
    # cells_rec 从下往上
    rec = list(reversed(cells_rec))
    exp_leaf = list(reversed(leaf_digits(leaf_no)))
    i = 0
    used = 0
    # 1) 对齐 葉码
    for exp_ch in exp_leaf:
        if i >= len(rec):
            errors.append("leaf_short")
            break
        sc, ch = rec[i][0], rec[i][1]
        if ch == exp_ch or sc > 0.55:
            i += 1
            used += 1
        else:
            errors.append(f"leaf_mis:{ch}!={exp_ch}")
            i += 1
            used += 1
            break
    # 2) 画数字段（从下往上：数字*+畫，1-2 组）
    hua_rev = []
    while i < len(rec) and len(hua_rev) < 2:
        # 收集数字直到 畫
        nums = []
        ok = False
        while i < len(rec):
            sc, ch = rec[i][0], rec[i][1]
            if ch == "畫" and sc > 0.30:
                ok = True
                i += 1
                used += 1
                break
            if ch in NUM_CH and sc > 0.34:
                nums.append(ch)
                i += 1
                used += 1
            else:
                break
        if not ok:
            if nums:
                errors.append("no_hua_after:" + "".join(nums))
            break
        v = numval("".join(nums))
        if v is None:
            errors.append("num_bad:" + "".join(nums))
        else:
            hua_rev.append(v)
    hua = list(reversed(hua_rev))
    return hua, used, errors, [r[1] for r in rec[:used]]


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
    x1 = (fr - 4) if (fr and fr > 55) else 95
    mask = strip_mask(gray, x0, x1)
    cells = segment_cells(mask)
    recs = []
    for a, b, m in cells:
        top = classify(m)
        recs.append((top[0][0], top[0][1], a, b))
    hua, used, errors, used_chars = parse_from_bottom(recs, page - 5)
    conf = 0.5
    if hua:
        conf = min(0.95, 0.55 + 0.12 * len(hua))
    if errors:
        conf = max(0.15, conf - 0.15)
    return {"page": f"{vol}_{page:04d}", "half": "L",
            "ji": section_ji(sections, vol, page), "bu": None,
            "hua": hua, "leaf_no": page - 5, "conf": round(conf, 3),
            "errors": errors, "strip_x": [x0, x1], "n_cells": len(cells),
            "cell_chars": used_chars}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", default="01")
    ap.add_argument("--pages", default="body")
    ap.add_argument("--eval-gold", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/headers_v3.jsonl"))
    ap.add_argument("--montage", default=None)
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
        gold = {pg: d for pg, d in g.items()}
    if args.eval_gold:
        jobs = [(p[:2], int(p[3:])) for p in sorted(gold)]
    else:
        jobs = []
        for vol in args.vols.split(","):
            for page, role in sorted(roles[vol]):
                if args.pages == "body" and role != "body":
                    continue
                jobs.append((vol, page))
    print(f"jobs {len(jobs)}")
    import fitz
    mp = json.load(open(os.path.join(ROOT, "work/t2/pdf_map.json"), encoding="utf-8"))
    tpl = templates()
    print("templates", len(tpl), "fonts", len(FONTS))
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
                   "hua": [], "errors": ["exc:" + str(e)[:80]], "cell_chars": []}
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
            print(f"{rec['page']} got {rec['hua']} chars={rec['cell_chars']} | "
                  f"truth {ghua} | {'OK' if ok else 'X'} {rec['errors']}")
    fout.close()
    for d in docs.values():
        d.close()
    print(dict(stats))


if __name__ == "__main__":
    main()
