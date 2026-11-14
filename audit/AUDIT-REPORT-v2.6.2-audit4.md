# 第 4 代独立代码审计报告 · v2.6.2

> 审计日期：2026-11-14 08:35–09:25（Asia/Shanghai）
> 审计对象：仓库 HEAD `d6a6229`（clean）；交付字体 `work/font/build/KangXiKai-v2.6.2.ttf`（sha256 `a8bb87d9c4a623d5fe88ae55c2f710a36827052c7cd3594fe70113f56ca18d5b`，17,005 字）；正式包 `release/KangXiKai-v2.6.2/` 与 `release/KangXiKai-v2.6.2.zip`（包内 gate-report 记构建 commit `8622ba8`，finalize 17 步 PASS）。
> 审计性质：**只读独立审计**——只发现问题与改进方案，**未修改任何既有代码/数据/文档，未做 git 写操作**。本次仅新增本报告、`audit/AUDIT4-FINDINGS-v2.6.2.jsonl` 与 `work/review/audit4/**` 证据；对抗实验均在 `/tmp` 包副本进行，`release/` 未被改动；审计期间对 released 包只做了只读校验。
> 审计组织：Lead + 4 名审计员（构建核心 / 门禁与对抗 / 数据真源与数字复算 / 文档流程与合规），Lead 对全部 P1 与关键实验独立复核（见 §9.4）。

> **记录状态（2026-11-14 09:45，owner 侧复核后追加；原文不改写）**
> 本报告是 **08:35–09:25 审计时点**的记录。复核人反馈及我方 09:40–09:50 复验后，以下 6 处表述需按此注阅读（结论不撤销，口径收紧）：
> 1. **`.DS_Store`（§2.1 / LEAD4-004）**：owner 已于 09:20 前删除；当前目录包 = zip = **33** 文件、SHA 覆盖 32，已一致。原「目录 34 vs zip 33」是审计时点事实；设计缺陷（打包/校验无文件 allowlist、finalize 后可被 Finder 写入且无检测）仍成立。
> 2. **finalize 失败改写包（G5 / LEAD4-002）**：需限定阶段——**pre-finalize 判定失败**会提前 return、`package_touched=false`（实测）；只有**进入 finalize 块之后**的失败（如 `pkg_font_sha`）才会重写 SHA/zip/包内报告并写入 `finalized:true` 的 `pass:false` 报告。原文「失败仍改写包」仅指后者。
> 3. **扫描证据被重写（G2）**：因果补充——其中一部分是**发布后审计/复核自跑**（E38 修复后重扫，sidecar created_utc 00:18/00:27Z）造成，不应理解为「发布时证据被替换」。设计缺陷仍成立：`work/lead` 证据可变、gate-report 不记产物 sha、后续任何重跑都会让当时字节不可证（GATE-403 TOCTOU 同源）。
> 4. **缓存命中 3m50s（原 §5/§9 的证据论证）**：审计时对「缓存全命中 = byte 级复现替代证据」的使用**撤回**。复核后实测：当前 `_CACHE_VER=61657834_…` 下 3 页样本构建 `cached=5/new=0`（缓存可用）；重构后首次全量重建 `cached=0`（402s）可由「脚本重构改变 `_CACHE_VER`、新缓存目录首次为空」解释，待 BF-60 用一次全量缓存命中重建确认耗时后再恢复该口径。可复现性的主证据改为：owner 侧全量重建 sha=`a8bb87d9…` 与正式包一致 + audit4 的 36 字逐点相同。**另：`build_stats` 本次样本记 `dirty=true status_n=2` 系本审计新增的 2 个 untracked 文件导致——接手后需先提交/归档 audit4 产物，否则 clean_tree 闸会拦 v2.6.3 打包。**
> 5. **617 vs 3,351（G6）**：两个数都保留——3,351 = 精确 glyf 轮廓差异；617 = 旧候选 b73e9f01 的阈值筛集。新维护者不得把 617 当变化规模。
> 6. **缺件 165 的 prune 归因（G7）**：文档侧仍未全部改（`ERRATA E37`、`KNOWN-DEBTS`、`PLAN-v2.6.3`、`BACKLOG BF-06` 仍写 prune 归因）→ 这是**已确认的文档错误**，接手第一批应改正，不得按旧归因去调 `prune_edge_contours`。
> 7. **终验证据（LEAD4-001）**：`work/lead/gate-report-v262.json` 已由 owner 从正式包恢复为 canonical（与包内同 sha `1288aa88…`）；但它是包内格式、不含 `sha_final_ok/zip_ok`，终验字段仍应另立不可变记录（结论保留，表述改为「未以不可变格式留档」）。
> 8. **v2.6.3 首批范围**：复核建议改为 **BUILD-404（mapping 生成器坐标）+ 证据链修复** 先行，BF-06/BF-54 顺延 v2.6.4；本报告路线图 §8 的 Phase A 因此升级为「第一批」，并需在 `docs/BACKLOG.md` 补 **BF-61 = BUILD-404**（当前无对应条目）。

---

## 0. 一页结论（TL;DR）

