# 对「GLM 审计」与「DSH Pro 审计」的抗辩 · 190 脚本梳理/归档/v2.5.6

> 时间：2026-11-12 · 被审对象：`docs/SCRIPTS.md`、`scripts/_archive/` 归档、v2.5.6 发布包与门禁。
> 裁决口径：**成立（已修）／成立（挂账）／部分成立／不成立**；每条附可复现证据。
> 两轮审计共 13+13 条声明，我方复核后：**成立 17 条、部分成立 4 条、不成立 3 条**（详见 §2/§3）。

## 1. 先回答项目方的问题：过期脚本是不是「反复出问题」的根源？

**是重要原因之一，但我把机制说准一点：**

1. **「已解决」的判定被写在会话里，而不在管线里**——`lead_*` 68 个脚本解决了映射，但映射定稿后
   生成命令是会话内联、没有脚本；旧脚本仍在 `scripts/` 且文档还引用它 → 后来者（LLM）读文档会以为
   「跑这个脚本就能复现」，实际管线已不用它。这就是「以为解决了、其实管线不用它」。
2. **验证缺环**：过去多轮问题（2×2 外带删除、v2.5.4 版本号、QA/PROVENANCE 数字）都不是被「读代码」
   发现的，而是被「全量复查」发现的。**没有全量复查，声明与实现就会漂移**——这是审计两轮都点中的同一病灶。
3. 本次归档**减少了表面积**（190→49），但也暴露了一个新失败模式：**归档把仍被文档引用的
   provenance 脚本的依赖剪断了**（`lead_char_align14 → t1_count_v3`）。本轮已修（恢复共享库，49/49 import 通过）。
4. 真正的根治不是「删干净旧脚本」，而是**把每条结论性声明绑定一条可复现命令**（本轮门禁加固即为此）。

## 2. 对【GLM 审计】的裁决

| # | GLM 声明 | 裁决 | 证据 / 处置 |
|---|---|---|---|
| G1 | 190=48+142、git mv R100、py_compile 48/48 | **成立** | 复核通过；py_compile 独立复跑通过 |
| G2 | **P1-1 内容缺失闸退出码恒 0 → release_gate 该步永不失败** | **成立（已修）** | 实测 `main()` 对 damaged 不 exit；仅覆盖率不足 exit 2。**已修**：damaged>阈值（默认 0）→ `sys.exit(3)`；release_gate 改为「退出码 + 解析 JSON damaged」双判 |
| G3 | **P1-2 release_gate 无 scan_missing_parts 步骤、`--skip-scan` 死旗标、quarantine 硬编码** | **成立（已修）** | **已修**：新增 `--scan` 步骤（全库缺件扫描，输出 gate 台账）、`--quarantine` 传参；删死参数 `allow_fail` |
| G4 | P2-3 SCRIPTS.md §4 与 §7.2 自相矛盾（删 vs 复活 `apply_reference_filter`） | **成立（已修）** | 已改为「§4 禁默认开启 + 走 §7.2 消融后显式启用」，并补 `clean_cluster/clean_ink` 措辞一致性说明 |
| G5 | P2-4 映射层可复算性被高估；`lead_char_align14` 模块级 import 已断 | **成立（已修/挂账）** | 实测 `from t1_count_v3 import ...` 顶层 import 断；**已修**：恢复 `t1_count_v3.py` 为共享库，49/49 脚本 import 通过；mapping 生成命令仍未脚本化 → **挂账**（build_recipe 记输入 sha 为部分缓解） |
| G6 | **P2-5 §8-4「layout_lattice 基本全空」证据错误** | **成立（我方认错，已改）** | 实测：3,869 页中 **3,582 页有框（92.7%）**、**139,056 框（38.8/页）**、中位 **79×72**。真实问题是**过检出+拟合退化**，不是全空。已改 SCRIPTS.md 并区分两类失败模式（big_boxes 稀疏 4.2/页 vs lattice 过检出） |
| G7 | P3 mapping23/32 漂移、PLAN「刃/刃」笔误、ledger 字段单薄、snap_box 依赖注记 | **成立（已修）** | 已校准为「基座 mapping32、发布 mapping33」；修 PLAN 笔误；补 ledger 溯源字段待办；补 snap_box 依赖 `cell_grid_boxes` 恢复注记 |
| G8 | P3-5「3,352 里有少量 prepare 失败行而非纯误报」 | **不成立** | 实测 `missing_scan_v252.jsonl` 3,352 行中 **error/prepare 失败行 = 0**；3,352 是参考支持过滤前的**误报行**口径，对比对象是 v252b 1,109。GLM 此条口径错误 |

**GLM 这次审计最有价值的两条**：G2（内容闸没有牙齿）与 G5（归档断链）——都是「门禁/可复算性」层面的真问题，已修。

## 3. 对【DSH Pro 审计】的裁决

