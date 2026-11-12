# WORK-CLEANUP-IMPACT · 删 A+B 的影响评估与重建可行性（2026-11-12）

> **v2 修订（owner 原则）：JSON/JSONL = 方法核心成果，全部保留；只删图片/数组/纯缓存等过程物。**
> 因此下面的「map 中间实验不可复原」「detect2/OCR 结果丢失」等风险已大幅降低——这些 JSON 结果都保留。
>
> 结论先行：**删 A+B 对现行管线（v2.6.1 构建 / 快闸 / 全闸 / 打包 / 复核）零影响**——
> 现行依赖全部在 **C 类**，且删前会做完整性留档、删后会跑验证。
> 对历史复现的影响按「可重建 / 需重跑（有成本） / 不可逐字节复原」分级列在下表。

---

## 1. 总体影响分级

| 影响对象 | 删 A+B 后 |
|---|---|
| **现行构建**（font_build + cache v350） | 无影响（mapping/geometry/字体/依赖都在 C 类；v350 缓存保留） |
| **现行闸**（fast_gate / release_gate） | 无影响（基线字体 v2.5.8、现行扫描结果、manifest 都保留） |
| **打包/发布** | 无影响（release_extras、PDF、pdf_map、_pylibs 保留） |
| **人工复核** | 无影响（defect-history-v260、round-001、owner 核验表保留；v258 台账可由 ledger 重生成） |
| **历史版本逐字节复现** | 部分受影响：旧缓存/旧 TTF 删了，但 sha 已留档（RELEASE-HISTORY）；重建需旧 commit+旧 mapping，部分版本只能近似 |
| **mapping 推导过程** | **有残余风险**：最终 mapping33 与 lineage（charalign9/14、v3full）保留、生成脚本保留；中间实验目录删除后，无法逐字节复原「当时的候选集」，但可用脚本重跑（结果可能不同） |
| **OCR/检测/书眉路线** | 中间缓存删除；代码与模型（models 保留）仍在，可重跑，但成本较高（见 §3） |

---

## 2. A 类逐项影响与重建

| 项 | 删除后失去 | 何时需要 | 重建方式 | 成本 |
|---|---|---|---|---|
| `work/t00`（851M） | T1 检测器用的 150dpi 页面缓存（284 页 PNG） | 只有重跑旧 T1 检测路线时需要 | `t1_v2.py`/`lead_t1v2_frozen.py` 自带 PDF 渲染（`--page-dir` 可省略）；或先重渲染 284 页 | **约 2–5 分钟**（8 workers） |
| `work/detect2`（525M） | 检测器 v2 的 boxes150/300、templates、montage | 重跑旧检测时会再生成 | `lead_run_detect.py` / `t1_v2.py` 重跑全 12 卷 | **约 10–20 分钟**（8 workers） |
| `work/paddlex_cache`（690M） | PaddleOCR 模型缓存 | OCR 路线重跑时自动重下 | 重下（首次联网，视网速） | 分钟级 |
| `work/uvcache`（716M） | uv 包缓存 | 重装环境时 | `uv sync/pip install` 重下 | 分钟级 |
| `work/font/build/cache_old_v11`（708M） | v1.1 时代旧格式字形缓存 | 几乎不需要（v1.1 结果在 COUTS 记录） | 用 git 旧 commit + 旧 demo manifest 重跑（如有需要） | ~分钟 |
| `work/t2`（除 pdf_map，~418M） | T2 DP 对齐的 reading/probe/marked_backup 等 | 不会再用（路线作废） | 旧代码在 git（`scripts/lead_*`/`t2` 时代），数据可由扫描页重算 | 高（数小时）且**不建议** |
| `work/seq/*.pkl`（210M） | 部界锚点/书眉 pkl 中间件 | 只在重跑书眉读数/部界锚点路线时需要 | `scripts/lead_bu_*` 重算（依赖 models，models 保留） | 约小时级 |
| `work/font/tmp`、`sheets`、`release-rehearsal`（~140M） | 临时稿/演练图 | 不需要 | 重新生成 | 分钟级 |

---

## 3. B 类逐项影响与重建

| 项 | 删除后失去 | 何时需要 | 重建方式 | 成本/风险 |
|---|---|---|---|---|
| 旧字形缓存 **v248–v341**（17.97G/322,935 文件） | 各代算法的逐字缓存（纯过程物） | 仅做旧版本回归时需要 | 用对应 git commit + mapping 重跑；旧版结果已无现行用途 | 每代约 10 分钟；不能逐字节复原（缓存本身不是成果） |
| 旧 TTF（48 个/1.2G） | 部分版本成品 | 对比/考古 | 保留 15 个跨代代表字体（v0.3/v0.9/v1.2/v2.3.2/v2.4.0/16/19/22/v2.5.0/6/7/8/v2.5.9/v2.6.0/v2.6.1）；删除其余（sha 留档） | ✅ 可对比，风险低 |
| `work/map` 全部实验目录 | **不删**（JSON 核心成果，2.88G 全部保留） | — | — | ✅ 无影响；mapping 推导证据完整 |
| `work/lead` 图片/数组（~659M）；`work/seq` 图片/数组（877M）；`work/t2` 图片/数组（424M）；`detect2`/`t00` 图片 | 图片/数组过程物 | 复核时 | JSON 结果全部保留（检测框/OCR/书眉结果/对齐 JSON）；图片可重跑生成，数组可由代码重算 | ✅ 主要证据已保留；仅图像/数组需重生成（检测 10–20 分钟，OCR 小时级） |
| `work/review/defect-history-v258`（79M） | v2.5.8 缺陷台账图 | 需要旧台账时 | `owner_defect_sheet.py` + `defect-ledger-v258.jsonl`（**保留**）+ v2.5.8 字体 | **约 3 分钟，可重建** |

---

## 4. 删前保障（脚本会做）

1. **留档清单**：`work/lead/work-artifacts-inventory.jsonl`（每项路径/大小/原因；C 类另记 sha256）；
2. **lineage 笔记**：复制 `work/map/{v3full,charalign9,charalign14}/report.json` 等小文件到 `work/lead/map-lineage-notes/`（KB 级），并在其中记录「mapping33 由哪些脚本/目录推导」；
3. **C 类完整性**：列出 C 类路径与 sha256（page_geometry、mapping33、mapping_block、repair_overlay、字体、manifest 等），删除后逐一校验；
4. 默认 `--dry-run`；`--apply` 才删；`--include-models` 需单独显式给。

## 5. 删后验证（约 2–3 分钟，证明零影响）

```bash
# 1) 缓存命中重建（应 ~20s，17,007 字全部命中 v350）
FONT_BUILD_WORKERS=10 .venv/bin/python scripts/font_build.py \
  --mapping work/lead/mapping_block_v270.jsonl --out /tmp/after_cleanup.ttf --version 2.6.1
sha256sum /tmp/after_cleanup.ttf   # 应 == c73c3023…（与发布字体一致）

# 2) 快闸（应 PASS，≤2 分钟）
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.1.ttf \
  --manifest work/font/build/manifest_v261.json --version 2.6.1 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json --content-max-damaged 35

# 3) C 类 sha 校验（对 inventory 里记录的 sha256 逐项核对）
```

## 6. 建议

- **执行 A+B**（回收 27.67GB），保留 models（13.8G，重下成本高）；
- 删除后立刻跑 §5 的三步验证；若任一步异常，停止并回滚（A+B 删除不可撤销，但 C 类与 release 包未动，重建能力保留）；
- models 若长期不用，建议**迁外置盘**而不是直接删（保留重跑 OCR/VLM 路线的能力）。