1. **字体产物与发布包本体没有发现 P0 级缺陷。** 包内 `SHA256SUMS` 32/32 通过、`unzip -t` 通过、zip 与目录包（除 finalize 后新增的 `.DS_Store`）逐文件一致；zip 内 gate-report 已是 `finalized:true`（上代 P0-02 的 zip≠目录问题在 v2.6.2 已修复）；包内 TTF sha = 候选字体 sha = 被 `pkg_font_sha` 步校验的字体 = build_recipe/stats 记录值。核心对外数字**全部复算一致**：17,005 字（+`.notdef` 使 glyph order=17,006）、基本区 10,267/20,992=**48.91%**、目标表 10,267/16,567=**61.97%**、缺口 **6,300**、隔离 9、empty_assign **1,173**（669/504/40 且含 `01_0006 L「一」`）、同框 0、TTF 轮廓重复 0。Lead 独立复跑 `fast_gate` **8/8 PASS（55s）**。
2. **但「发布可信链 / 证据链 / 对外口径」仍不达标，这是本代审计的主结论。** 共确认 **P1 15 组（20 条）**，集中在 5 个主题：
   - **构建 provenance 失真**：字体实际由 **dirty 工作树**（commit `8ac16dfe`，dirty=true，status_n=9）于 2026-11-13T14:33Z 构建，`build_stats.cache_ver=ae10c121_…` 与当前 clean tree 的 `_CACHE_VER=61657834_…` 不同；而包内 `build_recipe` 记的是**打包时刻**的 clean commit `8622ba89`，`build_stats` 不随包，README「构建时间」实为 finalize 时刻（真实构建早约 8h）。
   - **扫描证据链断裂**：包内 165/0 两个披露数字引用的 reused 扫描产物，在 finalize **之后**被重写（sidecar created_utc `00:18/00:27Z` > finalize `22:36Z`，git=3f11321 dirty vs finalize 8622ba8 clean，build_stats 指向已消失的 `/tmp/audit-build` 副本），且 gate-report 不记录被复用扫描产物的 sha/时间 → **165/0 无法锚回 finalize 当时的字节**。
   - **门禁可缩水 / 复用绑定漏项**：`validate_reuse` 只校验调用方列举的子集（缺 `geometry/page_line_bands/build_stats/precut_masks.py`，E30/E37 类变更不会使旧扫描失效）；只传 `--reuse-*` 不传 `--scan/--frame-scan` 时，两个扫描闸**根本不执行**，Lead 实测 full finalize 仍 `pass=true`（13 步）。
   - **对外指标/归因/披露失真**：RELEASE-METRICS 的「617 变化字」来自旧候选 b73e9f01 的阈值筛选集，对发布字体不可复算（真实 glyf 轮廓变化 **3,351** 字，Lead 独立复算 32.7s）；缺件 165 的公开归因「prune_edge_contours 删除」被复算证伪（0/234 组件满足删除条件，结构性互斥）；内容闸 18 中 **9 字 IoU<0.3**（50%，含常用字 公 0.082/遣 0.111/掊 0.090）未分级披露；RELEASE-INVENTORY 失真（v2.6.1 标 PASS、v2.6.2 files=27 实为 SHA 32/zip 33/目录 34、无 zip sha 列却有多份文档指向它查 zip sha）；SELF-AUDIT 的 clean-tree commit 记成 `c199945`（实为 `8622ba8`）；发布包 OFL.txt 与仓库根 OFL.txt 是两份不同文本。
   - **finalize 纪律与冻结**：finalize 阶段失败（如换包）**仍改写包**（SHA/zip/包内报告），并把 `finalized:true` 写进 `pass:false` 报告；包目录 finalize 后新增 `.DS_Store` 无任何校验能发现（重跑 finalize 会把它吞入 SHA/zip，实测 34 文件）；finalize 终验结果（sha_final_ok/zip_ok）未以不可变证据留档——`work/lead/gate-report-v262.json` 现与包内报告逐字节相同（sha `1288aa88…`），终验字段丢失。
3. **上代 audit3 的 86 条挂账仍未清**：fixed 32 / fixed-partial 17 / deferred 36 / accepted 1；P1 仍 open 约 20 条（57%）。本轮抽样复核 20 条：**真正 fixed-verified** 的有 geometry 消费、三闸、换包闸、finalize 顺序、同框/双真源、缓存 key 主体等；**确认未修/假修/回归**的有：`make_block_mapping` 坐标混用（BUILD-04 未修，重跑会改 999 字 box / 192 字越界）、`WORKFLOW.md:92`「~20s」回归、GATE-09/10（报告归因、doc_check）仍未闭环、内容严重度（LEAD-02）未修、DATA.md 旧口径（DATA-13）未修。
4. **结论**：**v2.6.2 作为字体产品可分发**（未发现错误字形批 / 假 PASS / 数据损坏级别的 P0）；但**作为「可复现、可审计的正式发布」不可签收**——构建 provenance、扫描证据、变化字指标、缺件归因、发布登记与冻结纪律均存在可复算证伪的失真项。建议下一补丁 **v2.6.3 先做「证据链 / 口径」补丁**（Phase A），再做字形/映射类修复（Phase B）；**在修好 `make_block_mapping` 坐标系之前，不要重跑全量 mapping**（CS3 补 669 半版会引入 192 个新的 box 越界）。
5. **计数**：P0 **0**；P1 **20 条 / 15 组**；P2 **35 条 / 30 组**；P3 **21 条 / 20 组**（3 组跨级重复按最高级计；去重后共 **65 组**）。机器可读：`audit/AUDIT4-FINDINGS-v2.6.2.jsonl`（76 行，含 `dedup_group`/`auditor`/`audit3_status` 字段）；四名审计员的明细与证据分别在 `work/review/audit4/{build,gates,data,docs}/`。

---

## 1. 审计范围、方法与边界

### 1.1 范围

| 层 | 对象 | 审计员 |
|---|---|---|
| 构建核心 S1–S3 | `scripts/font_build.py`、`font_norm.py`、`precut_masks.py`、`page_frames.py`、`make_block_mapping.py`、`build_page_geometry.py`、`detect_blocks.py`、`make_manifest_from_stats.py`；mapping/geometry/bands/build_stats/manifest | auditor-build |
| 门禁与对抗 | `font_qa`、`content_loss_gate`、`glyph_frame_gate`、`provenance_gate`、`page_geometry_gate`、`gate_binding`、`fast_gate`、`release_gate`（pre-finalize 语义）、`scan_missing_parts`、`scan_frame_escape`、`check_release_docs` | auditor-gates |
| 数据真源与数字 | TTF/manifest/mapping/geometry/bands/canonical；包内全部 JSON/MD 数字；扫描产物与 sidecar | auditor-data |
| 文档/流程/合规/挂账 | `AGENTS.md`、`docs/**`、`audit/**`、`release/` 登记表与许可文本、scripts 分层、§10bis 三件套 | auditor-docs |
| 发布信任链（Lead） | `release_gate` finalize/打包/zip/SHA 覆盖、`font_package` 打包器、证据冻结、`RELEASE-INVENTORY`/`package_summary` | Lead |

### 1.2 方法

1. **文档先行**：按 `AGENTS.md` 顺序读 `docs/README → ARCHITECTURE → METHOD → PROJECT-STATE → PIPELINE → WORKFLOW → DECISIONS → ERRATA`，再读上代 `audit/AUDIT-REPORT-v2.6.1-audit3.md` + `AUDIT-RESPONSE-v2.6.1-audit3.md` + `work/lead/audit3-findings-map.jsonl`；
2. **代码对读**：文档声明逐条落到 file:line，找「文档说 X、代码做 Y」；
3. **数字复算**：核心数字一律用 fontTools / 流式 JSONL / 复刻部分扫描链复算（不引用文档二手值）；
4. **对抗实验**：换包 finalize、无扫描闸 finalize、篡改文档数字跑 doc_check、额外文件混入、env 开关 A/B、几何四重内缩 A/B、v2.6.0 坏字体跑字形框线闸等，全部在 `/tmp` 副本上做；
5. **交叉复核**：4 名审计员独立取证，Lead 对全部 P1 与关键 P2 独立复跑/复核；跨审计员重复事实以 `dedup_group` 标注，不重复计问题组。

### 1.3 未做/局限

