#!/usr/bin/env python3
"""work/ 清理 v2（按 owner 原则：JSON/JSONL = 方法核心成果 → 保留；
只删图片/数组/纯缓存等可重建过程物）。

安全规则：
- 保留一切 .json/.jsonl（含 mapping 实验、检测框、OCR 结果、台账、报告）；
  例外：字形缓存（font/build/cache 旧 tag、cache_old_v11）属纯过程缓存，可删；
- 删：png/jpg 图片、pkl/npz/npy 数组、paddlex/uv 工具缓存、旧 TTF（留 3 个里程碑）、
      已被 v260 取代的 v258 台账图、临时稿；
- C 类（现行依赖）永不删除；
- 默认 dry-run；--apply 才删；--include-models 才处理 models；
- 删除前写 work/lead/work-artifacts-inventory.jsonl（+ C 类 sha256）与 lineage 笔记。
"""
import argparse, json, os, shutil, hashlib, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ARR_EXT = {".pkl", ".npz", ".npy", ".pt", ".pth"}
# 跨代代表性字体：保留用于后续对比（其余旧 TTF 删除，sha 留档于 RELEASE-HISTORY）
KEEP_TTF = {
    "KangXiKai-verified-v0.3.ttf",   # 首个实质字体（4,987 字）
    "KangXiKai-verified-v0.9.ttf",   # OCR 挖字饱和
    "KangXiKai-v1.2.ttf",            # 第二轮审计后修复版
    "KangXiKai-v2.3.2.ttf",          # headword-only 前最后大版本
    "KangXiKai-v2.4.0.ttf",          # 恢复「只收字头真迹」标准
    "KangXiKai-v2.4.16.ttf",         # 2×2 格块切分首次
    "KangXiKai-v2.4.19.ttf",         # 审计整改后的 v2.4 末段
    "KangXiKai-v2.4.22.ttf",         # 2×2 格块掩膜完成
    "KangXiKai-v2.5.0.ttf",          # v2.5 架构起点
    "KangXiKai-v2.5.6.ttf",          # 修复回写 + 门禁
    "KangXiKai-v2.5.7.ttf",          # 门禁加固
    "KangXiKai-v2.5.8.ttf",          # 重构前可信基线（现行内容闸对比基准）
    "KangXiKai-v2.5.9.ttf",          # 后处理擦线撤回版（失败证据）
    "KangXiKai-v2.6.0.ttf",          # 切前排除首版（restore 层失败证据）
    "KangXiKai-v2.6.1.ttf",          # 当前基线
}
C_CLASS = [
    "work/lead/page_geometry.jsonl", "work/lead/mapping_verified_all33.jsonl",
    "work/lead/mapping_block_v270.jsonl", "work/lead/repair_overlay_v256.jsonl",
    "work/font/build/manifest_v261.json", "work/font/build/release_extras",
    "work/font/_pylibs", "work/font/build/KangXiKai-v2.5.8.ttf",
    "work/font/build/KangXiKai-v2.6.0.ttf", "work/font/build/KangXiKai-v2.6.1.ttf",
    "work/seq/canonical.jsonl", "work/seq/volume_radicals.json", "work/t2/pdf_map.json",
    "work/review/defect-history-v260", "work/review/round-001",
]
# 目录级：整体删除（纯缓存/纯图片/旧版台账）
WHOLE_DIRS = ["work/t00", "work/detect2", "work/paddlex_cache", "work/uvcache",
              "work/font/build/cache_old_v11", "work/font/tmp", "work/font/sheets",
              "work/font/release-rehearsal", "work/review/defect-history-v258"]
# 文件级：只删图片/数组
FILE_SCAN_DIRS = ["work/t2", "work/seq", "work/lead"]


def sz(p):
    if os.path.isfile(p):
        return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(p) for f in fs
               if os.path.isfile(os.path.join(dp, f)))


def scan_exts(root, exts):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if os.path.splitext(f)[1].lower() in exts:
                p = os.path.join(dp, f)
                try:
                    out.append((p, os.path.getsize(p)))
                except OSError:
                    pass
    return out


