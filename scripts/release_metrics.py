#!/usr/bin/env python3
"""release_metrics.py — 跨版本发布指标对比（2.6 补丁线，发版通用）。

**v2.6.3 起参数化**（T0.5）：
  - `--versions-json` 可覆盖内置 VERSIONS（可选）；
  - `--out/--md-out` 显式指定输出（默认 work/lead/release-metrics.json/.md）；
  - 缺失字体/manifest 的版本不再崩溃：该行标 null 并 WARN（便于 v2.6.3 发布前先出对比表）。

"更好"的判定（见 docs/reference/RELEASE-METRICS.md）：
  - 覆盖不减（chars、目标覆盖、缺口不扩大）；
  - font_qa 不退化、glyph_frame 不增加、content damaged 不增加；
  - 已知债逐项披露且不新增 P0/P1 未解释项；
  - 所有口径变化（扫描/阈值/参考字体）必须同报告披露。

注意：`相对上一版变化字` 必须由「精确 glyf 轮廓 diff」生成（audit4 DATA-401：旧 617 是旧候选
阈值筛集、不可复算）；本脚本只读 diff JSON，不自行生成。v2.6.2 历史行保留旧值但见 RELEASE-METRICS 注记。
"""
import argparse, datetime, hashlib, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

VERSIONS = [
    {"label": "v2.5.8", "font": "work/font/build/KangXiKai-v2.5.8.ttf",
     "manifest": "work/font/build/manifest_v258.json",
     "gate_report": None, "fast_gate": None, "diff_from_prev": None},
    {"label": "v2.6.1", "font": "release/KangXiKai-v2.6.1/KangXiKai-Regular-v2.6.1.ttf",
     "manifest": "release/KangXiKai-v2.6.1/manifest-v261.json",
     "gate_report": "release/KangXiKai-v2.6.1/gate-report-v261.json",
     "fast_gate": None, "diff_from_prev": None},
    {"label": "v2.6.2", "font": "work/font/build/KangXiKai-v2.6.2.ttf",
     "manifest": "work/font/build/manifest_v262.json",
     "gate_report": "work/lead/gate-report-v262.json",
     "fast_gate": "work/lead/fast-gate-v262.json",
     "diff_from_prev": "work/lead/diff-v261-v262.json"},
    {"label": "v2.6.3", "font": "work/font/build/KangXiKai-v2.6.3.ttf",
     "manifest": "work/font/build/manifest_v263.json",
     "gate_report": "work/lead/gate-report-v263.json",
     "fast_gate": "work/lead/fast-gate-v263.json",
     "diff_from_prev": "work/lead/diff-v262-v263.json",
     # v2.6.3 起 patch 线内容基线 = 上一正式版 v2.6.2（owner 2026-11-14 决定）；
     # 累计 vs v2.5.8 仍单独报告（content_damaged_vs_v258）
     "content_baseline": {"font": "work/font/build/KangXiKai-v2.6.2.ttf",
                          "manifest": "work/font/build/manifest_v262.json"}},
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="work/lead/release-metrics.json")
    ap.add_argument("--md-out", default="work/lead/release-metrics.md")
    ap.add_argument("--versions-json", default=None, help="可选：覆盖内置 VERSIONS 的 JSON 数组")
    args = ap.parse_args()
    out = rel(args.out)
    mdout = rel(args.md_out)
    versions = VERSIONS
    if args.versions_json:
        versions = json.load(open(rel(args.versions_json), encoding="utf-8"))
    target = canonical_target()
    basic = {chr(c) for c in range(0x4E00, 0xA000)}
    rows = []
    missing_versions = []
    for v in versions:
        font_p, man_p = rel(v["font"]), rel(v["manifest"])
        if not os.path.exists(font_p) or not os.path.exists(man_p):
            missing_versions.append(v["label"])
            print(f"WARN: {v['label']} 字体/manifest 不存在，跳过（行标 null）：{v['font']}", file=sys.stderr)
            rows.append({"label": v["label"], "font": v["font"], "font_sha256": None,
                         "chars": None, "basic_covered": None, "basic_total": len(basic),
                         "target_covered": None, "target_total": len(target), "gap": None,
                         "font_qa": None, "glyph_frame_flagged": None,
                         "content_damaged_vs_baseline": None, "missing_flagged": None,
                         "frame_escape_flagged": None, "bad_boxes": None,
                         "empty_assign_halves": None, "fast_gate": None,
                         "changed_glyphs_vs_prev": None})
            continue
        man = json.load(open(man_p, encoding="utf-8"))
        mchars = set(man["chars"])
        item = {"label": v["label"], "font": v["font"], "font_sha256": None,
                "chars": len(mchars),
                "basic_covered": len(mchars & basic), "basic_total": len(basic),
                "target_covered": len(mchars & target), "target_total": len(target),
                "gap": len(target - mchars)}
        item["font_sha256"] = hashlib.sha256(open(font_p, "rb").read()).hexdigest()
        # font_qa
        rc, so, se = run(["scripts/font_qa.py", "--font", font_p, "--manifest", man_p,
                          "--outdir", f"/tmp/metrics-qa-{v['label']}"])
        item["font_qa"] = "PASS" if rc == 0 else "FAIL"
        # glyph_frame_gate
        gf = f"/tmp/metrics-gf-{v['label']}.json"
        run(["scripts/glyph_frame_gate.py", "--font", font_p, "--manifest", man_p, "--out", gf])
        item["glyph_frame_flagged"] = len(json.load(open(gf)).get("flagged") or []) if os.path.exists(gf) else None
        # content vs baseline（v2.6.3+ 可按版本指定 content_baseline=上一正式版；仍报累计 vs v2.5.8）
        item["content_damaged_vs_v258"] = None
        if v["label"] == BASELINE:
            item["content_damaged_vs_baseline"] = 0
        else:
            cbase = v.get("content_baseline")
            bfont = rel(cbase["font"]) if cbase else rel(versions[0]["font"])
            bman = rel(cbase["manifest"]) if cbase else rel(versions[0]["manifest"])
            cl = f"/tmp/metrics-cl-{v['label']}.json"
            if not (os.path.exists(cl) and os.path.getsize(cl) > 2):
                run(["scripts/content_loss_gate.py", bfont, font_p, bman, cl])
            item["content_damaged_vs_baseline"] = len(json.load(open(cl))) if os.path.exists(cl) else None
            if cbase:
                cl2 = f"/tmp/metrics-cl-v258-{v['label']}.json"
                if not (os.path.exists(cl2) and os.path.getsize(cl2) > 2):
                    run(["scripts/content_loss_gate.py", rel(versions[0]["font"]), font_p,
                         rel(versions[0]["manifest"]), cl2])
                item["content_damaged_vs_v258"] = len(json.load(open(cl2))) if os.path.exists(cl2) else None
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
        item["glyph_counts_vs_prev"] = None
        if v.get("diff_from_prev") and os.path.exists(rel(v["diff_from_prev"])):
            dj = json.load(open(rel(v["diff_from_prev"]), encoding="utf-8"))
            if isinstance(dj, list):
                item["changed_glyphs_vs_prev"] = len(dj)
            else:
                counts = dj.get("counts") or {}
                if counts:
                    item["glyph_counts_vs_prev"] = {"changed": counts.get("changed"),
                                                    "added": counts.get("added"),
                                                    "removed": counts.get("removed")}
                    item["changed_glyphs_vs_prev"] = (counts.get("changed") or 0) + (counts.get("added") or 0)
                else:
                    item["changed_glyphs_vs_prev"] = len(dj)
        else:
            item["changed_glyphs_vs_prev"] = None
        rows.append(item)
        print(json.dumps(item, ensure_ascii=False))
    report = {"generated_at": datetime.datetime.now().strftime("%Y-%m-%d"),
              "baseline": BASELINE,
              "target_set": "work/seq/canonical.jsonl unique CJK basic",
              "missing_versions": missing_versions,
              "versions": rows}
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # markdown
    md = ["# 版本对比指标（release_metrics.py 生成）", "",
          "| 指标 | " + " | ".join(r["label"] for r in rows) + " |",
          "|---|" + "---|" * len(rows)]
    fields = [("chars", "字形数"), ("basic_covered", "基本区覆盖/20,992"),
              ("target_covered", "目标表覆盖/16,567"), ("gap", "缺口"),
              ("font_qa", "font_qa"), ("glyph_frame_flagged", "字形级框线"),
              ("content_damaged_vs_baseline", "内容 damaged（基线；v2.6.3+=v2.6.2）"),
              ("content_damaged_vs_v258", "内容 damaged（累计 vs v2.5.8）"),
              ("missing_flagged", "缺件扫描"), ("frame_escape_flagged", "框线逃逸"),
              ("bad_boxes", "页几何 bad_boxes"), ("empty_assign_halves", "空指派半版"),
              ("fast_gate", "fast_gate"), ("changed_glyphs_vs_prev", "相对上一版变化字")]

    def cell(v):
        return "—" if v is None else str(v)
    for k, name in fields:
        md.append(f"| {name} | " + " | ".join(cell(r.get(k)) for r in rows) + " |")
    md.append("")
    md.append("> 注：v2.5.8 的缺件/框线/页几何扫描未按现行口径重跑（—=未测）；v2.6.1 的缺件/框线为当时口径，")
    md.append("> 不可与 v2.6.2 直接比较；v2.6.1 相对 v2.5.8 的变化字数未实测（—）。")
    md.append("> v2.6.2 的「617」是旧候选阈值筛集，**不可复算**；精确 glyf 轮廓差异见 E39（3,351），")
    md.append("> v2.6.3 起的「变化字」由精确轮廓 diff 脚本生成；v2.6.3 = changed 5（急愈架紉釘）+ added 1（釕）+ removed 0。")
    md.append("> v2.6.3 起内容闸基线 = 上一正式版 v2.6.2（owner 2026-11-14 决定）；累计 vs v2.5.8 单独列。")
    open(mdout, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps({"out": os.path.relpath(out, ROOT), "md": os.path.relpath(mdout, ROOT),
                      "missing_versions": missing_versions}, ensure_ascii=False))


if __name__ == "__main__":
    main()
