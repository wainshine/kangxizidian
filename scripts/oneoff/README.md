# scripts/oneoff/ · 一次性脚本

> 从 2026-11-14（v2.6.2 发布后）起：**所有一次性脚本一律放这里，不再混入 `scripts/` 顶层，
> 也不再用完就丢进 `_archive/`**。顶层 `scripts/` 只保留现行管线（主进程，28 个文件）。

## 目录内分类

| 分组 | 脚本 | 状态 |
|---|---|---|
| A. 当前真源生成（可复算，跑完即固化） | `expand_quads_to_cover_boxes`（E30 quad 扩张）· `fix_mapping_sameblock`（同块 2 对，E23）· `rebuild_mapping_boxes` · `add_verified_boxes` · `apply_frame_fix` | 属于当前 mapping/geometry 真源的生成链，保留可复跑 |
| B. 旧修复/诊断链（已被取代） | `refgate refgate2 refgate2_scan refgate_clean scan_aspect scan_distort scan_offset repair_missing_chars repair_all_missing repair_offset repair_frame_escape` | 被 `scan_missing_parts` + 内容/缺件闸取代；保留供审计与 ERRATA 追溯 |
| C. 旧复核/出图 | `owner_review_sheet owner_review_color owner_defect_sheet regenerate_sheets page_artifacts` | 被 `review_sheet + make_round_pack` 取代 |
| D. 历史配方/实验/维护 | `build_release`（旧构建配方）· `probe_strip_border`（E29 前实验）· `make_repair_overlay`（**禁止使用**，BF-43）· `cleanup_releases` · `cleanup_work` | 只作历史/维护，不参与构建 |

## 规则

1. 新增的一次性脚本（数据修复、体检、实验、迁移）直接放本目录，**不要再放 `scripts/` 顶层**；
2. 仍在现行发布流程里被调用的工具（`make_release_extras`、`release_metrics`、`make_readme_images`、
   `review_sheet`、`make_round_pack`）属于管线，留在顶层；
3. 本目录脚本从上级目录 import 时已修好路径（`ROOT` 取 repo 根，`sys.path` 加 `scripts/`），可独立运行：
   `PYTHONPATH= ... .venv/bin/python scripts/oneoff/<name>.py --help`；
4. `_archive/` 只接收「v2.6.2 之前冻结的历史」，不再作为日常归档目录。
