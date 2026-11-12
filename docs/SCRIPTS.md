# SCRIPTS 清单 · 代码梳理与「旧方法是否更优」评估（v2.5.6 基线，2026-11-12 注记）

> **时效注记（2026-11-12 晚）**：本文写于 v2.5.6；现行管线为 v2.6.1（见 `docs/PIPELINE.md`）。
> 脚本数量已变化：现行 **62** 个 + 归档 **141** 个（总计 203；本文旧述「190 个 / 50 现行 / 142 归档」作废）。
> 范围：`scripts/` 全部 `.py`（含 `scripts/_archive/`）
> 结论口径：**已解决 / 部分解决 / 未解决 / 待评估**；「更优」必须给出可复现的 A/B 方案与验收线，不靠直觉。

## 0. 一句话结论

190 个脚本 ≈ 3 周探索的沉积层：**50 个仍在现行链路上，142 个已完成使命或已被替代（已移入 `scripts/_archive/`）**。
探索想解决的问题**大多数已经解决**（正典序、映射、字头-only 字表、格块切分、双闸、发布门禁）；
**真正未解决**的是：缺口 6,298 的回收（隔离字 + 未对齐字）、残余碎片/杂物入字、09–11/13 卷锚点、100 字签核。
旧代码里有 **6 处方法比现行管线更强或更对症**（§8），其中 2 处（`layout_thick_detect` 的独立字头候选、`snap_box` 的参考评分选块）建议立即 A/B。

统计：

| 项 | 数量 |
|---|---|
| 脚本总数（梳理前） | 190 |
| 现行保留（`scripts/`） | **50** |
| 归档（`scripts/_archive/`） | **142** |
| 现行管线硬依赖闭包 | 24 个模块（定义：现行脚本的 import 传递闭包；其余为一次性/诊断/provenance）；50/50 import 自检通过（修复归档断链后） |

---

## 1. 现行管线（v2.5.8）：50 个脚本的角色

### 1.1 构建与发布（9）
| 脚本 | 角色 | 状态 |
|---|---|---|
| `font_build.py` | 全量构建：mapping + 格块掩膜 + 版框擦除 + `--repair-overlay` 回写；按页并行 | **核心** |
| `font_norm.py` | 二值化/掩膜/擦框/清理/矢量化/归一化 | **核心** |
| `font_qa.py` | 渲染闸/空字形/同框/内部一致性 | **核心** |
| `font_package.py` | 打包 + SHA256SUMS + zip 自检 | **核心** |
| `release_gate.py` | 发布门禁 7 项（QA/版本/字符集 diff/内容闸/文档/SHA/zip） | **核心（新）** |
| `content_loss_gate.py` | 逐字内容缺失闸（覆盖率下限） | **核心** |
| `check_release_docs.py` | README/PROVENANCE/QA 数字与引用校验 | **核心（新）** |
| `stamp_version.py` | 字体内部版本盖章 | **核心（新）** |
| `build_release.py` | v2.4.20 的构建配方脚本（已被 release_gate 覆盖） | 保留（历史配方） |

### 1.2 诊断 / 修复链（7）
`scan_missing_parts`（缺件扫描，1,109 修复的发现器）· `scan_offset`（切偏体检 825）· `scan_distort`（长宽比/大小 vs 参考，20）·
`scan_aspect`（源图口径几何体检，早期版）· `repair_missing_chars`（标记字缺件外科修复）·
`repair_all_missing`（全库批量缺件修复）· `repair_offset`（3×3 块重选修切偏，内置逐字 gate）

### 1.3 参考闸（5）
`refgate`（参考字体 raster/结构支持）· `refgate2`（带配准版）· `refgate2_scan`（全量扫描）·
`refgate_clean`（轮廓级外科清理，v2.5.1 清理 1,216 字）· `fidelity_eval`（字形↔原书墨迹配准 IoU，所有闸的底层量具）

### 1.4 页级工具（1 + 1）
`detect_blocks`（**仅** `page_gray/binarize/fit_axis` 被 font_build 复用；其「从零检测字头」主程序未启用）·
`header_read`（书眉读数，canonical/映射阶段的数据 provenance）

### 1.5 发布核验与出图（3）
`owner_review_sheet`（100 字核验表）· `owner_review_color`（彩色版）· `regenerate_sheets`（specimen/random120 确定性重生成）

