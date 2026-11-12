# 外部审计报告 · v2.4.19（边缘小碎片删除版）

- 被审对象：`release/KangXiKai-v2.4.19/`（发布包 18 文件）与 `release/KangXiKai-v2.4.19.zip`、`scripts/` 全部 177 个 .py（约 3.4 万行，HEAD `05617ca`）、`docs/` 与 `audit/` 现行文档、自审计 `AUDIT-SELF-v2.4.19.md` 的全部声明
- 审计方：代码审计 2 代（独立外部审计；团队：lead + release-verifier + code-auditor + docs-auditor）
- 审计时间：2026-11-11（Asia/Shanghai）
- 方法：发布包逐文件校验 + fontTools 实测 + QA 全量复跑（含 256px 渲染 17,007 字）+ 静态通读/引用扫描/py_compile + 合成墨迹实测 + 全量文档断链扫描 + 数字独立复算
- 证据底稿：`work/audit-v2419/release-verify.md`、`work/audit-v2419/code-audit.md`、`work/audit-v2419/docs-audit.md`（本报告为三份底稿的汇总与裁决）
- 分级沿用项目惯例：**P0**=发布阻断级（数字造假/校验失败/硬闸不成立）；**P1**=重要，可延后但须限期修；**P2**=轻微/建议
- 本报告只发现问题与改进方案，未修改任何被审文件（被审目录 release/、scripts/、docs/、audit/ 零改动）

---

## 〇、一句话总评

**字体本身全绿、无数字造假、QA 硬闸全部真实通过；问题集中在三处：随包文档（README/PROVENANCE 携带 v2.4.5 旧数字 + 8 个断链引用，P0）、构建可复现性缺口（cache 人工版本号、打包时间戳漂移、macOS 专用参考字体，3×P1）、审计流程自 v2.4.7 后停摆（核验台账与索引未更新，2×P1）。**

---

## 一、判定总表

