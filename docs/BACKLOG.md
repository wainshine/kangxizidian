# BACKLOG · 待修复清单（v2.6.1 之后，2026-11-12）

> 本文是**唯一待修复清单**：来源 = 第 3 代两份审计（GLM/DSH）+ 已知债 + 流程缺口。
> 规则：每项写清「证据 / 修法 / 验收 / 轮次」；修复后改状态为 ✅ 并注明 commit/证据，不删除记录。
> 状态：`P0` 阻塞发布 / `P1` 下一轮必修 / `P2` 可随轮次修 / `ACCEPT` 明确接受不修。

## 0. 总览

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 9（已完成 4） | BF-01/02/08/09 ✅；余：坐标 1、内容 1、闸契约 1、包 1、框线 1 |
| P1 | 22（已完成 5） | BF-12/14/37/43/45 ✅；余 17 |
| P2 | 20（已完成 4） | BF-22/46/48/50 ✅；余 16（含 BF-44 部分完成） |
| ACCEPT | 4 | 历史文档不改写、v2.6.1 旧包不重打、历史数字不回溯重算、审计报告保留 |

> 第 3 代审计 86 条 findings 的逐条状态见 `work/lead/audit3-findings-map.jsonl`（12 已修 / 6 部分修 / 1 接受 / 67 排期，**0 条无归属**）；汇总见 `audit/AUDIT-RESPONSE-v2.6.1-audit3.md` §5。
> BF-01..42 为 2026-11-12 首版；BF-43..51 为同日按 86 条 findings 逐条核对后补录的孤儿项（此前只按主题合并，存在归属缺口）。

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
| BF-02 | **同框冲突 2 对**：沓/𦧟（08_0319 R）、䛱/忠（10_0081 R） | 修复后的 font_qa 实测 2 对；审计 DSH P0-5 | 类级规则 `scripts/fix_mapping_sameblock.py`：同块多字保留 verified ink box 面积最大者，其余删除并写 residual（沓/忠 为片段框误标，转缺口待 CS3 重定位）；禁止改字形绕过 | ✅ **完成（2026-11-12）**：font_qa 同框=0 PASS；新字体 17,005 字（E23）；`sameblock-fix-report.json` | CS1.5 |
| BF-03 | **mapping box ∩ quad 越界** | 审计 GLM P0-3/DSH P1；页级几何闸复核：用 M（page→rot，正确口径）1px 容差 **198**、0 容差 **360**（与审计数字一致）、max 8.8px；Minv 反向 248 仅核对 | 复诊：**不是坐标空间错误**（make_block_mapping 已统一 get_page_content_quads），是 content quad 偏紧的页级几何残差；交 CS2 页级几何修（343 无 quad/184 半版/quad 外沿） | 0 容差 bad_boxes→0（或经 owner 同意的披露阈值） | CS2 |
| BF-04 | **v2.6.1 包不可签收**：旧 finalize（zip 内报告/SHA 旧）、包内 README 数字矛盾（60/700 vs 153/1200）、review tsv 混入 v2.6.0 数据 | 审计 DSH P0-2/P1；本次核对确认 | 不重打 v2.6.1；下一候选重建后按新 finalize 顺序出包；材料由同一数据源生成 | 新包 zip==目录、SHA 覆盖报告、材料数字与 gate-report 一致 | CS1 |
| BF-05 | **内容闸 35→33**（14 字 IoU<0.3 级别） | `content-loss` 闸；页级 pre-cut mask 后 35→33 | 归因：盒/指派/裁切；类级修 + 回写 mapping；不得用 restore | 内容闸 0（或经 owner 同意的披露阈值，且逐字有原因） | CS3 |
| BF-06 | **缺件 1,200**（邻字隔离未修+ref fail-closed 影响） | 审计 E3/P1；本次已修 ref fail-closed，需重扫 | 先修「block 内邻字组件不计入」类规则，重扫得到干净基线 | 缺件数字可解释；已知债清单冻结 | CS3/CS4 |
| BF-07 | **框线逃逸/字形级框线** | 源图口径 153（旧）；字形级 23→**14**（E24 页级 pre-cut mask 修 9 字） | 页级几何（BF-11）+ 页级 pre-cut mask（已有）+ verified tight bbox keep 区（框内残线） | 字形级框线=0；源图口径重扫后披露 | CS2 |
| BF-08 | **缓存/几何修复后首次全量重建候选** | 本轮修了 cache key/几何路径；旧字体是旧 key 产物 | 全量重建（0 命中）→ v2.6.2；回退实验后 v2.6.2 候选 | ✅ **完成（2026-11-12）**：v2.6.2 全量 6m42s（sha `58fd9235…`）；缓存命中重建（3m52s）sha 一致 —— 可复现；数字见 `fast-gate-v264.json` | CS1 |
| BF-09 | **构建失败静默**：单字失败仅 WARN，仍 exit 0 | 审计 GLM P1/DSH | 硬失败：任何 skipped（除 `--limit`）→ 写失败报告（`aborted/failed_n/failed`）并 exit≠0；`--allow-partial` 才放行 | ✅ **完成（2026-11-12）**：注入坏 box → `ABORT: 1 字构建失败` + `/tmp/bad.build_stats.json`，exit 1 | CS1 |

