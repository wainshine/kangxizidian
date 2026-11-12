# BACKLOG · 待修复清单（v2.6.1 之后，2026-11-12）

> 本文是**唯一待修复清单**：来源 = 第 3 代两份审计（GLM/DSH）+ 已知债 + 流程缺口。
> 规则：每项写清「证据 / 修法 / 验收 / 轮次」；修复后改状态为 ✅ 并注明 commit/证据，不删除记录。
> 状态：`P0` 阻塞发布 / `P1` 下一轮必修 / `P2` 可随轮次修 / `ACCEPT` 明确接受不修。

## 0. 总览

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 9 | 其中 3 项为闸缺失/闸契约，2 项为映射/几何坐标错误，1 项为内容缺损，1 项为重建，2 项为流程完整性 |
| P1 | 20 | 审计 P1（11）+ 历史遗留（9：隔离/签核/锚点/标签精度/数据源/复核包/术语检查/里程碑治理/缺口策略） |
| P2 | 13 | 审计 P2（8）+ 历史遗留（5：D19旧口径/SCRIPTS §8 A/B/代码文档不一致/lsb 口径等） |
| ACCEPT | 4 | 历史文档不改写、v2.6.1 旧包不重打、历史数字不回溯重算、审计报告保留 |

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
| BF-01 | **三闸缺失**：字形级框线闸 / provenance 无拷贝闸 / 页级几何闸 | 审计 DSH P0-3；PIPELINE §4 只有源图级扫描 | 新建 3 个脚本并接 release_gate：①glyph_frame_gate（细长线≥0.5 字宽且厚≤3px）②provenance_gate（禁止整字拷贝/overlay；构建 recipe 记录）③page_geometry_gate（每页 block 包住主簇/quad 压线/同页 box 恒定） | 三闸存在且能 FAIL；v2.6.0 坏字形可被 glyph_frame_gate 抓住（回归样本） | CS1 |
| BF-02 | **同框冲突 2 对**：沓/𦧟（08_0319 R）、䛱/忠（10_0081 R） | 修复后的 font_qa 实测 `same_box_conflicts` 2 对；审计 DSH P0-5 | 改 mapping 指派（全库同框检测为类规则）；禁止改字形绕过 | 同框=0；font_qa PASS | CS1.5 |
| BF-03 | **mapping box ∩ quad 坐标系错误**：用原坐标 block 与旋转空间 quad box 求交，audit 报 360/17,007 字 box 越出正文区 | 审计 GLM P0-3/DSH P1；`get_page_content_quads` 返回旋转空间 `box` | 求交前把 block 变换到旋转空间（M），或对 quad 取 Minv 四角得原空间 bbox；统一用同一函数 | 全库 mapping box 100% 在 content 内；238 字/343 页影响面复核 | CS1.5 |
| BF-04 | **v2.6.1 包不可签收**：旧 finalize（zip 内报告/SHA 旧）、包内 README 数字矛盾（60/700 vs 153/1200）、review tsv 混入 v2.6.0 数据 | 审计 DSH P0-2/P1；本次核对确认 | 不重打 v2.6.1；下一候选重建后按新 finalize 顺序出包；材料由同一数据源生成 | 新包 zip==目录、SHA 覆盖报告、材料数字与 gate-report 一致 | CS1 |
| BF-05 | **内容闸 35**（15 字 IoU<0.3，含常用字 公=0.08） | `work/lead/content-loss-gate-v261.json` | 归因：盒/指派/裁切；类级修 + 回写 mapping；不得用 restore | 内容闸 0（或经 owner 同意的披露阈值，且逐字有原因） | CS3 |
| BF-06 | **缺件 1,200**（邻字隔离未修+ref fail-closed 影响） | 审计 E3/P1；本次已修 ref fail-closed，需重扫 | 先修「block 内邻字组件不计入」类规则，重扫得到干净基线 | 缺件数字可解释；已知债清单冻结 | CS3/CS4 |
| BF-07 | **框线逃逸 153**（源图口径，且非字形级） | `frame_escape_scan_v261.jsonl`；审计 P0-3 | 页级几何（BF-11）+ glyph_frame_gate 双闸；按页修 quad/格点 | 字形级框线=0；源图口径残留在披露范围 | CS2 |
| BF-08 | **缓存/几何修复后首次全量重建候选** | 本轮修了 cache key/几何路径；旧字体是旧 key 产物 | 全量重建（cache 0 命中）→ 得候选 cYYYYMMDD-1；记录 sha/耗时/内容/框线/缺件数字 | 候选可复现（缓存命中重建 sha 一致）；数字落盘 | CS1 |
| BF-09 | **构建失败静默**：单字失败仅 WARN，仍 exit 0 | 审计 GLM P1/DSH；本轮只加 WARN | 加硬失败：失败/缺字>0 且无 `--allow-partial` 时 exit≠0；skipped 必须落盘 | 人为注入失败 → 构建退出非 0 | CS1 |

