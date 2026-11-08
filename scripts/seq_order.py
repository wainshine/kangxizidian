#!/usr/bin/env python3
"""A1 · 正典阅读序 + (部首, 部外笔画) 组表（正式版）。

口径（docs/TAKEOVER.md §2.A/B，docs/CANONICAL-ORDER.md）：
- 正集 42,302 条（path 不以【補遺】/【備考】开头）；補遺 1,769 / 備考 4,637 为独立序列
  （两者 kKangXi 不索引其版面；補遺/備考按数据集序，理由见文档）。
- 正典序 = (部首, 部外笔画) 组序，组内按 Unihan kKangXi (page, position) 升序，
  同位置平局用数据集 pos 作 tie-break（保留重出行独立槽位）。
- 部外笔画 = 数据集 stroke_total − 部首笔画。**数据集笔划口径实测**：其 stroke 字段
  = 部首全形笔画 + 部外笔画（例如「茶」stroke 9 = 艸6 + 余3；「汀」stroke 5 = 水4 + 丁1），
  所以该减法即刻本版心画数。部首笔画用 214 部首笔画表（=康熙字典部首表分画组）。
- 离群清洗：kKangXi 页落在本组页中位数 ±6 以外的条目（多为 kKangXi 索引近似/虚拟位置
  造成的错页），组内位置按数据集序插值；清洗动作全部落盘 outliers.json。
- kKangXi 位置语义（UAX #38）：位置 = 10×阅读序秩 + 标志位；末位 0 = 该版实际条目，
  末位 1 = 「未见于该版、为排序指派的虚拟位置」（与 kDaeJaweon 同文档口径）。
  → 虚拟位置条目照常入序（多数是异体/简体形），不参与离群清洗判据的页中位数以外扰动。

产出（全部可复算）：
  work/seq/canonical.jsonl   正集 42,302 行 {ci, char, rad, stroke_total, bu_strokes, gi,
                              kx, kpos, mt_pos, mt_i, path, outlier}
  work/seq/groups.json       正集 3,5xx 组 [{gi, rad, rad_i, bu_strokes, start, end, size}]
  work/seq/buqi.jsonl        補遺 1,769 行（数据集序）
  work/seq/beikao.jsonl      備考 4,637 行（数据集序）
  work/seq/outliers.json     离群条目与处理动作
  work/seq/seqorder_stats.json 全部统计数字
"""
import json
import os
import re
import statistics
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "work", "seq")
UNIHAN = os.path.join(ROOT, "data", "unihan", "Unihan_DictionaryIndices.txt")
SEQ = os.path.join(ROOT, "work", "t2", "entry_sequence.jsonl")

RAD214 = ("一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕"
          "大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰"
          "月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢"
          "石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言"
          "谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬"
          "骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠")

# 康熙字典 214 部首分画组（部首表原书分组；radical number range -> stroke count）
RAD_RANGES = [(1, 6, 1), (7, 29, 2), (30, 60, 3), (61, 94, 4), (95, 117, 5),
              (118, 146, 6), (147, 166, 7), (167, 175, 8), (176, 186, 9),
              (187, 194, 10), (195, 200, 11), (201, 204, 12), (205, 208, 13),
              (209, 210, 14), (211, 211, 15), (212, 213, 16), (214, 214, 17)]


def radical_strokes():
    tbl = {}
    for a, b, s in RAD_RANGES:
        for rn in range(a, b + 1):
            tbl[RAD214[rn - 1]] = s
    assert len(tbl) == 214
    return tbl


def load_kx():
    pat = re.compile(r"^U\+([0-9A-F]+)\tkKangXi\t(.+)$")
    val = re.compile(r"^(\d{4})\.(\d{3})$")
    kx = {}
    multi = {}
    for line in open(UNIHAN, encoding="utf-8"):
        m = pat.match(line.rstrip("\n"))
        if not m:
            continue
        ch = chr(int(m.group(1), 16))
        vals = [tuple(map(int, v.split("."))) for v in m.group(2).split()
                if val.match(v)]
        if len(vals) > 1:
            multi[ch] = vals
        if vals:
            kx[ch] = vals[0]
    return kx, multi


def is_zheng(e):
    p = e["path"]
    return not (p.startswith("【補遺】") or p.startswith("【備考】"))


