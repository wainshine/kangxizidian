# AUDIT-RESPONSE · 对第 3 代两份代码审计（GLM + DSH）的核验与整改（2026-11-12）

> 被审对象：v2.6.1（process baseline）；审计材料：`audit/AUDIT-REPORT-v2.6.1-audit3.md` + `audit/AUDIT3-FINDINGS-v2.6.1.jsonl`（DSH），GLM 报告为对话文本。
> 方法：逐条读代码 + 复现；**已修项附验证命令与结果**；未修项写清原因与排期。本文不宣称 v2.6.1 可签收。

## 0. 总结论

- 两份审计的**核心 P0 基本成立**，且 GLM 与 DSH 互补（GLM 强在闸/缓存逻辑，DSH 强在包完整性/几何链路）；
- 本轮已修 **14 项**（含 5 个 P0）；**3 项修正审计结论**（见 §4）；**剩余 P0 项**（三闸缺失、同框 2 对映射冲突）明确排入 CS1/CS3；
- 修复后 **v2.6.1 无法再通过门禁**：新增的同框检查如实报出 2 对冲突 → v2.6.1 状态下调为「有 P0 已知缺陷的过程版本」；
- 核心数字（17,007 / 48.92% / 61.98% / 6,298 / 隔离 9）复算一致；缓存命中重建 sha `c73c3023…` 不变。

## 1. 已确认并修复（含验证）

| # | 审计项 | 核验 | 修复 | 验证 |
|---|---|---|---|---|
| 1 | GLM P0-1 / DSH P1：cache key 无算法/几何版本 | 成立（`v350` 硬编码） | 改为 `_CACHE_VER = sha8(算法脚本) + sha12(page_geometry.jsonl)` 自动版本化；移除人工 tag | `cache_ver=0b1f5323_42da3c0f2f76`，几何变化/算法变化会自动失效 |
| 2 | DSH P0-4：S1 几何从未被 S3 消费 | **成立且更严重**：`WORK=work/font` 导致 `_GEOM_PATH=work/font/lead/...` 不存在（从未加载） | 修正为 `work/lead/page_geometry.jsonl` | 启动打印 `[geom] loaded 3869 pages`；`_CACHE_VER` 含其 sha |
| 3 | GLM P0-2：缺件闸 `flagged=None` 判 PASS | 成立（missing）；frame 原实现已安全（GLM 此处不成立） | missing：`flagged is None` → FAIL；reuse 文件缺失/空 → FAIL | 用不存在路径跑 `--reuse-missing` → `FAIL scan_missing_parts` |
| 4 | GLM P0-4：fast_gate 内容缓存 schema 冲突 | 成立（rows list vs summary dict 同路径） | rows/summary 分离 + baseline sha 绑定 + 类型校验 | 代码检查；快闸重跑 PASS（内容闸复用） |
| 5 | GLM P0-5：make_block_mapping 重复字跨页覆盖 | 成立（潜伏，数据现 0 重复） | 行级 `rid` 回写，不再全局 `newmap[ch]` 覆盖 | 代码检查 + 语法/运行 |
| 6 | DSH P0-1：换包不设防 | 成立（--font 只用于 QA，不校验包内 TTF） | finalize 增 `pkg_font_sha` 步：包内 TTF sha 必须 == --font | **把 v2.6.0 字体塞进 v2.6.1 包副本 → `FAIL pkg_font_sha`**；正常副本 `PASS pkg_font_sha` |
| 7 | DSH P0-2：finalize 顺序（zip 早于最终报告） | 成立（旧 zip 内报告 finalized:false） | 重写顺序：预报告→SHA→最终报告→重算SHA→**最后**重建 zip；`sha_verified_after_final_report` 改为实测 | 临时包副本 finalize：`sha_final_ok=true, zip_ok=true`（zip 在 SHA 冻结后生成） |
| 8 | DSH P0-5：同框硬闸 KeyError 被吞 | 成立（`r["char"]` 键不存在） | 改为 `for ch, r in chars.items()` | **如实报告 2 对**：沓/𦧟（08_0319 R）、䛱/忠（10_0081 R）；font_qa 现在会 FAIL |
| 9 | GLM P0-3：quad 三套口径 | 成立（mapping/frame 现算、无缓存无 fallback） | `make_block_mapping`、`scan_frame_escape` 统一走 `font_build.get_page_content_quads`（缓存+fallback） | 代码检查；下次 mapping 重生成即同口径 |
| 10 | GLM P1-3：`--limit` 静默吞字 | 成立（先 add 后 break） | 先判 limit 再 add，并记 skipped reason=limit | 实测 `--limit 2` → cmap=2，skipped=2 |
| 11 | GLM P1-2：font_package 无条件 rmtree 已 finalize 包 | 成立 | 检测包内 gate-report `finalized:true` → ABORT，需 `--force-overwrite` | 代码检查 |
| 12 | GLM P1-4：frame 闸静默吞异常 | 成立 | 异常写 error 行（不再 pass） | 代码检查 |
| 13 | GLM P1-5：缺件参考 fail-open（宋体不可用→全算缺件） | 成立 | 改为 fail-closed：ref 不可用 → `ref_unavailable` 单列，不计入 flagged | 代码检查；下次全库扫描会重算 |
| 14 | GLM P2-1/P2-11/P2-12/P2-13、DSH P2：D20 未登记、VERSION-HISTORY 重复 v2.6.1、workers 默认 8、content_loss docstring、built_at 本地时区、fidelity 无缓存、包覆盖保护等 | 成立 | 全部修：DECISIONS 补 D20；VERSION-HISTORY 去重；默认 workers=10；docstring 修正；`built_at_utc` 用 SOURCE_DATE_EPOCH/UTC；`glyph_mask_from_font` 加 lru_cache（64） | 代码检查 + fidelity 冒烟通过 |

