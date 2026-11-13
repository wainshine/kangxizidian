# 康熙楷 KangXi Kai

> 一套从《康熙字典》康熙五十五年内府刊本重建的**字头真迹**楷书字体。
> An open-source Kaishu typeface built from the *headword* glyphs of the 1716 Kangxi Dictionary woodblock print.

<p align="center">
  <img src="specimen.png" width="920" alt="KangXi Kai specimen">
</p>

**版本：v{version}** ｜ **{real}** 个真实字头字形（无生成字）｜ 授权：SIL Open Font License 1.1

## 这是什么

《康熙字典》（清康熙五十五年，1716，内府刊本）的**字头**以楷书大字刻印。本项目把每一页的
字头（占 2×2 个小字格的大字）逐字切出、矢量化、归一化，做成一套可安装、可再分发的 CJK 楷书字体：

- **真迹**：字形全部来自刻本字头墨迹，不补假字形、不收注文小字；
- **切前排除版面**：版框/界行/页边黑带在裁切阶段排除，不做「切后擦」；
- **可追溯**：每字可回溯到册/页/半版/框坐标，mapping 与闸报告随包提供。

## 原书与字体

上行是刻本字头原样（各字实际页/框），下行是同一串字用本字体渲染：

<p align="center">
  <img src="book-vs-font.png" width="920" alt="book vs font">
</p>

## 字体规格

| 项目 | 内容 |
|---|---|
| 家族名 | KangXi Kai（康熙楷） |
| 文件 | `{file}` |
| 字形 | **{real}** 个真实字头字形（headword-only，无生成字） |
| 格式 | TTF（glyf，UPM 1000；不含标点/数字/拉丁字母） |
| SHA-256 | `{sha256}` |
| 构建时间（UTC） | {built_at_utc} |
| 授权 | SIL Open Font License 1.1（见 `OFL.txt`） |

> **这不是全字库字体**：不承诺 20,992 全覆盖。缺字（含部分常用字）由排版软件系统字体回退显示。
> 覆盖/已知债/质量指标随包提供：`KNOWN-DEBTS.md`、`release-metrics.json`、`gate-report-*.json`。

## 安装与使用

1. 解压后安装 `{file}`；
2. 在排版软件中选择家族名 **KangXi Kai** / Regular；
3. 缺字（含拉丁字母、标点）由系统字体自动回退。

## 字形来源与许可

- 扫描件：《康熙字典》清康熙五十五年内府刊本，[書格 shuge.org](https://shuge.org) 数字化（不随包分发扫描图）；
- 参考字体：霞鹜文楷（LXGW WenKai，OFL）仅用于对比/QA，不参与字形生成，不随包分发；
- 字体：SIL Open Font License 1.1（`OFL.txt`）；代码（仓库）：MIT（`LICENSE`）。

## 文档

仓库文档：`docs/PIPELINE.md`（管线）、`docs/RELEASE-METRICS.md`（版本指标与发版判据）、
`docs/KNOWN-DEBTS-*.md`（已知债）、`docs/PLAN-v2.6.3.md` / `docs/PLAN-v2.7.0.md`（后续计划）。