| ID | 级别 | 位置 | 问题 |
|---|---|---|---|
| R1 | **P0** | `release/.../README.md` | 覆盖数字为 v2.4.5 旧快照手抄（10,353/62.49%/6,214 vs 实测 10,272/62.00%/6,295），内部自相矛盾（6,214 vs 6,219 等 5 处），并引用 8 个包内不存在的文件 → 违反 QA.md §4 自设补充闸「引用必存在 + 数字禁止手抄」与 D17.2 |
| R2 | P1 | `release/.../PROVENANCE.md` | 整份是 v2.4.5 旧版（17,121/10,353/6,214），与 v2.4.19 实际矛盾；README 的旧数字正源于它 |
| R3 | P1 | `release/.../RELEASE-NOTES-v2419.md` §2 | 声称「26 字对照图随包可查」，包内无此图（仅 random120/specimen）→ 断链 |
| R4 | P1 | `scripts/font_build.py:275` | cache 键=人工版本号 `v263_`+page/half/char/box，不含输入 PDF hash 与代码 hash；漏 bump 即静默复用旧轮廓 |
| R5 | P1 | `scripts/font_package.py:485,524` | `built_at_utc=date.today()` + zip 条目时间戳=mtime + freshness 闸用 mtime → 打包层字节不可复现、跨机器漂移（TTF 本体可复现，见 §四） |
| R6 | P1 | `scripts/font_norm.py:33`（及 refgate.py/refgate2.py） | `REF_FONT` 硬编码 macOS 宋体绝对路径，缺失时 `except→{}` 静默降级 → 非 macOS 构建输出不同且无告警 |
| R7 | P1 | `docs/README.md:9-13`；`COUNTS/V3-STATUS/SESSION-HANDOFF` 顶部横幅 | 「现行口径速查」与三份编年横幅数字停在 v2.4.3–v2.4.11（17,051/10,348/62.46%/6,214/20 项 SHA/发布物 v2.4.3）；编年正文（COUNTS §57-59、V3 §47-48、HANDOFF §1s）与实测全部一致 |
| R8 | P1 | `audit/AUDIT-VERIFICATION-LOG.md` | 核验台账停在轮次 4（v2.4.0），其后 16 份自审计 + 第 5 轮外部审计全部未入账 → 审计流程实质断裂 |
| R9 | P1 | `audit/README.md` 索引表 | 索引缺 v2.4.8–v2.4.19 共 12 份 AUDIT-SELF 行，且 v2.4.5/6/7 行序错乱 |
| R10 | P2 | `scripts/font_norm.py:533-562` | `strip_edge_fragments` 与文档判据 4 处出入：①分母是全 crop 墨量而非「块内墨量」（阈值被抬高→漏删）；②`min_area=80` 绝对像素与 0.9% 相对量在 `max()` 混用（dpi 依赖）；③`touches` 实际覆盖「块外 6% 带 ∪ 块外全部 pad 区」，宽于文档口径；④与主体 8 连通相连的贴边残屑并入大组件永久免疫。均合成实测证实；方向偏保守（漏删），与 docs 自述「仍有残留」互证 |
| R11 | P2 | `scripts/font_norm.py:690-691` | `strip_edge_small_comps → strip_edge_fragments` 顺序依赖：前级删组件后后级重算 `total`，0.9% 项变小 → 后级更激进；无回归测试保护 |
| R12 | P2 | `scripts/refgate_scan.py:25-29` | 逐字 `except→sus=[]` 吞异常当「干净」→ 参考闸计数可能系统性偏低（质量闸自身缺陷） |
| R13 | P2 | `scripts/refgate2_scan.py:17` | `if False else (0,0)` 死分支 |
| R14 | P2 | 84 个 `lead_*` | 36 个零引用完全孤立（6,373 行：char_align2-16、header_v2/v3/v4、relocate_v244/245/246、apply_delta 三代等）；另 `font_curate.py`（669 行）已不在现行链 |
| R15 | P2 | `scripts/fidelity_eval.py:129`、`class_eval.py:104`、`anchors_check_sheet.py:9`、`owner_review_color.py:7` 等 12+ 文件 | 签核/比对工具默认硬编码 v2.4.15/v2.4.17 字体与 manifest 路径（部分经 env/argv 可换，anchors_check_sheet 写死）；`owner_review_color.py` 默认 `work/font/build/KangXiKai-v2.4.17.ttf` 已不存在 |
| R16 | P2 | `release/.../stats.json:42` | `charset_scope.note` 引用 `v24x-strict-report/gan_targets`，包内不存在 |
| R17 | P2 | `release/.../QA.md`、`stats.json` nameID0 | QA.md 仍是 v2.4.4 文本（命令/文件名硬编码旧版）；nameID 0 版权串残留「demo v0」 |
| R18 | P2 | 自审计数字落盘 | refgate 1,261/9/残余 9 字在发布包内证据仅 coverage-detail 一处（qa-stats/qa-report/provenance-detail 均无字段）；仓库内 work/lead/refgate_*.jsonl 可完整复算（见 §三，无手抄） |
| R19 | P2 | `work/font/build/cache/` | 186,842 个文件、v248–v263 九代并存 + 30,283 个无前缀旧格式，无清理逻辑 |
| R20 | 建议 | 仓库 | 无 `tests/` 目录；170+ 脚本仅 3 个 ad-hoc 试验脚本，`strip_edge_fragments` 无回归测试 |

---

## 二、发布物完整性：字体数据全绿（无造假、无硬闸失效）

以下为**独立复算**结论（每条均可按底稿命令复现）：

1. **SHA256SUMS 17/17 全过**；`unzip -t` 无错误，zip 内 18 文件与目录逐字节一致（diff 干净）。✅
2. **TTF 实测**（fontTools 4.61）：cmap 17,007；glyf 17,008（+notdef）；name 表 Version 2.4.19；`head.fontRevision=2.59`（=2+4/10+19/100，QA 硬闸成立）。与 `stats.json` 声明逐项吻合。✅
3. **硬闸「cmap == manifest」**：双向差集为空（0/0），禁止假覆盖成立。✅
4. **覆盖率数字全部独立复算吻合**：cmap∩基本区=10,272；10,272/16,567=**62.00%**；10,272/20,992=**48.93%**；缺口 6,295；至基本区缺口 10,720。lead 另用 `work/seq/canonical.jsonl`（正典 42,302 条/基本区唯一 16,567）独立验证 cmap∩canonical∩basic=**10,272**，与 coverage-detail 一字不差。✅
5. **QA 全量复跑 PASS**（含 256px 渲染全 17,007 字、宋体对照，未减项）：empty/tiny/out_of_em/adv_bad/render_bad 全 0；同框多字冲突 0；与包内 `qa-stats-v2419.json` 全 19 字段逐字段一致。✅