## 2. 已确认但**本轮不修**（排期）

| 项 | 原因 | 排期 |
|---|---|---|
| DSH P0-3：字形级框线闸 / provenance 无拷贝闸 / 页级几何闸缺失 | 新闸需设计与基线，不能顺手加（会改变发布判定） | CS1（下一步） |
| 同框 2 对冲突（沓/𦧟、䛱/忠） | 属 mapping 指派错误，需要改 mapping（类级审计），不能改字形绕过 | CS3（mapping 指派审计） |
| GLM P2-2：主链仍跑 `strip_border_lines`（与 pre-cut 不变量张力） | 摘除会改变 17k 字形，需全量重建+内容闸/框线闸回归 | CS2 一并处理 |
| P1-6 fontRevision 公式 v2.10+ 崩坏 | 需 4 处统一 + 重新盖章 → 改变字体 sha，留到下一版本 | 下一候选 |
| P1-7 `--reuse-content` 语义 | 已修为真跳过（见 §4 修正），文档同步待做 | 已完成代码 |
| DSH P1：扫描结果与字体的 SHA 绑定、doc_check 数字对账、包内材料数字矛盾 | 需改闸契约与包材料生成顺序 | CS1 材料链 |
| Songti 专有字体替换（E8/P1-5） | 需 OFL 参考字体；短期仅报告用途并披露 | CS1 材料 |
| 缓存命中重建 242–251s | 根因=D0H P0-4 几何缓存从未加载（每页现算）；路径已修，重建后应显著下降 | 下次重建实测 |
| 缺件 1,200 / 框线 153 / 内容 35 未清零 | 已知债（E3），本轮只保证闸不空转 | CS1–CS3 |

## 3. 对审计结论的修正/澄清

