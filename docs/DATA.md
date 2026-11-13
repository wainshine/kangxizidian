> **文档状态：现行**（2026-11-10 按当前代码更新：kx_full 统计口径、work 产物结构、现行复现主链、环境、许可说明）。

# 数据、许可与校验和

> **现行状态（2026-11-13，v2.6.2 候选）**：字体 17,005 字形（headword-only 真迹），基本区 10,267/20,992 = 48.91%，目标字表 10,267/16,567 = 61.97%，缺口 6,300；fast_gate 8/8 PASS；全闸 3 项已知债（缺件 827 / 源图框线 1 / empty_assign 1,173）。
> 现行构建输入：`work/lead/page_geometry.jsonl`（E30 扩张版）、`work/lead/mapping_block_v271.jsonl`、`work/lead/page_line_bands.json`、`work/font/build/manifest_v262.json`；缓存版本 = 算法 sha8 + geometry sha12 + bands sha12；字体 sha `b73e9f01…`。
> 构建/闸命令见 `docs/PIPELINE.md` §6；本文 §1 的 14 册 PDF 描述仍准确（00–13，3,869 页，12GB）。
> **字体许可规则**（沿用馆阁体标准）：禁止把专有/商业字体（含系统宋体/黑体）作为发布依据或参照。全管线唯一参考字体 = **霞鹜文楷（LXGW WenKai，OFL 1.1）**，由 `scripts/reffont.py` 统一提供，默认 `work/font/_fonts/LXGWWenKai-Regular.ttf`（复制自馆阁体项目 vendored 文件，不随发布包分发）。参考字体只用于对比分析，不得用于自动删改字形（D20/D21）。
>
> 回答三个问题：每个文件从哪来、能不能用、怎么复现。
> **待补**：14 册 PDF 的来源信息（影印出版者／扫描者／获取渠道）——待所有者提供，见 §1。
>
> **现行项目口径**（2026-11-10）：字表 = canonical 正集 42,302 条 / 唯一基本区字 **16,567**；
> 发布标准 = headword-only（只收字头真迹，缺口不补假覆盖、留给 GAN），当前发布 v2.4.5：17,126 字形、覆盖 10,348（62.46%）、缺口 6,219。

---

## 1. 源扫描件（不入库）

| 项 | 值 |
|---|---|
| 文件 | `康熙字典/` 下 14 册 PDF（00 总目/检字/辨似/等韵；01–12 子丑寅…亥集；13 补遗/备考） |
| 版本 | 清康熙五十五年内府刊本（1716），张玉书等纂；**刻本** |
| 总量 | 12 GB，3,869 页（00:150 + 正文 3,541 + 13:178）；内容页 922×786 pt 跨页扫描 |
| 来源 | **书格 shuge.org 整理本**（owner 2026-11-12 确认）；影印出版者／扫描者／具体获取渠道仍待补。康熙五十五年（1716）内府刊本为公有领域；扫描件使用需遵循来源站点条款。 |
| 许可 | 原书 1716 年公版；扫描件若为公版忠实再现，按主流法域不构成新作品（同 guangeti DATA.md 口径）——**以来源确认后为准** |
| SHA-256 | `work/t00/pdf_sha256.txt`（14 册全量，2026-11-07 计算；入库时移至本文件并校验） |

## 2. 参照数据