**问题集中在随包文档（R1-R3、R16、R17）**：

- **R1（P0）**：README 的「覆盖口径」表写 10,353/20,992=49.32%、10,353/16,567=62.49%、缺口 6,214/10,639 —— 全部是 v2.4.5 时代快照（现为 10,272/48.93%/62.00%/6,295/10,720）；同文件内缺口又写 6,219，B_strict_dropped 377 vs PROVENANCE 374、B_early_regression 3 vs 1、可回收候选 3,885 vs 3,882 —— 5 处自相矛盾。文件表引用 `manifest-v245.json`、`provenance-detail-v245.json`、`coverage-detail-v245.json`、`qa-stats-v245.json`、`v2419-gan-targets.json`、`v2419-box-refine-report.json`、`v2419-strict-report.json`、`AUDIT-RESPONSE-4.md` 共 **8 个包内不存在的文件**。项目 QA.md §4 自设补充闸明确「发布包内每个被引用文件必须存在」「数字由脚本生成，禁止手抄」——本包两项皆不满足。**结论：v2.4.19 按项目自设标准不应签收/发布（自审计已标注「不签收」，与本结论一致）；若项目方将文档类问题降级为 P1，则必须在 v2.4.20 打包前修复。**
- **R2（P1）**：PROVENANCE.md 头部自称 v2.4.5、正文 17,121 字/已收 10,353/缺口 6,214，与 v2.4.19 的 17,007/10,272/6,295 矛盾；其引用的 `v245-verified.jsonl`/`v245-gan-targets.json` 亦不在包内。README 旧数字正是沿用它而来（连带误导）。
- **R3（P1）**：RELEASE-NOTES §2「26 字对照图（v2.4.18 上 / v2.4.19 下）随包可查」——包内仅 `random120-v2419.png`、`specimen.png`，无任何 26 字对照图。
- **R16（P2）**：stats.json 的 `charset_scope.note` 引用 `v24x-strict-report/gan_targets`，包内不存在（机器生成字段里的死引用）。
- **R17（P2）**：QA.md 整体仍是 v2.4.4 文本（示例命令/文件名硬编码 v244/v245，引用 `qa-report-v245.json` 等）；TTF nameID 0 版权串仍含「demo v0」字样。

---

## 三、自审计声明核验：数字全部属实、可复算（无手抄）

逐项复核 `AUDIT-SELF-v2.4.19.md` 的全部声明：

| 声明 | 复算证据 | 结论 |
|---|---|---|
| 字形 17,016→17,007 | v2.4.18/stats.json cmap=17,016；v2.4.19 cmap=17,007 | ✅ 属实 |
| refgate pre-clean 1,358（v2.4.18） | `wc -l work/lead/refgate_v18.jsonl` = 1,358 | ✅ 属实 |
| refgate pre-clean 1,261（v2.4.19） | `wc -l work/lead/refgate_v19.jsonl` = 1,261 | ✅ 属实 |
| after-clean 8→9 | `refgate_v18_after.jsonl`=8 行、`refgate_v19_after.jsonl`=9 行 | ✅ 属实 |
| 清理 1,252 字 | =1,261−9，且 after 字符集 ⊆ pre（程序验证 True） | ✅ 推导成立 |
| 残余 9 字「㣶䃬傈厺塏烌絞胷鎮」 | `refgate_v19_after.jsonl` 9 行字符与 coverage-detail `residual_quarantine` 逐字相同 | ✅ 属实 |
| QA PASS | 全量复跑 PASS（§二） | ✅ 属实 |

**结论：自审计无手抄、无夸大，全部声明可复算。** 唯一瑕疵（R18，P2）：这些数字在**发布包内**只有 coverage-detail 一个落盘点，qa-stats/qa-report/provenance-detail 均无 refgate 字段——审计证据单点，建议 qa 产物加 refgate 字段或打包时复制。另建议 refgate_clean 直接落盘 `cleaned_count`，避免依赖「1,261−9」减法推导（v2.4.17 的「清理 1,008」就不满足 1,009−6，口径不统一）。

