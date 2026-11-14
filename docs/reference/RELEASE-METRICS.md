# RELEASE-METRICS · 版本对比指标与「一版比上一版好」的判据

> 用途：发版（候选/正式）时用**同一套可复算指标**回答「v2.6.3 比 v2.6.2、v2.6.1、v2.5.8 好在哪」，
> 而不是靠印象或单张样张。指标由 `scripts/release_metrics.py` 生成，落盘
> `work/lead/release-metrics.json` + `work/lead/release-metrics.md`，正式包内随包提供。

## 1. 指标定义（全部可复算）

| 组 | 指标 | v2.5.8 | v2.6.1 | v2.6.2 | v2.6.3 |
|---|---|---|---|---|---|
| 字形数 | 17007 | 17007 | 17005 | **17006** |
| 基本区覆盖/20,992 | 10269 | 10269 | 10267 | **10268** |
| 目标表覆盖/16,567 | 10269 | 10269 | 10267 | **10268** |
| 缺口 | 6298 | 6298 | 6300 | **6299** |
| font_qa | PASS | FAIL | PASS | **PASS** |
| 字形级框线 | 19 | 23 | 0 | **0** |
| 内容 damaged（基线） | 0（自身） | 35（vs v2.5.8） | 18（vs v2.5.8） | **0（vs v2.6.2）** |
| 内容 damaged（累计 vs v2.5.8） | — | — | — | **18（披露）** |
| 缺件扫描 | — | 1200 | 165 | **19 字/20 组件** |
| 框线逃逸 | — | 153 | 0 | **0** |
| 页几何 bad_boxes | — | — | 0 | **0** |
| 空指派半版 | — | — | 1173 | **1172** |
| fast_gate | — | — | PASS | **PASS** |
| 相对上一版变化字 | — | — | 617（旧阈值筛集）/ **3,351**（精确轮廓） | **7 = changed 6（急愈架紉釘+而；而属 r1 修）+ added 1（釕）+ removed 0** |

> 注 1（2026-11-14，E39）：v2.6.2 的「617」来自旧候选 b73e9f01 的阈值筛选 diff，对发布字体**不可复算**；
> 精确 glyf 轮廓差异为 **3,351**（audit4 DATA-401 + Lead 独立复算）。v2.6.3 起该指标由精确轮廓 diff 脚本
> （`scripts/glyph_diff.py`）生成，禁止再用阈值筛集口径。
>
> 注 2（2026-11-14，owner 决定）：v2.6.3 起 patch 线**内容闸基线 = 上一正式版**（v2.6.3 对 v2.6.2 = 0；
> 累计 vs v2.5.8 = 18 单独列披露）。缺件口径以 E40 为准（旧 165 已作废，按现行扫描 19/20 披露）。

## 4. 使用

```bash
.venv/bin/python scripts/release_metrics.py --out work/lead/release-metrics.json --md-out work/lead/release-metrics.md
# 输出 work/lead/release-metrics.json + work/lead/release-metrics.md
```

版本清单在 `scripts/release_metrics.py::VERSIONS` 维护；新增版本时追加一行（font/manifest/gate-report）；
若该版内容基线不是 v2.5.8，需在 VERSIONS 行加 `content_baseline`（v2.6.3 起）。
