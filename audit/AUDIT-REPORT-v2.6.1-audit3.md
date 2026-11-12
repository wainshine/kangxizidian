# 第 3 代独立代码审计报告 · v2.6.1

> 审计日期：2026-11-12 20:16–20:45（Asia/Shanghai）
> 审计对象：仓库 HEAD `6f74a76`；交付字体 `work/font/build/KangXiKai-v2.6.1.ttf`（sha256 `c73c3023d30d7c4b14d04e420cb2d2661161962c60b5f5b22c51b8cf44659614`）；发布包 `release/KangXiKai-v2.6.1/` 与 `release/KangXiKai-v2.6.1.zip`
> 审计性质：**只读独立审计**——只发现问题与改进方案，**未修改任何既有文件、未做 git 写操作、未运行全量重建/全库扫描**。本次仅新增本报告与 `audit/AUDIT3-FINDINGS-v2.6.1.jsonl`（86 条机器可读 findings），证据在 `work/review/audit3/`。
> 审计组织：Lead + 4 名审计员（构建核心 S1–S3 / 门禁与打包发布 / 数据真源与闸数字 / 文档流程与合规），各自独立取证，Lead 对全部 P0 与关键 P1 做了独立复核（见 §8.4「Lead 独立复核记录」）。

---

## 0. 一页结论（TL;DR）

1. **字体产物本身可复现**：缓存命中重建 17,007 cached / 0 new / 0 skipped，输出与交付字体 **byte-identical**（sha `c73c3023…`）；目录侧 `SHA256SUMS` 26/26 通过。核心对外数字 **17,007 / 10,269/20,992=48.92% / 10,269/16,567=61.98% / 缺口 6,298 / 隔离 9** 全部复算一致。
2. **但「9/9 PASS」不能作为签收依据**：v2.6.1 的 9 步闸中**没有一步检查 TTF 输出字形**；项目自认的三处盲区闸（字形级框线、provenance 无拷贝、页级几何校验）全仓库确认不存在（GATE-03）。**已知坏字形的 v2.6.0 字体被塞进 v2.6.1 包副本后仍得到 `{"pass": true}`**（GATE-01），说明发布信任链是断的。
3. **发布包有两处结构性不一致**：finalize 先建 zip 后写最终报告/SHA，导致**对外 zip ≠ 目录包**（zip 内 gate-report 自称 `finalized:false`，7 步；目录为 `finalized:true`，9 步）；finalize 的终验结果不回写、attestation 硬编码 `true`（GATE-02 / LEAD-01）。
4. **下一步 CS2 会「修了等于没修」**：`font_build.py` 的 `_GEOM_PATH` 指向不存在的 `work/font/lead/page_geometry.jsonl`，S1 冻结几何**从未被 S3 消费**，构建改为每页从 PDF 现算；对 `work/lead/page_geometry.jsonl` 的页级修复重建后 TTF 可仍 byte-identical（BUILD-01）。同时 cache key 只含 `v350+page/half/char/box`，改几何/算法不 bump tag 会静默复用旧字形（BUILD-02）。
5. **QA 的「同框多标签」硬闸实际失效**：`font_qa.py` 读 manifest 不存在的 `r["char"]` 触发 KeyError 被 except 吞掉，永远 0 冲突；数据层实际存在 **2 对同框同轮廓字形**：沓/𦧟（08_0319R）、䛱/忠（10_0081R）——全库 17,007 字形中**仅此 2 组轮廓完全相同**（DATA-01）。
6. **三个闸数字是「阈值=观测值」的披露式 PASS**：内容 35≤35、缺件 1,200≤1,200、框线 153≤153，零余量；且 35 个内容缺损字中 **15 个 IoU<0.3**（近乎错字，含常用字 公 IoU=0.082），闸只计数不分级（GATE-07 / LEAD-02）。v2.6.0 的同类数字为内容 0、框线 60/60、缺件 592/700（口径不同，见 ERRATA E3，仅作参考）。
7. **发布包内文档数字错误**：`README.md:10` 写框线 **60/60**（同文件 :5 写 153，闸为 153/153），`QA.md:8` 写缺件阈值 **700**（闸为 1200）；`doc_check` 不校验这类数字仍 PASS；`01-changes.tsv` 还混入 v2.6.0 的 60 条框线记录（DATA-02/03、DOCS-05）。
8. **产品级事实（已知债，本轮确认）**：字体不含 U+4E00 **一**、U+738B **王**、U+6CD5 **法**；「高频缺 23」中仅 16 字在 6,298 缺口内，`在/教/清/你/為/裡/間` 因康熙字头使用异体（𡉈/敎/淸/…）不在目标表，且已存在的 敎/裏/閒 未做 D4 `mapped_traditional` 映射（LEAD-03/04、DATA-08）。**v2.6.1 不满足里程碑条件（这一点与项目自述一致）。**
9. 结论：**v2.6.1 不可签收；且在 P0 全清前，任何「9/9 PASS」不能作为里程碑依据。** 本轮共确认 **P0 5 组（6 条，含 1 条重复记录）/ P1 35 条 / P2 28 条 / P3 17 条**（去重后 64 个问题组，见 `audit/AUDIT3-FINDINGS-v2.6.1.jsonl`）。

| 严重度 | 条数 | 判定标准 |
|---|---|---|
| P0 | 5 组（6 条） | 会造成错误发布 / 假 PASS / 修复空转；**打正式包前必须修** |
| P1 | 35 | 系统性缺陷、口径错误、流程可被绕过；里程碑前应清零或明确披露 |
| P2 | 28 | 局部/低风险缺陷、文档失真、可维护性债 |
| P3 | 17 | 整洁度、口径小错、索引漂移 |

---

## 1. 审计范围与方法

### 1.1 范围

| 层 | 对象 |
|---|---|
| 构建核心 | `scripts/font_build.py`、`font_norm.py`、`make_block_mapping.py`、`build_page_geometry.py`、`page_frames.py`、`detect_blocks.py`、`fidelity_eval.py` 及相关数据 |
| 门禁/打包/发布 | `scripts/fast_gate.py`、`release_gate.py`、`font_package.py`、`font_qa.py`、`content_loss_gate.py`、`scan_missing_parts.py`、`scan_frame_escape.py`、`check_release_docs.py`、`jobrun.sh`、`release/KangXiKai-v2.6.1/`、`release/*.zip` |
| 数据真源 | `work/lead/page_geometry.jsonl`、`mapping_verified_all33.jsonl`、`mapping_block_v270.jsonl`、`work/font/build/manifest_v261.json`、`work/gates/`、`release` 数字文件、`work/seq/canonical.jsonl`、`data/ref/…/kx_full.xlsx`、`data/unihan` |
| 文档/流程/合规 | `AGENTS.md`、`docs/` 现行 31 份、`audit/` 顶层现行文件、`release` 包内材料、`scripts/_archive` 清单、历史审计挂账 |
| 审计对象边界 | 未审计：14 册 PDF 源图逐页内容、VLM/OCR 阶段历史代码、模型文件；未重跑：全库扫描、0 命中全量重建、历史版本闸 |

