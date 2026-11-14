# BACKLOG · 待修复清单（v2.6.1 之后，2026-11-12）

> 本文是**唯一待修复清单**：来源 = 第 3 代两份审计（GLM/DSH）+ 已知债 + 流程缺口。
> 规则：每项写清「证据 / 修法 / 验收 / 轮次」；修复后改状态为 ✅ 并注明 commit/证据，不删除记录。
> 状态：`P0` 阻塞发布 / `P1` 下一轮必修 / `P2` 可随轮次修 / `ACCEPT` 明确接受不修。

## 0. 总览（2026-11-13 梳理后）

| 口径 | 数量 | 说明 |
|---|---|---|
| 条目总数 | **60**（BF-01…BF-61；BF-52 未使用） | 逐条状态见各表 |
| 已完成 | **21** | BF-01/02/03/07/08/09/12/13/14/20/22/37/43/45/46/48/50/53/57/58/59 |
| 未完成 | **39** | 分类与顺序见 **§10**（2026-11-13 梳理） |
| 里程碑阻塞/硬条件 | 11 | BF-04/05/06/11/16/29/30/31/32/33/41（多需 owner 决策或数据动作） |
| v2.7.0 生成方案 | 2 | BF-55（GAN）、BF-56（带状扫掠回退） |
| 闸/流程/材料（可执行） | 23 | BF-10/15/17/18/19/21/24/25/26/27/28/34/36/38/39/40/42/44/47/49/51/54/60 |
| 暂缓/研究 | 2 | BF-23（LRU 计时）、BF-35（旧方法 A/B） |
| ACCEPT（不修） | 4 | 历史文档不改写、v2.6.1 旧包不重打、历史数字不回溯、审计报告保留原文 |

> 第 3 代审计（86 条 findings）逐条状态：`work/lead/audit3-findings-map.jsonl`；
> 2026-11-13 已把因 E24–E34 落地而解决的 findings 更新为 fixed/covered（见 §10-C）。
> 本表是**唯一待办清单**；旧汇总里的 35/35、153/153、1,200、343 页影响 238 字等数字已失效，见 §10-C。

## 1. 轮次与门

| 轮次 | 目标 | 验收 |
|---|---|---|
| **CS1（门禁基建 + 重建）** | 重建候选；补齐三闸；闸契约 fail-closed；扫描-字体绑定；材料数字对账 | 新候选过 `fast_gate` + `full_gate`；闸不再可空转；重建 sha/耗时/数字落盘 |
| **CS1.5（映射/坐标修正）** | 同框 2 对、mapping∩quad 坐标系、360 字越界 | 同框=0；mapping box 全在 content 内；内容/缺件/框线数字重测 |
| **CS2（页级几何）** | 343 页无 quad、184 半版兜底、框线逃逸 | 框线逃逸（字形级）→0；页级几何校验 PASS |
| **CS3（mapping 指派）** | 内容闸 35（含 15 字 IoU<0.3）→0；缺件邻字隔离 | 内容闸 0；缺件扫描口径修正后重测并定阈值 |
| **CS4（缺口/口径）** | 缺件 1,200 triage；高频缺 23 口径核对；隔离 9 | 已知债清单冻结并披露 |
| **CS5（签核/材料）** | 100 字签核；09–11/13 卷锚点；DATA 来源/许可；字体公式 | owner 签核完成；里程碑条件满足 |

## 2. P0（阻塞发布）

