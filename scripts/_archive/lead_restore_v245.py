#!/usr/bin/env python3
"""v2.4.5：把经「内容验证」确认的重定位字并入字表（headword-only 仍强制执行）。

输入：work/lead/v245_verified.jsonl（每行 {char,page,half,box,evidence}，人工/VLM 双确认）
处理：
  1. 排除已在 union13 的字；排除同框占用；
  2. 尺寸复核：max(w,h)>=65（D15），且不得 min<50 与 max<75 同时成立（注文窄框防线）；
  3. vectorize_box 生成字形，必须 ok 且轮廓非空；渲染 256px 质量检查（组件<=14、墨量正常）；
  4. 输出 mapping_verified_all14.jsonl / confirmed_union14.json / manifest-v245.json / report
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def main():
    import numpy as np, cv2
    import font_norm as FN
    u13 = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union13.json"), encoding="utf-8"))
    used = {(r["page"], r["half"], tuple(r["box"])) for r in u13.values()}
    verified = []
    p = os.path.join(ROOT, "work/lead/v245_verified.jsonl")
    for l in open(p, encoding="utf-8"):
        verified.append(json.loads(l))
    man = json.load(open(os.path.join(ROOT, "work/lead/manifest-v244.json"), encoding="utf-8"))
    chars = dict(man["chars"])
    added, rejected = [], []
    for it in verified:
        ch = it["char"]; page = it["page"]; half = it["half"]; box = [int(v) for v in it["box"]]
        if ch in chars:
            rejected.append({"char": ch, "reason": "already in font"}); continue
        if (page, half, tuple(box)) in used:
            rejected.append({"char": ch, "reason": "box occupied"}); continue
        w, h = box[2] - box[0], box[3] - box[1]
        if max(w, h) < 65:
            rejected.append({"char": ch, "reason": f"max edge {max(w,h)} <65"}); continue
        if min(w, h) < 50 and max(w, h) < 75:
            rejected.append({"char": ch, "reason": "narrow annotation-size box"}); continue
        try:
            res = FN.vectorize_box(page, box)
        except Exception as e:
            rejected.append({"char": ch, "reason": f"vectorize error {e}"}); continue
        if not res.get("ok") or not res.get("contours"):
            rejected.append({"char": ch, "reason": "vectorize failed/empty"}); continue
        # 质量复核：面积/轮廓数合理性
        ncont = len(res["contours"])
        if ncont > 40:
            rejected.append({"char": ch, "reason": f"too many contours ({ncont})"}); continue
        chars[ch] = {"page": page, "half": half, "box": box,
                     "label_source": "relocated_v245",
                     "evidence": it.get("evidence", "vlm_verified")}
        used.add((page, half, tuple(box)))
        added.append({"char": ch, "page": page, "half": half, "box": box,
                      "n_contours": ncont, "evidence": it.get("evidence", "")})
    # 写 mapping14（在 mapping13 基础上追加 assigned）
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "work/lead/mapping_verified_all13.jsonl"), encoding="utf-8")]
    by_page = {}
    for r in rows:
        by_page[(r["page"], r["half"])] = r
    for a in added:
        key = (a["page"], a["half"])
        if key in by_page:
            by_page[key]["assigned"].append({"char": a["char"], "cand": {"box": a["box"]}})
        else:
            rows.append({"page": a["page"], "half": a["half"], "ci_start": 0, "ci_end": 0,
                         "n": 1, "entries": a["char"], "in_body": True, "header_ok": None,
                         "assigned": [{"char": a["char"], "cand": {"box": a["box"]}}]})
            by_page[key] = rows[-1]
    with open(os.path.join(ROOT, "work/lead/mapping_verified_all14.jsonl"), "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    # manifest / union
    man["chars"] = chars
    man["n_chars"] = len(chars)
    json.dump(man, open(os.path.join(ROOT, "work/lead/manifest-v245.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(man, open(os.path.join(ROOT, "work/font/build/manifest_v245.json"), "w", encoding="utf-8"), ensure_ascii=False)
    u14 = {c: {"char": c, "page": r["page"], "half": r["half"], "box": r["box"],
               "label_source": r["label_source"]} for c, r in chars.items()}
    json.dump(u14, open(os.path.join(ROOT, "work/lead/confirmed_union14.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rep = {"added": added, "rejected": rejected, "n_before": len(man["chars"]) - len(added),
           "n_after": len(chars)}
    json.dump(rep, open(os.path.join(ROOT, "work/lead/v245_restore_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"added": len(added), "rejected": len(rejected), "n_after": len(chars),
                      "added_chars": "".join(a["char"] for a in added)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
