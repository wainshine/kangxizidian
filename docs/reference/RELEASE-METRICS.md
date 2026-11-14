# RELEASE-METRICS · 版本对比指标与「一版比上一版好」的判据

> 用途：发版（候选/正式）时用**同一套可复算指标**回答「v2.6.2 比 v2.6.1、v2.5.8 好在哪」，
> 而不是靠印象或单张样张。指标由 `scripts/release_metrics.py` 生成，落盘
> `work/lead/release-metrics.json` + `work/lead/release-metrics.md`，正式包内随包提供。

## 1. 指标定义（全部可复算）

| 组 | 指标 | v2.5.8 | v2.6.1 | v2.6.2 |
|---|---|---|---|
| 字形数 | 17007 | 17007 | 17005 |
| 基本区覆盖/20,992 | 10269 | 10269 | 10267 |
| 目标表覆盖/16,567 | 10269 | 10269 | 10267 |
| 缺口 | 6298 | 6298 | 6300 |
| font_qa | PASS | FAIL | PASS |
| 字形级框线 | 19 | 23 | 0 |
| 内容 damaged（vs v2.5.8） | 0 | 35 | 18 |
| 缺件扫描 | — | 1200 | 165 |
| 框线逃逸 | — | 153 | 0 |
| 页几何 bad_boxes | — | — | 0 |
| 空指派半版 | — | — | 1173 |
| fast_gate | — | — | PASS |
| 相对上一版变化字 | — | — | 617（旧阈值筛集）/ **3,351**（精确轮廓） |

> 注（2026-11-14，E39）：617 来自旧候选 b73e9f01 的阈值筛选 diff，对发布字体**不可复算**；
> 精确 glyf 轮廓差异为 **3,351**（audit4 DATA-401 + Lead 独立复算）。v2.6.3 起该指标必须由精确轮廓 diff 脚本生成。

## 4. 使用

```bash
.venv/bin/python scripts/release_metrics.py --out work/lead/release-metrics.json
# 输出 work/lead/release-metrics.json + work/lead/release-metrics.md
```

版本清单在 `scripts/release_metrics.py::VERSIONS` 维护；新增版本时追加一行（font/manifest/gate-report）。