| ID | 问题 | 证据 | 修法 | 验收 | 轮次 |
|---|---|---|---|---|---|
| BF-01 | **三闸缺失**：字形级框线闸 / provenance 无拷贝闸 / 页级几何闸 | 审计 DSH P0-3 | 已建三闸并接入快/全闸：`glyph_frame_gate`（TTF 输出字形扫细长直线，只用线段几何，不数孔洞 D21）、`provenance_gate`（manifest/mapping/stats 自洽 + 无拷贝标记）、`page_geometry_gate`（quad 覆盖/box 用 M 变换进旋转空间/空指派/块∩quad） | ✅ **完成（2026-11-12）**：三闸可 FAIL；glyph_frame_gate 抓住 v2.6.0 的 勤 等 10 字；v2.6.2 候选 23 字（同 v2.6.2；v2.5.8 19），见 `glyph-frame-gate-v26x.json`；检查 `work/lead/gate-*` | CS1 |
| BF-02 | **同框冲突 2 对**：沓/𦧟（08_0319 R）、䛱/忠（10_0081 R） | 修复后的 font_qa 实测 2 对；审计 DSH P0-5 | 类级规则 `scripts/oneoff/fix_mapping_sameblock.py`：同块多字保留 verified ink box 面积最大者，其余删除并写 residual（沓/忠 为片段框误标，转缺口待 CS3 重定位）；禁止改字形绕过 | ✅ **完成（2026-11-12）**：font_qa 同框=0 PASS；新字体 17,005 字（E23）；`sameblock-fix-report.json` | CS1.5 |
| BF-03 | **页几何残差**：box 越界 198@1px/360@0、max 8.8px | 已复核为 quad 偏紧非坐标错；E30 用 quad 扩张覆盖全部 box 修复 | `scripts/oneoff/expand_quads_to_cover_boxes.py`（只扩不缩，+0.5px） | ✅ **完成（2026-11-13，E30）**：bad_boxes 198→0、零容差 360→0、max overflow 0；内容 34→32 | CS2 |
| BF-04 | **v2.6.1 包不可签收**：旧 finalize（zip 内报告/SHA 旧）、包内 README 数字矛盾（60/700 vs 153/1200）、review tsv 混入 v2.6.0 数据 | 审计 DSH P0-2/P1；本次核对确认 | 不重打 v2.6.1；下一候选重建后按新 finalize 顺序出包；材料由同一数据源生成 | 新包 zip==目录、SHA 覆盖报告、材料数字与 gate-report 一致 | CS1 |
| BF-05 | **内容闸 34→32**；32 字归因为跨架构归一化差异（E31：12/32 旧字形长宽比偏差>15%，非真实缺笔） | `content-aspect-analysis-v262.json` / `content-triage-v262.json` | 提案 **D23**：内容判据改「源墨保真度」（字形 vs 自身 source ink 配准 IoU）；旧字体 delta 只作回归告警 | 里程碑内容判据经 owner 确认 + 源墨保真度基线披露 | CS3 |
| BF-06 | **缺件扫描 165**（E37 后；旧 32/827/1,200 不可比）。**T1 已定位根因**：扫描侧 `precut_masks` crossing 过滤 fail-open（模块级未 import numpy + `except:pass`）→ 扫描比构建多删墨 → E36 配准错位（E40）；audit4 DATA-402 证伪的「prune 边缘清理」仅解释残余子集 | `work/lead/v263-T1-BF06-report.md`、`missing_scan_v263-clean.jsonl`（19 字/20 组件，clean-HEAD 重扫）、`missing-19-v263-stage-attribution.jsonl`、`missing_scan_v263-t1fix.jsonl` | **v2.6.3 已完成**：扫描侧修复（np 导入 + fail-closed）入版，全库重扫 **165→19 字/20 组件**（error 0，unknown=0）；残余 17 prune_loss（owner 判 prune 删除正确=边角料，按 prune-by-design 披露）+ 3 scan 残差（㓚、譵×2）→ known-debt；**不得再按「165/prune 边缘口径」调参**；prune-by-design 归类代码留 v2.6.4 | 构建侧插桩 unknown=0 已达成；残余组件逐类归因/披露；新字体重扫 19/20（下降）；content 0（v2.6.2 基线）/glyph_frame=0/frame=0 | v2.6.3 完成（残余披露）；v2.6.4 prune-by-design 归类 |
| BF-07 | **框线逃逸/字形级框线** | 字形级 23→0（E27）；源图级 1 仍在（㨜 3px 界行残边 known debt） | 页级 pre-cut mask + 页级已验证线条带（`work/lead/page_line_bands.json`，数据驱动） | ✅ **完成（2026-11-13）**：glyph_frame_gate 0 PASS；源图口径待重扫后披露 | CS2 |
| BF-08 | **缓存/几何修复后首次全量重建候选** | 本轮修了 cache key/几何路径；旧字体是旧 key 产物 | 全量重建（0 命中）→ v2.6.2；回退实验后 v2.6.2 候选 | ✅ **完成（2026-11-12）**：v2.6.2 全量 6m42s（sha `58fd9235…`）；缓存命中重建（3m52s）sha 一致 —— 可复现；数字见 `fast-gate-v264.json` | CS1 |
| BF-09 | **构建失败静默**：单字失败仅 WARN，仍 exit 0 | 审计 GLM P1/DSH | 硬失败：任何 skipped（除 `--limit`）→ 写失败报告（`aborted/failed_n/failed`）并 exit≠0；`--allow-partial` 才放行 | ✅ **完成（2026-11-12）**：注入坏 box → `ABORT: 1 字构建失败` + `/tmp/bad.build_stats.json`，exit 1 | CS1 |

## 3. P1