---

## 四、代码审计：3 个 P1 可复现性缺陷 + 过滤器细节问题

### 4.1 P1 缺陷

- **R4 cache 键人工版本号**（`font_build.py:275-277`）：`ck = f"v263_{page}{half}_{ch}_{box}"`。只有人记得在每次改 `font_norm.py`/`font_build.py` 判据时手动 bump 才安全；漏 bump 一次 → 全量静默复用旧轮廓。磁盘证据：cache 目录 v248–v263 九代并存，每次发布靠人工 bump。**改进**：键中加入 `font_norm.py`+`font_build.py` 源码 sha256（或 git HEAD）+ 输入 PDF sha256（`work/t00/pdf_sha256.txt` 已存在，可直接复用），自动失效。
- **R5 打包层字节不可复现**（`font_package.py`）：①`built_at_utc = date.today().isoformat()`（:485）写入 stats.json → 隔天重建即不同；②zip 条目时间戳=文件 mtime（`copy2`+`zf.write`，:524-526）→ zip 字节随构建时刻漂移；③freshness 闸用 mtime 比较（:426-427）→ 换机器/git clone 后 mtime 全变。注意：TTF 本体可字节复现（`SOURCE_DATE_EPOCH` 固定、无时间戳/随机数），但**发布包（stats.json + zip）不可复现**，与「可复现（重建逐字节一致）」承诺在打包层断裂，也影响基于 SHA256SUMS 的逐版对照审计。**改进**：built_at_utc 改用 SOURCE_DATE_EPOCH 或删除；zip 用固定 `ZipInfo(date_time=(1980,1,1,0,0,0))`；freshness 闸改内容 hash。
- **R6 参考字体不可移植**（`font_norm.py:33` 等 3 处）：`REF_FONT="/System/Library/Fonts/Supplemental/Songti.ttc"`。`_ref_has()` 打开失败时 `except→{}` → 非 macOS 上 `apply_reference_filter` 与 refgate 全量静默 no-op，构建结果跨平台不同且无告警。**改进**：参考字体入 `data/ref/`（附许可）或缺失时 fail-fast 并显式记录。

### 4.2 strip_edge_fragments（v2.4.19 新功能，R10/R11，均 P2）

判据主体与文档一致（6% 带、`max(80, 0.9%×墨量)`、扁平、与外带相交），**坐标无错配**（`center` 为 crop 内字身框坐标，lead 已核）。4 处出入（合成墨迹实测证实）：

1. 分母是**整幅 crop 墨量**（含 pad 带邻字墨），非文档所称「块内墨量」→ 阈值被抬高 → 漏删（与 docs 自述「仍有残留」互证）；改进：`src[by0:by1, bx0:bx1].sum()`。
2. `min_area=80` 为绝对像素，与 0.9% 相对量混用，依赖 dpi/块尺寸；改进：换算为块面积比例或声明 300dpi 假设并随 dpi 缩放。
3. `touches` 实际覆盖「块外 6% 带 ∪ 块外全部 pad 区」，比文档「块边缘 6% 带」口径宽；改进：文档补精确口径。
4. 与主体 8 连通相连的贴边残屑并入大组件 → 面积/扁平闸全失效 → 永久免疫（这正是 26 标记字残余残片的机制性原因之一）；改进：对主组件做贴边细颈判定或轮廓级处理（refgate_clean 路线）。
5. 顺序依赖（R11）：`strip_edge_small_comps` 先删 → 后级重算 total → 0.9% 项变小 → 更激进；无回归测试保护。

另注意：该函数**无累计删除安全阀**（对比 `apply_reference_filter` 的 `max_drop_frac`），对贴边合法笔画（点、短横）的误删风险未量化——残余 9 字已隔离、26 标记字已目检，但其余 17,000 字未系统核查。**改进**：加 per-glyph 累计删除上限 + 在 QA 落盘「每字删除组件数」诊断清单。

### 4.3 工程卫生