## 3. P1

| ID | 问题 | 证据 | 修法 | 验收 | 轮次 |
|---|---|---|---|---|---|
| BF-10 | **闸契约仍可被绕过**：可选闸省略即 PASS；阈值=观测值（35/35、153/153、1200/1200）零余量；`doc_check` 不做数字对账 | 审计 GLM/DSH P1 | 候选/里程碑强制 full gate；阈值模式要求记录「上一版数字+delta」，零余量必须披露；doc_check 校验 README/QA 数字与 gate-report 一致 | 缺项即 FAIL；数字不一致即 FAIL | CS1 |
| BF-11 | **343 页无 quad / 184 页仅半版**（影响 238 字） | 审计 DSH P0-4 影响面；PROJECT-STATE P1 | 页级几何校验（BF-01③）→ 逐页修 quad（fallback 只能兜底，不能当修复） | 无 quad 页→0；238 字复测 | CS2 |
| BF-12 | **扫描结果未绑定字体 SHA**（早期扫描早于字体；reuse 无校验） | 审计 DSH P1 | 新增 `gate_binding.py`：扫描/内容输出旁写 `<out>.sha256`（font/manifest/mapping/geometry/参考字体/脚本 sha + argv + git）；快闸/全闸复用前校验，缺失或不匹配 → FAIL | ✅ **完成（2026-11-12）**：`validate_reuse` 单测（换字体→不通过）；内容/缺件/框线闸均已接入 | CS1 |
| BF-13 | **页级几何与 pre-cut 不变量冲突**：主链仍调 `strip_border_lines`（形状删线） | 审计 GLM P2-2；200 字 A/B 量化（`work/lead/strip-border-ab-v4.json`）：strip 改动 56/200（删 11,263px；仅 2/200 改变轮廓数），页面级 frame mask 对样本 0 作用；块边带（3px）会误删真笔画 | 结论：**CS1-B 暂保留 strip**（现页面几何下它仍承担块边界界行/框线清理）；CS2 先修页级几何/pre-cut，再按同 A/B 复测摘除 strip + 用 `glyph_frame_gate` 归零验收 | 摘除后 glyph_frame_gate=0 且内容/缺件闸无回归；内部 pad 实验已回退（ERRATA E21，归入 v2.6.2） | CS2 |
| BF-14 | **Songti 专有字体依赖** | 审计 E8；2026-11-12 全管线替换完成 | 新增 `scripts/reffont.py`（唯一参考字体：霞鹜文楷 OFL）并替换 font_qa/refgate/refgate2/scan_distort/fidelity_eval/scan_missing_parts/font_norm/review_sheet/owner_defect_sheet + 3 个 legacy 标注脚本；font_qa 孔洞对照删除（D21） | 构建/闸/报告脚本无 Songti/Hiragino 依赖 | ✅ 完成（2026-11-12） |
| BF-15 | **fontRevision 公式 v2.10+ 崩坏**（4 处同错） | 审计 GLM P1-6 | 统一共享函数 `major + minor/100 + patch/10000`；下一版本重盖章 | 用 v2.10 假设单测通过；闸与构建同源 | 下一候选 |
| BF-16 | **高频缺 23 口径**：审计称仅 16 字在目标缺口内（在/教/清等因异体口径不在目标表） | 审计 DSH P1；2026-11-12 复核：23 字均不在 mapping，且已验证 01_0006 L（一的字头页）有 quad 无 mapping 行 | 逐字核对 canonical/目标表口径；按页复查这 23 字是否属映射遗漏（真迹重新检测优先，禁止补假字）；更新名单与披露 | 名单与差集脚本一致；遗漏页有处置结论 | CS4 |
| BF-17 | **包材料数字同源**：README/QA/coverage 由不同手写模板产生 | 审计 DSH P1（60/700 vs 153/1200） | 材料模板从 gate-report/coverage JSON 生成；禁止手写数字 | 机器生成、doc_check 校验 | CS1 |
| BF-18 | **changesets/version-artifacts 三件套未强制** | 审计 GLM P1-1；本轮已补 v2.6.1 回溯文件 | release_gate finalize 检查三件套存在（新版本必须有 cs-\* + version-artifacts） | 缺失即 FAIL | CS1 |
| BF-19 | **mapping 生成链未脚本化**（仅数据+碎片脚本） | SCRIPTS/PROJECT-STATE 已知债 | 长期：用 charalign 脚本重建成可复现链；短期保留全部 map JSON 证据 | 能从 canonical + 扫描件重跑出 mapping（报告一致性） | 长期 |
| BF-20 | **fast_gate char_diff 不拦截 removed**（release_gate 有一致性检查） | 审计 GLM P2-8 | fast_gate 增加 quarantine 对账；removed>0 且不在隔离清单 → FAIL | 删字必须声明 | CS1 |
| BF-43 | **禁止能力仍可触达**：主链保留 restore/overlay 整字拷贝代码路径与缓存 `__overlay__` 分支 | 审计 BUILD-07/DOCS-10 | 删除主链 overlay 分支/`--repair-overlay`/`--src-map`/`contours_override` 读取；构建遇 dict 轮廓即报错；`make_repair_overlay.py` 停用 | ✅ **完成（2026-11-12）**：注入 `__overlay__` 字形 → RuntimeError exit 1；overlay 生成器 exit 1 | CS1 |
| BF-45 | **clean-tree/freshness 闸可绕过**：`--allow-dirty` 全绕过、被 gitignore 的构建输入不进 provenance | 审计 GATE-13 | finalize 前置 `clean_tree` 步（脏树 FAIL，`--allow-dirty` 仅调试且记录）；输入 sha 进 gate-report `inputs` | ✅ **完成（2026-11-12）**：临时包副本跑全闸 → `FAIL clean_tree`（dirty=true）且 `package_touched=false` | CS1 |

