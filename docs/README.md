# docs/ 文档索引（2026-11-12 整理）

> 规则：**根目录只放现行文档**；历史/过期文档移入 `docs/_history/`（不改写，仅供考古）。
> 新会话入口是根目录 `AGENTS.md`，按它列出的顺序读。

## 一、现行文档（读这些）

| 顺序 | 文件 | 内容 |
|---|---|---|
| 1 | `../AGENTS.md` | 入口约束：先读什么、硬性规则、当前状态、最短验证 |
| 2 | `PROJECT-STATE.md` | 30 秒现状、已知缺陷、下一步、如何独立审计 |
| 3 | `PIPELINE.md` | 管线架构/原理/流程/参数/复现命令/失败模式（**唯一权威**） |
| 4 | `WORKFLOW.md` | 流程纪律：候选/正式、变更集、闸分层、里程碑发版、7 张复核图 |
| 5 | `VERSION-HISTORY.md` | 逐版变更（v0.3→v2.6.1）+ 探索/修补分类 |
| 6 | `WORK-MAP.md` | `work/` 痕迹地图与安全清理规则 |
| 7 | `WORK-CLEANUP.md` / `WORK-CLEANUP-IMPACT.md` | 清理分类、已执行记录、影响评估 |
| 8 | `DECISIONS.md` | 口径决策（唯一权威，D1–D18+更正注记） |
| 9 | `GLOSSARY.md` | 术语（冲突时以它为准） |
| 10 | `ERRATA.md` | 历史错误/作废数字/已知误导（考古避坑） |
| 11 | `DATA.md` | 数据来源/许可/校验和/复现链 |
| 12 | `SCRIPTS.md` | 脚本清单与旧方法评估（含归档说明） |
| 13 | `CANONICAL-ORDER.md` | 正典序/字表数据层 |
| 14 | `STRUCTURE.md` | 卷/部/PDF 分节结构 |
| 15 | `HEADERS.md` | 书眉数据层（版心读数） |


审计：`../audit/README.md`（现行结论），`../audit/_history/`（历史审计存档）。

## 二、历史文档（`_history/`，不作现行依据）

| 文件 | 说明 |
|---|---|
| `COUNTS.md` | 逐节编年（1,095 行；VERSION-HISTORY 的章节来源） |
| `V3-STATUS.md` | v3 阶段编年 |
| `SESSION-HANDOFF.md` | 旧会话交接编年 |
| `TAKEOVER.md` | 2026-11-08 接手诊断（历史） |
| `PROBE.md` | T0 版面探测（历史；页码公式已作废） |
| `T2-EXP30.md` | T2 实验记录（历史） |
| `HEADWORD-COVERAGE.md` | 早期覆盖盘点（历史） |
| `OCR-OPTIONS.md` | OCR 调研与最终结论（历史） |
| `DETECTOR-V2.md` | 旧检测器设计（历史） |
| `FONT-BUILD.md` | demo 阶段构建链（历史；现行见 PIPELINE.md） |
| `VENDORED.md` | 第三方复制记录（历史） |
| `PLAN-v2.6.md` | v2.6 前的计划（历史） |
| `RELEASE-PLAN.md` | 旧发布计划（历史；现行见 WORKFLOW.md） |
| `PROMPT.md` | 馆阁体模板任务书原文（历史；现行需求见 DECISIONS） |

## 三、整理说明

- 本次整理把 14 个历史文档移入 `_history/`（根目录从 27 → 16 个文档 + 根 `AGENTS.md`），并批量修正了 20 个文件里的引用路径；
- 现行文档中已经包含必要的历史结论（VERSION-HISTORY 有逐版摘要、ERRATA 有作废说法），新会话**不需要读 _history**；
- 需要考古时再按需查阅，历史文档顶部均有「文档状态」横幅。