| ID | 问题 | 证据 | 修法 | 验收 | 轮次 |
|---|---|---|---|---|---|
| BF-10 | **闸契约仍可被绕过**：可选闸省略即 PASS；阈值=观测值（35/35、153/153、1200/1200）零余量；`doc_check` 不做数字对账 | 审计 GLM/DSH P1 | 候选/里程碑强制 full gate；阈值模式要求记录「上一版数字+delta」，零余量必须披露；doc_check 校验 README/QA 数字与 gate-report 一致 | 缺项即 FAIL；数字不一致即 FAIL | CS1 |
| BF-11 | **有 quad 但 0 指派的半版 1,173**（原条目「343 页无 quad/影响 238 字」已失效：`missing_quad_chars=0`，无字形落无 quad 页） | `page-geometry-gate-v262.json`、`empty-assign-triage-v262.json` | 668 个 vol 01–12 半版重跑检测/映射（含 01_0006 L「一」）；504 个 vol 00/13 口径待 owner；40 无 lattice 半版待核 | empty_assign→0 或经 owner 同意的披露；覆盖/缺口重算 | CS3 |
| BF-12 | **扫描结果未绑定字体 SHA**（早期扫描早于字体；reuse 无校验） | 审计 DSH P1 | 新增 `gate_binding.py`：扫描/内容输出旁写 `<out>.sha256`（font/manifest/mapping/geometry/参考字体/脚本 sha + argv + git）；快闸/全闸复用前校验，缺失或不匹配 → FAIL | ✅ **完成（2026-11-12）**：`validate_reuse` 单测（换字体→不通过）；内容/缺件/框线闸均已接入 | CS1 |
| BF-13 | **页级几何与 pre-cut 不变量冲突**：主链仍调 `strip_border_lines`（形状删线） | 200 字 A/B（`strip-border-ab-v4.json`）；E29 全量 A/B：strip 关→12 处框线→并入页级线条带（26 rect）后 glyph_frame=0、内容 0 回归 | 按 D22 原定路径：pre-cut 达标后摘除 strip，`FONT_STRIP_BORDER` 仅留复现口 | ✅ **完成（2026-11-13，E29/D22）**：strip 默认关闭；候选 sha `f901c9d4…`；fast_gate 8/8 PASS | CS2 |
| BF-14 | **Songti 专有字体依赖** | 审计 E8；2026-11-12 全管线替换完成 | 新增 `scripts/reffont.py`（唯一参考字体：霞鹜文楷 OFL）并替换 font_qa/refgate/refgate2/scan_distort/fidelity_eval/scan_missing_parts/font_norm/review_sheet/owner_defect_sheet + 3 个 legacy 标注脚本；font_qa 孔洞对照删除（D21） | 构建/闸/报告脚本无 Songti/Hiragino 依赖 | ✅ 完成（2026-11-12） |
| BF-15 | **fontRevision 公式 v2.10+ 崩坏**（4 处同错） | 审计 GLM P1-6 | 统一共享函数 `major + minor/100 + patch/10000`；下一版本重盖章 | 用 v2.10 假设单测通过；闸与构建同源 | 下一候选 |
| BF-16 | **高频缺 23**：一/件/你/內/合/在/多/張/教/樣/氣/法/清/為/王/相/種/臺/與/被/裡/都/間（**16 在目标缺口**，7 不在 canonical 目标表=异体口径） | 2026-11-13 复核 `work/lead/high_freq_gap.json`（285 常用表，23 缺） | 与 empty_assign 一起重定位（真迹优先，禁止补假字）；7 字异体口径需 owner 确认是否映射 | 23 字全部有结论（入字体/异体映射/披露） | CS3/CS4 |
| BF-17 | **包材料数字同源**：README/QA/coverage 由不同手写模板产生 | 审计 DSH P1（60/700 vs 153/1200） | 材料模板从 gate-report/coverage JSON 生成；禁止手写数字 | 机器生成、doc_check 校验 | CS1 |
| BF-18 | **changesets/version-artifacts 三件套未强制** | 审计 GLM P1-1；本轮已补 v2.6.1 回溯文件 | release_gate finalize 检查三件套存在（新版本必须有 cs-\* + version-artifacts） | 缺失即 FAIL | CS1 |
| BF-19 | **mapping 生成链未脚本化**（仅数据+碎片脚本） | SCRIPTS/PROJECT-STATE 已知债 | 长期：用 charalign 脚本重建成可复现链；短期保留全部 map JSON 证据 | 能从 canonical + 扫描件重跑出 mapping（报告一致性） | 长期 |
| BF-20 | **fast_gate char_diff 不拦截 removed**（release_gate 有一致性检查） | 审计 GLM P2-8 | fast_gate 增加 quarantine 对账；removed>0 且不在隔离清单 → FAIL | ✅ **完成（2026-11-12~13）**：fast_gate `char_diff` 步已拦截；v2.6.2 的 沓/忠 声明在 `v262_sameblock_residual.json`，未声明 removed 即 FAIL（实测生效） | CS1 |
| BF-43 | **禁止能力仍可触达**：主链保留 restore/overlay 整字拷贝代码路径与缓存 `__overlay__` 分支 | 审计 BUILD-07/DOCS-10 | 删除主链 overlay 分支/`--repair-overlay`/`--src-map`/`contours_override` 读取；构建遇 dict 轮廓即报错；`scripts/oneoff/make_repair_overlay.py` 停用 | ✅ **完成（2026-11-12）**：注入 `__overlay__` 字形 → RuntimeError exit 1；overlay 生成器 exit 1 | CS1 |
| BF-45 | **clean-tree/freshness 闸可绕过**：`--allow-dirty` 全绕过、被 gitignore 的构建输入不进 provenance | 审计 GATE-13 | finalize 前置 `clean_tree` 步（脏树 FAIL，`--allow-dirty` 仅调试且记录）；输入 sha 进 gate-report `inputs` | ✅ **完成（2026-11-12）**：临时包副本跑全闸 → `FAIL clean_tree`（dirty=true）且 `package_touched=false` | CS1 |
| BF-61 | **make_block_mapping 坐标系混用（BUILD-404，audit4）**：`block_for_box` 用原图 150dpi 坐标、`q["box"]` 用旋转空间坐标，两者直接求交；模拟重跑 **999/17,005** 字 box 改写（max 7px）、**192** 字重新越出 quad（当前 bad_boxes=0 是 E30 事后扩 quad 的结果，生成器未修） | `audit/AUDIT4-FINDINGS-v2.6.2.jsonl` BUILD-404；`scripts/make_block_mapping.py:63-90`；`page_frames.py:157-158` | 统一 M/Minv 坐标系求交 + L0 断言 box⊆quad=0 + dry-run 对比（预期 999 改动/192 越界） | 重跑模拟：非预期改动=0、越界=0；**任何 mapping 全量重生成（含 empty_assign 669）以本项修复为前置** | v2.6.4（v2.6.3 禁止全量重生成） |

