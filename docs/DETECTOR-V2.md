# DETECTOR-V2 · 字头候选检测器 v2 与半版计数金标

> 工作流 B（docs/TAKEOVER.md §3）产物。脚本 `scripts/t1_v2.py`；评测 `work/detect2/eval_v2.py`；
> 数字口径见 §3，全部可由 §6 命令重算。**状态：v1（30 页 montage 已交 Lead 逐半版复核）。**

## 0. 一句话

v3 的命门是「每半版有几个字头」。v2 从 v1.6 的「切格框」改为**每半版有序候选 + 六类分数**：
候选**宁多勿少**（box recall 优先），不确定性以 headword 中等分保留（不判死成非字头），
glue/ring/margin/title 只在**强结构证据**下压过 headword（Lead 2026-11-08 裁决）。
输出坐标统一 **150dpi 当量页坐标**（Lead 裁决 2），300dpi 渲染内部降采样到 150dpi 当量检测。

## 1. 相对 v1.6 的改动（为什么需要 v2）

| v1.6 | v2 |
|---|---|
| precision 0.42-0.43，FP 靠 T2 记账消化 | **计数**是验收项：每个 FP 都会让全局序列错 1 |
| 只有「框」 | 每框 6 类分数（headword/guwen/title/ring/glue/margin）+ argmax |
| 无古文概念 | 「〔大字形〕古文变体」识别（实测与字头**同尺寸级**，见 §4.1） |
| 无结构类别 | 书眉版心条 / 标题块（卷首九字、TOC 总目）/ 圈字 / 方框注文 / 粘连 单列 |
| 固定边距假设 | 每页自适应：版心内边界（书眉条）/ 上下框带 / 通高栏线（TOC） |

## 2. 检测架构（`scripts/t1_v2.py`）

### 2.1 版面归一
1. `BIN_T=150` 二值（透印残影灰度 ~180 可分离）；
2. `page_ink()`：形态学去长直线（版框/书口折缝 ~940px 竖线）；
3. `h0`（注文小字高）：方格状小分量高度中位数，282 页实测 36-38px@150dpi，极稳；
4. 上下框带 `hline_band()`；版心（书眉）内边界 `strip_borders()`（外缘 2%-12% 区内**最长竖线**）；
5. 通高竖线数 `vline_count()`（TOC→标题判定，实测 13_0012 总目 nvf=9）。

### 2.2 候选来源（P1-P5，合并时按「字形质量」而非面积去重）
| 源 | 说明 | 治什么 |
|---|---|---|
| P1 v1.6 提案 | 腐蚀(5)+膨胀(18)+NMS | 常规字头 |
| P2 框内拆字 | v1.6 大框内取「字头尺寸带」原墨分量（largest_comp + subglyph） | 字头被 v1.6 与邻字并成大框 |
| P3 原墨连通域 | 字头尺寸带 / 宽扁笔（一/乙/亅按宽度）/ 竖长窄字 / 贴页缘 | v1.6 漏检、扁平细笔画 |
| P4 碎片修复 | 小核膨胀(9)后取连通域 | 刻版磨损/断笔碎片化字形（13_0163/08_0020 实测） |
| P5 古文变体 | 古文三元组（§4.1）的第三个大字 | 古文变体不是数据条目但 gold 框要检出 |
| 竖向链合并 | 同列相邻「大字块/宽扁笔」合并（高 1.65-2.85h0） | 二/三/亖/上 等拆笔字头 |
| 超高/超宽拆分 | 沿低墨隙切块（块高 0.85-2.85h0） | 「音部/韋部」大字标题、注文竖排粘连 |

### 2.3 逐候选几何特征（40+ 维，见 JSON `feat`）
`size_ratio=h/h0`、`w_ratio`、`squareness=w/h`、`ink_ratio`、`max_comp_h_ratio`（最大分量高/框高）、
`dom_frac`（最大分量墨量/框墨量）、`n_comp`、`n_comp_ge32`、`n_ink_bands`/`max_band_frac`（行带结构，
双字竖排=2 条 ~0.4h 墨带）、`stroke_ratio`（距离变换 97 分位/ h0）、`ring_score`/`ring_r`（Hough 圆+圆周覆盖）、
`col_top`（列首）、`context_ink`（邻域密度）、`border_frame`/`edge_thin`/`frame_cover`（方框注文）、
`n_inner_char`（框内小字）、`margin_strip`/`outer_edge`/`outside_band`/`edge_flag`。

