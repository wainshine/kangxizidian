# scripts/provenance/ · 数据 provenance（保留不跑）

> 这些脚本是 mapping / 字表 / 部界 / 正典序的**历史求解链与数据 provenance**：
> 结果已经固化到 `work/lead/mapping_block_v271.jsonl`、`work/seq/canonical.jsonl` 等真源，
> **不参与 v2.6.2 构建**（顶层脚本不 import 本目录），保留用于审计追溯与「旧方法是否更优」的复查。

## 内容（24）

- 映射求解：`lead_solver` · `lead_solver2` · `lead_extract` · `lead_strict_headwords`（headword-only 原则）·
  `lead_finalize_union11` · `lead_validate_map` · `lead_mapping_check` · `lead_selfcheck_map` · `lead_run_detect` ·
  `lead_char_align14` · `lead_t1v2_frozen` · `t1_v2` · `t1_v3` · `t1_count_v3`
- VLM/指纹：`lead_vlm_fp_full` · `lead_vlm_confirm`
- 部界/书眉/结构：`lead_bu_dp2` · `lead_bu_dp3` · `header_read` · `structure_read` · `volume_structure` · `radical_templates`
- 正典序/分桶：`seq_order` · `lead_gan_targets`

## 规则

- 本目录脚本多数仍会 `sys.path` 找 `scripts/` 顶层的库（已修正为 repo 根 + `scripts/`），但**不保证与现行 API 同步**；
- 不是「死代码」：它们是数据真源的生成证据；不得删除（除非 owner 明确批准并留档）；
- 新的一次性脚本放 `scripts/oneoff/`，不要加到本目录（provenance 只收已固化数据的求解链）。
