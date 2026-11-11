# 自审计报告（v2.5.6：修复回写 + release_gate）  [2026-11-12 00:30]

## 变更
1. `repair_overlay-v256.jsonl`：1,602 个修复字的原始轮廓点（sha256 48c611ab…）；
2. `font_build --repair-overlay` + build_recipe 记录；
3. `scripts/release_gate.py`：QA/版本盖章/字符集 diff/内容闸/文档/SHA/zip 全链；
4. 字符集差集门禁（removed 必须出现在隔离清单）。

## 验证
| 项 | 结果 |
|---|---|
| 轮廓重建一致性 | glyf 级差异 0 / 17,007 字 |
| 内容缺失 vs v2.5.5 | 0 |
| 字符集 diff | removed 0，added 0 |
| 字体内部版本 | Version 2.5.6 / 2.56 |
| QA | PASS |
| 冻结 | SHA 全过 + zip PASS |

## 已知债（不变）
D19 清单、审计台账回填、主成分归一化、09–11/13 卷锚点、100 字签核、残余碎片/框线。
