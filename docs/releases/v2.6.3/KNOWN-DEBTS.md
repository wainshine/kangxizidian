# v2.6.3 已知债与披露（随包发布）

> 本文件是 v2.6.3 **正式发布包 r1（返工重发，2026-11-14）**的已知债清单（逐项披露，不宣称清零）。
> r1 变更：「而」框收紧修掉下邻注文框线；根 README/门脸图同步 v2.6.3；「字」的 prune 误删真迹列入下节（v2.6.5 类级修）。
> 指标定义与判据：`docs/reference/RELEASE-METRICS.md`；发布前自审计：`docs/releases/v2.6.3/SELF-AUDIT.md`；
> 详细证据：`docs/ERRATA.md`（E39/E40）、`docs/BACKLOG.md`、`docs/LAYOUT.md`。

## 1. 覆盖类

| 项目 | 数字 | 说明 / 计划 |
|---|---|---|
| 字形数 | **17,006**（headword-only 真迹） | 较 v2.6.2 +1（新增 釕 U+91D5）；基本区 10,268/20,992 = **48.91%**；目标表 10,268/16,567 = **61.98%**；缺口 **6,299** |
| empty_assign 半版 | **1,172** | 有 content quad 但 mapping 无行：vol 01–12 **668** / vol 00+13 **504**（含 40 个无 lattice 半版）；v2.6.3 因 04_0048 R 补 1 行，1,173→1,172；后续 2.6.x 补丁补映射（先 01_0006 L「一」，计划 v2.6.4+） |
| 高频缺 | 仍缺（与目标缺口 6,299 重叠） | 与 empty_assign 一并重定位；异体口径待 owner |

## 2. 字形质量类

| 项目 | 数字 | 说明 / 计划 |
|---|---|---|
| 标签错配（BF-54） | 基本区 **5 字已修**；扩展区 **6 字 defer** | 本批重定位：愈 U+6108、急 U+6025、架 U+67B6、紉 U+7D09、釘 U+91D8；旧釘框改标 **釕 U+91D5**（+1 字）。扩展区 6 字（䬩 U+4B29、䃧 U+40E7、𣟴 U+237F4、𧂁 U+27081、𧔁 U+27501、𧖤 U+275A4）按 owner 2026-11-14 决定本轮不处理（defer/ACCEPT），不补假字 |
| 缺件扫描（BF-06） | **19 字 / 20 组件** | 主因修复见 E40：扫描侧 `precut_masks.apply_precut_masks()` 的 `np` NameError 被 `except: pass` 吞掉（crossing 过滤 fail-open）→ 旧披露 165 中约 150 为扫描误报；修复后对同一字体重扫 19/20。残余：**17 prune_loss**（owner 2026-11-14 视觉复核判 prune 删除正确=边角料，不修）+ **3 scan 残差**（㓚、譵×2，披露）。**不得写成「已清零」** |
| 内容闸 | **0**（基线 v2.6.2；累计 vs v2.5.8 = 18） | patch 线内容基线按 owner 决定改为 v2.6.2；累计 v2.5.8 的 18 多为跨架构归一化差异（E31），D23 源墨保真度判据待 owner |
| 字形级框线 | **0** | glyph_frame_gate PASS |
| 源图框线逃逸 | **0** | ≤3px@300 亚像素线不计（E37 口径） |
| clean_ink_loss | 5 组件（旧集） | owner 2026-11-14 复核：模拟保留会找回误删部件，但同时带回边角料（trade-off）→ 本批不改 clean_ink，登记已知债；类级改进排 v2.6.4+ |
| 剩余边角料 | 少量 | round-005 owner 复核：个别字（#6 釕、#12 廁）仍有少量边角料混入，owner 指示「先不管」，登记 known-debt；r1 已修「而」的注文框线残片 |
| 「字」等 prune 误删真迹 | 已确认 1 字 | `字`（U+5B57）构建时 9→7 条轮廓：prune 把宀的点/钩当作字墨 bbox 边缘碎片删除，字形读似「孑」；属**类级 prune 判据**问题，v2.6.5 修（不可单字补丁）。r1 门脸图不使用「字」 |

## 3. 发布证据链说明

- 本版 T4 已修：OFL 单源、`FINALIZE.json`（包内 + 包外 detached）、finalize staging 原子替换、扫描产物 sha/manifest 绑定、`verify_release`、`glyph_diff` 精确变化字、RELEASE-INVENTORY 生成器。
- 包内 `FINALIZE.json` 的 zip 自指字段为 `null`+scope 说明；实际终验值（zip sha、sha_final_ok/zip_ok）在包外 detached `FINALIZE.json`（与包同名、置于 `release/` 根；zip 自指不可内嵌，见 `docs/WORKFLOW.md §8bis`）。
- v2.6.2 冻结包不回填新证据字段（只读）。

## 4. 里程碑硬条件（本包尚未闭环）

隔离 9 字结论、100 字 owner 签核、09–11/13 卷部界锚点、标签精度抽样披露、DATA 许可细节。
本包为 v2.6.3 正式发布：上述为**已披露已知债**，不随包宣称已解决。