### 1.6 数据 provenance（保留不跑，19）
`seq_order`（正典 42,302 序）· `lead_solver` / `lead_solver2`（映射求解）· `lead_extract` · `lead_strict_headwords`（headword-only 原则实现）·
`lead_finalize_union11` · `lead_validate_map` / `lead_mapping_check` / `lead_selfcheck_map` · `lead_run_detect` ·
`lead_t1v2_frozen` / `t1_v2` / `t1_v3`（候选检测器冻结版）· `lead_char_align14` · `lead_vlm_fp_full` / `lead_vlm_confirm`（VLM 指纹）·
`lead_bu_dp2` / `lead_bu_dp3`（部界 DP）· `volume_structure` · `radical_templates` · `structure_read` · `lead_gan_targets`（D19 分桶）

---

## 2. 归档脚本（142）：原计划解决什么、现在解决没有

| 族 | 数量 | 原计划解决的问题 | 现状 | 结局 |
|---|---|---|---|---|
| `t00_/t0_` | 10 | 语料盘点、页渲染、版面参数实测（h0/列数/框带）、纠偏、50 框金标 | 版面参数已固化进 `font_build` 格点拟合；纠偏 A/B 后未采用（1 赚 2 亏 1 平）；金标演进为 owner 39 锚点 | **完成/收编** |
| `t1_`/`lead_t1v2_frozen` 系 | 8 | 字头候选检测 + 每半版计数（映射的输入） | 映射已定稿（v2.5.6：基座 mapping32、发布 mapping33；注意旧文档写「mapping23」为漂移），不再跑检测；检测器「计数正确」目标未达（D9 门槛）后被结构对齐取代 | **封存**（历史路线） |
| `t2_` | 9 | 双引擎 OCR + 书眉窗口对账 + 全局单调 DP 对齐 | 结论作废（基于错误阅读序）；可复用 OCR/图像工具 | **作废**（TAKEOVER §1.4） |
| `bu_` | 4 | 214 部首页锚点（书眉部首 + 单调 DP） | 部界锚点后由 `lead_bu_dp3` 等替代，最终映射定稿后不再需要 | **完成** |
| `lead_` | 68 | 映射求解全过程：OCR 锚点、漂移校正、δ、重定位、指纹确认、重出对、质量过滤、页面角色、圈注剔除… | **映射问题已解决**：canonical 42,302 → 17,029 框指派 → 17,007 字表；label_source 通道完整。历史版本仅作 provenance | **完成**（数据资产保留） |
| `layout_/grid_` | 9 | 纯版面法大字检测（格点/笔画厚度/集成/并集） | `layout_thick_*` 产出 3,869 页独立候选（`work/lead/layout_big_boxes.jsonl`），**未进主链但可回收缺口**；`layout_lattice` 过检出+拟合退化（3,582/3,869 页有框、139,056 框、中位 79×72） | **部分可用**（§8-1） |
| `repair_/missing_` | 5 | 旧修复链：三类缺陷扫描、边栏/碎片删除、边栏检索 | 被 `scan_missing_parts/repair_*` + `refgate_clean` 取代；旧链是 v2.4.15 时代的一次性修补 | **替代** |
| `refgate/ref_` | 2 | 参考闸 v1、像素级参考过滤 `ref_filter_crop` | v1 无配准被 v2 取代；像素级过滤曾误删部件而停用（但值得复活，§8-2） | **部分**（§8-2） |
| `vlm/bench/hw_ocr` | 4 | OCR/VLM 证据通道基准 | 指纹通道结论已固化（84.6%，n=13）；重定位可复用 | **归档待用** |
| `anchors_/validate_` | 6 | 锚点体检、切边检测、框修复 | 部分判据已并入 `scan_offset/scan_distort`；注意旧「39/39」度量有缺陷（§9） | **部分替代** |
| `snap/block/refine/frame/scan_` | 7 | 格点框搜索、2×2 块切分、局部精修、帧线检测 | 块切分/掩膜已进主链；`snap_box` 的**参考评分选块**优于现行中心距评分（§8-3）；帧线检测被页级形态学 mask 取代 | **部分**（§8-3） |
| `font_/owner_/release_` 杂项 | 5 | demo 32 字 curation、QA 剔除回写、mapcheck、specimen | 被全量链 + 新门禁取代 | **替代** |
| 其它 | 6 | 圈注扫描、owner 标记对比、尝试性实验（`test_edge_clean`、`experiment_trace_fidelity`、`class_eval`、`postscale_glyphs`） | `class_eval`/`postscale_glyphs` 是**未采用但有用**的方法（§8-4/5） | **待评估** |

---

## 3. 按问题域给结论（「原计划的问题解决了没有」）

