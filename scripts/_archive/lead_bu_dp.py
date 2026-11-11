#!/usr/bin/env python3
"""Lead · 部界 DP：版心 OCR 部首文本 + 卷内部首顺序单调 → 214 个部首页锚点。

输入：work/lead/hdr_parsed.jsonl（每页 版心 部首/画数 OCR）+ work/seq/volume_radicals.json
输出：work/lead/bu_start_pages_lead.jsonl（214 行，书序）+ qa
"""
import argparse, json, os, sys, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 常见 OCR 混淆（双向）
CONFUS = [set("日曰"), set("口□〇"), set("夂夊"), set("己已巳"), set("彐彑"), set("木朩"),
          set("水氺"), set("火灬"), set("示礻"), set("衣衤"), set("心忄"), set("手扌"),
          set("糸系"), set("辵是"), set("犬大"), set("人亻"), set("刀刂"), set("月肉"),
          set("艸帅艹"), set("金釒"), set("言訁"), set("食飠"), set("馬马"), set("鳥鸟"),
          set("門门"), set("阜阝"), set("邑阝"), set("宀山"), set("疒广"), set("皮血"),
          set("舌日"), set("足疋"), set("米木"), set("羊⺷"), set("雨⻗"), set("頁页")]


def conf(r_text, radical):
    if not r_text:
        return 0.0
    if r_text == radical:
        return 2.0
    for gp in CONFUS:
        if r_text in gp and radical in gp:
            return 0.8
    return -1.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", default=os.path.join(ROOT, "work/lead/hdr_parsed.jsonl"))
    ap.add_argument("--radicals", default=os.path.join(ROOT, "work/seq/volume_radicals.json"))
    ap.add_argument("--roles", default=os.path.join(ROOT, "work/lead/page_roles.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/bu_start_pages_lead.jsonl"))
    ap.add_argument("--qa", default=os.path.join(ROOT, "work/lead/bu_qa_lead.json"))
    args = ap.parse_args()
    obs = {}
    for line in open(args.parsed, encoding="utf-8"):
        r = json.loads(line)
        obs[r["page"]] = r
    roles = collections.defaultdict(set)
    for line in open(args.roles, encoding="utf-8"):
        r = json.loads(line)
        if r["role"] == "body":
            roles[r["vol"]].add(r["page"])
    vr = json.load(open(args.radicals, encoding="utf-8"))
    anchors = []
    qa = {"juan": [], "problems": []}
    for vol in sorted(vr["volumes"]):
        for j in vr["volumes"][vol]["juan"]:
            a, b = j["body_pages"]
            rads = j["radicals"]
            pages = sorted(p for p in roles[vol] if a <= p <= b)
            n = len(pages)
            k = len(rads)
            if n < k:
                qa["problems"].append({"juan": j["juan"], "why": "pages<radicals",
                                       "n": n, "k": k})
                continue
            # emission[i][j] = page pages[j] 属于 rads[i] 的得分
            em = [[conf(obs.get(f"{vol}_{p:04d}", {}).get("bu_text"), rads[i])
                   for p in pages] for i in range(k)]
            # 前缀和
            pre = []
            for i in range(k):
                acc = [0.0]
                for v in em[i]:
                    acc.append(acc[-1] + v)
                pre.append(acc)
            NEG = -1e18
            # dp[i][j] = 前 i 部覆盖前 j 页的最大分（第 i 部止于第 j 页）
            dp = [[NEG] * (n + 1) for _ in range(k + 1)]
            bk = [[-1] * (n + 1) for _ in range(k + 1)]
            dp[0][0] = 0.0
            for i in range(1, k + 1):
                # 至少给前 i-1 部留 i-1 页，当前部至少 1 页
                for jj in range(i, n + 1):
                    best, best_t = NEG, -1
                    for tt in range(i - 1, jj):
                        if dp[i - 1][tt] == NEG:
                            continue
                        sc = dp[i - 1][tt] + (pre[i - 1][jj] - pre[i - 1][tt])
                        if sc > best:
                            best, best_t = sc, tt
                    dp[i][jj] = best
                    bk[i][jj] = best_t
            if dp[k][n] == NEG:
                qa["problems"].append({"juan": j["juan"], "why": "dp-infeasible"})
                continue
            # 回溯边界（每部起始页 index）
            starts = [0] * k
            jj = n
            for i in range(k, 0, -1):
                tt = bk[i][jj]
                starts[i - 1] = tt
                jj = tt
            for i in range(k):
                anchors.append({"vol": vol, "page": pages[starts[i]], "radical": rads[i],
                                "juan": j["juan"],
                                "score": round(dp[k][n], 2)})
            # 逐部一致性
            for i in range(k):
                lo = starts[i]
                hi = starts[i + 1] if i + 1 < k else n
                seg = [obs.get(f"{vol}_{pages[t]:04d}", {}).get("bu_text") for t in range(lo, hi)]
                exact = sum(1 for t in seg if t == rads[i])
                qa["juan"].append({"vol": vol, "juan": j["juan"], "radical": rads[i],
                                   "start_page": pages[starts[i]], "n_pages": hi - lo,
                                   "obs_exact": exact, "obs_n": len(seg),
                                   "obs_sample": seg[:6]})
    json.dump(qa, open(args.qa, "w"), ensure_ascii=False, indent=1)
    with open(args.out, "w", encoding="utf-8") as f:
        for x in anchors:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("anchors", len(anchors), "problems", len(qa["problems"]))
    # 关键校验：05 卷上 部界
    for x in anchors:
        if x["vol"] == "05" and x["juan"] == "辰集上":
            print("05 辰集上", x["radical"], "start", x["page"])
    # 36 卷首部校验
    bad = 0
    for vol in sorted(vr["volumes"]):
        for j in vr["volumes"][vol]["juan"]:
            first = j["radicals"][0]
            got = [x for x in anchors if x["vol"] == vol and x["radical"] == first
                   and x["juan"] == j["juan"]]
            if not got or got[0]["page"] != j["body_pages"][0]:
                bad += 1
                print("首部页异常", vol, j["juan"], first, got[0]["page"] if got else None,
                      "want", j["body_pages"][0])
    print("36 卷首部异常:", bad)


if __name__ == "__main__":
    main()
