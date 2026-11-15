# 正式版发布记录（releases/）

> 每个正式包一个子目录 `docs/releases/v<ver>/`，内含：
> `RELEASE.md`（版本/日期/字体与 zip sha/覆盖/闸况/已知债/复验命令）、`KNOWN-DEBTS.md`（该版已知债披露）、
> `SELF-AUDIT.md`（发布前自审计记录）。逐版变更总表见 `../VERSION-HISTORY.md`；
> 发布流程见 `../WORKFLOW.md` §7–§8；包本体不进 git（`release/` gitignored）。

| 版本 | 日期 | 类型 | 字体 sha256 | 发布记录 |
|---|---|---|---|---|
| v2.6.4 | 2026-11-15 | 正式（字形修正 + 证据硬化） | `9740e7aa…` | [v2.6.4/RELEASE.md](v2.6.4/RELEASE.md) |
| v2.6.3 | 2026-11-14 | 正式（r1 返工重发） | `2414847b…` | [v2.6.3/RELEASE.md](v2.6.3/RELEASE.md) |
| v2.6.2 | 2026-11-14 | 正式（2.6 补丁线） | `a8bb87d9…` | [v2.6.2/RELEASE.md](v2.6.2/RELEASE.md) |

## 规则

- 只有正式包才建立版本子目录；候选/预览不建（证据留在 `work/`）；
- 发布后本目录只读：不改已发布版本的数字，勘误写 `../ERRATA.md`；
- 新版本复制 `v2.6.2/` 的骨架（RELEASE/KNOWN-DEBTS/SELF-AUDIT），填新数字。