- 未重跑全库缺件/框线扫描（10–25 min）、未做 17,005 字 0 命中全量重建（约 10.5 min）、未对 12GB PDF 做全量 hash——均按「单命令 ≤3 分钟」纪律中止并标注；
- 构建可复现性用「17,005/17,005 缓存键命中 + 两版 cache 目录 17,005 条 contours/src 全同 + 36 字子集与发布 TTF 逐点相同 + 两次同输入 byte-identical」替代整字体 byte 比对（置信度高，但严格 byte 级标注「未实测」）；
- 未做字形/标签的人眼复核（项目 7 张复核图 + owner 签核流程仍待 owner）；未重渲染 18 个内容缺损字做源墨复核；
- 与上代一致：`release/` 不被修改；`/tmp` 实验中 failed-finalize 复制包/无扫描 finalize 复制包/篡改文档包均为临时副本。

---

## 2. 发布对象与本次新增对抗实验

### 2.1 发布对象事实（均只读复核）

| 项 | 值 | 复核方式 |
|---|---|---|
| 字体 | sha256 `a8bb87d9…`，17,005 cmap，`.notdef` 第 17,006 | TTF cmap / fontTools |
| 包内 SHA | 32 文件全部 OK（含 `review/` 7 文件） | `cd release/KangXiKai-v2.6.2 && shasum -a 256 -c SHA256SUMS` |
| zip | 33 文件、`unzip -t` OK、zip 内 gate-report 与目录同 sha（`1288aa88…`、finalized:true、17 步） | `unzip -t` / `unzip -p | shasum` |
| 目录 vs zip | **仅 `.DS_Store` 差异**（目录 34 文件 vs zip 33 文件；`.DS_Store` 不在 SHA256SUMS） | `find`/`unzip -Z1`/`diff` |
| gate-report 归因 | 7 个脚本 sha 与 `git show 8622ba8:scripts/…` 逐一相符；font/manifest/mapping/geometry/reffont 5 个输入 sha 与当前实物逐一相符 | Lead 独立脚本比对 |
| zip sha | `1c225e888388110ffc197b29b426661c26e57f71be0a18b90ee6a294213ee648`（实际计算） | `shasum -a 256 release/KangXiKai-v2.6.2.zip` |
| v2.6.1 归档包 | zip 内 gate-report 为 `finalized:false`（7 步）≠ 目录 `finalized:true`（9 步）——历史缺陷仍在，`RELEASE-INVENTORY` 却标 PASS | `unzip -p` 对比 |

### 2.2 Lead 新增对抗实验（证据在 `/tmp/audit4-lead/`，日志保留到本会话结束；结论已转写为 findings）

| # | 实验 | 结果 | 对应 finding |
|---|---|---|---|
| E-L1 | 包副本 TTF 换成 v2.5.8 后跑 full finalize | `pkg_font_sha` FAIL、EXIT=1（换包闸有效）；**但** SHA 32→34 文件、zip 重建、包内报告被改写为 `finalized:true/pass:false`，原 pass=true 报告仍在包内；`.DS_Store` 被吞入 SHA/zip | LEAD4-002 / GATE-411 |
| E-L2 | 只传 `--reuse-*`、不传 `--scan/--frame-scan` 跑 full finalize | **EXIT=0、pass=true、13 步**（无 scan_missing_parts / frame_escape 两闸），同样吞入 `.DS_Store`（34 文件） | LEAD4-003 / GATE-402 |
| E-L3 | 在包副本加 `STRAY-FILE.txt` 后跑 `shasum -c` + `check_release_docs` | 两者均 PASS（既不看多余文件，也不看目录/zip 一致性） | LEAD4-004 |
| E-L4 | 篡改包副本 QA.md「18/35」→「999/35」、KNOWN-DEBTS「165」→「100」 | `check_release_docs` 仍 **PASS** | LEAD4-005 / GATE-10 |
| E-L5 | 构建溯源对读 | `build_stats = {commit 8ac16dfe, dirty:true, status_n:9, cache_ver ae10c121_…}`；当前 clean tree `_CACHE_VER=61657834_…`；字体 mtime=2026-11-13T14:33:31Z；recipe 记 `8622ba89 clean` | BUILD-401 / DATA-404 |
| E-L6 | 「617 变化字」复算 | 617 = `work/lead/diff-v261-v262.json` 行数（mtime 早于最终字体，round-003 对象为候选 b73e9f01）；Lead 直接按 glyf 轮廓复算 v2.6.1→v2.6.2 变化 **3,351** 字（32.7s） | DATA-401 |
| E-L7 | 内容闸严重度复算 | 18 行中 IoU<0.3 = **9**（遣 .111、掊 .090、𩌏 .164、恄 .082、𧁃 .298、公 .082、𨽗 .243、檬 .141、瘚 .172），IoU<0.5=13 | DATA-405 |
| E-L8 | `fast_gate` 独立复跑（`--tag audit4-lead-fast`） | **8/8 PASS、55s**；内容 damaged 18（rc=3、缓存命中）、字形框线 0、页几何 0/0/1173（阈值 400/300/1200） | 正向复核 |
| E-L9 | `make_block_mapping` 代码对读 | `block_for_box(lat, old)` 为原图坐标，`q["box"]` 为旋转空间坐标，两者直接求交（`make_block_mapping.py:74-79`）——与 audit3 BUILD-04 同一缺陷，未修 | BUILD-404 |
| E-L10 | `frame_mask=None` 代码路径 | `font_norm.py:1089+` 的 `frame_mask_outer` 分支引用 `x0/y0`，而 `x0/y0` 仅在 `frame_mask is not None` 分支赋值；`FONT_PAGE_LINE_MASK=0` 时 `line_mask=None`、`thin_mask` 仍可能非 None → UnboundLocalError | BUILD-403 |

---

## 3. P0（0 条）

**本轮没有 P0**。判定沿用 audit3 标准：P0 = 会造成错误发布 / 假 PASS / 修复空转。

- 交付字体与包内 TTF、manifest、gate-report、SHA 互相绑定一致，未发现「被验字体 ≠ 包内字体」；
- 正式 finalize 确实执行了 17 步（含缺件/框线扫描闸与三闸），`fast_gate 8/8` 已独立复现；
- 核心数字复算一致，未发现数据损坏或错误字形批；
- 上述 P1 中「扫描可缺席 / 证据可覆盖 / provenance 失真」属于**发布可信度与可复现性**缺陷，本轮不升级为 P0 的理由是：它们没有证明**本次已发布包**被篡改或字形错误，而是证明「发布流程可产出无法复核的发布包，且当前证据链不足以自证」。
- 需要 owner 注意：若把「正式包必须来自 clean git tree / 可复现」按 AGENTS §1 作严格解释，则 BUILD-401/DATA-404（字体由 dirty tree 构建）可视为**发布口径违反**，建议按 P0 处理（本审计按「产物未坏」保留 P1，见 §8 Phase A 优先级）。

---

## 4. P1（15 组 / 20 条）

> 详细 facts/evidence/repro/impact/fix 见 `audit/AUDIT4-FINDINGS-v2.6.2.jsonl` 与各审计员 `findings.jsonl`；此处给结论、证据锚点与改进方案要点。

### 4.1 发布 provenance 与证据链（6 组）

