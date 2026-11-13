# PLAN v2.6.3 —— 正式发布里程碑（v2.6.2 之后的收敛计划）

> 背景（2026-11-13，E37 后）：v2.6.2 已具备**正式发布候选**条件（快闸 8/8 PASS；全闸 9 PASS / 2 FAIL，
> 2 项为已披露已知债），发布材料（README/LICENSE/OFL/指标/已知债）已补齐。
> 剩余小修放 **v2.6.x**，P0 数据/口径/材料项纳入 **v2.6.3**，按本文验收后出正式包。

## 0. 当前快照（v2.6.2 发布候选，E37 后）

- 字体 sha256 `a8bb87d9c4a623d5fe88ae55c2f710a36827052c7cd3594fe70113f56ca18d5b`，17,005 字；
- 覆盖：基本区 48.91%（10,267/20,992）、目标表 61.97%（10,267/16,567）、缺口 6,300；
- 快闸 **8/8 PASS**；全闸 **9 PASS / 2 FAIL**：缺件 165、页几何 empty_assign 1,173（均披露）；字形框线 0、框线逃逸 0；
- 内容 18/35（E31/E37 归因跨版本差异；D23 源墨保真度判据待 owner 确认）。

## 1. v2.6.2 正式包条件对照（WORKFLOW §7）

| §7 条件 | 现状 | 结论 |
|---|---|---|
| L1–L3 全 PASS（内容 0、框线 0 或 owner 同意且低于上版、几何校验） | 字形框线 0、框线逃逸 0；内容 18（D23 未定）；empty_assign 1,173 | 内容/几何按**披露阈值** finalize（待 owner 确认） |
| 变更集人工复核 01-changes（✗≤2%） | 第 1 轮 owner 已标 77 格（收窄为三类问题）；第 2 轮修复验证包已生成待复看 | 待 owner 复看 |
| 02-class-sample 全 ✓ / 03-regression-random-100 ✓≥98% | 第 1 轮已生成并标注（class X 类 11 = mapping 问题）；第 2 轮待复看 | 待复看 |
| owner 批量签核、已知债冻结 | 已知债清单已随包（`docs/KNOWN-DEBTS-v2.6.2.md`）；100 字签核未做 | 本版以披露 + finalize 处理，签核进 v2.6.3 硬条件 |
| 包内容齐全、SHA 覆盖 gate-report、zip 自检 | 干跑包已自检；clean-tree finalize 待 owner 提交后执行 | 待执行 |
| 字体结构本里程碑内不再变化 | v2.6.2 后仅小修（v2.6.x）；v2.6.3 将改 mapping/覆盖 | 符合 |

## 2. v2.6.x 小修（本版系列内完成，先于 v2.6.3 数据动作）

1. **BF-54 标签错配 11 字**：按页重定位真迹字头（禁止补假字）；无法定位的移出字表并披露（本版先披露，不改字表）；
2. **BF-06 缺件 165**：调 `prune_edge_contours` 边缘清理口径（保留恢复的块内细笔画），重扫并重生成缺件闸；
3. **D23 内容判据**：与 owner 确认后实现源墨保真度闸 v2；
4. **release_gate 披露阈值参数**（BF-58 已加 `--page-geometry-max-empty-assign/bad-boxes`；
   缺件/框线/内容阈值已有参数）→ 正式 finalize 时全部写入 gate-report 并随包披露；
5. 自审计发现的次要项（见 §4）。

## 3. v2.6.3 工作项（按顺序）

### A. P0 数据/覆盖（阻塞发布）
1. **empty_assign 1,173 → 0（或 owner 同意披露）**：
   - 669 个 vol 01–12 有 lattice 半版重跑检测/映射（真迹，不补假字）；先 01_0006 L「一」；
   - 504 个 vol 00/13 半版：owner 定口径（总目/补遗是否入字表）；
   - 40 个无 lattice 半版：核对是否确无字头；
   - 交付：mapping v272+、覆盖/缺口重算、page_geometry_gate 严格 0。
2. **高频缺 23（含 一/王/法）**：与 A1 同批重定位；7 个异体口径字给 owner 结论。
3. **缺口 6,300 策略（BF-41）**：owner 决定 headword-only 不补 vs D19 重定位；写入 DECISIONS。

### B. 口径决策（owner）
4. **缺件 165 口径**：prune 边缘清理 vs 真实缺笔分类后定阈值/披露（与 v2.6.x 修复联动）。
5. **扫描闸阈值模式**：BF-10 统一（零余量披露/上一版 delta 记录）。

### C. 闸/流程/材料（可执行）
6. BF-10/17/18/24/44/47/49/51/25/28/36/38/39/42：闸契约、材料数字同源、三件套强制、
   扫描/构建归因、audit 现状文档、脚本 keep/archive、降级标记、文档清理、check_terms、milestone.json、new_candidate。
7. 里程碑包材料：01-changes（本里程碑变更集）、02-class-sample、03-regression-random-100、
   known-debt 清单、coverage/QA 机器生成、RELEASE-INVENTORY 状态列。

### D. 里程碑硬条件（CS4/CS5）
8. BF-29 隔离 9 字结论（入字体或隔离+理由，随包）；
9. BF-30 100 字 owner 签核（✓/✗/? 全闭环）；
10. BF-31 部界锚点严格重校验 + 09–11/13 卷补锚点；
11. BF-32 标签精度抽样（扩大 n，按卷/部首分层）并披露；
12. BF-33 DATA 影印出版/扫描者/许可细节进包 PROVENANCE。

### E. 发布（顺序固定）
13. 全量重建 → 快闸/全闸（严格阈值）→ 复核包 → **clean tree** → `font_package`（不带 --allow-dirty）
    → `release_gate finalize`（zip==目录、SHA 覆盖 gate-report）→ 冻结 v2.6.3。

## 4. 自审计转入的次要项（2026-11-13，v2.6.x/v2.6.3）

- **版本指标补全**：v2.5.8 缺件/框线/页几何未按现行口径重跑（表内 —）；v2.6.1 相对变化字数未实测；
- **审计方法**：参考字体 IoU 标签审计噪声过大（4,675 flagged），改用 OCR 交叉核对（`work/lead/ocr_*`）；
- **脚本清理**：BF-49 顶层死脚本判定；`make_readme_images.py` 清理已完成；release_metrics 输出格式统一（—）；
- **图片许可**：`docs/images/` 中扫描书影属原文节选，已在 LICENSE/README 注明不在 MIT/OFL 范围；
- **发布包 README**：模板图片需打包时以 `--extra` 附入（specimen/book-vs-font）；
- **version-artifacts**：新候选（a8bb87d9）产物清单待补；
- **metrics 脚本**：`VERSIONS` 增减后需重跑并回写 `docs/RELEASE-METRICS.md` 表。