| 原问题 | 结论 | 依据 |
|---|---|---|
| 字表从哪来（headword-only、真迹、无注文小字） | **已解决** | 17,007 字全真迹；D15 严格执行；空/注文混入由 100 字核验表 + refgate 管 |
| 每页哪个框是哪个字（映射） | **已解决**（数据层，但**生成命令未脚本化**） | canonical 42,302 + mapping32/33；label_source 完整；`lead_*` 全链为 provenance；mapping 生成是会话内联，仓库无脚本可复算（build_recipe 记录输入 sha 算部分缓解） |
| 2×2 格块 = 字头、面积≈4 小字（切分源头） | **已解决**（架构层） | v2.5.0 起格块掩膜；v2.5.6 overlay 回写；重建轮廓差异 0 |
| 去边栏/页框/邻字 | **基本解决** | 页级框线 mask + 块掩膜；残余碎片率 random120 ≈4–7%（待 §8-2 压低） |
| 不误删字身部件（P0-1 类） | **已解决** | 内容缺失闸 0 + 缺件扫描修复 1,109 + 回写 overlay |
| 字体可复现（构建/版本/文档） | **已解决** | `repair_overlay` + `release_gate` 7 项 + `DOC-CHECK PASS` |
| 缺口 6,298（旧分桶口径：未对齐 5,839 + 严格剔除 374 + 回归 1 = 6,214，与当前 6,298 差 84；v245_gan_targets 为旧口径需重生成） | **未解决** | 高频缺 23（含 一/在/為/你）已披露；分桶清单未随包、未推进重定位 |
| 09–11/13 卷锚点缺失 | **未解决** | 39 锚点只覆盖 01–08,12 |
| 100 字 owner 签核 | **未解决** | 表格流水线已就绪，缺 owner 标注闭环 |

---

## 4. 现行 `font_norm` 的「危险开关」与死代码（本次梳理新发现）

`vectorize_gray` 主链**实际仍在执行**：`remove_specks → strip_border_lines → clean_cluster → clean_ink → trace_upscaled → normalize(全 ink bbox) → prune_edge_contours`。

以下函数正是 v2.4.16–19 P0（误删字身部件）的根因。**校准**：`enable_edge_strip` 的
函数默认值原为 **True**（只有 `font_build` 调用点显式传 False）——「默认关闭」的说法不准确，
这也是审计正确指出的风险：
- `strip_straight_lines_swt`（`enable_line_swt`）
- `strip_edge_small_comps` / `strip_edge_fragments`（`enable_edge_strip`）
- `apply_reference_filter`（`enable_ref_filter`，即 `ref_filter_crop` 的库版）

**已处置（2026-11-12）**：三者默认值改为 `False`，且 `vectorize_gray` 在任一开关为 True 时
**直接 raise**（策略 D20：禁用「按尺寸/位置删组件」的清理；新用途必须先过内容闸+缺件扫描双回归再单独评审）。
保留在链上的 `strip_border_lines` 与 `prune_edge_contours` 是「去长直线/去贴边轮廓」，
但「无损清理链」措辞应改为事实描述（`strip_border_lines` 仍在运行）。

---

## 5. 重复/碎片化脚本（合并建议）

| 重复族 | 现况 | 建议 |
|---|---|---|
| 参考闸 5 个（`refgate/refgate2/refgate2_scan/refgate_scan/refgate_clean`） | v1 无配准；v2 带配准；scan/clean 分工正确 | 删 `refgate_scan`；`refgate` 只留 raster 工具，文档标「v2 为唯一口径」 |
| 缺件检测 4 个（`missing_scan/scan_missing_parts/repair_scan/scan_frame_lines`） | 现行用 `scan_missing_parts`（带参考支持过滤） | 归档 3 个（已完成），保留 1 个 |
| 切偏修复 2 个（`repair_offset` vs `snap_box`） | 现行用中心距评分；snap_box 参考评分未采用 | **保留两套做 A/B**（§8-3） |
| 字体 QA 2 个（`font_qa` / `font_qa_filter`） | 现行 release_gate 用 font_qa；filter 是历史「剔除回写」 | 归档 filter（已完成） |
| 构建入口 3 个（`build_release` / `font_build` / `release_gate`） | 实际全量构建=font_build；配方向=build_release；门禁=release_gate | 文档明确「build_release 仅历史 v2.4.20 配方」，不删 |

---

## 6. 归档动作（已完成，可回滚）

- 建立 `scripts/_archive/`（142 个脚本，`git mv` 保留历史）；
- 写 `scripts/_archive/README.md`（归档原因 + 现行 48 个清单 + 「不保证可运行」声明）；
- 现行 50 个脚本 import 自检通过、`py_compile` 全过（50/50）；
- **注意**：`docs/`、`audit/` 里历史文档对归档脚本的引用均属历史记录，不追改（必要时加「已归档」注记）。