| 组 | IDs | 结论 | 关键证据 | 改进方案 |
|---|---|---|---|---|
| **G1 构建 provenance 失真** | BUILD-401, DATA-404 | 字体由 dirty tree（`8ac16dfe`，dirty=true）构建，cache_ver 与 clean tree 不同；recipe 记打包时 clean `8622ba89`；build_stats 不随包；README「构建时间」实为 finalize 时刻。字形可复现性已被 A 用「两版缓存 17,005 条 contours 全同 + 36 字逐点相同」佐证，故不是产品错误，是 provenance 失真 | `work/font/build/KangXiKai-v2.6.2.build_stats.json`（git/cache_ver）；`release/…/build_recipe-v262.json:8-10`；`font_build.py:254-268`（`_CACHE_VER`）；字体 mtime 2026-11-13T14:33Z | 构建期 clean-tree 闸；stats 记录 effective 脚本 sha / `_CACHE_VER` 组成 / 真实构建时间；build_recipe 由 build_stats 派生并随包；README 构建时间取真实构建时刻 |
| **G2 扫描证据不可锚定 / finalize 终验未留档** | DATA-403, GATE-404, DOCS-404, LEAD4-001 | reused 扫描在 finalize 后被重写（sidecar created_utc 00:18/00:27Z > finalize 22:36Z；git dirty vs clean；build_stats 指向已消失的 `/tmp/audit-build`）；gate-report 不记扫描产物 sha/时间；`work/lead/gate-report-v262.json` 与包内报告逐字节相同（`1288aa88…`），终验 `sha_final_ok/zip_ok` 丢失；package_summary 是唯一记录但无仓库生成器 | sidecar 文件；`gate-report-v262.json` steps 的 `missing_reuse_binding` 只有 ok 无 sha；`rm -rf` 后的 `/tmp` 路径 | 扫描产物+sidecar 纳入冻结证据目录并登记 sha；gate-report 记录「产物 sha/created_utc/生成 commit」；finalize 终验报告双写（包外冻结）；work/lead 证据只增不改 |
| **G3 复用绑定漏项** | GATE-401, DATA-406 | `validate_reuse` 只校验调用方列举的 files/scripts 子集；缺件扫描未校验 `geometry/page_line_bands/build_stats/precut_masks.py`，框线扫描未校验 `page_line_bands/precut_masks.py`。实测篡改这些 sha 后仍 `ok=True`；当前 missing sidecar 的 build_stats（`/tmp/audit-build` 版 sha 5829d8ce）已与仓库 stats（fe5237d6）不一致却仍被判 ok | `release_gate.py:197-206,240-247`；生产者 `scan_missing_parts.py:230-240` / `scan_frame_escape.py:124-130`；`gate_binding.py:134-165` | 绑定清单由生产方声明完整依赖（或共享 spec）；消费者校验**全量相等**（多记=FAIL）；sidecar 记录构建期输入快照 |
| **G4 扫描闸可整体缺席** | GATE-402, LEAD4-003 | 只传 `--reuse-*` 不传 `--scan/--frame-scan` 时两个扫描闸 step 不创建，`scans_required` 又把 reuse 当「已提供」→ full finalize `pass=true`（Lead 实测 13 步 EXIT=0） | `release_gate.py:192-268,310-317`；`/tmp/audit4-lead/gate-report-noscan.json` | 扫描闸硬编码必跑；reuse 仅决定「跑还是复用」，不能决定「是否检查」；缺产物=FAIL |
| **G5 finalize 失败仍改写包 / 非幂等** | GATE-411, LEAD4-002 | `pkg_font_sha` FAIL 后仍 `_rehash`+重建 zip+写包内报告（`finalized:true/pass:false`）；失败会改动已发布包；重跑 finalize 会把 `.DS_Store` 吞入 SHA/zip；包内出现两份 pass 不同的 gate-report | `release_gate.py:357-456`；`/tmp/audit4-lead/swap.log`、`pkg/SHA256SUMS`（34 行） | 全部终检通过后才允许写包；失败零写包；`finalized:true` 仅当终检全过；包内文件用 allowlist；写临时目录后原子替换 |
| **G15 sidecar 绑定时序（TOCTOU）** | GATE-403 | sidecar 在扫描**结束**后才哈希输入/脚本；长扫描期间脚本/输入变化会绑定错版本。现存 missing sidecar 本身已自相矛盾：旧脚本列表 `refgate.py:null` + 新脚本 sha `d05b9607`（producer 现版本已不含 refgate） | `gate_binding.py:81-123`；`work/lead/missing_scan_v262.jsonl.sha256` | 扫描开始时快照输入 sha（temp 记录），结束时再比对；或产物内嵌「启动时 sha」并由 gate 复核 |

### 4.2 对外指标、归因与披露（3 组）

| 组 | IDs | 结论 | 关键证据 | 改进方案 |
|---|---|---|---|---|
| **G6「617 变化字」不可复算** | DATA-401 | 617 = `work/lead/diff-v261-v262.json` 行数；该文件 mtime 2026-11-13 11:37（早于最终字体 22:33），round-003 自述对象是候选 **b73e9f01**、口径是渲染阈值筛（ink 比/IoU）。对发布字体 a8bb87d9：真实 glyf 轮廓变化 **3,351** 字；617 中 165 字与 v2.6.1 **逐坐标相同**；同阈值重算命中 676、与 617 交集仅 277。RELEASE-METRICS 却写成「相对上一版变化字 617」 | `work/lead/release-metrics.json:64`；`release_metrics.py:125-128`；Lead E-L6 复算 | 新增 `scripts/glyph_diff.py` 由最终字体生成 diff；指标写清「基线/阈值/生成时间」；对最终版重跑并在发布材料注明 |
| **G7 缺件 165 归因被证伪** | DATA-402 | 公开归因「prune_edge_contours 在字墨 bbox 边缘删掉组件」不可复算：234 个 missing 组件中满足 prune 删除条件（in_ring∧thin∧area）的 **0 个**；扫描过滤保证组件最小边 ≥8px，而 prune 细线阈值只有 5.0–6.8px（结构性互斥）；speck 规则命中 0；bbox 缩小比例 6.7% 与全库基线 8.7% 无差异 | `work/review/audit4/data/recompute/m_prune.py`+`.out`；`font_norm.py:348-399`；`KNOWN-DEBTS/QA/PIPELINE` 归因文字 | **先插桩定位真实丢失阶段**（逐字记录 clean_ink/prune/normalize 各阶段的组件存活），再写根因；BF-06 的「调 prune 口径」暂停 |
| **G8 内容闸 18 无严重度分级** | DATA-405 | 18 中 IoU<0.3 = **9 字（50%）**：恄 .082、公 .082、掊 .090、遣 .111、檬 .141、𩌏 .164、瘚 .172、𨽻 .243、𧁃 .298（含常用字）；audit3 时 15/35（43%）。包内只写「18/35 多为归一化差异」，无分桶/字表 | 包内 `content-loss-v258-v262.json`；`work/lead/content-loss-gate-v262.json`（三处副本 sha `f5383146…`） | 发布材料给 IoU 分桶（<0.3 / 0.3–0.7 / 掉墨<0.5）+ 字表；D23 定「IoU<0.3 桶=0」或逐字复核；阈值单调不增 |
| **G14 §10bis 三件套未闭环** | DOCS-405 | v2.6.2 发布材料 + 自审计这一批改动没有对应 changeset（`work/changesets/` 最新到 E37 cs4）；build_recipe 缺 WORKFLOW:226 明文要求的 cache_tag / 算法脚本 sha / 扫描数字来源 | `ls work/changesets`；`release/…/build_recipe-v262.json` keys | 每个候选/正式版补 changeset（材料类也开）；build_recipe 由脚本生成并含上述字段；门禁（`check_release_docs` 或 release_gate 新 step）校验三件套 |

