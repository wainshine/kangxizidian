# PROJECT-STATE · 项目状态与交接（2026-11-13）

> 新会话读这一页即可知道「现在到哪了、什么是真的、下一步干什么」。细节见：
> `PIPELINE.md`（怎么做）、`WORKFLOW.md`（怎么走流程）、`VERSION-HISTORY.md`（从哪来）、
> `WORK-MAP.md`（work/ 里有什么）、`ERRATA.md`（哪些旧说法作废）、`BACKLOG.md`（唯一待办清单）。

## 0. 三十秒快速开始

- **v2.6.3 正式发布候选**（2026-11-14）：字体 sha **`6dd473b9…`**（**17,006** 字；含新增 釕 U+91D5）已过
  fast_gate **8/8 PASS**；全闸 **12/12 PASS**（内容 0/18 基线 v2.6.2；缺件 19/20 零余量披露；empty_assign 1,172 披露）。
  发布材料：`docs/releases/v2.6.3/{RELEASE,KNOWN-DEBTS,SELF-AUDIT}.md`、`docs/reference/RELEASE-METRICS.md`（含 v2.6.3 列）。
  v2.6.3 = BF-54 基本区 5 字重定位（愈/急/架/紉/釘）+ 旧釘框改标 釕 + BF-06 扫描侧修复（E40：165→19/20）+ T4 证据链。
- 覆盖：基本区 10,268/20,992 = **48.91%**；目标字表 10,268/16,567 = **61.98%**；缺口 **6,299**。
- 闸（候选，现行）：font_qa PASS（同框 0）；字形级框线 **0**；框线逃逸 **0**；内容 **0**（v2.6.2 基线；累计 vs v2.5.8=18 披露）；
  provenance PASS；页几何 bad_boxes **0**、empty_assign **1,172**（披露）；缺件 **19 字/20 组件**（17 prune 判正确 + 3 scan 残差）。
- 构建：mapping `work/lead/mapping_block_v273.jsonl`（v271 + 5 条基本区重定位 + 釕）+ geometry `work/lead/page_geometry.jsonl`
  + 页级线条带（27 rect）+ 自动缓存版本；clean-HEAD 全量重建 398s（10 workers；T1 改动后首跑），cache 命中约 20s。
- 关键口径：只收字头真迹（D15）；2×2 格块；pre-cut 排除版面（D22，strip 已摘除 E29）；参考字体唯一 = 霞鹜文楷 OFL（D21）。
- 未决 owner 决策：**D23 内容判据**（改源墨保真度？）、**00/13 卷是否入字表**、**缺口 6,300 策略（BF-41）**。

## 1. 目标与已确认决策

- 目标：从《康熙字典》康熙五十五年内府刊本扫描件（书格 shuge.org，14 PDF / 3,869 页）重建**只收字头真迹**的楷书字体。
- 字表基准：`work/seq/canonical.jsonl` 正集 42,302 条 / 唯一基本区字 **16,567**（D19 口径；勿与 kx_full 16,791 混用）。
- 决策：`docs/DECISIONS.md` D1–D22 + **D22 更新**（strip 摘除）+ E24–E34 更正；D23 为**提案**，待 owner 确认。
- 字头 = 2×2 小字格块；框面积均匀（块宽 99–103、高 95–100，同页 σ≈0.4px）。

## 2. 当前交付物与真源