| 文件 | 来源 | 许可 | 用途 | 入库 |
|---|---|---|---|---|
| `data/ref/kangxi-dictionary/kx_full.xlsx` | [samsonhoi/kangxi-dictionary](https://github.com/samsonhoi/kangxi-dictionary)（源自汉典系转录，2021） | MIT（**许可文本未入库**——所有者指定屏蔽该目录；MIT 全文见上游仓库，发布前重估入库） | 条目参照表：**48,710 行 / 46,815 唯一字**（含補遺/備考）；其中**唯一基本区字 16,791**。⚠️ 本项目字表基准是正集 `work/seq/canonical.jsonl`（42,302 条 / 唯一基本区 **16,567**），两者口径不同勿混用 | ❌ |
| `data/unihan/Unihan_*.txt` | [Unicode UCD](https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip)（2026-07-31 构建） | Unicode License v3 | kKangXi（上界）、kRSUnicode、kTraditionalVariant | ❌ 可重下载 |
| `data/base/LXGWWenKai-Regular.ttf` | [LXGW WenKai](https://github.com/lxgw/LxgwWenKai/releases)（计划，未下载） | OFL 1.1 含 RFN | 训练输入骨架 + 标点来源；**不进发布字形** | ❌ |

**数据集质量记录**：MIT 数据集与扫描件样本命中 88.6%，但存在实证漏洞（玄字部缺「玄」，
见 HEADWORD-COVERAGE §4）——只能作强参照，不作真源（DECISIONS D10）。

## 3. 生成物（`work/`，全部不入库，可由脚本重建）

按阶段（现行链路加粗）：

| 路径 | 内容 |
|---|---|
| `work/seq/` | **正典序与结构**：`canonical.jsonl`(42,302)、`groups.json`(3,563)、`volume_radicals.json`、`buqi/beikao.jsonl`、`hdr_page_obs.jsonl` |
| `work/lead/boxes300/` | **字头候选检测**（t1_v2 冻结版，300dpi 渲染、150dpi 当量坐标） |
| `work/map/charalign14/` | **字符级序列对齐映射**（8 证据通道 + 部界锚点 lead3，42,302 条） |
| `work/lead/vlm_fp_full.jsonl` | **VLM 注文指纹**转写（32,788 条，Qwen3-VL-2B/MPS） |
| `work/lead/confirmed_union13.json` / `mapping_verified_all13.jsonl` | **最终入字体字集**（17,121）与 mapping |
| `work/font/build/` | 字体构建 cache、TTF、QA 中间产物 |
| `work/models/`（约 13 GB） | Qwen3-VL-2B / Qianfan-OCR 权重（本地推理，不入库） |
| `work/t00/` | T0 阶段：280 页抽样/渲染/检测/OCR、金标候选（`data/gold-certified/gold50.json` 为权威副本）、纠偏 |
| `work/t2/` | T2 阶段：`entry_sequence.jsonl`（48,708 行）、`pdf_map.json`、`owner_page_ranges.json`、书眉真值 |
| `work/t00/pdf_sha256.txt` | 14 册 PDF 校验和 |

## 4. 复现链

**现行主链（生成发布字体，v2.4.x；逐步见 `docs/_history/COUNTS.md` 各节）**：

```bash
# ① 正典序（一次性数据层）
.venv/bin/python scripts/seq_order.py                      # → work/seq/canonical.jsonl 等
# ② 字头候选检测（300dpi 渲染）
.venv/bin/python scripts/lead_run_detect.py --vols 01,...,12 --pages body --dpi 300 --workers 8
# ③ 部界锚点 + 字符级序列对齐
.venv/bin/python scripts/lead_bu_dp3.py                    # → bu_start_pages_lead3.jsonl
.venv/bin/python scripts/lead_char_align14.py              # → work/map/charalign14/mapping.jsonl
# ④ VLM 注文指纹（Qwen3-VL-2B，需 MPS）
PADDLE_PDX_CACHE_HOME=$PWD/work/paddlex_cache .venv/bin/python scripts/lead_vlm_fp_full.py
# ⑤ 指纹确认 + 严格 headword-only 过滤
.venv/bin/python scripts/lead_vlm_confirm.py
.venv/bin/python scripts/lead_strict_headwords.py          # → confirmed_union13 / mapping_verified_all13
# ⑥ 字体构建 → QA → 打包
SOURCE_DATE_EPOCH=1792713600 .venv/bin/python scripts/font_build.py   --mapping work/lead/mapping_verified_all13.jsonl --out work/font/build/KangXiKai-v2.4.2.ttf --version 2.4.2
.venv/bin/python scripts/font_qa.py --font <ttf> --manifest <manifest> --outdir <qa>
.venv/bin/python scripts/font_package.py --font <ttf> --manifest <manifest> --version 2.4.2 --out release
```

**T0 阶段旧链（历史，仅用于复现早期报告）**：`t00_sample → t00_render → t00_detect → t00_ocr → t00_report`。

环境：Python 3.12（`.venv`）；
- PaddleOCR：paddlepaddle 3.3.1 + paddleocr 3.7.0（PP-OCRv5/v6 系列），模型缓存用 `PADDLE_PDX_CACHE_HOME=work/paddlex_cache`（沙箱内 `~/.paddlex` 不可写）；
- VLM：torch 2.15 + transformers 5.22（Qwen3-VL-2B / Qianfan-OCR），权重在 `work/models/`，Apple MPS 推理约 0.2-0.5 s/字；
- 字体：fontTools/potracer 装在 `work/font/_pylibs`（不改 .venv）。

## 5. 许可结论（发布前复核）

- 字形真迹矢量化自 1716 公版刻本扫描件：字形本身公有领域；
- **当前发布（v2.4.5）不含任何合成字**：17,121 字形全部为真迹矢量化（provenance 全 real）；
- 未来 GAN 补全（6,219 缺口字）计划从零训练（目标风格=本书字头），若使用 LXGW WenKai 作骨架/垫字，则必须 OFL 1.1 且避开其 RFN（D2）；该路线尚未实施、无合成字形入库；
- 未使用任何商业字库、专有字体或衍生产物；OCR/VLM 仅作对齐与标签证据，不作字形数据源。

## 参照字体（复核图用，不进入发布字体）

| 项 | 值 |
|---|---|
| 字体 | **霞鹜文楷 LXGW WenKai Regular**（OFL 1.1） |
| 来源 | 复制自同机 `guangeti/data/base/LXGWWenKai-Regular.ttf`（馆阁体项目 vendored 文件） |
| 路径 | `work/font/_fonts/LXGWWenKai-Regular.ttf`（可用 `REVIEW_REF_FONT` 覆盖） |
| 用途 | 复核图的「Unicode 参照字形」与标签文字；**独立于项目字体**，避免拿被审字体自证；不随发布包分发 |

> 注意：康熙字典项目字体本身不受此字体许可约束；发布包只含项目字体与 OFL 声明。找不到参照字体时，复核脚本会明确报错（fail-closed），不退化为系统专有字体。
