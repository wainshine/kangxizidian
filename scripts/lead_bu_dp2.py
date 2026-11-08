#!/usr/bin/env python3
"""Lead · 部界 DP v2：seq 逐页版心观测（bu_text + hua + hua_drop）→ 214 部首页。

得分（段 = 一个部）：
  + 2.0   bu_text == radical
  + 0.6   bu_text 与 radical 是常见 OCR 混淆
  - 1.5   bu_text 是另一个已知部首
   0.0   bu_text 缺失
  + 2.0   段起始页 hua_drop（画数骤降 = 部界先验）
  + 1.0   段首页首个 hua 值小（<=4，每部从小画数开始）
  - 0.8   段首页首个 hua 值大（>=7）
  - 0.4   段内相邻页 hua 明显回落
"""
import argparse, json, os, sys, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFUS = [set("日曰"), set("口□〇囗"), set("土士王"), set("夂夊"), set("己已巳"), set("彐彑"),
          set("木朩"), set("水氺"), set("火灬"), set("心忄"), set("手扌"), set("糸系"),
          set("辵是"), set("犬大"), set("人亻"), set("月肉"), set("艸帅艹"), set("金釒"),
          set("言訁"), set("食飠"), set("馬马"), set("鳥鸟"), set("門门"), set("阜阝"),
          set("邑阝"), set("宀山「"), set("疒广"), set("皮血"), set("舌日"), set("足疋"),
          set("雨⻗"), set("頁页"), set("見角"), set("玉玄王"), set("子孑")]
RAD_SET = set("一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子"
              "宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳"
              "毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸"
              "缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰"
              "辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍"
              "黑黹黽鼎鼓鼠鼻齊齒龍龜龠")


