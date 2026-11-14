# v2.6.3 发布前自审计（SELF-AUDIT）

> 目的：在打包前用可复算证据回答「这一版能不能发」。本文件随发布材料提交；最终以包内 `FINALIZE.json`
> 与 `release/RELEASE-INVENTORY.tsv` 为准。

## 1. 构建可复现

- clean-HEAD 重建：`git status` clean、`build_stats.git.dirty=false`；r1 字体 sha **`2414847b…`**（在 v2.6.3 首包基础上仅改 `而` 的映射框，mapping v274）；
- mapping `work/lead/mapping_block_v273.jsonl`（仅 5 条基本区行级改动 + 釕；其余行逐字节不变）；
- manifest 由 build_stats 生成（17,006 字）；`build_recipe` 由 build_stats 派生（cache_ver=算法 sha8+geometry sha12+bands sha12、git commit、真实构建时间、input sha）。

## 2. 闸结果（v2.6.2 content 基线）

| 项 | 结果 | 证据 |
|---|---|---|
| font_qa | **PASS**（同框 0） | `qa-report` / `qa-stats` |
| glyph_frame_gate | **0**（17,006 字，errors 0） | `gate-report.glyph_frame_gate` |
| scan_frame_escape | **0**（0 error） | `frame_scan_v263-clean.jsonl` + sidecar |
| content_loss（vs v2.6.2） | **0 damaged**（阈值 18） | `content-loss-v262-v263.json` |
| scan_missing_parts | **19 字/20 组件**（17 prune_loss + 3 scan，unknown=0） | `missing_scan_v263-clean.jsonl` + sidecar + 归因 |
| page_geometry_gate | bad_boxes **0**；missing_quad_chars **0**；empty_assign **1,172**（披露） | `page-geometry-gate-v263.json` |
| fast_gate | **8/8 PASS** | `fast-gate-v263.json` |
| 变化字 | changed **5** + added **1** + removed **0**（精确轮廓） | `diff-v262-v263.json` / `glyph_diff.py` |
| release_gate | finalize 结果见包内 `FINALIZE.json` | 包外 detached `release/KangXiKai-v2.6.3.FINALIZE.json` |

## 2bis. r1 返工（2026-11-14）

- 首包（font sha `6dd473b9…`、zip sha `e943182b…`）发现：根 README 仍 v2.6.2；门脸图显示「而」带下邻注文框线、「字」prune 误删宀点/钩。
- r1 修复：「而」mapping 框 `[625,358,728,454]`（mapping v274）→ 字体 sha `2414847b…`；根 README/门脸图/样张同步 v2.6.3（图内避开「字/而/山」等已知缺陷字）；「字」披露并留 v2.6.5。
- 首包已撤回并在 ERRATA E41 记录；本文件与包内数字以 r1 为准。

## 3. 本批声明的变化（不是回归）

- BF-54 基本区 5 字重定位 + 旧釘框改标 釕：内容闸（v2.6.2 基线）0 damaged；相对 v2.5.8 的累计 17 单列披露；
- BF-06 扫描修复：缺件口径从 165（扫描误报为主）改为 19/20；E40 已记录旧 165 作废，不得再按旧值调参；
- 扩展区 6 字 defer（owner 决定）；不补假字。

## 4. 已知限制 / 残余风险

1. 包内 `FINALIZE.json` zip 自指字段 `null`+scope；实际 zip sha/终验在包外 detached（zip 自指不可内嵌，WORKFLOW §8bis）；
2. 缺件残余 19/20（17 prune 判正确 + 3 scan 残差）；clean_ink 5 组件 trade-off；少量剩余边角料——均披露，不宣称清零；
3. empty_assign 1,172 仍为严格闸 FAIL（披露阈值）；D23 内容判据待 owner；
4. 里程碑硬条件未闭环；v2.6.3 为 patch 线正式版，不是里程碑（GAN/带状扫掠留 v2.7.0）。

## 5. 复验命令

```bash
.venv/bin/python scripts/verify_release.py --dir release/KangXiKai-v2.6.3 \
  --zip release/KangXiKai-v2.6.3.zip --finalize-json release/KangXiKai-v2.6.3.FINALIZE.json
.venv/bin/python scripts/check_release_docs.py --dir release/KangXiKai-v2.6.3 --version 2.6.3
cd release/KangXiKai-v2.6.3 && shasum -a 256 -c SHA256SUMS && unzip -t ../KangXiKai-v2.6.3.zip
```
