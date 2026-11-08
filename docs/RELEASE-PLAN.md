# RELEASE-PLAN · KangXi Kai 发布计划与元数据定稿

> 2026-11-08 · C 流（font）产出。上游口径：`docs/TAKEOVER.md`（最高）、
> `docs/DECISIONS.md`（D2 家族名/许可、D3 覆盖边界、D4 provenance 四态、D11 基本区）。
> 本文件只定「发布」；构建链细节见 `docs/FONT-BUILD.md`，打包脚本 `scripts/font_package.py`。

---

## 1. 版本方案（建议，待所有者/Lead 拍板）

| 版本 | 定位 | 字量 | 是否公开发布 |
|---|---|---|---|
| `0.1.0`（当前） | **管线验证 demo**：32 个目检真迹字，验证「字头图→字体」全链 | 32 | 否（内部/技术预览） |
| `0.9.x` | 预发布：mapping 首批可用产物，字集/缺口仍在变 | 取决于 mapping | 可选（标注 pre-release） |
| **`1.0.0`** | **全量首发**：cmap 口径与 provenance 四态稳定、缺口已披露 | 目标 21,034 cmap | 是 |

**首发版本号判定（二选一，写死）**：

- 若发布时满足 §5 全部条件且 **cmap 口径（20,992 + 42）已兑现、缺口全部披露**
  → 直接 `1.0.0`。
- 若字量/缺口仍在变化，或 `DATA.md` 的扫描件权利状态未定
  → 先发 `0.9.0`（明确标 pre-release，不承诺 cmap 口径），待条件满足升 `1.0.0`。

**语义化版本语义（本项目自定义）**：

- `major`：字集口径 / provenance 口径 / 字体格式出现**破坏性**变化（如 cmap 结构、
  四态定义变更）；
- `minor`：字量增加、字形整体重建（同一版本词表下重新矢量化）、新增 GAN/ribbon 产出；
- `patch`：仅元数据/打包/构建修复，**发布字形文件内容不变**（改 patch 必须能复现
  「字形不变」的证明：`--glyphs` 缓存重放 sha256 一致）。

**命名**：`KangXiKai-Regular-v<ver>.ttf`；release 目录 `release/KangXiKai-v<ver>/`；
压缩包 `release/KangXiKai-v<ver>.zip`（zip 内根目录同名）。

---

## 2. 字体元数据定稿（脚本已实现，发布前复核）

| 项 | 值 | 位置/备注 |
|---|---|---|
| family name | `KangXi Kai` | name ID 1；D2 |
| style name | `Regular` | name ID 2 |
| full name | `KangXi Kai Regular` | name ID 4 |
| PostScript name | `KangXiKai-Regular` | name ID 6 |
| version string | `Version <major>.<minor>.<patch>` | name ID 5，必须与 `head.fontRevision` 一致（16.16 定点，缺省位补 0） |
| UPM | **1000** | `head.unitsPerEm` |
| ascent / descent | **880 / −120** | `hhea` + `OS/2.usWinAscent/usWinDescent` |
| typo metrics | ascender 880 / descender −120 / lineGap 0 | `OS/2.sTypo*` |
| x-height / cap-height | 500 / 700 | `OS/2.sxHeight/sCapHeight` |
| weight / width | 400 / 5（normal） | `OS/2.usWeightClass/usWidthClass` |
| fsType | 0（可嵌入） | `OS/2.fsType` |
| fsSelection | 64（REGULAR） | `OS/2.fsSelection` |
| achVendID | `KXKF` | `OS/2.achVendID` |
| Unicode ranges | 基本区（bit 0 + bit 28） | `OS/2.ulUnicodeRange1` |
| code pages | 中文简体/繁体（bit 18/20） | `OS/2.ulCodePageRange1` |
| glyph 命名 | `uniXXXX`（不保留 glyph 名） | `post` format 3 |
| cmap | format 4（BMP；发布版只含基本区 + 42 标点） | 若未来含扩展区需加 format 12 |
| 时间戳 | `head.created/modified = SOURCE_DATE_EPOCH + 2082844800`；`font.recalcTimestamp=False` | 可复现构建 |
| SOURCE_DATE_EPOCH | demo=`1792713600`（2026-10-23T00:00:00Z）；**发布版建议改为发布日期 00:00Z 并写进 stats** | `font_build.py --source-date-epoch` |
| 版权声明 | `Copyright 2026 The KangXi Kai Project Authors` | name ID 0 + OFL.txt |
| 许可声明 | OFL 1.1 文本 + FAQ URL | name ID 13/14 + `OFL.txt` |
| Reserved Font Name | **本项目不声明 RFN**；且不得使用 LXGW 的 RFN（霞鹜/霞鶩/落霞孤鹜/落霞孤鶩/LXGW） | D2；README/OFL 都要明示 |

> 复核命令：`.venv/bin/python scripts/font_qa.py --font <ttf> --manifest <manifest>` +
> 打包时 `font_package.py` 的 QA 闸（表/空字形/bbox/advance/fontRevision/provenance 一致）。

---

## 3. README 披露模板（发布包内 README.md 必须覆盖）

