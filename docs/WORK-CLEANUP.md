# WORK-CLEANUP · `work/` 痕迹分类与清理方案 v2（2026-11-12 修订）

> owner 原则（v2 修订）：
> **JSON / JSONL 是各方法的核心成果 → 一律保留**（mapping 实验、检测框、OCR 结果、缺陷台账、闸报告……）；
> **只删过程物**：图片、pkl/npz/npy 数组、纯缓存（字形缓存/工具缓存）、临时稿、已被取代的旧台账图；旧 TTF 只留 3 个里程碑。
>
> 结果：需删 **61 项 / 24.90 GB**（不含 models）；保留全部 JSON 结果，`work/` 从 43G → 约 18.1G（其中 models 13.8G、15 个对比字体约 0.7G，真正证据约 3.6G）。

---

## 〇、已执行（2026-11-12 19:10）

- 执行：`scripts/cleanup_work.py --apply`（A+B，不含 models；补删旧字形缓存一次）；
- **work/ 43G → 19G**；删除 **61 项 / 24.90GB**（其中旧字形缓存 322,935 文件/17.97GB）；
- 保留全部 JSON/JSONL 成果（map 2.7G、lead 702M、detect2 30M、seq 29M、t2 14M）；
- 保留 15 个跨代代表字体；models 13G 未动；
- 删后验证：缓存命中重建 **sha=c73c3023…（与发布字体一致）**、fast_gate **7/7 PASS**、C 类 15 项 **0 缺失/0 sha 异常**；
- 留档：`work/lead/work-artifacts-inventory.jsonl`、`work/lead/map-lineage-notes/`、`work/lead/cleanup-log-2026-11-12*.txt`。

## 一、判定框架（v2）

| 判定 | 含义 | 处理 |
|---|---|---|
| **A 删（过程物/死路线）** | 图片渲染缓存、工具缓存、临时稿 | 删 |
| **B 删（过程物/可重建）** | 字形缓存、旧字体、图片、数组、被取代台账图 | 删过程物；**JSON 结果全部保留** |
| **C 留** | 现行依赖 + 全部方法 JSON 成果 | 保留（C 类永不删） |

---

## 二、A 类：过程物/死路线（3.66GB）

| 项 | 大小 | 说明 |
|---|---|---|
| `work/t00/**/*(图片)` | **875M** | T0 页面渲染 PNG 缓存；t00 的 JSON 元数据保留；重渲染约 2–5 分钟 |
| `work/detect2/**/*(图片)` | **518M** | 检测器 montage/模板图；**检测框 JSON 全部保留** |
| `work/paddlex_cache` | **723M** | PaddleOCR 缓存（工具缓存） |
| `work/uvcache` | **690M** | uv 包缓存（工具缓存） |
| `work/font/build/cache_old_v11` | **708M** | v1.1 旧格式字形缓存（纯过程缓存） |
| `work/font/tmp`、`sheets`、`release-rehearsal` | **~141M** | 临时稿/演练图 |

## 三、B 类：过程物/可重建（21.64GB）

| 项 | 大小 | 说明 |
|---|---|---|
| `work/font/build/cache` 非 v350 旧 tag | **17.97G / 322,935 文件** | 各代字形缓存（纯过程缓存）；v350 保留 |
| `work/seq/**/*(图片+数组)` | **877M** | seq 的 pkl/npz/图片；**JSON/JSONL 全部保留**（canonical、headers、bu_*.jsonl 等） |
| `work/lead/**/*(图片+数组)` | **659M** | lead 的图片/数组（glyphs_verify、hdr npz 等）；**OCR/检测/台账 JSON 全部保留** |
| `work/t2/**/*(图片+数组)` | **424M** | T2 的 png/pkl；**JSON 全部保留**（含 pdf_map.json） |
| `work/font/build/*.ttf` 旧字体 48 个 | **1.2G** | **保留 15 个跨代代表字体**（v0.3/v0.9/v1.2/v2.3.2/v2.4.0/16/19/22/v2.5.0/6/7/8/v2.5.9/v2.6.0/v2.6.1）供后续对比；其余删除，sha 已留档 |
| `work/review/defect-history-v258` | **79M** | 已被 v260 台账取代（台账 JSON 在 work/lead/defect-ledger-v258.jsonl，保留） |

**保留的 JSON 示例**：`work/map/` 全部实验目录的 `mapping.jsonl/report.json`（约 2.88G，mapping 推导核心成果）、`work/detect2/boxes*`（检测框）、`work/lead/ocr_*.jsonl/hdr_*.json`（OCR/书眉结果）、`vlm_fp_full/boxes300`、各版扫描/修复/闸日志。

## 四、C 类：现行依赖（永不删）

`page_geometry.jsonl`、`mapping_verified_all33.jsonl`、`mapping_block_v270.jsonl`、`repair_overlay_v256.jsonl`、
`manifest_v261.json`、`release_extras`、`_pylibs`、v2.5.8/v2.6.0/v2.6.1 字体、`work/gates/`、`cache/v350_*`、
`canonical.jsonl`、`volume_radicals.json`、`pdf_map.json`、`defect-history-v260`、`round-001`、`owner` 核验表。

## 五、models（13.8G，单列）

`qianfan-ocr`(9.5G) + `qwen3vl2b`(4.3G)：模型权重（非 JSON 结果），重下成本高；**默认保留**，需要释放空间时再迁外置盘或显式 `--include-models` 删除。

## 六、汇总

| 项 | 数值 |
|---|---|
| 待删（A+B，不含 models） | **24.90 GB / 61 项** |
| 保留 | 全部 JSON 成果 + C 类依赖 + v350 缓存 + 3 个里程碑字体 |
| 删后 work 体积 | 约 **18.1G**（含 models 13.8G；不含 models 约 4.3G，含保留的 15 个字体） |

## 七、执行

```bash
# dry-run（已跑：73 项 / 25.29GB；同时写 inventory + lineage 笔记）
python scripts/cleanup_work.py --dry-run

# 确认后执行（A+B，不含 models）
python scripts/cleanup_work.py --apply

# 若要连 models 一起删（需明确同意）
python scripts/cleanup_work.py --apply --include-models
```

删前留档：`work/lead/work-artifacts-inventory.jsonl`（路径/大小/原因 + C 类 sha256）、`work/lead/map-lineage-notes/`。
删后验证：缓存命中重建 sha 应仍为 `c73c3023…`；fast_gate PASS；C 类 sha 校验（见 `docs/WORK-CLEANUP-IMPACT.md` §5）。
