> **文档状态：部分过期（历史 demo 阶段 + 现行链路附录）**。§0–§8 描述 2026-11-08 的 **32 字 demo** 链路，其中 `clean_ink v12 / potrace(1.0) / VERSION 0.1.0` 等已被后续版本取代；**现行链路见文末 §12**。
> 当前发布：v2.4.2，17,121 字形（headword-only），构建/QA/打包命令见 `docs/RELEASE-PLAN.md`。

# FONT-BUILD · C 流字体构建链 v0（KangXi Kai）

> 本文件是 C 流（字体构建）的实现与验收记录。**2026-11-08**，负责人：`font` teammate。
> 上游权威口径：`docs/TAKEOVER.md`（最高）、`docs/DECISIONS.md`（D2/D4/D11）。
> 本文件描述「标注产物 → 矢量化 → TTF」链路；产出的 v0 是**管线验证版 demo**，
> 不是发布版（发布版等 Lead 的全量 mapping 接入，字量 ~16k）。

---

## 0. 一句话

`150dpi 框坐标 + PDF 300dpi 直渲染 → 二值化/去栏线与邻字 → potracer 矢量化 →
EM1000 字面框归一化 → fontTools 组 TTF`，32 个**逐字目检过标签**的真迹字头，
两次构建 sha256 完全一致，可复现、可接全量 mapping。

产物：

| 产物 | 路径 |
|---|---|
| demo TTF（32 字） | `work/font/demo/KangXiKai-demo-v0.1.0.ttf` |
| 样张（字体自渲染） | `work/font/demo/specimen.png` |
| 字表 manifest | `work/font/demo/manifest.json` / `manifest.jsonl` |
| 构建统计（含每字 bbox/pad/来源） | `work/font/demo/KangXiKai-demo-v0.1.0.build_stats.json` |
| QA 报告 | `work/font/qa/stats.json`、`report.json`、`render160.png` |
| 目检用 contact sheets | `work/font/sheets/`、`work/font/qa/crop_vs_font.png` |

**最终状态（2026-11-08，Lead 目检通过）**：32 字 demo TTF 可构建/可复现/可排版；
两次构建 sha256 = `d9b9538afdd118eb90785c782cfa88ab65dc70db6ee05f630d5764dd64022f33`；
`--mapping`（全量）与 `--manifest`（字表）两路共用同一链路并实测输出字节一致；
全量 16k 预计单进程 17-31 min、8 进程 3-5 min（cache 断点续跑）。

---

## 1. 环境（不改 `.venv`）

```bash
cd /Users/wainshine/newAI/kangxizidian
python3 -m pip install --target work/font/_pylibs --no-deps fonttools potracer
# 已装：fonttools 4.68.0 + potracer 0.0.4
```

所有脚本 `sys.path.insert(0, "work/font/_pylibs")` 取 fontTools/potracer，
**只依赖 `.venv` 自带的 numpy/cv2/PIL/fitz**（pillow 13 / opencv 5 / pymupdf 2 已具备）。
`--no-deps` 是为了避免把 numpy 装进 `_pylibs` 覆盖 `.venv` 的版本（cv2 ABI）。

---

## 2. 链路与脚本

```
data/gold-certified/gold50.json（60 框 owner-certified，150dpi 页坐标；无 char 字段）
work/font/owner_verified_boxes.json（Lead 提供，10 字目检确认）
   │
   ├─ scripts/font_curate.py   crop 渲染 / 候选标签 / 目检图 / 字表 manifest
   │      crops      300dpi crop（PDF 直渲染，pad 6px@150dpi）
   │      candidates dp_alignment / t2_review_ids / OCR 候选汇总
   │      read|cards|verify   目检 contact sheet（纯 crop / crop+候选 / 放大对照）
   │      priors     部首+画数先验候选（Unihan kRSUnicode，供补标签）
   │      manifest   verdicts.json（人工裁定）→ manifest.json / manifest.jsonl
   │
   ├─ scripts/font_norm.py     灰度 → 二值化 → 清洗 → potrace → EM1000 归一化
   │      向量化后的 glyph 记录（contours，font units）
   │
   ├─ scripts/font_build.py    归一化轮廓 → glyf/cmap/name/OS2/head... → TTF
   │      --mapping  全量 mapping.jsonl（PDF 直渲染，断点续跑缓存）
   │      --manifest 字表 jsonl {char, crop_png}
   │      --glyphs   预归一化 glyphs.jsonl（demo 快路径）
   │
   ├─ scripts/font_qa.py       表完整性/空字形/bbox/cmap/manifest 一致性/孔洞/渲染粗检
   ├─ scripts/font_specimen.py 用构建出的 TTF 自渲染 96px/48px 样张
   └─ scripts/font_mapcheck.py mapping.jsonl 联调前置体检（格式/box 越界/重复/非基本区）
```

