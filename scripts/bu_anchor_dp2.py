#!/usr/bin/env python3
"""A3-2d · 214 部首页锚点（v2：混淆感知 emission + 标签检测加成 + entries 位置先验 DP）。"""
import json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "work", "seq")

# 版心部名 OCR 的实测混淆对（来自 A2 全量 raw vs 当前分段的一致性统计）
CONF = {
    "糸": {"系", "糹"}, "缶": {"系", "缶"}, "癶": {"广", "廾"}, "辵": {"是", "走"},
    "辰": {"是", "衣"}, "皮": {"血"}, "犬": {"大"}, "宀": {"山", "宁"},
    "彡": {"イ", "三"}, "寸": {"山", "才"}, "舌": {"日"}, "示": {"元"},
    "豕": {"身", "豕"}, "隹": {"住"}, "疒": {"广"}, "山": {"小", "宀"},
    "水": {"永", "小"}, "火": {"大", "灬"}, "玉": {"王"}, "肉": {"内"},
    "衣": {"是"}, "行": {"彳"}, "襾": {"西"}, "見": {"贝"}, "角": {"用"},
    "足": {"是", "走"}, "辛": {"立"}, "采": {"釆"}, "里": {"里"},
    "長": {"长"}, "門": {"门"}, "飞": {"飞"}, "韭": {"非"},
}


def norm_bu(v):
    if not v:
        return None
    s = str(v).replace("部", "").strip()
    return s[0] if s else None


def emis(obs, rad):
    if obs is None:
        return -0.30
    if obs == rad:
        return 1.25
    if obs in CONF.get(rad, ()):
        return 0.22
    return -0.95


def main():
    vol = json.load(open(os.path.join(OUT, "volume_radicals.json"), encoding="utf-8"))
    known = json.load(open(os.path.join(OUT, "bu_home_known36.json"), encoding="utf-8"))
    obs = {}
    for line in open(os.path.join(OUT, "headers_full_raw.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        obs[(r["pdf"], r["page"])] = norm_bu(r.get("bu") or r.get("bu_raw"))
    label = collections.defaultdict(dict)
    for line in open(os.path.join(OUT, "bu_home_candidates.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        v, p = r["vol"], r["page"]
        if p not in label[v] or r["bu_iou"] > label[v][p]["bu_iou"]:
            label[v][p] = r
    anchors, problems = [], []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        juan = vol["volumes"][v]["juan"]
        arr = [known[f"{v}_{j['juan']}"] for j in juan]
        last_page = juan[-1]["body_pages"][1]
        for idx, j in enumerate(juan):
            cstart = arr[idx]["content_start_page"]
            cend = (arr[idx + 1]["content_start_page"] - 1) if idx + 1 < len(arr) else last_page
            rads = j["radicals"]
            N = len(rads)
            width = cend - cstart + 1
            pages = list(range(cstart, cend + 1))
            per = j["entries"] / N
            cum = [per * (k + 1) for k in range(N)]
            exp = [cstart + (cum[k] - per / 2) / cum[-1] * (width - 1) for k in range(N)]
            sigma = max(5.0, 0.085 * width)
            NE = -1e9
            cost = [[NE] * (width + 1) for _ in range(N + 1)]
            back = [[0] * (width + 1) for _ in range(N + 1)]
            cost[1][1] = 0.0
            back[1][1] = 1
            for jj in range(1, N + 1):
                for pp in range(1, width + 1):
                    if jj == 1 and pp == 1:
                        continue
                    p = pages[pp - 1]
                    o = obs.get((v, p))
                    e = emis(o, rads[jj - 1])
                    if jj >= 2:
                        # 边界页版心部名常印 R 半版（= 上一部）：允许滞后一部的观测
                        e = max(e, emis(o, rads[jj - 2]) - 0.35)
                    best, bt = NE, 0
                    if jj == 1:
                        if cost[1][pp - 1] > NE / 2:
                            cand = cost[1][pp - 1] + e
                            if cand > best:
                                best, bt = cand, 0
                    else:
                        if cost[jj][pp - 1] > NE / 2:
                            cand = cost[jj][pp - 1] + e
                            if cand > best:
                                best, bt = cand, 0
                        if cost[jj - 1][pp - 1] > NE / 2:
                            pri = -0.5 * ((p - exp[jj - 1]) / sigma) ** 2
                            bonus = 0.0
                            lab = label.get(v, {}).get(p)
                            if lab:
                                bonus += 0.9 * min(1.0, max(0.0, (lab["bu_iou"] - 0.30) / 0.45))
                            cand = cost[jj - 1][pp - 1] + pri + bonus
                            if cand > best:
                                best, bt = cand, 1
                    cost[jj][pp] = best
                    back[jj][pp] = bt
            if cost[N][width] <= NE / 2:
                problems.append({"vol": v, "juan": j["juan"], "reason": "infeasible"})
                continue
            pos = []
            jj, pp = N, width
            while jj >= 1 and pp >= 1:
                if back[jj][pp] == 1:
                    pos.append(pages[pp - 1])
                    jj -= 1
                    pp -= 1
                else:
                    pp -= 1
            pos.reverse()
            if len(pos) != N:
                problems.append({"vol": v, "juan": j["juan"], "reason": "backtrack",
                                 "got": len(pos)})
                continue
            total_score = cost[N][width]
            for k in range(N):
                p = pos[k]
                lab = label.get(v, {}).get(p)
                anchors.append({
                    "vol": v, "page": p, "juan": j["juan"], "radical": rads[k],
                    "exp_page": round(exp[k], 1), "offset": round(p - exp[k], 1),
                    "obs": obs.get((v, p)),
                    "obs_match": bool(obs.get((v, p)) == rads[k]),
                    "label_score": round(float(lab["bu_iou"]) if lab else 0.0, 3),
                    "forced": bool(k == 0),
                    "conf": "A" if (k == 0 or (lab and lab["bu_iou"] >= 0.42) or
                                    obs.get((v, p)) == rads[k]) else "B",
                })
    anchors.sort(key=lambda a: (a["vol"], a["page"]))
    json.dump({"anchors": anchors, "n": len(anchors), "problems": problems},
              open(os.path.join(OUT, "bu_start_pages_seq.jsonl"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    c = collections.Counter(a["conf"] for a in anchors)
    print("anchors", len(anchors), "problems", problems, "tiers", dict(c))
    # 自洽性：obs 精确匹配率
    exact = sum(1 for a in anchors if a["obs_match"])
    print(f"anchor obs exact match {exact}/{len(anchors)} = {exact/len(anchors):.1%}")


if __name__ == "__main__":
    main()
