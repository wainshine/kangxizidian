# PROJECT-AUDIT · 接手可行性 / 文档-代码一致性 / 上下文污染 / 缺失补齐（2026-11-12）

> 回答四个问题：新会话能否只靠文档+代码理解项目？文档和代码匹配吗？哪些内容污染上下文？还缺什么？
> 另附：从馆阁体项目继承的规范中，哪些丢了、已补哪些、还差哪些。

---

## 0. 结论摘要

| 问题 | 结论 |
|---|---|
| 新会话能否接手 | **可以**（本次整理后）；首屏读 `AGENTS.md` → `PROJECT-STATE.md` → `PIPELINE.md` 共 **363 行**即可开工；完整现行文档 17 份/2,090 行，历史 14 份/3,945 行已隔离 |
| 文档-代码匹配 | 实测 219 条现行文档引用，修正 12 类不一致；剩余 15 条均为「已删除路径/占位符」，已在文档标注；代码侧改动（线程守卫）经缓存命中构建 + 快闸验证 |
| 上下文污染 | 已从「27 份文档混放（5,743 行）+ audit 51 份历史」改为「现行 17 份（2,090 行）+ 历史 14 份（3,945 行）+ audit/_history 51 份」；新会话不必读历史 |
| 缺失补齐 | 补了 5 个关键文件（AGENTS/PROJECT-STATE/GLOSSARY/ERRATA/README 索引）+ DATA 现行化 + 线程守卫 + 引用修正；仍缺 4 项（见 §5） |

---

## 1. 接手可行性（新会话怎么读）

**首屏（363 行，约 10–15 分钟）**：
1. `AGENTS.md`（122 行）：硬规则/当前状态/最短验证/发布流程/常见坑
2. `docs/PROJECT-STATE.md`（约 90 行）：30 秒现状、已知缺陷、下一步、如何独立审计
3. `docs/PIPELINE.md`（204 行）：管线架构/原理/流程/参数/复现命令

**完整现行文档（17 份 / 2,090 行）**：再加 WORKFLOW、VERSION-HISTORY、WORK-MAP、DECISIONS、GLOSSARY、ERRATA、DATA、SCRIPTS、WORK-CLEANUP(+IMPACT)、CANONICAL-ORDER、STRUCTURE、HEADERS。

**明确不需要读**：`docs/_history/`（14 份/3,945 行历史编年）、`audit/_history/`（51 份历史审计）、聊天记录。
历史结论已提炼进 VERSION-HISTORY（逐版摘要）与 ERRATA（作废说法），需要考古再查。

**关键：数据文件必须在位**（文档只讲方法，真源是数据）：
`work/lead/page_geometry.jsonl`、`mapping_verified_all33.jsonl`、`mapping_block_v270.jsonl`、`work/font/build/manifest_v261.json`、`cache v350`、`pdf_map.json`、字体 v2.6.1（均在，清理后已验证缓存命中重建 sha 一致）。

---

## 2. 文档-代码一致性审计（实测）

### 2.1 已修正（本轮）
| 问题 | 修正 |
|---|---|
| `PIPELINE.md` 写「12 卷 PDF」 | 实际 **14 个 PDF（00–13）**，3,869 页；已改 |
| `PIPELINE.md` 引用 `scripts/lead_page_roles.py`（已归档） | 改为 `scripts/_archive/lead_page_roles.py`（产物 work/lead/page_roles.jsonl） |
| `SCRIPTS.md` 写「190 脚本/50 现行/142 归档」 | 实际 **203/62/141**；顶部加「写于 v2.5.6、现行 v2.6.1」时效注记 |
| `DATA.md` 停在 v2.4.5（17,126/62.46%） | 顶部加 v2.6.1 现行状态 + 字体许可规则；14 册/12GB 描述核实正确 |
| `DECISIONS/HEADERS/STRUCTURE` 引用已归档脚本 | 统一改 `_archive/` 路径 |
| `HEADERS.md` 称「书眉是现行管线输入」 | 改为「数据层参考（历史校验用），现行构建不依赖」 |
| `PROMPT.md` 是馆阁体模板（05_select/13_qa/20,992 承诺） | 移入 `_history/`，加横幅说明属模板 |
| 13 份历史文档路径引用（20 个文件） | 批量改写 `docs/X` → `docs/_history/X`；Markdown 链接断链检查 **0** |
| `docs/README.md` 索引过时（还写 v2.6.0） | 重写为现行/历史两级索引 + 读文档顺序 |
| `WORK-CLEANUP*`/`WORKFLOW` 引用已删除目录 | 标注「已删除/占位符」；引用检查剩余 15 条全部属此类 |

### 2.2 仍存在但已标注
- `SCRIPTS.md` 内容基线仍是 v2.5.6（已加注记，未重写全文；现行链路以 PIPELINE 为准）；
- `docs/_history/*` 内部仍有对旧版本的描述（历史文档，按约定不改写）；
- `HEADERS.md` 的读数方法属历史校验链，非当前构建链。

### 2.3 代码侧验证（本轮改动后）
- 缓存命中重建：**17,007 cached / 0 new**，sha = `c73c3023…`（与发布字体一致）；
- `fast_gate`：**7/7 PASS**（字体 QA/版本/字符 diff/内容闸/box 均匀性/文档/SHA）。

---

## 3. 上下文污染审计（前后对比）

| 项 | 之前 | 现在 |
|---|---|---|
| `docs/` 根文档 | 27 份 / 5,743 行（现行与历史混放） | **16 份 / 2,090 行**（+ 根目录 AGENTS.md） |
| `docs/_history/` | 无 | **14 份 / 3,945 行**（历史归档，顶部有状态横幅） |
| `audit/` 顶层 | 56 份混放 | 6 份现行 + `_history/` 51 份归档 |
| 新会话必读 | 无明确入口，需翻聊天/编年 | 363 行首屏，明确读序 |

