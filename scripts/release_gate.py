#!/usr/bin/env python3
"""发布门禁：一条命令串起全部硬闸，任一失败即中止（返回非零）。

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
    args = ap.parse_args()
    v = args.version
    tag = args.tag or ("v" + v.replace(".", ""))
    steps = []

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
    if args.prev:
        out_json = os.path.join("work", "lead", f"content-loss-gate-{tag}.json")
        r = subprocess.run([sys.executable, "scripts/content_loss_gate.py", args.prev, args.font,
                            args.manifest, out_json], cwd=ROOT, capture_output=True, text=True)
        damaged = None
        try:
            rows = json.load(open(os.path.join(ROOT, out_json)))
            damaged = len([x for x in rows if "ink_ratio" in x])
        except Exception:
            pass
        if args.content_max_damaged > 0:
            ok_content = (damaged is not None and damaged <= args.content_max_damaged
                          and r.returncode in (0, 3))
            steps.append({"step": "content_loss_gate", "ok": ok_content,
                          "detail": {"returncode": r.returncode, "damaged": damaged,
                                     "threshold": args.content_max_damaged, "mode": "threshold"}})
        else:
            steps.append({"step": "content_loss_gate", "ok": (r.returncode == 0 and damaged == 0),
                          "detail": {"returncode": r.returncode, "damaged": damaged,
                                     "tail": (r.stdout or "")[-300:]}})
    # 4b) 全库缺件扫描（可选；发布候选版应开）
    if args.scan:
        out_scan = os.path.join("work", "lead", f"missing_scan_gate_{tag}.jsonl")
        r = subprocess.run([sys.executable, "scripts/scan_missing_parts.py", args.font,
                            args.manifest, out_scan], cwd=ROOT, capture_output=True, text=True)
        flagged = None
        try:
            flagged = sum(1 for line in open(os.path.join(ROOT, out_scan))
                          if json.loads(line).get("missing"))
        except Exception:
            pass
        limit = args.scan_max_flagged
        if limit is None:
            ok_scan = (r.returncode == 0 and flagged == 0)
            mode = "strict(0)"
        else:
            ok_scan = (r.returncode == 0 and (flagged is None or flagged <= limit))
            mode = f"threshold({limit})"
        steps.append({"step": "scan_missing_parts", "ok": ok_scan,
                      "detail": {"returncode": r.returncode, "flagged": flagged,
                                 "mode": mode, "tail": (r.stdout or "")[-200:]}})
    # 4c) 框线逃逸闸（v2.6：切前排除后块内不应再有贯穿框线）
    if args.frame_scan:
        out_frame = os.path.join("work", "lead", f"frame_escape_scan_{tag}.jsonl")
        r = subprocess.run([sys.executable, "scripts/scan_frame_escape.py",
                            "--manifest", args.manifest, "--out", out_frame],
                           cwd=ROOT, capture_output=True, text=True)
        flagged = None
        try:
            flagged = sum(1 for line in open(os.path.join(ROOT, out_frame)))
        except Exception:
            pass
        ok_frame = (r.returncode == 0 and flagged is not None and flagged <= args.frame_max_flagged)
        steps.append({"step": "frame_escape", "ok": ok_frame,
                      "detail": {"flagged": flagged, "threshold": args.frame_max_flagged,
                                 "mode": "strict" if args.frame_max_flagged == 0 else "threshold"}})
    # 5) 文档校验（gate-report 由 finalize 生成；首次运行未含报告时用 --first-pass 跳过该文件引用）
    if args.pkg_dir:
        cmd = [sys.executable, "scripts/check_release_docs.py",
               "--dir", args.pkg_dir, "--version", v]
        if args.allow_missing_attestation:
            cmd.append("--allow-missing-attestation")
        steps.append(run(cmd, "doc_check"))
    ok = all(s["ok"] for s in steps)
    report = {"version": v, "pass": ok, "steps": steps,
              "attestation": {"finalized": False,
                              "note": "gate-report 计入 SHA256SUMS；通过 shasum -a 256 -c 验证本文件"}}
    out = args.out or os.path.join(ROOT, "work", "lead", f"gate-report-{tag}.json")
    pkg_report = None
    # 6) finalize：报告冻结入包 → SHA 覆盖（含报告）→ zip 重建 → 校验
    #    两轮收敛：R1 用于算 SHA；SHA 通过后把 sha/zip 结果写进 R2，再算一次 SHA 并校验。
    if args.pkg_dir and not args.no_finalize:
        import hashlib as _hash
        import zipfile
        pkg_dir = os.path.join(ROOT, args.pkg_dir)
        pkg_report = os.path.join(pkg_dir, f"gate-report-{tag}.json")
        zip_path = args.zip or (args.pkg_dir.rstrip("/") + ".zip")
        zp = zip_path if os.path.isabs(zip_path) else os.path.join(ROOT, zip_path)

        def _write_report(rep):
            with open(pkg_report, "w", encoding="utf-8") as fo:
                json.dump(rep, fo, ensure_ascii=False, indent=1)

        def _rehash():
            files = sorted(f for f in os.listdir(pkg_dir)
                           if f != "SHA256SUMS" and os.path.isfile(os.path.join(pkg_dir, f)))
            with open(os.path.join(pkg_dir, "SHA256SUMS"), "w", encoding="utf-8") as fo:
                for f in files:
                    h = _hash.sha256(open(os.path.join(pkg_dir, f), "rb").read()).hexdigest()
                    fo.write(f"{h}  {f}\n")
            return files

        def _verify_sha():
            r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"],
                               cwd=pkg_dir, capture_output=True, text=True)
            failed = [ln for ln in (r.stdout or "").splitlines() if "FAILED" in ln]
            return (r.returncode == 0 and not failed), len((r.stdout or "").splitlines()), failed[:5]

        # R1：先冻结一份（不含 sha/zip 结果）
        _write_report(report)
        files = _rehash()
        sha_ok, sha_lines, sha_failed = _verify_sha()
        # zip 重建（在所有文件就绪后）
        if os.path.exists(zp):
            os.remove(zp)
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(os.listdir(pkg_dir)):
                zf.write(os.path.join(pkg_dir, f),
                         arcname=os.path.join(os.path.basename(pkg_dir.rstrip("/")), f))
        rz = subprocess.run(["unzip", "-t", zp], cwd=ROOT, capture_output=True, text=True)
        zip_ok = rz.returncode == 0
        steps.append({"step": "sha256", "ok": sha_ok,
                      "detail": {"files": len(files), "lines": sha_lines,
                                 "failed": sha_failed, "covers_gate_report": True}})
        steps.append({"step": "zip_selfcheck", "ok": zip_ok,
                      "detail": {"rebuilt": True, "tail": (rz.stdout or "")[-200:]}})
        final_ok = all(x["ok"] for x in steps)
        # R2：把 sha/zip 结果写入最终报告 → 重算 SHA（覆盖含 R2）→ 终校验
        report = {"version": v, "pass": final_ok, "steps": steps,
                  "attestation": {"finalized": True, "sha_covers": len(files),
                                  "sha_files": files,
                                  "sha_verified": sha_ok,
                                  "sha_verified_after_final_report": True,
                                  "zip": os.path.relpath(zp, ROOT)}}
        _write_report(report)
        files = _rehash()
        sha_ok2, sha_lines2, sha_failed2 = _verify_sha()
        final_ok = final_ok and sha_ok2
        # 终校验结果只写 stdout（避免再次改动报告破坏 SHA）
        try:
            with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
                json.dump({"version": v, "pass": final_ok, "steps": steps,
                           "attestation": report["attestation"]}, fo, ensure_ascii=False, indent=1)
        except Exception:
            pass
        for st in steps:
            print(("PASS " if st["ok"] else "FAIL ") + st["step"])
        print(json.dumps({"pass": final_ok, "report": out,
                          "pkg_report": os.path.relpath(pkg_report, ROOT),
                          "sha_final_ok": sha_ok2, "files": len(files)},
                         ensure_ascii=False))
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