## 4. P2

| ID | 问题 | 修法 | 轮次 |
|---|---|---|---|
| BF-21 | coverage JSON 字段命名含混（`basic_coverage_pct` 实为目标表口径） | 改名/加注（`target_set_coverage_pct`），旧字段保留一版 | 材料 |
| BF-22 | 缓存命中重建耗时（审计测得 242–251s） | 几何路径已修，重建后实测；更新 PIPELINE/AGENTS 的 ~20s 声明 | ✅ **完成（2026-11-12）**：全量 402s、缓存命中 232s（装配占大头）；文档已更正（ERRATA E22） | CS1 验证 |
| BF-23 | fidelity LRU 缓存效果未测 | 扫描重复运行计时对比 | 暂缓（非关键路径；当前瓶颈是扫描页级 mask 计算，见 E34） |
| BF-24 | 包内 `01-changes.tsv` 混入 v2.6.0 的框线 60 条数据 | 下一版由当前扫描结果重新生成 | CS1 |
| BF-25 | **文档一致性清理批次**：15 条已删除路径/占位符引用、DATA.md 残留 v2.4.5 段、docs 索引/规模漂移、12 vs 14 PDF 口径、扫描耗时矛盾、NFC/NFD sha 说明、.gitignore 许可文本规则、`release/_withdrawn` 引用、PIPELINE content clip 时序描述 | 审计 DOCS-14/15/16/18/20/21/23/24/28、DATA-13/14/16、BUILD-13 | 过期段删除或标「已过期/时点」；路径改现行；数字按现行口径重写；.gitignore 规则顺序修正 | docs 无过期数字/死路径；索引与文件一致 | 文档/CS1 |
| BF-26 | GLM 审计报告仅存在于对话 | 归档为 `audit/AUDIT-REPORT-v2.6.1-audit3-GLM.md` | 文档 |
| BF-27 | audit triage 与 backlog 的同步靠人工 | 每轮结束自动从 findings jsonl 生成 backlog 摘要（脚本） | 流程 |
| BF-28 | release 清单中 v2.6.1 状态未标「不可签收」 | 更新 RELEASE-INVENTORY/README 状态列 | 文档 |
| BF-44 | **闸/构建归因不可复现**：gate-report 无输入 sha/命令行/git commit；build_recipe 算法 sha 与记录的 commit/tag 不符；jobrun 不记命令行与日志 | 审计 GATE-09/12/21、DATA-06、DOCS-08 | gate-report 记录 font/manifest/扫描输入 sha + argv + git commit；build_recipe 的算法 sha 与构建 commit 同源；jobrun 落命令行与日志路径 | 同命令可从报告复现；归因字段齐全 | CS1 |
| BF-46 | **内容闸吞样**：异常字不计 damaged，覆盖下限 98% 可静默漏约 340 字 | 审计 GATE-17 | 覆盖率要求 100%：`n_ok != len(chars)` 或存在 error 行 → exit 2（不再按 98% 静默漏样）；error 单列 | ✅ **完成（2026-11-12）**：v2.6.1 全量 17,007/17,007 通过覆盖检查 | CS3 |
| BF-47 | **audit/ 顶层「现行」文档阶段过期且互相矛盾**：SELF-AUDIT/README 时点缺失，`_history/README` 把归档标现行 | 审计 DOCS-07/13/26 | 每份标 status/时点/被替代关系；过期移入 `_history/`；索引同步 | 顶层文档与索引一致、无过期结论当现行 | CS1 |
| BF-48 | **构建入口/边界缺陷与缓存卫生**：`--manifest` 入口未定义；仓库外路径写 stats 崩溃；测试条目污染生产缓存 | 审计 BUILD-09/10/11、DATA-15 | 实现 `load_from_manifest_jsonl`（复用 mapping 主链）；`_rel_path` 容错；缓存按 `_CACHE_VER` 分子目录（旧 flat 目录不再读取），stats 增 `cache` 计数 | ✅ **完成（2026-11-12）**：三入口均可跑；缓存目录 `b7441e3f…`/`fbe518ed…` 各 2 文件（limit 测试）；旧 flat 的甲/乙/丙不再被读取，待清理（不影响新构建） | CS1 |
| BF-49 | **scripts/ 保留判定缺失**：4 个已宣布归档的「切后擦线」死脚本仍在现行目录且可互 import；14 个脚本无调用方无判定 | 审计 DOCS-12/27 | 每脚本标 keep/archive（README 清单）；死脚本移 `scripts/_archive/` 或加 guard；主链不得 import | 现行 scripts 无未标注/不可判定脚本 | CS2 |
| BF-50 | **worker 上限未强制**：`--workers`/`FONT_BUILD_WORKERS` 无 clamp（999 可绕过 ≤10） | 审计 BUILD-05 | `clamp_workers`：`--workers`/env 都 clamp ≤10 并告警 | ✅ **完成（2026-11-12）**：`clamp_workers(999)` → 10 + WARN | CS1 |
| BF-54 | **标签错配（owner 复核 X 类）**：11 字「字与 Unicode 不对应」；经三轮候选复核，按 **Unicode 基本汉字区**范围处理 | `work/lead/review-feedback-v263-bf54.json`；`mapping_block_v273.jsonl`；`mapping_v273_summary.json`；round-005 | **v2.6.3 已完成基本区 5 字**：愈/急/架/紉/釘 行级重定位（canonical 邻字定位，owner 逐字确认）；旧釘框改标 **釕 U+91D5**（+1 字）；扩展区 6 字（䬩/䃧/𣟴/𧂁/𧔁/𧖤）按 owner 2026-11-14 决定本轮 defer（不补假字）；精确轮廓 diff changed 5/added 1/removed 0 | 基本区 5 字重定位 + 釕；扩展区 defer 披露；round-005 通过 | v2.6.3 完成（基本区）；扩展区 v2.6.4+ |
| BF-53 | **框内残线**：剩余 14 字细线在检测块框内；单字层 ROI 路线已两次失败（E25/E26） | E24–E27 实验 | 页级已验证线条带方案：残线反算页坐标 rect（`page_line_bands.json`），并入 pre-cut mask；页级作用域、数据驱动 | ✅ **完成（2026-11-13）**：glyph_frame 14→0；内容闸（上候选→本候选）0 damaged；fast_gate 8/8 PASS | CS2 |
| BF-51 | **构建降级路径无标记**：geometry/quad/lattice 异常只打日志继续，可在无 content clip/块掩膜下完成构建 | 审计 BUILD-08 | 降级次数/类型写 stats 并进闸；超阈值 FAIL | 人为降级 → stats 可见且闸失败 | CS2 |

