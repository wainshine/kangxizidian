#!/usr/bin/env python3
"""A2b · 卷/部首结构：卷→部首范围 + 每卷 entry 数 + 与 page_roles/volume_sections 核对。

证据来源：
- 36 个卷扉页（刻本版面实测，本文件 VOL_STARTS 的注释列出扉页页码与首部部首读数）；
- 正典序 work/seq/canonical.jsonl 的 (rad, bu) 组 size 求每卷 entries；
- work/lead/volume_sections.json 的 body 页区间求每卷页数、算密度。
产出：work/seq/volume_radicals.json、work/seq/volume_structure_stats.json
"""
import json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "work", "seq")
RAD214 = ("一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕"
          "大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰"
          "月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢"
          "石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言"
          "谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬"
          "骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠")
IDX = {c: i for i, c in enumerate(RAD214)}

# 卷→首部部首（实测自刻本卷扉页：右起首列部首；*_src = 扉页页码/位置）
VOL_STARTS = {
    "01": {"ji": "子", "juan": [("子集上", "一", "p5L(扉页, 一/丨/丶/丿/乙/亅) + p6R(2部/亠部)"),
                                ("子集中", "人", "p49L(扉页, 人部+亻同)"),
                                ("子集下", "儿", "p128L+p129R+p129L(扉页 儿/入/八/冂/冖/冫/几/凵/刀/力/勹/匕/匚/匸/十/卜/卩/厂/厶/又)") ]},
    "02": {"ji": "丑", "juan": [("丑集上", "口", "p4L(口/囗)"), ("丑集中", "土", "p127L(土/士/夂)"),
                                ("丑集下", "夊", "p185L(夊/夕/大/女)")]},
    "03": {"ji": "寅", "juan": [("寅集上", "子", "p4L(子/宀/寸/小/尢/尸) + p5R(屮)"),
                                ("寅集中", "山", "p80L(山/巛/工/己/巾)"),
                                ("寅集下", "干", "p161L(干/幺/广/廴/廾/弋) + p162R(弓/彐/彡/彳)")]},
    "04": {"ji": "卯", "juan": [("卯集上", "心", "p4L(心+小小同)"), ("卯集中", "戈", "p90L(戈/戶/手)"),
                                ("卯集下", "支", "p221L(支/攴/文) + p222R(斗/斤/方/无)")]},
    "05": {"ji": "辰", "juan": [("辰集上", "日", "p4L(日/曰/月)"), ("辰集中", "木", "p55L(木)"),
                                ("辰集下", "欠", "p189L(欠/止/歹) + p190R(殳/毋/比/毛/氏/气)")]},
    "06": {"ji": "巳", "juan": [("巳集上", "水", "p4L(水)"), ("巳集中", "火", "p151L(火/爪/父/爻/爿/片) + p152R(牙)"),
                                ("巳集下", "牛", "p230L(牛/犬)")]},
    "07": {"ji": "午", "juan": [("午集上", "玄", "p4L(玄/玉/瓜) + p5R(瓦/甘/生/用/田/疋)"),
                                ("午集中", "疒", "p113L(疒/癶/白) + p114R(皮/皿/目/矛/矢)"),
                                ("午集下", "石", "p252L(石/示/禸) + p253R(禾/穴/立)")]},
    "08": {"ji": "未", "juan": [("未集上", "竹", "p4L(竹/米)"),
                                ("未集中", "糸", "p97L(糸/缶/网) + p98R(羊/羽/老/而/耒/耳/聿)"),
                                ("未集下", "肉", "p238L(肉/臣/自) + p239R(至/臼/舌/舛/舟/艮/色)")]},
    "09": {"ji": "申", "juan": [("申集上", "艸", "p4L(艸)"), ("申集中", "虍", "p138L(虍/虫)"),
                                ("申集下", "血", "p220L(血/行/衣) + p221R(襾)")]},
    "10": {"ji": "酉", "juan": [("酉集上", "見", "p4L(見/角/言)"), ("酉集中", "谷", "p138L(谷/豆/豕) + p139R(豸/貝/赤/走/足/身)"),
                                ("酉集下", "車", "p261L(車/辛/辰) + p262R(辵/邑/酉/釆/里)")]},
    "11": {"ji": "戌", "juan": [("戌集上", "金", "p4L(金/長/門)"), ("戌集中", "阜", "p122L(阜/隶/隹) + p123R(雨/靑/非/面/革/韋/韭/音)"),
                                ("戌集下", "頁", "p253L(頁/風/飛) + p254R(食/首/香)")]},
    "12": {"ji": "亥", "juan": [("亥集上", "馬", "p4L(馬/骨/高) + p5R(髟/鬥/鬯/鬲/鬼)"),
                                ("亥集中", "魚", "p83L(魚/鳥)"),
                                ("亥集下", "鹵", "p183L(鹵/鹿/麥) + p184R(麻/黃/黍/黑/黹/黽/鼎/鼓/鼠/鼻/齊/齒/龍/龜/龠)")]},
}



