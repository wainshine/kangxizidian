#!/usr/bin/env python3
"""A3-2b · 部首页候选 → 214 锚点对齐（卷内单调 + entries 位置先验 DP）。

输入：work/seq/bu_home_candidates.jsonl（每页 0/1 个「X部」标签命中 + 部首自字候选）
      work/seq/bu_home_known36.json（36 个卷首部首页，A2b 结构已知，强制为锚点）
      work/seq/volume_radicals.json（每卷有序部首清单 + entries）
输出：work/seq/bu_start_pages.jsonl（214 锚点：vol/page/radical/score/margin/…）
      work/seq/radical_templates/（从锚点页切部首自字 → 214 模板 + index.json）
"""
import json, os, collections, warnings
import cv2
import fitz
import numpy as np

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_MAP = json.load(open(os.path.join(ROOT, "work", "t2", "pdf_map.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "work", "seq")
TROOT = os.path.join(OUT, "radical_templates")
SIZE = 48


def render_page_half(pdf, page, half, dpi=300):
    doc = fitz.open(os.path.join(ROOT, "康熙字典", PDF_MAP[pdf]))
    try:
        p = doc[page - 1]
        r = p.rect
        x0 = 0 if half == "L" else r.width / 2
        pix = p.get_pixmap(dpi=dpi, clip=fitz.Rect(x0, 0, x0 + r.width / 2, r.height))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
    finally:
        doc.close()
    return gray


def norm(ink, size=SIZE, pad=4):
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return np.zeros((size, size), np.float32)
    bb = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = bb.shape
    side = max(h, w) + 2 * pad
    c = np.zeros((side, side), np.uint8)
    c[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = bb
    return (cv2.resize(c, (size, size), interpolation=cv2.INTER_AREA) > 0).astype(np.float32)


def main():
    vol = json.load(open(os.path.join(OUT, "volume_radicals.json"), encoding="utf-8"))
    known = json.load(open(os.path.join(OUT, "bu_home_known36.json"), encoding="utf-8"))
    cand = collections.defaultdict(dict)
    for line in open(os.path.join(OUT, "bu_home_candidates.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        v, p = r["vol"], r["page"]
        if p not in cand[v] or r["bu_iou"] > cand[v][p]["bu_iou"]:
            cand[v][p] = r
    # 已知 36 个卷首部首页 → 强制候选（并标注 forced）
    for k, info in known.items():
        v = k.split("_")[0]
        p = info["content_start_page"]
        if p not in cand[v]:
            cand[v][p] = {"vol": v, "page": p, "bu_iou": 0.0,
                          "radical_box": None, "forced": True}
        else:
            cand[v][p]["forced"] = True
    # 每卷逐部首 DP
    anchors = []
    problems = []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        juan = vol["volumes"][v]["juan"]
        rads = [c for j in juan for c in j["radicals"]]
        entries = [e for j in juan for e in [j["entries"] / j["n_radicals"]] * j["n_radicals"]]
        pages_runs = [(j["body_pages"][0], j["body_pages"][1]) for j in juan]
        # 每个部首的期望页位置：卷内按 entries 累计比例
        page_min = pages_runs[0][0]
        page_max = pages_runs[-1][1]
        cum = np.cumsum(entries)
        tot = cum[-1]
        exp_pos = [page_min + (cum[k] - entries[k] / 2) / tot * (page_max - page_min)
                   for k in range(len(rads))]
        cand_pages = sorted(cand[v].keys())
        if len(cand_pages) == 0:
            problems.append({"vol": v, "reason": "no candidates"})
            continue
        # CFG: 给每个 (page) 一个分数；DP 选 N 个单调页对齐 N 部首，位置先验高斯
        ns = len(rads)
        nc = len(cand_pages)
        sigma = 0.12 * (page_max - page_min) + 8
        score = np.full((ns + 1, nc + 1), -1e9)
        back = np.full((ns + 1, nc + 1), -1, dtype=int)
        score[0, 0] = 0
        for k in range(1, ns + 1):
            for j in range(1, nc + 1):
                p = cand_pages[j - 1]
                c = cand[v][p]
                det = (c.get("bu_iou") or 0) * 4.0
                if c.get("forced"):
                    det += 1.0
                pos = -0.5 * ((p - exp_pos[k - 1]) / sigma) ** 2
                # 跳过第 j 个候选
                if score[k, j - 1] > score[k, j]:
                    score[k, j] = score[k, j - 1]
                    back[k, j] = 0
                if score[k - 1, j - 1] > -1e8:
                    val = score[k - 1, j - 1] + det + pos
                    if val > score[k, j]:
                        score[k, j] = val
                        back[k, j] = 1
                # 允许同一页对多个部首？不允许（部首不同页）
            # 边界：k 部首必须用 >= k 个页
        if score[ns, nc] < -1e8:
            problems.append({"vol": v, "reason": "dp infeasible", "nc": nc, "ns": ns})
            continue
        # 回溯
        chosen = []
        k, j = ns, nc
        while k > 0 and j > 0:
            if back[k, j] == 1:
                chosen.append(cand_pages[j - 1])
                k -= 1
                j -= 1
            else:
                j -= 1
        chosen.reverse()
        if len(chosen) != ns:
            problems.append({"vol": v, "reason": "backtrack short", "got": len(chosen), "ns": ns})
            continue
        for k in range(ns):
            p = chosen[k]
            c = cand[v].get(p, {})
            anchors.append({"vol": v, "page": p, "radical": rads[k],
                            "juan": juan_of(juan, rads, k),
                            "score": round(float((c.get("bu_iou") or 0)), 3),
                            "margin": round(float(((c.get("bu_iou") or 0) -
                                                   (score[ns, nc] / ns)) ), 3),
                            "exp_page": round(float(exp_pos[k]), 1),
                            "forced": bool(c.get("forced")),
                            "radical_box": c.get("radical_box")})
    json.dump({"anchors": anchors, "problems": problems},
              open(os.path.join(OUT, "bu_start_pages.jsonl"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("anchors", len(anchors), "problems", problems)
    for a in anchors[:5] + anchors[-5:]:
        print(a)


def juan_of(juan, rads, k):
    acc = 0
    for j in juan:
        acc += j["n_radicals"]
        if k < acc:
            return j["juan"]
    return juan[-1]["juan"]


if __name__ == "__main__":
    main()
