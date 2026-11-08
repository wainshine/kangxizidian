#!/usr/bin/env python3
"""A3-2c · 全书 214 个部首页锚点（版心部名观测 + 卷内单调 DP + entries 位置先验）。

输入：
  work/seq/headers_full_raw.jsonl   逐页版心读数（header_read.py 全量；bu_raw 为 1–2 字）
  work/seq/bu_home_known36.json     36 个卷首部首页（A2b 结构已知，强制锚点）
  work/seq/bu_home_candidates.jsonl 「X部」标签检测候选（加成项，可选）
  work/seq/volume_radicals.json     每卷有序部首 + entries
输出：
  work/seq/bu_start_pages.jsonl     214 锚点（含 margin/来源/置信）
  work/seq/radical_templates/       锚点页切部首自字 → 214 模板 + index.json
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

# 部首别名（OCR 常见混淆 & 刻本体异体）→ 规范形
ALIAS = {
    "亻": "人", "亠": "亠", "冫": "冫", "氵": "水", "扌": "手", "忄": "心",
    "艹": "艸", "衤": "衣", "礻": "示", "辶": "辵", "阝": "阜", "钅": "金",
    "訁": "言", "訁": "言", "飠": "食", "糹": "糸", "糹": "糸", "糸": "糸",
    "\\": "丶", "／": "丿", "|": "丨", "－": "一", "丶": "丶",
}


def norm_bu(v):
    if not v:
        return None
    s = str(v).strip()
    for ch in "部":
        s = s.replace(ch, "")
    s = s.strip()
    if not s:
        return None
    if len(s) > 1:
        s = s[0]
    return ALIAS.get(s, s)


def emis(obs, rad):
    """版心部名 OCR 观测 vs 期望部首 char 的对数似然（经验值）。"""
    if obs is None:
        return -0.35
    if obs == rad:
        return 1.2
    return -1.1


def load_obs():
    obs = {}
    path = os.path.join(OUT, "headers_full_raw.jsonl")
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        key = (r["pdf"], r["page"])
        obs[key] = norm_bu(r.get("bu") or r.get("bu_raw"))
    return obs


def main():
    vol = json.load(open(os.path.join(OUT, "volume_radicals.json"), encoding="utf-8"))
    known = json.load(open(os.path.join(OUT, "bu_home_known36.json"), encoding="utf-8"))
    obs = load_obs()
    label = collections.defaultdict(dict)
    lp = os.path.join(OUT, "bu_home_candidates.jsonl")
    if os.path.exists(lp):
        for line in open(lp, encoding="utf-8"):
            r = json.loads(line)
            v, p = r["vol"], r["page"]
            if p not in label[v] or r["bu_iou"] > label[v][p]["bu_iou"]:
                label[v][p] = r
    # 卷的页区间：content_start（第一部的部首页）→ 下一卷 content_start-1 / 卷末
    starts = []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        for j in vol["volumes"][v]["juan"]:
            info = known[f"{v}_{j['juan']}"]
            starts.append((v, j["juan"], info["content_start_page"]))
    byv = collections.defaultdict(list)
    for k, (v, jn, cs) in enumerate(starts):
        byv[v].append((jn, cs))
    anchors = []
    problems = []
    for v in [f"{i:02d}" for i in range(1, 13)]:
        juan = vol["volumes"][v]["juan"]
        jstarts = byv[v]
        last_page = vol["volumes"][v]["juan"][-1]["body_pages"][1]
        for idx, (jn, cstart) in enumerate(jstarts):
            cend = (jstarts[idx + 1][1] - 1) if idx + 1 < len(jstarts) else last_page
            rads = juan[idx]["radicals"]
            entries = juan[idx]["entries"] / juan[idx]["n_radicals"]
            N = len(rads)
            pages = list(range(cstart, cend + 1))
            P = len(pages)
            # 位置先验：第 k 个部首部首页 ≈ cstart + 累计 entries 比例 * 页数
            cum = np.cumsum([entries] * N)
            exp = [cstart + (cum[k] - entries / 2) / cum[-1] * (P - 1) for k in range(N)]
            sigma = max(6.0, 0.10 * P)
            NE = -1e9
            cost = np.full((N + 1, P + 1), NE)
            back = np.zeros((N + 1, P + 1), dtype=np.int8)
            # 初始化：第 1 个部首锚点固定在 cstart（A2b 已知）
            cost[1, 1] = 0.0
            back[1, 1] = 1
            for j in range(1, N + 1):
                for pp in range(1, P + 1):
                    if j == 1 and pp == 1:
                        continue
                    p = pages[pp - 1]
                    o = obs.get((v, p))
                    e = emis(o, rads[j - 1])
                    if pp > 1 and j == 1:
                        # 保持在第一部
                        val = cost[j, pp - 1] + e
                        back[j, pp] = 0
                        cost[j, pp] = val
                    elif pp > 1:
                        # 保持
                        val = cost[j, pp - 1] + e
                        if val > cost[j, pp]:
                            cost[j, pp] = val
                            back[j, pp] = 0
                        # 从 j-1 推进：page p 是第 j 个部首的部首页（j>=2）
                        if j >= 2:
                            pri = -0.5 * ((p - exp[j - 1]) / sigma) ** 2
                            bonus = 0.0
                            if p in label.get(v, {}):
                                bonus += 1.0
                            val = cost[j - 1, pp - 1] + pri + bonus
                            if val > cost[j, pp]:
                                cost[j, pp] = val
                                back[j, pp] = 1
            if cost[N, P] <= NE / 2:
                problems.append({"vol": v, "juan": jn, "reason": "dp infeasible"})
                continue
            # 回溯找到每个部首的起始页
            pos = []
            j, pp = N, P
            while j >= 1 and pp >= 1:
                if back[j, pp] == 1:
                    pos.append(pages[pp - 1])
                    j -= 1
                    pp -= 1
                else:
                    pp -= 1
            pos.reverse()
            if len(pos) != N:
                problems.append({"vol": v, "juan": jn, "reason": "backtrack", "got": len(pos)})
                continue
            for k in range(N):
                anchors.append({
                    "vol": v, "page": pos[k], "juan": jn, "radical": rads[k],
                    "exp_page": round(float(exp[k]), 1),
                    "offset": round(float(pos[k] - exp[k]), 1),
                    "obs": obs.get((v, pos[k])),
                    "label_score": round(float(label.get(v, {}).get(pos[k], {}).get("bu_iou", 0.0)), 3),
                    "forced": bool(k == 0),
                    "tier": "A" if (k == 0 or (v, pos[k]) in [(x[0], x[1]) for x in []]) else "B",
                })
    # 排序输出
    anchors.sort(key=lambda a: (a["vol"], a["page"]))
    json.dump({"anchors": anchors, "n": len(anchors), "problems": problems},
              open(os.path.join(OUT, "bu_start_pages.jsonl"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("anchors", len(anchors), "problems", problems)
    per = collections.Counter(a["vol"] for a in anchors)
    print("per vol", dict(per))


if __name__ == "__main__":
    main()