### 1.2 方法

1. **文档先行**：按 `AGENTS.md` 顺序读 `PROJECT-STATE / PIPELINE / WORKFLOW / DECISIONS / ERRATA`；
2. **代码对读**：把文档声明逐条落到代码行（file:line），找「文档说 X、代码做 Y」；
3. **可复现命令**：所有关键结论给可复制命令与输出摘录；数字一律用 python/fontTools/流式 JSONL 复算，不引用二手数字；
4. **对抗性验证**：不只读代码，实际构造「换包」「失败 finalize」「假 baseline 缓存」「同框两字」等实验；
5. **交叉复核**：4 名审计员独立取证，Lead 对全部 P0、Lead findings 与关键 P1 独立复跑/复核；团队间重复事实标注 `dedup_group` 而非重复计入。

### 1.3 本轮未做/局限

- 未跑全库缺件/框线重扫（预算 3 分钟/命令；且会写 work/），1,200/153 只复算既有产物并审计其口径与绑定；
- 未做 0 命中全量重建（~9 分钟），构建可复现性用「缓存命中重建 byte-identical + 17,007/17,007 cache 键命中」验证；
- 未读 `docs/_history/`、`audit/_history/` 全文（按项目约定只作考古，引用处已核对）；
- 人工视觉复核有限（审计员抽查 150+ 字阶段探针与 7 字 A/B），不能替代项目自己的 7 张复核图流程。

---

## 2. P0（5 组，打正式包前必须修）

### P0-01 发布门禁不校验「包内字体 = 被验证字体」，换包可假 PASS
**来源**：GATE-01（`auditor-gates`，verified）。

- **事实**：`release_gate.py:70-87` 只在 `--font` 上跑 `font_qa/version_stamp`；`:214-221` 只对包内文件算 SHA，**从不与 `--font` 比对**；`gate-report-v261.json` 里搜字体 sha = 0 次。
- **复现（审计实测）**：复制 v2.6.1 包到临时目录，把包内 TTF 换成**已知坏字形的 v2.6.0 TTF**（sha `0de02a16…`），执行 `release_gate.py --version 2.6.1 --font <v2.6.1字体> … --pkg-dir <包副本> --tag audit3swap` → **EXIT=0，`{"pass": true}`，6/6 PASS**；包内 `stats.json` 仍写 `c73c3023…`，无一步发现矛盾。证据：`work/review/audit3/gates/evidence/gate-report-audit3swap.json`、`swap-demo-facts.txt`。
- **影响**：v2.6.0 的坏字形可被重新封成「PASS 包」；`gate-report` 无法归因到具体字体，事后无法证明「包内字体=被验字体」。
- **改进方案**：
  1. `gate-report` 顶层记录 `font_sha256 / manifest_sha256 / mapping_sha256 / git_commit / argv`；
  2. finalize 前断言 `sha256(包内 TTF) == sha256(--font) == stats.json.sha256`，任一不符直接 ABORT；
  3. `check_release_docs` 增加「stats.sha256 vs 实际 TTF」校验。

### P0-02 finalize 顺序错误：发布 zip ≠ 目录包；对外报告未 finalize、终验声明硬编码
**来源**：GATE-02 + DOCS-01（两名审计员独立复核，verified）+ LEAD-01。

- **事实**：`release_gate.py:229-259` 先写 R1 报告并 rehash → **建 zip（:234-239）** → 之后才写 R2 最终报告并再次 rehash（:255-257），**zip 不重建**。且 R2 报告里 `"sha_verified_after_final_report": True` 是**硬编码常量**（`release_gate.py:253`），`pass` 也在 `sha_ok2` 计算前写定；终验结果只写 stdout。
- **v2.6.1 实测**：`release/KangXiKai-v2.6.1.zip`（18:27:23）内 `gate-report-v261.json` 为 **3949B/7 步/`finalized:false`**、`SHA256SUMS` 中该文件 hash `62077db2…`；目录内为 **5125B/9 步/`finalized:true`**、hash `454930c9…`。zip-vs-目录逐文件比对**仅这两个文件不同**（其余 25 个文件 SHA 相同，zip 内部自校验通过）。mtime 顺序：zip < 报告 < SHA。**历史基线 v2.5.8 同样命中**。证据：`audit/release-evidence/2.6.1-*` 与本次 `unzip -p` 复算。
- **影响**：「SHA 覆盖 gate-report、finalize 后不改包、zip 自检」三条声明同时不成立；只验 zip 的下游拿到的是**未 finalize 的报告**。
- **改进方案**：改为**单遍** finalize：写最终报告 → rehash → 校验目录 SHA → 建 zip → 解包复验 → 把 zip sha 记到包外清单；`attestation` 只写实测值，禁止硬编码；finalize 后再做一次只读终验。

### P0-03 三处盲区闸不存在：9/9 PASS 不含任何 TTF 输出字形检查
**来源**：GATE-03 + DATA-10（verified；项目已在 PROJECT-STATE/ERRATA E9 自认，但仍是本次签收的 P0 阻断项）。

- **事实**：
  - 全仓库无 `glyph_frame_gate / provenance_gate / page_geometry_gate` 实现（grep 仅命中文档「待实现」）；
  - `scan_frame_escape.py` 只接收 `--manifest/--out`，**渲染 PDF 源裁片**判「块内贯穿线」，**不读 TTF**（153 是源图口径，不是字形口径）；
  - `font_qa.py` 的 `render_bad` 判据对单条框线不敏感（合成「王+贯穿横线」实验不判坏，GATE-04）；
  - `content_loss_gate` 只查「掉墨」，不查「多墨/多线」；缺件扫描对加框线反而更干净；
  - `font_build.py:623` 仍保留 `--repair-overlay`；`work/lead/contours_override.json`（44,470B）仍在，构建会自动加载并对 `label_source=='from_v201_glyph'` 的字**直接注入旧 contours**（BUILD-07/DOCS-10）。
- **攻击路径（GATE-03 推演）**：用 overlay 回拷旧字形或直接换包 → 源图框线闸不变、内容闸只查掉墨、QA 对单条线不敏感、缺件扫描更干净 → 现有 9 步仍可 PASS。**v2.6.0 已实际发生过一次（9/9 PASS 但字形带框线）。**
- **改进方案（CS1 原计划，本轮确认必须做且设为必跑）**：
  1. **字形级框线闸**：直接扫 TTF 逐字轮廓/渲染，检测细长贯穿组件（水平/垂直长线、贴边整行整列、异常直线段）；
  2. **provenance 无拷贝闸**：逐字记录源 page/half/box + 源墨 hash + 轮廓 hash；与上一版字体做逐字轮廓比对，命中「旧字形 copy」即 FAIL；
  3. **页级几何校验闸**：quad 存在率/边界/block 包含关系/同页 box 尺寸方差；
  4. 三闸设为 `release_gate` **无 flag 必跑 step**（缺输入=FAIL），并加入 `fast_gate` 的轻量版本。