## 3. P1

| ID | 问题 | 证据 | 修法 | 验收 | 轮次 |
|---|---|---|---|---|---|
| BF-10 | **闸契约仍可被绕过**：可选闸省略即 PASS；阈值=观测值（35/35、153/153、1200/1200）零余量；`doc_check` 不做数字对账 | 审计 GLM/DSH P1 | 候选/里程碑强制 full gate；阈值模式要求记录「上一版数字+delta」，零余量必须披露；doc_check 校验 README/QA 数字与 gate-report 一致 | 缺项即 FAIL；数字不一致即 FAIL | CS1 |
| BF-11 | **343 页无 quad / 184 页仅半版**（影响 238 字） | 审计 DSH P0-4 影响面；PROJECT-STATE P1 | 页级几何校验（BF-01③）→ 逐页修 quad（fallback 只能兜底，不能当修复） | 无 quad 页→0；238 字复测 | CS2 |
| BF-12 | **扫描结果未绑定字体 SHA**（18:06/18:21 扫描早于 18:23 字体；reuse 无校验） | 审计 DSH P1；本次已加 reuse 文件存在校验 | 扫描输出旁写 `<file>.sha256`（字体 sha+几何 sha）；reuse 必须匹配；不匹配重跑 | reuse 侧车缺失/不匹配 → FAIL | CS1 |
| BF-13 | **页级几何与 pre-cut 不变量冲突**：主链仍调 `strip_border_lines`（形状删线） | 审计 GLM P2-2；`font_norm.py:872` | 二选一：摘除（pre-cut 承担）或在不变量/文档明确边界；改后全量重建回归 | 不变量与代码一致；内容/框线闸无回归 | CS2 |
| BF-14 | **Songti 专有字体依赖**（font_qa/scan_missing 参考；复核图已换 OFL） | 审计 E8 | 复核图已完成（霞鹜文楷 OFL）；剩余 font_qa 孔洞对照 / scan_missing 参考 → 换 OFL 或去掉 | 全管线无专有字体依赖（或仅展示层且披露） | 材料（部分完成） |
| BF-15 | **fontRevision 公式 v2.10+ 崩坏**（4 处同错） | 审计 GLM P1-6 | 统一共享函数 `major + minor/100 + patch/10000`；下一版本重盖章 | 用 v2.10 假设单测通过；闸与构建同源 | 下一候选 |
| BF-16 | **高频缺 23 口径**：审计称仅 16 字在目标缺口内（在/教/清等因异体口径不在目标表） | 审计 DSH P1 | 逐字核对 canonical/目标表口径；更新名单与披露 | 名单与差集脚本一致 | CS4 |
| BF-17 | **包材料数字同源**：README/QA/coverage 由不同手写模板产生 | 审计 DSH P1（60/700 vs 153/1200） | 材料模板从 gate-report/coverage JSON 生成；禁止手写数字 | 机器生成、doc_check 校验 | CS1 |
| BF-18 | **changesets/version-artifacts 三件套未强制** | 审计 GLM P1-1；本轮已补 v2.6.1 回溯文件 | release_gate finalize 检查三件套存在（新版本必须有 cs-\* + version-artifacts） | 缺失即 FAIL | CS1 |
| BF-19 | **mapping 生成链未脚本化**（仅数据+碎片脚本） | SCRIPTS/PROJECT-STATE 已知债 | 长期：用 charalign 脚本重建成可复现链；短期保留全部 map JSON 证据 | 能从 canonical + 扫描件重跑出 mapping（报告一致性） | 长期 |
| BF-20 | **fast_gate char_diff 不拦截 removed**（release_gate 有一致性检查） | 审计 GLM P2-8 | fast_gate 增加 quarantine 对账；removed>0 且不在隔离清单 → FAIL | 删字必须声明 | CS1 |

