#!/usr/bin/env python3
"""Lead 原型：正典序 + 组表（v3 structural labeling 骨架）。

口径（见 docs/TAKEOVER.md §2.A/B）：
- 正集 42,302 条 = path 不以【補遺】/【備考】开头。
- 正典序 = 按 Unihan kKangXi (page, position) 升序，同位置平局用数据集 pos tie-break。
- 组 = (部首, 部外笔画)，部外 = stroke_total - 部首笔画。部首笔画用 214 部首笔画表。
- 离群清洗：组的 kpage 中位 ±6 页以外的条目 = 离群（kKangXi 指错），用数据集序插回组内相对位置。

产出（原型，供 Lead 调 solver；正式版见 seq teammate 的 scripts/seq_order.py + work/seq/）：
  work/lead/canonical_proto.jsonl
  work/lead/groups_proto.json
  work/lead/canonical_stats.json
"""
import json, os, re, statistics, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEAD = os.path.join(ROOT, "work", "lead")
UNIHAN = os.path.join(ROOT, "data", "unihan", "Unihan_DictionaryIndices.txt")
SEQ = os.path.join(ROOT, "work", "t2", "entry_sequence.jsonl")

RAD214 = "一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠"


def radical_strokes():
    """214 部首笔画表（部首字本身的总笔画）。"""
    strokes = {
        "一": 1, "丨": 1, "丶": 1, "丿": 1, "乙": 1, "亅": 1, "二": 2, "亠": 2, "人": 2, "儿": 2,
        "入": 2, "八": 2, "冂": 2, "冖": 2, "冫": 2, "几": 2, "凵": 2, "刀": 2, "力": 2, "勹": 2,
        "匕": 2, "匚": 2, "匸": 2, "十": 2, "卜": 2, "卩": 2, "厂": 2, "厶": 2, "又": 2, "口": 3,
        "囗": 3, "土": 3, "士": 3, "夂": 3, "夊": 3, "夕": 3, "大": 3, "女": 3, "子": 3, "宀": 3,
        "寸": 3, "小": 3, "尢": 3, "尸": 3, "屮": 3, "山": 3, "巛": 3, "工": 3, "己": 3, "巾": 3,
        "干": 3, "幺": 3, "广": 3, "廴": 3, "廾": 3, "弋": 3, "弓": 3, "彐": 3, "彡": 3, "彳": 3,
        "心": 4, "戈": 4, "戶": 4, "手": 4, "支": 4, "攴": 4, "文": 4, "斗": 4, "斤": 4, "方": 4,
        "无": 4, "日": 4, "曰": 4, "月": 4, "木": 4, "欠": 4, "止": 4, "歹": 4, "殳": 4, "毋": 4,
        "比": 4, "毛": 4, "氏": 4, "气": 4, "水": 4, "火": 4, "爪": 4, "父": 4, "爻": 4, "爿": 4,
        "片": 4, "牙": 4, "牛": 4, "犬": 4, "玄": 5, "玉": 5, "瓜": 5, "瓦": 5, "甘": 5, "生": 5,
        "用": 5, "田": 5, "疋": 5, "疒": 5, "癶": 5, "白": 5, "皮": 5, "皿": 5, "目": 5, "矛": 5,
        "矢": 5, "石": 5, "示": 5, "禸": 5, "禾": 5, "穴": 5, "立": 5, "竹": 6, "米": 6, "糸": 6,
        "缶": 6, "网": 6, "羊": 6, "羽": 6, "老": 6, "而": 6, "耒": 6, "耳": 6, "聿": 6, "肉": 6,
        "臣": 6, "自": 6, "至": 6, "臼": 6, "舌": 6, "舛": 6, "舟": 6, "艮": 6, "色": 6, "艸": 6,
        "虍": 6, "虫": 6, "血": 6, "行": 6, "衣": 6, "襾": 6, "見": 7, "角": 7, "言": 7, "谷": 7,
        "豆": 7, "豕": 7, "豸": 7, "貝": 7, "赤": 7, "走": 7, "足": 7, "身": 7, "車": 7, "辛": 7,
        "辰": 7, "辵": 7, "邑": 7, "酉": 7, "釆": 7, "里": 7, "金": 8, "長": 8, "門": 8, "阜": 8,
        "隶": 8, "隹": 8, "雨": 8, "靑": 8, "非": 8, "面": 9, "革": 9, "韋": 9, "韭": 9, "音": 9,
        "頁": 9, "風": 9, "飛": 9, "食": 9, "首": 9, "香": 9, "馬": 10, "骨": 10, "高": 10,
        "髟": 10, "鬥": 10, "鬯": 10, "鬲": 10, "鬼": 10, "魚": 11, "鳥": 11, "鹵": 11, "鹿": 11,
        "麥": 11, "麻": 11, "黃": 12, "黍": 12, "黑": 12, "黹": 12, "黽": 13, "鼎": 13, "鼓": 13,
        "鼠": 13, "鼻": 14, "齊": 14, "齒": 15, "龍": 16, "龜": 16, "龠": 17,
    }
    assert len(strokes) == 214, len(strokes)
    return strokes