### 4.3 构建可复现性（2 组）

| 组 | IDs | 结论 | 关键证据 | 改进方案 |
|---|---|---|---|---|
| **G9 行为 env 开关不进缓存 key** | BUILD-402 | `_CACHE_VER` = 4 个算法脚本 sha8 + geometry sha12 + bands sha12（+人工 tag），**不含** `FONT_PAGE_LINE_MASK / PAGE_THIN_MASK / LINE_ULTRA / LINE_BANDS / STRIP_BORDER / VERIFIED_KEEP`，也不含 `work/t2/pdf_map.json`。热缓存下带开关构建 100% 命中、输出 sha 与默认逐字节相同（实测 36 字 LINE_MASK=0、18 字 LINE_BANDS=0）→ D22/E29 式 A/B「测了等于没测」；冷缓存带开关构建会污染同一 cache_ver | `font_build.py:254-268`；审计 A evidence `cached-subset-build.log` | env 取值进 key 或命中前校验；`--no-cache` 强制不落盘；cache 记录含开关快照 |
| **G10 mapping 生成器坐标系混用（上代未修）** | BUILD-404 | `make_block_mapping.py:63-90` 把原图 150dpi 的 `block_for_box()` 与旋转空间 `q["box"]` 直接求交；用当前 v271 输入模拟重跑：**999/17,005 字 box 被改写（max 7px）、192 字重算 box 越出 quad**。当前 bad_boxes=0 是 E30 事后扩 quad 的结果，生成器口径未修 → CS3 补 669 半版重跑即回归 | `make_block_mapping.py:70-79`；`page_frames.py:157-158`（quad box 在 rot space）；audit A probe | 统一坐标系（M/Minv）后求交；加 L0 断言 box⊆quad=0；**修复前禁止重跑全量 mapping** |

### 4.4 发布登记、发布文档与许可（4 组）

| 组 | IDs | 结论 | 关键证据 | 改进方案 |
|---|---|---|---|---|
| **G11 RELEASE-INVENTORY 失真 / zip sha 悬空** | DOCS-402 | v2.6.1 记 `gate_pass=PASS`（文档称不可签收）；v2.6.2 `files=27`（实际 SHA 32 / zip 33 / 目录 34）；**无 zip sha 列**，但 AGENTS/PROJECT-STATE/VERSION-HISTORY/RELEASE.md/PLAN 五处写「zip sha 见 RELEASE-INVENTORY.tsv」；preview 行指向不存在的 `release/_preview`；全仓库无脚本生成该表 | `release/RELEASE-INVENTORY.tsv`；`release/package_summary.json`（zip sha 真值 `1c225e88…`，无生成器）；`ls release/_preview` | 脚本化生成 inventory（名字/大小/文件数/zip sha/gate 状态/签收状态）；zip sha 写入 inventory；状态列区分「正式/过程/不可签收」 |
| **G12 SELF-AUDIT 发布 commit 记错** | DOCS-401 | `docs/releases/v2.6.2/SELF-AUDIT.md:52` 写 clean tree `c199945`；包内 gate-report、build_recipe、package_summary 三处均为 `8622ba8`；`c199945` 是 01:07 旧提交 | 三处 JSON + git log | 发布记录数字由脚本注入（commit/时间/sha）；SELF-AUDIT 的 §4 由 finalize 输出生成而非手写 |
| **G13 OFL 双真源** | DOCS-403 | 包内 `OFL.txt`（4826B，`font_package.py:65-78` 硬编码 + `:519` 写盘）≠ 仓库根 `OFL.txt`（5154B，含「digitised by 書格 (shuge.org)」「扫描图不随包分发」等归属句）；check_release_docs 不校验二者一致 | `diff OFL.txt release/…/OFL.txt`；`font_package.py:65-78` | 单一 OFL 源（仓库根或模板变量）；打包时复制并校验 sha；包内许可必须包含扫描件归属/不随包分发声明（README 有，OFL 文本也应一致） |

---

## 5. P2 / P3 摘要

### 5.1 P2（35 条；按最高严重度去重为 30 组）

