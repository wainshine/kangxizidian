#!/usr/bin/env python3
"""release/ 版本清理：保留指定版本，删除其余（目录+同名 zip），删除前导出历史证据。

用法：
  python scripts/cleanup_releases.py --keep 2.5.8,2.6.1 --dry-run
  python scripts/cleanup_releases.py --keep 2.5.8,2.6.1 --apply [--delete-withdrawn]

留档：
  audit/RELEASE-HISTORY.jsonl        每版本一行（版本/字体sha/闸/SHA状态/大小/日期）
  audit/release-evidence/<ver>-*.json 曾通过闸的版本留 gate-report + SHA256SUMS
"""
import argparse, json, os, shutil, subprocess, hashlib, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = os.path.join(ROOT, "release")
AUDIT = os.path.join(ROOT, "audit")


def ver_from_dir(name):
    if name.startswith("KangXiKai-v"):
        return name[len("KangXiKai-v"):]
    return None


def pkg_info(path):
    info = {"size": 0, "files": 0, "gate": None, "sha_ok": None, "font_sha": None}
    for dp, _, fs in os.walk(path):
        for f in fs:
            fp = os.path.join(dp, f)
            info["size"] += os.path.getsize(fp)
            info["files"] += 1
            if f.startswith("gate-report") and f.endswith(".json"):
                try:
                    info["gate"] = bool(json.load(open(fp)).get("pass"))
                except Exception:
                    info["gate"] = False
            if f.endswith(".ttf") and info["font_sha"] is None:
                info["font_sha"] = hashlib.sha256(open(fp, "rb").read()).hexdigest()
            if f == "SHA256SUMS":
                r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"],
                                   cwd=path, capture_output=True, text=True)
                fails = [ln for ln in (r.stdout or "").splitlines() if "FAILED" in ln]
                info["sha_ok"] = (r.returncode == 0 and not fails)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", default="2.5.8,2.6.1", help="保留的版本号，逗号分隔")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--delete-withdrawn", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        raise SystemExit("必须给 --dry-run 或 --apply")
    keep = {v.strip() for v in args.keep.split(",") if v.strip()}
    entries = []
    for name in sorted(os.listdir(REL)):
        p = os.path.join(REL, name)
        if not os.path.isdir(p) or not name.startswith("KangXiKai-v"):
            continue
        ver = ver_from_dir(name) or ""
        info = pkg_info(p)
        zip_p = os.path.join(REL, name + ".zip")
        info.update({"name": name, "version": ver, "zip_size": os.path.getsize(zip_p) if os.path.exists(zip_p) else 0,
                     "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")})
        info["action"] = "keep" if ver in keep else "delete"
        entries.append(info)

    # 留档（dry-run 也写，方便审计；apply 时同样先写）
    os.makedirs(os.path.join(AUDIT, "release-evidence"), exist_ok=True)
    hist = os.path.join(AUDIT, "RELEASE-HISTORY.jsonl")
    with open(hist, "w", encoding="utf-8") as fo:
        for e in entries:
            fo.write(json.dumps({k: e[k] for k in
                                 ("name", "version", "size", "zip_size", "files", "gate",
                                  "sha_ok", "font_sha", "mtime", "action")}, ensure_ascii=False) + "\n")
    for e in entries:
        if e["gate"] is True:
            p = os.path.join(REL, e["name"])
            for f in os.listdir(p):
                if f.startswith("gate-report") and f.endswith(".json"):
                    shutil.copy2(os.path.join(p, f),
                                 os.path.join(AUDIT, "release-evidence", f"{e['version']}-gate-report.json"))
                if f == "SHA256SUMS":
                    shutil.copy2(os.path.join(p, f),
                                 os.path.join(AUDIT, "release-evidence", f"{e['version']}-SHA256SUMS"))
    deleted = 0; freed = 0
    for e in entries:
        if e["action"] != "delete":
            continue
        p = os.path.join(REL, e["name"]); zp = os.path.join(REL, e["name"] + ".zip")
        freed += e["size"] + e["zip_size"]; deleted += 1
        if args.apply:
            shutil.rmtree(p, ignore_errors=True)
            if os.path.exists(zp):
                os.remove(zp)
    wd = os.path.join(REL, "_withdrawn")
    wd_size = 0
    if args.delete_withdrawn and os.path.isdir(wd):
        for dp, _, fs in os.walk(wd):
            for f in fs:
                wd_size += os.path.getsize(os.path.join(dp, f))
        if args.apply:
            shutil.rmtree(wd, ignore_errors=True)
    print(json.dumps({"keep": sorted(keep), "versions": len(entries), "delete": deleted,
                      "reclaim_mb": round(freed / 1e6, 1),
                      "withdrawn_mb": round(wd_size / 1e6, 1),
                      "withdrawn_deleted": bool(args.delete_withdrawn and args.apply),
                      "done": bool(args.apply),
                      "history": os.path.relpath(hist, ROOT)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