def pdf13_sections():
    """PDF13 補遺/備考 分节：entries 来自数据集 path；页区间来自 13 册书眉实测
    （work/seq/headers_13_probe.jsonl：逐页读「X集補遺/備考」集名 + 補/備 标记，
    单调分段；補遺總目 p4–15、備考總目 p77–90 另计）。"""
    import re
    seq = [json.loads(l) for l in open(os.path.join(ROOT, "work", "t2", "entry_sequence.jsonl"),
                                       encoding="utf-8")]
    probe = os.path.join(OUT, "headers_13_probe.jsonl")
    # 实测页段（读自 13 册书眉，见 headers_13_probe.jsonl 的 ji_char/suffix）
    OBS = {
        ("buqi", "子集"): (16, 20), ("buqi", "丑集"): (21, 27), ("buqi", "寅集"): (28, 33),
        ("buqi", "卯集"): (34, 36), ("buqi", "辰集"): (37, 39), ("buqi", "巳集"): (40, 44),
        ("buqi", "午集"): (45, 48), ("buqi", "未集"): (49, 51), ("buqi", "申集"): (52, 55),
        ("buqi", "酉集"): (56, 61), ("buqi", "戌集"): (62, 67), ("buqi", "亥集"): (68, 70),
        ("beikao", "子集"): (91, 97), ("beikao", "丑集"): (98, 104), ("beikao", "寅集"): (105, 113),
        ("beikao", "卯集"): (114, 118), ("beikao", "辰集"): (119, 122), ("beikao", "巳集"): (123, 128),
        ("beikao", "午集"): (129, 137), ("beikao", "未集"): (138, 142), ("beikao", "申集"): (143, 146),
        ("beikao", "酉集"): (147, 156), ("beikao", "戌集"): (157, 165), ("beikao", "亥集"): (166, 175),
    }
    out = {"sections": [], "toc_pages": {"buqi": [4, 15], "beikao": [77, 90]},
           "method": {
        "order": "補遺 12 集（子集→亥集）后接 備考 12 集（子集→亥集）："
                 "实测 13_0020=寅集補遺(p20)、13_0163=戌集備考(p163)，且书眉逐页读数单调；"
                 "数据集 entry_sequence 的 path 序与之一致",
        "entries": "数据集 path 【補遺/備考】【X集】【Y字部】分组计数",
        "pages": "headers_13_probe.jsonl 逐页书眉实测（集名+補/備 单调分段）；"
                 "補遺總目 p4–15、備考總目 p77–90（各 12 集扉页，每集一頁）",
    }}
    for sec in ("buqi", "beikao"):
        tag = "補遺" if sec == "buqi" else "備考"
        rows = [e for e in seq if e["path"].startswith(f"【{tag}】")]
        order, cnt, rads = [], collections.Counter(), collections.defaultdict(set)
        for e in rows:
            m = re.match(r"^【(補遺|備考)】【([^】]+)】【([^】]+)】$", e["path"])
            if not m:
                continue
            key = m.group(2)
            if not order or order[-1] != key:
                order.append(key)
            cnt[key] += 1
            rads[key].add(e["rad"])
        for k in order:
            rad_order = [c for c in RAD214 if c in rads[k]]
            pg = OBS.get((sec, k))
            out["sections"].append({
                "section": sec, "juan": k, "kind": tag,
                "radicals": rad_order, "n_radicals": len(rad_order),
                "entries": cnt[k],
                "body_pages": list(pg) if pg else None,
                "page_range_confidence": "measured_header" if pg else None,
                "evidence": "13 册书眉（headers_13_probe.jsonl）" if pg else None,
                "note": None if pg else "页段未实测",
            })
    return out


