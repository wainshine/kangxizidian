# RELEASE v2.6.4 · 康熙楷 KangXi Kai

- **发布日期**：2026-11-15
- **发布类型**：正式包（2.6 补丁线；字形正确性 + 证据硬化）
- **包路径**：`release/KangXiKai-v2.6.4/` + `release/KangXiKai-v2.6.4.zip`
- **构建来源**：clean git tree（dirty=false；commit 见包内 `build_recipe-*.json`）
- **字体 sha256**：`9740e7aa519873273ccea2d9d021b0a67490cb19f0c9f7195e0ee3c726487214`
- **zip sha256**：见 `release/RELEASE-INVENTORY.tsv`（包内 `SHA256SUMS` 覆盖全部非 SHA 文件）
- **finalize**：以包内 `FINALIZE.json` + 包外 detached `release/KangXiKai-v2.6.4.FINALIZE.json` 为准

## 规模与覆盖

- 字形 **17,006** 个（headword-only 真迹，无生成字）；
- 基本区 10,268/20,992 = **48.91%**；目标表 10,268/16,567 = **61.98%**；缺口 **6,299**。

## 本版改了什么（相对 v2.6.3 r1）

1. **「字」字形修正（mapping 选错源框）**：旧 mapping 把 `03_0007 L` 顶部另一个大字块标成「字」；真字头为古文标签上方块 `[697,1169.275,791.0,1267.375]`。修正后「字」为 4 条轮廓的正确字形（旧为 7 条错字形）。此前 `KNOWN-DEBTS` 的「prune 误删真迹」归因错误，见 ERRATA E43。
2. **古文异体标签修正（4 字）**：凔、濬、眞、䞯 的 mapping 框原本落在「古文」下方的大字异体块上；改用**古文上方正字完整 2×2 块**重新取字（避免半字切片）：
   - 凔 `01_0156 R [1016,535,1094,617]`
   - 濬 `06_0127 R [1154.95,842.7,1257.15,942.5]`
   - 眞 `07_0196 L [522.65,494.0,624.85,590.8]`
   - 䞯 `10_0205 L [423.75,613.0,525.95,711.8]`
3. **role/异体规则审计（不改变字体）**：
   - 全库使用本地 PaddleOCR 检测「古文/或作」标签，识别出 105 个古文/或作后的异体大字块（101 页）；
   - 确认「或作」后紧跟的是**注文小字异体**，其后大字是**下一个字头**，不是「或作」异体；原 detector 的 5 个「或作」冲突为误报，mapping 不改；
   - 硜 `07_0273 L` 经 owner 目检：当前红框正确，不改；
   - 其余异体候选与条目 role 留 `work/lead/variant-ledger-v264.jsonl`，v2.6.5 继续。
4. **BF-61 代码修复（未应用）**：`make_block_mapping.py` 统一 M/Minv 坐标系 + dry-run；1,764 个框变化留 v2.6.5 role 审计后统一应用，本版 mapping 不并入。
5. **Phase 1 证据/工程硬化**：内容闸交集宇宙契约、扫描/内容复用防篡改、BF-51 页级 pre-cut 可见化、BUILD-402 env 入缓存键、font_qa/font_package/verify_release 等 fail-closed 加固（详见变更集与 SELF-AUDIT）。

精确 glyf 轮廓差异（vs v2.6.3 r1）：**changed 5（字/凔/濬/眞/䞯）+ added 0 + removed 0**（`scripts/glyph_diff.py`）。

## 闸与披露阈值

| 闸 | 结果 | 披露阈值 |
|---|---|---|
| font_qa | PASS（同框 0） | 严格 |
| 字形级框线（glyph_frame_gate） | **0** | 严格 0 |
| 框线逃逸（scan_frame_escape） | **0** | 严格 0 |
| 内容（content_loss，基线 v2.6.3） | **0** | 严格 0；变化字列入 `declared_changes` |
| 缺件（scan_missing_parts） | **19 字 / 20 组件** | 19（阈值=观测值，零余量；17 prune 判正确 + 3 scan 残差披露） |
| 页几何 bad_boxes / empty_assign | **0 / 1,172** | 0 / 1,172（披露） |

## 已知债（详见包内 `KNOWN-DEBTS.md`）

1. empty_assign 1,172（vol 01–12 668 / vol 00+13 504，含 40 无 lattice）；
2. BF-54 扩展区 6 字 defer；BF-61 mapping 生成器代码已修、框变化留 v2.6.5；
3. 缺件残余 19/20：17 prune_loss 判正确（边角料）+ 3 scan 残差（㓚、譵×2）；
4. clean_ink 5 组件 trade-off 与少量剩余边角料，owner 指示先不管；
5. 内容判据 D23 待 owner；累计 vs v2.5.8 单列披露；
6. 里程碑硬条件（隔离 9 字 / 100 字签核 / 勘界锚点 / 标签精度 / DATA 许可）未闭环。

## 包内容

字体、manifest、provenance-detail、coverage-detail、qa-report/qa-stats、gate-report、content-loss、
residual-quarantine、release-metrics、PROVENANCE.md、QA.md、README.md（含图）、RELEASE-NOTES、build_recipe、
build_stats、KNOWN-DEBTS、LICENSE/OFL、missing/frame 扫描 jsonl+sidecar、FINALIZE.json、`review/` 复核快照（round-007）、SHA256SUMS。

## 复验

```bash
cd release/KangXiKai-v2.6.4 && shasum -a 256 -c SHA256SUMS
unzip -t ../KangXiKai-v2.6.4.zip
.venv/bin/python scripts/verify_release.py --dir release/KangXiKai-v2.6.4 \
  --zip release/KangXiKai-v2.6.4.zip --finalize-json release/KangXiKai-v2.6.4.FINALIZE.json
```
