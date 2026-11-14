# METHOD · 技术路线（可读版）

> 给使用者/非开发者看的「这套字体是怎么做出来的」。工程参数与复现命令见 `docs/PIPELINE.md`（唯一权威）；
> 架构与目录见 `docs/ARCHITECTURE.md`；决策依据见 `docs/DECISIONS.md`。

## 1. 从扫描到字头（S1 + S2）

- **源材料**：《康熙字典》清康熙五十五年内府刊本（1716），書格 shuge.org 数字化，14 册 / 3,869 页；
- **页级几何（S1）**：小字组件中心拟合每半版的格点周期与相位；检测版框/界行，得到正文区
  （`content_quad`，含页面微旋转矩阵）；产物 `work/lead/page_geometry.jsonl`；
- **字头定位（S2）**：按正典序（canonical 42,302 条 → 唯一基本区 16,567 字）把每个字对应到
  「页 / 半版 / 2×2 小字格块」；字头 = 2×2 格块，框 = 块 ∩ 正文区；产物
  `work/lead/mapping_block_v271.jsonl`（17,005 字，headword-only 真迹）。

## 2. 裁切（pre-cut）

每个字头按 300dpi 直渲染 box+pad，然后**在二值化前后按几何排除版面**：

1. 正文区外像素（版框/页边黑带/角部楔形）在掩膜前就置零；
2. 裁片外带的贯穿长线整条裁掉；
3. 页级直线 mask（长线 + E37 细线 crossing 过滤：只删穿越 2×2 块边界的线，块内细长笔画保留）；
4. 已验证的页级线条带（`page_line_bands.json`，27 rect）无条件应用；
5. 只保留 2×2 块内墨迹（块外邻字/注文丢弃）。

> 原则：**框线不进入二值图**，而不是「切进来再擦」（D22）。

## 3. 矢量化与归一化

- 主簇清理：保留最大主组件及邻近组件，剔除孤立碎片/贴边残片；E37 起增加「远离主体 >15px 且面积 <5% 主体」
  的注文/邻墨残片规则；
- potrace 2× 超采样描迹（避免偏移）；
- 归一化：以**字墨 bbox 最长边 → 760 font units**（UPM 1000），bbox 中心 → (500,400)；
- 轮廓整理：方向/回字规则 + 边缘清理（`prune_edge_contours`；缺件 165 的丢失阶段根因未定，E39）；
- 字体构建：合入 TTF，记录每字页/半版/框（provenance）。

## 4. 质量闸（S4）

| 闸 | 检查什么 |
|---|---|
| `font_qa` | 表/cmap==manifest/空字形/bbox/advance/同框；**不数孔洞/连通分量**（D21） |
| `content_loss_gate` | 新旧字形 ink_ratio/IoU（回归；跨架构差异见 E31/D23） |
| `glyph_frame_gate` | **输出字形**里的细长直线（框线回流） |
| `provenance_gate` | manifest/mapping/stats 自洽、无拷贝标记 |
| `page_geometry_gate` | quad 覆盖/box 坐标/空指派/块∩quad |
| `scan_missing_parts` | 源块组件未被字形覆盖（缺件） |
| `scan_frame_escape` | 源图块内贯穿线残留 |
| `fast_gate` / `release_gate` | 编排快闸（8 项）/ 全闸（17 项，含文档数字、SHA、zip、clean-tree、finalize） |

所有闸写输入绑定 sidecar（字体/manifest/mapping/几何/线条带/参考字体/脚本 sha + argv + git），复用前必须校验，失败 fail-closed。

## 5. 发布与复核

- 候选：构建 + 快闸 + 人工复核包（01-changes / 02-class-sample / 03-regression-random-100）；
- 正式包：clean git tree → `font_package`（README/已知债/指标/闸报告/复核快照）→ `release_gate finalize`
  （SHA 覆盖 gate-report、zip 自校验）→ 冻结。

## 6. 当前定位与后续

- v2.6.2：**17,005 个真实字头**，目标表覆盖 61.97%，缺口 6,300（含部分常用字）；字形框线 0、框线逃逸 0；
- 已知问题：缺件 165（根因未定，E39）、11 字标签错配、empty_assign 1,173（mapping 缺口）、内容判据 D23；
- 后续：2.6 补丁线（v2.6.3 起）修数据/口径；v2.7.0 计划引入 GAN + 带状扫掠生成回退（仅用于确实取不到真迹的缺口字，
  provenance 标注，不覆盖真实字头，见 `docs/plans/PLAN-v2.7.0.md`）。