`scripts/font_package.py` 内置模板（`--readme-template` 可覆盖），占位符：

| 占位符 | 含义 | 来源 |
|---|---|---|
| `{version}` | 版本号 | font name / `--version` |
| `{cmap_n}` | 本版 cmap 码位总数 | fonttools cmap |
| `{real_n}` / `{gan_n}` / `{ribbon_n}` / `{mapped_n}` | provenance 四态计数 | `provenance.json` |
| `{gap_text}` | 缺口披露句（demo/全量自动切换） | 脚本生成 |
| `{scan_rights}` | 扫描件/影印本权利状态 | `docs/DATA.md`（**发布前必须填实**） |
| `{extra_footer}` | 版本备注（如 demo 声明） | 脚本生成 |

**必须披露（缺一即不得发布）**：
1. 字形来源：1716 年清康熙五十五年内府刊本扫描件字头；**未使用现代字库轮廓**。
2. provenance 四态（D4）逐态计数 + 逐码位文件 `provenance.json`。
3. 缺口：**不得**把 `gan`/`ribbon_fb`/`mapped_traditional` 冒充 `real`；
   不得写「覆盖率 100% 真迹」；`20,992` 只能表述为 **cmap 覆盖承诺**。
4. 简体码位策略（D4 默认②：简体码位→繁体字形）及 `mapped_traditional` 码位清单。
5. 许可：OFL 1.1；未使用 LXGW Reserved Font Name。
6. 可复现：构建命令 + 两次构建 sha256 一致 + 包内 `SHA256SUMS` 自校验方法。
7. 扫描件/影印本权利状态（`docs/DATA.md`；所有者提供后补）。

---

## 4. 打包链（顺序铁律 + 自校验）

```
构建字体（font_build.py） → 写 stats.json / provenance.json / README / OFL / coverage
   → 复制 specimen（可选） → 【最后】重算 SHA256SUMS → zip → zip 内自校验
```

**顺序不能反**：`SHA256SUMS` 必须描述它所在目录的最终字节；先算后改任何文件都会
出现「包内自校验失败」（guangeti 踩过；`14_package.py` 的 `_fix_charset_records`
就是为此在改完记录后重算 SHA）。`font_package.py` 已把该顺序写死，且 zip 打包后
**重新读 zip 内的 SHA256SUMS 逐文件核对**，任一不符即 `ABORT`（不产出可用包）。

命令：

```bash
# demo（当前可用）
.venv/bin/python scripts/font_package.py \
    --font work/font/demo/KangXiKai-demo-v0.1.0.ttf \
    --manifest work/font/demo/manifest.json \
    --specimen work/font/demo/specimen.png --out work/font/release

# 全量（下一会话，mapping 到位后）
.venv/bin/python scripts/font_package.py \
    --font work/font/build/KangXiKai-full-v1.0.0.ttf \
    --provenance work/font/build/provenance-full.json \
    --charset work/font/build/cmap-full.txt \
    --version 1.0.0 --out release
```

QA 闸（`font_package.py` 内置，任一失败即中止）：
`fontTools 可开` / `表齐全` / `cmap == 期望字集（不假覆盖）` / `空字形 0` /
`bbox 在 em 内` / `advance == UPM` / `fontRevision 一致` / `font_qa 渲染+孔洞闸通过` /
`provenance 覆盖全部 cmap 且状态合法` / `provenance 计数 == stats` /
`SHA256SUMS 与目录一致` / `zip 内自校验通过`。

当前 demo 已实测通过：`work/font/release/KangXiKai-v0.1.0/`（7 个文件）+
`KangXiKai-v0.1.0.zip`，`zip_selfcheck: PASS`。

---

## 5. 发布前检查清单（发布负责人逐项打勾）

- [ ] **字集口径确认**：`cmap = 20,992（基本区）+ 42（标点/数字/空格）= 21,034`；
      唯一定义源 `punct_set.py` **尚未 vendor 到本项目**（PROMPT §3 计划清单）——
      **发布阻塞项**：需先复制 `punct_set.py`/`13_extend_punct.py` 或重实现并核对 42 码位。
- [ ] **provenance 完整**：`provenance.json` 覆盖全部 cmap，四态计数与 stats 一致，
      非 real 占比已披露；`gan`/`ribbon_fb` 逐码位可查。
- [ ] **缺口清单**：基本区 20,992 中未进 cmap 的码位、以及进 cmap 但非 real 的码位，
      各有清单或按 provenance 可导出；README 已写。
- [ ] **扫描件权利状态**：`docs/DATA.md` 已由所有者填写 14 个 PDF 来源/扫描者/许可判断
      （**发布阻塞项**）。
- [ ] **QA**：`font_qa.py` PASS；全量孔洞统计已记录（lost/fewer 清单，不只报数字）。
- [ ] **可复现**：同一 mapping + 同一 SOURCE_DATE_EPOCH 两次构建 sha256 一致；
      `--mapping` 断点续跑实测（见 FONT-BUILD §4）。