### P0-04 S1 页级几何产物从未被 S3 消费：CS2 的几何修复会「修了等于没修」
**来源**：BUILD-01（verified）。

- **事实**：`font_build.py:33` `WORK=ROOT/"work"/"font"`；`:259` `_GEOM_PATH=os.path.join(str(WORK),"lead","page_geometry.jsonl")` → 实际指向 **`work/font/lead/page_geometry.jsonl`（不存在）**；真实文件是 `work/lead/page_geometry.jsonl`。`:268-275` 文件缺失时**静默返回 `{}`**，随后 lattice/text_bbox/content_quad **每页从 PDF 现算**。`:348-360` 的 `fallback_quad_from_lattice` 只在「geometry 可加载」分支内 → **184 个单半版 quad 页的兜底永不执行**（实测 page_geometry 半版覆盖分布：双半版 3,342 / 单半版 184 / 无 343）。
- **证据**：`test -e work/font/lead/page_geometry.jsonl` → MISSING；构建日志无 `[geom] loaded` 行；`work/review/audit3/build-core/evidence/out_geometry.txt`。而 `build_recipe-v261.json` 却写 `geometry: work/lead/page_geometry.jsonl (g20261112-1)`。
- **影响**：CS2 计划中的「343 页无 quad / 184 页半版兜底」若通过修改 `page_geometry.jsonl` 实现，**重建仍按 PDF 现算，TTF 可保持 byte-identical**；交付包几何 provenance 不可复算；非缓存全量构建每页重复 PDF 渲染（lattice/bbox/quad 各一次）。当前字形未因此损坏（T1 抽查 4 页现算值与保存值一致），所以 P0 依据是**数据链断裂 + provenance 失真 + 下一步修复空转**，不是已发生字形错误。
- **改进方案**：`_GEOM_PATH` 改用 `ROOT/"work"/"lead"/…`；缺页 fail-loud（`stats.degraded_pages`，degraded>0 告警/失败）；`build_stats` 记录 geometry sha256/加载页数/fallback 数；重建前用冻结 geometry 快照做 A/B 证明被消费。

### P0-05 QA「同框多标签」硬闸失效，且已发布 2 对同轮廓字形（双真源）
**来源**：DATA-01（verified；Lead 独立复核：同框、KeyError、TTF 轮廓）

- **事实**：
  - `font_qa.py:231-244`：`bybox.setdefault(key,[]).append(r["char"])`；`manifest_v261` 记录实测字段只有 `{page,half,box,label_source}`（**无 `char`**）→ KeyError → `except: conflicts=[]` → **永远 0 冲突**；`qa-report-v261.json` 的 `same_box_conflicts=[]`。
  - 数据层实际 2 对同框：**沓/𦧟（08_0319 R，box 完全相同）**、**䛱/忠（10_0081 R，box 完全相同）**；TTF 轮廓哈希逐一比对：**全库 17,007 字形中仅此 2 组轮廓完全相同**（Lead 独立复算同结论）。
- **影响**：项目自定的 P0「同框多标签」硬闸形同虚设；发布字形存在 2 对双真源/标签错配（每对必有一字错标），17,007 个字面只有 17,005 个不同轮廓；内容闸对比新旧版（同框→ink 相同）不会触发。
- **改进方案**：`font_qa` 用 manifest 的 dict key 作为字符（或 `r.get("char")` 兜底）；加回归测试「同 box 两字必须 FAIL」；2 对已知错配回写 mapping 修正，并在 block 化后再次校验 `(page,half,box)` 唯一性。

---

## 3. P1（35 条，按主题；完整字段见 JSONL）

### 3.1 门禁可信度（16 条）