def collect():
    A, B = [], []  # (path, size, reason)

    # A：整体删除的死路线/纯缓存（注意：不再删 t00/detect2 的 JSON；这里改为只删其非 JSON）
    for d in ["paddlex_cache", "uvcache", "font/build/cache_old_v11",
              "font/tmp", "font/sheets", "font/release-rehearsal"]:
        p = os.path.join(WORK, d)
        if os.path.exists(p):
            A.append((p, sz(p), "A 纯缓存/临时物"))
    # t00：只删图片（保留其 json 元数据）
    p = os.path.join(WORK, "t00")
    if os.path.isdir(p):
        imgs = scan_exts(p, IMG_EXT)
        if imgs:
            total = sum(s for _, s in imgs)
            A.append((p + "/**/*(图片)", total, f"A 页面渲染图 {len(imgs)} 个"))
    # detect2：只删图片（保留检测框 JSON）
    p = os.path.join(WORK, "detect2")
    if os.path.isdir(p):
        imgs = scan_exts(p, IMG_EXT)
        if imgs:
            A.append((p + "/**/*(图片)", sum(s for _, s in imgs), f"A 检测 montage/模板图 {len(imgs)} 个"))
    # t2/seq/lead：只删图片+数组，JSON 全保留
    for rel in FILE_SCAN_DIRS:
        p = os.path.join(ROOT, rel)
        if not os.path.isdir(p):
            continue
        files = scan_exts(p, IMG_EXT | ARR_EXT)
        if files:
            B.append((p + "/**/*(图片+数组)", sum(s for _, s in files),
                      f"B 过程物（图片/数组 {len(files)} 个；JSON 全部保留）"))
    # 字形缓存旧 tag（纯过程缓存，保留 v350）
    cache = os.path.join(WORK, "font/build/cache")
    if os.path.isdir(cache):
        old = [f for f in os.listdir(cache) if not f.startswith("v350_")]
        total = sum(os.path.getsize(os.path.join(cache, f)) for f in old)
        B.append((cache + "/<非 v350 旧 tag 缓存>", total, f"B 可重建字形缓存 {len(old)} 文件"))
    # 旧 TTF（留 3 个里程碑）
    fb = os.path.join(WORK, "font/build")
    for f in os.listdir(fb):
        if f.endswith(".ttf") and f not in KEEP_TTF:
            B.append((os.path.join(fb, f), os.path.getsize(os.path.join(fb, f)),
                      "B 旧字体（里程碑 3 个保留；sha 已留档）"))
    # v258 台账图（被 v260 取代）
    p = os.path.join(WORK, "review/defect-history-v258")
    if os.path.isdir(p):
        B.append((p, sz(p), "B 已被 v260 取代的台账图"))
    models = []
    p = os.path.join(WORK, "models")
    if os.path.isdir(p):
        models.append((p, sz(p), "models（可选；重下成本高）"))
    return A, B, models


def _delete_item(path, size, reason, applied):
    """支持三类条目：真实路径；'dir/**/*(图片)' 标记；旧字形缓存标记。"""
    if "<非 v350 旧 tag 缓存>" in path:
        cache = path.split("/<非")[0]
        removed = 0
        if applied and os.path.isdir(cache):
            for f in os.listdir(cache):
                if not f.startswith("v350_"):
                    try:
                        os.remove(os.path.join(cache, f)); removed += 1
                    except OSError:
                        pass
        else:
            removed = sum(1 for f in os.listdir(cache) if not f.startswith("v350_")) if os.path.isdir(cache) else 0
        return removed
    if path.endswith("(图片)") or path.endswith("(图片+数组)"):
        base = path.split("/**/")[0]
        exts = IMG_EXT if path.endswith("(图片)") else (IMG_EXT | ARR_EXT)
        files = scan_exts(base, exts)
        if applied:
            for f, _ in files:
                try:
                    os.remove(f)
                except OSError:
                    pass
        return len(files)
    if not os.path.exists(path):
        return 0
    if applied:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass
    return 1


