# GLOSSARY · 术语表（唯一规范源）

> 冲突时以本文为准；新增术语先加这里再进代码/文档。历史迁移与勘误见 `docs/ERRATA.md`。

## 1. 版面与裁切

| 术语 | 定义 |
|---|---|
| **半版（L/R）** | 一页 PDF 是跨页扫描，按 gutter 分成左/右两个半版 |
| **gutter（中缝）** | 左右半版分界；由列墨投影 42%–58% 区间最小值定位 |
| **版框（外框/内框）** | 刻本页四周的双线框；外粗内细；**必须在裁切阶段排除** |
| **界行** | 列与列之间的竖细线；与版框同属「版面线」，不进入字形 |
| **页边黑带** | 扫描页边缘的黑色带（装订/扫描造成），同样排除 |
| **content quad（版框正文区）** | 每半版「版框内」的矩形（含微旋转矩阵 M/Minv）；裁切时 clip 到它，框线从不进入 ink |
| **content box** | content quad 的轴对齐描述（`(x0,y0,x1,y1)`，150dpi） |
| **裁片（crop）** | 以字框 box 为中心、pad=6@150dpi 渲染出的 300dpi 灰度图 |
| **150dpi 坐标** | 项目统一坐标：lattice、box、manifest 都用它；渲染裁片用 300dpi（`dpi_scale=2.0`） |
| **page key** | `NN_PPPP`（卷号两位 + 页码四位，如 `02_0074`） |

## 2. 格点与字头

| 术语 | 定义 |
|---|---|
| **小字（注文）** | 正文中双行小字注文；每个小字中心 = 一个**格点节点** |
| **lattice（格点）** | 每半版拟合的 `(px,py,phx,phy)`：列距/行距/相位；小字中心 = `(phx+c·px, phy+r·py)` |
| **2×2 格块（block）** | 字头大字 = 2×2 个小字格（面积≈4 小字）；块左上 = 节点 − 半格，外扩 3px |
| **block mask** | 只保留 2×2 块内墨的掩膜（块外邻字/注文丢弃） |
| **box（字框）** | 单字裁切框（150dpi）；v2.6.1 起 = 2×2 块 ∩ content quad，面积应均匀 |
| **字头 / 注文** | 本项目只收**字头真迹**（headword-only）；注文小字不收（D15） |
| **正典序（canonical）** | 《康熙字典》字头排列顺序（42,302 条 → 16,567 唯一基本区字）；`work/seq/canonical.jsonl` |
| **叶码** | 原书页码 = 扫描页 − 5（D14）；早期「×2−11」公式已作废 |

## 3. 映射与构建

| 术语 | 定义 |
|---|---|
| **mapping** | 正典序条目 → 页面/半版/box 的指派；**唯一真源** `work/lead/mapping_verified_all33.jsonl` |
| **block mapping** | v2.6.1 起：box = 2×2 块 ∩ content quad；`work/lead/mapping_block_v270.jsonl` |
| **manifest** | 字形清单（char → page/half/box/label_source），构建输入 |
| **geometry cache** | 页级几何预计算（lattice/text_bbox/content quads），`work/lead/page_geometry.jsonl` |
| **cache key** | 字形缓存键 = **算法脚本 sha8 + page_geometry.jsonl sha12** + page/half/char/box；自动版本化（人工 tag 已废弃） |
| **脏集（dirty set）** | 本次变更实际影响的字集合；只重建脏集 |
| **归一化** | 以主字簇 bbox 为基准，最长边 → **760 font units**（UPM 1000） |
| **pre-cut** | 在二值化/清理**之前**排除版面元素（content clip + 裁片外带规则） |

## 4. 修复与版本

| 术语 | 定义 |
|---|---|
| **restore/overlay** | 从旧字体整字拷贝字形来「修复」——**已废弃**，会把旧框线带回（勤 事件） |
| **类级修复** | 一次修一类问题（可复现、影响面清楚）；禁止单字补丁 |
| **变更集（change set）** | 一轮变更的唯一单位：scope/root_cause/fix/verification（`work/changesets/cs-*.jsonl`） |
| **候选（candidate）** | 字体 + 快闸 + 复核包；编号 `cYYYYMMDD-n`，不进 `release/` |
| **里程碑（milestone）** | 满足发布四条件后打正式包的节点（见 WORKFLOW §7） |
| **正式包（release）** | `release/KangXiKai-vX.Y.Z/` + zip；SHA 覆盖 gate-report；finalize 后冻结 |
| **隔离字** | 内容/参考闸残余、待重定位的字（当前 9 字），发布时点名披露 |

## 5. 闸与指标

| 术语 | 定义 |
|---|---|
| **fast_gate（快闸）** | ≤3 分钟：QA/版本/字符 diff/内容闸/box 均匀性/文档/SHA |
| **full_gate（全闸）** | release_gate 全库扫描：缺件/框线逃逸/几何校验/映射审计；仅里程碑前跑 |
| **内容闸（content gate）** | 新旧字形 ink_ratio/IoU（vs 基线 v2.5.8）：damaged 计数，阈值披露 |
| **缺件扫描** | 源块组件未被字形覆盖（content clip + block 区域口径） |
| **框线逃逸闸** | 块内「贯穿块」的框线残留检测 |
| **box 均匀性** | 同页/同半版框尺寸方差（应≈0；block mapping 下同页完全一致） |
| **字形级框线闸** | 对 TTF 输出逐字检测细长贯穿线（v2.6.0 盲区补丁，待实现 CS1） |
| **provenance 闸** | 每个字形须来自本版管线（page/box/算法可追溯）；禁止整字拷贝 |
| **owner 标记** | 复核图上按编号标 `✓ / ✗ / ?`；AI 据此归因到类 |

## 6. 命名

- 正式版本 `vX.Y.Z`；候选 `cYYYYMMDD-n`；**禁止把线名/分支名写进版本号**。
- 文件名：`KangXiKai-Regular-v<ver>.ttf`、`manifest-v<ver>.json`、`gate-report-v<ver>.json`、`coverage-detail-v<ver>.json`。
- 数据文件：`mapping_verified_all33.jsonl`、`mapping_block_v270.jsonl`、`page_geometry.jsonl`、`defect-ledger-v258.jsonl` 等带来源/版本后缀。
- 字体家族名固定 `KangXi Kai`；`KangXiKai-v<ver>.ttf` 是构建文件名，不是家族名。