- 静态检查**全绿**：177/177 py_compile 通过；0 裸 `except:`；0 `shell=True`（subprocess 均 argv 列表 + `sys.executable`）；0 `/Users/wainshine` 硬编码；随机数固定 seed（7/11）。✅
- **R12（P2）**：112 处 `except Exception` 中，`refgate_scan.py:25-29` 逐字吞异常当「无嫌疑」→ 参考闸计数可能系统性偏低（质检工具自身的精度缺陷）。
- **R13（P2）**：`refgate2_scan.py:17` 存在 `if False else (0,0)` 死分支。
- **R14（P2）**：84 个 `lead_*` 中 36 个零引用完全孤立（6,373 行，清单见底稿 §3(c)：char_align2/3/4/5/6/12/13/16、header_v2/v3/v4、relocate_v244/245/246、apply_delta 三代等）；`font_curate.py`（669 行）已不在现行链。**建议归档 `scripts/archive/` 并注明替代者**，而非直接删除。
- **R15（P2）**：12+ 个工具脚本默认路径硬编码 v2.4.11–v2.4.17 资产；其中 100 字签核链（`fidelity_eval/class_eval/anchors_check_sheet/owner_review_color`）默认仍是 v2.4.15/17，`owner_review_color.py` 默认字体路径已不存在。重跑 v2.4.19 签核需先改代码或设 env/argv。
- **R19（P2）**：cache 目录 186,842 文件九代并存，无清理逻辑；建议 `--prune-cache`。
- **R20（建议）**：无 tests/；建议把合成墨迹用例（6% 带、面积闸边界、8 连通主体相连、顺序依赖）固化为回归测试。

### 4.4 未完成项根因（无 P1）

- **09-11/13 卷锚点**：`lead_bu_dp3.py` 已产出 214 锚点/12 卷全覆盖落盘；卡点不是脚本，而是**人工金标缺口**——39 个金标只覆盖卷 01–08、12（docs/V3-STATUS 已证 7 条自动化路线定量失效，剩余可行=人工每卷抽 5-10 页核数）。
- **100 字签核**：脚本可执行、有落盘（work/review/），「未签收」= owner 人工动作未闭环，非代码不可用。唯一代码问题是 R15 的旧版本硬编码。

---

## 五、文档与审计流程：正文数字准、流程已停摆

- **R7（P1）**：docs/README.md 速查第 8 行已更新到 v2.4.19，第 9-13 行却停在 v2.4.3–v2.4.11 旧值（17,051/10,348/62.46%/6,214/20 项 SHA/发布物 v2.4.3）——同一块半新半旧。判定为**数据过时**（分母 16,567 口径未变，分子/缺口全是旧快照），非口径差异。COUNTS/V3-STATUS/SESSION-HANDOFF 顶部「现行口径（2026-11-10）」横幅同样停在 v2.4.3。而三份文档的**编年正文**（COUNTS §57-59、V3 §47-48、HANDOFF §1s）与实测全部一致（17,016→17,007、1,358→1,261、9 隔离、17/17 SHA）✅。
- **R8（P1，流程断裂）**：`AUDIT-VERIFICATION-LOG.md` 最后入账轮次 4（v2.4.0）；其后第 5 轮外部审计 + 16 份自审计（v2.4.2–v2.4.19）全部未入账；台账自身基准（:5）仍写 v2.4.3。与 audit/README.md 约定「核验结论写入台账」直接冲突。
- **R9（P1）**：audit/README.md 索引表缺 v2.4.8–v2.4.19 共 12 份 AUDIT-SELF，且 v2.4.5/6/7 行序错乱。
- 断链扫描：docs+audit 全量 329 个唯一路径引用抽查 60+，**现行文档无死链**；死链集中在已声明「历史不回写」的 PROMPT/VENDORED/DETECTOR-V2/STRUCTURE §11（旧编号脚本、guangeti/ 等），可按现状维持。
- P2 补充：docs/README.md:12 敞口「1,400-1,500」与 PROVENANCE「429–4,188（点估计 1,500）」口径不一（F9）；DECISIONS 示例数字停在 v2.4.3/4 时点（F11）。

---

## 六、改进方案（按优先级，均为一套动作各修一批）

### 第一优先：修复随包文档 + 把「文档闸」做成机器检查（对应 R1/R2/R3/R16）

