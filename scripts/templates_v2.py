#!/usr/bin/env python3
"""A3-1b · 214 部首模板 v2：扉頁逐列取形 + OCR + 期望部首序对齐（修顺序错位）。

流程：
1. 36 卷扉頁（半版列表见 radical_templates.FM）逐半版：按「部」字聚类定位部首列；
2. 部首字 = 部字正上方墨迹（150dpi 定位）；
3. 每卷取到的字形序列（右→左 = 阅读序）→ 与 volume_radicals 的已知部首序列做
   OCR 串 + 编辑距离对齐（OCR 正方向：白底黑字），得到每字形的 radical 身份；
4. 300dpi 取形，归一化 48×48 二值 + 96×96 png，index 记录 page/half/box/size/ocr/conf。
"""
import json, os, sys, warnings, collections
import cv2
import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radical_templates as RT
from header_read import get_ocr, _ocr_input, RAD214

ROOT = RT.ROOT
OUT = os.path.join(ROOT, "work", "seq", "radical_templates")
SIZE = 48


def norm(ink, size=SIZE, pad=4):
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return None
    bb = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = bb.shape
    side = max(h, w) + 2 * pad
    c = np.zeros((side, side), np.uint8)
    c[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = bb
    return (cv2.resize(c, (size, size), interpolation=cv2.INTER_AREA) > 0).astype(np.float32)


def ocr_glyph(ink, ocr, tmp="work/seq/probe/_v2.png"):
    img = (255 - (ink * 255)).astype(np.uint8)
    cv2.imwrite(tmp, _ocr_input(img, target_h=110))
    res = ocr.predict(tmp)[0]
    d = res.json.get("res", {})
    return (d.get("rec_text") or ""), float(d.get("rec_score") or 0.0)


def align(seq_ocr, rads):
    """编辑距离对齐：返回 {seq_idx: rad_char}。"""
    n, m = len(seq_ocr), len(rads)
    GAP = 1.0
    cost = np.zeros((n + 1, m + 1))
    back = np.zeros((n + 1, m + 1), dtype=np.int8)
    for i in range(1, n + 1):
        cost[i, 0] = cost[i - 1, 0] + GAP
        back[i, 0] = 1
    for j in range(1, m + 1):
        cost[0, j] = cost[0, j - 1] + GAP
        back[0, j] = 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            o = seq_ocr[i - 1]
            sub = 0.0 if o == rads[j - 1] else (0.45 if o in RT_CONF.get(rads[j - 1], set()) else 1.1)
            best = cost[i - 1, j - 1] + sub
            bt = 0
            if cost[i - 1, j] + GAP < best:
                best, bt = cost[i - 1, j] + GAP, 1
            if cost[i, j - 1] + GAP < best:
                best, bt = cost[i, j - 1] + GAP, 2
            cost[i, j] = best
            back[i, j] = bt
    out = {}
    i, j = n, m
    while i > 0 and j > 0:
        if back[i, j] == 0:
            out[i - 1] = rads[j - 1]
            i -= 1
            j -= 1
        elif back[i, j] == 1:
            i -= 1
        else:
            j -= 1
    return out


RT_CONF = {
    "糸": {"系", "糹"}, "缶": {"系"}, "癶": {"广", "廾"}, "辵": {"是", "走"},
    "辰": {"是", "衣"}, "皮": {"血"}, "犬": {"大"}, "宀": {"山", "宁"},
    "彡": {"イ", "三"}, "寸": {"山", "才"}, "舌": {"日"}, "示": {"元"},
    "豕": {"身"}, "隹": {"住"}, "疒": {"广"}, "山": {"小"}, "水": {"永", "小"},
    "火": {"大", "灬"}, "玉": {"王"}, "肉": {"内"}, "衣": {"是"}, "行": {"彳"},
    "襾": {"西"}, "見": {"贝"}, "角": {"用"}, "足": {"是", "走"}, "辛": {"立"},
    "長": {"长"}, "門": {"门"}, "韭": {"非"}, "曰": {"日"}, "厶": {"私"},
    "尢": {"尤", "兀"}, "屮": {"中", "山"}, "亠": {"二", "上"}, "丿": {"/", "ノ"},
    "丶": {"、"}, "丨": {"|", "l"}, "一": {"_", "-", "1"},
}


def main():
    vol = json.load(open(os.path.join(ROOT, "work", "seq", "volume_radicals.json"),
                         encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "work", "seq", "probe"), exist_ok=True)
    ocr = get_ocr()
    # 部模板：用 radical_templates 的方法（p5 的部字簇均值）
    bank = []
    index, per_vol_report, missing = [], [], []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        for j in vol["volumes"][v]["juan"]:
            rads = j["radicals"]
            parts = RT.FM[v][j["juan"][-1]]
            glyphs = []   # (page,half,box150, ink150)
            for page_s, half in parts:
                page = int(page_s)
                boxes = RT.extract_half(v, page, half, bank)
                # 累积部字形到模板库（用于小卷回退）
                g150 = RT.render_half(v, page, half, 150)
                comps, cl = RT.clean_comps(g150)
                if comps:
                    clusters, tiles = RT.cluster_comps(comps, cl)
                    clusters.sort(key=len, reverse=True)
                    for grp in clusters[:1]:
                        for k in grp[:3]:
                            bank.append(tiles[k])
                for b in boxes:
                    glyphs.append((page, half, b["radical_box_150"]))
            per_vol_report.append({"juan": j["juan"], "expected": len(rads), "got": len(glyphs)})
            # 取 300dpi 字形 + OCR（正方向）
            inks, ocs, geoms = [], [], []
            for (page, half, box) in glyphs:
                g150 = RT.render_half(v, page, half, 150)
                sub150 = g150[max(0, box[1]):box[3], max(0, box[0]):box[2]]
                ink150 = (sub150 <= 145).astype(np.uint8)
                if ink150.size == 0:
                    inks.append(None); ocs.append(""); geoms.append((page, half, box)); continue
                txt, sc = ocr_glyph(ink150, ocr)
                inks.append(ink150); ocs.append(txt); geoms.append((page, half, box))
            seq = [o[:1] if o else "" for o in ocs]
            assign = align(seq, rads)
            for k, (page, half, box) in enumerate(geoms):
                rad = assign.get(k)
                if rad is None or inks[k] is None:
                    continue
                if inks[k].shape[0] < 12:
                    continue
                ink300 = RT.crop_300(v, page, half, box)
                if ink300 is None:
                    continue
                t = norm(ink300)
                png = cv2.resize((ink300 * 255).astype(np.uint8), (96, 96),
                                 interpolation=cv2.INTER_AREA)
                fn = f"{rad}_u{ord(rad):04x}_{v}_{page:04d}{half}.png"
                cv2.imwrite(os.path.join(OUT, fn), (255 - png))
                index.append({"radical": rad, "vol": v, "juan": j["juan"], "page": page,
                              "half": half, "box150": [int(x) for x in box],
                              "size150": [int(box[2] - box[0]), int(box[3] - box[1])],
                              "size300": [int(ink300.shape[1]), int(ink300.shape[0])],
                              "ocr": ocs[k], "ocr_score": round(sc, 2),
                              "file": fn, "ink_sum48": round(float(t.sum()), 1)})
    # 去重：同 radical 保留 ocr 命中优先、ink 大的
    by = collections.defaultdict(list)
    for t in index:
        by[t["radical"]].append(t)
    final = []
    for rad, ts in by.items():
        ts.sort(key=lambda t: (t["ocr"] != rad, -t["ink_sum48"]))
        final.append(ts[0])
    final.sort(key=lambda t: ord(t["radical"]))
    missing = [r for r in RAD214 if r not in by]
    json.dump({"templates": final, "n": len(final), "missing": missing,
               "per_vol": per_vol_report,
               "method": "扉頁逐列取形（部字聚类定位）+ OCR 正方向识别 + 期望部首序编辑距离对齐；"
                         "300dpi 取形、48×48 归一化"},
              open(os.path.join(OUT, "index_v2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("final templates", len(final), "missing", len(missing), missing)


if __name__ == "__main__":
    main()
