#!/usr/bin/env python3
"""快闸（候选版每次跑；全库缺件/框线扫描仍在 release_gate，里程碑前跑）。

步骤（全部必填，缺一即 FAIL，不允许「没给参数就跳过」）：
  1 font_qa                 字体自洽（表/cmap/空字形/bbox/advance/同框；不数孔洞，D21）
  2 version                 内部 name ID5 == "Version <v>"（精确匹配，不再子串）
  3 char_diff               相对基线 manifest 的 removed 必须出现在 quarantine 隔离清单
  4 content_gate            内容缺失闸（按输入绑定 sidecar 复用，输入/脚本变化即重算）
  5 box_uniformity          同页框尺寸：median<=2.0 且 p95<=8.0（p95 防整页相位错）
  6 glyph_frame_gate        字形级框线闸（线段几何判据；v2.6.0 回归样本必须能抓住）
  7 page_geometry_gate      页级几何闸（候选允许已知债阈值，里程碑版由 release_gate 严格 0）
  8 doc_check / sha256      仅 --pkg-dir 存在时（缺 SHA256SUMS 也 FAIL，不静默跳过）

输出：work/lead/fast-gate-<tag>.json（含 inputs 归因：输入 sha/git commit/脚本 sha）。
扫描缓存：work/gates/<font_sha12>/；summary 旁写 .sha256 sidecar，复用前校验。
退出码 0=PASS。
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gate_binding as GB  # noqa: E402


def sha12(path):
    h = hashlib.sha256(open(os.path.join(ROOT, path), "rb").read()).hexdigest()
    return h[:12]


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def cache_dir(font):
    h = sha12(font)
    d = os.path.join(ROOT, "work/gates", h)
    os.makedirs(d, exist_ok=True)
    return d, h


def quarantine_chars():
    q = set()
    files = []
    for p in sorted(glob.glob(os.path.join(ROOT, "work", "lead", "v*_residual.json"))):
        try:
            q |= set(json.load(open(p))["chars"])
            files.append(os.path.relpath(p, ROOT))
        except Exception:
            pass
    return q, files


def load_quarantine_extra(path):
    if not path:
        return set(), []
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    try:
        return set(json.load(open(p))["chars"]), [os.path.relpath(p, ROOT)]
    except Exception:
        return set(), []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--baseline", required=True, help="上一版字体（内容闸基线；必填，不接受空转）")
    ap.add_argument("--baseline-manifest", required=True, help="上一版 manifest（字符差集基线；必填）")
    ap.add_argument("--quarantine", default=None)
    ap.add_argument("--pkg-dir")
    ap.add_argument("--content-max-damaged", type=int, default=0)
    ap.add_argument("--frame-max-flagged", type=int, default=0,
                    help="字形级框线闸阈值；默认 0（严格）")
    ap.add_argument("--skip-glyph-frame", action="store_true",
                    help="调试用：跳过字形级框线闸（会在报告里标记 skipped）")
    ap.add_argument("--max-bad-boxes", type=int, default=400,
                    help="页级几何闸：候选允许的已知 box∩quad 越界数（里程碑版应为 0）")
    ap.add_argument("--max-missing-quad-chars", type=int, default=300)
    ap.add_argument("--max-empty-assign-halves", type=int, default=1200,
                    help="页级几何闸：候选允许已知空指派半版（v2.6.1 实测 1,173；里程碑严格 0）")
    ap.add_argument("--mapping", default="work/lead/mapping_block_v271.jsonl")
    ap.add_argument("--geometry", default="work/lead/page_geometry.jsonl",
                    help="页级几何（传给 page_geometry_gate，避免默认路径与实际版本不一致）")
    ap.add_argument("--stats", default=None, help="build stats（默认 <font>.build_stats.json）")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    tag = args.tag or args.version
    steps = []
    skipped = []

    def add(step, ok, detail):
        steps.append({"step": step, "ok": bool(ok), "detail": detail})

    # 1) 字体 QA
    r = run([sys.executable, "scripts/font_qa.py", "--font", args.font,
             "--manifest", args.manifest, "--outdir", f"work/font/build/qa_fast_{tag}"])
    add("font_qa", r.returncode == 0, {"returncode": r.returncode,
                                       "tail": (r.stdout or "")[-300:]})

    # 2) 版本（精确匹配）
    inner = None
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(os.path.join(ROOT, args.font))
        inner = f["name"].getDebugName(5) or ""
    except Exception as e:
        inner = f"ERROR: {e}"
    add("version", inner == f"Version {args.version}",
        {"inner": inner, "expect": f"Version {args.version}"})

    # 3) 字符差集 + 隔离清单（removed 必须声明）
    try:
        new = set(json.load(open(os.path.join(ROOT, args.manifest)))["chars"])
        old = set(json.load(open(os.path.join(ROOT, args.baseline_manifest)))["chars"])
        removed, added = sorted(old - new), sorted(new - old)
        q, qfiles = quarantine_chars()
        q2, qfiles2 = load_quarantine_extra(args.quarantine)
        q |= q2
        qfiles += qfiles2
        undeclared = [c for c in removed if c not in q]
        add("char_diff", not undeclared,
            {"removed": len(removed), "added": len(added),
             "removed_sample": removed[:20], "undeclared_removed": undeclared[:20],
             "quarantine_n": len(q), "quarantine_files": qfiles})
    except Exception as e:
        add("char_diff", False, {"error": str(e)[:200]})

    # 4) 内容闸（输入绑定 sidecar 复用）
    try:
        cd, font_sha12 = cache_dir(args.font)
        rows_path = os.path.join(cd, "content_loss_rows.json")
        sum_path = os.path.join(cd, "content_loss_summary.json")
        bfiles = {"font": args.font, "baseline": args.baseline, "manifest": args.manifest}
        bscripts = ["content_loss_gate.py", "fidelity_eval.py"]
        cached = None
        if os.path.exists(sum_path) and os.path.exists(rows_path):
            vres = GB.validate_reuse(sum_path, files=bfiles, scripts=bscripts)
            if vres["ok"]:
                try:
                    cached = json.load(open(sum_path))
                    cached["reused"] = True
                except Exception:
                    cached = None
        if cached is None:
            r = run([sys.executable, "scripts/content_loss_gate.py", args.baseline, args.font,
                     args.manifest, rows_path])
            try:
                rows = json.load(open(rows_path))
                cached = {"damaged": len([x for x in rows if "ink_ratio" in x]),
                          "returncode": r.returncode, "sample": rows[:5], "reused": False}
            except Exception as e:
                cached = {"damaged": None, "returncode": r.returncode,
                          "error": str(e)[:150]}
            json.dump(cached, open(sum_path, "w"), ensure_ascii=False, indent=1)
            GB.write_sidecar(sum_path, GB.build_binding(files=bfiles, scripts=bscripts))
        ok_content = (isinstance(cached.get("damaged"), int)
                      and cached["damaged"] <= args.content_max_damaged
                      and cached.get("returncode", 9) in (0, 3))
        add("content_gate", ok_content,
            {**cached, "threshold": args.content_max_damaged,
             "font_sha12": font_sha12})
    except Exception as e:
        add("content_gate", False, {"error": str(e)[:200]})

    # 5) box 均匀性
    try:
        man = json.load(open(os.path.join(ROOT, args.manifest)))["chars"]
        import collections
        import statistics
        by = collections.defaultdict(list)
        for c, r in man.items():
            b = r.get("box")
            if b:
                by[(r.get("page"), r.get("half"))].append((b[2] - b[0], b[3] - b[1]))
        stds = []
        for k, v in by.items():
            if len(v) > 1:
                stds.append(statistics.pstdev([w for w, h in v]))
                stds.append(statistics.pstdev([h for w, h in v]))
        med = statistics.median(stds) if stds else None
        p95 = sorted(stds)[int(len(stds) * 0.95)] if stds else None
        add("box_uniformity", (med is not None and med <= 2.0 and (p95 or 0) <= 8.0),
            {"same_page_std_median": med, "same_page_std_p95": p95, "pages": len(by),
             "thresholds": {"median": 2.0, "p95": 8.0}})
    except Exception as e:
        add("box_uniformity", False, {"error": str(e)[:200]})

    # 6) 字形级框线闸（线段几何；不要孔洞/连通分量）
    gf = os.path.join(ROOT, "scripts", "glyph_frame_gate.py")
    if args.skip_glyph_frame:
        skipped.append("glyph_frame_gate")
        add("glyph_frame_gate", False, {"skipped": True,
                                        "error": "--skip-glyph-frame：候选不允许跳过（仅调试）"})
    elif os.path.exists(gf):
        out_gf = f"work/lead/glyph-frame-gate-fast-{tag}.json"
        r = run([sys.executable, "scripts/glyph_frame_gate.py", "--font", args.font,
                 "--manifest", args.manifest, "--out", out_gf])
        flagged = None
        try:
            flagged = json.load(open(os.path.join(ROOT, out_gf))).get("flagged")
            flagged = len(flagged) if isinstance(flagged, list) else flagged
        except Exception:
            pass
        add("glyph_frame_gate",
            (r.returncode == 0 and isinstance(flagged, int) and flagged <= args.frame_max_flagged),
            {"returncode": r.returncode, "flagged": flagged,
             "threshold": args.frame_max_flagged, "out": out_gf,
             "tail": (r.stdout or "")[-200:]})
    else:
        add("glyph_frame_gate", False, {"error": "脚本缺失 scripts/glyph_frame_gate.py"})

    # 6b) 无拷贝 provenance 闸（manifest/mapping/stats 三者自洽）
    prov = os.path.join(ROOT, "scripts", "provenance_gate.py")
    if os.path.exists(prov):
        out_pv = f"work/lead/provenance-gate-fast-{tag}.json"
        stats_path = args.stats or (os.path.splitext(args.font)[0] + ".build_stats.json")
        r = run([sys.executable, "scripts/provenance_gate.py", "--manifest", args.manifest,
                 "--mapping", args.mapping, "--stats", stats_path, "--out", out_pv])
        add("provenance_gate", r.returncode == 0,
            {"returncode": r.returncode, "out": out_pv, "stats": stats_path,
             "tail": (r.stdout or "")[-200:]})
    else:
        add("provenance_gate", False, {"error": "脚本缺失 scripts/provenance_gate.py"})

    # 7) 页级几何闸（候选允许已披露的已知债阈值；release_gate 用严格 0）
    pg = os.path.join(ROOT, "scripts", "page_geometry_gate.py")
    if os.path.exists(pg):
        out_pg = f"work/lead/page-geometry-gate-fast-{tag}.json"
        r = run([sys.executable, "scripts/page_geometry_gate.py", "--manifest", args.manifest,
                 "--mapping", args.mapping, "--geometry", args.geometry,
                 "--out", out_pg,
                 "--max-bad-boxes", str(args.max_bad_boxes),
                 "--max-missing-quad-chars", str(args.max_missing_quad_chars),
                 "--max-empty-assign-halves", str(args.max_empty_assign_halves)])
        detail = {"returncode": r.returncode, "out": out_pg,
                  "thresholds": {"bad_boxes": args.max_bad_boxes,
                                 "missing_quad_chars": args.max_missing_quad_chars,
                                 "empty_assign_halves": args.max_empty_assign_halves}}
        try:
            rep = json.load(open(os.path.join(ROOT, out_pg)))
            detail["counts"] = rep.get("counts")
        except Exception:
            pass
        add("page_geometry_gate", r.returncode == 0, detail)
    else:
        add("page_geometry_gate", False, {"error": "脚本缺失 scripts/page_geometry_gate.py"})

    # 8) 包存在时：文档预检 + SHA 自检（缺 SHA256SUMS 也 FAIL）
    if args.pkg_dir and os.path.isdir(os.path.join(ROOT, args.pkg_dir)):
        r = run([sys.executable, "scripts/check_release_docs.py", "--dir", args.pkg_dir,
                 "--version", args.version])
        add("doc_check", r.returncode == 0, {"tail": (r.stdout or "")[-300:]})
        d = os.path.join(ROOT, args.pkg_dir)
        sums = os.path.join(d, "SHA256SUMS")
        if not os.path.exists(sums):
            add("sha256", False, {"error": "包内缺 SHA256SUMS"})
        else:
            r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"],
                               cwd=d, capture_output=True, text=True)
            failed = [ln for ln in (r.stdout or "").splitlines() if "FAILED" in ln]
            add("sha256", r.returncode == 0 and not failed, {"failed": failed[:5]})

    ok = all(s["ok"] for s in steps)
    inputs = GB.build_binding(
        files={"font": args.font, "manifest": args.manifest,
               "baseline": args.baseline, "baseline_manifest": args.baseline_manifest,
               "mapping": args.mapping, "geometry": args.geometry},
        scripts=["fast_gate.py", "font_qa.py", "content_loss_gate.py",
                 "glyph_frame_gate.py", "page_geometry_gate.py"])
    out = os.path.join(ROOT, "work/lead", f"fast-gate-{tag}.json")
    json.dump({"version": args.version, "pass": ok, "skipped": skipped,
               "inputs": inputs, "steps": steps},
              open(out, "w"), ensure_ascii=False, indent=1)
    for s in steps:
        print(("PASS " if s["ok"] else "FAIL ") + s["step"])
    print(f"FAST-GATE {'PASS' if ok else 'FAIL'} -> {out}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