1. **GLM P0-2 的「frame_escape 同理」不成立**：原 `ok_frame` 已含 `flagged is not None`，不存在空转；仅缺件闸有此缺陷（已修）。
2. **DSH「缓存命中重建 242–251s」的根因不是组装慢，而是几何缓存路径 bug**（每页仍在现算 lattice/quad）。路径修复后重建会变快；文档「~20 秒」需在下一次实测后确认（当前不引用旧数字）。
3. **v2.6.1 包 finalize 缺陷属实**：本轮修复的是**门禁代码**；v2.6.1 包本身仍是旧 finalize 产物（zip 内报告可能是旧版），且新增同框闸后已不满足 PASS——因此 v2.6.1 **保持「过程版本、不可签收」**，不重新打包；修完后作为下一候选（v2.6.2）重建。

## 4. 修复后的状态与下一步

- v2.6.1 字体/包**状态下调**：`fast_gate` 现在会 FAIL（font_qa 同框 2 对）；这是预期（闸恢复牙齿），不是新回归；
- 下一步（CS1）：
  1. 重建候选（新 cache key + 几何缓存生效 + 新 mapping 口径）→ 观察 sha/内容闸/耗时；
  2. 新增三个闸：glyph_frame_gate（判据参照 P2-5：细长线≥0.5 字宽且厚≤3px）、provenance_gate（禁止整字拷贝）、page_geometry_gate；
  3. 修同框 2 对映射（CS3 提前为 CS1.5，因闸已挡住发布）；
  4. 扫描-字体 SHA 绑定 + 文档数字对账。
- 已建立审计 findings 的机器可读对照：`work/lead/audit3-findings-map.jsonl`（86/86 逐条；旧 `triage.jsonl` 仅保留主题级 21 行）；汇总见 §5。

## 5. findings 逐条对照（2026-11-12 补全；2026-11-13 更新）

> 首版只按主题合并（`audit3-findings-triage.jsonl` 21 行）；本次把 DSH 全部 **86** 条 findings 逐条对到状态与唯一清单，确认无孤儿项。

- 机器可读：`work/lead/audit3-findings-map.jsonl`（86 行；字段 `id/severity/status/bf/round/note/update_note`）。
- **2026-11-13 更新**：E24–E34 落地（字形框线 23→0、strip 摘除、quad 扩张 bad_boxes→0、扫描 pre-cut 口径对齐、极细线 pre-cut：缺件 1,200→827、框线 153→1、内容 35→29）后，18 条 findings 状态上修：
  `fixed` **32**、`fixed-partial` **17**、`accepted` **1**、`deferred` **36**。
  `deferred` 仍表示已进唯一清单（`docs/BACKLOG.md` §10）并有轮次，**不代表已修**。
- 按级别的状态分布：

| 级别 | fixed | fixed-partial | accepted | deferred | 合计 |
|---|---|---|---|---|---|
| P0 | 5 | 1 | 0 | 0 | 6 |
| P1 | 14 | 7 | 1 | 13 | 35 |
| P2 | 8 | 4 | 0 | 16 | 28 |
| P3 | 5 | 5 | 0 | 7 | 17 |
| **合计** | **32** | **17** | **1** | **36** | **86** |

- 首版 BACKLOG 42 条按主题合并；逐条核对发现 9 条 P2/P3 细节无独立归属，已补 **BF-43..51**：
  BF-43 overlay 能力仍可触达（P1）、BF-44 闸/构建归因不可复现（P2）、BF-45 clean-tree/freshness 可绕过（P1）、BF-46 内容闸吞样（P2）、BF-47 audit 现行文档时点（P2）、BF-48 构建入口/缓存卫生（P2）、BF-49 scripts 保留判定（P2）、BF-50 worker 上限（P2）、BF-51 降级路径标记（P2）。
- GLM 审计的 14 项修复中，有 5 项不在 DSH findings 清单（`--limit` 吞字、font_package rmtree、quad 三套口径、mapping 重复字跨页覆盖、D20 登记等），仅记录在本文 §1；DSH/GLM 重叠项以 DSH-ID 为准。
- 状态未变：v2.6.1 仍**不可签收**（font_qa 同框 2 对 FAIL；包为旧 finalize 产物）。
