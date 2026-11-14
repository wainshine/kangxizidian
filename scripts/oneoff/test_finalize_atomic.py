#!/usr/bin/env python3
"""T4 finalize 原子性失败注入自测（LEAD4-002）：进入 finalize 后任一步失败必须「零写包」。

不跑真实闸（用已 finalize 的 /tmp 合成包作为 fixture，步骤/输入直接取自包内 gate-report），
直接调用 release_gate.finalize_package 覆盖三种内部失败点（sha / zip / pre-swap）+ 换包（TTF 被改），
每次断言包目录逐文件字节不变、zip 字节不变；最后成功路径断言 FINALIZE.json/包外 detached 生成。

用法:
  .venv/bin/python scripts/oneoff/test_finalize_atomic.py --pkg /tmp/t4-rel/KangXiKai-v2.6.3 \
      --zip /tmp/t4-rel/KangXiKai-v2.6.3.zip
默认使用上面的 /tmp e2e 包（不存在则先按 T4 e2e 流程生成）。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import release_gate as RG  # noqa: E402


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(d):
    rows = []
    for root, dirs, fs in os.walk(d):
        dirs.sort()
        for f in sorted(fs):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, d).replace(os.sep, "/")
            rows.append(f"{sha256_file(p)}  {rel}")
    return hashlib.sha256(("\n".join(sorted(rows)) + "\n").encode()).hexdigest(), len(rows)


def make_args(pkg, zip_path):
    return types.SimpleNamespace(pkg_dir=pkg, zip=zip_path,
                                 font="work/font/build/KangXiKai-v2.6.3.ttf")


def fixture_meta(pkg, tag="v263"):
    gr = json.load(open(os.path.join(pkg, f"gate-report-{tag}.json"), encoding="utf-8"))
    fin = json.load(open(os.path.join(pkg, "FINALIZE.json"), encoding="utf-8"))
    fin_steps = {"sha256", "zip_selfcheck", "doc_check_final", "verify_release",
                 "pkg_font_sha", "pkg_scan_artifacts"}
    steps = [s for s in (gr.get("steps") or []) if s.get("step") not in fin_steps]
    scan = {k: {"path": v.get("path"), "sha256": v.get("sha256"),
                "rows": v.get("rows"), "flagged": v.get("flagged"),
                "error_rows": v.get("error_rows"),
                "created_utc": v.get("created_utc"), "git": v.get("git"),
                "sidecar": v.get("sidecar"), "ok": True}
            for k, v in (fin.get("scan_artifacts") or {}).items()}
    return steps, gr.get("inputs") or {}, scan


def run_case(name, pkg, zip_path, inject, expect_success=False):
    before_digest, n_before = tree_digest(pkg)
    before_zip = sha256_file(zip_path) if os.path.exists(zip_path) else None
    steps, inputs, scan = fixture_meta(pkg)
    ok, out_steps, info = RG.finalize_package(make_args(pkg, zip_path), "2.6.3", "v263",
                                              steps, inputs, scan,
                                              os.path.join(tempfile.gettempdir(), "t4-fin.json"),
                                              inject_fail=inject)
    after_digest, n_after = tree_digest(pkg)
    after_zip = sha256_file(zip_path) if os.path.exists(zip_path) else None
    faithful = (ok if expect_success else not ok)
    ok = faithful and before_digest == after_digest and before_zip == after_zip
    return {"case": name, "ok": bool(ok), "detail": (info.get("detail") or {}).get("reason", ""),
            "dir_unchanged": before_digest == after_digest,
            "zip_unchanged": before_zip == after_zip, "n_files": n_after}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", default="/tmp/t4-rel/KangXiKai-v2.6.3")
    ap.add_argument("--zip", default="/tmp/t4-rel/KangXiKai-v2.6.3.zip")
    args = ap.parse_args()
    if not os.path.isdir(args.pkg):
        print(json.dumps({"pass": False, "error": f"fixture 包不存在: {args.pkg}（先跑 T4 e2e）"}))
        return 2
    tmp = tempfile.mkdtemp(prefix="t4-finalize-atomic-")
    results = []
    try:
        # 1) finalize 后段注入失败：包/zip 必须字节不变
        for inject in ("sha", "zip", "pre-swap"):
            work_pkg = os.path.join(tmp, f"pkg-{inject}", os.path.basename(args.pkg))
            os.makedirs(os.path.dirname(work_pkg))
            shutil.copytree(args.pkg, work_pkg)
            work_zip = os.path.join(os.path.dirname(work_pkg), os.path.basename(args.zip))
            shutil.copy2(args.zip, work_zip)
            results.append(run_case(f"inject_fail_{inject}", work_pkg, work_zip, inject))
        # 2) 换包（TTF 被改）→ FAIL 且包字节不变
        work_pkg = os.path.join(tmp, "pkg-tamper", os.path.basename(args.pkg))
        os.makedirs(os.path.dirname(work_pkg))
        shutil.copytree(args.pkg, work_pkg)
        work_zip = os.path.join(os.path.dirname(work_pkg), os.path.basename(args.zip))
        shutil.copy2(args.zip, work_zip)
        ttf = [f for f in os.listdir(work_pkg) if f.lower().endswith(".ttf")][0]
        with open(os.path.join(work_pkg, ttf), "ab") as fo:
            fo.write(b"\x00tamper")
        results.append(run_case("tamper_pkg_font", work_pkg, work_zip, None))
        # 3) 成功路径：FINALIZE.json + 包外 detached 必须生成
        ok_pkg = os.path.join(tmp, "pkg-ok", os.path.basename(args.pkg))
        os.makedirs(os.path.dirname(ok_pkg))
        shutil.copytree(args.pkg, ok_pkg)
        ok_zip = os.path.join(os.path.dirname(ok_pkg), os.path.basename(args.zip))
        shutil.copy2(args.zip, ok_zip)
        steps, inputs, scan = fixture_meta(ok_pkg)
        ok, _, info = RG.finalize_package(make_args(ok_pkg, ok_zip), "2.6.3", "v263",
                                          steps, inputs, scan,
                                          os.path.join(tempfile.gettempdir(), "t4-fin-ok.json"))
        det = os.path.join(os.path.dirname(ok_zip), os.path.basename(ok_zip)[:-4] + ".FINALIZE.json")
        fin_ok = (ok and os.path.exists(os.path.join(ok_pkg, "FINALIZE.json"))
                  and os.path.exists(det)
                  and all(os.path.exists(p) for p in
                          (os.path.join(os.path.dirname(ok_zip), os.path.basename(ok_zip)[:-4] + ".FINALIZE.json"),))
                  and info.get("detail", {}).get("sha_final_ok") is True
                  and info.get("detail", {}).get("zip_ok") is True)
        results.append({"case": "success_path", "ok": bool(fin_ok),
                        "detail": "FINALIZE.json + detached + zip sha 记录" if fin_ok else
                                  json.dumps(info.get("detail"))[:200]})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    passed = all(r["ok"] for r in results)
    print(json.dumps({"pass": passed, "cases": results}, ensure_ascii=False, indent=1))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