**主要污染源（已隔离）**：`COUNTS.md` 1,095 行、`SESSION-HANDOFF.md` 439、`V3-STATUS.md` 432、`DETECTOR-V2.md` 426、`FONT-BUILD.md` 359、`PROMPT.md` 342、`TAKEOVER/PROBE/DETECTOR` 等——均为历史编年/旧设计，已移入 `_history/`。

---

## 4. 从馆阁体项目继承的规范：哪些丢了、现在补了什么

| # | 馆阁体规范 | 我们之前 | 现在 |
|---|---|---|---|
| 1 | **AGENTS.md 入口约束**（先读什么/硬规则/常见坑） | **缺失** | ✅ 新增 `AGENTS.md` |
| 2 | **PROJECT_STATE**（30 秒现状+已知缺陷+独立审计方法） | 散落各处 | ✅ 新增 `docs/PROJECT-STATE.md` |
| 3 | **GLOSSARY 唯一术语源**（+ 术语自动检查器 `97_check_terms.py`） | 无术语表 | ✅ 新增 `docs/GLOSSARY.md`；❌ **自动检查器未实现** |
| 4 | **ERRATA 勘误**（已发布/历史文档不再更正的错误） | 无 | ✅ 新增 `docs/ERRATA.md`（11 条） |
| 5 | **禁止专有/商业字体（含系统字体）** | ❌ 违反：Songti/Hiragino 用于 QA 对照、缺件参考、复核图 | ⚠️ 政策写入 AGENTS/ERRATA/DATA；**替换未完成**（待换 OFL 字体） |
| 6 | **并发上限（≤10 线程/20 核）+ `cv2.setNumThreads(1)` + OMP env** | ❌ 未设守卫，曾跑满 CPU | ✅ AGENTS 规则 + `jobrun.sh` env + 10 个管线脚本加守卫；构建/快闸已复验 |
| 7 | **agent 不做 git 写操作（由 owner 提交）** | ❌ 会话里多次自行提交 | ✅ 规则恢复，写入 AGENTS §1 |
| 8 | **发布流程固定顺序 + 发布前核对数字表** | 部分有（release_gate），但曾反复打包 | ✅ AGENTS §4 + WORKFLOW §7 + clean-tree/SHA 闸 |
| 9 | **DATA：来源/许可/校验和/重建链** | 部分过期（v2.4.5） | ✅ 更新 v2.6.1 现行状态；⚠️ 影印来源信息仍待 owner |
| 10 | **命名/版本规范**（版本号不带线名、术语禁用词） | 部分（D18） | ✅ AGENTS/GLOSSARY/WORKFLOW 覆盖；❌ 术语检查器缺 |
| 11 | **人工资产与生成图分开**（馆阁体踩过坑） | 未明文 | ✅ 写入本项目常见坑（复核图由脚本生成，人工图单独命名） |
| 12 | **最短验证命令** | 有零散命令 | ✅ AGENTS §3 + PROJECT-STATE §5 |
| 13 | **检查点保留规则** | 不适用（无训练） | 对应物 = work 痕迹保留规则（WORK-MAP/CLEANUP 已写） |
| 14 | **实验记录（EXPERIMENTS）** | 无独立表 | ✅ VERSION-HISTORY + COUNTS（够用） |

---

## 5. 仍缺 / 待办（按优先级）

| 优先级 | 缺口 | 计划 |
|---|---|---|
| P0 | 字形级框线闸、provenance 无拷贝闸、页级几何校验闸 | CS1（下一轮） |
| P0 | 术语自动检查器（GLOSSARY 落地为 CI 检查） | CS1 顺带，脚本 `scripts/check_terms.py` |
| P1 | 专有字体替换（Songti → OFL 字体，或去掉参考依赖） | CS1/材料轮 |
| P1 | 缺件扫描邻字隔离修正（1,200 偏高）；343 页无 quad | CS1/CS2 |
| P1 | mapping 生成链脚本化（当前只有数据+脚本碎片） | 长期，保留全部 map JSON 为证据 |
| P1 | 影印来源/许可信息（DATA §1 待补） | 需 owner 提供 |
| P2 | 100 字签核、高频缺 23、隔离 9 | CS4/CS5 |
| P2 | 历史文档内部引用仍指向旧名（历史不改写，不影响现行） | 不处理 |

---

## 6. 本轮改动清单（未提交）

- 新增：`AGENTS.md`、`docs/PROJECT-STATE.md`、`docs/GLOSSARY.md`、`docs/ERRATA.md`、`docs/PROJECT-AUDIT-2026-11-12.md`、`work/changesets/_TEMPLATE.json`；
- 重写：`docs/README.md`（现行/历史两级索引）；
- 归档：`docs/COUNTS/V3-STATUS/SESSION-HANDOFF/TAKEOVER/PROBE/T2-EXP30/HEADWORD-COVERAGE/OCR-OPTIONS/DETECTOR-V2/FONT-BUILD/VENDORED/PLAN-v2.6/RELEASE-PLAN/PROMPT` → `docs/_history/`（14 份；20 个文件引用路径已改写，0 断链）；
- 修正：`PIPELINE/SCRIPTS/DATA/DECISIONS/HEADERS/STRUCTURE/WORK-CLEANUP-IMPACT`；
- 代码：`jobrun.sh` 加线程 env；`font_build/font_norm/page_frames/detect_blocks/build_page_geometry/make_block_mapping/scan_missing_parts/scan_frame_escape/content_loss_gate/font_qa` 加并发守卫（`cv2.setNumThreads(1)` + OMP env）；
- 验证：缓存命中重建 sha 一致 + fast_gate 7/7 PASS。
