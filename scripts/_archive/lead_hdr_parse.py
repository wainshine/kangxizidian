#!/usr/bin/env python3
"""Lead · 版心 OCR 结构化解析（从 seq 的 headers_full_raw.jsonl）。

版式（自上而下）：康熙字典(4,常被裁) → 集名(3: 子/集/上) → 部首(1) → 部(1) → 画数(数字*+畫, 1-2 组) → 葉码(数字*)
输出 work/lead/hdr_parsed.jsonl：{page, ji, bu_text, bu_conf, hua:[..], leaf_text}
"""
import argparse, json, os, re, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMV = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
        "九": 9, "十": 10, "廿": 20, "卅": 30, "卌": 40, "百": 100}
NUM_RE = set("一二三四五六七八九十廿卅卌百")


def numval(s):
    if not s or any(c not in NUM_RE for c in s):
        return None
    if len(s) == 1:
        return NUMV[s]
    if len(s) == 2:
        a, b = s
        if a in "廿卅卌" and b in NUMV:
            return NUMV[a] + NUMV[b]
        if a == "十" and b in NUMV:
            return 10 + NUMV[b]
        if b == "十" and a in NUMV:
            return NUMV[a] * 10
        if a == "百" and b in NUMV:
            return 100 + NUMV[b]
    if len(s) == 3 and s[1] == "十":
        return NUMV[s[0]] * 10 + NUMV[s[2]]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(ROOT, "work/seq/headers_full_raw.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work/lead/hdr_parsed.jsonl"))
    args = ap.parse_args()
    fout = open(args.out, "w", encoding="utf-8")
    stats = collections.Counter()
    for line in open(args.raw, encoding="utf-8"):
        d = json.loads(line)
        page = f"{d['pdf']}_{d['page']:04d}"
        cells = d.get("cells") or []
        # 找「部」格
        bu_i = None
        for i, c in enumerate(cells):
            if c["text"] == "部" and c["score"] >= 0.5:
                bu_i = i
                break
        rec = {"page": page, "bu_text": None, "bu_conf": 0.0,
               "ji": None, "hua": [], "leaf_text": None}
        # 独立解析画数：从所有「畫」格向上收 1-2 个数字格
        hua2 = []
        for i, c in enumerate(cells):
            if c["text"] == "畫" and c["score"] >= 0.35:
                nums = []
                j = i - 1
                while j >= 0 and len(nums) < 2 and cells[j]["text"] in NUM_RE \
                        and cells[j]["score"] >= 0.2:
                    nums.insert(0, cells[j]["text"])
                    j -= 1
                if nums:
                    v = numval("".join(nums))
                    if v is not None:
                        hua2.append(v)
        rec["hua"] = hua2[:2]
        rec["hua2"] = hua2
        if bu_i is not None:
            if bu_i >= 1:
                rec["bu_text"] = cells[bu_i - 1]["text"] or None
                rec["bu_conf"] = round(cells[bu_i - 1]["score"], 2)
            if bu_i >= 4:
                # 集名 3 格 = 部 前第 2-4 格（跳过部首）
                rec["ji"] = "".join(cells[bu_i - 4]["text"] for _ in [0]) if False else None
                rec["ji_cells"] = [cells[bu_i - 4]["text"], cells[bu_i - 3]["text"],
                                   cells[bu_i - 2]["text"]]
            # 画数：部 之后 数字*+畫
            hua = []
            cur = ""
            j = bu_i + 1
            while j < len(cells):
                t = cells[j]["text"]
                if t == "畫":
                    v = numval(cur)
                    if v is not None:
                        hua.append(v)
                    cur = ""
                    j += 1
                    if len(hua) >= 2:
                        break
                    continue
                if t in NUM_RE:
                    cur += t
                    j += 1
                    continue
                break
            rec["hua_bu"] = hua
            # 葉码：底部 2-3 格文本
            tail = [c["text"] for c in cells[max(0, len(cells) - 3):]]
            rec["leaf_text"] = "".join(tail)
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        stats["n"] += 1
        if rec["bu_text"]:
            stats["has_bu"] += 1
        if rec["hua"]:
            stats["has_hua"] += 1
    fout.close()
    print(dict(stats))
    # 对 owner 20 页做校验
    g = json.load(open(os.path.join(ROOT, "work/t2/margin_labels_full.json"), encoding="utf-8"))["pages"]
    got = {}
    for line in open(args.out, encoding="utf-8"):
        r = json.loads(line)
        got[r["page"]] = r
    ok = 0
    tot = 0
    for pg, t in g.items():
        L = t.get("L") or {}
        if not L.get("bu"):
            continue
        want_bu = L["bu"].rstrip("部")
        want_hua = []
        for h in (L.get("hua") or []):
            v = numval(str(h).replace("畫", ""))
            if v is not None:
                want_hua.append(v)
        r = got.get(pg) or {}
        tot += 1
        b = r.get("bu_text")
        hua = r.get("hua") or []
        if b == want_bu and hua == want_hua:
            ok += 1
        else:
            print(f"  {pg} bu={b} want={want_bu} | hua={hua} want={want_hua}")
    print(f"owner 20 页: {ok}/{tot} 全对")


if __name__ == "__main__":
    main()
