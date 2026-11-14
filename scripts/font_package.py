#!/usr/bin/env python3
"""C 流 · 发布打包链：TTF + 字表/统计 → release/<family>-v<ver>/ → SHA256SUMS → zip。

改造自 guangeti scripts/14_package.py（来源 commit 见 docs/VENDORED.md），保持两条铁律：
  1) **顺序固定**：构建字体 → 写 stats/provenance/README/OFL → **最后重算 SHA256SUMS** → zip；
     顺序反了会出现「包内自校验失败」（guangeti 踩过）。
  2) **zip 内自校验**：打包后重新读 zip，按 zip 内 SHA256SUMS 逐文件核对，任一不符即失败。

本项目的差异（刻本 / 无 GAN 训练输入）：
  - provenance 四态（D4）：real / gan / ribbon_fb / mapped_traditional；
  - demo 版 provenance 由 manifest 推导（全部 real）；全量版用 `--provenance <json>` 注入；
  - 缺口披露：cmap 承诺（基本区 20,992）与「真迹数」分开统计，README 如实写；
  - **OFL 单一真源（DOCS-403）**：OFL.txt/LICENSE 直接复制仓库根文件，脚本不再内嵌许可全文；
    许可正文只在仓库根维护一份；包内 OFL 的 sha256 记录进 stats.json（check_release_docs 校验与根一致）。
  - **build_stats 证据（BUILD-401/T4）**：自动读取 `<font>.build_stats.json`（或 --build-stats），
    README 的构建时间取真实构建完成时间（字体 mtime UTC），并记录 build_stats 的 sha256。

QA 闸（任一失败即退出，不产出 zip）：
  - fontTools 可开；glyf/cmap/head/hhea/hmtx/maxp/name/OS-2/post 齐全；
  - cmap 与 manifest/expected-charset 完全一致（不假覆盖）；
  - 空字形 = 0；bbox 在 em 内；advance == UPM；
  - provenance 覆盖 cmap 全部码位、取值合法、与 stats 计数一致；
  - SHA256SUMS 与目录内文件一致；zip 内自校验通过。

用法（demo）：
  .venv/bin/python scripts/font_package.py \
      --font work/font/demo/KangXiKai-demo-v0.1.0.ttf \
      --manifest work/font/demo/manifest.json \
      --specimen work/font/demo/specimen.png \
      --out release

用法（全量，下一会话）：
  .venv/bin/python scripts/font_package.py \
      --font work/font/build/KangXiKai-full-v1.0.0.ttf \
      --provenance work/font/build/provenance-full.json \
      --charset work/font/build/cmap-full.txt \
      --version 1.0.0 --out release
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import subprocess
import json
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "font"
sys.path.insert(0, str(WORK / "_pylibs"))

FAMILY = "KangXi Kai"
STYLE = "Regular"
COPYRIGHT_HOLDER = "The KangXi Kai Project Authors"
COPYRIGHT_YEAR = "2026"

REQUIRED_TABLES = ["glyf", "loca", "cmap", "head", "hhea", "hmtx", "maxp", "name",
                   "OS/2", "post"]
PROV_STATES = {"real", "gan", "ribbon_fb", "mapped_traditional"}
BLOCK = (0x4E00, 0x9FFF)          # CJK 基本区（D3/D11 口径）
PUNCT_EXPECTED = 42               # 发布版标点/数字/空格数量（13_extend_punct，punct_set.py 唯一源）

README_TEMPLATE = """# {family} {style} v{version}

{family}（康熙楷）— 从清康熙五十五年内府刊本《康熙字典》扫描件的**字头楷书**矢量化而来。
Kai 指字头风格（楷体）；注文为宋体，本项目不使用注文字形。

## 文件

