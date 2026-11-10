# RELEASE-PLAN · 发布计划与元数据（现行版，2026-11-10）

> **文档状态：现行**。本文件已按当前代码（font_build / font_qa / font_package v2.4.x）重写；
> 旧版「0.1.0 demo → 0.9 pre → 1.0.0 首发、cmap=21,034 承诺、punct_set.py 阻塞」方案**作废**，
> 历史内容见文末「附录 A」。
> 上游口径：`docs/DECISIONS.md`（D15 headword-only / D17 发布流程 / D18 版本号）+ `docs/COUNTS.md`。

## 1. 当前版本线与发布物

- **当前版本：v2.4.4**（内部/技术预览，不对外签收）（2026-11-10，`release/KangXiKai-v2.4.4/` + zip；字形与 v2.4.3 相同，patch 为文档/审计校订）
- 字表：**17,121 字形**（全部真迹，provenance 全 real）；基本区∩16,567 = **10,348 = 62.46%**；
  缺口 **6,219** = GAN 补全目标（清单随包 `v242-strict-report.json`）
- QA PASS / SHA256SUMS **20 项**全过（21 文件）/ zip 自检 PASS（发布目录已冻结）
- 版本语义（D18）：`minor` = 字表/字形整体更新；`patch` = 发布材料/流程/元数据修复。
  历史版本线：v0.3 → v1.0 → v1.1 → v1.2 → v2.0 → v2.0.1 → v2.1.x → v2.2.0 → v2.3.x → v2.4.2 → **v2.4.3**。

## 2. 字体元数据定稿（以 v2.4.2 发布物实测为准）

| 项 | 值 |
|---|---|
| family / style / full / PS | `KangXi Kai` / `Regular` / `KangXi Kai Regular` / `KangXiKai-Regular` |
| version（name ID5） | `Version <major>.<minor>.<patch>`（如 `Version 2.4.3`）；`--version` 传入 |
| fontRevision | `major + minor/10 + patch/100`（2.4.3 → 2.43，16.16 定点） |
| UPM | 1000 |
| hhea asc/desc、typo、win | 880 / −120（win descent 记 120） |
| sxHeight / sCapHeight | 500 / 700 |
| weight / width / fsType / fsSelection | 400 / 5 / 0 / 64（REGULAR） |
| achVendID | `KXKF` |
| OS/2 unicode ranges | `ulUnicodeRange1=0x1`、`ulUnicodeRange2=0x38000000`（当前实现值，见下注） |
| code pages | `ulCodePageRange1=0x140000`（简/繁中文） |
| cmap | format 4 + format 12（**因字表含扩展 A/B 区字形**，旧版「只含基本区」说法已过时） |
| glyph 命名 / post | `uniXXXX` / format 3 |
| 时间戳 | `head.created/modified = SOURCE_DATE_EPOCH + 2082844800`，`recalcTimestamp=False` |
| SOURCE_DATE_EPOCH | 发布统一 `1792713600`（可复现构建；两次构建 sha256 一致已实测） |
| 版权 / 许可 | `Copyright 2026 The KangXi Kai Project Authors` + OFL 1.1；不声明 RFN、不使用 LXGW RFN |

> OS/2 unicode range 注：当前实现为 bit27/28/29（URO/ExtA/ExtB），审计曾指出可能与规范位号有偏差；
> 属待修工程项（不影响字体渲染与 cmap），修复时需同步本表与 `font_build.py`。

## 3. 打包链（现行命令）

```bash
# 构建 → QA → 打包（顺序铁律：SHA256SUMS 最后生成，打包后冻结）
SOURCE_DATE_EPOCH=1792713600 .venv/bin/python scripts/font_build.py \
  --mapping work/lead/mapping_verified_all13.jsonl \
  --out work/font/build/KangXiKai-v2.4.3.ttf --version 2.4.3
.venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-v2.4.3.ttf \
  --manifest work/font/build/manifest_v243.json --outdir work/font/build/qa_v243
.venv/bin/python scripts/font_package.py --font work/font/build/KangXiKai-v2.4.3.ttf \
  --manifest work/font/build/manifest_v243.json --specimen work/font/build/specimen_v243.png \
  --out release --version 2.4.3 \
  --readme-template work/font/build/release_extras/README.tpl.md \
  --extra work/font/build/release_extras/manifest-v243.json \
  --extra work/font/build/release_extras/provenance-detail-v243.json \
  --extra work/font/build/release_extras/qa-report-v243.json \
  --extra work/font/build/release_extras/qa-stats-v243.json \
  --extra work/font/build/release_extras/coverage-detail-v243.json \
  --extra work/font/build/release_extras/QA.md \
  --extra work/font/build/release_extras/PROVENANCE.md \
  --extra work/font/build/release_extras/RELEASE-NOTES-v243.md \
  --extra work/font/build/release_extras/v243-strict-report.json \
  --extra work/font/build/release_extras/random120-v243.png \
  --extra audit/AUDIT-SELF-v2.4.2.md
```

