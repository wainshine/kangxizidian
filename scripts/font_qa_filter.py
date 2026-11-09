#!/usr/bin/env python3
"""QA 剔除：跑 font_qa → 剔除 render_bad/tiny → 重写 union/mapping/manifest → 输出剔除清单。

用法：.venv/bin/python scripts/font_qa_filter.py --font <ttf> --manifest <manifest.json> \
        --union work/lead/confirmed_union8.json --mapping work/lead/mapping_verified_all8.jsonl \
        --out-dir work/font/build/qa_v201
"""
import argparse, collections, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--union", required=True)
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--excluded-out", default="")
    ap.add_argument("--manifest-out", default="")
    seconds = sys.argv[1:]
    args = ap.parse_args()
    qa = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/font_qa.py"),
                         "--font", args.font, "--manifest", args.manifest,
                         "--outdir", args.out_dir], capture_output=True, text=True)
    rep = json.load(open(os.path.join(args.out_dir, "report.json")))
    bad = sorted(set(d["char"] for d in rep["render_bad"]))
    tiny = sorted(set(ch for ch, w, h in rep["tiny"]))
    excluded = sorted(set(bad) | set(tiny))
    union = json.load(open(args.union))
    for ch in excluded:
        union.pop(ch, None)
    json.dump(union, open(args.union, "w"), ensure_ascii=False)
    rows = collections.OrderedDict()
    for ch, rec in sorted(union.items(), key=lambda kv: (kv[1]["page"], kv[1]["half"])):
        rows.setdefault((rec["page"], rec["half"]), []).append(rec)
    with open(args.mapping, "w", encoding="utf-8") as f:
        for (page, half), lst in rows.items():
            lst.sort(key=lambda r: r["box"][1])
            f.write(json.dumps({"page": page, "half": half, "ci_start": 0, "ci_end": 0,
                                "n": len(lst), "entries": "".join(r["char"] for r in lst),
                                "assigned": [{"char": r["char"], "cand": {"box": r["box"]}}
                                             for r in lst],
                                "in_body": True, "header_ok": None},
                               ensure_ascii=False) + "\n")
    man_path = args.manifest_out or args.manifest
    man = json.load(open(args.manifest))
    for ch in excluded:
        man["chars"].pop(ch, None)
    man["n_chars"] = len(man["chars"])
    json.dump(man, open(man_path, "w"), ensure_ascii=False)
    if args.excluded_out:
        json.dump({"render_bad": bad, "tiny": tiny, "n": len(excluded)},
                  open(args.excluded_out, "w"), ensure_ascii=False, indent=1)
    def is_basic(c):
        return 0x4E00 <= ord(c) <= 0x9FFF
    canon = set(json.loads(l)["char"] for l in open(os.path.join(ROOT, "work/seq/canonical.jsonl")))
    b = sum(1 for c in union if is_basic(c) and c in canon)
    print(json.dumps({"render_bad": len(bad), "tiny": len(tiny), "excluded": len(excluded),
                      "final_chars": len(union), "basic_in_canonical": b,
                      "basic_coverage_pct": round(b / 16567 * 100, 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
