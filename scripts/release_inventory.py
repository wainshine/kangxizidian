#!/usr/bin/env python3
"""release/ 发布清单生成器（v2.6.3 T4 item5；审计 DOCS-402 / DOCS-414 / LEAD4-001）。

扫描 `release/KangXiKai-v*/` 生成（数值全部现场计算，禁止手写）：
  - `release/RELEASE-INVENTORY.tsv`：name/version/status/finalized/gate_pass/gate_steps/sha_ok/
    files/size/zip 大小/zip_sha256/release_commit/finalize 记录/generated_utc；
  - `release/package_summary.json`：聚合 JSON（generated_utc 用真实 UTC；含每包 zip sha、文件数、
    finalize 状态、gate 状态、detached FINALIZE 校验结果）。

状态口径：
  正式        = 包外 detached `<pkg>.FINALIZE.json` 存在且 sha_final_ok/zip_ok=true，或
                docs/releases/v<ver>/ 有正式发布记录（v2.6.2 及更早的旧包无 FINALIZE）；
  过程版-不签收 = gate-report pass 但无 finalize 凭证；
  预览        = 目录名含 preview/预览 或 gate pass=false。

用法:
  python scripts/release_inventory.py                       # 写 release/（正式发布流程最后一步）
  python scripts/release_inventory.py --out-dir work/lead/test-inventory   # 干跑
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def verify_sha_sums(pkg_dir):
    """校验包内 SHA256SUMS；返回 (ok, n_files, bad)。"""
    sp = os.path.join(pkg_dir, "SHA256SUMS")
    if not os.path.exists(sp):
        return False, 0, ["缺 SHA256SUMS"]
    listed = {}
    try:
        for ln in open(sp, encoding="utf-8"):
            ln = ln.rstrip("\n")
            if not ln:
                continue
            h, rel = ln.split("  ", 1)
            listed[rel] = h
    except Exception as e:
        return False, 0, [f"解析失败 {e}"]
    bad = []
    for rel, h in listed.items():
        p = os.path.join(pkg_dir, rel)
        if not os.path.exists(p):
            bad.append(f"缺失 {rel}")
        elif sha256_file(p) != h:
            bad.append(f"sha 不符 {rel}")
    actual = set()
    for root, dirs, fs in os.walk(pkg_dir):
        for f in fs:
            rel = os.path.relpath(os.path.join(root, f), pkg_dir).replace(os.sep, "/")
            if rel != "SHA256SUMS":
                actual.add(rel)
    bad += [f"未覆盖 {r}" for r in sorted(actual - set(listed))]
    bad += [f"多余条目 {r}" for r in sorted(set(listed) - actual)]
    return (not bad), len(listed), bad


def pkg_info(pkg_dir, release_root):
    name = os.path.basename(pkg_dir.rstrip(os.sep))
    m = re.fullmatch(r"KangXiKai-v(.+)", name)
    version = m.group(1) if m else None
    zip_path = os.path.join(release_root, name + ".zip")
    detached = os.path.join(release_root, name + ".FINALIZE.json")
    info = {"name": name, "version": version, "dir": pkg_dir,
            "zip": zip_path if os.path.exists(zip_path) else None,
            "zip_sha256": sha256_file(zip_path) if os.path.exists(zip_path) else None,
            "zip_mb": round(os.path.getsize(zip_path) / 1e6, 1) if os.path.exists(zip_path) else None}
    # 文件数与大小
    n_files = 0
    total = 0
    for root, dirs, fs in os.walk(pkg_dir):
        for f in fs:
            n_files += 1
            total += os.path.getsize(os.path.join(root, f))
    info["files"] = n_files
    info["mb"] = round(total / 1e6, 1)
    # SHA 自校验
    sha_ok, sha_files, sha_bad = verify_sha_sums(pkg_dir)
    info["sha_ok"] = sha_ok
    info["sha_files"] = sha_files
    info["sha_bad"] = sha_bad[:5]
    # gate-report
    grs = sorted(glob.glob(os.path.join(pkg_dir, "gate-report-*.json")))
    gr = load_json(grs[0]) if grs else None
    info["gate_pass"] = bool((gr or {}).get("pass"))
    info["gate_steps"] = len(((gr or {}).get("steps") or []))
    # 包内 / 包外 FINALIZE
    fin = load_json(os.path.join(pkg_dir, "FINALIZE.json"))
    det = load_json(detached) if os.path.exists(detached) else None
    info["finalize_present"] = fin is not None
    info["detached_finalize"] = detached if os.path.exists(detached) else None
    info["finalized"] = bool(det and det.get("sha_final_ok") is True and det.get("zip_ok") is True)
    if info["finalized"] and info["zip_sha256"]:
        info["finalized"] = info["finalized"] and det.get("zip_sha256") == info["zip_sha256"]
    # 发布 commit
    commit = None
    if det:
        commit = (det.get("git") or {}).get("commit")
    elif fin:
        commit = (fin.get("git") or {}).get("commit")
    elif gr:
        commit = ((gr.get("inputs") or {}).get("git") or {}).get("commit")
    info["release_commit"] = commit
    info["gate_report"] = grs[0] if grs else None
    # 正式记录（旧包无 FINALIZE 时以 docs/releases/v<ver>/RELEASE.md 为准）
    official_doc = os.path.join(ROOT, "docs", "releases", f"v{version}", "RELEASE.md") if version else None
    info["official_release_doc"] = official_doc if official_doc and os.path.exists(official_doc) else None
    if "preview" in name.lower() or "预览" in name:
        info["status"] = "预览"
    elif info["finalized"] or info["official_release_doc"]:
        info["status"] = "正式"
    elif info["gate_pass"]:
        info["status"] = "过程版-不签收"
    else:
        info["status"] = "未签收"
    return info


TSV_COLUMNS = ["name", "version", "status", "finalized", "gate_pass", "gate_steps",
               "sha_ok", "files", "mb", "zip_mb", "zip_sha256", "release_commit",
               "finalize_record", "generated_utc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release-root", default=os.path.join(ROOT, "release"))
    ap.add_argument("--out-dir", default=None,
                    help="输出目录（默认 release-root；干跑时用 work/lead/... 或 /tmp）")
    ap.add_argument("--tsv-name", default="RELEASE-INVENTORY.tsv")
    ap.add_argument("--json-name", default="package_summary.json")
    ap.add_argument("--json-out", default=None, help="额外把聚合 JSON 写到这里")
    args = ap.parse_args()
    rr = os.path.abspath(args.release_root)
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else rr
    os.makedirs(out_dir, exist_ok=True)
    generated = utc_now()
    dirs = sorted(d for d in glob.glob(os.path.join(rr, "KangXiKai-v*")) if os.path.isdir(d))
    rows = []
    for d in dirs:
        info = pkg_info(d, rr)
        rows.append(info)
    rows.sort(key=lambda x: (tuple(int(p) if p.isdigit() else 0
                                   for p in (x["version"] or "0").replace("-", ".").split(".")),
                             x["name"]))
    # TSV
    lines = ["\t".join(TSV_COLUMNS)]
    for r in rows:
        lines.append("\t".join(str({
            "name": r["name"], "version": r["version"], "status": r["status"],
            "finalized": r["finalized"], "gate_pass": r["gate_pass"],
            "gate_steps": r["gate_steps"], "sha_ok": r["sha_ok"],
            "files": r["files"], "mb": r["mb"], "zip_mb": r["zip_mb"],
            "zip_sha256": r["zip_sha256"] or "", "release_commit": r["release_commit"] or "",
            "finalize_record": ("detached" if r["detached_finalize"] else
                                ("in-package" if r["finalize_present"] else "")),
            "generated_utc": generated,
        }[c]) for c in TSV_COLUMNS))
    tsv_path = os.path.join(out_dir, args.tsv_name)
    with open(tsv_path, "w", encoding="utf-8") as fo:
        fo.write("\n".join(lines) + "\n")
    # 聚合 JSON（package_summary.json：最近一版 + 全量清单）
    latest = rows[-1] if rows else None
    summary = {
        "generator": "scripts/release_inventory.py",
        "generated_utc": generated,
        "release_root": rr,
        "n_releases": len(rows),
        "latest": ({k: latest[k] for k in
                    ("name", "version", "status", "finalized", "gate_pass", "gate_steps",
                     "sha_ok", "files", "mb", "zip_mb", "zip_sha256", "release_commit",
                     "finalize_present", "detached_finalize")} if latest else None),
        "releases": [{k: r.get(k) for k in
                      ("name", "version", "status", "finalized", "gate_pass", "gate_steps",
                       "sha_ok", "sha_files", "files", "mb", "zip_mb", "zip_sha256",
                       "release_commit", "finalize_present", "detached_finalize",
                       "official_release_doc")} for r in rows],
    }
    json_path = os.path.join(out_dir, args.json_name)
    with open(json_path, "w", encoding="utf-8") as fo:
        json.dump(summary, fo, ensure_ascii=False, indent=1)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fo:
            json.dump(summary, fo, ensure_ascii=False, indent=1)
    print(json.dumps({"tsv": tsv_path, "json": json_path, "n_releases": len(rows),
                      "generated_utc": generated,
                      "releases": [{"name": r["name"], "status": r["status"],
                                    "finalized": r["finalized"], "sha_ok": r["sha_ok"],
                                    "zip_sha256": r["zip_sha256"]} for r in rows]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