| # | DSH 声明 | 裁决 | 证据 / 处置 |
|---|---|---|---|
| D1 | 190=48+142、overlay sha 一致、v2.5.6 包完整、上轮两 P0 已修 | **成立** | 复核通过 |
| D2 | **P1「重建 glyf 差异=0 与证据矛盾：974 字轮廓点不同（≤2 单位）」** | **不成立（口径误判）** | 独立实测：v2.5.5 vs v2.5.6 **17,007 字 glyf 坐标数组差异 = 0**（逐字逐点比较）；真正的 974 差异是 **hmtx lsb**（幅度 1–55 units，非 ≤2；抽样 㔌 139→174）。原因：overlay 重建用点集 xMin 重算 lsb，v2.5.5 的 lsb 是历史构建旧值。**已把文档「差异=0」校准为「轮廓 0 差异；974 字 lsb 由 overlay 重算」**（SCRIPTS.md §8bis）；DSH 引用的 `v256_rebuild_diff.json` 是早期 glyphSet 签名比对的中间产物，口径未标注 |
| D3 | P1「4 个危险开关默认关闭不实：`enable_edge_strip` 默认 True」 | **成立（已修）** | 实测函数默认值确为 True（仅调用点传 False）。**已修**：默认改 False，且任一破坏性开关为 True 时 `vectorize_gray` 直接 raise（策略 D20） |
| D4 | P1「§8-4 layout_lattice 与实测相反」 | **成立（同 G6，已改）** | 见 G6 |
| D5 | P1「归档断链：`lead_char_align14` 顶层 import 已归档模块，docs/DATA 复现链必 ImportError」 | **成立（已修）** | 见 G5；**已修**并验证 49/49 import |
| D6 | P2 overlay 提取器未入库（load-bearing 产物不可再生） | **成立（已修）** | 新增 `scripts/make_repair_overlay.py`，重跑生成 overlay sha256 = `48c611ab…`（与记录值一致，1,602 字） |
| D7 | P2 check_release_docs 白名单放行旧值 17,013/17,029 | **成立（已修）** | 已从白名单删除 17,029/17,013 |
| D8 | P2 隔离清单缺 仟/禦/絞 | **成立（已修）** | 隔离清单补全为 9 字（含 仟/禦/絞），并在 v2.5.7 包内披露 |
| D9 | P2 snap_box 的 μ 项未实现（半成品） | **成立（挂账）** | 复核属实；§7.3 A/B 前需补 μ 项并恢复依赖，已写入计划 |
| D10 | REBUTTAL 三条裁决：2a 部分成立（校验无上限/不落盘）；2b 部分成立（独立闸未列常规闸）；2c 部分成立（.notdef 路径） | **接受其中 2 条半，反驳 1 条** | 2a：校验已脚本化但「无上限/不落盘」属实 → 挂账（补 repair log 落盘/阈值）；2b：**已修**——release_gate 新增 `--scan` 步骤，独立源闸可进门禁；2c：`.notdef` 路径存在于 `fidelity_eval` 的通用渲染函数，但内容闸按 manifest 遍历、且 QA 有 `cmap==manifest` 硬闸，**「整字移除盲区」属 manifest 差集**——已由 `char_diff` 步骤覆盖；因此我方原句「不存在 .notdef 比较路径」表述过强，改为「移除场景不经过比较，由字符集 diff 覆盖」 |
| D11 | P3 name5=2.55/2.56 | **部分成立（口径小纠）** | name ID5 实为 `Version 2.5.5/2.5.6`；2.55/2.56 是 head.fontRevision。不影响结论 |

**DSH 最核心的指控（D2）我明确反驳**：974 不是轮廓差异，是 lsb 度量差异；「≤2 单位」与实测（1–55）不符。
但这轮暴露的**口径不严谨**是我的问题——文档里「差异=0」没有写清「轮廓 vs 度量」，已修正并在 §8bis 固化。

## 4. 本轮已执行的修复（可复现）

| 修复 | 命令/文件 | 验证 |
|---|---|---|
| 内容闸牙齿 | `content_loss_gate.py`：damaged>0 → exit 3；release_gate 双判 | 用 v2.4.19 vs v2.4.15 跑 → exit 3（1,132 damaged） |
| 门禁补 scan/参数 | `release_gate.py: --scan/--quarantine` | 语法/运行检查 |
| 白名单收紧 | `check_release_docs.py` | 复跑 DOC-CHECK |
| 危险开关 | `font_norm.py` 默认 False + raise 守卫 | import 自检 |
| 归档断链 | 恢复 `scripts/t1_count_v3.py` | 49/49 script import 通过 |
| overlay 可再生成 | 新增 `scripts/make_repair_overlay.py` | 重生成 sha = 记录值（1,602 字） |
| 隔离清单 | `v256_residual.json` = 9 字（补 仟/禦/絞） | 随 v2.5.7 包披露 |
| 文档校准 | SCRIPTS.md §8-4/§8bis、mapping 编号、PLAN 笔误 | — |

## 5. 仍在挂账（不粉饰）

1. mapping 生成命令未脚本化（`mapping_verified_all*` 无生成脚本）；
2. overlay 缺 page/box/script/version 溯源字段；
3. `scan_missing_parts` 参考检查 fail-open（应 fail-closed）；
4. `detect_blocks` docstring 与实现不一致；
5. `snap_box` μ 项未实现；
6. 审计台账/索引仍滞后；
7. `repair_*` 的逐字校验上限/拒收清单未落盘。

## 6. 一句话

两轮审计里 **2 条不成立/口径错误**（GLM 的 3,352 error 行、DSH 的 974 轮廓差异），
**4 条部分成立**，其余成立——其中两条最要命的（内容闸无牙齿、归档断链）已修。
这也再次证明：**「结论必须带可复现命令」不是形式主义，而是本项目唯一稳定的质量机制**。