---

## 7. 更优方法候选（重点：旧代码里哪些比现行管线强）

> 每条给：原脚本 → 方法 → 为什么可能更优 → 现有证据 → A/B 方案 → 验收线。

### 7.1 `layout_thick_detect` 的独立字头候选 → 缺口回收（最高价值）
- **方法**：无 mapping 依赖；笔画厚度（p90 距离变换）作种子 + 2×2 格约束聚类 → tight 墨迹框（无 pad，杜绝边角料）。
- **已有产物**：`work/lead/layout_big_boxes.jsonl`（**3,869 页**，每页含 h0/小字统计/候选框+厚度）。
- **为什么更优**：现行缺口 6,298 中 **5,839 是「从未对齐」**，只能靠新候选框回收；mapping 系检测器已封存，这是唯一现成的规模化候选源。
- **A/B**：先做 precision 评测（owner 38 + 50 随机页人工目检 100 框：是否字头/是否切边），再跑「候选→VLM 注文指纹确认」重定位链（复用 `lead_vlm_fp_full`），产出可回收清单。
- **验收**：字头 precision ≥0.85、可回收字 ≥300（先小步），全部过内容/缺件双闸后才入字表。

### 7.2 `ref_filter_crop`（像素级参考过滤）→ 杂物入字根治
- **方法**：矢量化**前**用参考字体同字删除「参考无对应」的组件；主簇 bbox 用于归一化——正好同时治「碎片/框线入字」与「杂物撑大 bbox → 字缩小」（审计 P1-B）。
- **为什么废弃过**：v2.4.14 在**多组件字**上配准错误 → 误删部件；但现在有 **块掩膜**（先归位）与 **参考支持率过滤**（scan_missing_parts 已验证有效：3,352→1,109，误报降 3 倍）。
- **A/B**：在 300 字样本（含 owner 38 与 22 掉墨字）上跑「块掩膜 + 参考过滤」vs「块掩膜 only」，用 `class_eval` 标定阈值（阳性=owner 缺陷字，阴性=随机字）。
- **验收**：阳性改善 ≥60%、阴性误删 ≤1%、内容闸 0；通过后作为 `--ref-filter` 可选开关，再考虑默认。
- **与 §4 的关系（消解矛盾）**：§4 禁的是「无消融评测就默认开启」与危险的整字删除启发式；
  本条的参考过滤是**候选复活方案**，必须先走 §7.2 的 A/B 与 `class_eval` 标定，通过后才重新打开开关
  （届时通过显式参数启用，不恢复默认 True）。

### 7.3 `snap_box` 的参考评分选块 → 修切偏/切不全（立即 A/B）
- **方法**：9 个候选块，评分 = 参考支持域覆盖 − λ×参考外多余墨 − μ×块外墨。
- **现行**：`repair_offset` 只用「墨迹中心到块中心距离」评分，v2.5.4 结果 822 候选仅 347 通过（478 被逐字 gate 回退）——说明**评分信号不足**。
- **依赖注记**：`snap_box` 及其依赖 `cell_grid_boxes` 已归档；A/B 前需从 `scripts/_archive/` 恢复这两个文件
  （或把其格点拟合/评分函数提取进 `scripts/_archive/`）。
- **A/B**：对 478 回退字 + 22 掉墨字重跑选块，用同一逐字 gate（墨量≥95%、IoU≥0.75）+ 内容闸。
- **验收**：通过率从 42% 提到 ≥65%，且内容闸 0。

### 7.4 `class_eval` 类级评测 harness → 给闸标定阈值
- **方法**：阳性（owner 标记缺陷字）+ 阴性（随机字）逐字判类，输出每类 detector 的命中/误报。
- **为什么需要**：当前缺件闸/杂物闸阈值（1%、8px、18px、0.45、0.25…）是手工拍定，没有统一 harness 标定；审计也点名「闸靠直觉」。
- **做法**：把 `class_eval` 复活为主链工具，纳入 `release_gate`（报告命中/误报率，不阻断）。
- **验收**：为正/负样本集建立固定 JSON + 每次发布输出混淆矩阵。

### 7.5 `postscale_glyphs` 的「发布前一致性后处理」→ 字身尺寸一致
- **方法**：把每字墨迹 bbox 长边统一 760、中心 (500,400)（v2.4.8 已验证能修「框含边距→字缩小」）。
- **现行**：`font_norm.normalize` 用**全 ink bbox** 归一化 → 杂物一多字就缩小（P1-B）。
- **更优点**：不动回矢量化，只对 intruder-ledger 命中的字做「主簇 bbox 重归一化」，零内容风险、可回退（适合发布前兜底）。
- **A/B**：对 22 掉墨字 + random120 脏字运行后处理，比较字身尺寸方差与目检。
- **验收**：字身尺寸方差下降 ≥50%，内容闸 0，无新碎片。

