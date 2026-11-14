#!/usr/bin/env python3
"""T4 证据链检查器自测（篡改测试）：check_release_docs / verify_release 必须能抓住改坏的数字与 sha。

做法：把 v2.6.2 正式包复制到 /tmp，补上 v2.6.3 起要求的证据文件（build_stats / 缺件+框线扫描
jsonl+sidecar / FINALIZE.json / 根 OFL/LICENSE 单源），重算 SHA256SUMS 得到一个「现代包」fixture；
基线必须 PASS，随后逐项篡改（QA 内容闸数字、KNOWN-DEBTS 缺件数、gate-report 数字、FINALIZE sha、
OFL 文本）每次都必须 FAIL。不触碰 release/（只读复制）。

用法: .venv/bin/python scripts/oneoff/test_release_evidence.py
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
SRC = os.path.join(ROOT, "release", "KangXiKai-v2.6.2")
V = "2.6.2"
TAG = "v262"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy(pkg, rel_pairs):
    for src, dst in rel_pairs:
        s = src if os.path.isabs(src) else os.path.join(ROOT, src)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(pkg, dst))
            return True
    return False


def rewrite_sha(pkg):
    rows = []
    for root, dirs, fs in os.walk(pkg):
        dirs.sort()
        for f in sorted(fs):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, pkg).replace(os.sep, "/")
            if rel == "SHA256SUMS":
                continue
            rows.append((sha256(p), rel))
    with open(os.path.join(pkg, "SHA256SUMS"), "w", encoding="utf-8") as fo:
        for h, rel in rows:
            fo.write(f"{h}  {rel}\n")


def payload_sha(pkg):
    rows = []
    for root, dirs, fs in os.walk(pkg):
        dirs.sort()
        for f in sorted(fs):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, pkg).replace(os.sep, "/")
            if rel in ("FINALIZE.json", "SHA256SUMS"):
                continue
            rows.append((rel, sha256(p)))
    rows.sort()
    return hashlib.sha256(("\n".join(f"{h}  {rel}" for rel, h in rows) + "\n").encode("utf-8")).hexdigest()


def build_fixture(tmp):
    pkg = os.path.join(tmp, "KangXiKai-v2.6.2")
    shutil.copytree(SRC, pkg)
    # 1) OFL/LICENSE 单一真源
    for name in ("OFL.txt", "LICENSE"):
        shutil.copy2(os.path.join(ROOT, name), os.path.join(pkg, name))
    # 2) build_stats
    shutil.copy2(os.path.join(ROOT, "work/font/build/KangXiKai-v2.6.2.build_stats.json"),
                 os.path.join(pkg, "KangXiKai-v2.6.2.build_stats.json"))
    # 3) 扫描证据 + sidecar
    for src, dst in (("work/lead/missing_scan_v262.jsonl", "missing_scan_v262.jsonl"),
                     ("work/lead/frame_scan_v262.jsonl", "frame_scan_v262.jsonl")):
        shutil.copy2(os.path.join(ROOT, src), os.path.join(pkg, dst))
        shutil.copy2(os.path.join(ROOT, src + ".sha256"), os.path.join(pkg, dst + ".sha256"))
    # 4) gate-report 注入 scan_artifacts（模拟 T4 起的新 gate-report 字段）
    gr_path = os.path.join(pkg, f"gate-report-{TAG}.json")
    gr = json.load(open(gr_path, encoding="utf-8"))
    scan = {}
    for kind, base in (("missing", "missing_scan_v262.jsonl"), ("frame", "frame_scan_v262.jsonl")):
        sp = os.path.join(pkg, base)
        side = sp + ".sha256"
        sc = json.load(open(side))
        rows = [json.loads(ln) for ln in open(sp, encoding="utf-8") if ln.strip()]
        scan[kind] = {"path": base, "sha256": sha256(sp), "bytes": os.path.getsize(sp),
                      "rows": len(rows),
                      "flagged": sum(1 for r in rows if r.get("missing")),
                      "error_rows": sum(1 for r in rows if r.get("error")),
                      "created_utc": sc.get("created_utc"), "git": sc.get("git"),
                      "sidecar": {"path": base + ".sha256", "sha256": sha256(side),
                                  "exists": True},
                      "ok": True, "reason": ""}
    gr["scan_artifacts"] = scan
    json.dump(gr, open(gr_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 5) FINALIZE.json（包内自指字段 null）
    fin = {
        "finalize_version": 1, "version": V,
        "created_utc": "2026-11-14T00:00:00Z",
        "git": {"commit": "8622ba891a20c2f96fc7cfb3080a0f5eed2083aa", "dirty": False},
        "font_sha256": sha256(os.path.join(pkg, f"KangXiKai-Regular-v{V}.ttf")),
        "gate_report_sha256": sha256(gr_path),
        "sha_final_ok": None, "zip_ok": None, "zip_sha256": None,
        "zip_sha256_scope": "自指不可内嵌：实际 zip sha 由包外 detached 记录",
        "record_scope": "in-package",
        "zip_payload_sha256": payload_sha(pkg),
        "scan_artifacts": {kind: {"path": base,
                                  "sha256": sha256(os.path.join(pkg, base)),
                                  "sidecar": {"path": base + ".sha256",
                                              "sha256": sha256(os.path.join(pkg, base + ".sha256"))},
                                  "sidecar_validated": True}
                           for kind, base in (("missing", "missing_scan_v262.jsonl"),
                                              ("frame", "frame_scan_v262.jsonl"))},
    }
    json.dump(fin, open(os.path.join(pkg, "FINALIZE.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    rewrite_sha(pkg)
    return pkg


def run_doc(pkg, allow=False):
    cmd = [PY, "scripts/check_release_docs.py", "--dir", pkg, "--version", V]
    if allow:
        cmd.append("--allow-missing-attestation")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_verify(pkg):
    r = subprocess.run([PY, "scripts/verify_release.py", "--dir", pkg],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def tamper(path, old, new):
    txt = open(path, encoding="utf-8").read()
    assert old in txt, f"tamper anchor not found: {old!r} in {path}"
    open(path, "w", encoding="utf-8").write(txt.replace(old, new, 1))


def main():
    tmp = tempfile.mkdtemp(prefix="t4-evidence-")
    results = []
    try:
        pkg = build_fixture(tmp)
        rc, out = run_doc(pkg)
        results.append(("baseline_doc_check", rc == 0, out.strip().splitlines()[-1][:120]))
        rc2, out2 = run_verify(pkg)
        results.append(("baseline_verify", rc2 == 0, out2.strip().splitlines()[-1][:120]))
        # 篡改 1：QA 内容闸 18/35 → 999/35
        tamper(os.path.join(pkg, "QA.md"), "**18 / 35**", "**999 / 35**")
        rewrite_sha(pkg)
        rc, out = run_doc(pkg)
        results.append(("tamper_qa_content", rc != 0 and "内容闸" in out, out.strip().splitlines()[1][:120] if rc else ""))
        # 篡改 2：KNOWN-DEBTS 缺件 165 → 100
        tamper(os.path.join(pkg, "KNOWN-DEBTS.md"), "| 缺件扫描 | 165 |", "| 缺件扫描 | 100 |")
        rewrite_sha(pkg)
        rc, out = run_doc(pkg)
        results.append(("tamper_known_debts_missing", rc != 0 and "缺件扫描" in out,
                        [ln for ln in out.splitlines() if "缺件扫描" in ln][:1]))
        # 篡改 3：gate-report content damaged 18 → 0（QA 仍是 18）
        gr_path = os.path.join(pkg, f"gate-report-{TAG}.json")
        gr = json.load(open(gr_path, encoding="utf-8"))
        for s in gr["steps"]:
            if s["step"] == "content_loss_gate":
                s["detail"]["damaged"] = 0
        json.dump(gr, open(gr_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rewrite_sha(pkg)
        rc, out = run_doc(pkg)
        results.append(("tamper_gate_report_number", rc != 0 and "内容闸" in out,
                        [ln for ln in out.splitlines() if "内容闸" in ln][:1]))
        # 篡改 4：FINALIZE font sha 改坏
        fin_path = os.path.join(pkg, "FINALIZE.json")
        fin = json.load(open(fin_path, encoding="utf-8"))
        fin["font_sha256"] = "0" * 64
        json.dump(fin, open(fin_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rewrite_sha(pkg)
        rc, out = run_doc(pkg)
        results.append(("tamper_finalize_font_sha", rc != 0 and "font_sha256" in out,
                        [ln for ln in out.splitlines() if "font_sha256" in ln][:1]))
        # 篡改 5：OFL 文本 = 破坏单一真源
        tamper(os.path.join(pkg, "OFL.txt"), "SIL OPEN FONT LICENSE", "SIL OPEN FONT LICENCE")
        rewrite_sha(pkg)
        rc, out = run_doc(pkg)
        results.append(("tamper_ofl_single_source", rc != 0 and "single_source:OFL.txt" in out,
                        [ln for ln in out.splitlines() if "OFL" in ln][:1]))
        # 篡改 6：FINALIZE 删除 → verify 必须 FAIL
        os.remove(fin_path)
        rewrite_sha(pkg)
        rc, out = run_verify(pkg)
        results.append(("tamper_finalize_missing_verify", rc != 0 and "finalize_present" in out, ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(r[1] for r in results)
    print(json.dumps({"pass": ok,
                      "cases": [{"name": n, "ok": o, "evidence": e}
                                for n, o, e in results]},
                     ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
