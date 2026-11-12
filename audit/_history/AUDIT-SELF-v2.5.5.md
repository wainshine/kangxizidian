# 自审计报告（v2.5.5：版本盖章 + 发布文档机器校验）  [2026-11-12 00:10]

## 变更
1. `scripts/stamp_version.py`：字体内部版本盖章（name ID5 / head.fontRevision），v2.5.5 实测 `Version 2.5.5` / 2.55；
2. `scripts/check_release_docs.py`：README/PROVENANCE/QA 数字与文件引用机器校验（发布前必跑）；
3. `content_loss_gate.py`：覆盖率下限（<98% → exit 2），杜绝静默跳过假阴性；
4. `repair_offset.py`：内置逐字校验（墨量≥0.95 / IoU≥0.75，自动回退）；
5. QA.md / PROVENANCE.md / README 按 v2.5.5 实测重写（17,007 等）；恢复精度敞口披露。

## 验证
| 项 | 结果 |
|---|---|
| 字体内部版本 | Version 2.5.5 / fontRevision 2.55（stamp_version 实测） |
| QA | PASS（render_bad=0 / tiny=0 / rev_ok=True） |
| 内容缺失闸 vs v2.5.4 | 0（17,007 全检，覆盖 100%） |
| 发布文档校验 | check_release_docs PASS |

## 未修（已知债，明确记录）
1. 修复未回写 mapping/cache（全量重建会回滚 1,109+347 修复）——下一版回写；
2. v2.5.0–2.5.4 无 build_recipe（v2.5.5 起随包）；
3. D19 缺口分桶清单仍未随包；
4. 审计台账（AUDIT-VERIFICATION-LOG）仍滞后；
5. `strip_border_lines` 仍在链上（「无损清理链」措辞不准确，已在 QA 文档改为事实描述）。