### 7.6 `t0_rectify` 的页面 H 矩阵 → 格点拟合的相位校正（低成本试验）
- **方法**：版框四角 → 透视 H；**只把「小字中心坐标」映射到拉正空间再拟合格点**（不重采样图像）。
- **证据**：几何 8/8 成功；但整图重采样伤细笔画（A/B 1 赚 2 亏 1 平，matched IoU 0.51–0.57 瓶颈是框紧度）→ 说明「拉正图」不该进渲染链，但「拉正坐标」可以进拟合链。
- **A/B**：对 offset top-100 页，比较「原空间拟合相位」vs「H 空间拟合相位」的块中心残差。
- **验收**：残差中位数下降 ≥30%，且对 09–11/13 卷（无锚点）先用它自检拟合质量。

---

## 8. 已知陷阱与度量缺陷（本次梳理发现）

1. **`detect_blocks.py`**：docstring 说「留边 ≥4%」，实现未设阈值（审计 V13 已指出）；其 `blocks_from_scratch` 主程序未采用。
2. **`scan_missing_parts.py`**：参考支持检查是 **fail-open**（refgate import 失败 → 跳过过滤 → 误报放大 3,352）；应改 fail-closed。
3. **「39/39 锚点墨迹落在格块内」** 这一历史结论不可全信：早期校验是在「块内取墨再判是否在块内」，属循环论证；`scan_offset` 实测 825 字偏移 >0.18 格、147 字 >0.35 格。锚点应重跑严格版（`validate_anchors3` 思路）后再作为回归基线。
4. **`layout_lattice_boxes.jsonl`**（本条曾写错，已校准）：实测 3,869 页中 **3,582 页有候选**（92.7%），
   共 **139,056 框**（38.8/页），中位框 **79×72**（2×2 块预期 ~95×90）→ 真实问题是**过检出+格点拟合退化**
   （密度超真值约 3 倍），不是「基本全空」。与 `layout_big_boxes`（4.2 框/页、稀疏高精度）失败模式相反，
   两者都暂不可直接引用，但缺口回收评测时都应纳入对比。
5. **`v245_gan_targets.json`**：D19 分桶清单存在但是旧口径（6,214 vs 当前 6,298），需用 `lead_gan_targets.py` 重生成并随包。

---

## 8bis. 「重建差异=0」的口径校准（回应审计 P1）

v2.5.6 重建 vs v2.5.5：**glyf 坐标点/轮廓 0 差异**（17,007 全检，逐字坐标数组完全一致）；
但 **974 字 hmtx lsb（左旁距）不同**，幅度 **1–129 units**（分布：563 字 ≤2；147 字 3–10；264 字 >10；抽样 㔌 +35）。原因：overlay 重建时
`font_build` 用点集 xMin 重算 lsb，而 v2.5.5 的 lsb 是历史构建期留下的旧值。
影响：advance 恒 1000、字符按坐标居中出现，视觉字形位置不变；但严格说「差异=0」应写成
「**轮廓差异=0；974 字 lsb 由 overlay 重算**」。v2.5.7 起 overlay 生成脚本
（`scripts/make_repair_overlay.py`）随仓库，可复算 overlay sha（实测 = 48c611ab…，1,602 字）。

## 9. 后续清理动作（按优先级）

| 优先级 | 动作 | 归属 |
|---|---|---|
| P0 | 删除/硬禁 `font_norm` 的 4 个危险开关（`strip_straight_lines_swt`/`strip_edge_small_comps`/`strip_edge_fragments`/`apply_reference_filter`） | 本清单 §4 |
| P0 | 修 `scan_missing_parts` fail-open → fail-closed；修 `detect_blocks` docstring 与实现一致 | §8 |
| P1 | `snap_box` vs `repair_offset` A/B（478 回退字）；通过则替换选块评分 | §7.3 |
| P1 | `layout_thick_detect` 候选 precision 评测 → 缺口回收（D19） | §7.1 |
| P1 | D19 清单重生成（6,298 口径）并随包 | §8-5 |
| P2 | `class_eval` 纳入 release_gate 报告；`ref_filter_crop`/`postscale_glyphs` A/B | §7.2/7.4/7.5 |
| P2 | 09–11/13 卷锚点补齐（可先用 §7.6 的 H 空间拟合自检） | 覆盖率 |
| P3 | 归档脚本不再维护；历史文档引用加「已归档」注记 | 文档 |
