#!/usr/bin/env python3
"""发布包独立验证器（v2.6.3 T4 item5；审计 LEAD4-004 / GATE-402 / DATA-403）。

只读校验，不改任何文件：
  1) 目录 == zip：逐文件（zip 内前缀 = 包目录名）文件名集合与字节 sha256 完全一致；
  2) SHA256SUMS 覆盖全部非 SHA256SUMS 文件、逐文件 sha 正确、无多余条目/未覆盖文件；
  3) 无多余文件（.DS_Store / ._* / *.tmp 等平台垃圾必须为 0）；
  4) FINALIZE.json 字段齐全；font_sha256 / gate_report_sha256 / scan_artifacts sha /
     zip_payload_sha256 与包内文件一致；包内自指字段（sha_final_ok/zip_ok/zip_sha256）必须为
     null 且有 scope 说明（自指不可内嵌）；若给 --finalize-json <包外 detached>：
     sha_final_ok/zip_ok 必须 true、zip_sha256 == 实际 zip sha256、package_finalize_sha256 一致；
  5) gate-report：pass true、attestation.finalized true。

输出 JSON；退出码 0=PASS。

用法:
  python scripts/verify_release.py --dir release/KangXiKai-v2.6.3 \
      --zip release/KangXiKai-v2.6.3.zip \
      --finalize-json release/KangXiKai-v2.6.3.FINALIZE.json
  仅校验目录包（无 zip）时省略 --zip（zip 相关检查记 SKIP）。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GARBAGE = re.compile(r"(^|/)(\.DS_Store|\._[^/]*|[^/]*\.tmp)$")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_files(d):
    out = {}
    for root, dirs, fs in os.walk(d):
        dirs.sort()
        for f in sorted(fs):
            p = os.path.join(root, f)
            out[os.path.relpath(p, d).replace(os.sep, "/")] = p
    return out


def verify(args):
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    d = os.path.abspath(args.dir)
    if not check("dir_exists", os.path.isdir(d), d):
        return [{"dir": d, "pass": False, "checks": checks, "files": 0}]
    dir_files = walk_files(d)
    pkg_name = os.path.basename(d.rstrip(os.sep))

    # 0) 平台垃圾
    garbage = sorted(f for f in dir_files if GARBAGE.search(f))
    check("no_garbage", not garbage, f"发现垃圾文件 {garbage[:8]}")

    # 1) SHA256SUMS
    sums_path = os.path.join(d, "SHA256SUMS")
    listed = {}
    if check("sha256sums_exists", os.path.exists(sums_path), sums_path):
        bad = []
        try:
            for ln in open(sums_path, encoding="utf-8"):
                ln = ln.rstrip("\n")
                if not ln:
                    continue
                h, rel = ln.split("  ", 1)
                if rel in listed:
                    bad.append(f"重复条目 {rel}")
                listed[rel] = h
        except Exception as e:
            bad.append(f"解析失败 {e}")
        non_sha = set(dir_files) - {"SHA256SUMS"}
        for rel, h in listed.items():
            p = os.path.join(d, rel)
            if not os.path.exists(p):
                bad.append(f"缺失 {rel}")
            elif sha256_file(p) != h:
                bad.append(f"sha 不符 {rel}")
        bad += [f"未覆盖 {rel}" for rel in sorted(non_sha - set(listed))]
        bad += [f"多余条目 {rel}" for rel in sorted(set(listed) - non_sha)]
        check("sha256sums_covers_all", not bad, "; ".join(bad[:10]))

    # 2) 目录 == zip
    zip_path = None
    zip_sha = None
    if args.zip:
        zip_path = os.path.abspath(args.zip)
        if check("zip_exists", os.path.exists(zip_path), zip_path):
            zip_sha = sha256_file(zip_path)
            bad = []
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    names = [n for n in zf.namelist() if not n.endswith("/")]
                    members = {}
                    for n in names:
                        if "/" not in n:
                            bad.append(f"zip 顶层散文件 {n}")
                            continue
                        prefix, rel = n.split("/", 1)
                        if prefix != pkg_name:
                            bad.append(f"zip 前缀不符 {n}")
                            continue
                        members[rel] = zf.read(n)
            except Exception as e:
                members = {}
                bad.append(f"zip 打开失败 {e}")
            if set(members) != set(dir_files):
                bad.append(f"文件集合不一致 only_zip={sorted(set(members)-set(dir_files))[:6]} "
                           f"only_dir={sorted(set(dir_files)-set(members))[:6]}")
            for rel in sorted(set(members) & set(dir_files)):
                if members[rel] != open(dir_files[rel], "rb").read():
                    bad.append(f"内容不一致 {rel}")
            check("dir_equals_zip", not bad, "; ".join(bad[:10]))
    else:
        check("zip_skipped", True, "未提供 --zip")

    # 3) FINALIZE.json（包内）
    fin_path = os.path.join(d, "FINALIZE.json")
    fin = {}
    if check("finalize_present", os.path.exists(fin_path), fin_path):
        try:
            fin = json.load(open(fin_path, encoding="utf-8"))
        except Exception as e:
            fin = {}
            check("finalize_parse", False, str(e))
        need = ["finalize_version", "version", "created_utc", "git", "font_sha256",
                "gate_report_sha256", "sha_final_ok", "zip_ok", "zip_sha256",
                "zip_sha256_scope", "zip_payload_sha256", "scan_artifacts", "record_scope"]
        miss = [k for k in need if k not in fin]
        check("finalize_keys", not miss, f"缺字段 {miss}")
        check("finalize_selfref_null",
              fin.get("sha_final_ok") is None and fin.get("zip_ok") is None
              and fin.get("zip_sha256") is None and bool(fin.get("zip_sha256_scope")),
              "包内 FINALIZE 自指字段应 null 且有 scope 说明（实际终验在 detached）")
        ttfs = [f for f in dir_files if f.lower().endswith(".ttf")]
        if ttfs:
            check("finalize_font_sha", fin.get("font_sha256") == sha256_file(dir_files[ttfs[0]]),
                  f"font_sha256={fin.get('font_sha256')}")
        grs = sorted(f for f in dir_files if re.fullmatch(r"gate-report-[^/]+\.json", f))
        if grs:
            check("finalize_gate_sha",
                  fin.get("gate_report_sha256") == sha256_file(dir_files[grs[0]]),
                  f"gate_report_sha256={fin.get('gate_report_sha256')}")
        # payload sha（排除 FINALIZE.json / SHA256SUMS）
        rows = [f"{sha256_file(p)}  {rel}" for rel, p in sorted(dir_files.items())
                if rel not in ("FINALIZE.json", "SHA256SUMS")]
        payload = hashlib.sha256(("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")).hexdigest()
        check("finalize_payload_sha", fin.get("zip_payload_sha256") == payload,
              "zip_payload_sha256 与包 payload 不一致")
        scan_bad = []
        for kind, rec in (fin.get("scan_artifacts") or {}).items():
            base = os.path.basename(rec.get("path") or "")
            p = os.path.join(d, base)
            if not os.path.exists(p) or sha256_file(p) != rec.get("sha256"):
                scan_bad.append(f"{kind}:产物 sha 不符")
            side_rel = (rec.get("sidecar") or {}).get("path")
            if side_rel:
                sp = os.path.join(d, side_rel)
                if not os.path.exists(sp) or sha256_file(sp) != (rec.get("sidecar") or {}).get("sha256"):
                    scan_bad.append(f"{kind}:sidecar sha 不符")
            if rec.get("sidecar_validated") is not True:
                scan_bad.append(f"{kind}:sidecar 未被 gate 校验通过")
        check("finalize_scan_artifacts", not scan_bad, "; ".join(scan_bad[:8]))

    # 4) gate-report
    grs = sorted(glob.glob(os.path.join(d, "gate-report-*.json")))
    if check("gate_report_present", bool(grs), "缺 gate-report-*.json"):
        gr = {}
        try:
            gr = json.load(open(grs[0], encoding="utf-8"))
        except Exception as e:
            check("gate_report_parse", False, str(e))
        check("gate_report_pass", gr.get("pass") is True, f"pass={gr.get('pass')}")
        check("gate_report_finalized", bool((gr.get("attestation") or {}).get("finalized")),
              "attestation.finalized 非 true")
        check("gate_report_scan_artifacts", bool(gr.get("scan_artifacts")),
              "gate-report 缺 scan_artifacts（扫描产物绑定）")

    # 5) 包外 detached FINALIZE（权威终验记录）
    if args.finalize_json:
        dj = os.path.abspath(args.finalize_json)
        if check("detached_finalize_exists", os.path.exists(dj), dj):
            det = json.load(open(dj, encoding="utf-8"))
            check("detached_sha_final_ok", det.get("sha_final_ok") is True, str(det.get("sha_final_ok")))
            check("detached_zip_ok", det.get("zip_ok") is True, str(det.get("zip_ok")))
            if zip_sha:
                check("detached_zip_sha", det.get("zip_sha256") == zip_sha,
                      f"detached={det.get('zip_sha256')} actual={zip_sha}")
            if os.path.exists(fin_path):
                check("detached_package_finalize_sha",
                      det.get("package_finalize_sha256") == sha256_file(fin_path),
                      "detached.package_finalize_sha256 与包内 FINALIZE.json 不一致")
            if fin:
                check("detached_matches_package",
                      det.get("gate_report_sha256") == fin.get("gate_report_sha256")
                      and det.get("font_sha256") == fin.get("font_sha256"),
                      "detached 与包内 FINALIZE 的 font/gate-report sha 不一致")

    result = {"dir": d, "zip": zip_path, "zip_sha256": zip_sha,
              "files": len(dir_files), "pass": all(c["ok"] for c in checks),
              "checks": checks}
    return [result]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="发布包目录 release/<pkg>/")
    ap.add_argument("--zip", default=None, help="发布 zip（可选；给了就逐文件比对）")
    ap.add_argument("--finalize-json", default=None,
                    help="包外 detached FINALIZE（release/<pkg>.FINALIZE.json，可选）")
    ap.add_argument("--json-out", default=None, help="结果 JSON 输出路径")
    args = ap.parse_args()
    results = verify(args)
    result = results[0]
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fo:
            json.dump(result, fo, ensure_ascii=False, indent=1)
    if result.get("pass"):
        print(f"VERIFY PASS: {result['dir']} files={result['files']} "
              f"zip_sha256={result.get('zip_sha256')}")
        return 0
    print("VERIFY FAIL:")
    for c in result["checks"]:
        if not c["ok"]:
            print(f"  - [{c['name']}] {c['detail']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