1. README 数字与文件表改由打包脚本模板生成：占位符从 stats.json/coverage-detail 注入，**禁手抄**；
2. 打包链新增两道机器闸（与 SHA256SUMS 同级）：①解析 README/PROVENANCE/QA/RELEASE-NOTES 中每个反引号文件名逐一 stat，缺失即 ABORT；②README 中的数字与 stats/coverage-detail 比对，且同一指标不允许出现两个值（6,214 vs 6,219 类直接报警）；
3. PROVENANCE.md 顶部加醒目横幅「数字最后更新于 v2.4.5，现行数字以 stats.json 为准」或模板化；
4. 凡 RELEASE-NOTES/AUDIT-SELF 声称「随包可查」的图，必须列入发布资产清单并由打包脚本校验存在（26 字对照图补入或以明确文件名交付）；
5. QA.md 去版本硬编码（示例命令用占位符/`--help`）；nameID 0 版权串禁止含 "demo"（打包闸）；
6. stats.json 生成器把 `v24x-strict-report/gan_targets` 死引用改为本版实际清单名或随包补齐缺口清单（本版 D17.3「随包披露缺口清单」未兑现）。

### 第二优先：构建可复现性（对应 R4/R5/R6）

7. cache 键自动失效（源码 hash + PDF hash，废除人工 v263）；
8. 打包层字节复现：built_at_utc 用 SOURCE_DATE_EPOCH 或删除、zip 固定时间戳、freshness 闸改内容 hash；
9. 参考字体入 data/ref/ 或缺失 fail-fast；跨平台构建结果需一致且可声明。

### 第三优先：审计流程恢复（对应 R8/R9）

10. 把「每版发布时向 AUDIT-VERIFICATION-LOG 追加一轮行」列为发布门禁（第四道闸，写进 RELEASE-PLAN 检查清单），台账行至少含：被审版本、声明要点、复算证据路径、结论、去向；
11. audit/README 索引表改为脚本扫描 AUDIT-SELF-*.md 自动生成（读首行标题提取版本/要点），或本轮补 12 行；
12. docs/README 速查 + COUNTS/V3-STATUS/SESSION-HANDOFF 顶部横幅刷新为 17,007/10,272/62.00%/6,295/17 项 SHA/v2.4.19，横幅日期更新为 2026-11-11（本报告 §五已给出最小改法）。

### 第四优先：过滤器与质检精度（对应 R10/R11/R12/R13/R18）

13. `strip_edge_fragments`：分母改「块内墨量」；`min_area=80` 注释 dpi 假设或按块面积缩放；补 per-glyph 累计删除安全阀；与主体相连的贴边残屑改轮廓级/细颈判定；文档补「带=块 bbox 内 6% ∪ 块外 pad」的精确口径；
14. refgate_scan 吞异常当干净 → 改为计数 + 落盘 errors 字段；删 refgate2_scan 死分支；
15. QA 产物加 refgate 字段（preclean/after/residual），或打包时把 coverage-detail 的 refgate 块复制进 qa-stats/qa-report，使审计证据 ≥2 落盘点；refgate_clean 落盘 `cleaned_count`。

### 工程建议（对应 R14/R15/R19/R20）

16. 36 个孤立文件（6,373 行）归档 `scripts/archive/` 并注明替代者；(b) 组过时工具同处理；
17. 签核工具字体/manifest 全参数化（argv/env），默认指向最新发布或 `release/latest` 符号链接；
18. cache 目录加 `--prune-cache`（保留最近 1-2 代）；
19. 新建 `tests/`：合成墨迹回归（strip_edge_fragments 边界）+ cache 键失效冒烟 + refgate golden 小字表。

---

## 七、遗留与限制

- 「26 个 owner 标记字的残余边缘碎片」「09-11/13 卷锚点」「100 字签核」三项待办均为**已知未完成项**，本报告确认其根因（判据覆盖不全 / 人工金标缺口 / owner 动作未闭环），无新阻塞。
- 精度敞口（指纹来源字 ~84.6%，n=13，宽 CI）为上一轮审计已确认的存量敞口，本版无新增证据，维持原状。
- 本次 QA 复跑使用系统 python3 + fontTools 4.61（脚本自升 4.68）；构建环境为 macOS，R6 的跨平台行为为静态推断 + 异常路径分析，未在非 macOS 实测。
- 本报告未改动任何被审文件；三份分项底稿留存于 `work/audit-v2419/`，供核验台账复算引用。
