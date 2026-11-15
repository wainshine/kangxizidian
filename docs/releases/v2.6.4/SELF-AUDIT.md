# v2.6.4 发布前自审计（SELF-AUDIT）

- 日期：2026-11-15
- 字体：`work/font/build/KangXiKai-v2.6.4.ttf`
- font sha256：`9740e7aa519873273ccea2d9d021b0a67490cb19f0c9f7195e0ee3c726487214`
- manifest：`work/font/build/manifest_v264.json`
- mapping：`work/lead/mapping_block_v275.jsonl`
- build_stats：`work/font/build/KangXiKai-v2.6.4.build_stats.json`
- git：clean tree（构建记录见 build_recipe；本文件随包）

## 1. 数据源与选字

- headword-only（D15）：只收字头大字，不收注文小字、不补生成字；
- `字` 修正：mapping 旧框 `03_0007 L [603,340,703,438]` 是另一大字（非字头）；真字头为 `[697,1169.275,791,1267.375]`（150dpi，2×2 块 ∩ quad）；修正后 `字` 为 4 条轮廓，旧为 7 条。
- 古文异体修正 4 字：凔/濬/眞/䞯 原框落在「古文」下方大字异体块上；改为古文上方正字完整 2×2 块。**不使用单字补丁**，全部经 mapping 行级修正。
- `硜` 保持当前 mapping（owner 目检红框正确）；「或作」5 例为注文小字异体，其后大字是下一字头，mapping 不改。

## 2. 精确变化（相对 v2.6.3 r1）

- `glyph_diff.py`：**changed 5（字/凔/濬/眞/䞯）/ added 0 / removed 0**；
- `declared_changes`：`work/lead/declared-changes-v264.json`（随包 material）；
- 内容闸（基线 v2.6.3）：**0 damaged**，17,006/17,006 覆盖。

## 3. 闸结果

| 闸 | 结果 |
|---|---|
| font_qa | PASS（同框 0） |
| glyph_frame_gate | 0 flagged |
| scan_frame_escape | 0 flagged / 0 error |
| content_loss_gate（v2.6.3 基线） | 0 damaged |
| scan_missing_parts | 19 字 / 20 组件、error 0 |
| page_geometry_gate | bad_boxes 0 / empty_assign 1,172（披露） |
| provenance_gate | PASS |
| fast_gate | 8/8 PASS |

## 4. 可复现与证据链

- 构建：`FONT_BUILD_WORKERS=10 font_build --mapping work/lead/mapping_block_v275.jsonl --out ... --version 2.6.4`；
- 扫描：`scan_missing_parts` / `scan_frame_escape` 均带 sidecar（含 `out_sha256`），release_gate 复用时校验；
- 内容闸：baseline∩new 交集宇宙，`added/removed` 单列，sidecar 绑定判定结果与输出 sha；
- finalize：staging 全验 → 原子替换 → detached FINALIZE；`verify_release` 强制存在。

## 5. 未完成/披露

- empty_assign 1,172；缺件 19/20（17 prune 判正确 + 3 scan 残差）；BF-54 扩展区 6 字 defer；BF-61 框变化留 v2.6.5；role 审计 105 候选块剩余条目留 v2.6.5；D23/里程碑硬条件未闭环。
