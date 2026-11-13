#!/usr/bin/env python3
"""release_metrics.py — 跨版本发布指标对比（v2.6.2 vs v2.6.1 / v2.5.8，发版通用）。

指标（全部可复算）：
  1 规模/覆盖：chars、基本区覆盖、目标表（canonical 唯一基本区 16,567）覆盖、缺口；
  2 质量闸：font_qa（PASS/FAIL）、glyph_frame_gate（字形级框线数）、
    content_loss_gate（相对基线 v2.5.8 的 damaged 数）；
  3 源级扫描：缺件 / 框线逃逸（读该版本 gate-report 或扫描产物；无则 null）；
  4 页几何：bad_boxes / empty_assign（读 gate-report；无则 null）；
  5 快闸：fast_gate pass（读报告；无则 null）；
  6 变更规模：与上一版本相比渲染字形有变化的字数（可选，读 diff JSON）。

"更好"的判定（见 docs/RELEASE-METRICS.md）：
  - 覆盖不减（chars、目标覆盖、缺口不扩大）；
  - font_qa 不退化、glyph_frame 不增加、content damaged 不增加；
  - 已知债逐项披露且不新增 P0/P1 未解释项；
  - 所有口径变化（扫描/阈值/参考字体）必须同报告披露。

用法：
  .venv/bin/python scripts/release_metrics.py --out work/lead/release-metrics.json
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

VERSIONS = [
    {"label": "v2.5.8", "font": "work/font/build/KangXiKai-v2.5.8.ttf",
     "manifest": "work/font/build/manifest_v258.json",
     "gate_report": None, "fast_gate": None,"diff_from_prev": None},
    {"label": "v2.6.1", "font": "release/KangXiKai-v2.6.1/KangXiKai-Regular-v2.6.1.ttf",
     "manifest": "release/KangXiKai-v2.6.1/manifest-v261.json",
     "gate_report": "release/KangXiKai-v2.6.1/gate-report-v261.json",
     "fast_gate": None, "diff_from_prev": None},
    {"label": "v2.6.2", "font": "work/font/build/KangXiKai-v2.6.2.ttf",
     "manifest": "work/font/build/manifest_v262.json",
     "gate_report": "work/lead/gate-report-v262.json",
     "fast_gate": "work/lead/fast-gate-v262.json",
     "diff_from_prev": "work/lead/diff-v261-v262.json"},
]
BASELINE = "v2.5.8"


def rel(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def run(cmd):
    r = subprocess.run([PY] + cmd, cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout or "")[-1500:], (r.stderr or "")[-800:]


def canonical_target():
    chars = set()
    with open(os.path.join(ROOT, "work/seq/canonical.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            ch = r.get("char")
            if ch and len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
                chars.add(ch)
    return chars


def main():
    out = os.path.join(ROOT, "work/lead/release-metrics.json")
    if "--out" in sys.argv:
        out = rel(sys.argv[sys.argv.index("--out") + 1])
    target = canonical_target()
    basic = {chr(c) for c in range(0x4E00, 0xA000)}
    rows = []
    for v in VERSIONS:
        font = rel(v["font"]); man = json.load(open(rel(v["manifest"]), encoding="utf-8"))
        mchars = set(man["chars"])
        item = {"label": v["label"], "font": v["font"], "font_sha256": None,
                "chars": len(mchars),
                "basic_covered": len(mchars & basic), "basic_total": len(basic),
                "target_covered": len(mchars & target), "target_total": len(target),
                "gap": len(target - mchars)}
        import hashlib
        item["font_sha256"] = hashlib.sha256(open(font, "rb").read()).hexdigest()
        # font_qa
        rc, so, se = run(["scripts/font_qa.py", "--font", font, "--manifest", rel(v["manifest"]),
                          "--outdir", f"/tmp/metrics-qa-{v['label']}"])
        item["font_qa"] = "PASS" if rc == 0 else "FAIL"
        # glyph_frame_gate
        gf = f"/tmp/metrics-gf-{v['label']}.json"
        rc, so, se = run(["scripts/glyph_frame_gate.py", "--font", font, "--manifest", rel(v["manifest"]), "--out", gf])
        item["glyph_frame_flagged"] = len(json.load(open(gf)).get("flagged") or []) if os.path.exists(gf) else None
        # content vs baseline
        if v["label"] == BASELINE:
            item["content_damaged_vs_baseline"] = 0
        else:
            cl = f"/tmp/metrics-cl-{v['label']}.json"
            rc, so, se = run(["scripts/content_loss_gate.py",
                              rel(VERSIONS[0]["font"]), font,
                              rel(VERSIONS[0]["manifest"]), cl])
            item["content_damaged_vs_baseline"] = len(json.load(open(cl))) if os.path.exists(cl) else None
        # recorded gate numbers
        item["missing_flagged"] = item["frame_escape_flagged"] = None
        item["bad_boxes"] = item["empty_assign_halves"] = None
        item["fast_gate"] = None
        if v.get("gate_report") and os.path.exists(rel(v["gate_report"])):
            gr = json.load(open(rel(v["gate_report"]), encoding="utf-8"))
            for s in gr.get("steps") or []:
                det = s.get("detail") or {}
                if s.get("step") == "scan_missing_parts":
                    item["missing_flagged"] = det.get("flagged")
                elif s.get("step") == "frame_escape":
                    item["frame_escape_flagged"] = det.get("flagged")
                elif s.get("step") == "page_geometry_gate":
                    cnt = det.get("counts") or {}
                    item["bad_boxes"] = cnt.get("bad_boxes")
                    item["empty_assign_halves"] = cnt.get("empty_assign_halves")
        pg_rep = os.path.join(ROOT, "work", "lead", f"page-geometry-gate-{v['label'].replace('.', '')}.json")
        if os.path.exists(pg_rep):
            cnt = (json.load(open(pg_rep, encoding="utf-8")) or {}).get("counts") or {}
            item["bad_boxes"] = cnt.get("bad_boxes")
            item["empty_assign_halves"] = cnt.get("empty_assign_halves")
        if v.get("fast_gate") and os.path.exists(rel(v["fast_gate"])):
            fg = json.load(open(rel(v["fast_gate"]), encoding="utf-8"))
            item["fast_gate"] = "PASS" if fg.get("pass") else "FAIL"
        if v.get("diff_from_prev") and os.path.exists(rel(v["diff_from_prev"])):
            item["changed_glyphs_vs_prev"] = len(json.load(open(rel(v["diff_from_prev"]), encoding="utf-8")))
        else:
            item["changed_glyphs_vs_prev"] = None
        rows.append(item)
        print(json.dumps(item, ensure_ascii=False))
    report = {"generated_at": "2026-11-13", "baseline": BASELINE,
              "target_set": "work/seq/canonical.jsonl unique CJK basic",
              "versions": rows}
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # markdown
    md = ["# 版本对比指标（release_metrics.py 生成）", "",
          "| 指标 | " + " | ".join(r["label"] for r in rows) + " |",
          "|---|" + "---|" * len(rows)]
    fields = [("chars", "字形数"), ("basic_covered", "基本区覆盖/20,992"),
              ("target_covered", "目标表覆盖/16,567"), ("gap", "缺口"),
              ("font_qa", "font_qa"), ("glyph_frame_flagged", "字形级框线"),
              ("content_damaged_vs_baseline", "内容 damaged（vs v2.5.8）"),
              ("missing_flagged", "缺件扫描"), ("frame_escape_flagged", "框线逃逸"),
              ("bad_boxes", "页几何 bad_boxes"), ("empty_assign_halves", "空指派半版"),
              ("fast_gate", "fast_gate"), ("changed_glyphs_vs_prev", "相对上一版变化字")]
    for k, name in fields:
        md.append(f"| {name} | " + " | ".join(str(r.get(k)) for r in rows) + " |")
    mdout = os.path.join(ROOT, "work/lead/release-metrics.md")
    open(mdout, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps({"out": os.path.relpath(out, ROOT), "md": os.path.relpath(mdout, ROOT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