## 4. P2

| ID | 问题 | 修法 | 轮次 |
|---|---|---|---|
| BF-21 | coverage JSON 字段命名含混（`basic_coverage_pct` 实为目标表口径） | 改名/加注（`target_set_coverage_pct`），旧字段保留一版 | 材料 |
| BF-22 | 缓存命中重建耗时（审计测得 242–251s） | 几何路径已修，重建后实测；更新 PIPELINE/AGENTS 的 ~20s 声明 | CS1 验证 |
| BF-23 | fidelity LRU 缓存效果未测 | 扫描重复运行计时对比 | CS1 |
| BF-24 | 包内 `01-changes.tsv` 混入 v2.6.0 的框线 60 条数据 | 下一版由当前扫描结果重新生成 | CS1 |
| BF-25 | 文档中 15 条已删除路径/占位符引用 | 标注「已删除/占位」或改为新路径 | 文档 |
| BF-26 | GLM 审计报告仅存在于对话 | 归档为 `audit/AUDIT-REPORT-v2.6.1-audit3-GLM.md` | 文档 |
| BF-27 | audit triage 与 backlog 的同步靠人工 | 每轮结束自动从 findings jsonl 生成 backlog 摘要（脚本） | 流程 |
| BF-28 | release 清单中 v2.6.1 状态未标「不可签收」 | 更新 RELEASE-INVENTORY/README 状态列 | 文档 |

## 8. 非审计遗留（历史欠账，2026-11-12 补录）

> 说明：这些不是第 3 代审计新发现，而是项目长期挂账的已知项。其中 3 项是**里程碑硬条件**（签核/锚点/标签精度），不能当 P2 拖到发布前才处理。

| ID | 问题 | 证据/来源 | 修法 | 验收 | 轮次 |
|---|---|---|---|---|---|
| BF-29 | **隔离 9 字**未处置：刃/榍/法/紆/総/荹/仟/禦/絞 | PROJECT-STATE/PIPELINE；释放包隔离清单 | 逐字重定位或定案隔离；发布时点名披露 | 9 字全部有结论（入字体/隔离+理由），随包清单 | CS5 |
| BF-30 | **100 字 owner provenance 签核未闭环** | PROJECT-STATE；PLAN-v2.6 §3.1（历史计划） | 生成 100 字核验表（已有 `owner_review_*` 脚本），owner 标 ✓/✗/?；✗ 修复或隔离 | 100 字全部有结论 + owner 签核记录随包 | CS5（里程碑硬条件） |
| BF-31 | **部界锚点口径不可全信**：39/39 系循环论证；09–11/13 卷锚点缺失 | SCRIPTS §8-3；PROJECT-STATE | 严格版锚点重校验（`validate_anchors3` 思路，禁止块内取墨再判块内）；补 4 卷锚点 | 严格校验 PASS；锚点作为 mapping 回归基线 | CS2/CS5 |
| BF-32 | **标签精度敞口**：VLM top-1 84.6%（n=13，宽 CI）→ 约 1,400–1,500 字级风险 | OCR-OPTIONS/历史记录；PROVENANCE 精度说明 | 独立抽样验证（扩大 n，按卷/部首分层）；高风险字进隔离或复核 | 抽样报告落盘；敞口区间更新并披露 | CS5（里程碑硬条件） |
| BF-33 | **DATA 源扫描件来源/许可信息**（渠道已确认=书格 shuge.org；影印出版者/扫描者/条款细节待补） | owner 2026-11-12 确认渠道；docs/DATA.md §1 已写 | 补影印出版/扫描者信息与站点条款；进包 PROVENANCE | DATA §1 完整；许可声明可追溯 | CS5/材料（部分完成） |
| BF-34 | **D19 缺口分桶清单旧口径**：`v245_gan_targets.json`=6,214 vs 当前缺口 6,298 | SCRIPTS §8-5 | 用 `lead_gan_targets.py` 重生成（若仍采用 D19 分桶策略） | 清单与当前缺口一致，随包 | P2（策略相关） |
| BF-35 | **SCRIPTS §8 的 6 处旧方法 A/B 未做**（重点：`layout_thick_detect` 独立字头候选、`snap_box` 参考评分选块 μ 未实现） | SCRIPTS §8/§7.3 | 至少完成 2 个建议项的 A/B（固定样本 + 内容/缺件闸）；其余记录取舍理由 | A/B 报告 + 决策记录（DECISIONS 追加） | P2（研究） |
| BF-36 | **代码-文档不一致**：`detect_blocks` docstring「留边≥4%」实现未设阈值 | SCRIPTS §8-1 | 改代码实现阈值或改 docstring；不得留双口径 | 文档=行为 | P2 |
| BF-37 | **复核包脚本化**：已简化为 3 件（`01-changes` / `02-random100` / `ledger.tsv`），`scripts/make_round_pack.py` 一条命令生成；其余图按需 | WORKFLOW §6；`work/review/round-002/` | 保持 3 件不膨胀 | 任一轮一条命令生成 3 件 | ✅ 完成（2026-11-12） |
| BF-38 | **术语检查器缺失**（GLOSSARY 未落地为检查；版本命名/禁用词） | PROJECT-AUDIT §4；馆阁体对照 | `scripts/check_terms.py`：检查 docs/代码/包内文档禁用词与命名；接进快闸 | 检查器存在且 0 违规（或白名单） | P1（流程） |
| BF-39 | **里程碑治理未机器化**：无「里程碑条件文件」，release_gate 不校验收否满足 | WORKFLOW §7 | 增加 `milestone.json`（P0 清零/已知债冻结/owner 签核/结构冻结）+ gate 校验 | 缺 milestone.json 或条件不满足 → 拒发正式包 | P1（流程） |
| BF-40 | **lsb/归一化口径历史差异未声明**：v2.5.6 曾 974 字 lsb 重算（1–129 units）；当前由轮廓决定 | SCRIPTS §8bis | 一次性核对当前构建 lsb 分布；在 PIPELINE/QA 记录归一化与 lsb 规则 | 文档写明；抽样验证 | P2 |
| BF-41 | **缺口 6,298 的处理策略未定**：headword-only 不补假字 vs D19 重定位/GAN 目标 | DECISIONS D19；PROJECT-STATE | owner 决定是否/如何补缺口；若做，先定验收与许可 | 策略记录（DECISIONS 追加） | P1（策略） |
| BF-42 | **候选版本流程三件套的自动化**（与 BF-18 代码检查配套）：目前手工写 cs/version-artifacts | WORKFLOW §10bis | 提供 `new_candidate.py` 模板生成三件套骨架 | 新版本三件套由工具生成 | P2（流程） |

