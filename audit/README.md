# audit/ —— 现行审计与流程文档（历史审计已归档到 `_history/`）

## 现行文件（每轮/每次发布应读）
| 文件 | 内容 |
|---|---|
| `SELF-AUDIT-2026-11-12.md` | 自审计与流程重梳理（流程错误、路由、门禁分层、清理计划） |
| `ROOT-CAUSE-FRAME-LOOP.md` | 框线问题反复回归的根因分析（三套真源） |
| `FRAME-ESCAPE-APPROACH-CORRECTION.md` | 框线修复方法纠正：切前排除 vs 切后擦除 |
| `RELEASE-CLEANUP-PLAN.md` | release/ 版本梳理与清理记录（已执行：2.6GB→175MB） |
| `RELEASE-HISTORY.jsonl` | 52 个历史版本的元数据留档（删除前导出） |
| `release-evidence/` | 4 个曾通过闸历史版本的 gate-report 与 SHA256SUMS |

## 历史归档（不改写）
- `_history/`：所有 AUDIT-REPORT / AUDIT-RESPONSE / AUDIT-REBUTTAL / AUDIT-SELF-v* / 核验台账 / 旧计划等（50 个文件），
  索引见 `_history/README.md`。

## 流程约定（自 2026-11-12 起）
1. 新审计/复核结论只写进 **现行文件**（`SELF-AUDIT`、`ROOT-CAUSE`、`FRAME-ESCAPE-*`）或每轮 `work/review/round-*/`；
2. 历史审计材料只归档、不改写；确需更新时在文件顶部加「记录状态」并在 `_history/README.md` 说明；
3. 发布包需要审计材料时从 `audit/` 复制（不移动），文件名保持一致；
4. 发布前只需核对 `RELEASE-CLEANUP-PLAN.md` 与 `RELEASE-HISTORY.jsonl` 的版本状态。