## 5. 非审计遗留（历史欠账，2026-11-12 补录）

> 说明：这些不是第 3 代审计新发现，而是项目长期挂账的已知项。其中 3 项是**里程碑硬条件**（签核/锚点/标签精度），不能当 P2 拖到发布前才处理。

| ID | 问题 | 证据/来源 | 修法 | 验收 | 轮次 |
|---|---|---|---|---|---|
| BF-29 | **隔离 9 字**未处置：刃/榍/法/紆/総/荹/仟/禦/絞 | PROJECT-STATE/PIPELINE；释放包隔离清单 | 逐字重定位或定案隔离；发布时点名披露 | 9 字全部有结论（入字体/隔离+理由），随包清单 | CS5 |
| BF-30 | **100 字 owner provenance 签核未闭环** | PROJECT-STATE；PLAN-v2.6 §3.1（历史计划） | 生成 100 字核验表（已有 `owner_review_*` 脚本），owner 标 ✓/✗/?；✗ 修复或隔离 | 100 字全部有结论 + owner 签核记录随包 | CS5（里程碑硬条件） |
| BF-31 | **部界锚点口径不可全信**：39/39 系循环论证；09–11/13 卷锚点缺失 | SCRIPTS §8-3；PROJECT-STATE | 严格版锚点重校验（`validate_anchors3` 思路，禁止块内取墨再判块内）；补 4 卷锚点 | 严格校验 PASS；锚点作为 mapping 回归基线 | CS2/CS5 |
| BF-32 | **标签精度敞口**：VLM top-1 84.6%（n=13，宽 CI）→ 约 1,400–1,500 字级风险 | OCR-OPTIONS/历史记录；PROVENANCE 精度说明 | 独立抽样验证（扩大 n，按卷/部首分层）；高风险字进隔离或复核 | 抽样报告落盘；敞口区间更新并披露 | CS5（里程碑硬条件） |
| BF-33 | **DATA 源扫描件来源/许可信息**（渠道已确认=书格 shuge.org；影印出版者/扫描者/条款细节待补） | owner 2026-11-12 确认渠道；docs/DATA.md §1 已写 | 补影印出版/扫描者信息与站点条款；进包 PROVENANCE | DATA §1 完整；许可声明可追溯 | CS5/材料（部分完成） |
| BF-34 | **D19 缺口分桶清单旧口径**：`v245_gan_targets.json`=6,214 vs 当前缺口 **6,300** | SCRIPTS §8-5 | 若仍采用 D19 分桶策略，用 `scripts/provenance/lead_gan_targets.py` 重生成 | 清单与当前缺口一致，随包 | P2（策略相关） |
| BF-35 | **SCRIPTS §8 的 6 处旧方法 A/B 未做** | SCRIPTS §8/§7.3 | 暂缓：方法与现架构（pre-cut/源码 bbox 归一）无关；如恢复研究再排期 | 决策记录（DECISIONS 追加） | P2（研究，暂缓） |
| BF-36 | **代码-文档不一致**：`detect_blocks` docstring「留边≥4%」实现未设阈值 | SCRIPTS §8-1 | 改代码实现阈值或改 docstring；不得留双口径 | 文档=行为 | P2 |
| BF-37 | **复核包脚本化**：已简化为 3 件（`01-changes` / `02-random100` / `ledger.tsv`），`scripts/make_round_pack.py` 一条命令生成；其余图按需 | WORKFLOW §6；`work/review/round-002/` | 保持 3 件不膨胀 | 任一轮一条命令生成 3 件 | ✅ 完成（2026-11-12） |
| BF-38 | **术语检查器缺失**（GLOSSARY 未落地为检查；版本命名/禁用词） | PROJECT-AUDIT §4；馆阁体对照 | `check_terms.py`（计划新增，BF-38）：检查 docs/代码/包内文档禁用词与命名；接进快闸 | 检查器存在且 0 违规（或白名单） | P1（流程） |
| BF-39 | **里程碑治理未机器化**：无「里程碑条件文件」，release_gate 不校验收否满足 | WORKFLOW §7 | 增加 `milestone.json`（P0 清零/已知债冻结/owner 签核/结构冻结）+ gate 校验 | 缺 milestone.json 或条件不满足 → 拒发正式包 | P1（流程） |
| BF-40 | **lsb/归一化口径历史差异未声明**：v2.5.6 曾 974 字 lsb 重算；当前由轮廓决定（PIPELINE §S3 已改为现行口径说明，BUILD-12） | SCRIPTS §8bis | 核对当前构建 lsb 分布并写入 QA 基线；文书已完成 | 抽样验证 + QA 记录 | P2 |
| BF-41 | **缺口 6,300 的处理策略未定**：headword-only 不补假字 vs D19 重定位/GAN 目标 | DECISIONS D19；PROJECT-STATE | owner 决定是否/如何补缺口；若做，先定验收与许可 | 策略记录（DECISIONS 追加） | P1（策略，待 owner） |
| BF-42 | **候选版本流程三件套的自动化**（与 BF-18 代码检查配套）：目前手工写 cs/version-artifacts | WORKFLOW §10bis | 提供 `new_candidate.py` 模板生成三件套骨架 | 新版本三件套由工具生成 | P2（流程） |

