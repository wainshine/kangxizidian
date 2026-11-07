# 数据、许可与校验和

> 回答三个问题：每个文件从哪来、能不能用、怎么复现。
> **待补**：14 册 PDF 的来源信息（影印出版者／扫描者／获取渠道）——待所有者提供，见 §1。

---

## 1. 源扫描件（不入库）

| 项 | 值 |
|---|---|
| 文件 | `康熙字典/` 下 14 册 PDF（00 总目/检字/辨似/等韵；01–12 子丑寅…亥集；13 补遗/备考） |
| 版本 | 清康熙五十五年内府刊本（1716），张玉书等纂；**刻本** |
| 总量 | 12 GB，3,869 页（00:150 + 正文 3,541 + 13:178）；内容页 922×786 pt 跨页扫描 |
| 来源 | **待补**（影印本出版信息／扫描者／获取渠道；文件命名风格与书格 shuge.org 整理本一致，待所有者确认） |
| 许可 | 原书 1716 年公版；扫描件若为公版忠实再现，按主流法域不构成新作品（同 guangeti DATA.md 口径）——**以来源确认后为准** |
| SHA-256 | `work/t00/pdf_sha256.txt`（14 册全量，2026-11-07 计算；入库时移至本文件并校验） |

## 2. 参照数据

| 文件 | 来源 | 许可 | 用途 | 入库 |
|---|---|---|---|---|
| `data/ref/kangxi-dictionary/kx_full.xlsx` | [samsonhoi/kangxi-dictionary](https://github.com/samsonhoi/kangxi-dictionary)（源自汉典系转录，2021） | MIT（`data/ref/kangxi-dictionary/LICENSE` 已入库） | 字头参照集（46,815 条；基本区 16,791） | 仅 LICENSE |
| `data/unihan/Unihan_*.txt` | [Unicode UCD](https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip)（2026-07-31 构建） | Unicode License v3 | kKangXi（上界）、kRSUnicode、kTraditionalVariant | ❌ 可重下载 |
| `data/base/LXGWWenKai-Regular.ttf` | [LXGW WenKai](https://github.com/lxgw/LxgwWenKai/releases)（计划，未下载） | OFL 1.1 含 RFN | 训练输入骨架 + 标点来源；**不进发布字形** | ❌ |

**数据集质量记录**：MIT 数据集与扫描件样本命中 88.6%，但存在实证漏洞（玄字部缺「玄」，
见 HEADWORD-COVERAGE §4）——只能作强参照，不作真源（DECISIONS D10）。

## 3. 生成物（`work/`，全部不入库，可由脚本重建）

| 路径 | 内容 |
|---|---|
| `work/t00/sample_manifest.json` | 280 页抽样清单（12 集各 20 + 补遗/备考 40） |
| `work/t00/pages/*.png` | 150 dpi 渲染（282 = 280 抽样 + 2 探针；有字头页 271） |
| `work/t00/headwords.jsonl` | 5,039 字头框 |
| `work/t00/ocr.jsonl / ocr_v5.jsonl` | PP-OCRv6 / v5 逐框识别 |
| `work/t00/gold50.json` | 53 框金标准（**provisional**：AI 目检，待所有者抽检 ≥20 框） |
| `work/t00/rect/` | 纠偏半版图 + 变换记录 + 评估 |
| `work/t00/pdf_sha256.txt` | 14 册 PDF 校验和 |

## 4. 复现链

```bash
.venv/bin/python scripts/t00_sample.py     # 抽样清单
.venv/bin/python scripts/t00_render.py     # 150 dpi 渲染
.venv/bin/python scripts/t00_detect.py     # 字头检测
.venv/bin/python scripts/t00_ocr.py        # 双引擎 OCR（模型自动下载）
.venv/bin/python scripts/t00_report.py     # 对账 → t00_stats.json
.venv/bin/python scripts/t0_gold.py        # 金标候选+拼图（人工核验）
.venv/bin/python scripts/t0_rectify.py     # 版面纠偏
.venv/bin/python scripts/t0_rectify_eval.py
```

环境：Python 3.12（`.venv`），paddlepaddle 3.3.1 + paddleocr（PP-OCRv6_medium/v5_server，
模型缓存 `.paddlex/` 不入库）；安装源清华镜像（pypi CDN 直连超时）。

## 5. 许可结论（发布前复核）

- 字形真迹矢量化自 1716 公版刻本扫描件：字形本身公有领域；
- 合成字由霞鹜文楷（OFL+RFN）派生：本体必须 OFL 1.1，家族名避开 RFN（DECISIONS D2）；
- 未使用任何商业字库、专有字体或衍生部件表；OCR 仅作先验不作数据源。