| 主题 | IDs | 要点 |
|---|---|---|
| 发布完整性/冻结 | LEAD4-004, DOCS-415 | finalize 后 `.DS_Store`/额外文件不被任何校验发现；目录≠zip；重跑 finalize 会吞入垃圾（32→34 文件）；`_iter_pkg_files` 无 allowlist |
| 门禁 fail-open / 纪律 | GATE-405, GATE-412, GATE-416, GATE-413 | `fast_gate --pkg-dir` 路径拼错静默跳过 doc/sha（8/8 实为无包检查）；`--allow-missing-scans/--allow-dirty/--allow-missing-attestation` 可用于正式 finalize；content `rc=3` 双语义；sidecar 只绑输入不绑输出 |
| 阈值/归因 | GATE-406, GATE-410, GATE-417, LEAD4-005 | 阈值无单调性/owner 签字（页几何 fast 阈值 400/300/1200 远宽于观测）；报告 inputs 缺 scan 脚本/build_stats/bands；单 `--frame-max-flagged` 混用两闸；check_release_docs 不核对闸数字（Lead 篡改实验 PASS） |
| 扫描语义 | GATE-407, GATE-408, GATE-409 | 扫描无 n_expected/n_scanned/skipped（0 字节 vs 完整扫描不可区分）；框线逃逸要求 bad≥2 条贯穿带（合成实验：单条贯穿线不 flagged）且 docstring 厚度口径（≤10px vs MIN_THICK=4）不一致；content_loss docstring 判据与实现不符 |
| 三闸牙齿 | GATE-414, GATE-415 | provenance_gate 只查 stats 自报元数据（未打标记的 overlay 可绕过，suspected）；page_geometry_gate 的 2×2 块∩quad 一致性/框稳定性只报告不设门 |
| 构建健壮性 | BUILD-403, BUILD-405, BUILD-406, BUILD-408, BUILD-409, BUILD-410 | `frame_mask=None` 时 `x0/y0` 未定义（`FONT_PAGE_LINE_MASK=0` 整页字崩溃，E37 对照实验不可复现）；geometry 缺失静默现算且 stats 无 loaded/degraded/fallback 计数；无 n_chars 断言（截断 mapping → exit 0）；WORKFLOW 缓存键漏 bands 且「~20s」回归；geometry 真源原地非原子重写；precut_masks `except:pass` + 手抄第二套映射 |
| 数据/发布材料一致性 | DATA-407, DATA-408, DOCS-412, DOCS-413 | 包内 KNOWN-DEBTS 与仓库版排期/链接不同且含包内死链；DATA.md 仍残留 v2.4.5/17,126/6,219；review/ 快照缺 04/05/diff-stats；包内文件名与 WORKFLOW §8 不符 |
| 文档权威性 | DOCS-406, DOCS-407, DOCS-408, DOCS-409, DOCS-410, DOCS-411, DOCS-417 | PIPELINE（唯一权威）§3/§4/§6/§7 仍写 v2.6.1/v270 且 §3 与 §2 PDF 数矛盾；AGENTS §2「工程候选」叙述与 v2.6.1 验证命令；PROJECT-STATE「CS3-A 进行中」过期；WORKFLOW:92「~20s」回归；GLOSSARY 5 处术语与代码不符；audit/ 现行文档过期且漏登记 audit3；发布后 3 个提交只在 ERRATA E38 部分声明，冻结包内文档引用因目录重构悬空 |
| 发布元数据 | DOCS-414, LEAD4-005 | package_summary `published_utc=2026-11-14T06:36:00Z` 实为本地时间（真 UTC 22:36Z，差 8h）；zip_sha256/finalized/gate_steps 等字段无仓库生成器；doc_check 不核数字 |

### 5.2 P3（21 条；去重 20 组）

`BUILD-407`（`--limit` 不提前终止，垃圾 skipped 记录）、`BUILD-411`（缓存 2.2GB 重复 + 17,010 旧 flat 文件）；`GATE-418`（fast_gate docstring 步骤数与实际不符）；`DATA-409`（标签 11 字不列字表）、`DATA-410`（high_freq_gap note 陈旧）、`DATA-411`（PIPELINE §7 标题 v2.6.1）、`DATA-412`（包内 17006/17005、字段名、日期小矛盾）、`DATA-413`（缺口叙述漏 沓）、`DATA-414`（缺件 165 单位不明）、`DATA-415`（E23 已清，正向）、`DATA-416`（核心数字复算一致，正向）；`DOCS-416`（WORK-MAP 缺 v2.6.2）、`DOCS-418`（BACKLOG 计数三处矛盾）、`DOCS-419`（E 系列/EXPERIMENTS 索引滞后）、`DOCS-420`（ARCHITECTURE docs 树旧路径）、`DOCS-421`（死目录/脚本引用）、`DOCS-422`（VERSION-HISTORY 候选行未标已被取代）、`DOCS-423`（DECISIONS 未登记 2026-11-14 决策、D23 不存在）、`DOCS-424`（data/base 92B HTML 假参考字体）、`DOCS-425`（provenance-detail 与 manifest 同构）、`DOCS-426`（changeset 扩展名与规定不符）；`LEAD4-00X`（v2.6.1 zip≠dir 历史包仍在，归入 G11 组）。

---

## 6. 数字核对（文档/包内 vs 复算）

> 完整 19 行对照见 `work/review/audit4/data/summary.md §2`；下表为核心结论。所有复算脚本在 `work/review/audit4/data/recompute/`。

| 项目 | 文档/包内 | 复算 | 判定 |
|---|---|---|---|
| 字形数 | 17,005 | cmap 17,005 == manifest；maxp/glyph order 17,006（含 `.notdef`） | ✅（口径未说明为 P3） |
| 基本区覆盖 | 10,267/20,992=48.91% | 同值 | ✅ |
| 目标表覆盖 | 10,267/16,567=61.97% | canonical 唯一基本区 16,567（42,302 行/40,412 唯一）；同值 | ✅ |
| 缺口 | 6,300 | canonical_basic−cmap_basic=6,300；v2.5.8/2.6.1 为 6,298（+2=沓/忠） | ✅（叙述漏 沓，P3） |
| 隔离 9 | 9 字 | 9/9 不在 cmap/manifest | ✅ |
| 内容闸 | 18/35 | 18 行三副本同 sha；**IoU<0.3=9/18** | ✅ 数量 / ❌ 严重度披露（P1） |
| 缺件扫描 | 165/165 | 165 行=165 字=157 半版=**234 组件**、error 0 | ✅ 数量 / ❌ 归因（P1）/ 单位未注明（P3） |
| 框线逃逸 | 0 | 0 行（reused，证据链见 G2） | ✅ 数量 / ⚠️ 证据 |
| empty_assign | 1,173（669/504/40） | quad 半版 6,868−mapping 5,695=1,173；按卷和一致；含 `01_0006 L「一」` | ✅ |
| 同框/重复轮廓 | 同框 0 | (page,half,box) 重复 0；TTF 17,005 轮廓哈希全不同 | ✅（audit3 DATA-01 fixed） |
| 617 变化字 | 617 | 旧候选阈值筛集；最终字体真实轮廓变化 **3,351** | ❌（P1） |
| 构建 provenance | recipe `8622ba89 clean`；README 构建时间 22:36:22Z | build_stats `8ac16dfe dirty=true status_n=9`，字体 mtime 14:33:31Z；cache_ver 与 clean tree 不同 | ❌（P1） |
| 包完整性 | SHA 32 文件 | 32/32 OK；目录多 `.DS_Store`（不在 SHA）；zip 33 文件 | ✅ zip / ⚠️ 目录（P2） |
| finalize | 17/17 PASS（sha_final_ok/zip_ok） | 包内报告 17 步 pass=true；sha/zip 可由当前实物复验 OK；但终验字段无冻结留档 | ⚠️（P1 G2） |

---

## 7. 上代 audit3 挂账复核（摘要）

> 完整 20 行抽样表见 `work/review/audit4/docs/summary.md §6`；86 条全量状态见 `work/lead/audit3-findings-map.jsonl`。