| 产物 | 路径 | 状态 |
|---|---|---|
| 当前候选字体 | `work/font/build/KangXiKai-v2.6.3.ttf`（sha `6dd473b9…`，17,006 字） | **fast_gate 8/8 PASS**；全闸 **12/12 PASS**（内容 0/18、缺件 19/20、empty_assign 1,172 均披露） |
| **v2.6.3 正式包（本版）** | `release/KangXiKai-v2.6.3/` + `KangXiKai-v2.6.3.zip` | 2026-11-14 发布；material staging `work/release/v2.6.3`；finalize 结果以包内 `FINALIZE.json` + `release/RELEASE-INVENTORY.tsv` 为准 |
| v2.6.2 正式包（上一版） | `release/KangXiKai-v2.6.2/` + `.zip` | ✅ 2026-11-14 finalize 17/17（font `a8bb87d9…`；内容 35 / 缺件 165 / empty 1,173 / 框线 0 披露） |
| 历史预览包 | `release/_preview/KangXiKai-v2.6.2-preview`（旧证据，b73e9f01 时代） | 已被正式包取代，保留备查 |
| 发布材料 | `README.md`、`LICENSE`、`OFL.txt`、`docs/reference/RELEASE-METRICS.md`、`docs/releases/v2.6.2/KNOWN-DEBTS.md`、`scripts/templates/README-TEMPLATE.md`、`docs/images/` | 2026-11-13 补齐 |
| 构建输入·mapping | `work/lead/mapping_block_v273.jsonl`（17,006 字；v271/v272 留档） | 唯一真源 |
| 构建输入·几何 | `work/lead/page_geometry.jsonl`（E30 扩张版；原版 `page_geometry_v1.jsonl`） | 唯一真源 |
| 构建输入·线条带 | `work/lead/page_line_bands.json`（27 rect，页级数据驱动） | pre-cut 数据 |
| 构建输入·manifest | `work/font/build/manifest_v263.json` | 由 build_stats 生成 |
| 参考字体 | `scripts/reffont.py` → 霞鹜文楷 LXGW WenKai（OFL，不随包分发） | 唯一参考 |
| 闸报告 | `work/lead/fast-gate-v262.json`、`gate-report-v262.json`、`glyph-frame-gate-v262.json`、`page-geometry-gate-v262.json` | 现行 |
| 扫描 | `work/lead/missing_scan_v262.jsonl`（165）、`frame_scan_v262.jsonl`（0） | 带 sidecar 绑定 |
| 分析数据 | `empty-assign-triage-v262.json`、`content-triage-v262.json`、`content-aspect-analysis-v262.json`、`frame43-triage.json`、`missing-32-triage.json` | CS3 输入 |
| 里程碑复核包（第 1 轮） | `work/review/round-003-v262/`（617 变化字/6 类抽样/盲抽 100） | owner 已标注（77 格）→ `review-feedback-v262.json` |
| **修复验证包（第 2 轮）** | `work/review/round-004-v262fix/`（71 个上轮标注字重渲 + 类样本 + 同种子 100） | E37 修复后待 owner 复看 |
| 过程包 | `release/KangXiKai-v2.6.1/`（旧 finalize，按现行闸会 FAIL） | 不签收、不重打（ACCEPT） |
| 重构前基线 | `release/KangXiKai-v2.5.8/`（8 项闸 PASS） | 内容闸基线 |
| 历史版本 | `audit/RELEASE-HISTORY.jsonl` + `audit/release-evidence/` | 52 版元数据 + 4 版闸证据 |

## 3. 已知缺陷（按严重度）

| 级别 | 缺陷 | 现状 / 计划 |
|---|---|---|
| P0·里程碑 | **empty_assign 1,173**：有 quad 无 mapping 行的半版（vol 01–12 **669**，其中 652 有 lattice；vol 00/13 **504**；40 无 lattice）；含 01_0006 L「一」 | CS3：669 个需重跑检测/映射（真迹，不补假字）；00/13 口径待 owner |
| P1·已收口（v2.6.3） | **缺件 165 → 19 字/20 组件**：E40 修复扫描侧 precut fail-open；残余 17 prune_loss（owner 判 prune 删除正确）+ 3 scan 残差，按 known-debt 披露 | BF-06 完成（v2.6.3）；prune-by-design 归类代码留 v2.6.4；不得再按 165/prune 旧口径调参 |
| P0·里程碑 | **内容判据 D23（待 owner）**：content 18（阈值 35）大部分是跨架构归一化差异（E31：旧字形长宽比偏差>15%），非真实缺笔 | 提案改「源墨保真度」（字形投影 vs 自身 source ink 配准 IoU） |
| P0·里程碑 | **v2.6.1 包不可签收**（旧 finalize/材料数字矛盾/混入 v2.6.0 数据） | 不重打；下一候选按新 finalize 出包（BF-04/17/18/24） |
| P0·里程碑 | 硬条件未闭环：隔离 **9 字**（刃/榍/法/紆/総/荹/仟/禦/絞）、**100 字签核**、部界锚点（09–11/13 卷缺）、标签精度敞口（VLM top-1 84.6%, n=13）、DATA 许可细节 | CS4/CS5（BF-29/30/31/32/33） |
| P1 | 高频缺 **23**（一/件/你/內/合/在/多/張/教/樣/氣/法/清/為/王/相/種/臺/與/被/裡/都/間）：16 在目标缺口内，7 不在 canonical 目标表（异体口径） | BF-16/41：与 empty_assign 一并处理；口径需 owner |
| P1 | mapping 生成链未脚本化（数据+证据保留） | BF-19 长期项 |
| P1 | 343 页无 content_quad：**对当前字体 0 影响**（无字形落这些页）；真实缺口是 empty_assign | BF-11 已改写为 empty_assign |
| P1 | 闸契约/材料/归因（BF-10/17/18/44/47/51/49/25/28） | 输出包前必须闭环 |
| P2 | 文档数字清理（DATA/PIPELINE/BACKLOG 仍有旧口径引用）、脚本 keep/archive 判定、研究项 BF-35、GAN 分桶清单 BF-34 | 随轮次清理 |
| ✅ 已解决 | 三闸缺失（BF-01）、同框 2 对（BF-02）、页几何 box 越界 198/360（BF-03/E30）、strip 切后擦（BF-13/E29）、Songti 依赖（BF-14）、字形框线 23→0（E24/E27/E29）、框线逃逸 153→0（E37）、内容 35→18（E31/E37）、缺件 1,200→165（E37 口径变化） | 见 ERRATA E21–E37 |