| ID | 问题 | 关键证据/复现 | 建议 |
|---|---|---|---|
| GATE-04 | `font_qa` `render_bad` 对单条框线不敏感（n_line_like≥1 单独不触发；框线并入字形时 ncomp 很小） | 合成「王+贯穿横线」不判坏 | 加字形级框线闸（P0-03） |
| GATE-05 | **可选闸 fail-open**：未给 `--prev/--scan/--frame-scan` 时对应 step 根本不存在，`all(steps)` 仍 PASS（实测 6/6 PASS）；`fast_gate --pkg-dir` 写错路径即静默跳过 doc/sha | `release_gate.py:120-186,194`；`fast_gate.py:120-131` | 必选闸硬编码；缺输入=FAIL；报告记录应有闸清单 |
| GATE-06 | **内容闸缓存 key 只含字体 sha12**，忽略 baseline/manifest/阈值；用不存在的 baseline 仍复用旧结果 PASS；`--reuse-content` 是伪复用且会覆写给定路径 | `fast_gate.py:19-23,73-90`；`release_gate.py:123-126`；`evidence/fast-gate-audit3-cachetest2.json` | key=(font,baseline,manifest,threshold,gate ver)；缓存只读；正式闸不复用内容缓存 |
| GATE-07 | **阈值=观测值**（35/35、153/153、1200/1200，零余量）且无单调性约束；`content_loss_gate` 的 rc=3（自身失败信号）被当 PASS；较上版（内容 0、框线 60/60、缺件 592/700，旧口径）表面放宽 | `gate-report-v261`；`audit/release-evidence/2.6.0-gate-report.json`；`release_gate.py:133-138` | 阈值常量+逐版单调不增；放宽需 owner 签字并写原因；rc=3 视为「有缺损」而非 PASS |
| GATE-08 | **失败不中止**：实测 `--version 2.6.9` → EXIT=1，但仍写 `gate-report(finalized:true)`、重算 SHA、重建 zip | `release_gate.py:200-272`；`evidence/gate-report-audit3fail.json` | `if not ok: return 1` 且不写包 |
| GATE-09 | gate-report **不可复现/不可归因**：无字体/manifest/扫描输入 sha、无 argv、无 git commit；扫描 step 只记 `tail:"reused"`；`work/jobs` 显示 gate 92s 完成而复用扫描各 26/28 分钟 → 1,200/153 来源不可复算 | `gate-report-v261`；`work/jobs/*.status` | 报告记录完整输入 sha/命令/耗时；扫描产物写侧车 meta |
| GATE-10 | `doc_check` 太弱：不比对 gate-report 数字；包内 README「60」/QA「700」与闸 153/1200 矛盾仍 PASS；finalize 前以 `--allow-missing-attestation` 首跑、最终包未重跑 | `check_release_docs.py:62-80` | 文档数字由 gate-report 自动生成；doc_check 校验数字集合 |
| GATE-11 | 包清单 vs WORKFLOW §8：**缺 `known-debt-v*.md` 与 `review/` 固定复核包**（01–06/ledger/diff-stats 全缺，仅根目录 2 个 01-changes 文件）；zip 在包外；多出 OFL/WORKFLOW/stats 等；README 却称随包 `review/` | `ls release/KangXiKai-v2.6.1` | 打包前按 §8 清单机检；`review/` 用脚本生成 |
| GATE-12 | `build_recipe` **自相矛盾**：记录 `git_commit=18944b9`、`cache_tag=v350`，但 `pipeline_sha256.font_build.py=10d5d376` 属于 **df068ff3（v341 时代）** 的版本（18944b9 应为 `c86279cd`）；其余 4 项与 18944b9 一致；仓库无该 schema 生成脚本 → 人工手写 | `build_recipe-v261.json`；`git show 18944b9:scripts/font_build.py \| shasum` | 脚本生成 recipe；release_gate 校验 recipe 与当前树一致；禁止手写入包 |
| GATE-13 | **clean-tree/freshness 形同虚设**：`--allow-dirty` 全绕；`.gitignore` 使 work/（mapping/geometry 唯一真源）与 release/ 不在视野；release_gate 无 clean-tree；freshness 仅 mtime（实测字体仅比 manifest 新 1 秒） | `font_package.py:417-424`；`.gitignore:8,13` | clean-tree 改为「工作树干净 + 构建输入 sha 记录 + recipe 可复算」 |
| GATE-14 | **人工闸未完成且与包不对应**：round-001 只有 2 个文件、无 v261 owner 标记；包内 `01-changes.tsv` 与 round-001 不同（block 102×98 vs 旧框 84×81）、PNG 相同；tsv 95 行=35+60（frame 60 为旧扫描） | `work/review/round-001/`；包内 tsv | 里程碑前按 WORKFLOW §6 出齐 7 张并绑定包内快照 |
| GATE-15 | **流程合规**：明示「过程版本，不签收」的 v2.6.1 位于 `release/` 且 `RELEASE-INVENTORY.tsv`/`audit/RELEASE-HISTORY.jsonl` 记为 PASS/keep；§10bis 的 `cs-*.jsonl`、`version-artifacts-v261.jsonl` 全缺 | `release/RELEASE-INVENTORY.tsv:3`；`ls work/changesets work/lead/version-artifacts*` | 候选移出 release/；补齐三件套；inventory 增加「状态=候选/正式」 |
| GATE-16 | 扫描闸**静默丢样与 fail-open**：`scan_frame_escape` 异常 `return []`（无覆盖率字段）；`scan_missing_parts` error 行不含 `missing` 不计 flagged；`--reuse-missing` 指向不存在文件时在阈值模式可 PASS | `scan_frame_escape.py:51,84`；`scan_missing_parts.py:42-43,132-133`；`release_gate.py:146-163` | 扫描产物含 n_expected/n_scanned/errors；覆盖率不足=FAIL |
| GATE-17 | `content_loss_gate` **容错吞样**：异常字不计 damaged；覆盖下限 98%（可静默漏约 340 字）；`n_checked` 打印 `len(chars)` 掩盖真实检查数 | `content_loss_gate.py:36-51,68-73` | 异常字单列 error 且计入失败；覆盖 100% 才允许 PASS |
| LEAD-02 | 内容闸 35/35 掩盖严重度：**15/35 字 IoU<0.3**（公 0.082、恄 0.082、𩺱 0.099、針 0.123…），单计数阈值无分级 | `work/lead/content-loss-gate-v261.json`（Lead 复算） | 分桶（IoU<0.3 / 0.3–0.7 / 掉墨<0.5）+ 常用字白名单；里程碑要求 IoU<0.3 桶=0 |

### 3.2 构建正确性（5 条）

| ID | 问题 | 关键证据/复现 | 建议 |
|---|---|---|---|
| BUILD-02 | **cache key 不含 geometry/算法版本**（只有硬编码 `v350+page/half/char/box`）；改几何或算法常量会全部命中旧轮廓、重建 sha 不变；与 PIPELINE §5/WORKFLOW §4 不变量冲突（PIPELINE:108 自己又写实际格式，自相矛盾） | `font_build.py:548-560`；17,007/17,007 全命中（Lead 复现） | key 加 geometry sha12、算法源码 sha/ALGORITHM_VERSION、pads/block 参数；cache 记录写组成 |
| BUILD-03 | **单字构建失败被静默跳过且 exit 0**：实测 2 字 mapping（万 box 在空白）→ `skipped 1`、`built … chars=1`、exit 0；无 `n_chars==17,007` 断言 | `font_build.py:465-476,583-589,658`；`evidence/fail_test.log` | skipped 非空写 failure report + 非零退出（`--allow-skip` 仅调试）；构建内断言字数并与 manifest 比对 |
| BUILD-04 | `make_block_mapping` **坐标系混用**：原图坐标 block 与旋转空间 quad box 直接求交 → **360/17,007 字（2.1%）box 越出 content_quad**（max 8.8px）；越界率 \|θ\|>0.3 页 4.40% vs \|θ\|≤0.05 页 0.00% | `make_block_mapping.py:75,80-82`；`page_frames.py:157-158,262-273`；`evidence/out_quad_frames.txt` | 统一坐标系（M/Minv）再求交；加 L0 断言 box⊆quad（容差 0.5px）必须 0 越界；重新生成 v270 |
| BUILD-06 / DOCS-09 | 文档「缓存命中重建 **~20 秒**」与实测差一个量级：**实测 242–251s**（缓存加载 16.1–16.6s + `build_font` 组装 234.6s，Lead 独立计时 16.57s+234.58s=251s）；根因首要嫌疑 `orient_contours` O(轮廓²×采样点)（150 字抽样外推 ≈172s/17,007 字） | `PROJECT-STATE:11`、`PIPELINE:108`、`AGENTS:33`；`evidence/out_assembly_timing.txt`；Lead 独立 benchmark | 文档改实测；构建分项计时；性能修复（把点-in-多边形嵌套判定改为 bbox/包围盒预筛或复用 fontTools 方向计算），目标回到 ≤60s |
| BUILD-07 / DOCS-10 | 文档称 restore/overlay「已删除、禁止恢复」，但主链仍保留：自动加载 `work/lead/contours_override.json`、`--repair-overlay`、`make_repair_overlay.py` 在现行目录；`contours_override.json` 44,470B（二/顔 旧轮廓）；`build_recipe` 却写 `no_restore_layer:true`；每次构建只 WARN | `font_build.py:487-505,542-546,623`；`build_recipe-v261.json` | 删除该分支与文件，或改显式 `--allow-override` 且记录+闸报红；文档同步 |

### 3.3 数据与闸数字（5 条）

