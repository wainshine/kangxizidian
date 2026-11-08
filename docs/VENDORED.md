# 从 guangeti 复制的代码清单

> 来源仓库：`/Users/wainshine/newAI/guangeti`
> 上游版本：A v1.7.2 / B v1.2.4 / C v1.2.0
> **原则**：复制后各自演进，不跨目录 import；上游修 bug 时按 diff 手动移植。
> 上游 commit（2026-11-08 实测）：`ef6e3f8`（2026-11-05）

## 状态（2026-11-08）

C 流（字体构建链 v0）**已复制/移植** 3 个上游脚本的逻辑（非逐字复制文件，而是把
`06_norm.py`+`glyphvec.py` / `fontbuild.py` / `13_qa.py`+`71_holes.py` 的逻辑
重写进本项目 3 个新脚本，去掉 guangeti 的「写本」术语，改成刻本口径）。
其余脚本（选优/配对/训练/标点/打包）**仍未复制**——等 T3/T4 开工时再逐个复制、逐个填。

| 文件 | 来源 commit | 复制日期 | 本项目的改动 |
|---|---|---|---|
| `scripts/font_norm.py` | `ef6e3f8`（源：`scripts/06_norm.py` + `scripts/glyphvec.py`） | 2026-11-08 | 只移植「灰度→二值化→potrace→EM 归一化」链路与 potrace 参数（`turdsize=2 / alphamax=1.0 / opticurve`）；**重写清洗**（`clean_ink` v12：贴边剔除 / 实心并集 bbox / 字身框 gate，针对刻本版框线与邻字注文），新增「PDF 300dpi 直渲染 + 自适应 pad」`render_pdf_crop`/`vectorize_box`；归一化改为统一「最长边 760 units」字面框（不用 guangeti 的 base 字体 bbox 混合，因为本项目暂无 `data/base/`） |
| `scripts/font_build.py` | `ef6e3f8`（源：`scripts/fontbuild.py` + `scripts/07_build_real.py`） | 2026-11-08 | 家族名 `KangXi Kai` / VERSION 0.1.0 / EM 1000 / achVendID `KXKF`；**保留** `_orient` 的「曲线上采样点判嵌套」审计 P0 修复、`Cu2QuPen(max_err=1.0)`、`recalcTimestamp=False`、`SOURCE_DATE_EPOCH` 固定时间戳；新增双 CLI `--mapping`（全量 mapping.jsonl，断点续跑 cache）/`--manifest`（{char,crop_png}）/`--glyphs`（预归一化），三路共用同一 `build_font`；不映射不存在的字、不 fill |
| `scripts/font_qa.py` | `ef6e3f8`（源：`scripts/13_qa.py` + `scripts/71_holes.py`） | 2026-11-08 | 覆盖断言从「基本区 20,992 全覆盖」改为「`cmap == manifest 字表`」（demo 语义：不假覆盖）；保留空字形/tiny/huge/fontRevision 闸与 contact sheet；孔洞审计保留「对照基准字体、只报告不硬判」的思路，基准从文楷换成系统宋体（TC Regular），只统计 lost/fewer；新增 256px 渲染粗检（墨量/连通分量）与 head 时间戳记录 |
| `scripts/font_curate.py` | — （本项目原创） | 2026-11-08 | 印刷品字头策展：PDF 300dpi crop、候选标签汇总（dp_alignment/dp_alignment2/t2_review_ids/OCR）、目检 contact sheet（read/cards/verify）、部首+画数先验候选（Unihan kRSUnicode）、verdicts→manifest。**非上游代码** |
| `scripts/font_specimen.py` | — （本项目原创） | 2026-11-08 | 用构建出的 TTF 自渲染样张（96px/48px） | 

## 未复制（计划清单，T3/T4 时填）

| 文件 | 用途 | 状态 |
|---|---|---|
| `scripts/punct_set.py` | 标点/数字/空格字集（20,992 + 42 = 21,034 唯一定义源） | 未复制 |
| `scripts/13_extend_punct.py` | 补标点/数字/空格 | 未复制 |
| `scripts/14_package.py` | 打包 + provenance + stats + SHA256SUMS（**保持 SHA256SUMS 最后重算**） | 未复制 |
| `scripts/08_make_pairs.py` | 造训练对（文楷→目标，S=256） | 未复制 |
| `scripts/21_train_gan.py` | zi2zi-GAN（U-Net + PatchGAN + hinge；必须移植已知坑修复） | 未复制 |
| `scripts/83_verify_ab_c.py` | 跨产物一致性闸（改单线版） | 未复制 |
| `scripts/95_compare_lines.py`、`98_style_sheet.py` | 视觉对照图（改「真迹/GAN/回退/文楷」四行） | 未复制 |

## 外部依赖（非代码复制）

| 依赖 | 版本 | 装在哪 | 说明 |
|---|---|---|---|
| `potracer` | 0.0.4 | `work/font/_pylibs`（`--no-deps`） | 纯 Python potrace，与 guangeti 同款；**不污染 `.venv`** |
| `fonttools` | 4.68.0 | `work/font/_pylibs`（`--no-deps`） | 组字体；`--no-deps` 避免 numpy 覆盖 `.venv` 版本（cv2 ABI） |

## 外部思想来源（未复制代码）

| 来源 | 许可 | 用在哪 | 记录 |
|---|---|---|---|
| [vModou 兀雨墨斗](https://github.com/shanleiguang/vModou)（shanleiguang，2025） | MIT | 版面纠偏思路：版框四角顶点 → 拉正。本项目用 Python 重实现为自动化步骤（强横线端点定角 + 透视变换），未复制其 Perl 代码 | `scripts/t0_rectify.py`，2026-11-07；效果见 `docs/PROBE.md` §7 |

**复制命令示例**（T3/T4 开工时执行）

```bash
cd /Users/wainshine/newAI/kangxizidian
mkdir -p scripts
cp ../guangeti/scripts/{punct_set.py,13_extend_punct.py,14_package.py,08_make_pairs.py} scripts/
git -C ../guangeti rev-parse --short HEAD   # ef6e3f8（2026-11-08 实测）
```