def main():
    os.makedirs(OUT, exist_ok=True)
    kx, multi = load_kx()
    rs = radical_strokes()
    rad_i = {c: i for i, c in enumerate(RAD214)}
    seq = [json.loads(l) for l in open(SEQ, encoding="utf-8")]
    zheng = [e for e in seq if is_zheng(e)]
    buqi = [e for e in seq if e["path"].startswith("【補遺】")]
    beikao = [e for e in seq if e["path"].startswith("【備考】")]
    assert (len(zheng), len(buqi), len(beikao)) == (42302, 1769, 4637), \
        (len(zheng), len(buqi), len(beikao))

    for e in zheng:
        e["bu"] = e["stroke"] - rs[e["rad"]]
        e["gi_key"] = (rad_i[e["rad"]], e["bu"])
        e["kx_multi"] = multi.get(e["char"])
        e["kx"] = kx.get(e["char"])

    for e in zheng:
        if e["char"] in multi:
            e["kx"] = None      # 多值条目：稍后按组页中位数选位置

    by_group = collections.defaultdict(list)
    for e in zheng:
        by_group[e["gi_key"]].append(e)

    # 多值 kKangXi（UAX#38 允许多个位置）：选与组页中位数最近的候选位置
    n_multi_used = 0
    for gkey, es in by_group.items():
        pages = [e["kx"][0] for e in es if e["kx"]]
        med = statistics.median(pages) if pages else None
        for e in es:
            if e["kx"] is None and e.get("kx_multi"):
                cands = e["kx_multi"]
                if med is not None:
                    e["kx"] = min(cands, key=lambda c: abs(c[0] - med))
                else:
                    e["kx"] = cands[-1]
                e["kx_used"] = "multi_alt"
                n_multi_used += 1
    missing = [e for e in zheng if e["kx"] is None]

    outliers = []
    for gkey, es in by_group.items():
        pages = [e["kx"][0] for e in es if e["kx"]]
        if len(pages) >= 3:
            med = statistics.median(pages)
            for e in es:
                if e["kx"] and abs(e["kx"][0] - med) > 6:
                    outliers.append({"char": e["char"], "gi_key": list(gkey),
                                     "rad": e["rad"], "mt_pos": e["pos"],
                                     "kx": list(e["kx"]),
                                     "group_page_median": med,
                                     "action": "kx_cleared_interp_mt_order"})
                    e["kx_outlier"] = e["kx"]
                    e["kx"] = None

    # 组内排序：有 kx 的按 kx，缺/离群的按数据集序插值（名次比例映射到 kx 区间）
    out = []
    for gkey in sorted(by_group):
        es = by_group[gkey]
        known = sorted([e for e in es if e["kx"]], key=lambda e: (e["kx"], e["pos"]))
        if not known:
            for e in sorted(es, key=lambda e: e["pos"]):
                out.append(e)
            continue
        mt_rank = {id(e): i for i, e in enumerate(sorted(es, key=lambda e: e["pos"]))}
        n = len(es)
        keys = []
        for e in es:
            if e["kx"]:
                keys.append((e, (e["kx"][0], e["kx"][1])))
            else:
                frac = mt_rank[id(e)] / max(n - 1, 1)
                if len(known) == 1:
                    p0, s0 = known[0]["kx"]
                    keys.append((e, (p0, s0 + 1e-3 * e["pos"])))
                else:
                    pos = frac * (len(known) - 1)
                    lo = min(len(known) - 2, int(pos))
                    hi = lo + 1
                    p0, s0 = known[lo]["kx"]
                    p1, s1 = known[hi]["kx"]
                    keys.append((e, (p0 + (p1 - p0) * (pos - lo),
                                    s0 + (s1 - s0) * (pos - lo) - 1e-3)))
        keys.sort(key=lambda t: (t[1], t[0]["pos"]))
        out.extend(e for e, _ in keys)

    # 组表
    groups = []
    prev = None
    for e in out:
        if e["gi_key"] != prev:
            groups.append({"gi": len(groups), "rad": e["rad"], "rad_i": e["gi_key"][0],
                           "bu_strokes": e["bu"], "size": 0})
            prev = e["gi_key"]
        groups[-1]["size"] += 1
    acc = 0
    for g in groups:
        g["start"] = acc
        g["end"] = acc + g["size"] - 1
        acc += g["size"]

    # 校验
    rad_seq = [g["rad_i"] for g in groups]
    rad_viol = sum(1 for a, b in zip(rad_seq, rad_seq[1:]) if b < a)
    # 组内 kx 单调（组内按 kx 排序后应非降；仅统计原始 kx，插值的不计）
    intra_viol = 0
    for g in groups:
        seg = out[g["start"]:g["end"] + 1]
        ks = [e["kx"] for e in seg if e["kx"]]
        intra_viol += sum(1 for a, b in zip(ks, ks[1:]) if b < a)
    # 数据集序 vs 正典序矛盾率：相邻两两比较正典序与数据集序方向
    zheng_mt_order = sorted(zheng, key=lambda e: e["pos"])
    canon_pos = {id(e): i for i, e in enumerate(out)}
    # 相邻（数据集序）条目在正典序中位置倒挂的比例
    inv = 0
    pairs = 0
    bound = 0
    for a, b in zip(zheng_mt_order, zheng_mt_order[1:]):
        pairs += 1
        if canon_pos[id(b)] < canon_pos[id(a)]:
            inv += 1
    # 已知正典序 vs 数据集序矛盾样本
    ci = {e["char"]: i for i, e in enumerate(out)}
    sample = [(c, ci.get(c)) for c in ("昴", "昵", "昶", "昷")]

    ties = collections.Counter((e["kx"][0], e["kx"][1]) for e in out if e["kx"])
    tie_groups = [k for k, v in ties.items() if v > 1]
    virtual = [e for e in out if e["kx"] and e["kx"][1] % 10 == 1]
    stats = {
        "kpos_tie_groups": len(tie_groups),
        "kpos_tie_entries": sum(ties[k] for k in tie_groups),
        "virtual_pos_entries_dataset": len(virtual),
        "n_zheng": len(out), "n_groups": len(groups),
        "n_buqi": len(buqi), "n_beikao": len(beikao),
        "missing_kx_before_fix": len(missing),
        "multi_valued_kx_used": n_multi_used,
        "kx_covered_zheng": sum(1 for e in zheng if e["kx"] or e.get("kx_outlier")),
        "outliers_cleaned": len(outliers),
        "group_size_median": statistics.median([g["size"] for g in groups]),
        "group_size_max": max(g["size"] for g in groups),
        "radical_order_violations": rad_viol,
        "intra_group_kx_violations_after_clean": intra_viol,
        "dataset_order_vs_canonical_adjacent_inversions": inv,
        "dataset_order_adjacent_pairs": pairs,
        "dataset_order_inversion_rate": round(inv / pairs, 4),
        "groups_with_negative_bu": sum(1 for g in groups if g["bu_strokes"] < 0),
        "negative_bu_entries": sum(1 for e in out if e["bu"] < 0),
        "unique_chars": len({e["char"] for e in out}),
        "duplicate_char_extra_slots": len(out) - len({e["char"] for e in out}),
        "sample_05_0017_canonical_ci": dict(sample),
        "sample_05_0017_ok": all(sample[i][1] is not None for i in range(4)) and
                             sample[0][1] < sample[1][1] < sample[2][1] < sample[3][1],
    }

    with open(os.path.join(OUT, "canonical.jsonl"), "w", encoding="utf-8") as f:
        for ci_, e in enumerate(out):
            f.write(json.dumps({
                "ci": ci_, "char": e["char"], "rad": e["rad"],
                "stroke_total": e["stroke"], "bu_strokes": e["bu"],
                "gi": None, "kx": list(e["kx"]) if e["kx"] else None,
                "kx_outlier": list(e["kx_outlier"]) if e.get("kx_outlier") else None,
                "mt_pos": e["pos"], "mt_i": e["i"], "path": e["path"],
                "group": [e["gi_key"][0], e["gi_key"][1]],
            }, ensure_ascii=False) + "\n")
    # 回填 gi
    lines = open(os.path.join(OUT, "canonical.jsonl"), encoding="utf-8").read().splitlines()
    for g in groups:
        for ci_ in range(g["start"], g["end"] + 1):
            d = json.loads(lines[ci_])
            d["gi"] = g["gi"]
            lines[ci_] = json.dumps(d, ensure_ascii=False)
    open(os.path.join(OUT, "canonical.jsonl"), "w",
         encoding="utf-8").write("\n".join(lines) + "\n")

    json.dump(groups, open(os.path.join(OUT, "groups.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    for name, arr in (("buqi.jsonl", buqi), ("beikao.jsonl", beikao)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            for ci_, e in enumerate(arr):
                f.write(json.dumps({
                    "ci": ci_, "char": e["char"], "rad": e["rad"],
                    "stroke_total": e["stroke"], "mt_pos": e["pos"], "mt_i": e["i"],
                    "path": e["path"], "order": "dataset",
                }, ensure_ascii=False) + "\n")
    json.dump({"n": len(outliers), "items": outliers},
              open(os.path.join(OUT, "outliers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(stats, open(os.path.join(OUT, "seqorder_stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
