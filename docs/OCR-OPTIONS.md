# 支持繁体的 OCR 方案调研 + 本机基准（2026-11-09）

目标：为康熙字典内府本（木刻楷体、繁体、竖排）寻找比现有 PP-OCR 更强的识别方案，用于补齐基本区剩余 8,760 字。

## 一、本机可用的 PaddleOCR 模型库（已实测）

`PADDLE_PDX_CACHE_HOME=<workspace>/work/paddlex_cache`（沙箱内 ~/.paddlex 不可写，需改缓存目录）。

**无偏基准集**：`work/lead/bench_unbiased_labels.json` = demo 目检 28 字 + owner 逐字核实 11 字（29 个唯一字，标签不由 OCR 产生）。
预处理：300dpi 裁切 + 8px padding + 2× 放大。

| 模型 | top-1 准确率（29 字） | 备注 |
|---|---|---|
| PP-OCRv5_server_rec | **20/29 = 69%** | 当前主力，无偏集最佳 |
| PP-OCRv6_medium_rec | 19/29 = 66% | 在 OCR 确认集上更高（95%），但该集有偏 |
| PP-OCRv4_server_rec_doc | 19/29 = 66% | 文档向 |
| PP-OCRv6_small_rec | 18/29 = 62% | |
| PP-OCRv5_mobile_rec | 15/29 = 52% | |
| ch_SVTRv2_rec / ch_RepSVTR_rec | 14/29 = 48% | 旧架构 |
| PP-OCRv6_tiny_rec | 13/29 = 45% | |
| PP-OCRv4_server_rec | 11/29 = 38% | |
| **chinese_cht_PP-OCRv3_mobile_rec** | **4/29 = 14%** | 专用繁体模型，但对木刻楷体最差 |

**多模型集成**：任一模型正确（oracle union）= **25/29 = 86%**；两模型一致时正确率约 **84–88%**（不同架构组合）。
→ 集成能提高召回，但单字级别仍不足以可靠标注生僻字。

**预处理消融**：padding 8/20/30、放大 2×/2.5×/3× —— v5 稳定 69%、v6 在 pad20 时 66→69%，**调参无实质提升**。

**挖字饱和证据**：对 600 个「未确认字」候选框跑 8 模型集成，仅 4 个新字（0.7%）达到「≥2 模型一致 + canonical」标准
→ 结论：剩余生僻字不是「换个 OCR 就能读」，而是**字形本身在 300dpi/木刻油墨下信息不足**。

## 二、外部方案（本环境受限，需资源/密钥）

| 方案 | 说明 | 本环境可行性 |
|---|---|---|
| 百度 Qianfan-OCR | OCR 大模型，官方有「古籍扫描件繁体字+批注+印章」案例；HF 上有 `baidu/Qianfan-OCR` | **HuggingFace 不可达**（超时）；若提供 API key/镜像可试 |
| AnandaSky（badianeai） | 626M 参数 VLM，古籍行图→文本、支持单双栏竖排；需 FlashAttention，**仅限非商业** | HF/gitcode 镜像；GPU 需求；许可证需注意 |
| 腾讯 HunyuanOCR-1.5 | 轻量 OCR 大模型 | 需云 API/权重 |
| PaddleOCR-VL（0.9B） | 文档 VLM，中文强 | 同 HF 问题；CPU 推理极慢 |
| Tesseract chi_tra / chi_tra_vert | 竖排支持是唯一亮点（注文列可直接读） | macOS 无现成二进制，需自行构建 |
| 云 OCR（百度/阿里/腾讯/Google/Azure） | 通用强，古籍专门优化程度不一 | 需 API key，且要评估按页计费 |
| 600dpi 重扫 | 从数据源头提升字形信息量 | 需原书/扫描条件 |

## 三、建议（按性价比）

1. **若可提供任一云 OCR/大模型 API key**（百度千帆、腾讯混元、阿里读光等）：我们可对 3,266 页跑**页级识别**，用文本+版面对齐反查生僻字标签——这是除重扫/人工外最可能补齐 8,760 字的路线；
2. **若可开 HF/GPU**：优先试 Qianfan-OCR（商用友好）与 AnandaSky（非商业限制，需评估）；
3. **本机增量**：8 模型集成 + 「≥2 票一致」规则只能再挖 ~几十到两百字（已实测），不是解法；
4. Tesseract 竖排模型值得作为**注文列读取**的独立通道（不是字头），但需先构建二进制。

复算命令：
```
PADDLE_PDX_CACHE_HOME=$PWD/work/paddlex_cache .venv/bin/python scripts/bench_ocr_unbiased.py
PADDLE_PDX_CACHE_HOME=$PWD/work/paddlex_cache .venv/bin/python scripts/lead_ocr_ensemble.py --limit 600
```
数据：`work/lead/bench_unbiased.json`（各模型逐字预测）、`work/lead/ocr_ensemble_sample.jsonl`（集成样本）。
