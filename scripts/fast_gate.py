#!/usr/bin/env python3
"""快闸（≤3 分钟）：每次构建候选都跑；全库扫描只在里程碑前跑（release_gate --scan/--frame-scan）。

检查：字体 QA / 版本 / 字符集差集 / 内容闸（复用按字体 SHA 缓存的结果）/ box 均匀性 /
      发布文档预检（若已有包）/ SHA+zip 自检（若已有包）。
扫描结果缓存：work/gates/<font_sha12>/content_loss.json（复用即不重跑）。
输出：work/lead/fast-gate-<tag>.json；退出码 0=PASS。
"""
import argparse, json, os, subprocess, sys, hashlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r


def cache_dir(font):
    h = hashlib.sha256(open(os.path.join(ROOT, font), "rb").read()).hexdigest()[:12]
    d = os.path.join(ROOT, "work/gates", h)
    os.makedirs(d, exist_ok=True)
    return d, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--baseline-manifest")
    ap.add_argument("--pkg-dir")
    ap.add_argument("--content-max-damaged", type=int, default=0)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    tag = args.tag or args.version
    steps = []

    r = run([sys.executable, "scripts/font_qa.py", "--font", args.font,
             "--manifest", args.manifest, "--outdir", f"work/font/build/qa_fast_{tag}"])
    steps.append({"step": "font_qa", "ok": (r.returncode == 0),
                  "detail": {"tail": (r.stdout or "")[-160:]}})

    r = run([sys.executable, "scripts/stamp_version.py", "--font", args.font,
             "--out", "/tmp/_fastgate_stamp.ttf", "--version", args.version])
    inner = None
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(os.path.join(ROOT, args.font))
        inner = f["name"].getDebugName(5) or ""
    except Exception:
        pass
    ok_ver = (args.version in (inner or "")) or (args.version.replace(".", "") in (inner or ""))
    steps.append({"step": "version", "ok": ok_ver, "detail": {"inner": inner}})

    # 字符集差集（必须给基线，防空转）
    ok_diff = False; diff_detail = {}
    if args.baseline_manifest:
        try:
            new = set(json.load(open(os.path.join(ROOT, args.manifest)))["chars"])
            old = set(json.load(open(os.path.join(ROOT, args.baseline_manifest)))["chars"])
            removed, added = sorted(old - new), sorted(new - old)
            ok_diff = True
            diff_detail = {"removed": len(removed), "added": len(added),
                           "removed_sample": removed[:20]}
        except Exception as e:
            diff_detail = {"error": str(e)[:120]}
    else:
        diff_detail = {"error": "缺 --baseline-manifest（不允许空转）"}
    steps.append({"step": "char_diff", "ok": ok_diff, "detail": diff_detail})

    # 内容闸：按字体 SHA 缓存复用
    content_detail = {}
    if args.baseline:
        cd, sha12 = cache_dir(args.font)
        cached = os.path.join(cd, "content_loss.json")
        if os.path.exists(cached):
            content_detail = json.load(open(cached))
            content_detail["reused"] = True
        else:
            r = run([sys.executable, "scripts/content_loss_gate.py", args.baseline, args.font,
                     args.manifest, cached])
            try:
                rows = json.load(open(cached))
                content_detail = {"damaged": len(rows), "returncode": r.returncode,
                                  "sample": rows[:5], "reused": False}
            except Exception as e:
                content_detail = {"error": str(e)[:120], "returncode": r.returncode}
            json.dump(content_detail, open(cached, "w"), ensure_ascii=False, indent=1)
        ok_content = content_detail.get("damaged") is not None and \
            content_detail.get("damaged", 999) <= args.content_max_damaged and \
            content_detail.get("returncode", 0) in (0, 3)
        steps.append({"step": "content_gate", "ok": bool(ok_content),
                      "detail": {**content_detail, "threshold": args.content_max_damaged}})

    # box 均匀性（同页/同半版的框尺寸方差）
    try:
        man = json.load(open(os.path.join(ROOT, args.manifest)))["chars"]
        import collections, statistics
        by = collections.defaultdict(list)
        for c, r in man.items():
            b = r.get("box")
            if b: by[(r.get("page"), r.get("half"))].append((b[2]-b[0], b[3]-b[1]))
        stds = []
        for k, v in by.items():
            if len(v) > 1:
                stds.append(statistics.pstdev([w for w, h in v]))
                stds.append(statistics.pstdev([h for w, h in v]))
        med = statistics.median(stds) if stds else None
        p95 = sorted(stds)[int(len(stds) * 0.95)] if stds else None
        steps.append({"step": "box_uniformity", "ok": (med is not None and med <= 2.0),
                      "detail": {"same_page_std_median": med, "same_page_std_p95": p95,
                                 "pages": len(by)}})
    except Exception as e:
        steps.append({"step": "box_uniformity", "ok": False,
                      "detail": {"error": str(e)[:120]}})

    # 包存在时：文档预检 + SHA/zip 自检
    if args.pkg_dir and os.path.isdir(os.path.join(ROOT, args.pkg_dir)):
        r = run([sys.executable, "scripts/check_release_docs.py", "--dir", args.pkg_dir,
                 "--version", args.version])
        steps.append({"step": "doc_check", "ok": (r.returncode == 0),
                      "detail": {"tail": (r.stdout or "")[-200:]}})
        d = os.path.join(ROOT, args.pkg_dir)
        if os.path.exists(os.path.join(d, "SHA256SUMS")):
            r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"],
                               cwd=d, capture_output=True, text=True)
            failed = [ln for ln in (r.stdout or "").splitlines() if "FAILED" in ln]
            steps.append({"step": "sha256", "ok": (r.returncode == 0 and not failed),
                          "detail": {"failed": failed[:5]}})
    ok = all(s["ok"] for s in steps)
    out = os.path.join(ROOT, "work/lead", f"fast-gate-{tag}.json")
    json.dump({"version": args.version, "pass": ok, "steps": steps},
              open(out, "w"), ensure_ascii=False, indent=1)
    for s in steps:
        print(("PASS " if s["ok"] else "FAIL ") + s["step"])
    print(f"FAST-GATE {'PASS' if ok else 'FAIL'} -> {out}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