## 6. 合并说明（历史遗留 → 已有条目）

以下历史遗留此前已并入审计条目，不再重复：343 页无 quad（BF-11）、Songti 依赖（BF-14）、高频缺 23 口径（BF-16）、mapping 生成链（BF-19）、物料/文档类（BF-25/26/28）。

## 7. ACCEPT（明确接受，不修）

| 项 | 理由 |
|---|---|
| `docs/_history/` 历史文档内部旧引用 | 约定「历史不改写」 |
| v2.6.1 旧包不重打包 | 已被 v2.6.2 候选替代；重打会改历史 SHA |
| 历史 release 旧口径数字不回溯重算 | 记录在 ERRATA E3；只保证新数字来源 |
| 审计报告/回应保留原文 | 只追加后续落实状态 |

## 8. 建议执行顺序与工作量（估算）

0. **CS0（度量与依据层）✅ 2026-11-12**：D21 参考字体唯一化（霞鹜文楷 OFL，`scripts/reffont.py`）、font_qa 删除孔洞/连通分量判据、QA 重跑 v2.6.1（仅同框 2 对 FAIL）；记录 `work/changesets/cs-20261112-refqa.json`；
1. **CS1-A（先决条件，不重建）**：①BF-12 扫描 sidecar 绑定（font/geometry/mapping/参考字体/脚本五个 sha；否则换参考字体后会误复用旧扫描结果）→ 重扫缺件（参考字体变化）与框线（几何/字体变化）；1,200 标注为宋体参考口径历史值，153 待重建后复测；②闸契约 BF-09/10/17/18/20/46 + 归因 BF-44 + clean-tree BF-45 + worker BF-50 + 构建入口 BF-48；③三闸 BF-01 代码（字形级框线/无拷贝 provenance/页级几何）；④BF-13 先用 200 字样本量化 strip_border_lines 影响，再决定摘除方式 → 1–1.5 天；
2. **CS1-B（一次性字形变更 + 全量重建）**：按 CS1-A 结论摘除主链「切后擦」残留（BF-13）+ overlay 代码移除（BF-43）→ 新 cache key 全量重建（BF-08/22）→ 候选 cYYYYMMDD-1；跑快闸/全闸得诚实基线（预计仍因同框 2 对 FAIL，属 mapping，CS1.5 修）→ 0.5 天；
3. **CS1.5（映射/坐标）**：BF-02 同框 + BF-03 box∩quad → 回写 mapping → 增量重建 → fast_gate PASS 候选 + BF-04 新包 → 0.5 天；
4. **CS2（pre-cut/页级几何）**：BF-11 343 页/184 半版 + BF-07 框线 → 全量重建 → glyph_frame_gate 归零验证；附带 BF-40/49/51/36；
5. **CS3**：BF-05 内容 35→0 + BF-06 缺件（构建侧插桩，E39）；
6. **CS4/CS5**：BF-16/BF-15 + 历史硬条件 BF-29/30/31/32/33 + 流程 BF-38/39 + 策略 BF-41/42 → 1–2 天。

> 合计未完成 **39 条**（见 §0 与 §10）。当前发布候选 sha `a8bb87d9…`（17,005 字）：fast_gate **8/8 PASS**；全闸 **9 PASS / 2 FAIL**
> （缺件 165、页几何 empty_assign 1,173，均披露；字形框线 0、框线逃逸 0、内容 18）。下一步：v2.6.x 小修（BF-54 标签 11、BF-06 缺件 165）→
> v2.6.3 = 2.6 补丁线首批（BF-06 缺件 165、BF-54 标签 11）；empty_assign 668 半版补映射（含 01_0006 L「一」）
> + D23 owner 决策 + CS4/CS5 硬条件 → 滚动到后续 patch；硬条件全满足时把当时 patch 定为里程碑正式版。

