# 自审计报告（v2.5.7：门禁加固 + 归档修复）  [2026-11-12 07:10]

## 变更（字形数据不变）
1. content_loss_gate：damaged>0 → exit 3；release_gate 双判（退出码 + JSON）；
2. release_gate：`--scan` 独立缺件扫描步骤、`--quarantine` 传参、删死参数；
3. check_release_docs 白名单收紧；font_norm 破坏性开关默认 False + raise 守卫（D20）；
4. 归档断链修复（t1_count_v3 恢复共享库，49/49 import 通过）；
5. make_repair_overlay.py 入库（overlay sha 可复算 = 48c611ab…）；
6. 隔离清单补 仟/禦/絞（9 字）；SCRIPTS.md 三处校准 + §8bis 口径说明。

## 验证
| 项 | 结果 |
|---|---|
| 内容闸牙齿 | v2.4.19 vs v2.4.15 实测 damaged>0 → exit 3 |
| overlay 可复算 | 重生成 sha256 与记录一致（1,602 字） |
| 现行脚本 import | 49/49 通过 |
| QA / 内容闸 / 字符集 diff | PASS / 0 / 0 |
| release_gate | 全绿（含 --scan） |
| 版本盖章 | Version 2.5.7 / fontRevision 2.57 |

## 挂账
mapping 生成脚本化、overlay 溯源字段、scan_missing_parts fail-open、detect_blocks docstring、
snap_box μ 项、审计台账、repair 校验落盘。
