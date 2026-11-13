# SELF-AUDIT v2.6.2（2026-11-13，发布材料 + 候选收敛自审计）

> 目的：在 owner 提交、正式打包前，对「本次改动 + 发布材料 + 闸数字」做一次自审计：
> 明显错误当场修，次要问题登记进 v2.6.x / v2.6.3。所有数字来自闸输出或可复算命令。

## 0. 审计对象与范围

- 候选字体：`work/font/build/KangXiKai-v2.6.2.ttf`，sha256 `a8bb87d9…`，17,005 字；
- 本轮改动：E37（owner 复核 77 格修复：细线 crossing 过滤 / 线条带解耦 / clean_ink 碎片规则 / frame_escape 厚度口径）；
- 发布材料：`README.md`、`LICENSE`、`OFL.txt`、`docs/reference/RELEASE-METRICS.md`、`docs/releases/v2.6.2/KNOWN-DEBTS.md`、
  `scripts/templates/README-TEMPLATE.md`、`docs/images/`（4 图）、`scripts/release_metrics.py`、`scripts/make_readme_images.py`；
- 文档：AGENTS / PROJECT-STATE / PIPELINE / DATA / VERSION-HISTORY / BACKLOG / ERRATA / PLAN-v2.6.3 / PLAN-v2.7.0。

## 1. 当场修正（明显错误）

| 项 | 问题 | 修正 |
|---|---|---|
| 文档数字 | AGENTS/PROJECT-STATE/PIPELINE/DATA/BACKLOG 仍写旧候选（b73e9f01）、旧闸况（缺件 827/32、框线 1、内容 29） | 统一为 a8bb87d9、缺件 165、框线 0、内容 18、empty 1,173；历史数字保留在 ERRATA/历史行并标注不可比 |
| README | 版式内容定位偏「发版工程」；版本指标表放在首页；无真实图片 | 改为项目介绍（是什么/原书对比/字形示例/规格/方法/限制/安装/许可）；指标移至 `docs/reference/RELEASE-METRICS.md`；生成 4 张真实图片并引用 |
| 图片缺字 | 早期样张出现 tofu（空格/「內」缺字）与残笔污染 | 重生成：主样张逐字排布、网格/对比图只取已验证干净字；书影裁右半版 |
| LICENSE/OFL | `docs/images/` 中扫描书影未被许可范围说明覆盖 | 在 LICENSE/OFL/README/包模板注明：书影为扫描节选、权利归原机构、不在 MIT/OFL 授权范围 |
| README 示例 | 演示串含「內」（字表缺口字） | 改为「康熙字典　楷書字頭」（均已收录） |
| 包模板 | 图片文件未在打包时附入则 README 悬空 | 已在 SELF-AUDIT/PLAN 记录：包构建时 `--extra docs/images/specimen.png --extra docs/images/book-vs-font.png` |
| BACKLOG | §0 计数/§10 结论残留旧候选与 34 条 | 更新为 57 条（已完成 20 / 未完成 37），v2.6.x 小修与 v2.6.3 分列 |
| 脚本 | `_filter_line_mask_to_crossing` 非 uint8 分支返回类型不一致；`make_readme_images` 有未用死函数 | 统一返回 uint8；删除死函数；`release_metrics` 空值输出「—」并注明口径 |
| 模板占位符 | `{version}/{file}/{sha256}/{real}/{built_at_utc}` 需与包 stats 对齐 | 用包 stats 校验：5 个占位符全部存在（missing=[]）；新增覆盖占位符 `{target_coverage_pct}` 等 |
| 正式包清单 | 旧打包链缺 WORKFLOW §8 的固定文件（manifest/coverage-detail/qa-report/PROVENANCE/QA/gate-report 等），`check_release_docs` FAIL | 新增 `scripts/make_release_extras.py`（自动生成清单文件）+ `font_package --extra-dir`；干跑包 `check_release_docs` **PASS** |
| 打包递归 | `font_package` 的 SHA256SUMS/zip 只扫包根目录，`review/` 复核快照未进 zip/SHA（首次正式包发现） | 改为递归（`_iter_pkg_files`）：SHA 25→32 文件、zip 含 review/ 7 文件；zip 自校验 PASS |

## 2. 复核通过的检查

- 候选字体 sha256 `a8bb87d9c4a623d5fe88ae55c2f710a36827052c7cd3594fe70113f56ca18d5b`，17,005 字；
- `font_qa` PASS（同框 0）；字形级框线 **0**；框线逃逸 **0**；内容 **18**（阈值 35）；provenance PASS；
- `fast_gate` **8/8 PASS**；全闸 **9 PASS / 2 FAIL**（缺件 165、empty_assign 1,173，均已知并披露）；
- `release_metrics.py` 重跑成功：v2.5.8/v2.6.1/v2.6.2 三版对比表与 `docs/reference/RELEASE-METRICS.md` 一致；
- README 相对链接/图片目标 28 个全部存在；`scripts/templates/README-TEMPLATE.md` 占位符校验通过；
- `make_readme_images.py` 可复现生成 4 图（样张 / 原书对比 / 书影 / 字形网格），无随机成分。

## 3. 转入 v2.6.x / v2.6.3 的次要项

1. **BF-54 标签错配 11 字**（mapping 重定位）→ v2.6.3 首批；
2. **BF-06 缺件 165**（prune 边缘清理口径）→ v2.6.x；
3. **empty_assign 1,173**（669 半版补映射 + 504 口径 + 40 无 lattice）→ 后续 2.6.x 补丁（计划 v2.6.4+）；
4. **D23 内容判据**（源墨保真度）→ owner 确认后 v2.6.x；
5. **标签审计方法**：参考字体 IoU 噪声过大（4,675 flagged），改用 OCR 交叉核对 → v2.6.3 批（BF-54）；
6. **版本指标补全**：v2.5.8 的缺件/框线/页几何未按现行口径重跑；v2.6.1 相对变化字数未实测 → 后续 patch；
7. **发布包图片**附入、version-artifacts 刷新、RELEASE-INVENTORY 状态列 → 打包时执行；
8. **BF-49 脚本 keep/archive 判定**、release_gate 披露阈值测试用例 → 后续 patch。

## 4. 正式发布结果（2026-11-14）

- clean tree：`c199945`（dirty=false）；`release/KangXiKai-v2.6.2/` + `KangXiKai-v2.6.2.zip`；
- 字体 sha256 **`a8bb87d9c4a623d5fe88ae55c2f710a36827052c7cd3594fe70113f56ca18d5b`**；
- finalize **17/17 PASS**（`sha_final_ok=true`、`zip_ok=true`、doc_check PASS、clean_tree PASS）；
- 披露阈值：内容 35（实际 18）、缺件 165（阈值=观测值）、empty 1,173、框线 0（严格）；
- 打包器递归修复后：包内 **32 个 SHA 文件**（含 `review/` 7 文件），zip sha 以 `release/RELEASE-INVENTORY.tsv` / zip 为准；SHA256SUMS 自校验 OK。

## 5. 复算命令

```bash
.venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-v2.6.2.ttf \
  --manifest work/font/build/manifest_v262.json --outdir /tmp/qa_audit
.venv/bin/python scripts/glyph_frame_gate.py --font work/font/build/KangXiKai-v2.6.2.ttf \
  --manifest work/font/build/manifest_v262.json --out /tmp/gf_audit.json
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.2.ttf \
  --manifest work/font/build/manifest_v262.json --version 2.6.2 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json --content-max-damaged 35 --tag v262
.venv/bin/python scripts/release_metrics.py --out work/lead/release-metrics.json
.venv/bin/python scripts/make_readme_images.py
```