### 2.4 结构检测（先于分类）
- **标题块**：模板匹配「康」「典」（模板取自 01_0006 目检框，150dpi 存 `work/detect2/templates/`），
  以匹配点为锚向左侧 ~6h0、下方 ~10.5h0 取标题块 zone → zone 内大字=title；
- **TOC/总目页**：通高竖线数 ≥7 且内区墨占比 <0.12 → 大字=title（13_0004/13_0012/13_0081）；
- **古文变体**（§4.1）：阅读序「[大字][古文两小字][大字]」三元组，小字对用多尺度模板匹配校验
  （古/文 NCC 阈值 0.62/0.68），第三字=guwen；连续同尺寸大字继续判第二个变体（弌/弍/弎、畐 等）；
- **圈字**：Hough 圆（半径 0.8-1.45h0）+ 圆周墨覆盖 ≥0.62；
- **书眉/版心**：外缘书眉小字条（小字堆叠形状）→ margin；
- **透印/空白半版**：正文带内区墨占比 <0.075 → blank（01_0006R=0.055；注意总目页/稀疏页会落 blank，
  计数口径下 blank=0 字头，正确）。

### 2.5 分类打分（每类 0-1，JSON `cls`）
- 强否决顺序：margin（页缘/框带/线状大框）→ ring（强圆）→ title（模板/TOC）→ guwen（三元组）；
- 强 glue 证据：竖向双字（2.15≤sr≤3.05、w≤1.42h0、两条 ~0.3-0.62h 墨带）/ 横向双字 /
  方框注文（框线贯穿全高 + 框内小字）；
- 其余 glyph-like（1.38≤sr≤3.05 方框、扁平、竖长窄）→ headword **0.50-0.97**：
  单主分量+尺寸带+方形度越高分越高；**拿不准也不判死**；
- argmax 类 + `count_headword`（严格口径：argmax=headword 且 hw≥0.80，供计数对账）
  与 `count_headword_soft`（argmax=headword，慷慨口径）。

### 2.6 输出
- 每页 JSON：`{page, dpi, halves:{R:{blank, inner_frac, toc_like, y_range, strip_x, n,
  count_by_cls, count_headword, count_headword_soft, cands:[{box,w,h,size_ratio,squareness,
  ink_ratio,edge_flag,src,cls{6类},argmax,feat}]}}, stats:{h0,render_dpi,coord_dpi,ms}}`
- 半版内候选按阅读序（列右→左、列内上→下，`reading_order()`）；
- `--montage DIR`：①`<stem>_cands[_k].png` 候选裁框拼图（每行 8 格、编号+类别色+hw 分数）；
  ②`<stem>_page.png` 整页编号框叠加图（查漏检）。

## 3. 评测口径（数字可复算）

- **box recall**：金标/EXP30 框被任一候选 IoU≥0.5 覆盖（不管类别）；
- **head-cls recall**：匹配候选 argmax ∈ {headword, guwen}——金标 60 含「弌/畐」类古文变体框，
  按 TAKEOVER §5 必须 cls=guwen，不能算 headword 但也不能算「非字头」；
- **head_argmax recall**：argmax==headword（不含古文变体，严格）；
- **EXP30 分母**：86 = 94 框 − 8 结构框（title 5：id0,1,2,3,5；blank 3：id4,6,11）。
  8 结构框另列 `struct_ok`（title→title 类；blank→无候选）；
- **红标 FP**：EXP30 42 个 owner 红标框，匹配候选 argmax≠headword 或未出候选 = 正确；
- **半版计数**：`count_headword`（严格）vs Lead 目检 truth，逐半版 Δ。

## 4. 实测事实（本次新增，直接可复用）

1. **古文变体不只是 1.7-1.75×h0**：01_0006「弌」=73×83（sr 2.18）、01_0007「𠆤」=80×84（sr 2.21）、
   13_0163/08_0020 的「畐」类变体 sr 1.56-2.3——**与字头同尺寸级，尺寸不可区分**。
   唯一可靠特征 = 前方两小字「古文」标签（模板匹配 古/文 NCC≥0.62/0.68）+ 标签前为大字。
2. **标题块字符也是 2.0-2.4×h0**（与字头同级），靠模板匹配「康/典」+ 位置簇区分；TOC 页靠通高竖线。
3. **圈字含圆圈内数字**（圈「二」「七」）与「增」圈：Hough 圆 + 圆周覆盖是可靠判据。
4. **02_0155/08_0020 等页存在「古文」双变体连续出现**（弌→弍?、畐→畐）：需连判第 2 变体。
5. **透印/空白判定**：01_0006R inner=0.055；但 13_0012 总目页 inner=0.038、稀疏正文页可到 0.09——
   阈值 0.075 且「总目页=0 字头」口径下无误。