## 9. 维护规则

- 每轮开始从本表认领（写 `work/changesets/cs-*.json` 引用 BF-ID）；结束把状态改为 ✅ + 证据路径；
- 新审计/新缺陷先入本表再动手；
- 任何「阈值放宽」必须在本表与发布报告中同时披露，不得只改代码。

## 9bis. v2.7.0 / 发布材料新增条目（2026-11-13 owner 指示）

| ID | 事项 | 说明 | 轮次 |
|---|---|---|---|
| BF-55 | **v2.7.0：GAN 生成字形实现**（参考 guangeti `21_train_gan.py`（馆阁体仓库）、`22_eval_gan.py`、`33_struct_metrics.py`） | 真迹 pair 训练 + 结构闸门 + provenance=gan；生成字不覆盖真迹 | v2.7.0 |
| BF-56 | **v2.7.0：带状扫掠（ribbon）生成/回退**（参考 guangeti `brush_lib.py`（馆阁体仓库）、`generate_lib.py`、`36_fill_fallback.py`） | 骨架→笔宽→变宽渲染；GAN 输出不过结构闸门时回退 ribbon | v2.7.0 |
| BF-57 | **发布材料三件套**：项目 README、LICENSE/OFL、版本对比指标（`scripts/release_metrics.py` + `docs/reference/RELEASE-METRICS.md`） | ✅ 完成（2026-11-13） | 已完成 |
| BF-58 | **release_gate 页几何披露阈值**：支持 `--page-geometry-max-empty-assign/bad-boxes` 并在报告披露 | ✅ 完成（2026-11-13） | 已完成 |
| BF-59 | **正式包固定清单自动生成**（WORKFLOW §8）：`scripts/make_release_extras.py` + `font_package --extra-dir` + `check_release_docs` 干跑 PASS | ✅ 完成（2026-11-13，`docs/releases/v2.6.2/SELF-AUDIT.md`） | 已完成 |
| BF-60 | **构建缓存命中复核**：目录重构后全量重建 `cached=0`（402s）；不影响 sha 可复现（重建 sha=a8bb87d9），但「缓存命中 ~3m50s」需复核（cache 失效原因/键口径） | `work/lead/refactor-audit-2026-11-14.md` | v2.6.3 排查：cache 目录/键版本/清理记录；确认后更新 AGENTS/PIPELINE 的耗时声明 | 任一次重建能命中且 sha 一致，或明确记录“缓存不可用”并改文档 | v2.6.3 |

## 10. 2026-11-13 梳理：剩余执行清单（权威）

> 依据：BACKLOG 60 条 + 第 3 代审计 86 findings（`work/lead/audit3-findings-map.jsonl`）+ E24–E34 落地结果 + 当前候选闸况。

### 10-A 需执行 · 里程碑阻塞（多需 owner 决策或数据动作）

| ID | 事项 | 状态/证据 | 下一步 |
|---|---|---|---|
| BF-11 | **empty_assign 1,173**：有 quad 无 mapping 行；vol 01–12 668（651 有 lattice，含 01_0006 L「一」）、vol 00/13 504、无 lattice 40 | `empty-assign-triage-v262.json`；页几何唯一严格 FAIL | 669 个重跑检测/映射（真迹）；504 口径待 owner；40 待核 |
| BF-06 | **缺件 165**（E37 后；旧 32/827/1,200 不计）。**T1 根因=扫描侧 precut fail-open（E40）**，修复后 v2.6.2 字体重扫 **19 字/20 组件**；v2.6.3 同集 | `work/lead/v263-T1-BF06-report.md`；E40；missing_scan_v263-clean.jsonl | v2.6.3 完成（残余 17 prune 判正确 + 3 scan 残差披露）；prune-by-design 归类留 v2.6.4 |
| BF-61 | **mapping 生成器坐标系（BUILD-404）**——全量 mapping 重生成的硬前置 | audit4 BUILD-404；模拟 999 改动/192 越界 | v2.6.4 修 M/Minv + L0 断言；**修好前禁止重跑全量 mapping/补 668 半版** |
| BF-05 | **内容判据 D23（待 owner）**：content 18/35（阈值披露）；E31 证明大部分是跨架构归一化差异 | `content-aspect-analysis-v262.json` | owner 确认改「源墨保真度」后实现 gate v2 |
| BF-16 | **高频缺 23**：16 在目标缺口、7 异体口径 | `high_freq_gap.json`（2026-11-13 复核） | 与 empty_assign 合并处理；7 字口径 owner |
| BF-41 | **缺口 6,300 策略** | 与 D23/BF-16 联动 | owner 决策 |
| BF-04/17/18/24 | 新包材料/finalize：材料数字同源、三件套、01-changes 重生成 | BF-04 旧包不可签收（ACCEPT）；新包未做 | 里程碑前一次性生成 |
| BF-29/30/31/32/33 | 硬条件：隔离 9、100 字签核、锚点、精度敞口、DATA 许可 | 见 §5 | CS4/CS5 |

### 10-B 需执行 · 闸/流程/材料（无 owner 依赖，可立即做）

