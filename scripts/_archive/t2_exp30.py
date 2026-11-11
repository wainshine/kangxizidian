#!/usr/bin/env python3
"""T2 · §3.0 决定性实验 v2：一部字头专有过滤器的 precision（所有者裁定修正版）

SESSION-HANDOFF §3.0 + 所有者 r9 裁定修正：
  - 范围 = 一部全跨度（01_0006..01_0009，书眉实测一部页码一~四）+ 正常密度页
    04_0030（心部）+ 13_0163（補遺）——只测最难页会把分支推向过度工程（裁定#1）
  - 版框闸：用原墨 ≥300px 竖线段 + page_stats 版框兜底（裁定#3）。
    语义勘定（150dpi，visual 实证）：~814/1053 = 左/右版框缘，~1831-1835 = 右框缘，
    ~940 = 书口折缝阴影（非印刷线，判定时不得当框界用），x<50 / x>W-50 = 页缘黑边
  - 新增结构性闸臂（离线矩阵用，不进评审图标记，盲判不受影响）：
    arm_blank  透印/空白半版切除（inner_frac<0.10 实证：01_0006R=0.061，
               该半版为背面目录透印，全部检出框=伪框）
    arm_title  卷首标题块切除（01_0006L「康熙字典/子集上/一部」九字块 bbox）
    arm_frame  版框闸（跨框缘竖线或越 page_stats 版框外沿 >5px）
  - 五臂矩阵在所有者盲判后离线计算：原五闸 / +版框闸 / 触边只标 / 方形度放宽 /
    +标题臂 / +透印臂

输出：work/t2/exp30_result.json + exp30_sheet1.png（一部 49 框，编号不变）
      + exp30_sheet2.png（04_0030+13_0163，编号 49+）+ 逐页叠加图
"""
import json, os, sys
import numpy as np
import cv2

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from t1_segment import (page_ink, rule_xs, raw_blocks,
                        height_mode)  # 复用切格器的墨提取/界栏/h0 统计

T00 = os.path.join(ROOT, "work", "t00")
T1 = os.path.join(ROOT, "work", "t1")
T2 = os.path.join(ROOT, "work", "t2")

PAGES = ["01_0006", "01_0007", "01_0008", "01_0009", "04_0030", "13_0163"]
SHEET1_PAGES = ("01_",)   # sheet1 = 一部
SPLIT_X = 950
DPI = 150
GOLD = json.load(open(os.path.join(ROOT, "data", "gold-certified", "gold50.json")))
# 卷首标题块（01_0006L「康熙字典/子集上/一部」九字，zoom 实测）
TITLE_ZONES = {"01_0006": ("L", [545, 350, 800, 735])}


def page_meta(stem):
    """h0 + page_stats 版框"""
    for line in open(os.path.join(T00, "page_stats.jsonl")):
        d = json.loads(line)
        if d.get("file") == stem + ".png":
            return d.get("h0"), [h.get("frame") for h in d.get("halves", [])]
    return None, []


def frame_segments(gray):
    """原墨 ≥300px 竖线段（版框缘候选；语义见 docstring）"""
    raw = (gray <= 150).astype(np.uint8)
    v = cv2.morphologyEx(raw, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, 200)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(v, connectivity=8)
    segs = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if h >= 300:
            segs.append({"x": int(x), "y0": int(y), "h": int(h)})
    segs.sort(key=lambda s: s["x"])
    return segs


def half_kind(gray):
    """透印/空白半版判定：版框内区（去边 120px）墨占比 <0.10 = 透印/空白
    （实证：01_0006R=0.061 为目录透印；正常半版 0.148-0.194）"""
    H, W = gray.shape
    kinds = {}
    for name, sl in (("L", slice(0, SPLIT_X)), ("R", slice(SPLIT_X, None))):
        ink = (gray[:, sl] <= 150)
        inner = ink[120:-120, 120:-120]
        kinds[name] = "透印/空白" if inner.mean() < 0.10 else "content"
    return kinds


def gold_boxes_for(stem):
    return [g["box"] for g in GOLD["boxes"] if g["page"] == stem]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua else 0.0


