# 自审计报告（v2.5.8：发布证据链 + 文档一致性）  [2026-11-12 08:20]

## 变更
1. release_gate：finalize（报告冻结→SHA 覆盖含报告→zip 重建自检）、--quarantine 接通并合并全部隔离清单、
   char_diff 缺基线 FAIL、扫描严格/阈值两档；
2. check_release_docs：pct/gap 强校验、扫 RELEASE-NOTES、首跑模式（--allow-missing-attestation）；
3. font_norm：vectorize_gray 默认关闭；font_build：版权串去 demo v0；font_package：死路径注记修正；
4. 高频字缺口表（285 繁体常用字缺 23）随包并首页披露；
5. 文档/版本/隔离清单统一到 v2.5.8；审计文件与开发文档移出发布包（D17 §4）。

## 验证
| 项 | 结果 |
|---|---|
| 内容缺失 vs v2.5.7 | 0（17,007 全检） |
| 字符集差集 | removed=0；隔离清单合并 9 字 |
| 缺件扫描 | flagged=587（阈值 700，披露为已知债） |
| gate-report 计入 SHA | 是（finalize 冻结后） |
| zip | finalize 重建 + 自检 PASS |
| 版本盖章 | Version 2.5.8 / 2.58；nameID0 无 demo v0 |

## 挂账
mapping 从零可复算、overlay 溯源字段、scan_missing_parts fail-open、snap_box μ 项、
100 字签核、09–11/13 卷锚点、残余碎片、D19 清单。