### 2.1 crop 与清洗口径（生产）

- **crop**：从 14 个 PDF 直渲染 300dpi（原生分辨率，不插值），150dpi 框坐标
  `px@150 × 72/150 = pt`，pad = 6px@150dpi（=12px@300dpi）。pad 不能用大：
  刻本注文离字头框只有 ~15px@150dpi，大 pad 会把版框线/邻字注文带进来。
- **自适应 pad**：若最大连通域触 crop 边界（框偏紧、字身被裁），自动换 18px@150dpi
  重渲一次（`vectorize_box`）。
- **清洗**（`font_norm.clean_ink` v12）：
  1) 主成分（面积最大）永远保留；
  2) 贴 crop 边的成分 = 版框/栏线/邻字残片 → 丢；
  3) 实心成分（短边 >14px）并集 bbox；细线成分若中心落在该 bbox 外扩 8px 之外
     → 栏线/杂线，丢；落在内部 → 字身细笔，保留；
  4) 字身框外扩 25% 之外的成分 → 邻字/注文，丢；
  5) 极小碎片（<40px）只在主成分 bbox 内（点画）保留。
- **不做**轮廓面积补偿（PROMPT §7 反模式已证伪）。

### 2.2 归一化（v0 口径，已知缺陷见 §6）

- potrace 输出像素坐标（y 向下）→ 等比缩放：`长边 = 760 font units`（EM1000）；
- 位图 bbox 中心 → `(500, 400)`，y 向上；基线 y=0，ascent 880 / descent −120；
- 扁平字（一/乙/亠）按「最长边」归一，不会被拉高；
- 未做 base 字体逐字光学校正（没有 `data/base/` 基准字体；等 v1）。

### 2.3 组字体（font_build.py）

- `glyf`（TrueType 二次曲线，`Cu2QuPen(max_err=1.0)`）+ `loca`；
- 轮廓方向：TrueType 外轮廓顺时针/孔洞逆时针，按「曲线上采样点」判嵌套深度
  （沿用 guangeti fontbuild.py 的审计 P0 修复，避免孔洞被填）；
- 表：`glyf/loca/cmap/head/hhea/hmtx/maxp/name/OS-2/post`（+ `ltag` 由 fontTools 自动加）；
- 只映射 manifest/mapping 里真实存在的字，**缺字不 fill、不假覆盖**；
- 命名：family `KangXi Kai`，style `Regular`，version `0.1.0`，
  psName `KangXiKai-Regular`，achVendID `KXKF`；OFL 1.1 文本进 name 表；
- 可复现：`head.created/modified = SOURCE_DATE_EPOCH + 2082844800`，
  `font.recalcTimestamp = False`，排序固定（glyph order/name 顺序确定）。

---

## 3. 重建命令（demo 一键）

```bash
cd /Users/wainshine/newAI/kangxizidian

# ① crop（PDF 300dpi 直渲染；已有则缓存）
.venv/bin/python scripts/font_curate.py crops --boxes gold
.venv/bin/python scripts/font_curate.py crops --boxes extra     # owner_verified 10 框

# ② 字表：人工裁定 verdicts（crop 与候选标签并排目检）→ manifest
.venv/bin/python scripts/font_curate.py manifest --verdicts work/font/demo/verdicts.json
.venv/bin/python scripts/font_curate.py emit-jsonl

# ③ demo TTF（走 --mapping，和全量同一条链路；也等价于 --manifest）
rm -rf work/font/build/cache
.venv/bin/python scripts/font_build.py \
    --mapping work/font/demo/mapping_demo.jsonl \
    --out work/font/demo/KangXiKai-demo-v0.1.0.ttf

# ④ QA + 样张
.venv/bin/python scripts/font_qa.py \
    --font work/font/demo/KangXiKai-demo-v0.1.0.ttf \
    --manifest work/font/demo/manifest.json --outdir work/font/qa
.venv/bin/python scripts/font_specimen.py \
    --font work/font/demo/KangXiKai-demo-v0.1.0.ttf \
    --manifest work/font/demo/manifest.json --out work/font/demo/specimen.png
```

### 3.1 两次构建 sha256（固定 SOURCE_DATE_EPOCH=1792713600）

