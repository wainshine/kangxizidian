#!/usr/bin/env python3
"""发布构建脚本（v2.4.20 起固化，保证可复现；替换以往会话内联命令）。

用法: python scripts/build_release.py --version 2.4.20 --mapping <mapping.jsonl> --manifest <manifest.json> \
        --out-prefix work/font/build/KangXiKai-v2.4.20 [--clean-scan work/lead/refgate_xxx.jsonl] [--baseline-font <prev.ttf>]
步骤：1) font_build（固定 SOURCE_DATE_EPOCH）→ 2) 可选 refgate_clean → 3) font_qa → 4) content_loss_gate(对基线)
全部命令与输入/输出 sha256 记录到 <prefix>.build_recipe.json。
"""
import argparse, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY313 = os.path.join(ROOT, ".venv", "bin", "python")
EPOCH = "1792713600"


def run(cmd):
    env = dict(os.environ, SOURCE_DATE_EPOCH=EPOCH)
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)
    return " ".join(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--clean-scan", default=None)
    ap.add_argument("--baseline-font", default=None)
    args = ap.parse_args()
    base_ttf = args.out_prefix + ".base.ttf"
    final_ttf = args.out_prefix + ".ttf"
    recipe = {"version": args.version, "source_date_epoch": EPOCH, "steps": []}
    recipe["steps"].append(run([PY313, "scripts/font_build.py", "--mapping", args.mapping,
                               "--out", base_ttf, "--version", args.version]))
    ttf_in = base_ttf
    if args.clean_scan:
        recipe["steps"].append(run([PY313, "scripts/refgate_clean.py", base_ttf,
                                    args.clean_scan, final_ttf]))
        ttf_in = final_ttf
    else:
        final_ttf = base_ttf
    recipe["steps"].append(run([PY313, "scripts/font_qa.py", "--font", final_ttf,
                                "--manifest", args.manifest,
                                "--outdir", os.path.join(ROOT, "work/font/build", "qa_" + args.version.replace(".", ""))]))
    if args.baseline_font:
        recipe["steps"].append(run([PY313, "scripts/content_loss_gate.py", args.baseline_font,
                                    final_ttf, args.manifest,
                                    "work/lead/content_loss_%s.json" % args.version.replace(".", "")]))
    json.dump(recipe, open(args.out_prefix + ".build_recipe.json", "w"), ensure_ascii=False, indent=1)
    for f in (base_ttf, final_ttf):
        if os.path.exists(f):
            import hashlib
            recipe.setdefault("sha256", {})[os.path.basename(f)] = hashlib.sha256(open(f, "rb").read()).hexdigest()
    json.dump(recipe, open(args.out_prefix + ".build_recipe.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"recipe": args.out_prefix + ".build_recipe.json", "font": final_ttf}))


if __name__ == "__main__":
    main()