## 9. 合并说明（历史遗留 → 已有条目）

以下历史遗留此前已并入审计条目，不再重复：343 页无 quad（BF-11）、Songti 依赖（BF-14）、高频缺 23 口径（BF-16）、mapping 生成链（BF-19）、物料/文档类（BF-25/26/28）。

## 9. ACCEPT（明确接受，不修）

| 项 | 理由 |
|---|---|
| `docs/_history/` 历史文档内部旧引用 | 约定「历史不改写」 |
| v2.6.1 旧包不重打包 | 已被 v2.6.2 候选替代；重打会改历史 SHA |
| 历史 release 旧口径数字不回溯重算 | 记录在 ERRATA E3；只保证新数字来源 |
| 审计报告/回应保留原文 | 只追加后续落实状态 |

## 10. 建议执行顺序与工作量（估算）

1. **CS1-A（先决条件）**：BF-08 重建候选 + BF-22 耗时实测 + BF-09/BF-12/BF-10/BF-17/BF-18/BF-20 闸契约 → 0.5–1 天；
2. **CS1-B（新闸）**：BF-01 三闸 + BF-24/BF-25 材料整理 → 0.5 天；
3. **CS1.5**：BF-02 同框 + BF-03 坐标 + BF-04 新包 → 0.5 天；
4. **CS2**：BF-11 页级几何 + BF-13 strip_border + BF-07 框线归零 → 1 天；
5. **CS3**：BF-05 内容 35→0 + BF-06 缺件口径 → 1 天；
6. **CS4/CS5**：BF-16/BF-14/BF-15 + 历史硬条件 BF-29/30/31/32/33 + 流程 BF-37/38/39 + 策略 BF-41 → 1–2 天。

## 11. 维护规则

- 每轮开始从本表认领（写 `work/changesets/cs-*.json` 引用 BF-ID）；结束把状态改为 ✅ + 证据路径；
- 新审计/新缺陷先入本表再动手；
- 任何「阈值放宽」必须在本表与发布报告中同时披露，不得只改代码。