## 4. P2

| ID | 问题 | 修法 | 轮次 |
|---|---|---|---|
| BF-21 | coverage JSON 字段命名含混（`basic_coverage_pct` 实为目标表口径） | 改名/加注（`target_set_coverage_pct`），旧字段保留一版 | 材料 |
| BF-22 | 缓存命中重建耗时（审计测得 242–251s） | 几何路径已修，重建后实测；更新 PIPELINE/AGENTS 的 ~20s 声明 | ✅ **完成（2026-11-12）**：全量 402s、缓存命中 232s（装配占大头）；文档已更正（ERRATA E22） | CS1 验证 |
| BF-23 | fidelity LRU 缓存效果未测 | 扫描重复运行计时对比 | CS1 |
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
| BF-34 | **D19 缺口分桶清单旧口径**：`v245_gan_targets.json`=6,214 vs 当前缺口 6,298 | SCRIPTS §8-5 | 用 `lead_gan_targets.py` 重生成（若仍采用 D19 分桶策略） | 清单与当前缺口一致，随包 | P2（策略相关） |
| BF-35 | **SCRIPTS §8 的 6 处旧方法 A/B 未做**（重点：`layout_thick_detect` 独立字头候选、`snap_box` 参考评分选块 μ 未实现） | SCRIPTS §8/§7.3 | 至少完成 2 个建议项的 A/B（固定样本 + 内容/缺件闸）；其余记录取舍理由 | A/B 报告 + 决策记录（DECISIONS 追加） | P2（研究） |
| BF-36 | **代码-文档不一致**：`detect_blocks` docstring「留边≥4%」实现未设阈值 | SCRIPTS §8-1 | 改代码实现阈值或改 docstring；不得留双口径 | 文档=行为 | P2 |
| BF-37 | **复核包脚本化**：已简化为 3 件（`01-changes` / `02-random100` / `ledger.tsv`），`scripts/make_round_pack.py` 一条命令生成；其余图按需 | WORKFLOW §6；`work/review/round-002/` | 保持 3 件不膨胀 | 任一轮一条命令生成 3 件 | ✅ 完成（2026-11-12） |
| BF-38 | **术语检查器缺失**（GLOSSARY 未落地为检查；版本命名/禁用词） | PROJECT-AUDIT §4；馆阁体对照 | `scripts/check_terms.py`：检查 docs/代码/包内文档禁用词与命名；接进快闸 | 检查器存在且 0 违规（或白名单） | P1（流程） |
| BF-39 | **里程碑治理未机器化**：无「里程碑条件文件」，release_gate 不校验收否满足 | WORKFLOW §7 | 增加 `milestone.json`（P0 清零/已知债冻结/owner 签核/结构冻结）+ gate 校验 | 缺 milestone.json 或条件不满足 → 拒发正式包 | P1（流程） |
| BF-40 | **lsb/归一化口径历史差异未声明**：v2.5.6 曾 974 字 lsb 重算（1–129 units）；当前由轮廓决定 | SCRIPTS §8bis | 一次性核对当前构建 lsb 分布；在 PIPELINE/QA 记录归一化与 lsb 规则 | 文档写明；抽样验证 | P2 |
| BF-41 | **缺口 6,298 的处理策略未定**：headword-only 不补假字 vs D19 重定位/GAN 目标 | DECISIONS D19；PROJECT-STATE | owner 决定是否/如何补缺口；若做，先定验收与许可 | 策略记录（DECISIONS 追加） | P1（策略） |
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
5. **CS3**：BF-05 内容 35→0 + BF-06 缺件（新参考口径）；
6. **CS4/CS5**：BF-16/BF-15 + 历史硬条件 BF-29/30/31/32/33 + 流程 BF-38/39 + 策略 BF-41/42 → 1–2 天。

> 合计未完成 **38 条**（P0 5 + P1 17 + P2 16；已完成 13：BF-01/02/08/09/12/14/22/37/43/45/46/48/50）。CS2 剩余：BF-03/04/05/06/07 + 字框线 23 + 闸契约尾项 BF-10/17/18/20/23/24/25/44/47。审计 86 条 findings 现 28 fixed / 8 fixed-partial / 1 accepted / 49 deferred。

## 9. 维护规则

- 每轮开始从本表认领（写 `work/changesets/cs-*.json` 引用 BF-ID）；结束把状态改为 ✅ + 证据路径；
- 新审计/新缺陷先入本表再动手；
- 任何「阈值放宽」必须在本表与发布报告中同时披露，不得只改代码。