| ID | 问题 | 关键证据 | 建议 |
|---|---|---|---|
| DATA-02 / DOCS-05 | 发布包内文档数字错误且自相矛盾：README:10 框线 60/60（实际 153/153，同文件 :5 写 153）；QA.md:8 / QA-v261.md:8 缺件阈值 700（实际 1200）；doc_check 仍 PASS | `release/KangXiKai-v2.6.1/README.md`、`QA.md` | 重打包前修正；披露段由 gate-report 自动生成；doc_check 校验闸数字 |
| DATA-03 | 包内 `01-changes.tsv` **串版**：frame_escape 60 行 == `frame_escape_scan_v260.jsonl`（v2.6.0），不是本版 153；content 35 行正确 | 包内 tsv；`work/lead/frame_escape_scan_v260.jsonl` | 复核表按本版扫描重新生成并与包内扫描同源 |
| DATA-04 / GATE-09 | 缺件/框线扫描产物**早于最终字体且以 `--reuse` 复用**：missing 18:06:48、frame 18:21:23 < 字体 18:23:53；扫描产物无 font sha；`work/gates/<sha12>/` 只有 content 缓存；PIPELINE「扫描结果按字体 SHA 缓存」实现不存在 | mtime；`release_gate.py:146-148`；`PIPELINE:123` | 扫描写 meta（font/manifest/mapping sha+命令+时间）；release_gate 校验 sha 命中否则重扫 |
| DATA-08 / LEAD-03 | 「高频缺 23」口径不纯：仅 **16/23 在 6,298 缺口内**；`在/教/清/你/為/裡/間` 不在 canonical 目标表（康熙字头用 𡉈/敎/淸/…，`kx_full.xlsx` 行 1418/11138/15399）；note「缺失字全在 6,298 缺口内」错误；敎/裏/閒 已有字形但 `mapped_traditional=0`（D4 设计未实施） | `work/lead/high_freq_gap.json`；`kx_full.xlsx`；TTF cmap；`stats.json` | 文档明确「目标表=康熙字头（异体）口径」；高频缺拆两桶；D4 映射路线给定论 |
| LEAD-04 | 字体**不含 U+4E00 一、U+738B 王、U+6CD5 法**（Lead 读 TTF cmap 确认）——「高频缺 23」的当前事实；产品级阻塞，非代码 bug | TTF cmap | 按 CS4/CS5 处理；完成前不满足 WORKFLOW §7 里程碑 |

### 3.4 文档/流程/合规（9 条）

| ID | 问题 | 关键证据 | 建议 |
|---|---|---|---|
| DOCS-02 | `VERSION-HISTORY.md:67` 与 `:69` **重复 v2.6.1 行**；:67 变更列复制自 v2.6.0；v2.5.9 排在 v2.6.x 后（违反 §10bis 每版一行） | `docs/VERSION-HISTORY.md` | 合并为一行并补变更集编号 |
| DOCS-03 / GATE-15 | §10bis「缺一不发版」三件套**全缺**：`work/changesets/` 仅 README+模板，无 `cs-*.jsonl`；无 `work/lead/version-artifacts-v*.jsonl`（v2.6.0/v2.6.1 都缺） | `ls work/changesets`、`ls work/lead/version-artifacts*` | 补 v2.6.0/v2.6.1 记录，之后每版强制 |
| DOCS-04 | `release/` 保留未签收过程包 v2.6.1，与 WORKFLOW §1/§11「候选不进 release、只留 v2.5.8」冲突；AGENTS/PROJECT-STATE/RELEASE-CLEANUP-PLAN 三处口径不一 | `ls release/` | owner 决定：撤回 `_withdrawn/` 或明示「基线候选」并统一文档 |
| DOCS-06 | **D16 披露回归**：v2.5.8 PROVENANCE 有 84.6%(n=13)/CI/约 1,500 字敞口 + `high-freq-gap-v258.json`；v2.6.1 全无（RELEASE-NOTES 只写「高频缺 23」无名单、包内无该文件） | `release/KangXiKai-v2.5.8/` vs `v2.6.1/` | 恢复精度敞口与高频缺口清单随包发布 |
| DOCS-07 | `audit/SELF-AUDIT-2026-11-12.md`（`audit/README` 列为「现行」）仍称 v2.6.1 包 `pass:false / SHA 21 行 / 6 文件比 zip 新 / 缺件 564 / 框线 60 / 52 版本 / HEAD 0aff3ac`，**已被 18:27 refinalize 与清理推翻**（现 HEAD 6f74a76、2 版/175MB、pass:true/SHA 26、1,200/153），无状态横幅 | `audit/SELF-AUDIT-2026-11-12.md:19-25,33-38` | 加「记录状态：已被 X 取代」横幅；现行结论只留一份 |
| DOCS-11 | 历史审计 7 项挂账**5 项未修**：scan_missing fail-open、`detect_blocks` docstring≠实现、审计台账停更在 v2.5.4、mapping 未脚本化、repair 拒收不落盘；另 2 项「已修」但 QA/PROVENANCE 静态数字与精度敞口**复发**（DOCS-05/06） | `audit/_history/AUDIT-VERIFICATION-LOG.md`；见报告 §6 | 建挂账台账并纳入每轮闸 |
| DOCS-13 / DOCS-20 | `audit/` 顶层「现行」文档阶段过期（ROOT-CAUSE/FRAME-ESCAPE 引用已删除的 `release/_withdrawn/`，无时点标注）；WORKFLOW 规定的 `_withdrawn/` 目录已被清理删除仍多处引用 | `audit/ROOT-CAUSE-FRAME-LOOP.md`、`FRAME-ESCAPE-*`；`docs/WORKFLOW.md` | 加状态横幅/修正路径；或归档到 `_history/` |
| DOCS-15 / DOCS-18 | 文档把已归档脚本写成现行路径（复现命令必失败）；docs 索引漏 `PROJECT-AUDIT-2026-11-12.md`、行数漂移 | `STRUCTURE:192`；`docs/README.md` | 路径改 `_archive/`；索引重算 |
| LEAD-01 | finalize **终验结果不落盘、attestation 硬编码 true**：R2 报告在 `sha_ok2` 之前写定，`sha_verified_after_final_report: true` 是常量 | `release_gate.py:249-257` | 见 P0-02 改进方案 |

> 说明：`GATE-11/DOCS-05` 的「包清单缺项/文档错数字」与 `DATA-02/03` 事实重叠，JSONL 用 `dedup_group` 标注，不重复计入统计。

---

## 4. P2 / P3（摘要；完整 45 条见 JSONL）

### 4.1 P2（28 条，按主题）

