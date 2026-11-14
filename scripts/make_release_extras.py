#!/usr/bin/env python3
"""make_release_extras.py — 生成正式包固定清单（WORKFLOW §8）所需的附加文件。

**v2.6.3 起参数化**（T0.5）：所有路径/数字都由 `--version` 派生或显式传入，不再硬编码 v2.6.2；
包内闸数字从 gate-report 读取（禁止手抄）；review 快照 / KNOWN-DEBTS / release-metrics 均按版本查找。

输出 staging 目录（默认 work/release/v<ver>/），由 font_package.py 以 --extra/--extra-dir 打入包：
  manifest-v<tag>.json           字表+来源
  provenance-detail-v<tag>.json  每字 page/half/box/来源
  coverage-detail-v<tag>.json    覆盖数字 + 分类别统计（doc_check 依赖）
  qa-report-v<tag>.json / qa-stats-v<tag>.json
  content-loss-v<prev>-v<tag>.json
  residual-quarantine-v<tag>.json
  known-debt-v<tag>.md / KNOWN-DEBTS.md
  RELEASE-NOTES-v<tag>.md / RELEASE-METRICS.md
  PROVENANCE.md / QA.md
  build_recipe-v<tag>.json
  review/                       复核包快照（默认 round-005-<tag> + 反馈记录）
"""
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TAG = lambda v: "v" + v.replace(".", "")
BASIC = set(chr(c) for c in range(0x4E00, 0xA000))

# 里程碑硬条件「隔离 9」（BF-29 待结论）；可用 --isolation-json 覆盖
ISOLATION_9 = ["刃", "榍", "法", "紆", "総", "荹", "仟", "禦", "絞"]


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_target():
    target = set()
    p = os.path.join(ROOT, "work/seq/canonical.jsonl")
    for line in open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        ch = r.get("char")
        if ch and len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
            target.add(ch)
    return target


