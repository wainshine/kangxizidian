# EXPERIMENTS · 实验与探索索引

> 本文是**索引**，不是正文。每次探索/失败/回退的完整记录在：
> `docs/ERRATA.md`（E1–E37，含作废数字与结论）、`work/changesets/`（变更集 JSON，含 before/after 与证据路径）、
> `docs/VERSION-HISTORY.md`（逐版摘要）、`work/lead/`（闸报告/扫描/诊断数据）。
> 目的：像馆阁体项目的 `docs/reference/EXPERIMENTS.md` 一样，能快速回答「这条路试过没有、结论是什么、证据在哪」。

## 1. 实验编号索引（E 系列）

| 编号 | 主题 | 结论 | 证据 |
|---|---|---|---|
| E1–E21 | 早期切分/检测/OCR/对齐/映射探索（v0.3–v2.5） | 多数被结构对齐/2×2 格块路线取代；历史结论文档见 `audit/_history/` 与 `docs/_history/` | `docs/_history/`、`audit/_history/` |
| E21 | 内部 pad 实验 | 掉墨，回退 | `docs/ERRATA.md` E21 |
| E22 | 构建耗时实测更正 | 全量 402s / 缓存命中 232s | `docs/ERRATA.md` E22 |
| E23 | 同块冲突 2 对（沓/忠） | 清除并写 residual | `scripts/oneoff/fix_mapping_sameblock.py`、`work/lead/sameblock-fix-report.json` |
| E24 | 页级 pre-cut 直线 mask（CS2 v1） | 字形框线 23→14 | `docs/ERRATA.md` E24 |
| E25 | verified-box keep（单字 ROI） | 内容回归（去/蘇/緅），**回退** | `docs/ERRATA.md` E25 |
| E26 | thick-ink ROI（距离场） | 961 字受损，**回退** | `docs/ERRATA.md` E26 |
| E27 | 页级已验证线条带 | 清最后 14 处；14→26 rect | `work/lead/page_line_bands.json` |
| E29 | strip_border_lines 摘除（D22） | 字形框线仍 0；线条带扩到 26 rect | `docs/ERRATA.md` E29 |
| E30 | quad 扩张（BF-03） | bad_boxes 198→0、内容 34→32 | `scripts/oneoff/expand_quads_to_cover_boxes.py`、`work/lead/quad-expand-report.json` |
| E31 | 内容闸跨架构归因（D23 提案） | 大部分为归一化差异，非真实缺笔 | `work/lead/content-aspect-analysis-v262.json` |
| E32 | 扫描口径对齐（pre-cut） | 缺件 1,155→1,117、框线 158→43 | `docs/ERRATA.md` E32 |
| E33 | 极细线 pre-cut（ultra-thin pass） | 缺件 1,117→827、框线 43→1；但误删字身细笔画，E37 改为 crossing 过滤 | `docs/ERRATA.md` E33/E37 |
| E34 | 扫描耗时说明 | 全库扫描 20–25 分钟 | `docs/ERRATA.md` E34 |
| E35 | 缺件扫描配准错误 | 827 大多为假阳性；主成分配准 bug | `docs/ERRATA.md` E35 |
| E36 | 缺件扫描复刻构建墨迹链 | 827→32、interior=0；sidecar 绑 build_stats | `scripts/scan_missing_parts.py` |
| E37 | owner 复核 77 格修复（三类缺陷） | 边角料 49/过滤多 17/标签错 11；修前两类，候选 a8bb87d9 | `docs/ERRATA.md` E37、`work/lead/defect-diagnostics-v262.json`、`work/review/round-004-v262fix/` |

## 2. 变更集索引（`work/changesets/`）

| 变更集 | 内容 |
|---|---|
| `cs-20261112-auditfix` | 审计修复（三闸/绑定/构建硬化等） |
| `cs-20261112-cs1a` · `cs1b` · `cs1p5-sameblock` | CS1 构建链/同块修复 |
| `cs-20261112-refqa` | 参考字体统一（D21） |
| `cs-20261113-cs2-linemask` | 页级直线 mask（E24） |
| `cs-20261113-cs2-strip-ab` | strip 关闭 A/B（E29） |
| `cs-20261113-cs2-quad-expand` | quad 扩张（E30） |
| `cs-20261113-cs3-scan-precut-align` | 扫描口径对齐（E32） |
| `cs-20261113-cs3-ultra-thin` | 极细线 pre-cut（E33；后被 E37 修正） |
| `cs-20261113-cs3-missing-scan-e36` | 缺件扫描重写（E36） |
| `cs-20261113-cs4-review-feedback` | owner 复核反馈修复（E37） |

> 失败实验（E25/E26/E33 初版/E35）保留记录与证据文件，不删；结论已进 ERRATA，避免重复踩坑。

## 3. 看数字的正确入口

- 当前候选/正式包：`work/lead/gate-report-v262.json`、`fast-gate-v262.json`；
- 缺件/框线/内容：`work/lead/missing_scan_v262.jsonl` / `frame_scan_v262.jsonl` / `content-loss-v258-v262.json`；
- 版本对比：`docs/reference/RELEASE-METRICS.md` + `work/lead/release-metrics.json`；
- 每个数字的可复算命令：`docs/PROJECT-STATE.md` §5。