| 文件 | 说明 |
|---|---|
| `{ttf_name}` | 字体本体（TrueType, EM {upm}） |
| `OFL.txt` | SIL Open Font License 1.1 全文（**复制仓库根 OFL.txt**，单一真源） |
| `LICENSE` | 代码/仓库许可（MIT，复制仓库根 LICENSE） |
| `README.md` | 本文件 |
| `manifest-v{tag}.json` | 字表 + 每字 page/half/box 来源 |
| `provenance.json` | 逐码位来源（{prov_states}） |
| `provenance-detail-v{tag}.json` | 逐字来源明细（mapping 快照） |
| `coverage-detail-v{tag}.json` | 覆盖数字（机器可读） |
| `stats.json` | 字集/来源/构建证据统计（机器可读） |
| `build_recipe-v{tag}.json` | 可复现构建配方（git/cache_ver/输入 sha/真实构建时间） |
| `KangXiKai-v{version}.build_stats.json` | 构建统计原始证据（逐字落盘字段） |
| `gate-report-v{tag}.json` | L1–L3 全闸报告（含扫描产物 sha 绑定） |
| `missing_scan_v{tag}.jsonl` + `.sha256` | 缺件扫描产物 + 输入绑定 sidecar |
| `frame_scan_v{tag}.jsonl` + `.sha256` | 框线逃逸扫描产物 + 输入绑定 sidecar |
| `FINALIZE.json` | finalize 只读凭证（font/gate-report/扫描产物 sha、git、时间） |
| `KNOWN-DEBTS.md` / `QA.md` / `PROVENANCE.md` | 已知债 / 质量闸 / 来源披露 |
| `review/` | 本轮人工复核包快照 |
| `SHA256SUMS` | 包内所有文件的 sha256（自校验用） |
{specimen_row}

## 字集与来源（provenance 四态）

| provenance | 含义 | 本版数量 |
|---|---|---|
| `real` | 字头真迹矢量化 | **{real_n}** |
| `gan` | GAN 生成（目标风格=本书字头） | {gan_n} |
| `ribbon_fb` | ribbon 回落（文楷骨架+带状） | {ribbon_n} |
| `mapped_traditional` | 简体码位 → 映射繁体字形 | {mapped_n} |

- cmap 覆盖：**{cmap_n}** 码位；其中真迹 **{real_n}**。
- {gap_text}
- 缺口原因：简体新码点、日文新字体、现代造字在 1716 年字典中本无字头；
  **不得**把生成/回落/映射字形冒充 `real`。
- 具体逐码位来源见 `provenance.json`；本版未进 cmap 的码位不会以「假覆盖」出现。

## 来源与许可

- 字形来源：清康熙五十五年内府刊本《康熙字典》（1716）扫描件字头；
  未使用任何现代字库轮廓。
- 许可：SIL Open Font License 1.1（见 `OFL.txt`）。
  本项目未使用 LXGW WenKai 的任何 Reserved Font Name（霞鹜/霞鶩/落霞孤鹜/落霞孤鶩/LXGW）。
- 扫描件/影印本的权利状态：{scan_rights}

## 重建与校验

```bash
sha256sum -c SHA256SUMS          # 校验包内文件
```
本包由 `scripts/font_package.py` 生成；构建顺序：字体 → stats/provenance → SHA256SUMS → zip。

