# RELEASE v2.6.3 · 康熙楷 KangXi Kai

- **发布日期**：2026-11-14
- **发布类型**：正式包 r1（2.6 补丁线；返工重发：修正「而」框边角料 + 根 README/门脸图同步；BF-54 基本区标签重定位 + BF-06 扫描修复 + 证据链修复）
- **包路径**：`release/KangXiKai-v2.6.3/` + `release/KangXiKai-v2.6.3.zip`
- **构建来源**：clean git tree（dirty=false；commit 见包内 `build_recipe-*.json`，本版字体由 clean-HEAD 重建复现）
- **字体 sha256**：`2414847b88457ffaee11fa2a2e89e3c456aa14efd867904119f032485b5a360f`
- **zip sha256**：见 `release/RELEASE-INVENTORY.tsv`（包内 `SHA256SUMS` 覆盖全部非 SHA 文件，含 `review/`）
- **finalize**：以包内 `FINALIZE.json` + 包外 detached `release/KangXiKai-v2.6.3.FINALIZE.json` 为准（finalize 全链 PASS 才允许出包）

## 规模与覆盖

- 字形 **17,006** 个（headword-only 真迹，无生成字；较 v2.6.2 +1：新增 釕 U+91D5）；
- 基本区 10,268/20,992 = **48.91%**；目标表 10,268/16,567 = **61.98%**；缺口 **6,299**。

## 本版改了什么（相对 v2.6.2）

1. **BF-54 基本区标签重定位（5 字）**：愈/急/架/紉/釘 按 2×2 大字块重新定位到真字头；旧釘框实际字改标 **釕 U+91D5**（+1 字）。精确 glyf 轮廓差异（vs v2.6.2）：**changed 6（含 r1 修的「而」）+ added 1 + removed 0**（由 `scripts/glyph_diff.py` 生成）。
   - **r1 返工**：`而` 的 mapping 框下边带入下邻注文框线（边角料）→ 框收紧为 `[625,358,728,454]`（mapping v274）；`字` 的 prune 误删真迹（宀点/钩，9→7 轮廓）留 v2.6.5 类级修，本版披露、门脸图不使用该字。
2. **BF-06 扫描侧修复（E40）**：`precut_masks.apply_precut_masks()` 补 `import numpy` + fail-closed，修复 crossing 过滤 fail-open；缺件披露从 165（扫描误报为主）更新为 **19 字/20 组件**（17 prune_loss + 3 scan 残差，unknown=0）。
3. **T4 发布证据链**：OFL 单源、`FINALIZE.json`、finalize staging 原子替换、扫描产物绑定校验、`verify_release`、`check_release_docs` 数值对账/篡改测试、`build_stats` 入包。
4. 页几何：04_0048 R 补 1 行 → empty_assign **1,173→1,172**；bad_boxes 仍 **0**。

## 闸与披露阈值

| 闸 | 结果 | 披露阈值 |
|---|---|---|
| font_qa | PASS（同框 0） | 严格 |
| 字形级框线（glyph_frame_gate） | **0** | 严格 0 |
| 框线逃逸（scan_frame_escape） | **0** | 严格 0 |
| 内容（content_loss，基线 v2.6.2） | **0** | 18（硬线；累计 vs v2.5.8 的 17 单列披露） |
| 缺件（scan_missing_parts） | **19 字 / 20 组件** | 19（阈值=观测值，零余量；17 prune 已判正确 + 3 scan 残差披露） |
| 页几何 bad_boxes / empty_assign | **0 / 1,172** | 0 / 1,172（披露） |

## 已知债（详见包内 `KNOWN-DEBTS.md`）

1. empty_assign 1,172（vol 01–12 668 / vol 00+13 504，含 40 无 lattice）；后续 2.6.x 补丁补映射；
2. BF-54 扩展区 6 字（䬩/䃧/𣟴/𧂁/𧔁/𧖤）本轮 defer（owner 决定，不补假字）；
3. 缺件残余 19/20：17 prune_loss 判正确（边角料）+ 3 scan 残差（㓚、譵×2）；
4. clean_ink 5 组件 trade-off（修则带回边角料）与少量剩余边角料，owner 指示先不管；
5. 内容判据 D23（源墨保真度）待 owner；
6. 里程碑硬条件（隔离 9 字 / 100 字签核 / 勘界锚点 / 标签精度 / DATA 许可）未闭环。

## 包内容

字体、manifest、provenance-detail、coverage-detail、qa-report/qa-stats、gate-report、content-loss、
residual-quarantine、release-metrics、PROVENANCE.md、QA.md、README.md（含图）、RELEASE-NOTES、build_recipe、
build_stats、KNOWN-DEBTS、LICENSE/OFL、missing/frame 扫描 jsonl+sidecar、FINALIZE.json、`review/` 复核快照（round-005）、SHA256SUMS。

## 复验

```bash
cd release/KangXiKai-v2.6.3 && shasum -a 256 -c SHA256SUMS
unzip -t ../KangXiKai-v2.6.3.zip
.venv/bin/python scripts/verify_release.py --dir release/KangXiKai-v2.6.3 \
  --zip release/KangXiKai-v2.6.3.zip --finalize-json release/KangXiKai-v2.6.3.FINALIZE.json
```