- **状态分布**：fixed 32 / fixed-partial 17 / deferred 36 / accepted 1；其中 P1 35 条里仍 open（deferred 13 + fixed-partial 7）约 20 条（57%）。
- **fixed-verified（本轮正向复核）**：geometry 真被 S3 消费（P0-04）、三闸落地（P0-03）、换包闸 `pkg_font_sha`（P0-01）、finalize zip 顺序（P0-02）、同框硬闸+双真源（P0-05，E23 后同框/重复=0）、缓存 key 主体（BUILD-02 的脚本/geometry/bands 部分）、内容闸缓存绑定（GATE-06）、字形级框线闸负样本（v2.6.0 字体 10 flagged/exit 3）、递归 SHA/zip（GATE-19）、失败 pre-finalize 不动包（GATE-08 的 pre 部分）。
- **未修 / 假修 / 回归**：
  - **BUILD-04 未修**（本轮 BUILD-404：生成器仍混坐标，重跑 999 改动/192 越界）；
  - **BUILD-02 partial**（本轮 BUILD-402：env 开关不在 key）；
  - **BUILD-06 回归**（WORKFLOW:92「~20s」仍在，本轮 BUILD-408/DOCS-409）；
  - **GATE-09/10 未闭环**（本轮 G2/LEAD4-005：报告归因缺扫描产物 sha；doc_check 不核闸数字）；
  - **LEAD-02 未修**（本轮 DATA-405：9/18 IoU<0.3 未分级）；
  - **DATA-13 未修**（本轮 DATA-408/DOCS-412：DATA.md 旧口径）；
  - **GATE-07 阈值纪律未修**（本轮 GATE-406）；
  - **GATE-16 扫描覆盖 partial**（本轮 GATE-407）；
  - **overlay/restore**：主链入口已删除（fixed-verified），但 `work/lead/contours_override.json` 数据残留（P3）。
- **上代审计的数个「已修」声明本轮被证伪**：BUILD-04（回应称 CS3 处理，实际生成器未改）、DATA-11/content_loss docstring（GATE-409 实测仍不符）、GATE-10（doc_check 仍不核闸数字）、WORKFLOW ~20s（上代 DOCS-09 标 fixed，本轮回归）。

---

## 8. 改进路线图（建议，按依赖顺序；本审计不改代码）

> 原则：先修「证据链与口径」，再修「构建/字形」，最后清「文档/材料」。每项验收必须可由命令复算。

### Phase A — v2.6.3：发布证据链与口径补丁（建议 1–2 天，P1 全清）

1. **构建 provenance（G1）**：构建期 clean-tree 闸；`build_stats` 记录 `git{commit,dirty}`、`_CACHE_VER` 组成（各脚本 sha）、geometry 加载页数/fallback 数、真实 `built_at_utc`；build_recipe 由 build_stats 生成并随包；README「构建时间」取真实构建时刻。
   - 验收：从 clean tree 重建→stats 与 recipe 的 commit/cache_ver 与当前树一致；`shasum` 记录三方一致。
2. **扫描证据冻结（G2）**：扫描产物+sidecar 写入不可变证据目录（如 `work/evidence/v<ver>/`），登记 sha256/created_utc/生成 commit；gate-report 记录被复用产物 sha；finalize 终验报告双写（包外冻结）；work/lead 只增不改。
   - 验收：仅凭包内材料+冻结证据可复算 165/0，且 sha/时间可锚定到 finalize。
3. **复用绑定完整化（G3/G15）**：生产方声明全部依赖（files+scripts+env），消费者全量校验；扫描开始/结束两次快照；多记/缺记均 FAIL。
   - 验收：篡改 geometry/bands/build_stats/precut_masks 任一，`--reuse-*` 必须 FAIL。
4. **扫描闸必跑（G4）**：`--scan/--frame-scan` 与 `--reuse-*` 解耦为「闸必跑、执行可复用」；缺产物=FAIL；报告记录应有/实际闸清单。
   - 验收：不带扫描参数跑 release_gate → FAIL（不再是 13/13 PASS）。
5. **finalize 原子化（G5）**：全部终检通过后才写包；失败零写包；`finalized:true` 仅在全过时；包内文件 allowlist（过滤 `.DS_Store/._*`）；写临时目录后原子替换；增加 `scripts/verify_release.py`（目录==zip、SHA 覆盖全部非 SHA 文件、无多余文件、zip sha 登记）。
   - 验收：换包/坏 zip/多余文件三种负向测试全部 FAIL 且包字节不变。
6. **指标与归因（G6/G7/G8/G14）**：新增 glyph diff 生成脚本，对最终字体重算「变化字」（当前真实 3,351，仍待二次确认口径）；内容闸输出 IoU 分桶+字表并写入发布材料；缺件 165 先插桩定位真实丢失阶段再写根因（撤回/改写 prune 归因）；补 v2.6.2 发布批次 changeset；build_recipe 补 cache_tag/算法 sha/扫描来源。
7. **发布登记与许可（G11/G12/G13）**：脚本化生成 `RELEASE-INVENTORY.tsv`（含 zip sha/签收状态）与 `package_summary.json`；SELF-AUDIT 的 commit/时间由 finalize 注入；OFL 单一源，包内必须含扫描件归属/不随包分发声明（与 README 一致）。
   - 验收：inventory 行数/文件数/zip sha 与实际一致；`diff` OFL 两份为空；五处「zip sha 见 …」引用可命中。

### Phase B — v2.6.x：字形/映射类修复（依赖 Phase A 的可信证据）

1. **先修 `make_block_mapping` 坐标系（G10）**，再做 CS3 的 empty_assign 669 半版补映射；否则重跑 mapping 会引入 192 个 box 越界（当前 0 会被打破）。
2. **缺件 165 的类级修复**：按 Phase A.6 的插桩结果定位阶段（clean_ink / normalize / prune / 扫描配准），再决定修口径或披露；不要先调 prune。
3. **D23 内容判据**：按 IoU 分桶与源墨保真度判据由 owner 定稿；里程碑要求「IoU<0.3 桶=0」或逐字复核。
4. **标签 11 字重定位（BF-54）**、高频缺 23/隔离 9/100 字签核，按现有 PLAN-v2.6.3 排期。
5. **构建健壮性 P2**：修 BUILD-403（frame_mask_outer 未定义）、BUILD-405/406（降级标记/n_chars 断言）、BUILD-402（env 进 key）等，作为下一候选前置。

### Phase C — 文档/流程收口（可与 A 并行但发版前必须清）

- 修正 PIPELINE/AGENTS/PROJECT-STATE/WORKFLOW/DATA/GLOSSARY/audit README/WORK-MAP 的 v2.6.1 残留、旧路径、旧数字（P2/P3 共 30+ 条）；
- `docs/releases/v2.6.2/SELF-AUDIT.md` 补「记录状态」；包内 KNOWN-DEBTS 与仓库版统一（说明冻结版本）；
- 补 `work/changesets/`（发布材料批次）与 `work/lead/version-artifacts-v2.6.2.jsonl` 的刷新（当前 2 条 sha 已与磁盘不符）；
- ERRATA 增补 E39（本审计发现的作废数字：617、缺件 prune 归因、构建 commit 等）。

### 不建议做（本轮已证伪/高风险）

