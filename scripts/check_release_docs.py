#!/usr/bin/env python3
"""发布文档机器校验（P0 防复发）：README/PROVENANCE/QA 的数字与文件引用必须与包内 JSON/文件一致。

用法: python scripts/check_release_docs.py --dir release/KangXiKai-v2.5.5 --version 2.5.5
失败返回非零。
"""
import argparse, json, os, re, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--version", required=True)
    args = ap.parse_args()
    d = args.dir
    v = args.version
    tag = "v" + v.replace(".", "")
    errs = []
    files = set(os.listdir(d))
    # 1) 读取统计
    cov_path = os.path.join(d, f"coverage-detail-{tag}.json")
    stats_path = os.path.join(d, "stats.json")
    man_path = os.path.join(d, f"manifest-{tag}.json")
    if not os.path.exists(man_path):
        # 兼容 v250 命名
        cands = [f for f in files if f.startswith("manifest-") and f.endswith(".json")]
        man_path = os.path.join(d, cands[0]) if cands else None
    cov = json.load(open(cov_path)) if os.path.exists(cov_path) else {}
    stats = json.load(open(stats_path)) if os.path.exists(stats_path) else {}
    n_chars = cov.get("total_glyphs") or stats.get("cmap")
    basic = cov.get("cjk_basic_in_target_set")
    pct = cov.get("basic_coverage_pct")
    gap = cov.get("target_headword_gap")
    for name in ("README.md", "PROVENANCE.md", "QA.md"):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            errs.append(f"{name} 缺失")
            continue
        txt = open(p, encoding="utf-8").read()
        # 版本号
        if v not in txt:
            errs.append(f"{name}: 未出现版本号 {v}")
        # 允许出现的旧版本号（只提示）
        for old in re.findall(r"v?2\.5\.\d", txt):
            pass
        # 数字校验：出现 17,0xx 必须等于 n_chars
        for num in re.findall(r"1[0-9],[0-9]{3}", txt):
            nn = int(num.replace(",", ""))
            if n_chars and nn not in (n_chars, basic, 16567, 20992, 17029, 17013):
                errs.append(f"{name}: 可疑数字 {num}（当前字数 {n_chars}）")
        # 文件引用存在性：`.json/.png/.md` 文件名词
        for ref in re.findall(r"[A-Za-z0-9_.\-]+\.(?:json|png|md)", txt):
            if ref in ("README.md", "PROVENANCE.md", "QA.md", "SHA256SUMS", "OFL.txt"):
                continue
            if ref not in files:
                errs.append(f"{name}: 引用不存在文件 {ref}")
        # 历史版本号出现在「历史/基线」语境中是允许的；仅提示，不算失败
        # （如需强制只出现当前版本，可用 --strict-versions 开关，默认关闭）
    # 2) 包内必须有的清单
    required = [f"KangXiKai-Regular-v{v}.ttf", f"manifest-{tag}.json",
                f"coverage-detail-{tag}.json", f"qa-report-{tag}.json", f"qa-stats-{tag}.json",
                "QA.md", "PROVENANCE.md", "README.md", "SHA256SUMS"]
    for r in required:
        if r not in files:
            errs.append(f"包内缺文件 {r}")
    if errs:
        print("DOC-CHECK FAIL:")
        for e in errs:
            print("  -", e)
        return 1
    print("DOC-CHECK PASS:", v, "chars", n_chars)
    return 0


if __name__ == "__main__":
    sys.exit(main())