```
build #1  d9b9538afdd118eb90785c782cfa88ab65dc70db6ee05f630d5764dd64022f33
build #2  d9b9538afdd118eb90785c782cfa88ab65dc70db6ee05f630d5764dd64022f33  (清空 cache 后重建)
```

> 注意：不同 `SOURCE_DATE_EPOCH` 会改变 sha256；本文与 `build_stats.json` 记录的
> epoch 固定为 1792713600（2026-10-23T00:00:00Z），可用 `--source-date-epoch` 覆盖。

### 3.2 全量 mapping 接入（Lead 的 mapping.jsonl）

```bash
.venv/bin/python scripts/font_build.py \
    --mapping work/font/mapping/full.jsonl \
    --out work/font/build/KangXiKai-full-v0.1.0.ttf
```

- **先体检**：`.venv/bin/python scripts/font_mapcheck.py --mapping <path>` —— 检查
  行格式、`assigned` 结构、box 越界/长宽比、重复字、非基本区字；输出 work/font/build/mapcheck.json（历史批次产物；如需重新生成请运行 scripts/font_mapcheck.py）。
- 输入格式（每行一个半页；`box` = **150dpi 页坐标**，与 `gold50.json` 同口径）：
  ```jsonl
  {"page": "01_0110", "half": "R", "assigned": [{"char": "僨", "cand": {"box": [535,366,622,463]}}, {"char": "僬", "cand": {"box": [1085,744,1165,824]}}]}
  {"page": "08_0020", "half": "L", "assigned": [{"char": "符", "cand": {"box": [241,422,323,502]}}]}
  ```
  同页可多行/多 half；`assigned` 为空数组表示该半页无字（跳过）。
- **幂等/断点续跑**：每个字处理完立即写 `work/font/build/cache/<page><half>_<char>_<x0>_<y0>.json`；
  重跑时命中 cache 直接加载（`--no-cache` 可强制重算）。中断后再跑不会重复矢量化。
- 跳过并记录（不中断构建）：缺 `char`/`box`、同字重复（取第一次）、矢量化失败（空/碎片）。
  全部写进 `<out>.build_stats.json` 的 `mapping.skipped`。
- 输出目录：`work/font/build/`（demo 的 32 字也在同链路验证过，sha 与 --manifest 一致）。

---

## 4. 性能（32 核机器，单进程）

| 步骤 | 样本 | 单字 |
|---|---|---|
| 归一化（crop→potrace→EM 坐标） | 32 字 demo | **23.6 ms/字** |
| 组字体（glyf/cmap/表） | 32 字 demo | **5.3 ms/字** |
| mapping 全链路（PDF 渲染+矢量化+缓存写），框对齐良好 | 32 字 demo | **~62 ms/字**（冷） |
| mapping 全链路，框偏差大（触发自适应 pad 重渲） | 400 个检测器框压测 | **~115 ms/字**（冷） |
| mapping 重跑（全 cache 命中） | 32 字 demo | ~6 ms/字 |
| **全量预演**：400 字冷构建 | 5,000 框合成 mapping 前 400 | **95.8 ms/字**（0 skipped） |
| **全量预演**：缓存命中重跑 | 400 字 | **0.2 ms/字**（sha 与冷构建一致） |
| **全量预演**：断点续跑 | 400 缓存 + 400 新 = 800 字 | 40.8 s（摊薄 50.9 ms/字；cached=400/new=400） |
| **全量预演**：5,000 字冷构建（实测） | 271 页 5,000 框 | **86.8 ms/字**（433.9 s；cached=800/new=4200，0 skipped，max RSS 854.6 MiB，font 6.68 MB） |

**16k 估算（用全量预演实测：5,000 字 86.8 ms/字摊薄、纯新字 ≈103 ms/字）**：
`16,000 × 103ms ≈ 27.5 min` 单进程；按 PDF 分片 8 进程并行（各自 cache 目录、
无共享写）→ **3.5–5 min**；暖 cache 重跑近似秒级。内存 5,000 字 max RSS 854.6 MiB
→ 16k 预计 2–3 GB；cache 116 MB/5,000 字 → 16k ≈ 380 MB。
组字体单进程 ~1.4 min。`concurrent ≤10 / cv2.setNumThreads(1)` 约束下完全可行。
构建日志每 `--progress-every N` 字打印进度（默认 500），便于 16k 批跑监控。
预演实测细节（含内存/断点续跑/失败率）见 `docs/RELEASE-PLAN.md` §6。