`font_package.py` 内置闸（任一失败即 ABORT）：字体可开 / 表齐全 / `cmap == manifest` / 空字形 0 /
bbox 在 em 内 / advance == UPM / fontRevision 一致 / `font_qa` PASS / provenance 覆盖且状态合法 /
provenance 计数 == stats / SHA256SUMS 与目录一致 / zip 内自校验通过。

## 4. README 披露项（发布包内 README 必须覆盖，缺一不得发布）

1. **headword-only 标准**：只收字头级真迹；注文小字一律不收；缺口不补假覆盖、留待 GAN；
2. 覆盖数字（自动生成）：字形总数、基本区∩16,567 的分子/百分比、缺口数；
3. provenance 四态计数（当前 release：real=全量，其余 0）；
4. **精度敞口**：指纹来源字 84.6%（n=13，宽 CI）→ 约 1,400-1,500 字级错标风险；建议 1% 人工抽验；
5. 缺口/剔除清单文件名（`v242-strict-report.json`）；
6. 许可与版权：OFL 1.1、无 LXGW RFN；
7. 可复现：构建命令 + SOURCE_DATE_EPOCH + `shasum -a 256 -c SHA256SUMS`；
8. 扫描件/影印本权利状态（`docs/DATA.md`；所有者提供后补）。

README 模板占位符（`--readme-template`）：`{version}/{cmap}/{real}/{non_real}/{upm}/{file}/{sha256}` 等
stats 字段 + provenance 计数（含 `{k}_n` 后缀形式）。

## 5. 发布前检查清单（逐项打勾）

- [ ] 字表经 `lead_strict_headwords.py` 严格过滤：无 smallsrc / 无源框 max<65px / 无同框多字 / 无圈号；
- [ ] `font_qa` **PASS**（render_bad=0、tiny=0、同框=0）；holes 仅作诊断（刻本开放字腔，不硬判）；
- [ ] 数字由 manifest/脚本产出（禁止手抄），与 `coverage-detail`/`stats.json` 一致；
- [ ] 随包披露：manifest、provenance 明细、qa-report/stats、coverage、严格清单、抽查图；
- [ ] 打包后 **release 目录冻结**：`shasum -a 256 -c SHA256SUMS` 全过且无 FAILED，zip 内自校验 PASS；
- [ ] 自审计/外部审计材料已归档 `audit/`，如需随包从该目录复制；
- [ ] 文档同步：`docs/COUNTS.md` 追加一节、`docs/V3-STATUS.md`/`docs/SESSION-HANDOFF.md` 更新、`audit/` 记录。

## 附录 A · 历史方案（已作废，保留留痕）

2026-11-08 初版 RELEASE-PLAN 曾定：
- 版本线 0.1.0（demo 32 字）→ 0.9.x pre → **1.0.0 全量首发**；cmap 承诺 `20,992 + 42 = 21,034`；
- 发布阻塞项 = `punct_set.py` 未 vendor（42 标点码位无定义源）+ PDF 权利状态未填；
- 语义化三段版本规则（major/minor/patch）。

**作废原因**：① D15 headword-only 标准取消了 cmap 21,034 承诺（不补假覆盖，缺口留 GAN）；
② 实际版本线按迭代发布为 v0.3…v2.4.2（D18）；③ `punct_set.py` 在当前标准下**不再需要**
（发布 cmap 只含真迹字表）；④ PDF 权利状态仍未填，但已作为发布披露项保留（不阻塞当前内部迭代）。
