#!/usr/bin/env python3
"""发布包文档/数字机器校验（P0 防复发；v2.6.3 T4 扩容）。

在原「README/PROVENANCE/QA 引用的覆盖数字一致 + 文件引用存在」基础上，v2.6.3 起：
  1) **固定清单扩容**（WORKFLOW §8 / T4 item5）：gate-report、build_recipe、build_stats、
     缺件/框线扫描 jsonl + sidecar、FINALIZE.json、KNOWN-DEBTS、QA、coverage-detail、manifest 等；
  2) **数值对账**（LEAD4-005 / GATE-10）：content damaged/threshold、missing flagged/threshold、
     frame_escape、glyph_frame、bad_boxes、empty_assign、覆盖率/缺口/字形数 —— 以 gate-report、
     manifest、stats.json、coverage-detail 为唯一来源，逐项与 QA.md / KNOWN-DEBTS.md / PROVENANCE.md /
     README.md 对账，改坏任一数字即 FAIL；
  3) **证据绑定校验**：gate-report.scan_artifacts 记录的扫描产物 sha256/sidecar 必须与包内文件一致；
     FINALIZE.json 字段齐全且 font/gate-report/扫描产物 sha 与包内文件一致；OFL/LICENSE sha 必须等于
     仓库根文件（DOCS-403 单一真源）。

用法:
  python scripts/check_release_docs.py --dir release/KangXiKai-v2.6.2 --version 2.6.2
  python scripts/check_release_docs.py --dir <staging> --version 2.6.3 --json-out /tmp/doc_check.json
  # pre-finalize（gate-report / FINALIZE.json 由 finalize 生成，允许暂缺）：
  python scripts/check_release_docs.py --dir <pkg> --version 2.6.3 --allow-missing-attestation
失败返回非零；--json-out 输出结构化结果（供篡改测试断言）。
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASIC = set(chr(c) for c in range(0x4E00, 0xA000))

VNUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def num_tokens(txt):
    """文本里的数字 token（含千分位/百分号）。"""
    return [t.rstrip("%") for t in VNUM_RE.findall(txt)]


def token_matches(tok, value):
    try:
        return int(tok.replace(",", "")) == int(value)
    except Exception:
        return False


def pct_matches(tok, value):
    try:
        return abs(float(tok.rstrip("%")) - float(value)) < 0.011
    except Exception:
        return False


def expect_near(txt, keyword, value, window=160, pct=False):
    """keyword 所在行（同一行内）必须出现数值 value（容忍千分位/百分号）。

    按行而不是按窗口匹配：防止「内容闸 18/35」后面紧邻行的「字形级框线 0」把篡改后的
    数字 0 误判为命中（audit LEAD4-005 篡改测试要求 fail-closed）。
    """
    if value is None:
        return True
    for line in txt.splitlines():
        if keyword not in line:
            continue
        for tok in num_tokens(line):
            if pct_matches(tok, value) if pct else token_matches(tok, value):
                return True
    return False


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _parse_tail_json(tail):
    """旧版 release_gate 的 page_geometry step 只有 out/tail；从 tail 里提取末个 JSON 对象。"""
    if not tail:
        return {}
    s = tail.strip()
    # 从右往左找能以 {...} 解析的最长后缀（stdout tail 可能从中间截断）
    for i in range(len(s) - 1, -1, -1):
        if s[i] != "{":
            continue
        try:
            return json.loads(s[i:])
        except Exception:
            continue
    return {}


def gate_numbers(gate):
    """从 gate-report 提取权威闸数字（唯一来源）。"""
    if not gate:
        return {}
    steps = {s.get("step"): s for s in (gate.get("steps") or [])}

    def det(name):
        return (steps.get(name) or {}).get("detail") or {}

    cl = det("content_loss_gate")
    sm = det("scan_missing_parts")
    fe = det("frame_escape")
    gf = det("glyph_frame_gate")
    pg = det("page_geometry_gate")
    pg_counts = pg.get("counts") or {}
    pg_thr = pg.get("thresholds") or {}
    if not pg_counts:
        blob = _parse_tail_json(pg.get("tail"))
        pg_counts = blob.get("counts") or {}
        pg_thr = blob.get("thresholds") or {}
        if not pg_counts and pg.get("tail"):
            # stdout tail 从中间截断时 JSON 无法解析：按 key 正则兜底
            for k in ("bad_boxes", "empty_assign_halves", "missing_quad_chars"):
                mm = re.search(rf'"{k}"\s*:\s*(\d+)', pg["tail"])
                if mm:
                    pg_counts[k] = int(mm.group(1))
    mthr = sm.get("threshold")
    if mthr is None:
        mm = re.search(r"threshold\((\d+)\)", sm.get("mode") or "")
        if mm:
            mthr = int(mm.group(1))
    if mthr is None and sm.get("artifact"):
        mthr = (sm["artifact"] or {}).get("flagged")
    return {
        "font_qa_ok": bool((steps.get("font_qa") or {}).get("ok")),
        "content_damaged": cl.get("damaged"),
        "content_threshold": cl.get("threshold"),
        "missing_flagged": sm.get("flagged"),
        "missing_threshold": mthr,
        "frame_flagged": fe.get("flagged"),
        "frame_threshold": fe.get("threshold"),
        "glyph_frame_flagged": gf.get("flagged"),
        "bad_boxes": pg_counts.get("bad_boxes"),
        "empty_assign": pg_counts.get("empty_assign_halves"),
        "scan_artifacts": gate.get("scan_artifacts") or {},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="发布包目录")
    ap.add_argument("--version", required=True)
    ap.add_argument("--allow-missing-attestation", action="store_true",
                    help="首跑模式：gate-report-*.json / FINALIZE.json 尚未生成，允许暂缺")
    ap.add_argument("--json-out", default=None, help="机器可读结果输出（可选）")
    args = ap.parse_args()
    d = args.dir
    v = args.version
    tag = "v" + v.replace(".", "")
    errs = []
    warns = []
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            errs.append(f"[{name}] {detail}")

    files = set()
    for root, dirs, fs in os.walk(d):
        dirs.sort()
        for f in sorted(fs):
            files.add(os.path.relpath(os.path.join(root, f), d).replace(os.sep, "/"))

    def has(name):
        return name in files

    def find_glob(pattern):
        return sorted(f for f in files if fnmatch.fnmatchcase(f, pattern))

    # 0) 固定清单（WORKFLOW §8 + T4 item5）
    ttf = f"KangXiKai-Regular-v{v}.ttf"
    required = [
        ttf, f"manifest-{tag}.json", f"coverage-detail-{tag}.json",
        f"qa-report-{tag}.json", f"qa-stats-{tag}.json",
        f"residual-quarantine-{tag}.json", f"known-debt-{tag}.md", "KNOWN-DEBTS.md",
        "QA.md", "PROVENANCE.md", "README.md", "SHA256SUMS",
        "stats.json", "provenance.json", f"provenance-detail-{tag}.json",
        "coverage.txt", "OFL.txt", "LICENSE",
        f"build_recipe-{tag}.json",
    ]
    cl_files = find_glob("content-loss-*.json")
    required += cl_files
    if not cl_files:
        errs.append("[required] 缺 content-loss-<prev>-<ver>.json")
    required += find_glob("KangXiKai-v*.build_stats.json") or ["<font>.build_stats.json"]
    scan_required = []
    for kind in ("missing_scan_*.jsonl", "frame_scan_*.jsonl"):
        got = find_glob(kind)
        scan_required += got
        scan_required += [f + ".sha256" for f in got]
        if not got:
            errs.append(f"[required] 缺 {kind} 证据文件")
    required += scan_required
    if not args.allow_missing_attestation:
        required += [f"gate-report-{tag}.json", "FINALIZE.json"]
    for r in required:
        if r not in files:
            errs.append(f"[required] 包内缺文件 {r}")

    # 1) 读取权威来源
    man = load_json(os.path.join(d, f"manifest-{tag}.json")) or {}
    stats = load_json(os.path.join(d, "stats.json")) or {}
    cov = load_json(os.path.join(d, f"coverage-detail-{tag}.json")) or {}
    gate_path = os.path.join(d, f"gate-report-{tag}.json")
    gate = load_json(gate_path) if has(f"gate-report-{tag}.json") else None
    nums = gate_numbers(gate)
    n_chars = len((man.get("chars") or {})) or None
    if n_chars is None:
        cands = sorted(f for f in files if f.startswith("manifest-") and f.endswith(".json"))
        if cands:
            n_chars = len((load_json(os.path.join(d, cands[0])) or {}).get("chars") or {}) or None

    check("manifest_chars", n_chars is not None and stats.get("cmap") == n_chars,
          f"manifest={n_chars} stats.cmap={stats.get('cmap')}")
    check("stats_font_sha", bool(stats.get("sha256")) == bool(has(ttf)) and (
        not has(ttf) or stats.get("sha256") == sha256_file(os.path.join(d, ttf))),
        f"stats.sha256={stats.get('sha256')} ttf={'present' if has(ttf) else 'missing'}")
    check("stats_real", stats.get("real") == n_chars,
          f"stats.real={stats.get('real')} chars={n_chars}")
    if has("provenance.json") and n_chars:
        prov = load_json(os.path.join(d, "provenance.json")) or {}
        check("provenance_count", len(prov) == n_chars, f"provenance={len(prov)} chars={n_chars}")

    # 2) 覆盖率/缺口（以 manifest + canonical 目标表可复算；与 coverage-detail 对账）
    target = set()
    tp = os.path.join(ROOT, "work/seq/canonical.jsonl")
    if os.path.exists(tp):
        for line in open(tp, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ch = rec.get("char")
            if ch and len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
                target.add(ch)
    if target and n_chars:
        covered = len(set(man.get("chars") or {}) & target)
        pct = round(100.0 * covered / len(target), 2)
        gap = max(0, len(target) - covered)
        basic_covered = len(set(man.get("chars") or {}) & BASIC)
        check("coverage_detail_counts",
              cov.get("total_glyphs") == n_chars
              and cov.get("cjk_basic_in_target_set") == covered
              and abs(float(cov.get("basic_coverage_pct") or 0) - pct) < 0.011
              and cov.get("target_headword_gap") == gap
              and cov.get("basic_block_20992_pct") is not None,
              f"cov={ {k: cov.get(k) for k in ('total_glyphs', 'cjk_basic_in_target_set', 'basic_coverage_pct', 'target_headword_gap')} } "
              f"recompute=({covered}, {pct}, {gap})")
        check("stats_coverage", stats.get("target_covered") == covered
              and abs(float(stats.get("target_coverage_pct") or 0) - pct) < 0.011
              and stats.get("target_headword_gap") == gap,
              f"stats.target_covered={stats.get('target_covered')} "
              f"stats.target_coverage_pct={stats.get('target_coverage_pct')} stats.gap={stats.get('target_headword_gap')}")
    else:
        covered = cov.get("cjk_basic_in_target_set")
        pct = cov.get("basic_coverage_pct")
        gap = cov.get("target_headword_gap")
        warns.append("缺 work/seq/canonical.jsonl 或 manifest，跳过覆盖率复算")
    # 供文档对账用的权威数字
    A = {
        "chars": n_chars, "pct": pct, "gap": gap,
        "content": nums.get("content_damaged"), "content_thr": nums.get("content_threshold"),
        "missing": nums.get("missing_flagged"), "missing_thr": nums.get("missing_threshold"),
        "frame": nums.get("frame_flagged"), "glyph_frame": nums.get("glyph_frame_flagged"),
        "bad_boxes": nums.get("bad_boxes"), "empty_assign": nums.get("empty_assign"),
    }

    # 3) 文本数字对账（QA / KNOWN-DEBTS / PROVENANCE / README）
    texts = {}
    for name in ("QA.md", "KNOWN-DEBTS.md", f"known-debt-{tag}.md", "PROVENANCE.md", "README.md"):
        if has(name):
            texts[name] = open(os.path.join(d, name), encoding="utf-8").read()

    def check_text(name, keyword, value, pct=False, required=False):
        if name not in texts:
            return
        txt = texts[name]
        if keyword not in txt:
            if required:
                check(f"text:{name}:{keyword}", False, f"未出现关键词 {keyword}")
            return
        check(f"text:{name}:{keyword}", expect_near(txt, keyword, value, pct=pct),
              f"{keyword} 附近未出现权威值 {value}")

    if gate:
        qa = "QA.md"
        check_text(qa, "内容闸", A["content"], required=True)
        if A["content_thr"] is not None:
            check_text(qa, "内容闸", A["content_thr"], required=True)
        check_text(qa, "缺件扫描", A["missing"], required=True)
        if A["missing_thr"] is not None:
            check_text(qa, "缺件扫描", A["missing_thr"], required=True)
        check_text(qa, "字形级框线", A["glyph_frame"], required=True)
        check_text(qa, "框线逃逸", A["frame"], required=True)
        check_text(qa, "bad_boxes", A["bad_boxes"], required=True)
        check_text(qa, "empty_assign", A["empty_assign"], required=True)
        if pct is not None:
            check_text(qa, "目标表", pct, pct=True, required=True)
            check_text(qa, "缺口", gap, required=True)
        for name in ("KNOWN-DEBTS.md", f"known-debt-{tag}.md"):
            if name not in texts:
                continue
            check_text(name, "缺件扫描", A["missing"])
            check_text(name, "内容闸", A["content"])
            check_text(name, "字形级框线", A["glyph_frame"])
            check_text(name, "框线逃逸", A["frame"])
            check_text(name, "empty_assign", A["empty_assign"])
            if pct is not None:
                check_text(name, "目标表", pct, pct=True)
                check_text(name, "缺口", gap)
            check_text(name, "字形数", A["chars"])
        for name in ("PROVENANCE.md", "README.md"):
            if name in texts and pct is not None:
                check_text(name, "目标表", pct, pct=True)
                check_text(name, "缺口", gap)
        if "README.md" in texts:
            check("README_version", v in texts["README.md"], f"README.md 未出现版本号 {v}")
    else:
        warns.append("gate-report 缺失：跳过闸数字对账（pre-finalize 首跑允许）")

    # 4) 版本号/引用存在性（原 P0 检查，保留）
    for name in ("README.md", "PROVENANCE.md", "QA.md"):
        if name in texts and v not in texts[name]:
            check(f"version:{name}", False, f"{name}: 未出现版本号 {v}")
    ignore_refs = set(required) | {"SHA256SUMS", "OFL.txt", "LICENSE",
                                   "README.md", "PROVENANCE.md", "QA.md"}
    ref_re = re.compile(r"[A-Za-z0-9_.\-]+\.(?:jsonl|json|png|md)\b")
    for name, txt in texts.items():
        for m in ref_re.finditer(txt):
            ref = m.group(0)
            if ref in ignore_refs or ref.startswith(("gate-report-", "FINALIZE")):
                continue
            # 通配模式（README 证据表里的 `missing_scan_*.jsonl` 等）不是具体引用
            if ref.startswith(".") or txt[max(0, m.start() - 1):m.start()] == "*":
                continue
            # 仓库文档路径（docs/…、../…）不是包内引用
            prefix = txt[max(0, m.start() - 8):m.start()]
            if "docs/" in prefix or "../" in prefix or prefix.endswith("`docs/"):
                continue
            if ref not in files and ref not in texts:
                check(f"ref:{name}", False, f"{name}: 引用不存在文件 {ref}")

    # 5) gate-report 证据校验：字体/版本/步骤/扫描产物 sha
    if gate:
        check("gate_version", gate.get("version") in (v, None), f"gate.version={gate.get('version')}")
        check("gate_pass", gate.get("pass") is True, f"gate.pass={gate.get('pass')}")
        steps = {s.get("step") for s in (gate.get("steps") or [])}
        need_steps = {"font_qa", "content_loss_gate", "scan_missing_parts", "frame_escape",
                      "glyph_frame_gate", "provenance_gate", "page_geometry_gate"}
        check("gate_steps", need_steps <= steps, f"缺步骤 {sorted(need_steps - steps)}")
        g_font_sha = ((gate.get("inputs") or {}).get("sha256") or {}).get("font")
        if g_font_sha and has(ttf):
            check("gate_font_sha", g_font_sha == sha256_file(os.path.join(d, ttf)),
                  f"gate.inputs.font={g_font_sha}")
        sa = gate.get("scan_artifacts") or {}
        if sa:
            for kind, rec in sa.items():
                if not rec:
                    continue
                base = os.path.basename(rec.get("path") or "")
                p = os.path.join(d, base)
                side = os.path.join(d, base + ".sha256")
                check(f"scan_artifact:{kind}",
                      os.path.exists(p) and sha256_file(p) == rec.get("sha256")
                      and os.path.exists(side)
                      and sha256_file(side) == ((rec.get("sidecar") or {}).get("sha256")),
                      f"{base} sha/sidecar 与 gate-report 记录不一致")
                check(f"scan_artifact_binding:{kind}", bool(rec.get("ok")),
                      f"gate-report 记录 sidecar 校验未通过: {rec.get('reason')}")
        elif not args.allow_missing_attestation:
            check("scan_artifacts_recorded", False,
                  "gate-report 缺 scan_artifacts（T4 起必须记录扫描产物 sha/sidecar 校验）")

    # 6) FINALIZE.json（字段齐全 + 与包内文件 sha 一致；包内自指字段允许 null + scope 说明）
    if has("FINALIZE.json"):
        fin = load_json(os.path.join(d, "FINALIZE.json")) or {}
        need_keys = ["finalize_version", "version", "created_utc", "git", "font_sha256",
                     "gate_report_sha256", "sha_final_ok", "zip_ok", "zip_sha256",
                     "zip_sha256_scope", "zip_payload_sha256", "scan_artifacts", "record_scope"]
        miss = [k for k in need_keys if k not in fin]
        check("finalize_keys", not miss, f"FINALIZE.json 缺字段 {miss}")
        check("finalize_version", fin.get("finalize_version") == 1,
              f"finalize_version={fin.get('finalize_version')}")
        check("finalize_version_match", fin.get("version") == v, f"FINALIZE.version={fin.get('version')}")
        check("finalize_created", bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                                                    str(fin.get("created_utc") or ""))),
              f"created_utc={fin.get('created_utc')}")
        check("finalize_git", bool((fin.get("git") or {}).get("commit")),
              f"git={fin.get('git')}")
        if has(ttf):
            check("finalize_font_sha", fin.get("font_sha256") == sha256_file(os.path.join(d, ttf)),
                  "FINALIZE.font_sha256 与包内 TTF 不一致")
        if has(f"gate-report-{tag}.json"):
            check("finalize_gate_sha",
                  fin.get("gate_report_sha256") == sha256_file(os.path.join(d, f"gate-report-{tag}.json")),
                  "FINALIZE.gate_report_sha256 与包内 gate-report 不一致")
        # payload sha（排除 FINALIZE.json / SHA256SUMS，自指不可内嵌）
        rows = []
        for rel in sorted(files):
            if rel in ("FINALIZE.json", "SHA256SUMS"):
                continue
            rows.append(f"{sha256_file(os.path.join(d, rel))}  {rel}")
        payload = hashlib.sha256(("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")).hexdigest()
        check("finalize_payload_sha", fin.get("zip_payload_sha256") == payload,
              "FINALIZE.zip_payload_sha256 与包 payload 不一致")
        ref_scan = (gate or {}).get("scan_artifacts") or {}
        for kind, rec in (fin.get("scan_artifacts") or {}).items():
            base = os.path.basename(rec.get("path") or "")
            p = os.path.join(d, base)
            ok = os.path.exists(p) and sha256_file(p) == rec.get("sha256")
            side_rel = (rec.get("sidecar") or {}).get("path")
            if side_rel:
                sp = os.path.join(d, side_rel)
                ok = ok and os.path.exists(sp) and sha256_file(sp) == (rec.get("sidecar") or {}).get("sha256")
            check(f"finalize_scan:{kind}", ok, f"FINALIZE.scan_artifacts[{kind}] 与包内文件不一致")
    elif not args.allow_missing_attestation:
        check("finalize_present", False, "包内缺 FINALIZE.json（finalize 未完成）")

    # 7) OFL/LICENSE 单一真源（DOCS-403）
    for name in ("OFL.txt", "LICENSE"):
        root_p = os.path.join(ROOT, name)
        pkg_p = os.path.join(d, name)
        if not os.path.exists(root_p):
            check(f"root:{name}", False, f"仓库根缺 {name}（单一真源）")
        elif not os.path.exists(pkg_p):
            check(f"pkg:{name}", False, f"包内缺 {name}")
        else:
            check(f"single_source:{name}", sha256_file(root_p) == sha256_file(pkg_p),
                  f"包内 {name} 与仓库根 sha 不一致（应从根复制，DOCS-403）")

    # 8) SHA256SUMS 覆盖（文件清单完整性；逐文件 sha）
    if has("SHA256SUMS"):
        listed = {}
        bad = []
        try:
            for ln in open(os.path.join(d, "SHA256SUMS"), encoding="utf-8"):
                ln = ln.rstrip("\n")
                if not ln:
                    continue
                h, rel = ln.split("  ", 1)
                listed[rel] = h
        except Exception as e:
            bad.append(f"解析失败 {e}")
        for rel, h in listed.items():
            p = os.path.join(d, rel)
            if not os.path.exists(p):
                bad.append(f"缺失 {rel}")
            elif sha256_file(p) != h:
                bad.append(f"sha 不符 {rel}")
        non_sha = set(f for f in files if f != "SHA256SUMS")
        bad += [f"未覆盖 {rel}" for rel in sorted(non_sha - set(listed))]
        bad += [f"多余条目 {rel}" for rel in sorted(set(listed) - non_sha)]
        check("sha256sums", not bad, "; ".join(bad[:8]))

    result = {"dir": d, "version": v, "pass": not errs, "errors": errs,
              "warnings": warns, "authoritative": A,
              "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "checks_failed": [c for c in checks if not c["ok"]]}
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fo:
            json.dump(result, fo, ensure_ascii=False, indent=1)
    if errs:
        print("DOC-CHECK FAIL:")
        for e in errs:
            print("  -", e)
        for w in warns:
            print("  WARN:", w)
        return 1
    print(f"DOC-CHECK PASS: {v} chars {n_chars}"
          + (f" | content {A['content']}/{A['content_thr']} missing {A['missing']}/{A['missing_thr']} "
             f"frame {A['frame']} glyph_frame {A['glyph_frame']} empty_assign {A['empty_assign']} "
             f"bad_boxes {A['bad_boxes']} pct {pct}" if gate else " (pre-finalize: gate 数字未对账)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
