#!/usr/bin/env python3
"""A2 · 书眉读数后处理：序列约束求解（集名卷 / 部名 / 画数）。

输入：work/seq/headers_raw.jsonl（scripts/header_read.py 的单页原始读数）
输出：work/seq/headers.jsonl（Lead solver 口径）：
  {"page":"01_0006","half":"L","ji":"子集上","bu":"一部","hua":[1,2],"hua_l":2,
   "leaf_no":1,"conf":0.9,"errors":[],"step":"raw|rides|dp"}

约束（全部来自刻本自身结构，非数据集顺序）：
1. 集名卷：PDF01–12 = 册号（子…亥）+ page_roles body 段（上/中/下）；PDF13 = 补遗 12 节
   顺序（子…亥 補遺，后接 子…亥 備考），用「集」字 OCR + 補/考 OCR 做单调 DP 定节。
2. 部名：214 部首在全书顺序固定且单调不减；对每页 rad OCR 作发射，单调 DP（允许
   跳 1–3 部，罚分），得到每页部首。低置信（无 OCR 命中且两侧证据弱）→ null。
3. 画数：同一部内 部外笔画单调不减、每页只有 0/1/2 个画数字段（2 个 = 跨分界页，
   第一字段 = R 半版组，第二字段 = L 半版组）；对每部页序列做单调 DP（状态 0–44），
   发射来自 OCR 读数，并利用「第一字段 = 上一页 L 组」约束。
4. 葉码：PDF01–12 = 扫描页 − 5（owner 20 页实证）；PDF13 用 OCR 尾巴数字；PDF00 null。
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "work", "seq")

RAD214 = ("一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕"
          "大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰"
          "月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢"
          "石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言"
          "谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨靑非面革韋韭音頁風飛食首香馬"
          "骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠")
RAD_IDX = {c: i for i, c in enumerate(RAD214)}
VOL_JI = {"01": "子", "02": "丑", "03": "寅", "04": "卯", "05": "辰", "06": "巳",
          "07": "午", "08": "未", "09": "申", "10": "酉", "11": "戌", "12": "亥"}
JI_ORDER = "子丑寅卯辰巳午未申酉戌亥"


# --------------------------------------------------------------------------- #
def load_raw(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        rows.append(json.loads(line))
    rows.sort(key=lambda r: (r["pdf"], r["page"]))
    return rows


def load_roles():
    p = os.path.join(ROOT, "work", "lead", "page_roles.jsonl")
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    byv = {}
    for r in rows:
        byv.setdefault(r["vol"], []).append((r["page"], r["role"]))
    info = {}
    for vol, rs in byv.items():
        rs.sort()
        runs, start = [], None
        for pg, role in rs:
            if role == "body" and start is None:
                start = pg
            if role != "body" and start is not None:
                runs.append((start, pg - 1))
                start = None
        if start is not None:
            runs.append((start, rs[-1][0]))
        info[vol] = runs
    return info


# --------------------------------------------------------------------------- #
# 1. 集名卷
# --------------------------------------------------------------------------- #
def resolve_ji(rows, roles):
    for r in rows:
        vol, page = r["pdf"], r["page"]
        if vol in VOL_JI:
            runs = roles.get(vol, [])
            got = None
            for i, (a, b) in enumerate(runs[:3]):
                if a <= page <= b:
                    got = f"{VOL_JI[vol]}集{'上中下'[i]}"
                    break
            r["ji"] = got
        elif vol == "13":
            r["ji"] = None   # 由 DP 填
        else:
            r["ji"] = None

    # PDF13：补遗 12 节 → 备考 12 节，单调 DP
    r13 = [r for r in rows if r["pdf"] == "13"]
    if r13:
        states = [(s, j) for s in ("補遺", "備考") for j in JI_ORDER]  # 24
        n = len(r13)
        NEG = -1e9
        score = [[NEG] * len(states) for _ in range(n + 1)]
        back = [[-1] * len(states) for _ in range(n + 1)]
        for k in range(len(states)):
            score[0][k] = 0.0     # 起节未知：不强制 子集補遺
        for i, r in enumerate(r13):
            obs_ji = r.get("ji_char")
            obs_suf = r.get("suffix")
            for si, (sec, jc) in enumerate(states):
                if score[i][si] <= NEG / 2:
                    continue
                for sj in range(si, len(states)):
                    if sj - si > 2:
                        break
                    pen = 0.0 if sj == si else -1.2 * (sj - si)
                    em = 0.0
                    if obs_ji and obs_ji == jc:
                        em += 2.0
                    elif obs_ji:
                        em -= 1.0
                    if obs_suf in ("補遺", "備考"):
                        em += 2.0 if obs_suf == sec else -1.5
                    v = score[i][si] + em + pen
                    if v > score[i + 1][sj]:
                        score[i + 1][sj] = v
                        back[i + 1][sj] = si
        best = max(range(len(states)), key=lambda k: score[n][k])
        assign = [best] * n
        for i in range(n, 0, -1):
            assign[i - 1] = best
            best = back[i][best]
            if best < 0:
                best = assign[i - 1]
        for r, si in zip(r13, assign):
            sec, jc = states[si]
            r["ji"] = f"{jc}集{sec}"


# --------------------------------------------------------------------------- #
# 2. 部名单调 DP（PDF01–12）
# --------------------------------------------------------------------------- #
def resolve_bu(rows, roles):
    body = []
    for r in rows:
        if r["pdf"] in VOL_JI:
            runs = roles.get(r["pdf"], [])
            is_body = any(a <= r["page"] <= b for a, b in runs)
            r["is_body"] = is_body
            if is_body:
                body.append(r)
        elif r["pdf"] == "13":
            r["is_body"] = r.get("section") in ("buqi", "beikao") or bool(r.get("ji"))
        else:
            r["is_body"] = False
    if not body:
        return
    if len(body) < 3000:
        # 稀疏样本（如仅 owner 20 页）：单调 DP 无连续约束会退化 → 直接用 raw 读取
        for r in body:
            obs = r.get("bu")
            if obs is None:
                raw = r.get("bu_raw") or ""
                for ch in raw:
                    if ch in RAD_IDX:
                        obs = ch
                        break
            r["bu"] = (obs + "部") if obs else None
            r["rad_k"] = RAD_IDX.get(obs) if obs else None
            r["bu_conf"] = 0.9 if obs else 0.2
        return
    N = len(body)
    S = 214
    NEG = -1e9
    score = [[NEG] * S for _ in range(N + 1)]
    back = [[-1] * S for _ in range(N + 1)]
    # 首部 = 一部（子集上首页）
    score[0][0] = 0.0
    for i, r in enumerate(body):
        obs = r.get("bu")
        if obs is None:
            raw = r.get("bu_raw") or ""
            for ch in raw:
                if ch in RAD_IDX:
                    obs = ch
                    break
        k_obs = RAD_IDX.get(obs) if obs else None
        conf = r.get("bu_score") or 0.0
        for si in range(S):
            base = score[i][si]
            if base <= NEG / 2:
                continue
            for sj in range(si, min(S, si + 4)):
                pen = 0.0 if sj == si else -1.5 * (sj - si)
                em = 0.0
                if k_obs is not None:
                    if sj == k_obs:
                        em = 2.2 * min(1.0, 0.4 + conf)
                    else:
                        em = -0.5
                v = base + pen + em
                if v > score[i + 1][sj]:
                    score[i + 1][sj] = v
                    back[i + 1][sj] = si
    best = max(range(S), key=lambda k: score[N][k])
    assign = [best] * N
    for i in range(N, 0, -1):
        assign[i - 1] = best
        best = back[i][best]
        if best < 0:
            best = assign[i - 1]
    for r, k in zip(body, assign):
        r["rad_k"] = k
        r["bu"] = RAD214[k] + "部"
        # 置信：本页 OCR 命中且与 DP 一致
        ok = (r.get("bu") == r.get("bu_dp"))  # unused
        r["bu_conf"] = 0.9 if (r.get("bu_raw") and RAD_IDX.get(r.get("bu"))
                               == k) else 0.5


# --------------------------------------------------------------------------- #
# 3. 画数单调 DP（每部内）
# --------------------------------------------------------------------------- #
HUAMAX = 44


def raw_hua_values(r):
    vals = r.get("hua") or []
    return [v for v in vals if isinstance(v, int)]


def resolve_hua(rows):
    body = [r for r in rows if r.get("rad_k") is not None]
    # 按部切段
    runs = []
    cur = []
    for r in body:
        if cur and r["rad_k"] != cur[-1]["rad_k"]:
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)

    if len(body) < 3000:
        # 非全量：不做部内单调 DP（序列不完整会失真），直接用原始读数
        for r in body:
            vals = raw_hua_values(r)
            basis = r.get("hua_basis") or []
            if vals:
                r["hua"] = vals if len(vals) > 1 else [vals[0]]
                r["hua_l"] = vals[-1]
                b0 = basis[-1] if basis else None
                r["hua_conf"] = {"ocr": 0.9, "region": 0.7, "ocr_weak": 0.6,
                                 "flat": 0.5}.get(b0, 0.7)
            else:
                r["hua"] = None
                r["hua_l"] = None
                r["hua_conf"] = 0.3
        return
    BASIS_W = {"ocr": 2.8, "ocr_weak": 1.4, "region": 1.2, "flat": 0.4}
    for run in runs:
        # 每页状态 = L 半版组；单调不减
        n = len(run)
        S = HUAMAX + 1
        NEG = -1e9
        score = [[NEG] * S for _ in range(n + 1)]
        back = [[-1] * S for _ in range(n + 1)]
        score[0][0] = 0.0
        for i, r in enumerate(run):
            vals = raw_hua_values(r)
            basis = (r.get("hua_basis") or [])
            w = 1.0
            if basis:
                ws = [BASIS_W.get(b, 0.8) for b in basis]
                w = max(ws) if ws else 1.0
            hint_l = vals[-1] if vals else None
            hint_r = vals[0] if len(vals) >= 2 else None
            for si in range(S):
                base = score[i][si]
                if base <= NEG / 2:
                    continue
                for sj in range(si, min(S, si + 3)):
                    pen = 0.0 if sj == si else -0.8 * (sj - si)
                    em = 0.0
                    if hint_l is not None:
                        em += w if hint_l == sj else -0.5 * w
                    if hint_r is not None and si == hint_r and sj == si:
                        em += 0.4   # 双字段页第一字段 = 上一页 L 组
                    elif i == 0 and r.get("hua") is None:
                        em += 0.5 if sj == 0 else 0.0
                    v = base + pen + em
                    if v > score[i + 1][sj]:
                        score[i + 1][sj] = v
                        back[i + 1][sj] = si
        best = max(range(S), key=lambda k: score[n][k])
        assign = [best] * n
        for i in range(n, 0, -1):
            assign[i - 1] = best
            best = back[i][best]
            if best < 0:
                best = assign[i - 1]
        prev = None
        for r, v in zip(run, assign):
            vals = raw_hua_values(r)
            r["hua_l"] = v
            if vals and len(vals) >= 2:
                r["hua"] = [vals[0], v]
            elif v is not None:
                r["hua"] = [v]
            basis = (r.get("hua_basis") or [])
            b0 = basis[-1] if basis else None
            if vals and vals[-1] == v:
                r["hua_conf"] = {"ocr": 0.9, "region": 0.7, "ocr_weak": 0.6,
                                 "flat": 0.5}.get(b0, 0.7)
            elif vals:
                r["hua_conf"] = 0.3
            else:
                r["hua_conf"] = 0.35
            prev = v


# --------------------------------------------------------------------------- #
# 4. 集名/部名/葉码/输出
# --------------------------------------------------------------------------- #
def finalize(rows):
    out = []
    for r in rows:
        vol, page = r["pdf"], r["page"]
        key = f"{vol}_{page:04d}"
        ji = r.get("ji")
        bu = r.get("bu")
        if bu is None and r.get("rad_k") is not None:
            bu = RAD214[r["rad_k"]] + "部"
        hua = r.get("hua")
        if hua is not None and not isinstance(hua, list):
            hua = [hua]
        leaf_no = None
        if vol in VOL_JI:
            leaf_no = page - 5 if page > 5 else None
        elif vol == "13":
            lo = r.get("leaf_ocr")
            if lo:
                leaf_no = cn2int(lo)
        confs = []
        if ji:
            confs.append(0.95)
        if bu:
            confs.append(r.get("bu_conf") or 0.6)
        if hua is not None:
            confs.append(r.get("hua_conf") or 0.5)
        if leaf_no is not None:
            confs.append(0.95 if vol in VOL_JI else 0.5)
        conf = round(sum(confs) / len(confs), 3) if confs else 0.05
        errs = r.get("errors") or []
        if errs:
            conf = round(conf * max(0.35, 1.0 - 0.12 * len(errs)), 3)
        if bu is None:
            conf = round(conf * 0.8, 3)
        if hua is None:
            conf = round(conf * 0.9, 3)
        out.append({
            "page": key, "half": "L",
            "ji": ji, "bu": bu, "hua": hua,
            "hua_l": r.get("hua_l"),
            "leaf_no": leaf_no,
            "conf": conf,
            "errors": r.get("errors") or [],
            "section": r.get("section") or ("zheng" if vol in VOL_JI else None),
        })
    return out


def cn2int(s):
    CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
          "十": 10, "廿": 20, "卅": 30, "百": 100, "千": 1000}
    if not s:
        return None
    s = "".join(ch for ch in s if ch in CN)
    if not s:
        return None
    if s in CN:
        return CN[s]
    total, cur = 0, 0
    for ch in s:
        if ch == "百":
            total += (cur if cur else 1) * 100
            cur = 0
        elif ch == "十":
            total += (cur if cur else 1) * 10
            cur = 0
        elif ch == "廿":
            total += 20
            cur = 0
        elif ch == "卅":
            total += 30
            cur = 0
        else:
            cur = CN.get(ch, 0)
    return total + cur


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(OUT_DIR, "headers_raw.jsonl"))
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "headers.jsonl"))
    ap.add_argument("--eval-gold", action="store_true")
    args = ap.parse_args()

    rows = load_raw(args.raw)
    roles = load_roles()
    print(f"raw rows {len(rows)}")
    resolve_ji(rows, roles)
    resolve_bu(rows, roles)
    resolve_hua(rows)
    out = finalize(rows)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    low = [r for r in out if r["conf"] < 0.55 or r["errors"]]
    lowpath = os.path.join(OUT_DIR, "headers_lowconf.jsonl")
    with open(lowpath, "w", encoding="utf-8") as f:
        for r in low:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} rows -> {args.out}; lowconf {len(low)} -> {lowpath}")
    stats = summarize(out)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    if args.eval_gold:
        evaluate(out)


def summarize(out):
    import collections
    c = collections.Counter()
    per = collections.Counter()
    for r in out:
        c["n"] += 1
        per[r["page"][:2] + "_n"] += 1
        if r["ji"]:
            c["ji"] += 1
            per[r["page"][:2] + "_ji"] += 1
        if r["bu"]:
            c["bu"] += 1
            per[r["page"][:2] + "_bu"] += 1
        if r["hua"]:
            c["hua"] += 1
            per[r["page"][:2] + "_hua"] += 1
        if r["leaf_no"] is not None:
            c["leaf"] += 1
        if not r["errors"]:
            c["clean"] += 1
    return {"total": dict(c), "per_pdf": dict(per)}


def load_gold():
    d = json.load(open(os.path.join(ROOT, "work", "t2", "margin_labels_full.json"),
                       encoding="utf-8"))
    return d["pages"]


def gold_hua(hs):
    from collections import OrderedDict
    CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
          "十": 10, "廿": 20, "卅": 30, "百": 100}
    if not hs:
        return None
    out = []
    for h in hs:
        v = cn2int(h.rstrip("?"))
        if v is None:
            return None
        out.append(v)
    return out


def gold_leaf(leaf):
    if not leaf:
        return None
    s = re.sub(r"[（(].*?[)）]", "", leaf).rstrip("?")
    return cn2int(s)


def evaluate(out):
    import collections
    gold = load_gold()
    by = {r["page"]: r for r in out}
    n = 0
    cnt = collections.Counter()
    print("\n== owner 20 页评测（序列修正后）==")
    for key, g in gold.items():
        r = by.get(key)
        if r is None:
            print(f" {key}: NO ROW"); continue
        n += 1
        L = g["L"]
        ji_e = L.get("ji")
        bu_e = (L.get("bu") or "").rstrip("?").replace("部", "") if L.get("bu") else None
        hua_e = gold_hua(L.get("hua"))
        leaf_e = gold_leaf(g.get("leaf"))
        passed = []
        if ji_e:
            cnt["ji_n"] += 1
            if r["ji"] == ji_e:
                cnt["ji"] += 1; passed.append("ji")
        if bu_e:
            cnt["bu_n"] += 1
            if r["bu"] == bu_e + "部":
                cnt["bu"] += 1; passed.append("bu")
        if hua_e is not None:
            cnt["hua_n"] += 1
            if r["hua"] == hua_e:
                cnt["hua"] += 1; passed.append("hua")
        if leaf_e is not None and r["leaf_no"] is not None:
            cnt["leaf_n"] += 1
            if r["leaf_no"] == leaf_e:
                cnt["leaf"] += 1; passed.append("leaf")
        print(f" {key}: ji={r['ji']} vs {ji_e} | bu={r['bu']} vs {bu_e} | "
              f"hua={r['hua']} vs {hua_e} | leaf={r['leaf_no']} vs {leaf_e} | {passed}")
    print(f"\n集名 {cnt['ji']}/{cnt['ji_n']}  部名 {cnt['bu']}/{cnt['bu_n']}  "
          f"画数 {cnt['hua']}/{cnt['hua_n']}  葉码 {cnt['leaf']}/{cnt['leaf_n']}")


if __name__ == "__main__":
    main()
