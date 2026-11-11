# scripts/_archive · 历史/废弃脚本归档（2026-11-12）

按《SCRIPTS 清单》（`docs/SCRIPTS.md`）整理：这里存放**已完成使命或被替代**的一次性脚本，
保留原文以便审计追溯与「旧方法是否更优」的复查；**不参与现行管线**，也不保证可直接运行
（多数仍会 `sys.path.insert(0, "scripts")` 找同目录模块，移到此处后 import 会失效）。

现行管线（v2.5.6）只用 `scripts/` 下 48 个文件：
- 核心：`font_build · font_norm · font_qa · font_package · release_gate · check_release_docs · stamp_version · content_loss_gate`
- 诊断/修复链：`scan_missing_parts · scan_offset · scan_distort · scan_aspect · repair_missing_chars · repair_all_missing · repair_offset`
- 参考闸：`refgate · refgate2 · refgate2_scan · refgate_clean · fidelity_eval`
- 页级工具：`detect_blocks`（仅 page_gray/binarize/fit_axis；其「从零检测字头」主程序未启用）
- 发布/核验：`owner_review_sheet · owner_review_color · regenerate_sheets · build_release`
- 数据 provenance（保留不跑）：`seq_order · lead_solver* · lead_extract · lead_strict_headwords · header_read · lead_vlm_fp_full · lead_char_align14 · volume_structure · radical_templates · structure_read · lead_t1v2_frozen · t1_v2 · t1_v3 · lead_gan_targets`

归档目录内按族分组（见 `docs/SCRIPTS.md` §5–§7）：
`t00_/t0_/t1_/t2_`（早期检测/OCR/对齐实验）、`bu_/lead_*`（映射求解历史版本）、
`layout_* / grid_* / snap_box / block_cut / refine_boxes*`（切分实验）、`repair_apply* / missing_scan`（旧修复链）、
`lead_vlm_* / vlm_* / bench_ocr*`（VLM/OCR 实验）、`ref_filter_crop / class_eval / postscale_glyphs`（**待评估的更优方法**，见清单 §8）。