- **门禁/发布**：GATE-18 box_uniformity 只看 median（p95=3.73 被忽略）、版本校验子串匹配（`--version 2.6` 也过）；GATE-19 finalize 的 `_rehash`/zip 只处理顶层文件（若按 §8 加 `review/` 子目录，其内容既不入 SHA 也不入 zip）；GATE-20 包内物料与字体不同源（package_summary 记 21 条 vs 实际 26、content-loss 包内 schema 与闸输出不同、qa-report 早于最终字体 2h45m）；GATE-21 `jobrun` 退出码捕获有效但 status 不记命令行、日志不留存；GATE-22 包内 WORKFLOW.md 是旧快照（199 行 vs docs 210 行、缺 §10bis）；GATE-23 缓存算法版本手写 tag。
- **构建**：BUILD-05 worker 上限未强制（默认 8≠文档 10；`--workers 999` 可绕；线程 env 仅 `setdefault`）；BUILD-08（suspected）降级路径静默（geometry/quad/lattice 异常只打日志继续，无 stats 标记）。
- **数据**：DATA-09 缺件 1,200 是字符数（组件 1,538；19 个 frame-like 组件、84.8% 组件 bbox 越出 block，口径偏高）；DATA-11 content gate docstring 与实现判据不一致（0.80/0.55 vs 0.50/(0.80,0.70)）；DATA-12 343 无 quad 页对现字体**零影响**（337 非 body+6 body 无字；184 单半版/910 half 缺 lattice 同样零影响）——P1 债务表述误导优先级；DATA-13 DATA.md 滞后自相矛盾（v2.4.5/17,121/62.46%/6,219 与顶部 v2.6.1 并存；48,710 off-by-one；88.6% 无产物）。
- **文档/合规**：DOCS-12 SELF-AUDIT 宣布归档的 4 个死脚本仍在 `scripts/`（`apply_frame_fix/repair_frame_escape/page_artifacts/rebuild_mapping_boxes`，前二者互相 import）；DOCS-14 SCRIPTS.md 内部 62/141 vs 190/50/142/48 自相矛盾；DOCS-16 DATA.md v2.4.5 段+`data/base/LXGWWenKai-Regular.ttf` 是 **92B HTML 504 错误页**（OFL 替换未实施）；DOCS-17 专有字体实际依赖清单不完整：**12 个现行脚本**引用 Songti/Hiragino，文档只列 2–3 个，**发布包零披露**（`grep` 包内 md/json 无 Songti）；DOCS-19 release/ 根目录与 audit 汇总计数陈旧（package_summary 21/26、release-evidence 4/5）；DOCS-21 PIPELINE 称 content clip 在二值化前，代码在 `binarize` 后（`font_norm.py:860-863`）；LEAD-03 高频缺口径（见 3.3）；LEAD-04 产品缺 一/王/法（见 3.3）。

### 4.2 P3（17 条）

BUILD-09 `--manifest` 入口 NameError；BUILD-10 `--mapping` 仓库外绝对路径构建后 stats 构造崩溃；BUILD-11 生产 cache 混入 3 条合成条目（甲/乙/丙，17,010≠17,007）；BUILD-12 归一化文档不符（主簇 bbox vs 全轮廓 bbox+固定中心）；BUILD-13 PIPELINE 内部矛盾（pre-cut vs 形状启发式 trim/strip）+ `_shrink_box_past_bands` 死代码 + 7.7% box 非纯 2×2 块需注明「修复字除外」；DATA-14 PDF sha 校验按文档原样执行失败（NFC/NFD，内容 14/14 通过）；DATA-15 同 BUILD-11；DATA-16 PIPELINE「12 PDF」vs「14 PDF」、body 3,266 未注明口径（全库 body=3,528）；DATA-17 provenance-detail 与 manifest 同字段，无独立可复算证据；DATA-18 阈值=观测值（同 GATE-07，去重）；DOCS-22 默认 workers 8 vs 文档 10；DOCS-23 扫描耗时 10 vs 25 分钟（suspected）；DOCS-24 .gitignore 许可文本规则被后置规则覆盖（kx_full MIT LICENSE 未跟踪）；DOCS-25 高频缺口径（同 DATA-08，去重）；DOCS-26 `audit/_history/README` 把归档抗辩标「现行」；DOCS-27 14 个脚本仅 SCRIPTS.md 提及无调用方；DOCS-28 fast_gate 默认输出名与 WORK-MAP 记录不一致。

---

## 5. 数字核对（文档 vs 复算）

| 项目 | 文档（出处） | 复算（命令/产物） | 判定 |
|---|---|---|---|
| 字形数 | 17,007（PROJECT-STATE:9、PIPELINE:183） | manifest chars=17,007；TTF cmap=17,007；集合相等 | ✅ |
| 基本区覆盖 | 10,269/20,992=48.92% | 17,007 中 basic=10,269；48.9186% | ✅ |
| 目标字表 | 10,269/16,567=61.98% | canonical 唯一基本区=16,567（链路闭合到 kx_full 48,709 数据行→entry_sequence 48,708）；61.9847% | ✅ |
| 缺口 | 6,298 | canonical basic − manifest = 6,298 | ✅ |
| 隔离 9 | 刃/榍/法/紆/総/荹/仟/禦/絞 | 9 字均不在 cmap/manifest | ✅ |
| 内容闸 | 35（阈值 35） | `work/gates/c73c3023d30d/content_loss.json` damaged=35；抽 8 字重算一致；其中 15 字 IoU<0.3 | ✅ 数字 / ⚠️ 语义 |
| 缺件 | 1,200（阈值 1,200） | residual n=1,200 字符（组件 1,538；19 frame-like）；扫描早于最终字体、--reuse | ⚠️ 计数对、口径/绑定待修 |
| 框线逃逸 | 153（阈值 153） | residual n=153（149 页）；**源图级扫描，不读 TTF** | ⚠️ 计数对、非字形级 |
| 有/无 quad 页 | 3,526 / 343 | 3,869 行中 3,526 非空 / 343 空；另 184 页单半版 | ✅（对现字体零影响） |
| mapping | 5,695 半版、17,007 字 | 两 mapping 文件均 5,695 行、17,007 字；无重复 char、无 (page,half,char) 冲突；2 对同框 | ⚠️ 见 DATA-01 |
| 框尺寸 | 宽 99/102/103、高 95/98/100、σ≈0.4 | p5/p50/p95 精确复现；同页 σ 中位 w=0.400 h=0.433（p95 4.44/2.50 未披露） | ✅（p95 需注明） |
| 包内 SHA | 26 行覆盖 gate-report | 目录 26/26 通过；**zip 侧 gate-report/SHA 非最终** | ⚠️ 见 P0-02 |
| 缓存命中重建 | ~20 秒 | **实测 242–251s**（16.6s 加载 + 234.6s 组装） | ❌ 文档错（BUILD-06） |
| 包内 README 数字 | 框线 60/60 | 实际 153/153（同文件 :5 写 153） | ❌（DATA-02） |
| 包内 QA 数字 | 缺件阈值 700 | 实际 1200 | ❌（DATA-02） |
| 高频缺 23 | 全在 6,298 缺口内 | 仅 16/23 在缺口；7 字不在目标表（异体口径） | ❌（DATA-08/LEAD-03） |
| DATA.md | 标「现行」 | 顶部 v2.6.1 与 § 内 v2.4.5/17,121/62.46%/6,219 并存；48,710 off-by-one | ❌（DOCS-16） |
| 构建 commit/recipe | git_commit 18944b9 + cache v350 | `pipeline_sha256.font_build.py` 属 df068ff3（v341）；其余 4 项与 18944b9 一致 | ❌（GATE-12） |

---