6. **版心（书眉）条内边界**：外缘 2%-12% 区内最长竖线（150dpi 实测 L border≈39-54，R border≈W-40..W-100）；
   书眉小字堆叠的高约 85-95px（2.3-2.6h0），形状与注文双字粘连相同——**只能靠位置区分**。
7. gold 60 中 3 框是古文变体（01_0006「弌」、08_0020「畐」×2）→ head_argmax 上限 0.95 是**正确行为**。

## 5. 当前数字（2026-11-08，`work/detect2/report.json`）

| 指标 | 值 | 门 |
|---|---|---|
| 候选生成：gold 60 box recall | **1.000** | ≥0.995 |
| EXP30 86 字头 box recall | **1.000** | ≥0.995 |
| head-cls recall（gold 60：headword∪guwen） | **1.000** | ≥0.99 |
| head-cls recall（EXP30 86） | **1.000** | ≥0.99 |
| head_argmax（严格，不含古文变体）gold / EXP30 | 0.950 / 0.965 | — |
| EXP30 8 结构框（title5/blank3） | **1.000** | — |
| EXP30 42 红标 FP 非字头率 | **0.952**（2 个残差：0009R 增圈粘连、0030R 音注框） | ≥0.90 |
| 半版计数（Lead truth 第一波 4 页 8 半版） | **1.000**（max|Δ|=0） | ≥0.95 |
| 计时 150dpi 渲染+检测 | 0.35-0.85 s/页（单进程）；8 进程 ~0.15 s/页墙钟 | ≤2s |
| 计时 300dpi 渲染（--render-dpi 300）+ 150 当量检测 | ~0.7 s/页 | ≤2s |

半版计数 truth 第一波（Lead 300dpi 目检）：01_0006 L1/R0、01_0007 L0/R1、01_0008 L5/R2、01_0009 L1/R1。
落盘 `work/detect2/count_truth.json`；30 页 montage 见 `work/detect2/montage_v1/`，
等 Lead 第二波 truth（20-30 半版）后补报全 30 页的 |Δ| 分布。

## 5.9 与 Lead 冻结副本的 diff（2026-11-08 17:34 `scripts/lead_t1v2_frozen.py`）

冻结后本脚本仅有一处**纯增量**改动（无函数签名变化、不影响任何已报数字）：
`reading_order()` 给每个候选额外写入 `col`（0=最右列）与 `col_cx`——供 solver 重建列结构。
复现全部数字请用冻结副本；本脚本 `--dpi 300` 默认渲染 150dpi（`--render-dpi 300` 可强制 300 渲染再降采样，
两者输出坐标与计数一致，已实测）。后续调参请另存 `scripts/t1_v3.py`。

## 6. 复现命令

```bash
# 4 页 truth + gold/EXP30 标注页（150dpi 缓存页）
.venv/bin/python scripts/t1_v2.py --pdf 01 --pages 6-9,27,110 --dpi 150 \
    --page-dir work/t00/pages --out work/detect2/boxes150 --montage work/detect2/montage_v1
.venv/bin/python scripts/t1_v2.py --pdf 02 --pages 29,155 --dpi 150 \
    --page-dir work/t00/pages --out work/detect2/boxes150 --montage work/detect2/montage_v1
.venv/bin/python scripts/t1_v2.py --pdf 08 --pages 20 --dpi 150 \
    --page-dir work/t00/pages --out work/detect2/boxes150 --montage work/detect2/montage_v1
.venv/bin/python scripts/t1_v2.py --pdf 13 --pages 163 --dpi 150 \
    --page-dir work/t00/pages --out work/detect2/boxes150 --montage work/detect2/montage_v1
.venv/bin/python scripts/t1_v2.py --pdf 04 --pages 30 --dpi 150 \
    --page-dir work/t00/pages --out work/detect2/boxes150 --montage work/detect2/montage_v1
# 评测（写 work/detect2/report.json）
.venv/bin/python work/detect2/eval_v2.py --boxes work/detect2/boxes150 \
    --json work/detect2/report.json
# 生产：300dpi 渲染（内部 150 当量检测），全量可 8 进程
.venv/bin/python scripts/t1_v2.py --pdf 01 --pages 6-40 --dpi 300 --render-dpi 300 \
    --out work/detect2/boxes300 --workers 8
```

