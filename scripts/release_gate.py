#!/usr/bin/env python3
"""发布门禁：一条命令串起全部硬闸。所有步骤都会执行并记录，然后统一判定（返回非零）。

说明：旧版 docstring 声称「任一失败即中止」但实际会继续 finalize 并写包——已改：
  - 未通过 pre-finalize 判定时**绝不改动包**（不写报告/SHA/zip），只在 work/lead 写失败报告；
  - finalize 前要求 clean git tree（--allow-dirty 仅调试）、缺件/框线扫描必须提供（--allow-missing-scans 仅调试）；
  - 复用扫描/内容结果必须带输入绑定 sidecar，输入或脚本变化即 FAIL（BF-12）；
  - 新增三闸：glyph_frame_gate / provenance_gate / page_geometry_gate（BF-01）。

用法:
  python scripts/release_gate.py --version 2.5.6 \
     --font work/font/build/KangXiKai-v2.5.6.ttf \
     --manifest work/font/build/manifest_v256.json \
     --prev release/KangXiKai-v2.5.5/KangXiKai-Regular-v2.5.5.ttf \
     --pkg-dir release/KangXiKai-v2.5.6 --tag v256

步骤:
 1) font_qa（渲染闸/同框/内部自洽）
 2) 版本盖章校验：name ID5 / head.fontRevision 与 --version 一致
 3) manifest 字符集 diff：相对 --prev-manifest 的 removed 必须出现在 quarantine 清单
 4) content_loss_gate（覆盖率下限内建）
 5) check_release_docs（包存在时）
 6) SHA256SUMS + zip 自检（包存在时）
输出 gate-report.json（成功才写 PASS）。
"""
import argparse, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gate_binding as GB


