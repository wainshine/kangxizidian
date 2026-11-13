# RELEASE v2.6.2 · 康熙楷 KangXi Kai

- **发布日期**：2026-11-14
- **发布类型**：正式包（2.6 补丁线；披露已知债的小版本）
- **包路径**：`release/KangXiKai-v2.6.2/` + `release/KangXiKai-v2.6.2.zip`
- **构建来源**：clean git tree `8622ba89…`（dirty=false）
- **字体 sha256**：`a8bb87d9c4a623d5fe88ae55c2f710a36827052c7cd3594fe70113f56ca18d5b`
- **zip sha256**：见 `release/RELEASE-INVENTORY.tsv`（包内 `SHA256SUMS` 覆盖 32 个文件，含 `review/`）
- **finalize**：17/17 PASS（sha_final_ok / zip_ok / doc_check / clean_tree 全过）

## 规模与覆盖

- 字形 **17,005** 个（headword-only 真迹，无生成字）；
- 基本区 10,267/20,992 = **48.91%**；目标表 10,267/16,567 = **61.97%**；缺口 **6,300**。

## 闸与披露阈值

| 闸 | 结果 | 披露阈值 |
|---|---|---|
| font_qa | PASS（同框 0） | 严格 |
| 字形级框线（glyph_frame_gate） | **0** | 严格 0 |
| 框线逃逸（scan_frame_escape） | **0** | 严格 0 |
| 内容（content_loss vs v2.5.8） | **18** | 35 |
| 缺件（scan_missing_parts） | **165** | 165（阈值=观测值，零余量） |
| 页几何 bad_boxes / empty_assign | 0 / **1,173** | 0 / 1,173 |

## 已知债（详见包内 `KNOWN-DEBTS.md`）

1. empty_assign 1,173（669 个 vol 01–12 半版 + 504 个 vol 00/13 + 40 无 lattice）；后续 2.6.x 补丁补映射；
2. 11 字标签错配（v2.6.3 批 BF-54 按页重定位）；
3. 缺件 165（v2.6.3 批 BF-06 修 prune 边缘清理口径）；
4. 内容判据 D23（源墨保真度）待 owner；
5. 里程碑硬条件（隔离 9 字 / 100 字签核 / 勘界锚点 / 标签精度 / DATA 许可）未闭环。

## 包内容

字体、manifest、provenance-detail、coverage-detail、qa-report/qa-stats、gate-report、content-loss、
residual-quarantine、release-metrics、PROVENANCE.md、QA.md、README.md（含图）、RELEASE-NOTES、build_recipe、
KNOWN-DEBTS、LICENSE/OFL、`review/` 复核快照、SHA256SUMS。

## 复验

```bash
cd release/KangXiKai-v2.6.2 && shasum -a 256 -c SHA256SUMS
unzip -t ../KangXiKai-v2.6.2.zip
```