def save_lineage_notes():
    dst = os.path.join(WORK, "lead", "map-lineage-notes")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for d in ["v3full", "charalign9", "charalign14"]:
        src = os.path.join(WORK, "map", d)
        if not os.path.isdir(src):
            continue
        os.makedirs(os.path.join(dst, d), exist_ok=True)
        for f in os.listdir(src):
            sp = os.path.join(src, f)
            if os.path.isfile(sp) and os.path.getsize(sp) < 2_000_000 and f.lower().endswith((".json", ".md", ".txt")):
                shutil.copy2(sp, os.path.join(dst, d, f)); n += 1
    open(os.path.join(dst, "README.md"), "w", encoding="utf-8").write(
        "# mapping lineage 笔记（清理前保存）\n\n"
        "mapping 最终数据：`work/lead/mapping_verified_all33.jsonl`（保留，不可从零重建）。\n"
        "生成脚本：`lead_char_align14.py`（charalign14→mapping）、`lead_gan_targets.py`、`lead_vlm_fp_full.py`（需 work/models）。\n"
        "**所有 map 实验目录的 JSON 结果均已保留**（本清理只删图片/数组/纯缓存）。\n")
    return dst, n


def c_sha():
    out = {}
    for rel in C_CLASS:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p) and os.path.getsize(p) < 200_000_000:
            out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        elif os.path.isdir(p):
            out[rel] = "<dir>"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-models", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        raise SystemExit("必须给 --dry-run 或 --apply")
    A, B, models = collect()
    rows = A + B + (models if args.include_models else [])
    total = sum(r[1] for r in rows)
    missing_c = [rel for rel in C_CLASS if not os.path.exists(os.path.join(ROOT, rel))]
    notes_dir, n_notes = save_lineage_notes()
    csha = c_sha()
    inv = os.path.join(WORK, "lead", "work-artifacts-inventory.jsonl")
    with open(inv, "w", encoding="utf-8") as fo:
        for p, s, why in rows:
            fo.write(json.dumps({"path": os.path.relpath(p, ROOT) if "/**/" not in p else p,
                                 "bytes": s, "reason": why,
                                 "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")},
                                ensure_ascii=False) + "\n")
        for c in C_CLASS:
            cp = os.path.join(ROOT, c)
            if os.path.exists(cp):
                fo.write(json.dumps({"path": c, "bytes": sz(cp),
                                     "reason": "C 保留（唯一证据/现行依赖）",
                                     "sha256": csha.get(c)}, ensure_ascii=False) + "\n")
    for name, rr in (("A 纯缓存/图片（死路线）", A), ("B 过程物/可重建缓存/旧字体", B),
                     ("models（可选）", models if args.include_models else [])):
        if not rr:
            continue
        print(f"\n== {name}: {len(rr)} 项 / {sum(r[1] for r in rr)/1e9:.2f} GB")
        for p, s, why in sorted(rr, key=lambda x: -x[1])[:14]:
            print(f"  {s/1e6:9.1f} MB  {p.replace(ROOT+'/','')}")
        if len(rr) > 14:
            print(f"  ... 其余 {len(rr)-14} 项")
    print(f"\n合计待删: {len(rows)} 项 / {total/1e9:.2f} GB"
          f"{'（不含 models）' if not args.include_models else '（含 models）'}")
    print(f"留档: {os.path.relpath(inv, ROOT)}；lineage 笔记: {os.path.relpath(notes_dir, ROOT)}（{n_notes} 文件）")
    if missing_c:
        print("WARN C 类缺失:", missing_c)
    if args.apply:
        cnt = 0
        for p, s, why in rows:
            cnt += _delete_item(p, s, why, applied=True)
        # 清空目录
        for d in ["t00", "detect2"]:
            dp = os.path.join(WORK, d)
            if os.path.isdir(dp):
                for dp2, _, fs in os.walk(dp):
                    pass
        print(f"已删除。涉及 {cnt} 个路径/文件组；C 类未动。")
    else:
        print("dry-run：未删除任何文件。")


if __name__ == "__main__":
    main()