def load_kx():
    pat = re.compile(r"^(U\+[0-9A-F]+)\tkKangXi\t(\d{4})\.(\d+)\s*$")
    kx = {}
    for line in open(UNIHAN, encoding="utf-8"):
        m = pat.match(line)
        if m:
            kx[chr(int(m.group(1)[2:], 16))] = (int(m.group(2)), int(m.group(3)))
    return kx


def main():
    os.makedirs(LEAD, exist_ok=True)
    kx = load_kx()
    rstroke = radical_strokes()
    ridx = {c: i for i, c in enumerate(RAD214)}
    seq = [json.loads(l) for l in open(SEQ, encoding="utf-8")]
    zheng = [e for e in seq
             if not e["path"].startswith("【補遺】") and not e["path"].startswith("【備考】")]
    print("正集条目", len(zheng))

    # --- 组 + 部外笔画 ---
    for e in zheng:
        rad = e["rad"]
        rs = rstroke.get(rad)
        e["bu_strokes"] = (e["stroke"] - rs) if rs is not None else None
        e["kx"] = kx.get(e["char"])
        e["gi_key"] = (ridx.get(rad, 999), e["bu_strokes"])
    missing_rad = sorted({e["rad"] for e in zheng if e["rad"] not in rstroke})
    missing_kx = sum(1 for e in zheng if e["kx"] is None)
    print("未知部首", missing_rad, "缺 kKangXi", missing_kx)

    # --- 离群清洗：组内 kpage 中位 ±6 外 ---
    by_group = collections.defaultdict(list)
    for e in zheng:
        by_group[e["gi_key"]].append(e)
    n_out = 0
    for gkey, es in by_group.items():
        pages = [e["kx"][0] for e in es if e["kx"]]
        if len(pages) >= 3:
            med = statistics.median(pages)
            for e in es:
                if e["kx"] and abs(e["kx"][0] - med) > 6:
                    e["_kx_page"] = e["kx"][0]
                    e["kx"] = None  # 用数据集序插回组内（组内排序时作缺省处理）
                    n_out += 1
    print("离群 kKangXi 清洗", n_out)

    # --- 组内排序（含离群/缺 kx 条目按数据集 mt 名次插值）---
    out = []
    for gkey in sorted(by_group):
        es = by_group[gkey]
        known = sorted([e for e in es if e["kx"]], key=lambda e: e["kx"])
        unknown = [e for e in es if not e["kx"]]
        if not known:
            for e in sorted(unknown, key=lambda e: e["pos"]):
                out.append(e)
            continue
        # 名次插值：未知条目 mt_pos 在组内 mt_pos 序列中的比例 -> 目标坐标
        mt_sorted = sorted(es, key=lambda e: e["pos"])
        rank = {id(e): i for i, e in enumerate(mt_sorted)}
        n = len(es)
        keys = []
        for e in es:
            if e["kx"]:
                keys.append((e, (e["kx"][0], e["kx"][1])))
            else:
                # 目标名次比例 = 组内 mt 名次 -> 映射到 known 坐标区间内
                frac = rank[id(e)] / max(n - 1, 1)
                if len(known) == 1:
                    p0, s0 = known[0]["kx"]
                    keys.append((e, (p0, s0 + 1e-3 * e["pos"])))
                    continue
                pos = frac * (len(known) - 1)
                lo = min(len(known) - 2, int(pos))
                hi = lo + 1
                p0, s0 = known[lo]["kx"]
                p1, s1 = known[hi]["kx"]
                page = p0 + (p1 - p0) * (pos - lo)
                posv = s0 + (s1 - s0) * (pos - lo)
                # 缺 kx 条目按 mt 序同组相邻：确保不与 known 完全同坐标
                keys.append((e, (page, posv - 1e-3)))
        keys.sort(key=lambda t: (t[1], t[0]["pos"]))
        out.extend(e for e, _ in keys)

    # --- 生成组表 ---
    groups = []
    cur_key = None
    for e in out:
        k = e["gi_key"]
        if k != cur_key:
            groups.append({"gi": len(groups), "rad": e["rad"], "bu_strokes": e["bu_strokes"],
                           "rad_i": k[0], "start": len([x for gg in groups for x in range(gg["size"])]),
                           "size": 0})
            cur_key = k
        groups[-1]["size"] += 1
    # 简化 start 计算
    acc = 0
    for gi, g in enumerate(groups):
        g["start"] = acc
        g["end"] = acc + g["size"] - 1
        acc += g["size"]

    # --- 校验 ---
    rad_seq = [g["rad_i"] for g in groups]
    viol = sum(1 for a, b in zip(rad_seq, rad_seq[1:]) if b < a)
    stats = {
        "n_zheng": len(out),
        "n_groups": len(groups),
        "group_size_median": statistics.median([g["size"] for g in groups]),
        "group_size_max": max(g["size"] for g in groups),
        "radical_order_violations": viol,
        "missing_kx": missing_kx,
        "outliers_cleaned": n_out,
        "unknown_radicals": missing_rad,
        "unique_chars": len({e["char"] for e in out}),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=1))

    with open(os.path.join(LEAD, "canonical_proto.jsonl"), "w", encoding="utf-8") as f:
        for ci, e in enumerate(out):
            f.write(json.dumps({"ci": ci, "char": e["char"], "rad": e["rad"],
                                "stroke_total": e["stroke"], "bu_strokes": e["bu_strokes"],
                                "gi": None, "mt_pos": e["pos"], "mt_i": e["i"],
                                "kx": e["kx"], "path": e["path"]}, ensure_ascii=False) + "\n")
    # gi 回填
    lines = open(os.path.join(LEAD, "canonical_proto.jsonl"), encoding="utf-8").read().splitlines()
    for g in groups:
        for ci in range(g["start"], g["end"] + 1):
            d = json.loads(lines[ci])
            d["gi"] = g["gi"]
            lines[ci] = json.dumps(d, ensure_ascii=False)
    open(os.path.join(LEAD, "canonical_proto.jsonl"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(groups, open(os.path.join(LEAD, "groups_proto.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    # 已知点校验：05_0017 序
    chars = [e["char"] for e in out]
    ci = {c: i for i, c in enumerate(chars)}
    sample = ["昴", "昵", "昶", "昷"]
    print("05_0017 序检查:", [(c, ci.get(c)) for c in sample])
    print("一部前 20:", [(i, out[i]["char"]) for i in range(0, 20)])
    json.dump(stats, open(os.path.join(LEAD, "canonical_stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