> 压测产物（perf_test*.ttf）已删除；mapping 冷跑命令加 `--limit N --pages 01_0110`
> 可先小样验证再全量。

---

## 5. 字表（32 字，全部逐字目检）

> **gold50.json 没有 char 字段**——60 框只是切格 IoU 金标（证明「这是字头」），
> 不是标签真源。可用的标签来源全部先当候选，最终 label 由人工目检确定（见 §6.1）。

| # | char | U+ | page | box (150dpi) | 来源 |
|---|---|---|---|---|---|
| 1 | 九 | 4E5D | 01_0027 | 1498,862,1574,941 | gold50 框 + 目检 |
| 2 | 乞 | 4E5E | 01_0027 | 359,1181,436,1258 | gold50 框 + 目检 |
| 3 | 倉 | 5009 | 08_0020 | 714,1133,801,1213 | gold50 框 + 目检 |
| 4 | 傅 | 5085 | 01_0110 | 1184,1148,1265,1230 | gold50 框 + 目检 |
| 5 | 僥 | 50E5 | 01_0110 | 1185,1328,1273,1412 | gold50 框 + 目检 |
| 6 | 僪 | 50EA | 01_0110 | 1280,1058,1361,1137 | gold50 框 + 目检 |
| 7 | 僬 | 50EC | 01_0110 | 1085,744,1165,824 | gold50 框 + 目检 |
| 8 | 僭 | 50ED | 01_0110 | 543,374,612,450 | gold50 框 + 目检 |
| 9 | 僮 | 50EE | 01_0110 | 337,1156,422,1231 | gold50 框 + 目检 |
| 10 | 儀 | 5100 | 01_0110 | 1468,514,1556,598 | gold50 框 + 目检 |
| 11 | 儷 | 5137 | 01_0110 | 634,1153,710,1230 | gold50 框 + 目检 |
| 12 | 場 | 5834 | 02_0155 | 345,656,438,748 | gold50 框 + 目检 |
| 13 | 塋 | 584B | 02_0155 | 538,1269,612,1350 | gold50 框 + 目检 |
| 14 | 宵 | 5BB5 | 03_0027 | 1229,709,1300,796 | Lead owner_verified |
| 15 | 弌 | 5F0C | 01_0006 | 432,543,505,626 | gold50 框 + 目检（古文大字） |
| 16 | 怒 | 6012 | 04_0017 | 1727,775,1810,850 | Lead owner_verified |
| 17 | 怔 | 6014 | 04_0017 | 260,1285,325,1364 | Lead owner_verified |
| 18 | 昴 | 6634 | 05_0017 | 1653,453,1726,542 | Lead owner_verified |
| 19 | 昵 | 6635 | 05_0017 | 1470,956,1546,1037 | Lead owner_verified |
| 20 | 曀 | 66C0 | 05_0030 | 1722,1362,1802,1454 | Lead owner_verified |
| 21 | 況 | 6CC1 | 06_0032 | 1200,790,1272,866 | Lead owner_verified |
| 22 | 泄 | 6CC4 | 06_0032 | 252,840,321,910 | Lead owner_verified |
| 23 | 班 | 73ED | 07_0021 | 1733,654,1814,734 | Lead owner_verified |
| 24 | 畐 | 7550 | 08_0020 | 728,1240,785,1299 | gold50 框 + 目检 |
| 25 | 笋 | 7B0B | 08_0020 | 1348,685,1426,765 | gold50 框 + 目检 |
| 26 | 符 | 7B26 | 08_0020 | 241,422,323,502 | gold50 框 + 目检 |
| 27 | 筒 | 7B52 | 08_0020 | 1637,417,1712,495 | gold50 框 + 目检 |
| 28 | 答 | 7B54 | 08_0020 | 711,957,800,1037 | gold50 框 + 目检 |
| 29 | 策 | 7B56 | 08_0020 | 143,1357,226,1435 | gold50 框 + 目检 |
| 30 | 築 | 7BC9 | 08_0020 | 429,1270,509,1347 | gold50 框 + 目检 |
| 31 | 隆 | 9686 | 02_0155 | 1500,357,1570,437 | gold50 框 + 目检 |
| 32 | 駮 | 99EE | 12_0017 | 1359,868,1439,945 | Lead owner_verified |

全部 provenance = `real`（字头真迹矢量化）；无 `gan` / `ribbon_fb` / `mapped_traditional`。

### 5.1 为什么 demo 不是 60 字（重要，勿踩）