def run(cmd, name):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0
    return {"step": name, "cmd": " ".join(cmd), "ok": ok,
            "stdout": (r.stdout or "")[-1500:], "stderr": (r.stderr or "")[-800:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--font", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--prev", default=None, help="上一版字体（内容闸对比基线）")
    ap.add_argument("--prev-manifest", default=None)
    ap.add_argument("--pkg-dir", default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--quarantine", default=None,
                    help="隔离清单 JSON（缺省自动找 work/lead/v*_residual.json）")
    ap.add_argument("--scan", action="store_true",
                    help="加跑全库缺件扫描（scan_missing_parts；耗时约 10 分钟，发布候选版应开）")
    ap.add_argument("--content-max-damaged", type=int, default=0,
                    help="内容缺失闸阈值（默认 0=严格；过程版本可给阈值并披露）")
    ap.add_argument("--reuse-missing", default=None,
                    help="复用已有缺件扫描 jsonl（不重跑，按字体/几何版本缓存思想）")
    ap.add_argument("--reuse-frame", default=None,
                    help="复用已有框线逃逸扫描 jsonl")
    ap.add_argument("--reuse-content", default=None,
                    help="复用已有内容缺失闸 json")
    ap.add_argument("--frame-scan", action="store_true",
                    help="加跑框线逃逸闸（scan_frame_escape）")
    ap.add_argument("--frame-max-flagged", type=int, default=0,
                    help="框线逃逸闸阈值（默认 0=严格；预览可给阈值并披露）")
    ap.add_argument("--scan-max-flagged", type=int, default=None,
                    help="缺件扫描 flagged 阈值；缺省=严格模式要求 0（签收版）；预览版可显式给阈值并披露")
    ap.add_argument("--zip", default=None, help="打包后的 zip 路径（finalize 时重建 zip 并校验）")
    ap.add_argument("--allow-missing-attestation", action="store_true",
                    help="首跑模式：doc_check 允许 gate-report 引用暂缺（finalize 会生成）")
    ap.add_argument("--no-finalize", action="store_true",
                    help="不写 gate-report 进包、不重算 SHA（仅用于调试）")
    ap.add_argument("--mapping", default="work/lead/mapping_block_v271.jsonl",
                    help="mapping（provenance/页级几何闸输入）")
    ap.add_argument("--geometry", default="work/lead/page_geometry.jsonl",
                    help="S1 页级几何（页级几何闸输入）")
    ap.add_argument("--stats", default=None, help="build stats JSON（默认 <font>.build_stats.json）")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="调试用：允许脏工作区 finalize（正式包禁止）")
    ap.add_argument("--page-geometry-max-empty-assign", type=int, default=0,
                    help="页几何 empty_assign_halves 阈值（默认 0=严格；明确披露的已知债可给阈值）")
    ap.add_argument("--page-geometry-max-bad-boxes", type=int, default=0,
                    help="页几何 bad_boxes 阈值（默认 0=严格）")
    ap.add_argument("--allow-missing-scans", action="store_true",
                    help="调试用：finalize 允许不做缺件/框线扫描（正式包禁止）")
    args = ap.parse_args()
    v = args.version
    tag = args.tag or ("v" + v.replace(".", ""))
    steps = []
    inputs = GB.build_binding(
        files={"font": args.font, "manifest": args.manifest, "prev_font": args.prev,
               "prev_manifest": args.prev_manifest, "mapping": args.mapping,
               "geometry": args.geometry},
        scripts=["release_gate.py", "font_qa.py", "content_loss_gate.py",
                 "glyph_frame_gate.py", "provenance_gate.py", "page_geometry_gate.py",
                 "check_release_docs.py"],
        include_reffont=True)

    # 1) QA
    qa_dir = os.path.join("work", "font", "build", f"qa_gate_{tag}")
    steps.append(run([sys.executable, "scripts/font_qa.py", "--font", args.font,
                      "--manifest", args.manifest, "--outdir", qa_dir], "font_qa"))
    # 2) 版本盖章
    from fontTools.ttLib import TTFont
    f = TTFont(os.path.join(ROOT, args.font))
    name_v = f["name"].getDebugName(5) or ""
    rev = round(f["head"].fontRevision, 4)
    expect_rev = None
    try:
        parts = (v.split(".") + ["0", "0"])[:3]
        expect_rev = round(int(parts[0]) + int(parts[1]) / 10.0 + int(parts[2]) / 100.0, 2)
    except Exception:
        pass
    ok_stamp = (name_v == f"Version {v}") and (expect_rev is None or abs(rev - expect_rev) < 1e-6)
    steps.append({"step": "version_stamp", "ok": ok_stamp,
                  "detail": {"name_id5": name_v, "fontRevision": rev, "expect": f"Version {v}"}})

    # 3) 字符集 diff + 隔离清单
    man = json.load(open(os.path.join(ROOT, args.manifest), encoding="utf-8"))["chars"]
    removed, added = [], []
    if args.prev_manifest and os.path.exists(os.path.join(ROOT, args.prev_manifest)):
        prev = json.load(open(os.path.join(ROOT, args.prev_manifest), encoding="utf-8"))["chars"]
        removed = sorted(set(prev) - set(man))
        added = sorted(set(man) - set(prev))
    # 隔离清单：显式参数优先；缺省合并 work/lead/v*_residual.json（防单文件过期）
    quarantine, qfiles = set(), []
    cands = [args.quarantine] if args.quarantine else []
    import glob as _glob
    cands += sorted(_glob.glob(os.path.join(ROOT, "work", "lead", "v*_residual.json")))
    for cand in cands:
        p = cand if os.path.isabs(cand) else os.path.join(ROOT, cand)
        if os.path.exists(p):
            try:
                quarantine |= set(json.load(open(p))["chars"])
                qfiles.append(os.path.relpath(p, ROOT))
            except Exception:
                pass
    # 字符集差集必须有基线输入，否则 FAIL（防空转）
    if not (args.prev_manifest and os.path.exists(os.path.join(ROOT, args.prev_manifest))):
        steps.append({"step": "char_diff", "ok": False,
                      "detail": {"error": "缺 --prev-manifest，字符集差集无法校验（不允许空转）"}})
    else:
        undeclared = [c for c in removed if c not in quarantine]
        steps.append({"step": "char_diff", "ok": not undeclared,
                      "detail": {"removed": removed, "added": added,
                                 "undeclared_removed": undeclared,
                                 "quarantine_files": qfiles, "quarantine_n": len(quarantine)}})

    # 4) 内容缺失闸：既看退出码，也解析 JSON 的 damaged（双重保险）
    #    复用必须过输入绑定 sidecar（BF-12）；失败则重算并把 reuse 拒绝写进报告
    if args.prev:
        fresh_json = os.path.join("work", "lead", f"content-loss-gate-{tag}.json")
        out_json = fresh_json
        r = None
        reuse_ok = None
        if args.reuse_content:
            vres = GB.validate_reuse(args.reuse_content,
                                  files={"font": args.font, "baseline": args.prev,
                                         "manifest": args.manifest},
                                  scripts=["content_loss_gate.py", "fidelity_eval.py"])
            reuse_ok = vres["ok"]
            steps.append({"step": "content_reuse_binding", "ok": reuse_ok,
                          "detail": {"file": args.reuse_content, **vres}})
            if reuse_ok:
                out_json = args.reuse_content
                r = subprocess.CompletedProcess(args=[], returncode=0, stdout="reused")
        if r is None:
            r = subprocess.run([sys.executable, "scripts/content_loss_gate.py", args.prev, args.font,
                                args.manifest, out_json], cwd=ROOT, capture_output=True, text=True)
        damaged = None
        try:
            rows = json.load(open(os.path.join(ROOT, out_json)))
            if isinstance(rows, list):
                damaged = len([x for x in rows if isinstance(x, dict) and "ink_ratio" in x])
        except Exception:
            pass
        mode = "threshold" if args.content_max_damaged > 0 else "strict(0)"
        zero_margin = (args.content_max_damaged > 0 and damaged is not None
                       and damaged == args.content_max_damaged)
        if args.content_max_damaged > 0:
            ok_content = (damaged is not None and damaged <= args.content_max_damaged
                          and r.returncode in (0, 3))
        else:
            ok_content = (r.returncode == 0 and damaged == 0)
        steps.append({"step": "content_loss_gate", "ok": ok_content,
                      "detail": {"returncode": r.returncode, "damaged": damaged,
                                 "mode": mode, "reused": bool(reuse_ok),
                                 "threshold": args.content_max_damaged,
                                 "zero_margin": zero_margin,
                                 "threshold_note": ("阈值=观测值，无余量" if zero_margin else ""),
                                 "tail": (r.stdout or "")[-300:]}})
    # 4b) 全库缺件扫描（候选可开；里程碑 finalize 强制要求）
    if args.scan:
        out_scan = os.path.join("work", "lead", f"missing_scan_gate_{tag}.jsonl")
        r = None
        reuse_ok = None
        if args.reuse_missing:
            out_scan = args.reuse_missing
            vres = GB.validate_reuse(out_scan,
                                  files={"font": args.font, "manifest": args.manifest,
                                         "geometry": args.geometry,
                                         "page_line_bands": "work/lead/page_line_bands.json",
                                         "build_stats": stats_path},
                                  scripts=["scan_missing_parts.py", "precut_masks.py", "reffont.py",
                                           "font_build.py", "font_norm.py", "page_frames.py",
                                           "fidelity_eval.py"],
                                  include_reffont=True)
            reuse_ok = vres["ok"]
            steps.append({"step": "missing_reuse_binding", "ok": reuse_ok,
                          "detail": {"file": out_scan, **vres}})
            if reuse_ok:
                r = subprocess.CompletedProcess(args=[], returncode=0, stdout="reused")
        if r is None:
            r = subprocess.run([sys.executable, "scripts/scan_missing_parts.py", args.font,
                                args.manifest, out_scan], cwd=ROOT, capture_output=True, text=True)
        flagged = n_error = None
        try:
            rows = [json.loads(ln) for ln in open(os.path.join(ROOT, out_scan))]
            n_error = sum(1 for x in rows if x.get("error"))
            # fail-closed：error 行无法判定，与「缺件」一起计入 flagged（不允许静默丢样）
            flagged = sum(1 for x in rows if x.get("missing")) + n_error
        except Exception:
            pass
        limit = args.scan_max_flagged
        zero_margin = (limit is not None and flagged is not None and flagged == limit)
        if limit is None:
            ok_scan = (r.returncode == 0 and flagged == 0)
            mode = "strict(0)"
        else:
            ok_scan = (r.returncode == 0 and flagged is not None and flagged <= limit)
            mode = f"threshold({limit})"
        steps.append({"step": "scan_missing_parts", "ok": ok_scan,
                      "detail": {"returncode": r.returncode, "flagged": flagged,
                                 "error_rows": n_error, "mode": mode, "reused": bool(reuse_ok),
                                 "zero_margin": zero_margin,
                                 "tail": (r.stdout or "")[-200:]}})
    # 4c) 框线逃逸闸（切前排除后块内不应再有贯穿框线）
    if args.frame_scan:
        out_frame = os.path.join("work", "lead", f"frame_escape_scan_{tag}.jsonl")
        r = None
        reuse_ok = None
        if args.reuse_frame:
            out_frame = args.reuse_frame
            vres = GB.validate_reuse(out_frame,
                                  files={"manifest": args.manifest, "geometry": args.geometry,
                                         "page_line_bands": "work/lead/page_line_bands.json"},
                                  scripts=["scan_frame_escape.py", "precut_masks.py", "font_build.py",
                                           "font_norm.py", "page_frames.py", "detect_blocks.py"])
            reuse_ok = vres["ok"]
            steps.append({"step": "frame_reuse_binding", "ok": reuse_ok,
                          "detail": {"file": out_frame, **vres}})
            if reuse_ok:
                r = subprocess.CompletedProcess(args=[], returncode=0, stdout="reused")
        if r is None:
            r = subprocess.run([sys.executable, "scripts/scan_frame_escape.py",
                                "--manifest", args.manifest, "--out", out_frame],
                               cwd=ROOT, capture_output=True, text=True)
        flagged = n_error = None
        try:
            rows = [json.loads(ln) for ln in open(os.path.join(ROOT, out_frame))]
            n_error = sum(1 for x in rows if x.get("error"))
            flagged = len(rows)  # 所有行都是 flagged；error 行同样计入（fail-closed）
        except Exception:
            pass
        zero_margin = (flagged is not None and flagged == args.frame_max_flagged)
        ok_frame = (r.returncode == 0 and flagged is not None
                    and flagged <= args.frame_max_flagged)
        steps.append({"step": "frame_escape", "ok": ok_frame,
                      "detail": {"flagged": flagged, "error_rows": n_error,
                                 "reused": bool(reuse_ok),
                                 "threshold": args.frame_max_flagged,
                                 "zero_margin": zero_margin,
                                 "mode": "strict" if args.frame_max_flagged == 0 else "threshold"}})
    # 4d) 三闸（BF-01）：字形级框线 / 无拷贝 provenance / 页级几何（全部严格 0）
    out_gf = os.path.join("work", "lead", f"glyph-frame-gate-{tag}.json")
    r = subprocess.run([sys.executable, "scripts/glyph_frame_gate.py", "--font", args.font,
                        "--manifest", args.manifest, "--out", out_gf,
                        "--max-flagged", str(args.frame_max_flagged)],
                       cwd=ROOT, capture_output=True, text=True)
    try:
        gfr = json.load(open(os.path.join(ROOT, out_gf)))
        gf_flagged = len(gfr.get("flagged") or [])
    except Exception:
        gf_flagged = None
    steps.append({"step": "glyph_frame_gate",
                  "ok": (r.returncode == 0 and gf_flagged is not None
                         and gf_flagged <= args.frame_max_flagged),
                  "detail": {"returncode": r.returncode, "flagged": gf_flagged,
                             "threshold": args.frame_max_flagged, "out": out_gf,
                             "tail": (r.stdout or "")[-200:]}})
    stats_path = args.stats or (os.path.splitext(args.font)[0] + ".build_stats.json")
    out_prov = os.path.join("work", "lead", f"provenance-gate-{tag}.json")
    r = subprocess.run([sys.executable, "scripts/provenance_gate.py",
                        "--manifest", args.manifest, "--mapping", args.mapping,
                        "--stats", stats_path, "--out", out_prov],
                       cwd=ROOT, capture_output=True, text=True)
    steps.append({"step": "provenance_gate", "ok": r.returncode == 0,
                  "detail": {"returncode": r.returncode, "out": out_prov,
                             "stats": stats_path,
                             "tail": (r.stdout or "")[-300:]}})
    out_pg = os.path.join("work", "lead", f"page-geometry-gate-{tag}.json")
    r = subprocess.run([sys.executable, "scripts/page_geometry_gate.py",
                        "--manifest", args.manifest, "--mapping", args.mapping,
                        "--geometry", args.geometry, "--out", out_pg,
                        "--max-bad-boxes", str(args.page_geometry_max_bad_boxes),
                        "--max-missing-quad-chars", "0",
                        "--max-empty-assign-halves", str(args.page_geometry_max_empty_assign)],
                       cwd=ROOT, capture_output=True, text=True)
    steps.append({"step": "page_geometry_gate", "ok": r.returncode == 0,
                  "detail": {"returncode": r.returncode, "out": out_pg,
                             "tail": (r.stdout or "")[-300:]}})

    # 4e) finalize 前置条件（正式包不允许跳过；--allow-* 仅调试且写进报告）
    if args.pkg_dir and not args.no_finalize:
        missing_scans = (not (args.scan or args.reuse_missing) or
                         not (args.frame_scan or args.reuse_frame))
        steps.append({"step": "scans_required",
                      "ok": (not missing_scans) or args.allow_missing_scans,
                      "detail": {"scan": bool(args.scan or args.reuse_missing),
                                 "frame_scan": bool(args.frame_scan or args.reuse_frame),
                                 "allow_missing_scans": args.allow_missing_scans,
                                 "note": "正式包必须提供缺件+框线扫描（BF-10）"}})
        steps.append({"step": "content_baseline_required",
                      "ok": bool(args.prev) or args.allow_missing_scans,
                      "detail": {"prev": args.prev,
                                 "note": "正式包必须有内容闸基线（BF-10）"}})
        git = inputs.get("git") or {}
        steps.append({"step": "clean_tree",
                      "ok": (git.get("dirty") is False) or args.allow_dirty,
                      "detail": {"git": git, "allow_dirty": args.allow_dirty,
                                 "note": "正式包必须来自 clean git tree（AGENTS §1）"}})

    # 5) 文档校验（gate-report 由 finalize 生成；首次运行未含报告时用 --first-pass 跳过该文件引用）
    if args.pkg_dir:
        cmd = [sys.executable, "scripts/check_release_docs.py",
               "--dir", args.pkg_dir, "--version", v]
        if args.allow_missing_attestation:
            cmd.append("--allow-missing-attestation")
        steps.append(run(cmd, "doc_check"))
    ok = all(s["ok"] for s in steps)
    report = {"version": v, "pass": ok, "inputs": inputs, "steps": steps,
              "attestation": {"finalized": False,
                              "note": "gate-report 计入 SHA256SUMS；通过 shasum -a 256 -c 验证本文件"}}
    out = args.out or os.path.join(ROOT, "work", "lead", f"gate-report-{tag}.json")
    pkg_report = None
    if args.pkg_dir and not args.no_finalize and not ok:
        # 审计 GATE-08：失败时绝不改动包（不写包内报告/SHA/zip），只在 work/lead 留失败报告
        report["attestation"] = {"finalized": False, "package_touched": False,
                                 "reason": "pre-finalize steps failed"}
        with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
            json.dump(report, fo, ensure_ascii=False, indent=1)
        for st in steps:
            print(("PASS " if st["ok"] else "FAIL ") + st["step"])
        print(json.dumps({"pass": False, "report": out, "package_touched": False},
                         ensure_ascii=False))
        return 1
    # 6) finalize（顺序固定，审计 P0-2 修正）：
    #    a) 包内字体 sha 校验（审计 P0-1：换包不设防）
    #    b) 预报告（不含 sha 步）→ 写盘 → SHA → 校验
    #    c) 追加 sha 步骤写最终报告 → 重算 SHA → 校验
    #    d) SHA 冻结后再重建 zip 并校验（保证 zip == 目录包，且报告自称 finalized=True）
    if args.pkg_dir and not args.no_finalize:
        import hashlib as _hash
        import zipfile
        pkg_dir = os.path.join(ROOT, args.pkg_dir)
        pkg_report = os.path.join(pkg_dir, f"gate-report-{tag}.json")
        zip_path = args.zip or (args.pkg_dir.rstrip("/") + ".zip")
        zp = zip_path if os.path.isabs(zip_path) else os.path.join(ROOT, zip_path)

        def _sha_of(path):
            return _hash.sha256(open(path, "rb").read()).hexdigest()

        # a) 包内 TTF 必须与 --font 一致（否则 9/9 PASS 可被换包绕过）
        pkg_ttfs = [f for f in os.listdir(pkg_dir) if f.lower().endswith(".ttf")]
        if not pkg_ttfs:
            steps.append({"step": "pkg_font_sha", "ok": False,
                          "detail": {"error": "包内无 TTF"}})
        else:
            src_sha = _sha_of(os.path.join(ROOT, args.font))
            pkg_sha = _sha_of(os.path.join(pkg_dir, pkg_ttfs[0]))
            steps.append({"step": "pkg_font_sha", "ok": (src_sha == pkg_sha),
                          "detail": {"font_sha": src_sha, "pkg_font": pkg_ttfs[0],
                                     "pkg_font_sha": pkg_sha}})

        def _write_report(rep):
            with open(pkg_report, "w", encoding="utf-8") as fo:
                json.dump(rep, fo, ensure_ascii=False, indent=1)

        def _pkg_rel_files():
            """包内全部文件（递归；review/ 等子目录必须进 SHA 与 zip）。"""
            out = []
            for root, dirs, fs in os.walk(pkg_dir):
                dirs.sort()
                for f in sorted(fs):
                    p = os.path.join(root, f)
                    out.append(os.path.relpath(p, pkg_dir).replace(os.sep, "/"))
            return out

        def _rehash():
            files = [f for f in _pkg_rel_files() if f != "SHA256SUMS"]
            with open(os.path.join(pkg_dir, "SHA256SUMS"), "w", encoding="utf-8") as fo:
                for f in files:
                    fo.write(f"{_sha_of(os.path.join(pkg_dir, f))}  {f}\n")
            return files

        def _verify_sha():
            r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"],
                               cwd=pkg_dir, capture_output=True, text=True)
            failed = [ln for ln in (r.stdout or "").splitlines() if "FAILED" in ln]
            return (r.returncode == 0 and not failed), len((r.stdout or "").splitlines()), failed[:5]

        def _build_zip():
            if os.path.exists(zp):
                os.remove(zp)
            root_name = os.path.basename(pkg_dir.rstrip("/"))
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in _pkg_rel_files():
                    zf.write(os.path.join(pkg_dir, f),
                             arcname=f"{root_name}/{f}")
            return subprocess.run(["unzip", "-t", zp], cwd=ROOT, capture_output=True, text=True)

        # b) 预报告（不含 sha 步）
        pre_ok = all(x["ok"] for x in steps)
        _write_report({"version": v, "pass": pre_ok, "inputs": inputs, "steps": steps,
                       "attestation": {"finalized": False, "stage": "pre-sha"}})
        files = _rehash()
        sha_ok, sha_lines, sha_failed = _verify_sha()
        steps.append({"step": "sha256", "ok": sha_ok,
                      "detail": {"files": len(files), "lines": sha_lines,
                                 "failed": sha_failed, "covers_gate_report": True}})
        # c) 最终报告（含 sha 步）→ 重算 SHA → 校验
        final_ok = all(x["ok"] for x in steps)
        _write_report({"version": v, "pass": final_ok, "inputs": inputs, "steps": steps,
                       "attestation": {"finalized": True, "sha_algorithm": "sha256",
                                       "sha_covers": len(files), "sha_files": files,
                                       "zip": os.path.relpath(zp, ROOT)}})
        files = _rehash()
        sha_ok2, sha_lines2, sha_failed2 = _verify_sha()
        final_ok = final_ok and sha_ok2
        # d) SHA 冻结后再重建 zip（zip == 目录包），校验后不再改动包内任何文件
        rz = _build_zip()
        zip_ok = rz.returncode == 0
        final_ok = final_ok and zip_ok
        # 终态只写 work/lead 报告（不改包内文件，避免破坏已冻结 SHA）
        try:
            with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
                json.dump({"version": v, "pass": final_ok, "inputs": inputs, "steps": steps,
                           "attestation": {"finalized": True,
                                           "sha_final_ok": sha_ok2,
                                           "zip_selfcheck_ok": zip_ok,
                                           "zip": os.path.relpath(zp, ROOT)}},
                          fo, ensure_ascii=False, indent=1)
        except Exception:
            pass
        for st in steps:
            print(("PASS " if st["ok"] else "FAIL ") + st["step"])
        print(json.dumps({"pass": final_ok, "report": out,
                          "pkg_report": os.path.relpath(pkg_report, ROOT),
                          "sha_final_ok": sha_ok2, "zip_ok": zip_ok,
                          "files": len(files)}, ensure_ascii=False))
        return 0 if final_ok else 1
    with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
        json.dump(report, fo, ensure_ascii=False, indent=1)
    for st in steps:
        print(("PASS " if st["ok"] else "FAIL ") + st["step"])
    print(json.dumps({"pass": report["pass"], "report": out,
                      "pkg_report": pkg_report and os.path.relpath(pkg_report, ROOT)},
                     ensure_ascii=False))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