def main():
    gold_map = {s: gold_boxes_for(s) for s in PAGES}
    records, page_infos = [], {}
    idx = 0
    for stem in PAGES:
        b = json.load(open(os.path.join(T1, "orig_boxes", stem + ".json")))
        gray = cv2.imread(os.path.join(T00, "pages", stem + ".png"), cv2.IMREAD_GRAYSCALE)
        ink = page_ink(gray)
        rules = rule_xs(ink)  # 恒空（残墨无长竖线，勘误见 PROBE §8）——保留以记录
        h0, frames_ps = page_meta(stem)
        h0 = h0 or height_mode(raw_blocks(ink)) or 41
        thr_h = 1.5 * h0
        segs = frame_segments(gray)
        kinds = half_kind(gray)
        tzone = TITLE_ZONES.get(stem)
        # 版框闸用线 = ≥300px 段中排除页缘（x<50 / x>W-50）
        Hh, Ww = gray.shape
        gate_xs = [s["x"] for s in segs if 50 < s["x"] < Ww - 50]
        page_infos[stem] = {"h0": h0, "frames_page_stats": frames_ps,
                            "frame_segments": segs, "half_kind": kinds,
                            "rules_residual": rules, "half_inner_note":
                            "gate_xs 排除页缘；书口折缝~940 无≥300px段、不进闸"}
        for bi, (box, ef) in enumerate(zip(b["boxes"], b["edge_flags"])):
            x0, y0, x1, y1 = box
            w, hh = x1 - x0, y1 - y0
            ar = w / max(1, hh)
            half = "L" if (x0 + x1) / 2 < SPLIT_X else "R"
            ghit = max((iou(box, g) for g in gold_map[stem]), default=0.0)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            # 结构性闸臂（不在五闸内，供离线矩阵）
            blank = kinds[half] != "content"
            frame_kill = any(x0 < gx < x1 for gx in gate_xs)
            if not frame_kill and frames_ps:
                fr = frames_ps[0 if half == "L" else 1]
                if fr:
                    frame_kill = (x0 < fr[0] - 5 or x1 > fr[2] + 5)
            title_kill = bool(tzone and tzone[0] == half and
                              tzone[1][0] <= cx <= tzone[1][2] and
                              tzone[1][1] <= cy <= tzone[1][3])
            rec = {"id": idx, "page": stem, "half": half, "src_idx": bi,
                   "box": box, "w": int(w), "h": int(hh), "ar": round(float(ar), 2),
                   "edge_flag": bool(ef.get("edge_flag")), "blobs": ef.get("blobs"),
                   "edge_frac": ef.get("edge_frac"), "src": ef.get("src", "main"),
                   "gold_iou": round(float(ghit), 3), "h0": h0,
                   "arm_blank": blank, "arm_frame": frame_kill,
                   "arm_title": title_kill}
            why = []
            if hh < thr_h:
                why.append(f"h<{thr_h:.0f}")
            crossing = [r for r in rules if x0 < r < x1]
            if crossing:
                why.append(f"跨栏x{crossing}")
            if ef.get("edge_flag"):
                why.append(f"触边{ef.get('edge_frac')}")
            if ef.get("blobs") != 1:
                why.append(f"墨团{ef.get('blobs')}")
            if not (0.7 <= ar <= 1.4):
                why.append(f"方形度{ar:.2f}")
            rec["pass"] = not why
            rec["kill"] = why
            records.append(rec)
            idx += 1

    survivors = [r for r in records if r["pass"]]
    result = {
        "experiment": "SESSION-HANDOFF §3.0 决定性实验 v2（r9 裁定修正：补正常密度页+版框闸+结构臂）",
        "dpi": DPI, "pages": PAGES,
        "scope_note": "01_0006..09=一部（书眉页码一~四）；04_0030=心部正文；13_0163=補遺。"
                      "01_0006R=目录透印半版（inner_frac 0.061<0.10）",
        "page_meta": page_infos,
        "title_zone": TITLE_ZONES,
        "arms_doc": "arm_blank=透印/空白半版(inner_frac<0.10); arm_frame=跨框缘线或越"
                    "page_stats版框5px; arm_title=标题块内。五臂矩阵于盲判后离线计算",
        "n_raw": len(records), "n_pass": len(survivors),
        "boxes": records,
        "gold_overlap_ids": [r["id"] for r in records if r["gold_iou"] > 0.5],
    }
    os.makedirs(T2, exist_ok=True)
    json.dump(result, open(os.path.join(T2, "exp30_result.json"), "w"),
              ensure_ascii=False, indent=1)

    # ---- 评审图（两张）：3x 裁剪，阅读序 = 页序→右版先→列右→左→上→下 ----
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 26)
    for part, pred in ((1, lambda r: r["page"].startswith(SHEET1_PAGES)),
                       (2, lambda r: not r["page"].startswith(SHEET1_PAGES))):
        recs = [r for r in records if pred(r)]
        if not recs:
            continue
        recs = sorted(recs, key=lambda r: (r["page"], 0 if r["half"] == "R" else 1,
                                           -r["box"][0], r["box"][1]))
        cells = []
        for r in recs:
            stem, (x0, y0, x1, y1) = r["page"], r["box"]
            g = cv2.imread(os.path.join(T00, "pages", stem + ".png"), cv2.IMREAD_GRAYSCALE)
            Hh, Ww = g.shape
            m = 18
            crop = g[max(0, y0-m):min(Hh, y1+m), max(0, x0-m):min(Ww, x1+m)]
            crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            cells.append((r, crop))
        CW = max(c.shape[1] for _, c in cells) + 16
        CH = max(c.shape[0] for _, c in cells) + 46
        COLS = 5
        rows = (len(cells) + COLS - 1) // COLS
        sheet = np.full((rows*CH+20, COLS*CW+20, 3), 235, dtype=np.uint8)
        for i, (r, c) in enumerate(cells):
            cx, cy = (i % COLS)*CW+8, (i // COLS)*CH+8
            arr = np.full((CH-40, CW-16, 3), 255, dtype=np.uint8)
            hh, ww = c.shape[0], c.shape[1]
            arr[:hh, :ww, 0] = arr[:hh, :ww, 1] = arr[:hh, :ww, 2] = c
            bx0, by0 = (r["box"][0]-max(0, r["box"][0]-18))*3, (r["box"][1]-max(0, r["box"][1]-18))*3
            color = (0, 160, 0) if r["pass"] else (200, 0, 0)
            cv2.rectangle(arr, (int(bx0), int(by0)),
                          (int(bx0+(r["box"][2]-r["box"][0])*3), int(by0+(r["box"][3]-r["box"][1])*3)),
                          color, 2)
            sheet[cy+34:cy+34+arr.shape[0], cx:cx+arr.shape[1]] = arr
        simg = Image.fromarray(sheet)
        dr = ImageDraw.Draw(simg)
        for i, (r, c) in enumerate(cells):
            cx, cy = (i % COLS)*CW+8, (i // COLS)*CH+8
            tag = f"#{r['id']} {r['page'][-4:]}{r['half']} {r['w']}x{r['h']}"
            if r["gold_iou"] > 0.5:
                tag += " ★金标"
            mark = "PASS" if r["pass"] else "✗" + ",".join(r["kill"])
            my = cy + 34 + min(c.shape[0], CH-46) + 2
            dr.text((cx, cy+2), tag, fill=(0, 0, 0), font=font)
            dr.text((cx, my), mark[:24],
                    fill=(0, 120, 0) if r["pass"] else (180, 0, 0), font=font)
        out = os.path.join(T2, f"exp30_sheet{part}.png")
        cv2.imwrite(out, np.array(simg))
        print(f"sheet{part}: {len(cells)} cells -> {out}")

    # ---- 叠加图 ----
    for stem in PAGES:
        g = cv2.imread(os.path.join(T00, "pages", stem + ".png"), cv2.IMREAD_GRAYSCALE)
        vis = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        for r in records:
            if r["page"] != stem:
                continue
            x0, y0, x1, y1 = r["box"]
            color = (0, 180, 0) if r["pass"] else (0, 0, 220)
            cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
            cv2.putText(vis, str(r["id"]), (x0, max(12, y0-4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        cv2.imwrite(os.path.join(T2, f"exp30_overlay_{stem}.png"), vis)

    print(f"raw={len(records)} pass={len(survivors)}")
    for r in records:
        if not r["pass"]:
            continue
        print(f"  PASS #{r['id']:3d} {r['page']} {r['half']} [{r['box']}] "
              f"{r['w']}x{r['h']} ar={r['ar']} {r['src']:4s} gold={r['gold_iou']:.2f} "
              f"arms: blank={r['arm_blank']} frame={r['arm_frame']} title={r['arm_title']}")


if __name__ == "__main__":
    main()
