# 对两份审计意见的回应（基于 v2.4.20 处置）  [2026-11-11 15:55]

## 接受并已处置

### P0-1 内容缺损（931+ 字）
**审计正确，我方严重失误**。v2.4.16 引入 2×2 格块切分后，`strip_edge_small_comps` 把字身断开部件当外带注文删除；
v2.4.17/18/19 的「修删多了」只调窗口，**从未回头对存量做全量对账**，导致 1,132 字掉墨（实测）。
处置：
1. 回滚字形基线到 v2.4.15（本版 v2.4.20）；
2. 新增内容缺失闸 `scripts/content_loss_gate.py`，发布前必跑；
3. 复验：v2.4.20 vs v2.4.15 **掉墨 20%+ = 0**；
4. 2×2 重切方案撤回，后续必须在双闸下重做。

### P0-2 构建不可复原 / label_source 被覆盖
接受。v2.4.16–19 为会话内联命令生成、无脚本入库 → 不可复核。
处置：`scripts/build_release.py` 固化全序并输出 build_recipe（含输入/SHA）；本版 manifest 恢复 v2.4.15 通道标签
（vlm_fp_A/B、charalign9 等分布见 PROVENANCE.md），`cell2x2_block` 覆盖问题撤销。

### P1-3/P1-4 随包文档失真
接受。本版 README 数字由包内 JSON 渲染填入；PROVENANCE/QA 重写为 v2.4.20 且与代码阈值一致；
仅引用实际打包文件（不再引用不存在的 gan-targets 等）。

### P1-5 字节不可复现
接受。`postscale_glyphs.py`/`refgate_clean.py`/`repair_apply*.py` 全部改为 `recalcTimestamp=False`。

### P1-6 REF_FONT 硬编码
接受。改为 `REF_FONT_PATH` 环境变量覆盖，缺失时 **RuntimeError fail-fast**（不静默降级）。

## 部分接受 / 待办
- P2 `strip_edge_fragments` 判据与文档出入、无累计删除安全阀：该函数随 2×4 方案一并**撤回**（本版不使用）；
- 审计台账、docs/README 跨时代混用：正在按 v2.4.20 统一校订（本轮先更新 README 发布行与 RELEASE-PLAN §1）；
- 100 字签核 / 09–11/13 卷锚点：仍为人工金标缺口，承认未完成。