1. `gold50.json` 的 60 框**没有 char**，只是 IoU 切格金标；不能直接当标签。
2. 60 框分布：`13_0163` 26 框 + `01_0110` 14 + `08_0020` 8 + `02_0155` 6 + `01_0027` 5 + `01_0006` 1。
   `13_0163` 是 **【戌集備考】** 页（owner 书眉核验：戌集備考；非 13_0163=戌集備考 的
   音部/革部備考），其大字几乎全是 **Ext A/Ext B**（U+3400–4DBF / U+20000+），
   按 D11「只处理 CJK 基本区」**全部排除**；dp/rv 标签在该页也全错（備考不参与
   kKangXi 序，DP 只能错配）→ 26 框弃用。
3. `01_0027` 5 框中 3 框是 Ext B（𠃏/𠃐/𠃊）→ 弃用，剩 乞/九。
4. `t2_review_ids`（100 框含 char，T2 所有者复核抽样记录）经抽样目检：**约 24/25 框
   的 crop 与 char 对不上**（例：k0 标「晜」实际是「麻」；k3 标「鉚」实际「鉏」），
   其标签是 DP 指派结果、TAKEOVER §1.4 已判作废 → 不能作为补字来源。
5. Lead 从 dp_alignment2 提取并逐个目检的 `work/font/owner_verified_boxes.json`
   10 字（時 已剔除为「晋」）全部入表；其中 `弌` 是从 [古文] 标签后的**古文大字**
   （TAKEOVER §5：可带标签复用），映射 U+5F0C。
6. 结论：**宁可少字，不可错标**（Lead 指示）。补字只能走「crop↔渲染比对 + 目检」，
   全量标签由 Lead 的 mapping 提供。

---

## 6. 验收结果（32 字 demo）

```
fontTools 可开：glyf/loca/cmap/head/hhea/hmtx/maxp/name/OS-2/post 齐全
UPM=1000，ascent=880 descent=-120，advance 全 1000，fontRevision=0.1.0 与 name 一致
glyphs = 33（32 + .notdef），cmap = 32 == manifest 字表（无假覆盖）
空字形 = 0；tiny(<60) = 0；out-of-em = 0
两次构建 sha256 一致（见 §3.1）
孔洞（对照宋体 TC，仅供参考）：lost=['場']，fewer=['儷','笋']
渲染粗检（256px）：全部有墨；无 >14 连通分量的异常碎片
```

目检记录：`work/font/qa/crop_vs_font.png`（crop ↔ 构建后字体渲染并排），
`work/font/qa/render160.png`（全部字 160px 网格），
`work/font/qa/layout_check.png`（连续字符串排版：基线一致；**demo 只映射 32 个真迹字，
拉丁/数字/标点不在 cmap 中，显示为缺字——这是口径而不是缺陷**；发布版按
`13_extend_punct` 补 42 个标点/数字/空格，届时 cmap = 真迹 + 42）。

---

## 7. 已知缺陷（v0，按影响排序）

1. **统一最长边归一化**：所有字共用「最长边 760 units」字面框，未做 base 字体
   逐字光学校正（`data/base/` 无基准字体）。后果：个别字（如 弌/乞）光学大小与
   邻字略有差异；刻本天生偏斜的字（刻工/扫描形变）不会被扶正。**记录，不在 v0 修**。
2. **紧框/错位框的残留**：owner 框个别偏紧或偏移（`僭` 需 pad 18 重渲，`場` 有碎笔）。
   已用「自适应 pad + 贴边剔除 + 字身框 gate」压到最小；彻底解决要靠检测器 v2 的框。
   当前 32 字中 `僭` 左下残留极少量邻字碎片，`場` 笔画略碎。
3. **孔洞**：`場` 1 个孔洞被二值化封死（对照宋体）；`儷/笋` 孔洞数少于宋体。
   未做 carve_holes（guangeti E38 实测无收益，默认关）。
4. **字重偏细/边缘毛**：300dpi 刻工 + Otsu 二值化 → 边缘 1px 级毛刺；未做
   denoise/面积补偿（反模式清单 §7：轮廓面积补偿已证伪）。
5. **无程序化自交检测**：只有 256px 渲染粗检 + 目检；potrace 输出理论上可能自交，
   目检未见明显自交/翻转（轮廓方向已按嵌套深度修正）。
6. **字形候选/标签证据链**：demo 32 字的 label 来源/box/page 全在 manifest 里可查；
   未目检的候选一律未入表（verdicts.json 记录 accept/drop）。