## 6. 历史审计挂账复核（节选；全表见 `work/review/audit3/docs/summary.md` §四）

| 项 | 当时级别 | 现状 | 判定 |
|---|---|---|---|
| mapping 生成未脚本化 | P1（2 代） | 未修（仅 cleanup_work.py 引用产物） | 挂账 |
| overlay 无溯源字段 | P1 | 未修且升级：机制仍在、`contours_override` 未文档化 | 挂账/复发 |
| scan_missing_parts fail-open | P1 | 未修 | 挂账 |
| detect_blocks docstring≠实现 | P2 | 未修 | 挂账 |
| 审计台账/索引滞后 | P1 | `AUDIT-VERIFICATION-LOG` 停在轮次 6（v2.5.4） | 挂账 |
| repair_* 拒收清单未落盘 | P1 | 未修（只 print） | 挂账 |
| QA/PROVENANCE 静态数字失真 | P0（v2.5.4） | **复发**（v2.6.1 包内 README/QA 数字错） | 复发 |
| 精度敞口披露（V9） | P1（v2.5.4） | **复发**（v2.6.1 包内全无） | 复发 |
| build_recipe 可复核 | P1（v2.5.4） | 已建但哈希不实 | 部分修 |
| 版本盖章（V1） | P0（v2.5.4） | 已修（version_stamp PASS） | 已修 |
| 内容闸整字移除盲区（V3） | P1（v2.5.4） | 已修（char_diff + 量化隔离清单） | 已修 |
| tests/（R20） | P2（v2.5.4） | 未建（无 tests 目录） | 未修 |

---

## 7. 改进路线图（建议，按依赖顺序）

> 原则：先修「闸与信任链」，再修「数据链」，最后修「文档/物料」；**P0 全清前不打正式包**。每步验收标准必须可由命令复算。

### 阶段 A（立即，1–2 天）：让 PASS 重新有意义
1. **A1 发布信任链**（P0-01/02 + GATE-05/08/09）：gate-report 记 font/manifest sha+argv+commit；finalize 单遍（报告→SHA→zip→解包复验）；finalize 前断言包内 TTF==被验字体==stats.sha256；失败即中止不写包；`attestation` 只写实测值。
2. **A2 闸基线**（GATE-05/06/16/17）：内容/缺件/框线/几何改为必跑 step；缓存 key 完整化并只读；扫描产物写 meta（输入 sha+覆盖率+错误数）；补齐 `known-debt`/`review/` 清单机检。
3. **A3 阈值纪律**（GATE-07/18 + LEAD-02）：阈值常量集中定义；逐版单调不增；放宽需 owner 签字入报告；内容闸分严重度桶，里程碑要求 IoU<0.3 桶=0。
   - 验收：用「换包」「假 baseline」「失败 finalize」三个负向测试全部 FAIL。

### 阶段 B（CS1，2–4 天）：补三处盲区闸
1. 字形级框线闸（TTF 输出轮廓/渲染级）；
2. provenance 无拷贝闸（源墨 hash + 轮廓 hash + 与旧版逐字比对）；
3. 页级几何校验闸（quad 边界/block 包含/同页尺寸方差）；
4. `font_qa` 同框硬闸修复（P0-05）+ `skip`/降级路径 fail-loud（BUILD-03/08）；
5. 三闸设为 `release_gate` 无 flag 必跑。
   - 验收：v2.6.0 字体（已知坏字形）作为负样本必须 FAIL；v2.6.1 正样本三闸通过并输出明细。

### 阶段 C（CS2/CS3/CSS，1–2 周）：修构建/数据链
1. `_GEOM_PATH` 修正 + geometry 真正被消费（P0-04）；build_stats 记 geometry sha；用冻结几何做 A/B；
2. cache key 加 geometry/算法版本（BUILD-02），并 bump tag 后做一次 0 命中全量重建验证；
3. `make_block_mapping` 坐标系修复（BUILD-04）→ 重生成 `mapping_block_v270` → 360 字越界清零；
4. mapping 指派审计 content 35→0（先清 IoU<0.3 的 15 字）；2 对同框错配（P0-05）回写修正；
5. 高频缺 23 / 隔离 9 / 100 字签核（CS5）：含 一/王/法；D4 `mapped_traditional` 与异体口径给定论并在 README 披露。
   - 验收：框线逃逸=0（字形级）、缺件 triage 完成、内容闸=0、TTF 不含重复轮廓。

### 阶段 D（发布物料/流程收口）
1. 文档数字全部由脚本生成/校验（README/QA/PROVENANCE 的闸数字、覆盖、缺口）；
2. `VERSION-HISTORY` 去重、`§10bis` 三件套补齐、SELF-AUDIT 加状态横幅、`DATA.md`/`SCRIPTS.md`/`STRUCTURE.md` 修正、`docs/README` 索引重算；
3. `release/` 只放正式包（v2.6.1 撤回或明示状态）；`build_recipe` 脚本化；clean-tree 改为「工作树干净+输入 sha 记录」；
4. 性能：`orient_contours` 优化，缓存命中重建回到 ≤60s，文档改实测；
5. 合规：Songti 依赖清单与披露补齐，或替换 OFL；`data/base` 占位文件清理；`repair/overlay` 能力删除或显式门禁。
   - 验收：`release_gate` 全闸 PASS + 7 张复核图 + owner 签核 + 文档数字机检 0 差异。

---

## 8. 附录

### 8.1 复现命令索引（关键）