| ID | 事项 | 说明 |
|---|---|---|
| BF-10 | 闸契约：缺项即 FAIL、阈值零余量披露、doc_check 数字对账 | 当前全闸已强制扫描；阈值披露待完善 |
| BF-44 | gate-report/build_recipe 归因（argv/commit/输入 sha） | 部分已做（gate-report inputs+git），build_recipe 待接 |
| BF-51 | 构建降级路径标记（geometry/quad/lattice 异常） | stats 需记降级计数并进闸 |
| BF-47/25/26/27/28/34 | 文档/审计/索引/GLM 报告归档/RELEASE-INVENTORY 状态 | 本轮已修 PROJECT-STATE/DATA/PIPELINE 主要数字；SCRIPTS/README 索引待清 |
| BF-49 | scripts keep/archive 判定（顶层仍有死脚本） | 逐脚本标注 |
| BF-36 | detect_blocks docstring 与实现不一致 | 二选一改齐 |
| BF-38/39/42 | check_terms.py / milestone.json / new_candidate.py | 流程工具 |
| BF-15 | fontRevision 公式统一（下一版本重盖章） | 与 gate 同源 |
| BF-19 | mapping 生成链脚本化 | 长期项，本轮不动 |
| BF-21/40 | coverage JSON 字段命名、lsb 口径基线 | 材料前清理 |

### 10-C 已完成 / 失效 / 改写（不再重复执行）

1. **已完成待勾销（E24–E37）**：BF-03（E30 quad 扩张 bad_boxes→0）、BF-07（E27/E33/E37 字形框线→0；框线逃逸 153→0）、BF-13（E29 strip 摘除）、BF-20（char_diff quarantine）、BF-53（E27 线条带）、BF-57/58（发布材料/披露阈值）、BF-01/02/08/09/12/14/22/37/43/45/46/48/50（早期）。
2. **已完成待勾销（E35/E36，2026-11-13）**：缺件扫描配准重写（复刻构建最终墨迹链；827→32，interior 0；sidecar 绑定 build_stats）。
3. **失效数字/说法（已改写）**：
   - 「缺件 1,200 / 1,153 / 1,155 / 827 / 32」→ **165**（v2.6.2 披露值；旧口径不可比）。**T1（E40）：主因=扫描侧 precut fail-open，修复后对 v2.6.2 字体重扫 19 字/20 组件；165 不再作候选口径**；
   - 「框线逃逸 153 / 158 / 43 / 1」→ **0**（E37 只删穿越块边界线 + 亚像素口径）；
   - 「内容闸 35 / 34 / 33 / 32 / 29」→ **18**（阈值 35；E31/E37 归因跨架构差异，D23 待定）；
   - 「343 页无 quad 影响 238 字」→ **失效**：`missing_quad_chars=0`，无字形落这些页；真实缺口是 empty_assign 1,173（BF-11 已改写）；
   - 「阈值=观测值 35/35、153/153、1200/1200」→ 现状 18<35、frame 0、empty 1,173<1,200；披露方式由 BF-10/BF-58（release_gate 显式阈值参数）统一；
   - 「缺口 6,298 / 分桶 6,214」→ **6,300**；
   - 「BUILD-04/DATA-07 坐标系矛盾、DATA-10 字形级框线盲区」→ 已修（BF-03/BF-01），findings-map 已更新。
4. **暂缓（明确不排期）**：BF-23（fidelity LRU 计时）、BF-35（旧方法 A/B，与现架构无关）。

### 10-D 建议顺序

1. CS3-A：empty_assign 668 半版补映射（先 01_0006 L「一」）→ 覆盖/缺口重算；
2. v2.6.3：缺件已定位（E40：扫描侧 fail-open，修复后 165→19）；残余 17 prune_loss+5 clean_ink_loss+3 scan 残差 → 类级修/披露；BF-61 修复前禁止重跑全量 mapping；
3. D23 owner 决策（内容判据）→ 实现源墨保真度基线；
4. BF-10/44/51/47/25/49/36/28 等闸/流程/材料项随轮次清理；复核包已生成：`work/review/round-003-v262/`（第 1 轮，owner 已标注 77 格）与 `work/review/round-004-v262fix/`（第 2 轮修复验证，待 owner 复看）；
5. CS4/CS5 硬条件（隔离 9、100 字签核、锚点、精度、许可）→ 里程碑严格全闸 → 复核包 → 正式包。

> **版本策略（owner 2026-11-14）**：v2.6.x = 2.6 系列补丁线；修复随 v2.6.3、v2.6.4…… 发布，计划项未完成则顺延，
> 不要求 v2.6.3 一次做完所有项；minor（v2.7.0）仅用于 GAN/带状扫掠等结构性新增。
>
> **2026-11-13（E37 后）**：v2.6.2 为**正式发布候选**（sha `a8bb87d9…`；发布材料 README/LICENSE/OFL/指标/已知债已补齐）。
> owner 提交 + 确认 3 项披露阈值（缺件 165、empty_assign 1,173、内容 18/35）后 clean-tree 打包 + finalize。
> 剩余小修（BF-54 标签 11、BF-06 缺件 165）放 v2.6.x；empty_assign/D23/硬条件纳入 **v2.6.3**（见 `docs/plans/PLAN-v2.6.3.md`）。