def bu_score(t, radical):
    if not t:
        return 0.0
    if t == radical:
        return 2.0
    for gp in CONFUS:
        if t in gp and radical in gp:
            return 0.6
    if t in RAD_SET:
        return -1.5
    return -0.3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs", default=os.path.join(ROOT, "work/seq/hdr_page_obs.jsonl"))
    ap.add_argument("--radicals", default=os.path.join(ROOT, "work/seq/volume_radicals.json"))
    ap.add_argument("--roles", default=os.path.join(ROOT, "work/lead/page_roles.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead2.jsonl"))
    ap.add_argument("--qa", default=os.path.join(ROOT, "work/lead/bu_qa_lead2.json"))
    args = ap.parse_args()
    obs = {}
    for line in open(args.obs, encoding="utf-8"):
        r = json.loads(line)
        obs[r["page"]] = r
    roles = collections.defaultdict(set)
    for line in open(args.roles, encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body":
            roles[r["vol"]].add(r["page"])
    vr = json.load(open(args.radicals, encoding="utf-8"))
    # 每部 entries（正典）
    by_rad = collections.Counter()
    for line in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8"):
        e = json.loads(line)
        by_rad[e["rad"]] += 1
    anchors, qa = [], {"juan": [], "problems": []}
    for vol in sorted(vr["volumes"]):
        for j in vr["volumes"][vol]["juan"]:
            a, b = j["body_pages"]
            rads = j["radicals"]; pages = sorted(p for p in roles[vol] if a <= p <= b)
            n = len(pages); k = len(rads)
            if n < k:
                qa["problems"].append({"juan": j["juan"], "why": "pages<radicals"}); continue
            P = [f"{vol}_{p:04d}" for p in pages]
            obs_bu = [obs.get(p, {}).get("bu_text") for p in P]
            hua = [obs.get(p, {}).get("hua") or [] for p in P]
            drop = [bool(obs.get(p, {}).get("hua_drop")) for p in P]
            # 页级基础分
            em = [[bu_score(obs_bu[t], rads[i]) for t in range(n)] for i in range(k)]
            # 段起始页加分（只跟页有关）
            start_bonus = []
            for t in range(n):
                sc = 2.0 if (t > 0 and drop[t]) else 0.0
                first = hua[t][0] if hua[t] else None
                if first is not None:
                    sc += 1.0 if first <= 4 else (-0.8 if first >= 7 else 0.0)
                start_bonus.append(sc)
            # 段内相邻 hua 回落罚
            def seg_pen(lo, hi):
                pen = 0.0
                prev = None
                for t in range(lo, hi):
                    h = hua[t]
                    if not h:
                        continue
                    if prev is not None and h[0] < prev - 1:
                        pen -= 0.4
                    prev = h[-1]
                return pen
            # 前缀和
            pre = []
            for i in range(k):
                acc = [0.0]
                for v in em[i]:
                    acc.append(acc[-1] + v)
                pre.append(acc)
            # 每部页数约束：密度 3-25 条/页（正典全局 12.95）
            minlen = [max(1, (by_rad.get(r, 0) + 24) // 25) for r in rads]
            maxlen = [max(1, (by_rad.get(r, 0) + 2) // 3 + 1) for r in rads]
            NEG = -1e18
            dp = [[NEG] * (n + 1) for _ in range(k + 1)]
            bk = [[-1] * (n + 1) for _ in range(k + 1)]
            dp[0][0] = 0.0
            for i in range(1, k + 1):
                for jj in range(i, n + 1):
                    best, best_t = NEG, -1
                    for tt in range(i - 1, jj):
                        ln = jj - tt
                        if ln < minlen[i - 1] or ln > maxlen[i - 1]:
                            continue
                        if dp[i - 1][tt] == NEG:
                            continue
                        sc = (dp[i - 1][tt] + (pre[i - 1][jj] - pre[i - 1][tt])
                              + start_bonus[tt] + seg_pen(tt, jj))
                        if sc > best:
                            best, best_t = sc, tt
                    dp[i][jj] = best; bk[i][jj] = best_t
            starts = [0] * k
            jj = n
            for i in range(k, 0, -1):
                tt = bk[i][jj]
                starts[i - 1] = tt; jj = tt
            for i in range(k):
                anchors.append({"vol": vol, "page": pages[starts[i]], "radical": rads[i],
                                "juan": j["juan"], "score": round(dp[k][n], 2)})
                lo = starts[i]; hi = starts[i + 1] if i + 1 < k else n
                seg = [obs_bu[t] for t in range(lo, hi)]
                qa["juan"].append({"vol": vol, "juan": j["juan"], "radical": rads[i],
                                   "start_page": pages[lo], "n_pages": hi - lo,
                                   "obs_exact": sum(1 for t in seg if t == rads[i]),
                                   "obs_n": len(seg),
                                   "hua_first": (hua[lo][0] if hua[lo] else None)})
    json.dump(qa, open(args.qa, "w"), ensure_ascii=False, indent=1)
    with open(args.out, "w", encoding="utf-8") as f:
        for x in anchors:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("anchors", len(anchors), "problems", len(qa["problems"]))
    for x in anchors:
        if x["vol"] == "05" and x["juan"] == "辰集上":
            print("05 辰集上", x["radical"], "start", x["page"])
    # owner 校验
    g = json.load(open(os.path.join(ROOT, "work/t2/margin_labels_full.json"), encoding="utf-8"))["pages"]
    ok = tot = 0; bad = []
    byvol = collections.defaultdict(list)
    for x in anchors:
        byvol[x["vol"]].append(x)
    for name, t in g.items():
        L = t.get("L") or {}
        bu = L.get("bu")
        if not bu:
            continue
        want = bu.rstrip("部")
        if want not in RAD_SET:
            continue
        vol = name[:2]; pg = int(name[3:])
        rs = sorted(byvol[vol], key=lambda r: r["page"])
        pred = None
        for r in rs:
            if r["page"] <= pg:
                pred = r["radical"]
        tot += 1
        if pred == want:
            ok += 1
        else:
            bad.append((name, want, pred))
    print(f"owner 部名校验: {ok}/{tot}", "bad:", bad)


if __name__ == "__main__":
    main()