```bash
cd /Users/wainshine/newAI/kangxizidian

# 缓存命中重建 + sha（~250s；应 17,007 cached/0 new/0 skipped，sha=c73c3023…）
FONT_BUILD_WORKERS=4 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python scripts/font_build.py --mapping work/lead/mapping_block_v270.jsonl \
  --out /tmp/audit3_rebuild.ttf --version 2.6.1
shasum -a 256 /tmp/audit3_rebuild.ttf work/font/build/KangXiKai-v2.6.1.ttf

# 快闸（7 项；实测 PASS，~83s）
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.1.ttf \
  --manifest work/font/build/manifest_v261.json --version 2.6.1 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json \
  --pkg-dir release/KangXiKai-v2.6.1 --content-max-damaged 35 --tag audit3-lead

# 目录侧 SHA（26/26 OK）
cd release/KangXiKai-v2.6.1 && shasum -a 256 -c SHA256SUMS

# P0-02：zip 内 gate-report 非最终（两文件 hash 不同）
cd release && for f in gate-report-v261.json SHA256SUMS; do
  shasum -a 256 KangXiKai-v2.6.1/$f
  unzip -p KangXiKai-v2.6.1.zip KangXiKai-v2.6.1/$f | shasum -a 256
done

# P0-04：几何路径不存在
test -e work/font/lead/page_geometry.jsonl && echo EXISTS || echo MISSING

# P0-05：同框硬闸（应为 2 对；TTF 全库仅这 2 组同轮廓）
.venv/bin/python - <<'PY'
import json,sys; sys.path.insert(0,'work/font/_pylibs')
from fontTools.ttLib import TTFont
m=json.load(open('work/font/build/manifest_v261.json'))['chars']
from collections import defaultdict
d=defaultdict(list)
for ch,r in m.items(): d[(r['page'],r.get('half'),tuple(r['box']))].append(ch)
print([v for v in d.values() if len(v)>1])
f=TTFont('release/KangXiKai-v2.6.1/KangXiKai-Regular-v2.6.1.ttf'); import hashlib
sig=defaultdict(list)
for cp,gn in f.getBestCmap().items():
    g=f['glyf'][gn]
    if g.numberOfContours==0: continue
    s=hashlib.sha256((str(list(g.endPtsOfContours))+str(list(g.coordinates))+str(bytes(g.flags))).encode()).hexdigest()
    sig[s].append(chr(cp))
print({k:v for k,v in sig.items() if len(v)>1})
PY

# 换包假 PASS 演示（只在 /tmp 做，不碰 release/）
cp -a release/KangXiKai-v2.6.1 /tmp/swappkg
cp work/font/build/KangXiKai-v2.6.0.ttf /tmp/swappkg/KangXiKai-Regular-v2.6.1.ttf
.venv/bin/python scripts/release_gate.py --version 2.6.1 \
  --font work/font/build/KangXiKai-v2.6.1.ttf --manifest work/font/build/manifest_v261.json \
  --prev-manifest work/font/build/manifest_v258.json --pkg-dir /tmp/swappkg --tag audit3swap
# → {"pass": true}，6/6 PASS（GATE-01）
```

### 8.2 证据与产出索引

| 路径 | 内容 |
|---|---|
| `audit/AUDIT3-FINDINGS-v2.6.1.jsonl` | 86 条机器可读 findings（id/severity/title/area/evidence/repro/impact/fix/confidence/auditor/dedup_group） |
| `work/review/audit3/build-core/` | S1–S3 审计：findings 13 条、summary 85 行、evidence 探针脚本与输出（geometry/quad/box/assembly/fail-test） |
| `work/review/audit3/gates/` | 门禁/打包审计：findings 23 条、summary 82 行、evidence（换包 PASS 报告、失败 finalize 报告、假 baseline PASS 报告） |
| `work/review/audit3/data/` | 数据真源审计：findings 18 条、summary 81 行（含文档数字 vs 复算对照表）、scratch 复算脚本 |
| `work/review/audit3/docs/` | 文档/流程/合规审计：findings 28 条、summary 66 行（含历史挂账复核表） |
| `audit/release-evidence/` | 各版本 gate-report/SHA 历史留档（本次引用 2.6.0/2.6.1） |
| `work/gates/c73c3023d30d/content_loss.json` | 内容闸缓存（35 行明细见 `work/lead/content-loss-gate-v261.json`） |

### 8.3 审计员分工与产出

| 成员 | 任务 | 结论概览 |
|---|---|---|
| lead | 范围/复核/汇总 | P0 全部独立复核；新增 LEAD-01…04；报告与 JSONL |
| auditor-build | task-1 构建核心 S1–S3 | P0×1（几何断链）/ P1×3 / P2×4 / P3×5；缓存重建 byte-identical 正向确认 |
| auditor-gates | task-2 门禁与打包发布 | P0×3（换包/zip/盲区闸）/ P1×14 / P2×6；换包、失败 finalize、假 baseline 三组对抗实验 |
| auditor-data | task-3 数据真源与闸数字 | P0×1（同框硬闸+双真源）/ P1×6 / P2×6 / P3×5；核心数字全部复算一致 |
| auditor-docs | task-4 文档/流程/合规 | P0×1（zip，独立复核）=GATE-02 / P1×10 / P2×10 / P3×7；历史挂账复核 |

### 8.4 Lead 独立复核记录（防止「只信队友」）

以下关键结论由 Lead 独立跑过/读过，未仅依赖审计员报告：

1. **缓存命中重建**：`/tmp/audit3_lead.ttf` sha=`c73c3023…`，与交付字体 `cmp` 相同；`cached=17007 new=0 skipped=0`；独立 benchmark：加载 16.57s + `build_font` 234.58s（BUILD-06）。
2. **zip≠目录**：`unzip -p` 取 zip 内 `gate-report-v261.json` → `attestation.finalized=false`；目录 → `true`；两文件 hash `62077db2…` vs `454930c9…`；zip 内部 SHA 自校验通过（P0-02）。
3. **几何路径**：`work/font/lead/page_geometry.jsonl` MISSING；`work/lead/page_geometry.jsonl` 3,869 行；半版覆盖分布 3,342/184/343（P0-04）。
4. **同框闸**：manifest 两对同 page/half/box；`font_qa.py` 代码中 `r["char"]` → KeyError；TTF 全库轮廓哈希仅 2 组重复，恰为这两对（P0-05）。
5. **换包门禁**：通读 `release_gate.py` 全文确认无「包内 TTF vs --font」比对；核对 `evidence/gate-report-audit3swap.json` 6/6 PASS（P0-01）。
6. **build_recipe 哈希**：`git show df068ff3:scripts/font_build.py | shasum` = `10d5d376…`，`18944b9` = `c86279cd…`（GATE-12）。
7. **阈值对比**：`audit/release-evidence/2.6.0-gate-report.json` 实测 content 0、frame 60/60、missing 592/700（GATE-07）。
8. **内容闸严重度**：35 行中 IoU<0.3 共 15 字，最低 恄 0.082/公 0.082（LEAD-02）。
9. **产品缺口**：TTF cmap 无 一/王/法；`kx_full.xlsx` 行 1418=𡉈、11138=敎、15399=淸；字体有 敎/裏/閒 但 `mapped_traditional=0`（LEAD-03/04）。
10. **SELF-AUDIT 过期**：其 `pass:false / SHA 21 / 564 / 60 / 52 版本 / HEAD 0aff3ac` 与当前 `pass:true / SHA 26 / 1,200 / 153 / 2 版本 / 6f74a76` 对照（DOCS-07）。

### 8.5 审计声明

- 本审计**只发现问题、提出改进方案，不修改代码/数据/文档**；审计期间 `git status` 对 tracked 文件保持干净（新增的仅为 `audit/AUDIT-REPORT-v2.6.1-audit3.md`、`audit/AUDIT3-FINDINGS-v2.6.1.jsonl` 与 `work/review/audit3/**` 证据，是否入库由 owner 决定）。
- 对 `release/` **未运行 finalize / font_package**；换包与失败 finalize 演示均在临时副本 `/tmp` 或 `work/review/audit3/gates/tmp/` 进行；未重跑全库扫描与 0 命中全量重建（理由见 §1.3）。
- 所有 P0/P1 均有可复制 repro；若复算结果与本文不一致，以复算为准，请记入 `docs/ERRATA.md`。

---

*报告生成：2026-11-12 · 第 3 代独立代码审计 · 全部证据可复算*