{extra_footer}"""


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str):
    raise SystemExit(f"ABORT: {msg}")


def load_font_qa(font_path: Path, expected: set[str]) -> dict:
    """字体侧 QA 闸：表/空字形/bbox/advance/fontRevision。"""
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen

    f = TTFont(str(font_path))
    missing = [t for t in REQUIRED_TABLES if t not in f]
    if missing:
        fail(f"missing tables {missing}")
    cmap = f.getBestCmap()
    have = {chr(cp) for cp in cmap}
    if have != expected:
        fail(f"cmap({len(have)}) != expected charset({len(expected)}); "
             f"missing={sorted(expected - have)[:6]} extra={sorted(have - expected)[:6]}")
    gs = f.getGlyphSet()
    empty, out_of_em, adv_bad = [], [], []
    for cp, gname in cmap.items():
        bp = BoundsPen(gs)
        gs[gname].draw(bp)
        if not bp.bounds:
            empty.append(chr(cp))
            continue
        x0, y0, x1, y1 = bp.bounds
        if x0 < -80 or x1 > 1080 or y0 < -200 or y1 > 980:
            out_of_em.append(chr(cp))
        if f["hmtx"][gname][0] != f["head"].unitsPerEm:
            adv_bad.append(chr(cp))
    if empty:
        fail(f"empty glyphs {empty[:8]}")
    if out_of_em:
        fail(f"out-of-em glyphs {out_of_em[:8]}")
    if adv_bad:
        fail(f"advance != UPM for {adv_bad[:8]}")
    ver = f["name"].getDebugName(5) or ""
    return {
        "tables": sorted(f.keys()),
        "upm": f["head"].unitsPerEm,
        "ascent": f["hhea"].ascent, "descent": f["hhea"].descent,
        "glyphs": f["maxp"].numGlyphs,
        "cmap": len(cmap),
        "name_family": f["name"].getDebugName(1),
        "name_style": f["name"].getDebugName(2),
        "name_version": ver,
        "name_ps": f["name"].getDebugName(6),
        "head_created": f["head"].created,
        "head_modified": f["head"].modified,
    }


def build_provenance(manifest: dict | None, prov_file: str | None,
                     font_chars: set[str]) -> dict[str, str]:
    """构造逐码位 provenance；demo 用 manifest，全量用 --provenance 文件。"""
    prov: dict[str, str] = {}
    if prov_file:
        p = Path(prov_file)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            fail(f"provenance 文件不存在: {p}")
        raw = json.load(open(p))
        for k, v in raw.items():
            ch = k if len(k) == 1 else None
            if ch is None and k.startswith("U+"):
                ch = chr(int(k[2:], 16))
            if ch is None or ch not in font_chars:
                fail(f"provenance 含 cmap 外码位: {k}")
            if v not in PROV_STATES:
                fail(f"非法 provenance 状态 {v!r} ({k})")
            prov[ch] = v
        missing = font_chars - set(prov)
        if missing:
            fail(f"provenance 缺 {len(missing)} 个 cmap 码位: {''.join(sorted(missing)[:12])}")
        return prov
    if not manifest:
        fail("需要 --manifest（demo）或 --provenance（全量）")
    chars = manifest.get("chars") or {}
    for ch, rec in chars.items():
        state = rec.get("provenance") or manifest.get("provenance") or "real"
        if state not in PROV_STATES:
            fail(f"manifest 非法 provenance {state!r} ({ch})")
        prov[ch] = state
    missing = font_chars - set(prov)
    if missing:
        fail(f"manifest 缺 {len(missing)} 个 cmap 码位: {''.join(sorted(missing)[:12])}")
    return {k: prov[k] for k in sorted(prov)}


def expected_from_manifest(manifest: dict | None, charset: str | None) -> set[str]:
    if charset:
        p = Path(charset)
        if not p.is_absolute():
            p = ROOT / p
        raw = p.read_text(encoding="utf-8")
        return {ch for ch in raw if not ch.isspace()}
    if manifest:
        return set((manifest.get("chars") or {}).keys())
    fail("需要 --manifest 或 --charset 指定期望字集")


def count_prov(prov: dict[str, str]) -> dict:
    from collections import Counter
    c = Counter(prov.values())
    return {s: c.get(s, 0) for s in sorted(PROV_STATES)}


def utc_iso(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_build_stats(font_path: Path, explicit: str = "") -> tuple[dict, Path | None]:
    """读取构建统计（证据链）：默认与字体同名的 <font>.build_stats.json。"""
    p = Path(explicit) if explicit else Path(str(font_path).rsplit(".", 1)[0] + ".build_stats.json")
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {}, None
    try:
        return json.load(open(p, encoding="utf-8")), p
    except Exception:
        return {}, p


def copy_license_files(out: Path) -> dict:
    """OFL/LICENSE 单一真源（DOCS-403）：只复制仓库根文件，不在脚本里内嵌许可全文。"""
    res = {}
    for name in ("OFL.txt", "LICENSE"):
        src = ROOT / name
        if not src.exists():
            fail(f"仓库根缺少 {name}（许可单一真源）；拒绝生成包内 {name}")
        shutil.copy2(src, out / name)
        res[name] = {"source": name, "sha256": sha256(src)}
    return res


def render_readme(stats: dict, prov_counts: dict, version: str, ttf_name: str,
                  specimen: bool) -> str:
    cmap_n = stats["cmap"]
    real_n = prov_counts.get("real", 0)
    tag = "v" + version.replace(".", "")
    gap_text = (f"本版为**管线验证 demo**：只映射真实存在且已目检的真迹字 "
                f"（{real_n} 字），未做 20,992 基本区全覆盖承诺；缺字不 fill。"
                if cmap_n < 1000 else
                f"本版目标 cmap {20992 + PUNCT_EXPECTED}（基本区 20,992 + 标点/数字/空格 "
                f"{PUNCT_EXPECTED}），实际 {cmap_n}；真迹 {real_n}，"
                f"非真迹 {cmap_n - real_n}（见 provenance 表）。")
    return README_TEMPLATE.format(
        family=FAMILY, style=STYLE, version=version, tag=tag, upm=stats["upm"],
        ttf_name=ttf_name,
        prov_states="real / gan / ribbon_fb / mapped_traditional",
        specimen_row="| `specimen.png` | 样张（字体自渲染） |" if specimen else "",
        real_n=real_n, gan_n=prov_counts.get("gan", 0),
        ribbon_n=prov_counts.get("ribbon_fb", 0),
        mapped_n=prov_counts.get("mapped_traditional", 0),
        cmap_n=cmap_n, gap_text=gap_text,
        scan_rights="以项目 `docs/DATA.md` 的披露为准（所有者提供后更新；当前 demo 版本未随包披露）。",
        extra_footer=("## 备注\n\n- 本版为 v0 demo（32 字），用于验证「字头图 → 归一化 → 矢量化 → 字体」"
                      "全链；全量版将按 D3/D4 口径披露缺口与 provenance 分布。\n"
                      if cmap_n < 1000 else ""),
    )


def _iter_pkg_files(out: Path):
    """包内全部文件（递归；review/ 等子目录必须进 SHA256SUMS 与 zip）。"""
    for root, dirs, files in os.walk(out):
        dirs.sort()
        for f in sorted(files):
            yield Path(root) / f


def write_sha256sums(out: Path) -> list[tuple[str, str]]:
    rows = []
    for p in _iter_pkg_files(out):
        rel = p.relative_to(out).as_posix()
        if rel == "SHA256SUMS":
            continue
        rows.append((sha256(p), rel))
    (out / "SHA256SUMS").write_text(
        "\n".join(f"{h}  {n}" for h, n in rows) + "\n", encoding="utf-8")
    return rows


def verify_zip(zip_path: Path) -> None:
    """zip 内自校验：读 zip 内 SHA256SUMS，逐文件核对。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        sums_name = [n for n in names if n.endswith("/SHA256SUMS")][0]
        prefix = sums_name[: -len("SHA256SUMS")]
        expected = {}
        for line in zf.read(sums_name).decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            h, name = line.split("  ", 1)
            expected[name] = h
        for name, h in expected.items():
            data = zf.read(prefix + name)
            got = hashlib.sha256(data).hexdigest()
            if got != h:
                fail(f"zip 内自校验失败: {name}")
        extra = [n for n in names
                 if not n.endswith("/") and n != sums_name
                 and n[len(prefix):] not in expected]
        if extra:
            fail(f"zip 内有 SHA256SUMS 未覆盖的文件: {extra[:6]}")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True, help="构建好的 TTF")
    ap.add_argument("--manifest", default="", help="demo manifest.json（含 chars）")
    ap.add_argument("--provenance", default="", help="全量 provenance.json（char/U+XXXX -> 状态）")
    ap.add_argument("--charset", default="", help="全量期望字集文件（每行/连续字符串均可）")
    ap.add_argument("--specimen", default="", help="样张 PNG（可选，打包进 release）")
    ap.add_argument("--readme-template", default="", help="覆盖内置 README 模板（可选）")
    ap.add_argument("--out", default=str(ROOT / "release"), help="release 根目录")
    ap.add_argument("--version", default="", help="默认从 name 表 Version 读取")
    ap.add_argument("--zip", action="store_true", default=True, help="生成 zip（默认开）")
    ap.add_argument("--no-zip", dest="zip", action="store_false")
    ap.add_argument("--skip-qa", action="store_true", help="跳过字体 QA（不建议）")
    ap.add_argument("--force-overwrite", action="store_true",
                    help="允许覆盖已 finalize（包内 gate-report 标记 finalized=true）的包")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="允许工作区未提交（仅调试；正式包必须 clean tree 并记录 commit）")
    ap.add_argument("--extra-dir", action="append", default=[],
                    help="额外打进 release 的目录（可多次；保留目录名，在 SHA256SUMS 前复制）")
    ap.add_argument("--extra-dir-flat", action="append", default=[],
                    help="额外目录内容摊平到包根（可多次；子目录保留，用于 make_release_extras staging）")
    ap.add_argument("--extra", action="append", default=[],
                    help="额外打进 release 的文件（可多次；在 SHA256SUMS 前复制）")
    ap.add_argument("--build-stats", default="",
                    help="构建统计 JSON（默认 <font>.build_stats.json；用于真实构建时间/证据）")
    args = ap.parse_args()

    # 可复现性闸：打包必须来自已提交的代码树（否则 hash 不可复现）
    if not args.allow_dirty:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT),
                           capture_output=True, text=True)
        dirty = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        if dirty:
            fail("工作区有未提交改动，先提交代码再打包（--allow-dirty 仅限调试）：\n  "
                 + "\n  ".join(dirty[:10]))

    font_path = Path(args.font)
    if not font_path.is_absolute():
        font_path = ROOT / font_path
    if not font_path.exists():
        fail(f"font 不存在: {font_path}")

    manifest = None
    if args.manifest:
        mp = Path(args.manifest)
        if not mp.is_absolute():
            mp = ROOT / mp
        manifest = json.load(open(mp))
        manifest_mtime = mp.stat().st_mtime
        # freshness（BUILD-401/T4）：manifest 由 build_stats 派生时，字体只需与 build_stats 的
        # sha256 一致即可证明「manifest 来自该字体构建」，不再依赖脆弱的 mtime 先后。
        build_stats, build_stats_path = load_build_stats(font_path, args.build_stats)
        font_sha = sha256(font_path)
        fresh_by_evidence = bool(
            build_stats
            and build_stats.get("sha256") == font_sha
            and int(build_stats.get("n_chars") or -1) == len((manifest or {}).get("chars") or {}))
        if font_path.stat().st_mtime < manifest_mtime and not fresh_by_evidence:
            fail(f"{font_path.name} 比 manifest 旧，请先重建字体（freshness gate）")
    else:
        build_stats, build_stats_path = load_build_stats(font_path, args.build_stats)
        font_sha = sha256(font_path)

    expected = expected_from_manifest(manifest, args.charset)
    qa = load_font_qa(font_path, expected)
    version = args.version or "".join(
        ch for ch in qa["name_version"].replace("Version ", "").strip())
    if not version:
        fail("无法确定 version（name 表为空且未传 --version）")

    if not args.skip_qa:
        # 复用 font_qa.py 的字体检查（manifest 模式）；失败即中止
        qa_out = WORK / "qa" / f"package-{version}"
        cmd = [sys.executable, str(ROOT / "scripts" / "font_qa.py"),
               "--font", str(font_path), "--outdir", str(qa_out)]
        if manifest is not None:
            cmd += ["--manifest", str(ROOT / args.manifest)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            fail("font_qa 未通过:\n" + r.stdout[-2000:] + r.stderr[-1000:])

    prov = build_provenance(manifest, args.provenance, expected)
    prov_counts = count_prov(prov)

    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    out = out_root / f"KangXiKai-v{version}"
    if out.exists():
        # 审计 P1-2：已 finalize 的包不允许静默覆盖（冻结后不改包内文件）
        if not args.force_overwrite:
            for f in os.listdir(out):
                if f.startswith("gate-report-") and f.endswith(".json"):
                    try:
                        gr = json.load(open(os.path.join(out, f), encoding="utf-8"))
                        if (gr.get("attestation") or {}).get("finalized"):
                            fail(f"包已 finalize（{f}），拒绝覆盖；确需重建请加 --force-overwrite")
                    except Exception:
                        pass
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # ① 字体本体
    ttf_name = f"KangXiKai-{STYLE}-v{version}.ttf"
    shutil.copy2(font_path, out / ttf_name)
    # ② OFL / README / provenance / stats / coverage
    def load_target_chars():
        """canonical 唯一基本区目标表（D19 口径）。"""
        target = set()
        tp = ROOT / "work/seq/canonical.jsonl"
        if tp.exists():
            for line in open(tp, encoding="utf-8"):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                ch = r.get("char")
                if ch and len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
                    target.add(ch)
        return target
    target = load_target_chars()
    target_covered = len(set(prov) & target) if target else 0
    basic_covered = sum(1 for ch in prov if 0x4E00 <= ord(ch) <= 0x9FFF)
    # OFL/LICENSE：单一真源 = 仓库根文件（DOCS-403）；脚本内不再内嵌许可全文
    license_info = copy_license_files(out)
    packaged_at_utc = utc_iso(datetime.datetime.now(datetime.timezone.utc).timestamp())
    # 真实构建完成时间（BUILD-401/T4）：字体 mtime 是构建落盘时刻；SOURCE_DATE_EPOCH 只决定
    # 字体内部 head 时间戳（可复现构建口径），不等于构建时间。
    build_time_utc = utc_iso(font_path.stat().st_mtime)
    stats = {
        "family": FAMILY, "style": STYLE, "version": version,
        "license": "OFL-1.1",
        "file": ttf_name, "file_bytes": (out / ttf_name).stat().st_size,
        "sha256": font_sha,
        **qa,
        "license_files": license_info,
        "build_evidence": {
            "build_time_utc": build_time_utc,
            "build_time_utc_source": "font file mtime (build completion)",
            "packaged_at_utc": packaged_at_utc,
            "source_date_epoch": (build_stats or {}).get("source_date_epoch"),
            "cache_ver": (build_stats or {}).get("cache_ver"),
            "git": (build_stats or {}).get("git"),
            "build_stats": ({
                "path": (os.path.relpath(build_stats_path, ROOT)
                         if build_stats_path and build_stats_path.is_relative_to(ROOT)
                         else (str(build_stats_path) if build_stats_path else None)),
                "sha256": sha256(build_stats_path) if build_stats_path else None,
            } if build_stats_path else None),
        },
        "charset_scope": {
            # D15（headword-only）：不再承诺 20,992/21,034 cmap 覆盖；只发布真迹字表。
            # legacy_target_cmap 仅留作历史对照（D3 旧口径，已作废）。
            "actual_cmap": len(prov),
            "legacy_target_cmap": 20992 + PUNCT_EXPECTED,
            "cjk_basic_block": [f"U+{BLOCK[0]:04X}", f"U+{BLOCK[1]:04X}"],
            "punct_expected": 0,
            "note": "headword-only：不含标点/数字/空格；缺口清单见 high-freq-gap 与 lead_gan_targets（D19）",
        },
        "provenance_counts": prov_counts,
        "real": prov_counts.get("real", 0),
        "non_real": sum(v for k, v in prov_counts.items() if k != "real"),
        # 覆盖数字（README 模板 / doc_check 用；D19 口径）
        "target_set_size": len(target),
        "target_covered": target_covered,
        "target_coverage_pct": round(100.0 * target_covered / len(target), 2) if target else 0.0,
        "basic_block_covered": basic_covered,
        "basic_block_total": BLOCK[1] - BLOCK[0] + 1,
        "basic_block_pct": round(100.0 * basic_covered / (BLOCK[1] - BLOCK[0] + 1), 2),
        "target_headword_gap": max(0, len(target) - target_covered),
        # README 模板 `{built_at_utc}` 用：真实构建完成时间（不是打包/写文件时间）
        "built_at_utc": build_time_utc,
        "packaged_at_utc": packaged_at_utc,
    }
    (out / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "coverage.txt").write_text("".join(sorted(expected)), encoding="utf-8")
    tpl = Path(args.readme_template) if args.readme_template else None
    if tpl and tpl.exists():
        fmt = {k: v for k, v in stats.items() if isinstance(v, (str, int, float))}
        for k, v in prov_counts.items():
            fmt[k] = v
            fmt[f"{k}_n"] = v
        readme = tpl.read_text(encoding="utf-8").format(**fmt)
    else:
        readme = render_readme(stats, prov_counts, version, ttf_name, False)
    (out / "README.md").write_text(readme, encoding="utf-8")
    # ③ 样张（可选）
    if args.specimen:
        sp = Path(args.specimen)
        if not sp.is_absolute():
            sp = ROOT / sp
        if sp.exists():
            shutil.copy2(sp, out / "specimen.png")
    # ③b 额外文件（审计要求：manifest / QA 报告 / provenance 明细随包发布）
    for extra in args.extra:
        ep = Path(extra)
        if not ep.is_absolute():
            ep = ROOT / ep
        if not ep.exists():
            fail(f"extra 文件不存在: {ep}")
        shutil.copy2(ep, out / ep.name)
    for ed in args.extra_dir:
        edp = Path(ed)
        if not edp.is_absolute():
            edp = ROOT / edp
        if not edp.exists():
            fail(f"extra-dir 不存在: {edp}")
        dst = out / edp.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(edp, dst)
    # staging 目录内容摊平到包根（make_release_extras 产出；review/ 子目录保留为包内子目录）
    for ed in args.extra_dir_flat:
        edp = Path(ed)
        if not edp.is_absolute():
            edp = ROOT / edp
        if not edp.exists():
            fail(f"extra-dir-flat 不存在: {edp}")
        for entry in sorted(os.listdir(edp)):
            src = edp / entry
            dst = out / entry
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    # ④ SHA256SUMS（最后重算 —— 顺序铁律）
    sums = write_sha256sums(out)
    # ⑤ zip（再自校验）
    zip_path = out_root / f"KangXiKai-v{version}.zip"
    if args.zip:
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in _iter_pkg_files(out):
                rel = p.relative_to(out).as_posix()
                zf.write(p, arcname=f"{out.name}/{rel}")
        verify_zip(zip_path)

    summary = {
        "release_dir": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
        "zip": str(zip_path.relative_to(ROOT)) if zip_path.is_relative_to(ROOT) else str(zip_path),
        "version": version, "chars": stats["cmap"], "real": stats["real"],
        "provenance_counts": prov_counts,
        "sha256sums_entries": len(sums),
        "zip_selfcheck": "PASS" if args.zip else "skipped",
        "font_sha256": stats["sha256"],
        "zip_sha256": sha256(zip_path) if args.zip and zip_path.exists() else None,
        "build_evidence": stats.get("build_evidence"),
        "license_files": stats.get("license_files"),
        "generated_utc": utc_iso(datetime.datetime.now(datetime.timezone.utc).timestamp()),
    }
    (out_root / "package_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
