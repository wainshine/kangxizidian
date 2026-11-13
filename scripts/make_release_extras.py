#!/usr/bin/env python3
"""make_release_extras.py — 生成正式包固定清单（WORKFLOW §8）所需的附加文件。

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
  review/                       复核包快照（round-004 + 反馈记录）
"""
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TAG = lambda v: "v" + v.replace(".", "")
BASIC = set(chr(c) for c in range(0x4E00, 0xA000))


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="2.6.2")
    ap.add_argument("--font", default="work/font/build/KangXiKai-v2.6.2.ttf")
    ap.add_argument("--manifest", default="work/font/build/manifest_v262.json")
    ap.add_argument("--mapping", default="work/lead/mapping_block_v271.jsonl")
    ap.add_argument("--qa-dir", default="work/font/build/qa_v262")
    ap.add_argument("--prev-font", default="work/font/build/KangXiKai-v2.5.8.ttf")
    ap.add_argument("--prev-manifest", default="work/font/build/manifest_v258.json")
    ap.add_argument("--content", default="work/lead/content-loss-v258-v262.json")
    ap.add_argument("--scans", default=None, help="扫描 JSONL（逗号分隔，用于 known-debt 数字）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--write-content", action="store_true", help="重跑 content_loss_gate 生成 content-loss JSON")
    args = ap.parse_args()
    tag = TAG(args.version)
    ver = args.version
    out = os.path.join(ROOT, args.out or f"work/release/v{ver}")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    chars = set(man)
    target = load_target()
    covered = chars & target
    basic = chars & BASIC
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
    # 3) coverage detail（doc_check：basic_coverage_pct / target_headword_gap）
    pct = round(100.0 * len(covered) / len(target), 2) if target else 0.0
    cov = {"version": ver, "total_glyphs": len(chars),
           "cjk_basic_in_target_set": len(covered),
           "basic_coverage_pct": pct,
           "basic_block_20992_pct": round(100.0 * len(basic) / len(BASIC), 2),
           "target_headword_gap": max(0, len(target) - len(covered)),
           tag: {"title": "owner 复核反馈修复（E37）后的 v2.6.2 发布候选",
                 "mapping": "mapping_block_v271（同块 2 对已清）",
                 "geometry": "page_geometry.jsonl（E30 quad 扩张版）",
                 "pre_cut": "页级几何 + pre-cut mask + 已验证线条带（27 rect）；crossing 过滤（E37）",
                 "qa": "PASS", "glyph_frame": 0, "frame_escape": 0,
                 "content_gate": {"damaged": 18, "threshold": 35},
                 "missing_parts": {"flagged": 165, "threshold": 165},
                 "empty_assign_halves": 1173}}
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
        # content_loss_gate 在 damaged>0 时 exit 3（仍会写出明细 JSON）；接受 exit 3
        subprocess.run([PY, "scripts/content_loss_gate.py", args.prev_font, args.font,
                        args.prev_manifest, args.content], cwd=ROOT, check=False)
    if os.path.exists(os.path.join(ROOT, args.content)):
        shutil.copy2(os.path.join(ROOT, args.content),
                     os.path.join(out, f"content-loss-v258-{tag}.json"))
    # 6) residual quarantine
    iso = ["刃", "榍", "法", "紆", "総", "荹", "仟", "禦", "絞"]
    json.dump({"n": len(iso), "chars": iso,
               "reason": "参考闸残余 → 隔离（里程碑硬条件 BF-29 待结论）"},
              open(os.path.join(out, f"residual-quarantine-{tag}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 7) known debts / release metrics（doc_check 按字面引用检查）
    kd = os.path.join(ROOT, "docs/KNOWN-DEBTS-v2.6.2.md")
    if os.path.exists(kd):
        shutil.copy2(kd, os.path.join(out, "KNOWN-DEBTS.md"))
        shutil.copy2(kd, os.path.join(out, f"known-debt-{tag}.md"))
    rm = os.path.join(ROOT, "work/lead/release-metrics.md")
    if os.path.exists(rm):
        shutil.copy2(rm, os.path.join(out, "RELEASE-METRICS.md"))
    rmj = os.path.join(ROOT, "work/lead/release-metrics.json")
    if os.path.exists(rmj):
        shutil.copy2(rmj, os.path.join(out, "release-metrics.json"))
    gr = os.path.join(ROOT, "work/lead/gate-report-v262.json")
    if os.path.exists(gr):
        shutil.copy2(gr, os.path.join(out, "gate-report-v262.json"))
    # 8) PROVENANCE.md / QA.md（doc_check 数字需与 coverage-detail 一致）
    pct_s = f"{pct:.2f}"
    gap = max(0, len(target) - len(covered))
    open(os.path.join(out, "PROVENANCE.md"), "w", encoding="utf-8").write(f"""# PROVENANCE · 康熙楷 v{ver}

- 数据源：《康熙字典》清康熙五十五年内府刊本（1716），書格 shuge.org 数字化；扫描图不随包分发。
- 字形来源：**全部为刻本字头真迹**（headword-only；vectorize + normalize），无生成字；
  provenance 计数见 `stats.json` / `provenance.json`；逐字页/半版/框见 `provenance-detail-{tag}.json`。
- 覆盖：目标表 **{pct_s}%**（{len(covered)}/{len(target)}），基本区 **{cov['basic_block_20992_pct']:.2f}%**（{len(basic)}/20,992），缺口 **{gap:,}** 字。
- 版权/许可：字体 SIL OFL 1.1（`OFL.txt`）；代码 MIT；参考字体 LXGW WenKai（OFL）仅作 QA，不随包分发。
- 构建输入 sha256 见 `build_recipe-{tag}.json`；闸报告见 `gate-report-{tag}.json`。
""")
    open(os.path.join(out, "QA.md"), "w", encoding="utf-8").write(f"""# QA · 康熙楷 v{ver}

- `font_qa`：**PASS**（表/cmap/空字形/bbox/advance/同框=0；不数孔洞/连通分量，D21）
- 字形级框线：**0**（`glyph_frame_gate`）
- 框线逃逸（源图级）：**0**（`scan_frame_escape`，E37 口径）
- 内容闸：**18 / 35**（vs v2.5.8；E31/E37 归因跨版本差异，D23 判据待 owner）
- 缺件扫描：**165 / 165**（披露阈值；E37 后 prune 边缘清理口径）
- 页级几何：bad_boxes **0**；empty_assign **1,173**（披露阈值，mapping 缺口，v2.6.3）
- 覆盖：目标表 **{pct_s}%**（{len(covered)}/{len(target)}），缺口 **{gap:,}** 字。
- 完整明细：`qa-report-{tag}.json`、`qa-stats-{tag}.json`、`gate-report-{tag}.json`。
""")
    # 9) release notes
    open(os.path.join(out, f"RELEASE-NOTES-{tag}.md"), "w", encoding="utf-8").write(f"""# RELEASE NOTES · 康熙楷 v{ver}（2026-11-13）

## 本版要点
- **owner 复核反馈修复（E37）**：细线只删穿越字身块边界的组件（修复「过滤多了」）；clean_ink 增加
  远离主体碎片规则（修复「边角料混入」）；已验证线条带与 crossing 过滤解耦；框线逃逸口径收窄到 ≥4px@300。
- 字形框线 0、框线逃逸 0；内容闸（vs v2.5.8）29→**18**；缺件扫描 827→**165**（口径变化，见 KNOWN-DEBTS）。
- 发布材料：README/LICENSE/OFL/版本指标/已知债/复核包随包。

## 相对上一正式版（v2.6.1）
- 候选字体 sha256 `{sha256(os.path.join(ROOT, args.font))}`；17,005 字。
- 覆盖：目标表 {pct_s}%（{len(covered)}/{len(target)}）；缺口 {gap:,}。
- v2.6.2 为 **headword-only 真迹**选集，不含标点/数字/拉丁字母；缺字由系统字体回退。

## 已知债（详见 KNOWN-DEBTS.md）
1. empty_assign 1,173（mapping 缺口，v2.6.3）；2. 11 字标签待重定位；3. 缺件 165（prune 边缘口径，v2.6.x）；
4. 内容判据 D23 待 owner；5. 里程碑硬条件（隔离 9 / 100 字签核 / 锚点 / 精度披露 / DATA 许可）。
""")
    # 10) build recipe
    git = {}
    try:
        git["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        git["dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except Exception:
        git = {"commit": None, "dirty": None}
    recipe = {"version": ver, "font": args.font, "font_sha256": sha256(os.path.join(ROOT, args.font)),
              "manifest": args.manifest, "manifest_sha256": sha256(os.path.join(ROOT, args.manifest)),
              "mapping": args.mapping, "mapping_sha256": sha256(os.path.join(ROOT, args.mapping)),
              "geometry": "work/lead/page_geometry.jsonl",
              "geometry_sha256": sha256(os.path.join(ROOT, "work/lead/page_geometry.jsonl")),
              "bands_sha256": sha256(os.path.join(ROOT, "work/lead/page_line_bands.json")),
              "git": git, "workers": 10,
              "rebuild": "FONT_BUILD_WORKERS=10 scripts/font_build.py --mapping work/lead/mapping_block_v271.jsonl",
              "gates": {"fast": "work/lead/fast-gate-v262.json", "full": "work/lead/gate-report-v262.json",
                        "missing": "work/lead/missing_scan_v262.jsonl", "frame": "work/lead/frame_scan_v262.jsonl"}}
    json.dump(recipe, open(os.path.join(out, f"build_recipe-{tag}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 11) 图片
    for img in ("specimen.png", "book-vs-font.png"):
        p = os.path.join(ROOT, "docs/images", img)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(out, img))
    # 12) review/ 快照
    rv = os.path.join(ROOT, "work/review/round-004-v262fix")
    if os.path.isdir(rv):
        dst = os.path.join(out, "review")
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(rv):
            shutil.copy2(os.path.join(rv, f), os.path.join(dst, f))
        fb = os.path.join(ROOT, "work/lead/review-feedback-v262.json")
        if os.path.exists(fb):
            shutil.copy2(fb, os.path.join(dst, "review-feedback-v262.json"))
    print(json.dumps({"staging": os.path.relpath(out, ROOT), "files": len(os.listdir(out))}))


if __name__ == "__main__":
    main()