def main():
    canon = [json.loads(l) for l in open(os.path.join(OUT, "canonical.jsonl"),
                                         encoding="utf-8")]
    # radicals in canonical order (from canonical: rad_i 0..213)
    rad_entries = collections.Counter()
    rad_order = []
    for e in canon:
        ri = e["group"][0]
        rad_entries[ri] += 1
        if not rad_order or rad_order[-1] != ri:
            rad_order.append(ri)
    # 卷 range
    vs = json.load(open(os.path.join(ROOT, "work", "lead", "volume_sections.json"),
                        encoding="utf-8"))
    out = {"volumes": {}, "method": {
        "radical_ranges": "由 36 个刻本卷扉页实测的首部部首确定卷界；卷内部首 = RAD214 连续区间",
        "entries": "work/seq/canonical.jsonl 的 (rad,bu) 组 size 之和",
        "body_pages": "work/lead/volume_sections.json 的 body runs（页号含扉页尾/卷界页，见 docs/STRUCTURE.md）",
        "verified_against": "12 卷×3 卷扉页（首部部首逐卷读数，见每个 juan.evidence）",
    }}
    stats = {}
    # flatten starts: for each vol, 3 starts; last vol end = 214
    # build global list of (vol, juan_name, start_rad_char, evidence) and next start
    allj = []
    for vol in [f"{i:02d}" for i in range(1, 13)]:
        for name, rch, ev in VOL_STARTS[vol]["juan"]:
            allj.append((vol, name, rch, ev))
    starts = [IDX[rch] for _, _, rch, _ in allj]
    # sanity: monotone increasing
    assert all(a < b for a, b in zip(starts, starts[1:])), "starts not monotone"
    bounds = starts + [len(RAD214)]
    vol_juan = collections.defaultdict(list)
    for k, (vol, name, rch, ev) in enumerate(allj):
        a, b = bounds[k], bounds[k + 1] - 1
        rads = RAD214[a:b + 1]
        entries = sum(rad_entries[IDX[c]] for c in rads)
        ji = VOL_STARTS[vol]["ji"]
        juan_full = name
        runs = vs[vol]["runs"]
        idx = {"上": 0, "中": 1, "下": 2}[name[-1]]
        body = runs[idx]
        pages = body[1] - body[0] + 1
        item = {"juan": juan_full, "radicals": list(rads),
                "radical_range": [a, b], "n_radicals": len(rads),
                "entries": entries, "body_pages": body,
                "n_pages": pages,
                "entries_per_page": round(entries / max(1, pages), 2),
                "evidence": ev}
        vol_juan[vol].append(item)
        stats[f"{vol}_{juan_full}"] = {"entries": entries, "pages": pages,
                                       "density": round(entries / max(1, pages), 2),
                                       "n_radicals": len(rads)}
    for vol in [f"{i:02d}" for i in range(1, 13)]:
        out["volumes"][vol] = {"ji": VOL_STARTS[vol]["ji"], "juan": vol_juan[vol],
                               "entries_total": sum(j["entries"] for j in vol_juan[vol]),
                               "pages_total": sum(j["n_pages"] for j in vol_juan[vol])}
    # 全体校验
    all_rads = [c for vol in out["volumes"].values() for j in vol["juan"] for c in j["radicals"]]
    out["checks"] = {
        "n_radicals": len(all_rads),
        "radicals_complete": all_rads == list(RAD214),
        "n_entries_total": sum(v["entries_total"] for v in out["volumes"].values()),
        "n_pages_total": sum(v["pages_total"] for v in out["volumes"].values()),
        "entries_total_expected": len(canon),
        "density_overall": round(sum(v["entries_total"] for v in out["volumes"].values()) /
                                 max(1, sum(v["pages_total"] for v in out["volumes"].values())), 2),
    }
    # 与数据集 path 集名划分逐部首比对（质疑项：entries 是否对不上）
    import re as _re
    seq = [json.loads(l) for l in open(os.path.join(ROOT, "work", "t2", "entry_sequence.jsonl"),
                                       encoding="utf-8")]
    ds = collections.defaultdict(collections.Counter)
    for e in seq:
        if e["path"].startswith("【補遺】") or e["path"].startswith("【備考】"):
            continue
        m = _re.match(r"^【([^】]+)】【([^】]+)】$", e["path"])
        if m:
            ds[e["rad"]][m.group(1)] += 1
    ds_ji = {c: cnt.most_common(1)[0][0] for c, cnt in ds.items()}
    mismatch = []
    our = {}
    for vol, v in out["volumes"].items():
        for j in v["juan"]:
            for c in j["radicals"]:
                our[c] = j["juan"]
    for c in RAD214:
        if ds_ji.get(c) != our.get(c):
            mismatch.append({"rad": c, "dataset_ji": ds_ji.get(c), "printed_juan": our.get(c)})
    out["checks"]["dataset_ji_mismatch"] = {"n": len(mismatch), "items": mismatch,
                                            "note": "数据集 path 集名 vs 刻本卷扉页实测；应为 0"}
    out["pdf13"] = pdf13_sections()
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "volume_radicals.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(stats, open(os.path.join(OUT, "volume_structure_stats.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out["checks"], ensure_ascii=False, indent=1))
    # 逐卷打印
    for vol in [f"{i:02d}" for i in range(1, 13)]:
        v = out["volumes"][vol]
        print(vol, v["ji"], "entries", v["entries_total"], "pages", v["pages_total"],
              "density", round(v["entries_total"] / max(1, v["pages_total"]), 2))
        for j in v["juan"]:
            print("   ", j["juan"], "radicals", j["radicals"][0] + ".." + j["radicals"][-1],
                  f"({j['n_radicals']})", "entries", j["entries"], "pages", j["body_pages"],
                  "density", j["entries_per_page"])


if __name__ == "__main__":
    main()