7. **13_0163 備考页 26 框**：Ext A/B + 标签不可信，整批弃用（理由见 §5.1）。
8. **`--glyphs` 快路径无缓存**：demo 用；全量请用 `--mapping`（有断点续跑缓存）。

---

## 8. 依赖与来源

- 页面/框坐标：`data/gold-certified/gold50.json`（owner-certified 60 框，150dpi）；
  `work/font/owner_verified_boxes.json`（Lead 提取并目检的 10 字，150dpi）。
- 页图/PDF：`work/t00/pages/`（150dpi 渲染），`康熙字典/` 下 14 个 PDF（300dpi 直渲染）。
- 矢量化：`potracer 0.0.4`（纯 Python potrace，guangeti 同款）；组字体 `fonttools 4.68.0`。
- 系统宋体（`/System/Library/Fonts/Supplemental/Songti.ttc`）**只用于**目检候选字形与
  孔洞对照，**不进入发布字体**。
- 许可：OFL 1.1。字形来源 = 清康熙五十五年内府刊本（1716）扫描件的字头；
  未使用任何现代字库轮廓。demo 只映射真实存在的字，不做「覆盖率 100%」表述。

---

## 9. 下一步（已与 Lead 对齐）

1. Lead 产出全量 `mapping.jsonl`（{page, half, assigned:[{char, cand:{box}}]}，box=150dpi）
   → `font_build.py --mapping ... --out work/font/build/KangXiKai-full-v0.1.0.ttf`。
2. cache 断点续跑 + 并行（按页分片、≤10 进程）。
3. 全量构建后跑 `font_qa.py` + 抽样目检；`font_specimen.py` 出样张。
4. v1 改进：base 字体引导归一化、框质量分级、轮廓平滑/自交检测、16k 字重一致性。


---

## 12. 现行构建链（v2.4.x，2026-11-10，以代码为准）

> 本节与 §1–§11 冲突时以本节 + 代码为准。

### 12.1 font_norm.py（矢量化）
- **二值化**：`binarize()` = medianBlur(3) + Otsu，阈值下移 5（去墨晕）；不再用 v22 的无模糊/-10 参数；
- **主体联通簇裁切** `clean_cluster()`：主成分（排除细长栏线） + 距主体 ≤20px 或落在映射框内的成分 = 字形簇；
  簇外墨迹整体剔除；簇明显小于映射框（丢偏旁）时回退「映射框内墨迹」；
- **清洗** `clean_ink()`（v11 规则）：贴边/细线/字身框外成分剔除，兜底；
- **potrace**：`turdsize=3, alphamax=0.8, opttol=0.2`；**归一化**后 `prune_edge_contours()`：
  删外环 10% 内的碎轮廓 + <0.4% 字形面积的微小「孔」（印刷墨点噪声）；
- `vectorize_box()`：自适应 pad（6→18px@150dpi），裁切判定只认「团块状」成分（避免栏线误触）；
- **contours_override.json 门禁**：仅当条目标记 `from_v201_glyph` 时才从 v2.0.1 轮廓复刻注入。

### 12.2 font_build.py（组字体）
- 新增 **`--version`**（name ID5/fontRevision 与版本一致）；`--no-cache` 显式；
- 缓存 key = page+half+char+**完整 box**（v2.3.1 修）；
- OS/2 unicode ranges 当前实现值 `range1=0x1 / range2=0x38000000`（待修工程项，见 RELEASE-PLAN §2 注）；
- 构建实测：17,121 字单进程约 20-22 min（cache 冷启动）；同 mapping + 同 SOURCE_DATE_EPOCH 两次字节一致。

### 12.3 font_qa.py（QA）
- 硬闸：表齐全 / cmap==manifest / 空字形 / tiny(<60) / out-of-em / advance==UPM / fontRevision 一致 /
  **render_bad（256px 连通域>14）** / **同框多字=FAIL**（审计 P0-1 引入）；
- 孔洞（holes lost/fewer，对照系统宋体）**仅诊断不硬判**：刻本常见开放字腔（“日”中横不接右竖=1 腔），
  与宋体不可直接比；语义见 release `QA.md`。

### 12.4 现行发布数字（v2.4.3）
- 17,121 字形；基本区∩16,567 = 10,348 = 62.46%；缺口 6,219（GAN 目标）；
- QA PASS；SHA256SUMS 20 项全过（21 文件）；sha256 `d0107b11067dcebda6b6f356ee3018f4338a95f40f13555d1f732912ec868622`（v2.4.3；字体内容同 v2.4.2）。
