# docs/ 文档地图（2026-11-14）

> 先看这一页，再按「必读顺序」读。**docs/ 里 90% 的文件不需要使用者看**：
> 用户只需要根 `README.md`；接手/审计者看下面「必读 5 个」；其余按需查。

## 一、用户该看哪几个（按角色）

| 角色 | 只看这些 |
|---|---|
| 使用者（安装/使用字体） | 根 `../README.md` |
| 新接手的开发者（30 分钟） | `README.md`（本页）→ `ARCHITECTURE.md` → `METHOD.md` → `PROJECT-STATE.md` → `PIPELINE.md` |
| 发布/发版 | + `WORKFLOW.md` → `reference/RELEASE-METRICS.md` → `releases/v<ver>/` |
| 审计 | + `reference/WORK-MAP.md`、`reference/SCRIPTS.md`、`BACKLOG.md`、`VERSION-HISTORY.md`、`ERRATA.md` |

## 二、文档地图（分层：必读 / 权威 / 工作 / 参考 / 发布 / 历史）

### A. 必读入口（5）

| 文件 | 定位 |
|---|---|
| `ARCHITECTURE.md` | 项目架构、文件夹层级、依赖方向、新增文件放哪 |
| `METHOD.md` | 技术路线（可读版，给非开发者） |
| `PROJECT-STATE.md` | 30 秒现状、已知缺陷、下一步、独立审计命令 |
| `PIPELINE.md` | 管线唯一权威（参数/命令/失败模式） |
| `WORKFLOW.md` | 流程纪律（候选/正式、闸、里程碑、复核） |

### B. 权威口径（不能随意改；只增/只更正）

| 文件 | 定位 | 修改规则 |
|---|---|---|
| `DECISIONS.md` | 口径决策（D1–D23+更正注记） | 新决策追加；旧决策不删除，更正用注记 |
| `GLOSSARY.md` | 术语（冲突时以它为准） | 追加/勘误 |
| `DATA.md` | 数据来源/许可/校验和/复现链 | 只更正事实，不覆盖历史 |
| `PIPELINE.md` | 同上（管线权威） | 变更需同步 VERSION-HISTORY + changeset |
| `WORKFLOW.md` | 流程权威 | 同上 |

### C. 工作/编年（可追加，不可回写历史数字）

| 文件 | 定位 |
|---|---|
| `BACKLOG.md` | 唯一待办清单（P0/P1/P2/ACCEPT） |
| `VERSION-HISTORY.md` | 逐版变更（append-only） |
| `ERRATA.md` | 历史错误/作废数字/考古避坑（append-only） |
| `reference/EXPERIMENTS.md` | 实验与探索索引（E1–E37、changesets、失败实验） |

### D. 参考手册（查阅型，平时不用读）

| 文件 | 定位 |
|---|---|
| `reference/SCRIPTS.md` | 脚本四层分类（管线/oneoff/provenance/archive）与旧方法评估 |
| `reference/WORK-MAP.md` | `work/` 痕迹地图与安全清理规则 |
| `reference/WORK-CLEANUP.md` | 清理分类/已执行记录/影响评估（含原 IMPACT 附录） |
| `reference/RELEASE-METRICS.md` | 版本对比指标与「一版比上一版好」判据 |
| `reference/CANONICAL-ORDER.md` · `reference/STRUCTURE.md` · `reference/HEADERS.md` | 正典序/卷部结构/书眉数据层 |

### E. 发布记录（每版一个子目录，发布后只读）

| 路径 | 定位 |
|---|---|
| `releases/README.md` | 发布记录索引 |
| `releases/v<ver>/` 下：`RELEASE.md` · `KNOWN-DEBTS.md` · `SELF-AUDIT.md` | 该版发布说明/已知债/发布前自审计 |

### F. 计划（滚动，随版本移动）

| 文件 | 定位 |
|---|---|
| `plans/PLAN-v2.6.3.md` | 2.6 补丁线滚动计划（做不完顺延 v2.6.4…） |
| `plans/PLAN-v2.7.0.md` | v2.7.0（GAN + 带状扫掠生成回退） |

### G. 历史（不改写，仅供考古）

| 路径 | 内容 |
|---|---|
| `_history/` | 旧文档（含 `_history/PROJECT-AUDIT-2026-11-12.md`、TAKEOVER、旧计划/发布计划等） |
| `../audit/_history/` | 历史审计证据 |

## 三、哪些不能动 / 合并删除 / 归档（2026-11-14 决策）

| 类别 | 处理 |
|---|---|
| **不能动** | `PIPELINE.md`/`WORKFLOW.md`/`DECISIONS.md`/`GLOSSARY.md`/`DATA.md`（权威口径）；`VERSION-HISTORY.md`/`ERRATA.md`（append-only）；`releases/v<ver>/`（发布后只读）；`_history/`（不改写）；已 finalize 的 `release/` 包 |
| **已合并后删除** | 原 `WORK-CLEANUP-IMPACT.md` → 并入 `reference/WORK-CLEANUP.md` 附录后已删除 |
| **已移出 docs** | 原 `README-TEMPLATE.md` → `scripts/templates/README-TEMPLATE.md`（打包资产，不是文档） |
| **已归档** | `PROJECT-AUDIT-2026-11-12.md` → `_history/`；`KNOWN-DEBTS/SELF-AUDIT` 按版本移入 `releases/v2.6.2/` |
| **保留但归入 reference** | SCRIPTS/WORK-MAP/WORK-CLEANUP/RELEASE-METRICS/EXPERIMENTS/数据层三篇 |

## 四、新增文档放哪

- 现行文档 → `docs/` 根，并更新本页地图；
- 查阅/工具型 → `docs/reference/`；
- 计划 → `docs/plans/`；
- 正式版材料 → `docs/releases/v<ver>/`；
- 过期/被取代 → `docs/_history/`（顶部加「历史」横幅，不改写原文）。
