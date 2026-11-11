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
    quarantine = set()
    qp = os.path.join(ROOT, "work", "lead", "v255_residual.json")
    for cand in ("work/lead/v255_residual.json", "work/lead/v251_residual.json"):
        p = os.path.join(ROOT, cand)
        if os.path.exists(p):
            quarantine |= set(json.load(open(p))["chars"])
            break
    undeclared = [c for c in removed if c not in quarantine]
    steps.append({"step": "char_diff", "ok": not undeclared,
                  "detail": {"removed": removed, "added": added, "undeclared_removed": undeclared}})

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
        steps.append({"step": "scan_missing_parts", "ok": (r.returncode == 0),
                      "detail": {"returncode": r.returncode, "flagged": flagged,
                                 "tail": (r.stdout or "")[-200:]}})
    # 5) 文档校验
    if args.pkg_dir:
        steps.append(run([sys.executable, "scripts/check_release_docs.py",
                          "--dir", args.pkg_dir, "--version", v], "doc_check"))
        sha = os.path.join(args.pkg_dir, "SHA256SUMS")
        if os.path.exists(os.path.join(ROOT, sha)):
            r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"],
                               cwd=os.path.join(ROOT, args.pkg_dir), capture_output=True, text=True)
            failed = [l for l in (r.stdout or "").splitlines() if "FAILED" in l]
            steps.append({"step": "sha256", "ok": r.returncode == 0 and not failed,
                          "detail": {"lines": len((r.stdout or "").splitlines()), "failed": failed[:5]}})
        zip_path = f"{args.pkg_dir}.zip"
        if os.path.exists(os.path.join(ROOT, zip_path)):
            r = subprocess.run(["unzip", "-t", zip_path], cwd=ROOT, capture_output=True, text=True)
            steps.append({"step": "zip_selfcheck", "ok": r.returncode == 0,
                          "detail": {"tail": (r.stdout or "")[-300:]}})

    ok = all(s["ok"] for s in steps)
    report = {"version": v, "pass": ok, "steps": steps}
    out = args.out or os.path.join("work", "lead", f"gate-report-{tag}.json")
    with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
        json.dump(report, fo, ensure_ascii=False, indent=1)
    for s in steps:
        print(("PASS " if s["ok"] else "FAIL ") + s["step"])
    print(json.dumps({"pass": ok, "report": out}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
