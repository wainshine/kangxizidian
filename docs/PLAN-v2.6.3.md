# PLAN v2.6.3 —— 正式发布里程碑（v2.6.2 之后的收敛计划）

> 背景（2026-11-13）：v2.6.2 工程候选达到「快闸 8/8 PASS + 全闸 8 PASS/3 FAIL（3 项已知债）」
> 的候选标准，但**未达到 `docs/WORKFLOW.md` §7 正式发布标准**（见 §1）。
> v2.6.2 以 **preview 包**（`release/_preview/KangXiKai-v2.6.2-preview`）冻结供效果评估；
> 剩余 P0/口径/材料项全部纳入 **v2.6.3**，按本文验收后出正式包。

## 0. 当前快照（v2.6.2-preview）

- 字体 sha256 `b73e9f01ac39dd094d51895a2c740c75f26889e8482ba4abd26165dc30e9c24d`，17,005 字；
- 覆盖：基本区 48.91%（10,267/20,992）、目标表 61.97%（10,267/16,567）、缺口 6,300；
- 快闸 8/8 PASS；全闸 8 PASS / 3 FAIL：缺件 32、源图框线 1、页几何 empty_assign 1,173；
- 内容 29/35（E31 归因跨架构差异，判据改版 D23 待确认）。

## 1. 为什么现在不能发正式包（WORKFLOW §7 硬条件对照）

| §7 条件 | 现状 | 结论 |
|---|---|---|
| L1–L3 全 PASS（内容 0、框线 0 或 owner 同意且低于上版、几何校验） | 内容 29（D23 未定）、框线 1、empty_assign 1,173 | ✗ |
| 变更集人工复核 01-changes（✗≤2%） | 未生成/未复核 | ✗ |
| 02-class-sample 全 ✓ / 03-regression-random-100 ✓≥98% | 未做 | ✗ |
| owner 批量签核、已知债冻结 | 未做；P0 债（empty_assign）未清零 | ✗ |
| 包内容齐全、SHA 覆盖 gate-report、zip 自检 | 预览包已自检；正式 finalize 未做 | 部分 |
| 字体结构本里程碑内不再变化 | 仍在演进（v2.6.3 将改 mapping） | ✗ |

## 2. v2.6.3 工作项（按顺序）

### A. P0 数据/覆盖（阻塞发布）
1. **empty_assign 1,173 → 0（或 owner 同意披露）**：
   - 669 个 vol 01–12 有 lattice 半版重跑检测/映射（真迹，不补假字）；先 01_0006 L「一」；
   - 504 个 vol 00/13 半版：owner 定口径（总目/补遗是否入字表）；
   - 40 个无 lattice 半版：核对是否确无字头；
   - 交付：mapping v272+、覆盖/缺口重算、page_geometry_gate 严格 0。
2. **高频缺 23（含 一/王/法）**：与 A1 同批重定位；7 个异体口径字给 owner 结论。
3. **缺口 6,300 策略（BF-41）**：owner 决定 headword-only 不补 vs D19 重定位；写入 DECISIONS。

### B. 口径决策（owner）
4. **D23 内容判据**：确认改「源墨保真度」（字形投影 vs 自身 source ink 配准 IoU）+ 基线；
   旧字体 delta 只作回归告警。
5. **缺件 32 口径**：11 edge_pruned + 22 sliver（interior 0）是否按 prune-by-design 排除；
   若排除，缺件闸口径改为「interior 真实缺笔=0」并记录。
6. **框线 1（㨜）**：接受为已知债披露，或补页级 band 清零（kernel 加宽风险已知）。
7. **扫描闸阈值模式**：BF-10 统一（零余量披露/上一版 delta 记录）。

### C. 闸/流程/材料（可执行）
8. BF-10/17/18/24/44/47/49/51/25/28/36/38/39/42：闸契约、材料数字同源、三件套强制、
   扫描/构建归因、audit 现状文档、脚本 keep/archive、降级标记、文档清理、check_terms、milestone.json、new_candidate。
9. 里程碑包材料：01-changes（本里程碑变更集）、02-class-sample、03-regression-random-100、
   known-debt 清单、coverage/QA 机器生成、RELEASE-INVENTORY 状态列。

### D. 里程碑硬条件（CS4/CS5）
10. BF-29 隔离 9 字结论（入字体或隔离+理由，随包）；
11. BF-30 100 字 owner 签核（✓/✗/? 全闭环）；
12. BF-31 部界锚点严格重校验 + 09–11/13 卷补锚点；
13. BF-32 标签精度抽样（扩大 n，按卷/部首分层）并披露；
14. BF-33 DATA 影印出版/扫描者/许可细节进包 PROVENANCE。

### E. 发布（顺序固定）
15. 全量重建 → 快闸/全闸（严格阈值）→ 复核包 → **clean tree** → `font_package`（不带 --allow-dirty）
    → `release_gate finalize`（zip==目录、SHA 覆盖 gate-report）→ 冻结 v2.6.3。

## 3. v2.6.3 验收清单（缺一不发）

- [ ] page_geometry_gate：bad_boxes 0、empty_assign 0（或 owner 披露阈值）、missing_quad_chars 0
- [ ] glyph_frame_gate 0；frame_escape 0 或 owner 披露（比 v2.6.2 下降）
- [ ] content 判据按 D23 确认后的基线 PASS（或 owner 披露阈值）
- [ ] 缺件按 D23/BF-06 口径 PASS 或披露
- [ ] font_qa PASS；provenance PASS；输入绑定齐全
- [ ] 01-changes ✗≤2%、02-class-sample 全 ✓、03-regression-random-100 ✓≥98%
- [ ] owner 签核闭环、已知债清单冻结、材料数字机器校验 PASS
- [ ] clean tree + finalize 顺序 + zip 自检 PASS

## 4. v2.6.2 → v2.6.3 之间明确不做的事

- 不重打 v2.6.2 正式包（预览包仅评估用，不签收）；
- 不用单字补丁修 empty_assign/缺件（走 mapping/几何类级修复）；
- 不回退 pre-cut 架构（D22）；不引入专有字体（D21）。