## 6.5 全量跑批口径（2026-11-08 实测，脚本已冻结）

| 路径 | 实测 | 全量 3,869 页外推（8 进程） |
|---|---|---|
| `--dpi 150`（默认，渲染 150dpi 缓存等价；t00 渲染与直渲染逐像素一致） | vol01 242 页 31.7 s = **0.131 s/页墙钟** | **~8.4 min** |
| `--dpi 300 --render-dpi 300`（300dpi 渲染→内部降采样 150 当量检测，输出坐标一致） | vol02 24 页 2.4 s = **0.10 s/页墙钟**（CPU ~0.70 s/页） | **~6.5 min**（CPU 下限 ~5.6 min） |

- 单页 CPU：检测 0.35-0.85 s（150 当量尺度），渲染 0.10 s（150dpi）/0.25 s（300dpi）；
  8 进程满载时 32 核机器 <10% 占用富余，可上 10-12 进程。
- 每页独立 JSON（`--out DIR`），断点续跑安全；`--page-dir work/t00/pages` 可复用 150dpi 缓存页，
  无缓存页直接 fitz 渲染（同一渲染器，逐像素一致，已实测 diff=0）。
- **内存**：单页 300dpi 灰度 ~12.5 MB + cv2 中间量 <200 MB/进程 → 8 进程 <2 GB。

## 6.6 半版计数已知系统偏差（下一会话头号问题）

Lead 全量检测：vol01-03 半版计数总和比正典序少 ~10%（2381/2633、2564/2901、2337/2597）；
但 0006-0009 的 8 个半版与 owner truth 完全一致（Δ=0）。现有证据与判断：

1. **候选生成不是瓶颈**：vol01 随机 40 页「headword 尺寸带+方形+面积≥700」的大字形原墨分量
   与全部候选的覆盖率 = **0 个未覆盖/40 页**（`work/detect2/tmp/coverage_check.py` 可复算）——
   字头级漏检基本不存在。
2. **分类层面采样的非字头是真非字头**：vol01 中 argmax=ring 的大字形抽样 6/6 为真圈字
   （圈「增」「五」等）；guwen 大字形抽样 5/5 为真古文变体（前有「古文」标签）。这些均**不应计入**。
3. **正典序口径本身偏大（已量化）**：canonical_proto 中同一 (kx page,position) 的重复条目
   （重出/异体）为：子集 90、丑集 110、寅集 68（=3.4-3.8%）；即「该印但不可字形头计」的一部分。
   扣除后：子集 2381/2543=93.6%、丑集 2564/2789=91.9%、寅集 2337/2529=92.4%。
4. **剩余 ~6-8% 的待验假设**（现有证据无法唯一判定，需人工目检 10 个随机跨页）：
   (a) 正典序含「本刻本未以大字字形头印出」的条目（数据集/Unihan 转写误差、重出行只有小字标注）；
   (b) 严格计数阈值 `hw≥0.80` 在磨损页丢掉少量真字头（需要 row-level 抽样验证）；
   (c) 备考/補遺页「X部」大字标题被计为 headword（13_xxx 页实测每半版 0-3 个，见 §7）。
5. **下一会话验证方案（30 分钟可定论）**：抽 10 个 vol01 随机跨页（非 0006-0009），
   300dpi 人工逐半版数**印刷数据条目级字头**，与 {detector count, 正典序 kx 切片} 三方对账；
   若 detector≈人工 → 结论 = 正典序含未印条目（v3 映射需容忍/剔除）；若 detector<人工 → 定位漏计类别后修 v3。

## 7. 已知残差 / 下一步

1. **13_0163/13_0154 等備考密排页**的「X部」大字标题（音部/韋部）目前判 headword（尺寸与字头同级、
   无可匹配模板）→ 计数偏高，待 Lead 对 13_0163/13_0124/13_0141 的 truth 后加「部名标题」模板/位置规则；
2. 04_0017R/06_0018R/10_0023L 等「0 计数半版」需 Lead 目检确认（可能是跨页续排，也可能漏检）；
3. 2 个红标残差：0009R 圈+粘连混合块、04_0030R「音注方框」与细边框磨损混淆；
4. 全量 3,869 页：本脚本单页无外部状态、支持多进程；Lead 有 8 进程 driver 可直接调用
   `scripts/t1_v2.py`（每页独立 JSON，断点续跑按输出文件判断）。