- ❌ 先按 BF-06「调 prune 口径」修 165——归因被复算证伪，会空转；
- ❌ 在 make_block_mapping 未修前重跑全量 mapping——会引入 192 个新 box 越界；
- ❌ 用「617 变化字」继续作为版本变化规模指标——对最终字体不可复算；
- ❌ 对已发布包目录重跑 finalize——当前实现会改写 SHA/zip 并吞入 `.DS_Store`。

---

## 9. 附录

### 9.1 Findings 分布

| 严重度 | 条数 | 去重组数 | 说明 |
|---|---|---|---|
| P0 | 0 | 0 | 无错误发布/假 PASS/数据损坏级缺陷 |
| P1 | 20 | **15** | 跨审计员重复 5 条（含 Lead 复核） |
| P2 | 35 | **30** | 与 P1 跨级 2 组（按最高级计入 P1）；组内重复见 dedup_group |
| P3 | 21 | **20** | 与 P2 跨级 1 组（按最高级计入 P2） |
| 合计 | **76** | **65** | 4 名审计员 71 条 + Lead 5 条；跨级组按最高级计 |

机器可读文件字段：`id/severity/area/title/facts/evidence/repro/impact/fix/confidence/audit3_status/auditor/dedup_group`。`confidence ∈ {verified, suspected}`；`audit3_status ∈ {new, regression, unfixed, fixed-verified, accepted}`。

### 9.2 证据索引

| 路径 | 内容 |
|---|---|
| `audit/AUDIT4-FINDINGS-v2.6.2.jsonl` | 76 条机器可读 findings（本报告合并） |
| `work/review/audit4/build/` | findings 11 条、summary、`evidence/`（probe 脚本与输出、E37 变体、确定性/失败注入/崩溃日志） |
| `work/review/audit4/gates/` | findings 18 条、summary、`evidence/`（fast_gate 报告、v2.6.0 负样本、fail-open 报告、reuse 子集漏检测试、frame 扫描合成/覆盖、发布后证据时间线） |
| `work/review/audit4/data/` | findings 16 条、summary（19 行数字对照）、`recompute/`（全部复算脚本与原始输出） |
| `work/review/audit4/docs/` | findings 26 条、summary（挂账复核表 20 条、复现命令） |
| `/tmp/audit4-lead/` | Lead 对抗实验日志/报告（swap、noscan、doc_check 篡改、包清单对比等；临时目录，结论已转写进 findings 与本报告） |
| `work/lead/*audit4-*` | 审计期间以 `audit4-` tag 生成的闸产物（与既有 v262 产物并存，未覆盖正式证据） |

### 9.3 审计员分工与产出

| 成员 | 任务 | 条数 | 结论概览 |
|---|---|---|---|
| Lead | 发布信任链/finalize/证据冻结 + 交叉复核 | 5 条（+全部 P1 复核） | finalize 失败写入/无扫描 finalize PASS/冻结无校验/终验证据丢失/doc_check 太弱 |
| auditor-build | 构建核心 S1–S3 | 11（P1×3/P2×6/P3×2） | provenance 失真、env 不进 cache key、mapping 坐标系未修；geometry 消费/确定性/fail-loud 已修 |
| auditor-gates | 门禁契约与对抗 | 18（P1×4/P2×12/P3×2） | 复用子集、扫描闸可缺席、绑定时序、证据不可归因；三闸牙齿基本有效 |
| auditor-data | 数据真源与数字复算 | 16（P1×5/P2×3/P3×8） | 核心数字全部一致；617/缺件归因/扫描证据/构建 provenance/内容严重度 5 个 P1 |
| auditor-docs | 文档/流程/合规/挂账 | 26（P1×5/P2×12/P3×9） | inventory 失真、SELF-AUDIT commit 错、OFL 双源、证据覆盖、§10bis 未闭环；audit3 P1 仍 open 20 条 |

### 9.4 Lead 独立复核记录（防止「只信队友」）

以下关键结论由 Lead 自己复跑/复算，不只依赖审计员报告：

1. **包完整性**：`shasum -a 256 -c SHA256SUMS` → 32/32 OK；zip `unzip -t` OK；zip 内 gate-report 与目录同 sha（`1288aa88…`）、`finalized:true`、17 步；目录 vs zip 仅 `.DS_Store` 差（34 vs 33 文件）。
2. **gate-report 归因**：7 个脚本 sha 与 `git show 8622ba8:scripts/…` 全部相符（当前 HEAD `release_gate.py` 已变，属发布后提交）；font/manifest/mapping/geometry/reffont 输入 sha 与当前实物全部相符。
3. **换包失败路径**：/tmp 副本 full finalize → `FAIL pkg_font_sha`、EXIT=1，但 SHA/zip/包内报告仍被改写、`.DS_Store` 被吞入（34 文件）——LEAD4-002 实证。
4. **无扫描闸 finalize**：仅 `--reuse-*` 不传 `--scan/--frame-scan` → EXIT=0、pass=true、13 步、无两个扫描闸——LEAD4-003 实证。
5. **doc_check 篡改**：QA.md 数字改 999/35、KNOWN-DEBTS 165→100 后仍 PASS——LEAD4-005 实证。
6. **构建 provenance**：`build_stats` = `{8ac16dfe, dirty:true, status_n:9, cache_ver ae10c121_…}`；当前 `_CACHE_VER=61657834_…`；字体 mtime 2026-11-13T14:33:31Z；recipe 记 `8622ba89 clean`。
7. **617 变化字**：直接按 glyf 轮廓复算 v2.6.1→v2.6.2 变化 3,351 字（32.7s），617 的来源文件 mtime 早于最终字体。
8. **内容严重度**：包内 content-loss 18 行 IoU<0.3 = 9 字。
9. **fast_gate**：独立以 `--tag audit4-lead-fast` 复跑 → 8/8 PASS（55s），内容 18（rc=3、缓存命中）与包内 gate-report 一致。
10. **v2.6.1 历史包**：zip 内 gate-report `finalized:false`（7 步）≠ 目录 `finalized:true`（9 步），`RELEASE-INVENTORY` 却标 PASS。

### 9.5 审计声明

- 本审计**只发现问题、提出改进方案，不修改代码/数据/文档**；审计期间 tracked 工作区保持 clean（`git status --short` 空），未做任何 git 写操作；
- 未对 `release/` 运行 finalize/font_package/任何写操作；换包、无扫描 finalize、篡改文档等实验均在 `/tmp` 副本完成；
- 新增文件：本报告、`audit/AUDIT4-FINDINGS-v2.6.2.jsonl`、`work/review/audit4/**`（证据），以及审计 tag 产生的 `work/lead/*audit4-*`、`work/font/build/qa_gate_audit4-*` 产物（不影响正式证据文件）；是否入库/保留由 owner 决定；
- 所有 P0/P1 均有可复制 repro；若复算结果与本文不一致，以复算为准，并请记入 `docs/ERRATA.md`（建议 E39）。

---

*报告生成：2026-11-14 · 第 4 代独立代码审计 · 全部证据可复算*
