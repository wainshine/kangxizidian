#!/usr/bin/env python3
"""A4 · 逐页版心观测（供 lead 的「部界 DP + 画数逐页锚点」）。

输入：work/seq/headers_full_raw.jsonl（header_read.py 全量 300dpi 版心条 OCR cells）
输出：work/seq/hdr_page_obs.jsonl 每行：
  {"page":"05_0017","vol":"05","page_no":17,"ji":"辰集上","ji_conf":...,"suffix":"上",
   "bu_text":"日","bu_conf":0.81,"bu_ban_conf":1.0,
   "hua":[5,6],"hua_conf":[0.97,0.78],"hua_fields":[{"text":"五","value":5,"conf":0.97,
     "mark_text":"畫","mark_conf":0.78,"y":[1907,2040]}, ...],
   "hua_texts":["五","六"],"leaf_text":"...","leaf_conf":...,"errors":[...]}

规则：
- 集名锚点 = cells 中 text=='集' 且 score>=0.7；suffix = 其后一格（上/中/下/末）；
- 部名锚点 = 集名之后的 text=='部' 格；部首格 = 其前一格 OCR 文本（可能为空）；
- 画数：部名之后，凡「畫」类格（畫/画/晝/書 且 score>=0.35，或高≥62px 且非数词）
  为一个画数字段的收尾；该格前面的数词格（可能多格，如「十」+「二」）拼成一个数；
  支持 一…十、廿/卅、阿拉伯数字、十位组合（十二/二十/三十二/四十四）；
- 葉码：最后一个画数字段之后的格，拼接文本 + 最低/平均分；
- 没有对应字段 → null（部首页无画数字段是正常现象）。
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "work", "seq")

NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
       "十": 10, "廿": 20, "卅": 30, "〇": 0, "零": 0, "两": 2, "兩": 2,
       "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9}
MARK_CHARS = set("畫画晝書昼")


def cells_of(row):
    cs = row.get("cells") or []
    return [c for c in cs if c.get("text")]


def find_ji_idx(cells):
    best = None
    for i, c in enumerate(cells):
        if c["text"] == "集" and c["score"] >= 0.7:
            best = i
    return best


def parse_num(texts):
    """把数词 OCR 文本序列拼成一个整数；失败返回 None。"""
    s = "".join(texts)
    s = s.strip()
    if not s:
        return None
    # 阿拉伯数字
    if re.fullmatch(r"\d+", s):
        v = int(s)
        return v if 0 <= v <= 60 else None
    # 纯汉字数字
    if not all(ch in NUM or ch in "十廿卅" for ch in s):
        # 允许混入少量 OCR 垃圾，尝试提取数字字符
        digits = "".join(ch for ch in s if ch in NUM)
        if digits and digits != s:
            s = digits
        else:
            return None
    if "廿" in s:
        base = 20
        rest = s.split("廿", 1)[1]
        return base + (NUM.get(rest[0], 0) if rest else 0)
    if "卅" in s:
        base = 30
        rest = s.split("卅", 1)[1]
        return base + (NUM.get(rest[0], 0) if rest else 0)
    if "十" in s:
        parts = s.split("十")
        left = parts[0]
        right = parts[1] if len(parts) > 1 else ""
        tens = NUM.get(left[-1], 0) if left else 1
        ones = NUM.get(right[0], 0) if right else 0
        v = tens * 10 + ones
        return v if 1 <= v <= 60 else None
    # 纯个位
    v = 0
    for ch in s:
        if ch in NUM:
            v = v * 10 + NUM[ch]
    return v if 0 <= v <= 60 else None


def is_mark(c, prev_vals):
    t = c["text"]
    if any(ch in MARK_CHARS for ch in t):
        return c["score"] >= 0.35
    h = c.get("y1", 0) - c.get("y0", 0)
    # 几何兜底：畫字通常比数词高（≥62px@300dpi），且前面已经有数词
    return h >= 62 and bool(prev_vals) and c["score"] >= 0.45 and not any(ch in NUM for ch in t)


def merge_hua(parsed, parsed_confs, parsed_fields, raw_hua, raw_texts):
    """OCR-cell 解析 vs resolver(几何兜底) hua 合并：条数多者优先，同条数用 OCR 解析。"""
    if parsed and len(parsed) >= len(raw_hua or []):
        return parsed, parsed_confs, parsed_fields, ["ocr_cell"] * len(parsed)
    if raw_hua:
        vals = [v for v in raw_hua if isinstance(v, int)]
        if vals:
            return vals, [None] * len(vals), parsed_fields, ["resolver_geometry"] * len(vals)
        return parsed, parsed_confs, parsed_fields, ["ocr_cell"] * len(parsed)
    return parsed, parsed_confs, parsed_fields, ["ocr_cell"] * len(parsed)


def extract_row(row):
    vol = row["pdf"]
    pno = row["page"]
    out = {"page": f"{vol}_{pno:04d}", "vol": vol, "page_no": pno,
           "ji": None, "ji_conf": None, "suffix": None, "suffix_conf": None,
           "bu_text": None, "bu_conf": None, "bu_ban_conf": None, "bu_src": None,
           "bu_cell_text": None,
           "hua": [], "hua_conf": [], "hua_fields": [], "hua_raw_texts": [],
           "leaf_text": None, "leaf_conf": None, "errors": row.get("errors") or []}
    if row.get("ji"):
        out["ji"] = row["ji"]
        out["ji_conf"] = round(float(row.get("ji_score") or 0), 3)
    cells = cells_of(row)
    if not cells:
        return out
    ji_idx = find_ji_idx(cells)
    if ji_idx is None:
        # 用 row 的 ji/ji_score（无位置时无法继续部名/画数解析）
        return out
    if ji_idx + 1 < len(cells):
        out["suffix"] = cells[ji_idx + 1]["text"]
        out["suffix_conf"] = round(float(cells[ji_idx + 1]["score"]), 3)
    # 部名：集名之后 8 格内 text=='部'
    ban_idx = None
    for i in range(ji_idx + 2, min(len(cells), ji_idx + 10)):
        c = cells[i]
        if c["text"] == "部" and c["score"] >= 0.5:
            ban_idx = i
            break
    if ban_idx is not None:
        out["bu_ban_conf"] = round(float(cells[ban_idx]["score"]), 3)
        if ban_idx - 1 > ji_idx + 1:
            rad = cells[ban_idx - 1]
            out["bu_cell_text"] = rad["text"]
            out["bu_text"] = rad["text"]
            out["bu_conf"] = round(float(rad["score"]), 3)
        else:
            out["bu_text"] = None
    if out["bu_text"] is None and row.get("bu"):
        b = str(row["bu"]).replace("部", "").strip()
        if b:
            out["bu_text"] = b
            out["bu_conf"] = round(float(row.get("bu_score") or 0), 3)
            out["bu_src"] = "resolver"
    if out.get("bu_src") is None and out["bu_text"] is not None:
        out["bu_src"] = "ocr_cell"
    start = (ban_idx + 1) if ban_idx is not None else (ji_idx + 2)
    # 画数：从 start 到尾部，识别「数词 + 畫」字段
    vals, confs, fields = [], [], []
    pending = []          # 待与「畫」配对的数词格
    last_mark_y1 = None
    for i in range(start, len(cells)):
        c = cells[i]
        if is_mark(c, pending):
            texts = [p["text"] for p in pending]
            v = parse_num(texts)
            fields.append({
                "text": "".join(texts), "value": v,
                "conf": round(float(min([p["score"] for p in pending] or [0])), 3),
                "mark_text": c["text"], "mark_conf": round(float(c["score"]), 3),
                "y": [c["y0"], c["y1"]],
            })
            if v is not None:
                vals.append(v)
                confs.append(round(float(min([p["score"] for p in pending] or [0])), 3))
            pending = []
            last_mark_y1 = c["y1"]
        elif any(ch in NUM for ch in c["text"]):
            pending.append(c)
        else:
            # 非数词非畫：如果已有画数解析，视作葉码/尾部噪声
            if vals:
                break
    raw_hua = row.get("hua") or []
    vals, confs, fields, srcs = merge_hua(vals, confs, fields, raw_hua, row.get("hua_raw"))
    out["hua"] = vals
    out["hua_conf"] = confs
    out["hua_fields"] = fields
    out["hua_src"] = srcs
    out["hua_raw_texts"] = [f["text"] for f in fields] or list(row.get("hua_raw") or [])
    out["hua_resolver"] = list(raw_hua) if raw_hua else []
    out["hua_n"] = len(vals)
    out["hua_has_mark_but_unread"] = bool(fields) and len(vals) < len(fields)
    out["n_hua_marks"] = len(fields)
    # 葉码：最后一个畫之后的格（y 更大）
    tail = []
    for i in range(start, len(cells)):
        c = cells[i]
        if last_mark_y1 is not None and c["y0"] > last_mark_y1 + 20:
            tail.append(c)
        elif last_mark_y1 is None and vals and c["y0"] > (fields[-1]["y"][1] if fields else 0) + 20:
            tail.append(c)
    if tail:
        out["leaf_text"] = "".join(t["text"] for t in tail)
        out["leaf_conf"] = round(float(min(t["score"] for t in tail)), 3)
    if row.get("leaf_ocr"):
        out["leaf_text"] = row["leaf_ocr"]
        out["leaf_conf"] = out["leaf_conf"] or 0.5
    return out


def main():
    rows = [json.loads(l) for l in open(os.path.join(OUT, "headers_full_raw.jsonl"),
                                        encoding="utf-8")]
    rows.sort(key=lambda r: (r["pdf"], r["page"]))
    outs = []
    for r in rows:
        outs.append(extract_row(r))
    path = os.path.join(OUT, "hdr_page_obs.jsonl")
    # 跨页辅助信号：画数「重置」（版心部界处 画数 大→小），供 lead 的部界 DP 用
    prev = None
    for o in outs:
        if prev is not None and prev["vol"] == o["vol"]:
            ph = prev.get("hua") or []
            ch = o.get("hua") or []
            o["prev_page"] = prev["page"]
            o["prev_hua"] = ph
            ph = [v for v in ph if isinstance(v, int)]
            ch = [v for v in ch if isinstance(v, int)]
            o["prev_hua"] = ph
            if ph and ch:
                o["hua_drop"] = bool(min(ph) > max(ch) and (min(ph) - max(ch)) >= 1)
                o["hua_jump"] = int(min(ph) - max(ch))
            else:
                o["hua_drop"] = None
                o["hua_jump"] = None
        else:
            o["prev_page"] = None
            o["prev_hua"] = None
            o["hua_drop"] = None
            o["hua_jump"] = None
        prev = o
    with open(path, "w", encoding="utf-8") as f:
        for o in outs:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    n = len(outs)
    bu = sum(1 for o in outs if o["bu_text"])
    hua = sum(1 for o in outs if o["hua"])
    hua2 = sum(1 for o in outs if len(o["hua"]) >= 2)
    leaf = sum(1 for o in outs if o["leaf_text"])
    drops = sum(1 for o in outs if o.get("hua_drop"))
    print(f"rows={n} bu={bu} ({bu/n:.1%}) hua={hua} ({hua/n:.1%}) "
          f"hua>=2={hua2} leaf={leaf} ({leaf/n:.1%}) hua_drop={drops} -> {path}")


if __name__ == "__main__":
    main()
