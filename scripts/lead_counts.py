#!/usr/bin/env python3
"""Lead · 字头计数估计器（特征规则，可调参）+ 校准。

用 t1_v2 候选特征（feat）估计每半版字头数，避免只依赖 cls.headword 阈值。
规则（默认）：
  headword if cls.headword>=hw_thr
           and 1.82<=size_ratio<=2.75
           and 0.63<=squareness<=1.55
           and not edge_flag and not margin_strip
           and n_ink_bands<=2
           and ink_ratio<=0.62
用法：
  .venv/bin/python scripts/lead_counts.py --eval          # 对 truth 页 + 分册表评估
  .venv/bin/python scripts/lead_counts.py --out work/lead/counts_v4.jsonl
"""
import argparse, glob, json, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRUTH_PAGES = {  # half -> truth count（人部 = Lead 目检；0006-0009 = 金标）
    "01_0006": {"R": 0, "L": 1},
    "01_0007": {"R": 1, "L": 0},
    "01_0008": {"R": 2, "L": 5},
    "01_0009": {"R": 1, "L": 1},
    "01_0060": {"R": 4, "L": 3},
    "01_0085": {"R": 9, "L": 8},
    "01_0100": {"R": 10, "L": 8},
    "01_0115": {"R": 8, "L": 6},
    "04_0010": {"R": 10, "L": 4},
}


def is_head(c, p):
    f = c["feat"]
    hw = c["cls"].get("headword", 0)
    if hw < p["hw"]:
        return False
    sr = f.get("size_ratio", 0)
    if not (p["sr_lo"] <= sr <= p["sr_hi"]):
        return False
    sq = f.get("squareness", 0)
    if not (p["sq_lo"] <= sq <= p["sq_hi"]):
        return False
    if f.get("edge_flag") or f.get("margin_strip"):
        return False
    if f.get("n_ink_bands", 0) > p["bands"]:
        return False
    if f.get("ink_ratio", 0) > p["ink_max"]:
        return False
    if c["argmax"] == "guwen":
        return False
    if c["cls"].get("guwen", 0) >= p["guwen_excl"]:
        return False
    if c["cls"].get("margin", 0) >= p["margin_excl"]:
        return False
    if c["cls"].get("glue", 0) >= p["glue_excl"]:
        return False
    return True


def load_boxes(boxdir, vols=None):
    out = {}
    for f in sorted(glob.glob(os.path.join(boxdir, "*.json"))):
        page = os.path.basename(f)[:7]
        if vols and page[:2] not in vols:
            continue
        r = json.load(open(f, encoding="utf-8"))
        out[page] = r
    return out


DEFAULTS = dict(hw=0.45, sr_lo=1.82, sr_hi=2.75, sq_lo=0.63, sq_hi=1.55,
                bands=2, ink_max=0.62, guwen_excl=0.5, margin_excl=0.5,
                glue_excl=0.6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", default=os.path.join(ROOT, "work/lead/boxes300"))
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--params", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--calibrate", action="store_true")
    args = ap.parse_args()
    p = dict(DEFAULTS)
    if args.params:
        p.update(json.loads(args.params))
    boxes = load_boxes(args.boxes)
    print(f"pages {len(boxes)}  rule {p}")
    counts = {}
    for page, r in boxes.items():
        for half in ("R", "L"):
            h = r["halves"].get(half) or {}
            counts.setdefault(page, {})[half] = sum(
                1 for c in h.get("cands", []) if is_head(c, p))
    if args.eval:
        err = 0
        tot = 0
        for page, t in TRUTH_PAGES.items():
            got = counts.get(page, {})
            for half in ("R", "L"):
                g = got.get(half, 0)
                tot += 1
                if g != t[half]:
                    err += 1
                    print(f"  X {page}{half} got {g} want {t[half]}")
        print(f"truth pages: {tot-err}/{tot} halves exact")
        # 分册表
        vr = json.load(open(os.path.join(ROOT, "work/seq/volume_radicals.json"),
                            encoding="utf-8"))
        rows = []
        tc = td = 0
        for vol, info in vr["volumes"].items():
            for j in info["juan"]:
                a, b = j["body_pages"]
                d = 0
                for page, c in counts.items():
                    if page[:2] != vol:
                        continue
                    pg = int(page[3:])
                    if a <= pg <= b:
                        d += c["R"] + c["L"]
                can = j["entries"]
                rows.append((vol, j["juan"], can, d, 100 * (d - can) / can))
                tc += can
                td += d
        rows.sort(key=lambda r: r[4])
        print(f"{'卷':14s}{'canon':>7s}{'est':>7s}{'%':>8s}")
        for vol, name, can, d, pct in rows:
            print(f"{vol} {name:8s}{can:>7d}{d:>7d}{pct:>+8.1f}%")
        print(f"{'合计':14s}{tc:>7d}{td:>7d}{100*(td-tc)/tc:>+8.1f}%  MAE={sum(abs(r[4]) for r in rows)/len(rows):.1f}%")
    if args.calibrate:
        vr = json.load(open(os.path.join(ROOT, "work/seq/volume_radicals.json"),
                            encoding="utf-8"))
        for vol, info in vr["volumes"].items():
            for j in info["juan"]:
                a, b = j["body_pages"]
                keys = [(page, half) for page in counts if page[:2] == vol
                        and a <= int(page[3:]) <= b for half in ("R", "L")]
                got = sum(counts[page][half] for page, half in keys)
                delta = j["entries"] - got
                if not keys or delta == 0:
                    continue
                # 按现计数比例分配整数增减
                tot = max(1, got)
                shares = []
                for k in keys:
                    share = delta * counts[k[0]][k[1]] / tot
                    shares.append([k, int(round(share)), share])
                diff = sum(x[1] for x in shares)
                # 余数补到小数部分最大的
                order = sorted(range(len(shares)), key=lambda i: -(shares[i][2] - shares[i][1]))
                i = 0
                while diff != 0 and order:
                    idx = order[i % len(order)]
                    shares[idx][1] += 1 if diff > 0 else -1
                    diff += -1 if diff > 0 else 1
                    i += 1
                for k, d, _ in shares:
                    counts[k[0]][k[1]] = max(0, counts[k[0]][k[1]] + d)
                print(f"  calib {vol} {j['juan']}: {got} -> {j['entries']} (delta {delta:+d})")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for page in sorted(counts):
                f.write(json.dumps({"page": page, **counts[page]}, ensure_ascii=False) + "\n")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