## 4. 下一步（唯一清单见 `docs/BACKLOG.md` §10）

1. **CS3-A（进行中）**：empty_assign 669 个 vol 01–12 半版补映射（先 01_0006 L「一」）→ 覆盖/缺口重算；00/13 口径待 owner；
2. **CS3-B（v2.6.3）**：缺件 165 已完成构建侧插桩（E40：主因=扫描侧 fail-open，修复后重扫 19/20）→ 剩余 17 prune_loss+5 clean_ink_loss+3 scan 残差待类级修/披露；
3. **D23 owner 决策**：内容判据（源墨保真度）→ 里程碑内容硬条件口径；
4. **CS4/CS5**：高频缺 23、隔离 9、100 字签核、锚点、精度披露、DATA 许可；
5. 以上归零/披露后 → 里程碑严格全闸 → 复核包 → `font_package` → `release_gate finalize` → 冻结。

## 5. 如何独立审计（不信任任何人写下的数字）

```bash
# 1) 字体 QA / 快闸（现行候选预期：QA PASS、fast_gate 8/8 PASS）
.venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-v2.6.2.ttf \
  --manifest work/font/build/manifest_v262.json --outdir /tmp/qa_now
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.2.ttf \
  --manifest work/font/build/manifest_v262.json --version 2.6.2 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json --content-max-damaged 35 --tag v262
# 2) 全闸（复用已绑定扫描；缺基线参数即 FAIL）
.venv/bin/python scripts/release_gate.py --version 2.6.2 \
  --font work/font/build/KangXiKai-v2.6.2.ttf --manifest work/font/build/manifest_v262.json \
  --prev work/font/build/KangXiKai-v2.5.8.ttf --prev-manifest work/font/build/manifest_v258.json \
  --scan --reuse-missing work/lead/missing_scan_v262.jsonl \
  --frame-scan --reuse-frame work/lead/frame_scan_v262.jsonl --content-max-damaged 35 --tag v262
# 3) 数字核对：content 18 / glyph 0 / missing 165 / frame 0 / bad_boxes 0 / empty_assign 1,173
```

- 所有闸输出含输入绑定 sidecar（`<out>.sha256`：font/manifest/mapping/geometry/bands/reffont/脚本 sha + git）；
  复用前必须校验，失败 fail-closed。
- 缓存键 = 算法 sha8 + geometry sha12 + bands sha12；换任一项即全量重建（约 10m30s）。

## 6. 明确接受（不修）

- `docs/_history/` 历史文档内部旧引用不改写；v2.6.1 旧包不重打；历史 release 数字不回溯重算；审计报告保留原文（只追加状态）。
- 内容闸与 v2.5.8 的差异（E31）不再逐字追平——改为 D23 源墨保真度判据（待 owner）。

## 7. 常见坑

见 `AGENTS.md` §6（框线切后擦、restore/overlay、闸盲区、单字补丁、管道吞退出码、未提交打包、finalize 后改包、扫描复用、旧口径数字不可比、会话失忆）。