- [ ] **打包**：`font_package.py` 全程无 ABORT；zip 内自校验 PASS；`SHA256SUMS` 最后生成。
- [ ] **文档**：README 披露项 §3 全覆盖；OFL.txt 版本/年份/版权正确；
      FONT-BUILD/RELEASE-PLAN 与产物一致。
- [ ] **视觉抽检**：`specimen.png` + 随机 300 字目检（常用字优先），
      记录未通过字与是否剔除/重做。
- [ ] **术语**：全库无「写本」；A/B/C 只出现在版本线语境；provenance 四态命名与 D4 一致。

---

## 6. 全量预演实测（2026-11-08，5,000 帧合成 mapping）

> 目的：不依赖真 mapping，验证 16k 全量的耗时/内存/断点续跑/失败率。
> 做法：`work/t00/headwords.jsonl` 的 5,000 个检测器框（271 页）配唯一合成字符标签
> （仅压测，字形标签不发布），跑 `font_build.py --mapping`。

| 指标 | 实测 |
|---|---|
| **冷构建（5,000 字，271 页）** | **433.9 s（7.2 min）**；cached=800 / new=4,200；**86.8 ms/字**（摊薄，含组字体） |
| 冷构建速率（纯新字） | **≈103 ms/字**（PDF 渲染+矢量化+缓存写+potrace 重试） |
| 冷构建速率（400 字样本，干净头框） | 95.8 ms/字 |
| 缓存命中重跑 | **0.2 ms/字**（400 字 0.09 s，sha256 与冷构建一致 = 可复现） |
| 断点续跑（实测） | 已有 400 缓存时跑 800：cached=400 / new=400，40.8 s（摊薄 50.9 ms/字） |
| **失败/跳过** | **0 / 5,000（0.0%）** —— 5,000 个检测器框全部矢量化成功 |
| 峰值内存 | **854.6 MiB**（`/usr/bin/time -l` max RSS；`peak memory footprint` 645.9 MB）；16k 预计 2–3 GB（glyph dict 全内存），32 核机可承受 |
| 缓存体积 | 5,000 字 **116 MB**（≈23.7 KB/字）→ 16k ≈ **380 MB** |
| 5,000 字字体产物 | `work/font/build/rehearsal_5000.ttf`（6.68 MB，5,001 glyphs）+ `.build_stats.json` |
| **全量打包链预演** | 5,000 字 + 混合 provenance（real 4,500/gan 250/ribbon 150/mapped 100）→ 打包 3.3 s，`zip_selfcheck: PASS`，产物 `work/font/release-rehearsal/`（版本号 9.9.9，仅压测） |

**16k 预估**（按实测 103 ms/字冷跑）：`16,000 × 103ms ≈ 27.5 min` 单进程；
按 PDF 分片 8 进程（各自独立 cache 目录）≈ **3.5–5 min**；暖 cache 重跑近似秒级。
内存：5,000 字 max RSS 854.6 MiB → 16k 预计 2–3 GB（32 核机可承受；若需更低，
可按 4 批冷跑+缓存拼装，见 FONT-BUILD §9 待办）。

---

## 7. 发布操作 sequence（全量版，命令级）

```bash
cd /Users/wainshine/newAI/kangxizidian

# 1) mapping 体检（Lead 的 mapping.jsonl）
.venv/bin/python scripts/font_mapcheck.py --mapping work/font/mapping/full.jsonl

# 2) 全量构建（可分批/中断续跑；建议先小样）
rm -rf work/font/build/cache
.venv/bin/python scripts/font_build.py --mapping work/font/mapping/full.jsonl \
    --out work/font/build/KangXiKai-full-v1.0.0.ttf --progress-every 1000

# 3) 生成全量 provenance（mapping 的 char→provenance 由 D 流产物导出）与 charset
#    （格式见 font_package.py --provenance/--charset）

# 4) QA + 样张
.venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-full-v1.0.0.ttf \
    --manifest <全量 manifest> --outdir work/font/qa/full
.venv/bin/python scripts/font_specimen.py --font work/font/build/KangXiKai-full-v1.0.0.ttf \
    --manifest <全量 manifest> --out work/font/build/specimen-full.png

# 5) 打包（顺序内置）+ zip 自校验
.venv/bin/python scripts/font_package.py \
    --font work/font/build/KangXiKai-full-v1.0.0.ttf \
    --provenance work/font/build/provenance-full.json \
    --charset work/font/build/cmap-full.txt --version 1.0.0 --out release
```

---

## 8. 当前 demo 包与「发布阻塞项」

- demo 包已生成并自校验通过：`work/font/release/KangXiKai-v0.1.0/`（仅内部验证，
  **不公开发布**；32 字，无缺口承诺）。
- 发布阻塞项（全量 1.0.0 前必须解决）：
  1. `docs/DATA.md` 的扫描件/影印本权利状态（所有者提供）；
  2. `punct_set.py`/`13_extend_punct.py` vendor（42 标点/数字/空格，cmap 口径唯一源）；
  3. Lead 的全量 `mapping.jsonl` + 逐字 provenance；
  4. 发布版 `SOURCE_DATE_EPOCH` 定稿（建议发布日期 00:00Z）并写进 stats/README。