def gate_numbers(path):
    """从 gate-report 读披露数字（缺失/解析失败返回 {}；发布前必须提供）。"""
    try:
        r = json.load(open(path, encoding="utf-8"))
        steps = {s.get("step"): s for s in (r.get("steps") or [])}
        det = lambda k: (steps.get(k) or {}).get("detail") or {}
        gf = det("glyph_frame_gate")
        fe = det("frame_escape")
        cl = det("content_loss_gate")
        sm = det("scan_missing_parts")
        pg = det("page_geometry_gate")
        cnt = pg.get("counts") or {}
        if not cnt and pg.get("out"):
            # release_gate 的 step detail 只有 out/tail；counts 需读 page-geometry-gate 报告
            try:
                cnt = (json.load(open(os.path.join(ROOT, pg["out"]), encoding="utf-8")) or {}).get("counts") or {}
            except Exception:
                cnt = {}
        return {
            "gate_pass": r.get("pass"),
            "font_qa": bool((steps.get("font_qa") or {}).get("ok")),
            "glyph_frame": gf.get("flagged"),
            "frame_escape": fe.get("flagged"),
            "content_damaged": cl.get("damaged"),
            "content_threshold": cl.get("threshold"),
            "missing": sm.get("flagged"),
            "empty_assign": cnt.get("empty_assign_halves"),
            "bad_boxes": cnt.get("bad_boxes"),
        }
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    # 以下全部可显式传；缺省由 --version 派生
    ap.add_argument("--font", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--mapping", default=None, help="缺省 work/lead/mapping_block_v271.jsonl（跨版本名不带 ver）")
    ap.add_argument("--qa-dir", default=None)
    ap.add_argument("--prev-font", default=None)
    ap.add_argument("--prev-manifest", default=None)
    ap.add_argument("--content", default=None)
    ap.add_argument("--known-debts", default=None, help="缺省 docs/releases/v<ver>/KNOWN-DEBTS.md")
    ap.add_argument("--release-notes", default=None, help="缺省自动生成通用 RELEASE-NOTES")
    ap.add_argument("--release-metrics-md", default=None)
    ap.add_argument("--release-metrics-json", default=None)
    ap.add_argument("--review-dir", default=None, help="缺省 work/review/round-005-<tag>")
    ap.add_argument("--review-feedback", default=None, help="缺省 work/lead/review-feedback-<tag>.json")
    ap.add_argument("--gate-report", default=None, help="缺省 work/lead/gate-report-<tag>.json")
    ap.add_argument("--fast-gate", default=None)
    ap.add_argument("--missing-scan", default=None)
    ap.add_argument("--frame-scan", default=None)
    ap.add_argument("--stats", default=None, help="缺省 <font>.build_stats.json")
    ap.add_argument("--missing-threshold", type=int, default=None, help="缺省=gate-report actual（零余量披露）")
    ap.add_argument("--empty-assign", type=int, default=None)
    ap.add_argument("--isolation-json", default=None, help="可选：{chars:[...]} 隔离清单")
    ap.add_argument("--scans", default=None, help="兼容旧参数（保留）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--write-content", action="store_true", help="重跑 content_loss_gate 生成 content-loss JSON")
    args = ap.parse_args()
    ver = args.version
    tag = TAG(ver)
    args.font = args.font or f"work/font/build/KangXiKai-v{ver}.ttf"
    args.manifest = args.manifest or f"work/font/build/manifest_{tag}.json"
    args.mapping = args.mapping or "work/lead/mapping_block_v271.jsonl"
    args.qa_dir = args.qa_dir or f"work/font/build/qa_{tag}"
    args.prev_font = args.prev_font or "work/font/build/KangXiKai-v2.5.8.ttf"
    args.prev_manifest = args.prev_manifest or "work/font/build/manifest_v258.json"
    args.content = args.content or f"work/lead/content-loss-v258-{tag}.json"
    args.known_debts = args.known_debts or f"docs/releases/v{ver}/KNOWN-DEBTS.md"
    args.review_dir = args.review_dir or f"work/review/round-005-{tag}"
    args.review_feedback = args.review_feedback or f"work/lead/review-feedback-{tag}.json"
    args.gate_report = args.gate_report or f"work/lead/gate-report-{tag}.json"
    args.fast_gate = args.fast_gate or f"work/lead/fast-gate-{tag}.json"
    args.missing_scan = args.missing_scan or f"work/lead/missing_scan_{tag}.jsonl"
    args.frame_scan = args.frame_scan or f"work/lead/frame_scan_{tag}.jsonl"
    args.stats = args.stats or (os.path.splitext(args.font)[0] + ".build_stats.json")
    if args.release_metrics_md is None:
        cand = f"work/lead/release-metrics-{tag}.md"
        args.release_metrics_md = cand if os.path.exists(os.path.join(ROOT, cand)) else "work/lead/release-metrics.md"
    if args.release_metrics_json is None:
        cand = f"work/lead/release-metrics-{tag}.json"
        args.release_metrics_json = cand if os.path.exists(os.path.join(ROOT, cand)) else "work/lead/release-metrics.json"

    out = os.path.join(ROOT, args.out or f"work/release/v{ver}")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    chars = set(man)
    target = load_target()
    covered = chars & target
    basic = chars & BASIC
    num = gate_numbers(os.path.join(ROOT, args.gate_report))
    if not num or num.get("content_damaged") is None:
        print(f"WARN: gate-report 缺失或无闸数字：{args.gate_report}；包内数字将标 null，发布前必须补",
              file=sys.stderr)
    cthr = num.get("content_threshold")
    mthr = args.missing_threshold if args.missing_threshold is not None else num.get("missing")
    eassign = args.empty_assign if args.empty_assign is not None else num.get("empty_assign")

    # 1) manifest
    shutil.copy2(os.path.join(ROOT, args.manifest), os.path.join(out, f"manifest-{tag}.json"))
    # 2) provenance detail（mapping → 每字 page/half/box/label_source）
    prov = {}
    mapping_path = os.path.join(ROOT, args.mapping)
    for line in open(mapping_path, encoding="utf-8"):
        r = json.loads(line)
        for a in r.get("assigned") or []:
            ch = a.get("char")
            box = (a.get("cand") or {}).get("box") or a.get("box")
            if ch and box and ch not in prov:
                prov[ch] = {"page": r.get("page"), "half": r.get("half"),
                            "box": [round(float(v), 1) for v in box],
                            "label_source": os.path.relpath(mapping_path, ROOT)}
    json.dump(prov, open(os.path.join(out, f"provenance-detail-{tag}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 3) coverage detail（数字全部来自 gate-report，禁止手抄）
    pct = round(100.0 * len(covered) / len(target), 2) if target else 0.0
    cov = {"version": ver, "total_glyphs": len(chars),
           "cjk_basic_in_target_set": len(covered),
           "basic_coverage_pct": pct,
           "basic_block_20992_pct": round(100.0 * len(basic) / len(BASIC), 2),
           "target_headword_gap": max(0, len(target) - len(covered)),
           tag: {"title": f"v{ver} 发布候选",
                 "mapping": os.path.basename(args.mapping),
                 "geometry": os.path.basename("work/lead/page_geometry.jsonl"),
                 "pre_cut": "页级几何 + pre-cut mask + 已验证线条带（数据驱动）",
                 "qa": "PASS" if num.get("font_qa") else "FAIL",
                 "glyph_frame": num.get("glyph_frame"),
                 "frame_escape": num.get("frame_escape"),
                 "content_gate": {"damaged": num.get("content_damaged"), "threshold": cthr},
                 "missing_parts": {"flagged": num.get("missing"), "threshold": mthr},
                 "empty_assign_halves": eassign,
                 "source_gate_report": os.path.relpath(os.path.join(ROOT, args.gate_report), ROOT)}}
    json.dump(cov, open(os.path.join(out, f"coverage-detail-{tag}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 4) QA 报告（font_qa 输出 report.json/stats.json）
    qd = os.path.join(ROOT, args.qa_dir)
    for src, dst in (("report.json", f"qa-report-{tag}.json"), ("stats.json", f"qa-stats-{tag}.json")):
        p = os.path.join(qd, src)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(out, dst))
    # 5) content loss
    if args.write_content:
        subprocess.run([PY, "scripts/content_loss_gate.py", args.prev_font, args.font,
                        args.prev_manifest, args.content], cwd=ROOT, check=False)
    if os.path.exists(os.path.join(ROOT, args.content)):
        shutil.copy2(os.path.join(ROOT, args.content),
                     os.path.join(out, f"content-loss-v258-{tag}.json"))
    # 6) residual quarantine
    if args.isolation_json:
        iso = list(json.load(open(os.path.join(ROOT, args.isolation_json), encoding="utf-8")).get("chars") or [])
    else:
        iso = list(ISOLATION_9)
    json.dump({"n": len(iso), "chars": iso,
               "reason": "参考闸残余 → 隔离（里程碑硬条件 BF-29 待结论）"},
              open(os.path.join(out, f"residual-quarantine-{tag}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 7) known debts / release metrics / gate report（按版本查找；缺失 → WARN，发布前必须补）
    kd = os.path.join(ROOT, args.known_debts)
    if os.path.exists(kd):
        shutil.copy2(kd, os.path.join(out, "KNOWN-DEBTS.md"))
        shutil.copy2(kd, os.path.join(out, f"known-debt-{tag}.md"))
    else:
        print(f"WARN: KNOWN-DEBTS 缺失：{args.known_debts}（发布前必须补）", file=sys.stderr)
    rm = os.path.join(ROOT, args.release_metrics_md)
    if os.path.exists(rm):
        shutil.copy2(rm, os.path.join(out, "RELEASE-METRICS.md"))
    rmj = os.path.join(ROOT, args.release_metrics_json)
    if os.path.exists(rmj):
        shutil.copy2(rmj, os.path.join(out, "release-metrics.json"))
    gr = os.path.join(ROOT, args.gate_report)
    if os.path.exists(gr):
        shutil.copy2(gr, os.path.join(out, f"gate-report-{tag}.json"))
    # 8) PROVENANCE.md / QA.md（doc_check 数字需与 coverage-detail 一致；数字来自 gate-report）
    pct_s = f"{pct:.2f}"
    gap = max(0, len(target) - len(covered))
    def ns(v):
        return "待 gate-report" if v is None else str(v)
    open(os.path.join(out, "PROVENANCE.md"), "w", encoding="utf-8").write(f"""# PROVENANCE · 康熙楷 v{ver}

- 数据源：《康熙字典》清康熙五十五年内府刊本（1716），書格 shuge.org 数字化；扫描图不随包分发。
- 字形来源：**全部为刻本字头真迹**（headword-only；vectorize + normalize），无生成字；
  provenance 计数见 `stats.json` / `provenance.json`；逐字页/半版/框见 `provenance-detail-{tag}.json`。
- 覆盖：目标表 **{pct_s}%**（{len(covered)}/{len(target)}），基本区 **{cov['basic_block_20992_pct']:.2f}%**（{len(basic)}/20,992），缺口 **{gap:,}** 字。
- 版权/许可：字体 SIL OFL 1.1（`OFL.txt`）；代码 MIT；参考字体 LXGW WenKai（OFL）仅作 QA，不随包分发。
- 构建输入 sha256 见 `build_recipe-{tag}.json`；闸报告见 `gate-report-{tag}.json`。
""")
    open(os.path.join(out, "QA.md"), "w", encoding="utf-8").write(f"""# QA · 康熙楷 v{ver}

- `font_qa`：**{'PASS' if num.get('font_qa') else 'FAIL'}**（表/cmap/空字形/bbox/advance/同框=0；不数孔洞/连通分量，D21）
- 字形级框线：**{ns(num.get('glyph_frame'))}**（`glyph_frame_gate`）
- 框线逃逸（源图级）：**{ns(num.get('frame_escape'))}**（`scan_frame_escape`）
- 内容闸：**{ns(num.get('content_damaged'))} / {ns(cthr)}**（vs v2.5.8；D23 判据待 owner）
- 缺件扫描：**{ns(num.get('missing'))} / {ns(mthr)}**（阈值模式须披露零余量）
- 页级几何：bad_boxes **{ns(num.get('bad_boxes'))}**；empty_assign **{ns(eassign)}**（披露阈值，mapping 缺口）
- 覆盖：目标表 **{pct_s}%**（{len(covered)}/{len(target)}），缺口 **{gap:,}** 字。
- 完整明细：`qa-report-{tag}.json`、`qa-stats-{tag}.json`、`gate-report-{tag}.json`。
""")
    # 9) release notes（有现成文件则复制；否则生成通用版，禁止写历史数字）
    rn = args.release_notes
    if rn and os.path.exists(os.path.join(ROOT, rn)):
        shutil.copy2(os.path.join(ROOT, rn), os.path.join(out, f"RELEASE-NOTES-{tag}.md"))
    else:
        open(os.path.join(out, f"RELEASE-NOTES-{tag}.md"), "w", encoding="utf-8").write(f"""# RELEASE NOTES · 康熙楷 v{ver}

## 本版要点
- 本版为 v{ver} 补丁批次；完整闸结果见 `gate-report-{tag}.json` 与 `KNOWN-DEBTS.md`（随包）。
- 候选字体 sha256 `{sha256(os.path.join(ROOT, args.font))}`；{len(chars):,} 字。
- 覆盖：目标表 {pct_s}%（{len(covered)}/{len(target)}）；缺口 {gap:,}。
- headword-only 真迹（headword-only，无生成字）；缺字由系统字体回退。

## 已知债（详见 KNOWN-DEBTS.md）
""")
    # 10) build recipe（路径参数化；cache_ver/build git 从 build_stats 读取，T4 完整派生）
    git = {}
    try:
        git["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        git["dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except Exception:
        git = {"commit": None, "dirty": None}
    stats = {}
    try:
        stats = json.load(open(os.path.join(ROOT, args.stats), encoding="utf-8"))
    except Exception:
        stats = {}
    recipe = {"version": ver, "font": args.font, "font_sha256": sha256(os.path.join(ROOT, args.font)),
              "manifest": args.manifest, "manifest_sha256": sha256(os.path.join(ROOT, args.manifest)),
              "mapping": args.mapping, "mapping_sha256": sha256(os.path.join(ROOT, args.mapping)),
              "geometry": "work/lead/page_geometry.jsonl",
              "geometry_sha256": sha256(os.path.join(ROOT, "work/lead/page_geometry.jsonl")),
              "bands_sha256": sha256(os.path.join(ROOT, "work/lead/page_line_bands.json")),
              "build_stats": args.stats,
              "cache_ver": stats.get("cache_ver"),
              "build_git": stats.get("git"),
              "package_git": git, "workers": 10,
              "rebuild": f"FONT_BUILD_WORKERS=10 scripts/font_build.py --mapping {args.mapping} "
                         f"--out {args.font} --version {ver}",
              "gates": {"fast": args.fast_gate, "full": args.gate_report,
                        "missing": args.missing_scan, "frame": args.frame_scan}}
    json.dump(recipe, open(os.path.join(out, f"build_recipe-{tag}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 11) 图片
    for img in ("specimen.png", "book-vs-font.png"):
        p = os.path.join(ROOT, "docs/images", img)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(out, img))
    # 12) review/ 快照（版本派生；缺失只 WARN，发布前必须补）
    rv = os.path.join(ROOT, args.review_dir)
    if os.path.isdir(rv):
        dst = os.path.join(out, "review")
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(rv):
            shutil.copy2(os.path.join(rv, f), os.path.join(dst, f))
        fb = os.path.join(ROOT, args.review_feedback)
        if os.path.exists(fb):
            shutil.copy2(fb, os.path.join(dst, f"review-feedback-{tag}.json"))
    else:
        print(f"WARN: review 快照目录缺失：{args.review_dir}（发布前必须补）", file=sys.stderr)
    print(json.dumps({"staging": os.path.relpath(out, ROOT), "files": len(os.listdir(out)),
                      "version": ver, "gate_numbers": num}, ensure_ascii=False))


if __name__ == "__main__":
    main()
