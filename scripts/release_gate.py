#!/usr/bin/env python3
"""发布门禁：一条命令串起全部硬闸。所有步骤都会执行并记录，然后统一判定（返回非零）。

证据链纪律（v2.6.3 T4 / audit4）：
  - **pre-finalize 失败零写包**：未通过时不写包内报告/SHA/zip，只在 work/lead 留失败报告；
  - **finalize 原子化**（LEAD4-002）：所有写包动作先在同一文件系统的临时 staging 目录完成，
    全部校验通过后才原子替换包目录与 zip；任何一步失败 → 原包/原 zip 字节不变；
  - **扫描产物绑定**（DATA-403/GATE-404 / T4 item3）：gate-report 记录缺件/框线扫描 jsonl 的
    sha256、created_utc、sidecar sha256 与 sidecar 校验结果；扫描与字体/manifest/sidecar 不匹配即 FAIL；
  - **FINALIZE.json**（LEAD4-001 / T4 item4）：finalize 成功后写只读 FINALIZE.json（包内 + 包外 detached），
    记录 font/gate-report/扫描产物 sha、git、created_utc、finalize_version；包内记录不含自指的
    sha_final_ok/zip_ok（自指不可内嵌），这两项由包外 `<pkg>.FINALIZE.json` 记录实际 zip sha 与终验结果；
  - 复用扫描/内容结果必须带输入绑定 sidecar，输入或脚本变化即 FAIL（BF-12 / GATE-401）；
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
  5) 缺件/框线扫描（fresh 或 reuse；均要求产物 + sidecar 输入绑定，gate-report 记录产物 sha）
  6) 三闸：glyph_frame_gate / provenance_gate / page_geometry_gate
  7) check_release_docs（包存在时；pre-finalize 允许 gate-report/FINALIZE 暂缺）
  8) finalize：包内 TTF sha → 预检 → staging 写终版 gate-report + FINALIZE.json + SHA256SUMS + zip
     → 全部校验 → 原子替换 → 包外 detached FINALIZE + zip sha 记录
输出 gate-report.json（成功才写 PASS）。
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gate_binding as GB  # noqa: E402

FINALIZE_VERSION = 1
GARBAGE_NAMES = (".DS_Store",)


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def _rel(path):
    try:
        return os.path.relpath(_abs(path), ROOT)
    except Exception:
        return str(path)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, name):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0
    return {"step": name, "cmd": " ".join(cmd), "ok": ok,
            "stdout": (r.stdout or "")[-1500:], "stderr": (r.stderr or "")[-800:]}


# --------------------------------------------------------------------------- #
# 扫描产物绑定（T4 item3 / DATA-403 / GATE-404 / GATE-401）
# --------------------------------------------------------------------------- #
def validate_scan_artifact(path, expected_files, expected_scripts, include_reffont=False):
    """校验一个扫描产物 + 它的 `<out>.sha256` sidecar。

    返回记录（写进 gate-report 的 scan_artifacts）：
      {path, sha256, bytes, rows, flagged, error_rows, created_utc, git,
       sidecar:{path, sha256, exists}, ok, reason, missing, mismatch}
    FAIL 条件（fail-closed）：产物不存在 / sidecar 缺失 / sidecar 记录的输入或脚本与当前不一致 /
    sidecar 有未纳入校验的多余键。
    """
    p = _abs(path)
    rec = {"path": _rel(p), "exists": os.path.exists(p), "sha256": None, "bytes": None,
           "rows": None, "flagged": None, "error_rows": None,
           "created_utc": None, "git": None,
           "sidecar": {"path": _rel(GB.sidecar_path(p)),
                       "sha256": None, "exists": os.path.exists(GB.sidecar_path(p))},
           "ok": False, "reason": "", "missing": [], "mismatch": {}}
    if not rec["exists"]:
        rec["reason"] = "扫描产物不存在"
        return rec
    rec["sha256"] = GB.sha256_file(p)
    rec["bytes"] = os.path.getsize(p)
    rec["sidecar"]["sha256"] = GB.sha256_file(GB.sidecar_path(p)) if rec["sidecar"]["exists"] else None
    rows = []
    try:
        for ln in open(p, encoding="utf-8"):
            if ln.strip():
                rows.append(json.loads(ln))
    except Exception as e:
        rec["reason"] = f"扫描产物解析失败: {str(e)[:120]}"
        return rec
    rec["rows"] = len(rows)
    rec["flagged"] = sum(1 for r in rows if r.get("missing") or (not r.get("error") and "missing" not in r and False))
    rec["flagged"] = sum(1 for r in rows if r.get("missing"))
    rec["error_rows"] = sum(1 for r in rows if r.get("error"))
    sc = GB.read_sidecar(p)
    if sc is None:
        rec["reason"] = "缺少 sidecar（<out>.sha256），无法证明扫描输入与字体一致"
        return rec
    rec["created_utc"] = sc.get("created_utc")
    rec["git"] = sc.get("git")
    expect_files = {}
    for name, fpath in (expected_files or {}).items():
        expect_files[name] = GB.sha256_file(fpath) if fpath else None
    if include_reffont:
        try:
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            import reffont
            expect_files["reffont"] = GB.sha256_file(reffont.path())
        except Exception:
            expect_files["reffont"] = None
    sc_sha = sc.get("sha256") or {}
    for name, want in expect_files.items():
        got = sc_sha.get(name)
        if got is None:
            rec["missing"].append(name)
        elif got != want:
            rec["mismatch"][name] = {"sidecar": (got or "")[:12], "current": (want or "")[:12]}
    extra = sorted(set(sc_sha) - set(expect_files))
    if extra:
        rec["mismatch"]["sidecar_has_unverified_keys"] = extra
    sc_scripts = sc.get("scripts") or {}
    for name in (expected_scripts or []):
        want = GB.script_sha(name)
        got = sc_scripts.get(name)
        if got is None:
            rec["missing"].append(f"script:{name}")
        elif got != want:
            rec["mismatch"][f"script:{name}"] = {"sidecar": (got or "")[:12],
                                                "current": (want or "")[:12]}
    extra_s = sorted(set(sc_scripts) - set(expected_scripts or []))
    if extra_s:
        rec["mismatch"]["sidecar_has_unverified_scripts"] = extra_s
    # v2.6.4：产物自身 sha 必须绑定在 sidecar.extra.out_sha256（失败/被改产物不可复用）
    sc_extra = sc.get("extra") or {}
    if not sc_extra.get("out_sha256"):
        rec["missing"].append("extra:out_sha256")
    elif sc_extra["out_sha256"] != rec["sha256"]:
        rec["mismatch"]["out_sha256"] = {"sidecar": str(sc_extra["out_sha256"])[:12],
                                         "current": (rec["sha256"] or "")[:12]}
    if not rec["missing"] and not rec["mismatch"]:
        rec["ok"] = True
    else:
        rec["reason"] = "sidecar 与当前输入/脚本不一致（产物与字体或 sidecar 不匹配）"
    return rec


# --------------------------------------------------------------------------- #
# finalize（T4 item4）：staging → 全验 → 原子替换 → detached 终验记录
# --------------------------------------------------------------------------- #
def _payload_manifest_sha(pkg_dir):
    """包 payload 的确定性摘要：全部文件（排除自指的 FINALIZE.json 与 SHA256SUMS）的
    `sha256  relpath` 排序行的 sha256。可由发布包逐文件复算（verify_release.py）。"""
    entries = []
    for root, dirs, files in os.walk(pkg_dir):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, pkg_dir).replace(os.sep, "/")
            if rel in ("FINALIZE.json", "SHA256SUMS"):
                continue
            entries.append((rel, sha256_file(p)))
    entries.sort()
    rows = [f"{h}  {rel}" for rel, h in entries]
    return hashlib.sha256(("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")).hexdigest(), rows


def _write_sha256sums(pkg_dir):
    rows = []
    for root, dirs, files in os.walk(pkg_dir):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, pkg_dir).replace(os.sep, "/")
            if rel == "SHA256SUMS":
                continue
            rows.append((sha256_file(p), rel))
    with open(os.path.join(pkg_dir, "SHA256SUMS"), "w", encoding="utf-8") as fo:
        for h, rel in rows:
            fo.write(f"{h}  {rel}\n")
    return rows


def _verify_sha256sums(pkg_dir):
    expected = {}
    try:
        for ln in open(os.path.join(pkg_dir, "SHA256SUMS"), encoding="utf-8"):
            ln = ln.rstrip("\n")
            if not ln:
                continue
            h, rel = ln.split("  ", 1)
            expected[rel] = h
    except FileNotFoundError:
        return False, ["SHA256SUMS 不存在"]
    bad = []
    for rel, h in expected.items():
        p = os.path.join(pkg_dir, rel)
        if not os.path.exists(p):
            bad.append(f"缺失 {rel}")
        elif sha256_file(p) != h:
            bad.append(f"sha 不符 {rel}")
    listed = set(expected)
    actual = set()
    for root, dirs, files in os.walk(pkg_dir):
        dirs.sort()
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), pkg_dir).replace(os.sep, "/")
            if rel != "SHA256SUMS":
                actual.add(rel)
    for rel in sorted(actual - listed):
        bad.append(f"未列入 SHA256SUMS: {rel}")
    return (not bad), bad


def _zip_members(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return {n.split("/", 1)[1]: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def _build_zip(pkg_dir, zip_path):
    """确定性 zip：排序成员 + 固定时间戳 + 固定压缩级别（同平台字节可复现）。"""
    prefix = os.path.basename(pkg_dir.rstrip(os.sep))
    names = []
    for root, dirs, files in os.walk(pkg_dir):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, pkg_dir).replace(os.sep, "/")
            names.append((rel, p))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, p in names:
            zi = zipfile.ZipInfo(f"{prefix}/{rel}", date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o100644 << 16
            with open(p, "rb") as fh:
                zf.writestr(zi, fh.read())
    return names


def _verify_zip_matches_dir(pkg_dir, zip_path):
    bad = []
    members = _zip_members(zip_path)
    dir_files = {}
    for root, dirs, files in os.walk(pkg_dir):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            dir_files[os.path.relpath(p, pkg_dir).replace(os.sep, "/")] = p
    if set(members) != set(dir_files):
        bad.append(f"zip/目录文件集合不一致: only_zip={sorted(set(members)-set(dir_files))[:6]} "
                   f"only_dir={sorted(set(dir_files)-set(members))[:6]}")
    for rel, p in dir_files.items():
        if rel in members and members[rel] != open(p, "rb").read():
            bad.append(f"zip/目录内容不一致: {rel}")
    return (not bad), bad


def _clean_garbage(pkg_dir):
    removed = []
    for root, dirs, files in os.walk(pkg_dir):
        for f in list(files):
            if f in GARBAGE_NAMES or f.startswith("._") or f.endswith(".tmp"):
                rel = os.path.relpath(os.path.join(root, f), pkg_dir).replace(os.sep, "/")
                os.remove(os.path.join(root, f))
                removed.append(rel)
    return removed


def finalize_package(args, v, tag, steps, inputs, scan_artifacts, out_report, inject_fail=None):
    """原子 finalize：返回 (ok, steps, finalize_info)。失败时原包/原 zip 不变。"""
    pkg_dir = _abs(args.pkg_dir).rstrip(os.sep)
    zip_path = _abs(args.zip) if args.zip else pkg_dir + ".zip"
    parent = os.path.dirname(pkg_dir) or "."
    staging_root = tempfile.mkdtemp(prefix=f".finalize-{tag}-", dir=parent)
    staging_pkg = os.path.join(staging_root, os.path.basename(pkg_dir))
    staging_zip = os.path.join(staging_root, os.path.basename(zip_path))
    backup_pkg = None
    backup_zip = None
    # 预检步骤里已有 pkg_font_sha；staging 内复核后只保留一份
    local_steps = [x for x in steps if x.get("step") != "pkg_font_sha"]
    info = {"detail": {}}

    def fail(reason, extra=None):
        info["detail"] = {"reason": reason, **(extra or {})}
        return False

    try:
        shutil.copytree(pkg_dir, staging_pkg)
        removed_garbage = _clean_garbage(staging_pkg)
        # 1) 包内 TTF 必须与 --font 一致（再次在 staging 上复核，防 copy 期间换包）
        ttf_rel = "KangXiKai-Regular-v%s.ttf" % v
        staging_ttf = os.path.join(staging_pkg, ttf_rel)
        if not os.path.exists(staging_ttf):
            pkgs = [f for f in os.listdir(staging_pkg) if f.lower().endswith(".ttf")]
            staging_ttf = os.path.join(staging_pkg, pkgs[0]) if pkgs else None
        src_sha = sha256_file(_abs(args.font))
        pkg_sha = sha256_file(staging_ttf) if staging_ttf else None
        font_ok = bool(pkg_sha and pkg_sha == src_sha)
        local_steps.append({"step": "pkg_font_sha", "ok": font_ok,
                            "detail": {"font_sha": src_sha,
                                       "pkg_font": os.path.basename(staging_ttf) if staging_ttf else None,
                                       "pkg_font_sha": pkg_sha}})
        if not font_ok:
            return fail("包内字体与 --font 不一致（换包）"), local_steps, info

        # 2) 包内扫描证据必须与 gate-report 记录的产物 sha 一致（DATA-403 防 finalize 后重写）
        pkg_artifacts = {}
        for kind, rec in (scan_artifacts or {}).items():
            if not rec or not rec.get("sha256"):
                continue
            base = os.path.basename(rec.get("path") or "")
            cand = os.path.join(staging_pkg, base)
            if not os.path.exists(cand):
                pkg_artifacts[kind] = {"path": base, "present": False,
                                       "reason": "包内缺扫描产物（应随包发布）"}
                continue
            got = sha256_file(cand)
            pkg_artifacts[kind] = {"path": base, "present": True, "sha256": got,
                                   "gate_report_sha256": rec.get("sha256"),
                                   "match": got == rec.get("sha256")}
        if any(not x.get("present") or not x.get("match") for x in pkg_artifacts.values()):
            local_steps.append({"step": "pkg_scan_artifacts", "ok": False,
                                "detail": pkg_artifacts})
            return fail("包内扫描证据与 gate-report 记录的产物 sha 不一致（证据被改写？）"), local_steps, info
        if pkg_artifacts:
            local_steps.append({"step": "pkg_scan_artifacts", "ok": True, "detail": pkg_artifacts})

        # 3) 终版 gate-report 写入 staging（不含自指的 sha/zip 终验；终验在 detached FINALIZE）
        gate_report = {
            "version": v,
            "gate": "release_gate",
            "pass": all(s["ok"] for s in local_steps),
            "inputs": inputs,
            "steps": local_steps,
            "scan_artifacts": scan_artifacts or {},
            "attestation": {
                "finalized": True,
                "finalize_version": FINALIZE_VERSION,
                "note": ("gate-report 于 finalize 时写定并被 SHA256SUMS 覆盖；"
                         "sha_final_ok/zip_ok/zip sha 记录在 FINALIZE.json 与包外 detached "
                         "<pkg>.FINALIZE.json（自指不可内嵌）"),
                "sha_algorithm": "sha256",
            },
        }
        gate_report_path = os.path.join(staging_pkg, f"gate-report-{tag}.json")
        with open(gate_report_path, "w", encoding="utf-8") as fo:
            json.dump(gate_report, fo, ensure_ascii=False, indent=1)
        gate_report_sha = sha256_file(gate_report_path)

        # 4) 包内 FINALIZE.json（自指字段置 null + 说明；实际终验见 detached）
        payload_sha, payload_rows = _payload_manifest_sha(staging_pkg)
        scan_final = {}
        for kind, rec in (scan_artifacts or {}).items():
            if not rec:
                continue
            base = os.path.basename(rec.get("path") or "")
            pkgp = os.path.join(staging_pkg, base)
            scan_final[kind] = {
                "path": base,
                "sha256": sha256_file(pkgp) if os.path.exists(pkgp) else None,
                "rows": rec.get("rows"), "flagged": rec.get("flagged"),
                "error_rows": rec.get("error_rows"), "created_utc": rec.get("created_utc"),
                "git": rec.get("git"),
                "sidecar": {"path": base + ".sha256",
                            "sha256": (sha256_file(os.path.join(staging_pkg, base + ".sha256"))
                                       if os.path.exists(os.path.join(staging_pkg, base + ".sha256")) else None)},
                "sidecar_validated": bool(rec.get("ok")),
            }
        finalize_rec = {
            "finalize_version": FINALIZE_VERSION,
            "version": v,
            "created_utc": utc_now(),
            "git": GB.git_state(),
            "font_sha256": pkg_sha,
            "gate_report_sha256": gate_report_sha,
            # 自指字段：包内为 null；包外 detached finalize 记录实际值（见 record_scope）
            "sha_final_ok": None,
            "zip_ok": None,
            "zip_sha256": None,
            "record_scope": "in-package",
            "zip_sha256_scope": ("自指不可内嵌：实际 zip sha256 与 sha_final_ok/zip_ok "
                                 "记录在包外 <pkg>.FINALIZE.json 与 <pkg>.zip.sha256"),
            "zip_payload_sha256": payload_sha,
            "scan_artifacts": scan_final,
            "garbage_removed": removed_garbage,
        }
        finalize_json_path = os.path.join(staging_pkg, "FINALIZE.json")
        with open(finalize_json_path, "w", encoding="utf-8") as fo:
            json.dump(finalize_rec, fo, ensure_ascii=False, indent=1)
        finalize_json_sha = sha256_file(finalize_json_path)

        # 5) SHA256SUMS（必须覆盖 FINALIZE.json / gate-report；最后写）
        sums = _write_sha256sums(staging_pkg)
        sha_ok, sha_bad = _verify_sha256sums(staging_pkg)
        if inject_fail == "sha":
            sha_ok, sha_bad = False, ["inject-fail=sha"]
        local_steps.append({"step": "sha256", "ok": sha_ok,
                            "detail": {"files": len(sums), "bad": sha_bad[:5],
                                       "covers_gate_report": True,
                                       "covers_finalize": True}})
        if not sha_ok:
            return fail("终版 SHA256SUMS 校验失败"), local_steps, info

        # 6) 确定性 zip + 目录/zip 逐文件一致
        _build_zip(staging_pkg, staging_zip)
        zip_ok, zip_bad = _verify_zip_matches_dir(staging_pkg, staging_zip)
        if inject_fail == "zip":
            zip_ok, zip_bad = False, ["inject-fail=zip"]
        zip_sha = sha256_file(staging_zip) if os.path.exists(staging_zip) else None
        local_steps.append({"step": "zip_selfcheck", "ok": zip_ok,
                            "detail": {"zip": os.path.basename(staging_zip),
                                       "zip_sha256": zip_sha, "bad": zip_bad[:5],
                                       "method": "dir==zip 逐文件 + 确定性时间戳"}})
        if not zip_ok:
            return fail("zip 自检失败（目录/zip 不一致）"), local_steps, info

        # 7) 终版文档对账（完整模式：gate-report/FINALIZE 必须存在）
        r = subprocess.run([sys.executable, "scripts/check_release_docs.py",
                            "--dir", staging_pkg, "--version", v],
                           cwd=ROOT, capture_output=True, text=True)
        local_steps.append({"step": "doc_check_final", "ok": r.returncode == 0,
                            "detail": {"tail": (r.stdout or r.stderr or "")[-800:]}})
        if r.returncode != 0:
            return fail("终版文档对账失败"), local_steps, info

        # 8) 独立 verifier（必须存在；缺失 = fail-closed，不允许静默跳过）
        verify_script = os.path.join(ROOT, "scripts", "verify_release.py")
        if not os.path.exists(verify_script):
            local_steps.append({"step": "verify_release", "ok": False,
                                "detail": {"error": "verify_release.py 缺失（fail-closed）"}})
            return fail("verify_release.py 缺失"), local_steps, info
        vr = subprocess.run([sys.executable, verify_script, "--dir", staging_pkg,
                             "--zip", staging_zip, "--json-out",
                             os.path.join(staging_root, "verify.json")],
                            cwd=ROOT, capture_output=True, text=True)
        local_steps.append({"step": "verify_release", "ok": vr.returncode == 0,
                            "detail": {"tail": (vr.stdout or vr.stderr or "")[-800:]}})
        if vr.returncode != 0:
            return fail("verify_release 终验失败"), local_steps, info
        if inject_fail == "pre-swap":
            return fail("inject-fail=pre-swap（模拟 finalize 后段失败）"), local_steps, info

        # 9) 原子替换：失败零写包；先备份原包/原 zip，全部成功后才删备份
        if os.path.exists(pkg_dir):
            backup_pkg = pkg_dir + f".bak-{os.getpid()}"
            os.replace(pkg_dir, backup_pkg)
        if os.path.exists(zip_path):
            backup_zip = zip_path + f".bak-{os.getpid()}"
            os.replace(zip_path, backup_zip)
        try:
            os.replace(staging_pkg, pkg_dir)
            os.replace(staging_zip, zip_path)
            # 替换后只读复验（不改包）
            sha_ok2, sha_bad2 = _verify_sha256sums(pkg_dir)
            zip_ok2, zip_bad2 = _verify_zip_matches_dir(pkg_dir, zip_path)
            zip_sha2 = sha256_file(zip_path)
            final_ok = sha_ok2 and zip_ok2 and zip_sha2 == zip_sha
            if not final_ok:
                raise RuntimeError(f"替换后复验失败: sha={sha_bad2[:3]} zip={zip_bad2[:3]}")
        except Exception as e:
            # 回滚：恢复备份，删除半成品
            try:
                if os.path.exists(pkg_dir):
                    shutil.rmtree(pkg_dir)
                if backup_pkg and os.path.exists(backup_pkg):
                    os.replace(backup_pkg, pkg_dir)
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                if backup_zip and os.path.exists(backup_zip):
                    os.replace(backup_zip, zip_path)
            except Exception as e2:
                return fail(f"原子替换失败且回滚异常: {e} / {e2}"), local_steps, info
            return fail(f"原子替换后复验失败（已回滚）: {e}"), local_steps, info

        # 10) 包外 detached 终验记录（实际 zip sha / sha_final_ok / zip_ok）
        detached_path = os.path.join(os.path.dirname(zip_path),
                                     os.path.basename(zip_path)[:-4] + ".FINALIZE.json")
        detached = dict(finalize_rec)
        detached.update({
            "record_scope": "detached-authoritative",
            "sha_final_ok": True,
            "zip_ok": True,
            "zip_sha256": zip_sha2,
            "zip_sha256_scope": "实际分发 zip 的 sha256（包含包内 FINALIZE.json）",
            "package_finalize_sha256": finalize_json_sha,
            "gate_report_sha256": gate_report_sha,
            "font_sha256": pkg_sha,
            "sha_covers": len(sums),
            "sha_files": [rel for _h, rel in sums],
            "zip": _rel(zip_path),
            "package": _rel(pkg_dir),
            "verified_after_swap": True,
        })
        with open(detached_path, "w", encoding="utf-8") as fo:
            json.dump(detached, fo, ensure_ascii=False, indent=1)
        zip_sums_path = zip_path + ".sha256"
        with open(zip_sums_path, "w", encoding="utf-8") as fo:
            fo.write(f"{zip_sha2}  {os.path.basename(zip_path)}\n")
        # 清理备份 + staging
        for b in (backup_pkg, backup_zip):
            if b and os.path.exists(b):
                if os.path.isdir(b):
                    shutil.rmtree(b)
                else:
                    os.remove(b)
        info["detail"] = {
            "package": _rel(pkg_dir), "zip": _rel(zip_path),
            "zip_sha256": zip_sha2, "sha_covers": len(sums),
            "gate_report_sha256": gate_report_sha,
            "finalize_json_sha256": finalize_json_sha,
            "detached_finalize": _rel(detached_path),
            "zip_sha256_file": _rel(zip_sums_path),
            "garbage_removed": removed_garbage,
            "sha_final_ok": sha_ok2, "zip_ok": zip_ok2,
        }
        return True, local_steps, info
    except Exception as e:
        # 若已替换但尚未完成 detached 记录/清理，回滚到备份（失败零写包的兜底）
        try:
            if backup_pkg and os.path.exists(backup_pkg):
                if os.path.isdir(pkg_dir):
                    shutil.rmtree(pkg_dir)
                os.replace(backup_pkg, pkg_dir)
            if backup_zip and os.path.exists(backup_zip):
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                os.replace(backup_zip, zip_path)
        except Exception:
            pass
        return fail(f"finalize 异常: {str(e)[:300]}"), local_steps, info
    finally:
        if os.path.isdir(staging_root):
            shutil.rmtree(staging_root, ignore_errors=True)


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
                    help="复用已有缺件扫描 jsonl（不重跑；复用前必须校验 sidecar 输入绑定）")
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
                    help="首跑模式：doc_check 允许 gate-report/FINALIZE 暂缺（finalize 会生成）")
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
    ap.add_argument("--inject-fail", default=None,
                    choices=["none", "sha", "zip", "pre-swap"],
                    help="仅失败注入自测：sha/zip/pre-swap 在 finalize 内部模拟失败，验证「零写包」")
    args = ap.parse_args()
    inject_fail = args.inject_fail if args.inject_fail not in (None, "none") else None
    v = args.version
    tag = args.tag or ("v" + v.replace(".", ""))
    stats_path = args.stats or (os.path.splitext(args.font)[0] + ".build_stats.json")
    steps = []
    scan_artifacts = {}
    unsafe = []
    if args.allow_dirty:
        unsafe.append("allow_dirty")
    if args.allow_missing_scans:
        unsafe.append("allow_missing_scans")
    if args.allow_missing_attestation:
        unsafe.append("allow_missing_attestation")
    if inject_fail:
        unsafe.append(f"inject_fail:{inject_fail}")
    inputs = GB.build_binding(
        files={"font": args.font, "manifest": args.manifest, "prev_font": args.prev,
               "prev_manifest": args.prev_manifest, "mapping": args.mapping,
               "geometry": args.geometry, "build_stats": stats_path,
               "page_line_bands": "work/lead/page_line_bands.json"},
        scripts=["release_gate.py", "font_qa.py", "content_loss_gate.py",
                 "glyph_frame_gate.py", "provenance_gate.py", "page_geometry_gate.py",
                 "check_release_docs.py", "verify_release.py",
                 "scan_missing_parts.py", "scan_frame_escape.py"],
        include_reffont=True)
    inputs["stats"] = stats_path

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
    quarantine, qfiles = set(), []
    cands = [args.quarantine] if args.quarantine else []
    import glob as _glob
    # P1-2：只认当前版 residual，不并集历史版本；历史隔离字必须显式 --quarantine
    _tag = "v" + str(args.version).replace(".", "")
    cands += sorted(_glob.glob(os.path.join(ROOT, "work", "lead", f"{_tag}*_residual.json")))
    for cand in cands:
        p = cand if os.path.isabs(cand) else os.path.join(ROOT, cand)
        if os.path.exists(p):
            try:
                quarantine |= set(json.load(open(p))["chars"])
                qfiles.append(os.path.relpath(p, ROOT))
            except Exception:
                pass
    if not (args.prev_manifest and os.path.exists(os.path.join(ROOT, args.prev_manifest))):
        steps.append({"step": "char_diff", "ok": False,
                      "detail": {"error": "缺 --prev-manifest，字符集差集无法校验（不允许空转）"}})
    else:
        undeclared = [c for c in removed if c not in quarantine]
        steps.append({"step": "char_diff", "ok": not undeclared,
                      "detail": {"removed": removed, "added": added,
                                 "undeclared_removed": undeclared,
                                 "quarantine_files": qfiles, "quarantine_n": len(quarantine)}})

    # 4) 内容缺失闸（v2.6.4 契约：baseline∩new 交集；新增/删除字单列；失败产物不可复用）
    if args.prev:
        fresh_json = os.path.join("work", "lead", f"content-loss-gate-{tag}.json")
        out_json = fresh_json
        r = None
        reuse_ok = None
        if not args.prev_manifest or not os.path.exists(os.path.join(ROOT, args.prev_manifest)):
            steps.append({"step": "content_loss_gate", "ok": False,
                          "detail": {"error": "缺 --prev-manifest，content 宇宙无法确定"}})
        else:
            if args.reuse_content:
                vres = GB.validate_reuse(args.reuse_content,
                                         files={"font": args.font, "baseline": args.prev,
                                                "manifest": args.prev_manifest},
                                         scripts=["content_loss_gate.py", "fidelity_eval.py"],
                                         require_out_sha=True)
                reuse_ok = vres["ok"]
                steps.append({"step": "content_reuse_binding", "ok": reuse_ok,
                              "detail": {"file": args.reuse_content, **vres}})
                if reuse_ok:
                    out_json = args.reuse_content
                    r = subprocess.CompletedProcess(args=[], returncode=0, stdout="reused")
            if r is None:
                _env = dict(os.environ)
                _env["CONTENT_LOSS_MAX_DAMAGED"] = str(args.content_max_damaged)
                r = subprocess.run([sys.executable, "scripts/content_loss_gate.py",
                                    args.prev, args.font, args.prev_manifest, out_json],
                                   cwd=ROOT, capture_output=True, text=True, env=_env)
            summary = None
            try:
                obj = json.load(open(os.path.join(ROOT, out_json), encoding="utf-8"))
                if isinstance(obj, dict) and obj.get("contract_version") == 1:
                    summary = obj
            except Exception:
                summary = None
            damaged = len(summary["damaged"]) if summary and isinstance(
                summary.get("damaged"), list) else None
            n_expected = (summary or {}).get("n_expected")
            n_ok = (summary or {}).get("n_ok")
            n_error = (summary or {}).get("n_error")
            coverage_ok = (isinstance(n_expected, int) and isinstance(n_ok, int)
                           and isinstance(n_error, int) and n_expected == n_ok
                           and n_error == 0)
            mode = "threshold" if args.content_max_damaged > 0 else "strict(0)"
            zero_margin = (args.content_max_damaged > 0 and damaged is not None
                           and damaged == args.content_max_damaged)
            ok_content = (summary is not None and coverage_ok
                          and bool(summary.get("gate_pass"))
                          and isinstance(damaged, int)
                          and damaged <= args.content_max_damaged
                          and r.returncode in (0, 3))
            steps.append({"step": "content_loss_gate", "ok": ok_content,
                          "detail": {"contract_version": (summary or {}).get("contract_version"),
                                     "returncode": r.returncode,
                                     "damaged": damaged,
                                     "n_expected": n_expected, "n_ok": n_ok,
                                     "n_error": n_error,
                                     "added_skipped": len((summary or {}).get("added_chars") or []),
                                     "removed_skipped": len((summary or {}).get("removed_chars") or []),
                                     "universe_manifest": (summary or {}).get("universe_manifest"),
                                     "universe_manifest_sha256": (summary or {}).get(
                                         "universe_manifest_sha256"),
                                     "mode": mode, "reused": bool(reuse_ok),
                                     "threshold": args.content_max_damaged,
                                     "zero_margin": zero_margin,
                                     "threshold_note": ("阈值=观测值，无余量" if zero_margin else ""),
                                     "tail": (r.stdout or "")[-300:]}})

    # 4b) 全库缺件扫描（--reuse-missing 本身也触发该闸；GATE-402）
    if args.scan or args.reuse_missing:
        out_scan = args.reuse_missing or os.path.join("work", "lead", f"missing_scan_gate_{tag}.jsonl")
        r = None
        reuse_ok = None
        if args.reuse_missing:
            rec = validate_scan_artifact(
                args.reuse_missing,
                {"font": args.font, "manifest": args.manifest, "geometry": args.geometry,
                 "page_line_bands": "work/lead/page_line_bands.json", "build_stats": stats_path},
                ["scan_missing_parts.py", "precut_masks.py", "reffont.py", "font_build.py",
                 "font_norm.py", "page_frames.py", "fidelity_eval.py"],
                include_reffont=True)
            reuse_ok = rec["ok"]
            scan_artifacts["missing"] = rec
            steps.append({"step": "missing_reuse_binding", "ok": reuse_ok,
                          "detail": {"file": args.reuse_missing, "artifact": rec}})
            if reuse_ok:
                r = subprocess.CompletedProcess(args=[], returncode=0, stdout="reused")
        if r is None:
            r = subprocess.run([sys.executable, "scripts/scan_missing_parts.py", args.font,
                                args.manifest, out_scan, stats_path],
                               cwd=ROOT, capture_output=True, text=True)
            rec = validate_scan_artifact(
                out_scan,
                {"font": args.font, "manifest": args.manifest, "geometry": args.geometry,
                 "page_line_bands": "work/lead/page_line_bands.json", "build_stats": stats_path},
                ["scan_missing_parts.py", "precut_masks.py", "reffont.py", "font_build.py",
                 "font_norm.py", "page_frames.py", "fidelity_eval.py"],
                include_reffont=True)
            scan_artifacts["missing"] = rec
        flagged = n_error = None
        try:
            rows = [json.loads(ln) for ln in open(os.path.join(ROOT, out_scan)) if ln.strip()]
            n_error = sum(1 for x in rows if x.get("error"))
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
        art_ok = bool((scan_artifacts.get("missing") or {}).get("ok"))
        steps.append({"step": "scan_missing_parts", "ok": ok_scan and art_ok,
                      "detail": {"returncode": r.returncode, "flagged": flagged,
                                 "error_rows": n_error, "mode": mode, "reused": bool(reuse_ok),
                                 "zero_margin": zero_margin,
                                 "artifact": scan_artifacts.get("missing"),
                                 "tail": (r.stdout or "")[-200:]}})
    # 4c) 框线逃逸闸（切前排除后块内不应再有贯穿框线）
    if args.frame_scan or args.reuse_frame:
        out_frame = args.reuse_frame or os.path.join("work", "lead", f"frame_escape_scan_{tag}.jsonl")
        r = None
        reuse_ok = None
        if args.reuse_frame:
            rec = validate_scan_artifact(
                args.reuse_frame,
                {"manifest": args.manifest, "geometry": args.geometry,
                 "page_line_bands": "work/lead/page_line_bands.json"},
                ["scan_frame_escape.py", "precut_masks.py", "font_build.py",
                 "font_norm.py", "page_frames.py", "detect_blocks.py"])
            reuse_ok = rec["ok"]
            scan_artifacts["frame"] = rec
            steps.append({"step": "frame_reuse_binding", "ok": reuse_ok,
                          "detail": {"file": args.reuse_frame, "artifact": rec}})
            if reuse_ok:
                r = subprocess.CompletedProcess(args=[], returncode=0, stdout="reused")
        if r is None:
            r = subprocess.run([sys.executable, "scripts/scan_frame_escape.py",
                                "--manifest", args.manifest, "--out", out_frame],
                               cwd=ROOT, capture_output=True, text=True)
            rec = validate_scan_artifact(
                out_frame,
                {"manifest": args.manifest, "geometry": args.geometry,
                 "page_line_bands": "work/lead/page_line_bands.json"},
                ["scan_frame_escape.py", "precut_masks.py", "font_build.py",
                 "font_norm.py", "page_frames.py", "detect_blocks.py"])
            scan_artifacts["frame"] = rec
        flagged = n_error = None
        try:
            rows = [json.loads(ln) for ln in open(os.path.join(ROOT, out_frame)) if ln.strip()]
            n_error = sum(1 for x in rows if x.get("error"))
            flagged = len(rows)  # 所有行都是 flagged；error 行同样计入（fail-closed）
        except Exception:
            pass
        zero_margin = (flagged is not None and flagged == args.frame_max_flagged)
        ok_frame = (r.returncode == 0 and flagged is not None
                    and flagged <= args.frame_max_flagged)
        art_ok = bool((scan_artifacts.get("frame") or {}).get("ok"))
        steps.append({"step": "frame_escape", "ok": ok_frame and art_ok,
                      "detail": {"flagged": flagged, "error_rows": n_error,
                                 "reused": bool(reuse_ok),
                                 "threshold": args.frame_max_flagged,
                                 "zero_margin": zero_margin,
                                 "artifact": scan_artifacts.get("frame"),
                                 "mode": "strict" if args.frame_max_flagged == 0 else "threshold"}})
    if scan_artifacts:
        # T4 item3：扫描产物绑定独立成步（sha256/created_utc/sidecar 校验结果）
        binder_ok = all((r or {}).get("ok") for r in scan_artifacts.values())
        steps.append({"step": "scan_artifact_binding", "ok": binder_ok,
                      "detail": {k: {"path": (r or {}).get("path"),
                                     "sha256": (r or {}).get("sha256"),
                                     "rows": (r or {}).get("rows"),
                                     "created_utc": (r or {}).get("created_utc"),
                                     "git": (r or {}).get("git"),
                                     "sidecar_sha256": ((r or {}).get("sidecar") or {}).get("sha256"),
                                     "ok": (r or {}).get("ok"),
                                     "reason": (r or {}).get("reason")}
                                 for k, r in scan_artifacts.items()}})
    # 4d) 三闸（BF-01）：字形级框线 / 无拷贝 provenance / 页级几何（全部严格 0）
    out_gf = os.path.join("work", "lead", f"glyph-frame-gate-{tag}.json")
    r = subprocess.run([sys.executable, "scripts/glyph_frame_gate.py", "--font", args.font,
                        "--manifest", args.manifest, "--out", out_gf,
                        "--max-flagged", str(args.frame_max_flagged)],
                       cwd=ROOT, capture_output=True, text=True)
    try:
        gfr = json.load(open(os.path.join(ROOT, out_gf)))
        gf_flagged = len(gfr.get("flagged") or [])
        gf_font_sha = gfr.get("font_sha256")
    except Exception:
        gf_flagged = None
        gf_font_sha = None
    steps.append({"step": "glyph_frame_gate",
                  "ok": (r.returncode == 0 and gf_flagged is not None
                         and gf_flagged <= args.frame_max_flagged
                         and (gf_font_sha is None or gf_font_sha == sha256_file(os.path.join(ROOT, args.font)))),
                  "detail": {"returncode": r.returncode, "flagged": gf_flagged,
                             "font_sha256": gf_font_sha,
                             "threshold": args.frame_max_flagged, "out": out_gf,
                             "tail": (r.stdout or "")[-200:]}})
    out_prov = os.path.join("work", "lead", f"provenance-gate-{tag}.json")
    r = subprocess.run([sys.executable, "scripts/provenance_gate.py",
                        "--manifest", args.manifest, "--mapping", args.mapping,
                        "--stats", stats_path, "--out", out_prov],
                       cwd=ROOT, capture_output=True, text=True)
    steps.append({"step": "provenance_gate", "ok": r.returncode == 0,
                  "detail": {"returncode": r.returncode, "out": out_prov,
                             "stats": stats_path, "tail": (r.stdout or "")[-300:]}})
    out_pg = os.path.join("work", "lead", f"page-geometry-gate-{tag}.json")
    r = subprocess.run([sys.executable, "scripts/page_geometry_gate.py",
                        "--manifest", args.manifest, "--mapping", args.mapping,
                        "--geometry", args.geometry, "--out", out_pg,
                        "--max-bad-boxes", str(args.page_geometry_max_bad_boxes),
                        "--max-missing-quad-chars", "0",
                        "--max-empty-assign-halves", str(args.page_geometry_max_empty_assign)],
                       cwd=ROOT, capture_output=True, text=True)
    pg_counts, pg_thr = {}, {}
    try:
        pgr = json.load(open(os.path.join(ROOT, out_pg)))
        pg_counts = pgr.get("counts") or {}
        pg_thr = pgr.get("thresholds") or {}
    except Exception:
        pass
    steps.append({"step": "page_geometry_gate", "ok": r.returncode == 0,
                  "detail": {"returncode": r.returncode, "out": out_pg,
                             "counts": pg_counts, "thresholds": pg_thr,
                             "tail": (r.stdout or "")[-300:]}})

    # 4e) finalize 前置条件（正式包不允许跳过；--allow-* 仅调试且写进报告）
    pkg_dir_abs = _abs(args.pkg_dir).rstrip(os.sep) if args.pkg_dir else None
    pkg_ttf = pkg_sha = None
    if pkg_dir_abs:
        if not os.path.isdir(pkg_dir_abs):
            steps.append({"step": "pkg_dir", "ok": False,
                          "detail": {"error": f"包目录不存在: {args.pkg_dir}"}})
        else:
            steps.append({"step": "pkg_dir", "ok": True, "detail": {"pkg_dir": _rel(pkg_dir_abs)}})
            ttfs = [f for f in os.listdir(pkg_dir_abs) if f.lower().endswith(".ttf")]
            pkg_ttf = os.path.join(pkg_dir_abs, ttfs[0]) if ttfs else None
            pkg_sha = sha256_file(pkg_ttf) if pkg_ttf else None
            src_sha = sha256_file(os.path.join(ROOT, args.font))
            steps.append({"step": "pkg_font_sha",
                          "ok": bool(pkg_sha and pkg_sha == src_sha),
                          "detail": {"pkg_font": os.path.basename(pkg_ttf) if pkg_ttf else None,
                                     "pkg_font_sha": pkg_sha, "font_sha": src_sha,
                                     "note": "换包即 FAIL；finalize 会再次在 staging 复核"}})
    if args.pkg_dir and not args.no_finalize:
        missing_scans = (not scan_artifacts.get("missing") or not scan_artifacts.get("frame"))
        steps.append({"step": "scans_required",
                      "ok": (not missing_scans) or args.allow_missing_scans,
                      "detail": {"scan_artifacts": {k: bool(v) for k, v in scan_artifacts.items()},
                                 "allow_missing_scans": args.allow_missing_scans,
                                 "note": "正式包必须提供缺件+框线扫描（BF-10）；reuse 也必须带有效 sidecar"}})
        steps.append({"step": "content_baseline_required",
                      "ok": bool(args.prev) or args.allow_missing_scans,
                      "detail": {"prev": args.prev,
                                 "note": "正式包必须有内容闸基线（BF-10）"}})
        git = inputs.get("git") or {}
        steps.append({"step": "clean_tree",
                      "ok": (git.get("dirty") is False) or args.allow_dirty,
                      "detail": {"git": git, "allow_dirty": args.allow_dirty,
                                 "note": "正式包必须来自 clean git tree（AGENTS §1）"}})

    # 5) 文档校验（pre-finalize：gate-report/FINALIZE 由 finalize 生成，允许暂缺）
    if args.pkg_dir:
        cmd = [sys.executable, "scripts/check_release_docs.py",
               "--dir", args.pkg_dir, "--version", v]
        # finalize 会生成 gate-report/FINALIZE.json：pre-finalize 首跑必须允许这两项暂缺，
        # 否则正式 finalize 永远过不了 doc_check；终版对账由 finalize 内 doc_check_final 强制执行。
        if args.allow_missing_attestation or not args.no_finalize:
            cmd.append("--allow-missing-attestation")
        steps.append(run(cmd, "doc_check"))
    ok = all(s["ok"] for s in steps)
    report = {"version": v, "pass": ok, "inputs": inputs, "steps": steps,
              "scan_artifacts": scan_artifacts, "unsafe_bypasses": unsafe,
              "attestation": {"finalized": False,
                              "note": "gate-report 计入 SHA256SUMS；通过 shasum -a 256 -c 验证本文件"}}
    out = args.out or os.path.join(ROOT, "work", "lead", f"gate-report-{tag}.json")
    pkg_report = None
    if args.pkg_dir and not args.no_finalize and not ok:
        # 审计 GATE-08/LEAD4-002：失败时绝不改动包（不写包内报告/SHA/zip），只在 work/lead 留失败报告
        report["attestation"] = {"finalized": False, "package_touched": False,
                                 "reason": "pre-finalize steps failed"}
        with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
            json.dump(report, fo, ensure_ascii=False, indent=1)
        for st in steps:
            print(("PASS " if st["ok"] else "FAIL ") + st["step"])
        print(json.dumps({"pass": False, "report": out, "package_touched": False},
                         ensure_ascii=False))
        return 1
    # 6) finalize（原子：staging → 全验 → 替换；失败零写包）
    if args.pkg_dir and not args.no_finalize:
        ok_fin, fin_steps, fin_info = finalize_package(
            args, v, tag, steps, inputs, scan_artifacts, out, inject_fail=inject_fail)
        report = {"version": v, "pass": ok_fin, "inputs": inputs, "steps": fin_steps,
                  "scan_artifacts": scan_artifacts, "unsafe_bypasses": unsafe,
                  "finalize": fin_info.get("detail"),
                  "attestation": {"finalized": bool(ok_fin),
                                  "package_touched": bool(ok_fin),
                                  "sha_final_ok": (fin_info.get("detail") or {}).get("sha_final_ok"),
                                  "zip_ok": (fin_info.get("detail") or {}).get("zip_ok"),
                                  "zip_sha256": (fin_info.get("detail") or {}).get("zip_sha256")}}
        with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
            json.dump(report, fo, ensure_ascii=False, indent=1)
        for st in fin_steps:
            print(("PASS " if st["ok"] else "FAIL ") + st["step"])
        print(json.dumps({"pass": ok_fin, "report": out,
                          "package_touched": bool(ok_fin),
                          **(fin_info.get("detail") or {})}, ensure_ascii=False))
        return 0 if ok_fin else 1
    # 非 finalize 模式：只写 work/lead 报告
    with open(os.path.join(ROOT, out), "w", encoding="utf-8") as fo:
        json.dump(report, fo, ensure_ascii=False, indent=1)
    for st in steps:
        print(("PASS " if st["ok"] else "FAIL ") + st["step"])
    print(json.dumps({"pass": report["pass"], "report": out,
                      "pkg_report": pkg_report}, ensure_ascii=False))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
