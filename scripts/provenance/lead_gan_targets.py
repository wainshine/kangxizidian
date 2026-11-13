#!/usr/bin/env python3
"""生成完整「GAN 补全目标」清单（不再是 80 样本）+ 按原因分桶。

桶定义：
  B_strict_dropped  曾被 union 收录、v2.4.0 严格闸剔除（smallsrc / 框 max<65 / small 来源）
  B_early_regression 更早 union 有、后续清理/圈号/挂起丢失（v1.x 回归）
  E_never_aligned   从未进入 union（映射/质量闸从未采纳）
另附：c14 空闲候选数（65..145 双维）、同字候选总数（不限尺寸）。

输出：work/lead/v244_gan_targets.json + 随包副本
  {generated_at, standard, total_missing, buckets{}, missing_list[{char,ci,rad,bu,bucket,drop_reason,c14_free_headword_cands,c14_all_cands}],
   sha256_of_list}
"""
import collections, hashlib, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    canon = [json.loads(l) for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8")]
    def basic(c): return 0x4E00 <= ord(c) <= 0x9FFF
    target = list(dict.fromkeys(e["char"] for e in canon if basic(e["char"])))
    ci = {e["char"]: i for i, e in enumerate(canon)}
    u13 = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union13.json"), encoding="utf-8"))
    u12 = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union12.json"), encoding="utf-8"))
    u8 = json.load(open(os.path.join(ROOT, "work/lead/confirmed_union8.json"), encoding="utf-8"))
    drop = {x["char"]: x.get("reason", "") for x in
            json.load(open(os.path.join(ROOT, "work/lead/v240_strict_report.json"), encoding="utf-8"))["dropped_list"]}
    used = collections.defaultdict(set)
    for c, r in u13.items():
        used[(r["page"], r["half"])].add(tuple(r["box"]))
    c14 = collections.defaultdict(list)
    for l in open(os.path.join(ROOT, "work/map/charalign14/mapping.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        for a in r.get("assigned", []):
            ch = a.get("char"); box = (a.get("cand") or {}).get("box")
            if ch and box:
                b = tuple(int(v) for v in box)
                w, h = b[2] - b[0], b[3] - b[1]
                free = b not in used[(r["page"], r["half"])]
                c14[ch].append({"w": w, "h": h, "free": free,
                                "headword_size": bool(65 <= w <= 145 and 65 <= h <= 145)})
    missing = [c for c in target if c not in u13]
    rows = []
    buckets = collections.Counter()
    for c in missing:
        if c in u12:
            bucket = "B_strict_dropped"
        elif c in u8:
            bucket = "B_early_regression"
        else:
            bucket = "E_never_aligned"
        buckets[bucket] += 1
        cands = c14.get(c, [])
        free_hw = sum(1 for x in cands if x["free"] and x["headword_size"])
        rows.append({"char": c, "ci": ci[c],
                     "rad": canon[ci[c]].get("rad"), "bu": canon[ci[c]].get("bu_strokes"),
                     "bucket": bucket, "drop_reason": drop.get(c, ""),
                     "c14_all_cands": len(cands), "c14_free_headword_cands": free_hw})
    payload = {
        "standard": "headword-only（D15）：缺口不补假覆盖；B/E 桶须先重定位真字头，GAN 仅补真缺",
        "generated_from": ["work/seq/canonical.jsonl", "work/lead/confirmed_union13.json",
                           "work/lead/confirmed_union12.json", "work/lead/confirmed_union8.json",
                           "work/lead/v240_strict_report.json", "work/map/charalign14/mapping.jsonl"],
        "total_missing": len(rows),
        "buckets": dict(buckets),
        "recoverable_candidates": sum(1 for r in rows if r["c14_free_headword_cands"] > 0),
        "missing_list": rows,
    }
    h = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    payload["sha256_of_list"] = h
    out = os.path.join(ROOT, "work/lead/v244_gan_targets.json")
    json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps({"total": len(rows), "buckets": dict(buckets),
                      "recoverable_candidates": payload["recoverable_candidates"],
                      "sha256": h[:16], "out": out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
