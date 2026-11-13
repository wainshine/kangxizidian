# RELEASE-METRICS · 版本对比指标与「一版比上一版好」的判据

> 用途：发版（候选/正式）时用**同一套可复算指标**回答「v2.6.2 比 v2.6.1、v2.5.8 好在哪」，
> 而不是靠印象或单张样张。指标由 `scripts/release_metrics.py` 生成，落盘
> `work/lead/release-metrics.json` + `work/lead/release-metrics.md`，正式包内随包提供。

## 1. 指标定义（全部可复算）

| 组 | 指标 | 计算方式 | 方向 |
|---|---|---|---|
| 规模/覆盖 | chars | manifest 字数 | ↑（或持平） |
| | basic_covered | manifest ∩ U+4E00–U+9FFF | ↑ |
| | target_covered | manifest ∩ canonical 唯一基本区（16,567） | ↑ |
| | gap | 16,567 − target_covered | ↓ |
| 质量闸 | font_qa | `font_qa.py` 退出码 + 报告 | 必须 PASS |
| | glyph_frame_flagged | `glyph_frame_gate.py`（TTF 输出字形细长直线） | ↓，发布要求 0 或 owner 披露 |
| | content_damaged_vs_baseline | `content_loss_gate.py`（相对 v2.5.8 的 damaged 数） | ↓，阈值须披露 |
| 源级扫描 | missing_flagged | `scan_missing_parts.py`（与构建同口径） | ↓，阈值须披露 |
| | frame_escape_flagged | `scan_frame_escape.py`（源图块内贯穿线） | ↓，发布要求 0 或披露 |
| 页几何 | bad_boxes / empty_assign_halves | `page_geometry_gate.py` | ↓，empty_assign 为 mapping 缺口 |
| 快闸 | fast_gate | `fast_gate.py` 8 项 | 必须 PASS |
| 变更规模 | changed_glyphs_vs_prev | 与上一版字体逐字渲染比较（ink 比/IoU 阈值） | 报告项，不判优劣 |

## 2. 「更好」的判据（发版条件）

一版字体**优于上一版**（允许发版）当且仅当：

1. **覆盖不减**：chars、target_covered 不下降；gap 不扩大（若因隔离坏字导致 chars 略降，必须逐字披露）；
2. **质量闸不退化**：font_qa PASS；glyph_frame_flagged 不增加；content_damaged 不增加
   （若口径变化导致不可比，必须给同口径复算值）；
3. **源级/页几何不恶化**：missing/frame/empty_assign/bad_boxes 不增加（口径变化需复算并披露）；
4. **已知债逐项披露**：新增已知债必须归因、登记 BACKLOG，并随包披露；不得用「披露式阈值」掩盖新回归；
5. **可复现**：字体 sha、构建输入 sha、闸报告、版本对比指标随包；
6. **人工复核**：01-changes ✗≤2%、02-class-sample 全 ✓、03-regression-random-100 ✓≥98%
   （里程碑正式包条件，见 `docs/WORKFLOW.md` §7）。

> 固定阈值披露模式：content/missing/frame 若沿用「观测值=阈值」，必须在 gate-report 与
> KNOWN-DEBTS 同时写明「零余量」；里程碑仍应追求 0 或 owner 明确同意的数值。

## 3. 当前三版对比（2026-11-13）

| 指标 | v2.5.8 | v2.6.1 | v2.6.2 |
|---|---|---|---|
| 字形数 | 17007 | 17007 | 17005 |
| 基本区覆盖/20,992 | 10269 | 10269 | 10267 |
| 目标表覆盖/16,567 | 10269 | 10269 | 10267 |
| 缺口 | 6298 | 6298 | 6300 |
| font_qa | PASS | FAIL | PASS |
| 字形级框线 | 19 | 23 | 0 |
| 内容 damaged（vs v2.5.8） | 0 | 35 | 18 |
| 缺件扫描 | None | 1200 | 165 |
| 框线逃逸 | None | 153 | 0 |
| 页几何 bad_boxes | None | None | 0 |
| 空指派半版 | None | None | 1173 |
| fast_gate | None | None | PASS |
| 相对上一版变化字 | None | None | 617 |

## 4. 使用

```bash
.venv/bin/python scripts/release_metrics.py --out work/lead/release-metrics.json
# 输出 work/lead/release-metrics.json + work/lead/release-metrics.md
```

版本清单在 `scripts/release_metrics.py::VERSIONS` 维护；新增版本时追加一行（font/manifest/gate-report）。
