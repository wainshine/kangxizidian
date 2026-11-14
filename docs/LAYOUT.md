# LAYOUT · 原书版式、切分与选用规则

> **本文回答一个问题：这本《康熙字典》刻本长什么样，我们按什么规则把它切成「一个字」，又按什么规则决定收谁、不收谁。**
> 不是从代码反推——本文是规则的文字版；代码/数据/闸只是规则的实现与验证。
> 本文不是「另一套管线」：技术参数仍以 `docs/PIPELINE.md` 为唯一权威；口径决策以 `docs/DECISIONS.md` 为准；
> 卷/部首/书眉数据层见 `docs/reference/STRUCTURE.md`、`docs/reference/HEADERS.md`；方法概览见 `docs/METHOD.md`。

## 0. 一句话

刻本正文是**竖排、右→左**；一页扫描图是**跨页（左右两个半版）**；正文大字（字头）占 **2×2 个小字格**，
小字注文占约 **1 个小字格**；我们只取「2×2 格块里的字头大字」，按「版框正文区 ∩ 2×2 格块」成框，
**在二值化前**排除版框/界行/页边黑带/注文残线，再矢量化、归一化、闸检、发布。

---

## 1. 原书版式（刻本）

### 1.1 页、半版与阅读序

- 扫描件一页 = 刻本的**一个跨页**，分 **L（左）/ R（右）** 两个半版；
- 刻本阅读序为**竖排、每行从右向左**；跨页的阅读顺序是 **先 R 后 L**（`docs/reference/STRUCTURE.md` §3/§5 实测）；
- 页 key 规则：`NN_PPPP`（NN=册号 00–13，PPPP=册内扫描页号）；`work/t2/pdf_map.json` 是页→PDF 的映射；
- 正集为 **12 集 × 上/中/下 = 36 卷**；PDF00=总目/检字等，PDF13=補遺/備考（**不参与正集正典序**）。

### 1.2 版面骨架

```
┌──────── 版框（外框线）────────┐
│ 书眉（L 半版左缘版心，竖排：     │
│  康熙字典 / 子集中 / 日部 / 五畫 / 葉码）│
│ ┌─界行─┬─界行─┬─界行─┬─界行─┐ │
│ │ 字头 │ 大字 │ ...  │      │ │
│ │  2×2 小字格块（大字 = 字头）   │ │
│ │ 注文小字（约 1 小字格）...      │ │
│ └──────┴──────┴──────┴──────┘ │
└──────────────────────────────┘
```

| 元素 | 规则 | 来源/实现 |
|---|---|---|
| 版框 | 四周外框线；正文区 = 版框内再内缩 4px | `page_frames.py`、`content_quad` |
| 界行 | 列间竖线；用于列定位；**不得进入字形** | pre-cut（`precut_masks.py` / `font_build`） |
| 版心/书眉 | 书眉在 **L 半版左缘**竖排：`康熙字典 → 集名卷 → 部名 → 画数 → 葉码`；画数=部外笔画；跨分界页有两个画数字段（第一字段=R 半版组、第二=L 半版组） | `docs/reference/HEADERS.md` §1 |
| 葉码 | PDF01–12 实测 **葉码 = 扫描页 − 5**；PDF13 按分节另读 | `docs/reference/HEADERS.md` |
| 卷扉页 | 每卷前 1 个扉页（可能跨 2–3 个半版），列该卷部首；扉页尾可落在卷首跨页 R 半版，L 半版才是正文 | `docs/reference/STRUCTURE.md` §3/§5 |
| 部首页 | 部与部之间没有独立扉页，直接接排；部首页版心写「X部」+画数，字头为部首自字 | `docs/reference/STRUCTURE.md` §4 |
| 卷界 | 卷首跨页 R 半版=扉页尾/留白，L 半版=正文第一半版；卷末 14/36 卷 L 半版留白 | 同上 §5 |

### 1.3 文字层级（本项目的「字头」定义）

| 层级 | 排版单位 | 字号/实测 | 是否收录 |
|---|---|---|---|
| **字头（大字）** | **2×2 个小字格**，格块边界≈版框内一格大字 | 框宽 p5/p50/p95 = **99/102/103px@150dpi**；框高 **95/98/100px**（同页 σ≈0.4px） | ✅ **只收这一级**（D15） |
| 注文（正文小字） | 约 1×1 小字格（约为字头一半） | 源框 max 边 **<65px@150dpi** 即视为注文级 | ❌ 不收（D15） |
| 书眉/版心字 | 版心竖排小字 | 不属于正文 | ❌ 不收 |
| 版框/界行/页码 | 线条/数字 | — | ❌ 裁切阶段排除 |

### 1.4 格点（lattice）与行款

- 小字组件中心（h 24–54、w 9–60、area 40–1200，150dpi）→ 对 x/y 分别拟合**格点周期 `(px,py)` 与相位 `(phx,phy)`**；
- 每半版一个 lattice；**2×2 小字格块 = 字头大字**；`block_for_box(lat, box)` 从字框中心取 2×2 格（半格偏移 + 3px 余量）；
- 行款实测：正集正文 **3,266 body 页**、约 **6,479 个正文半版**；全书密度 **12.95 条/页 ≈ 6.53 条/半版**（`docs/reference/STRUCTURE.md` §5）；
- 因此框面积由**排版**决定，**不是字墨紧框**；框面积必须均匀——这正是 block mapping 的由来，也是不能退回「墨迹紧框」的原因。

---

## 2. 切分规则（我们如何把版式变成单字）

### 2.1 坐标约定（先记这一条，避免所有坐标坑）

| 坐标 | 用途 | 约定 |
|---|---|---|
| 150dpi 页坐标 | lattice / box / manifest 全部用它 | `page_geometry.jsonl`、`mapping_block_v*.jsonl` |
| 300dpi 裁片坐标 | 渲染/二值化/掩膜 | `dpi_scale=2.0`，裁片 pad150=6px（不够时自动加大 pad 重渲一次） |
| 旋转空间（rot） | 版框正文区 `content_quad` 的 `box`/`M`/`Minv` | `page_frames.py`：先估页微旋转 θ（0.2–0.4°）→ 旋转校正 → 线簇聚类 |
| 归一化 EM 坐标 | TTF 轮廓 | 最长边 760 units，bbox 中心 (500,400)，UPM 1000，ascent 880 / descent −120 |

> **规则**：任何跨坐标运算必须先显式变换（`M/Minv`）。`make_block_mapping` 的「原图 block vs 旋转空间 quad」直接求交是已登记缺陷 BUILD-404；在修好前，**禁止重跑全量 mapping 生成**（详见 `docs/plans/PLAN-v2.6.3.md` / audit4 BUILD-404）。

### 2.2 S1：页级几何（把一页变成可切分的半版）

1. **半版划分**：gutter 由列投影取 42–58% 区间最小值定位；
2. **lattice 拟合**：见 §1.4；
3. **text_bbox**：正文墨迹 bbox 内缩 5px（版框外沿≈bbox）；
4. **content_quad（版框正文区）**：
   - Hough 长线估页微旋转 θ → 旋转校正；
   - 近轴（±2.5°）线段聚类得竖线簇 x / 横线簇 y；
   - 每半版取「靠边但最靠内」的框线簇作为版框内边界，再内缩 4px；
   - 兜底：小字 bbox ±60px、页边黑带钳制、框线缺失侧用 `fallback_quad_from_lattice`；
5. 产物：`work/lead/page_geometry.jsonl`（3,869 行；**3,526 页有 quad，343 页无 quad**→ 走兜底/裁片外带规则）。

### 2.3 S2：字头 mapping（把正典序落到「哪个框」）

1. **正典序**：`work/seq/canonical.jsonl` 正集 **42,302 条** → 唯一基本区 **16,567 字**；PDF13 補遺/備考不参与；
2. **页定位**：正集 → **3,266 body 页** → 半版 → `mapping_verified_all33.jsonl`（5,695 页半版、17,007 字；E23 同块冲突剔除 沓/忠 后 **17,005**）；
3. **成框**：`box = 2×2 格块 ∩ content_quad`（`make_block_mapping.py`）；`block_for_box(lat, box)` 取中心所在 2×2 格（半格偏移 + 3px 余量）再与 quad 求交；
4. **单一真源**：修复（扩框/重定位/同块冲突）必须**回写 mapping**；禁止 overlay/restore 把旧字形拷回（会带回旧框线）；
5. **空指派**：有 quad 但 mapping 无行的半版 → `empty_assign`（v2.6.2 为 **1,173**：vol01–12 **669** + vol00/13 **504** + 无 lattice **40**）；这些半版**不产生字形**；
6. **隔离**：9 字（刃/榍/法/紆/総/荹/仟/禦/絞）不进入发布字表，理由随包。

### 2.4 S3：裁切与矢量化（切分规则的核心）

每字按 300dpi 渲染 `box + pad150(6)`，然后：

1. **二值化**：中值背景相减；
2. **pre-cut（在二值化后、2×2 块掩膜前）**：
   - `clip_mask_page`：按 `content_quad` 把版框正文区外像素置零（框线/黑带/角部楔形不进入后续掩膜）；
   - `trim_crop_frame_edges`：裁片外带若有贯穿长线，整条裁掉（只动外带）；
   - `strip_crop_frame_bands`：删贯穿裁片边界、触到两侧的整行/整列墨带；
   - 页级直线 mask：长线 + **E37 crossing 过滤**（只删「贴/穿 2×2 块边界」的线组件；完全在块内的细长组件视为字身笔画保留）；
   - **已验证线条带**（`page_line_bands.json`，27 rect）：无条件应用（E37 与 crossing 过滤解耦）；
   - **2×2 块掩膜**：只保留该字 2×2 格块内墨（块外邻字/注文丢弃，3px 余量）；
3. **主簇清理**：`remove_specks` → `clean_cluster` → `clean_ink`；E37 起 clean_ink 增加「非主体、面积 <5% 主体、距主体 bbox >15px」的注文/邻墨碎片规则；
4. **描迹**：2× 超采样 → potrace；
5. **归一化**：以字墨全轮廓 bbox 为基准，最长边 → 760 units，bbox 中心 → (500,400)；
6. **轮廓整理**：`orient_contours` + `prune_edge_contours`（prune 只删「贴边+线状+小面积」轮廓）；**旧缺件 165 的根因不是 prune**（E39/E40：主因是扫描侧 precut crossing 过滤 `np` 未导入导致 fail-open；owner 复核确认 prune 删除正确，不修 prune）；
7. **缓存**：key = `_CACHE_VER + page+half+char+box`；`_CACHE_VER` 含算法脚本 sha8 + geometry sha12 + bands sha12（+可选 tag）。改任一脚本/几何/线条带 → 全量重建。

### 2.5 切分的硬规则（不能违反）

1. **框 = 2×2 格块 ∩ content_quad**，不是字墨紧框；
2. **版框/界行/页边黑带/注文残线必须在裁切阶段排除**（pre-cut，D22）；禁止「切进来再擦」；
3. 修复必须**类级**：改码/改数据层后全量重建；禁止单字补丁；禁止 restore/overlay 整字拷贝；
4. 破坏性清理开关（按尺寸/位置删组件）默认关闭，主链启用即 raise（D20）；
5. 不数是孔洞/连通分量（D21）；字形质量由 pre-cut 几何 + 字形级框线闸 + 内容/缺件闸承担。

---

## 3. 选用规则（收谁、不收谁）

### 3.1 只收字头真迹（D15）

- ✅ 收：**2×2 小字格块内的字头大字**（刻本真迹墨迹）；
- ❌ 不收：注文小字（约 1 小字格；源框 max 边 <65px@150dpi 一律视为注文级）、书眉/版心字、版框/界行/页码；
- ❌ 不补：OCR 补字、补假字形、拿小字顶替大字（D15）；当前发布 **17,005 字全部 provenance=real**；
- ❌ 不做「cmap 全覆盖承诺」：D3 的 21,034 全覆盖作废；发布 cmap = 实际真迹字表；
- 字表基准：canonical 正集 **42,302 条 / 唯一基本区 16,567 字**；目标覆盖 **10,267/16,567 = 61.97%**；基本区 **10,267/20,992 = 48.91%**；缺口 **6,300**。

### 3.2 一条 mapping 记录 = 一个字的一次选用

| 字段/规则 | 含义 |
|---|---|
| `char` | Unicode 字符（正典序对应） |
| `page` / `half` | 该字所在的册/页与半版 |
| `box` | 2×2 格块 ∩ content_quad 的 150dpi 框（框面积均匀，见 §1.3） |
| `label_source` | 来源（mapping/修复通道）；所有修复回写 mapping |
| 同块冲突 | 同一 2×2 块被多个字指向时，按类级规则保留 verified ink box 面积最大者，其余删除并写 residual（E23：沓/忠 转缺口） |
| 无法安全定位 | 不硬塞；进 `empty_assign`/隔离清单并披露，不产生字形 |

### 3.3 选用后的质量闸（收了也不算完）

| 闸 | 检查 | 当前 v2.6.2 基线 |
|---|---|---|
| `font_qa` | 表/cmap==manifest/空字形/bbox/advance/同框 | PASS（同框 0） |
| `glyph_frame_gate` | TTF 输出字形扫细长直线（只用线段几何） | 0 PASS |
| `content_loss_gate` | 新旧字形 ink_ratio/IoU（vs v2.5.8） | 18/35（9 字 IoU<0.3，严重度待分桶） |
| `scan_missing_parts` | 源块组件未被字形覆盖（E36 复刻链；E40 修复扫描侧 precut fail-open） | v2.6.2 发布值 165 字/234 组件；**E40 修复后对 v2.6.2 字体重扫 = 19 字/20 组件**（残余 17 prune_loss + 3 scan 残差；owner 判定 prune 删除正确，不改 prune） |
| `scan_frame_escape` | 源图块内贯穿线残留 | 0 |
| `page_geometry_gate` | quad 覆盖/box 坐标/空指派/块∩quad | bad_boxes 0；empty_assign 1,173 |
| `provenance_gate` | manifest/mapping/stats 自洽、无拷贝通道 | PASS |

> 发布前还要人工复核包（01-changes / 02-class-sample / 03-regression-random-100）；「闸 PASS」不等于「可签收」，流程见 `docs/WORKFLOW.md`。

### 3.4 明确不收/不进发布的内容

- 補遺/備考（PDF13）不参与正集字表（`docs/reference/CANONICAL-ORDER.md` §3.6）；
- 总目/检字/卷扉页/部首页标题等非字头内容；
- 空指派半版（v2.6.2 1,173）不产生字形；缺件旧值 165 是 v2.6.2 发布值，E40 修复扫描侧后重扫为 19 字/20 组件（发布记录只读，以 ERRATA E40 为准）；
- 9 个隔离字不进入发布字表；
- 标签错配/无法核实的字：不补假字，按 BF-54 逐字重定位/移出并披露；
- 未修完的已知债不会因「闸阈值」被写成 0；对外一律披露实际值（`docs/releases/v2.6.2/KNOWN-DEBTS.md`）。

---

## 4. 边界与例外（照规则切不出来的情况）

1. **343 页无 content_quad**：走 lattice fallback/裁片外带规则；当前字体无字形落这些页（`docs/PROJECT-STATE.md`）。
2. **卷扉页/部首页**：按 §1.2 的半版规则记账；卷首 R 半版不是正文。
3. **PDF13**：補遺/備考有独立 24 分节（`docs/reference/STRUCTURE.md` §7），不参与正集。
4. **注文/邻墨**：pre-cut + 块掩膜 + clean_ink 远碎片规则处理；**不得**为了干净而扩大成「按形状删组件」。
5. **缺件 165**：v2.6.2 发布值；E40 已定位主因为扫描侧 `precut_masks.apply_precut_masks` 的 `np` NameError 被 `except: pass` 吞掉（crossing 过滤未执行），修复后对同一 v2.6.2 字体重扫 **19 字/20 组件**；残余 17 prune_loss（owner 判 prune 正确、不修）+ 3 scan 残差。**不是字形/cut 规则问题**，见 ERRATA E40。
6. **标签错配**：属 mapping 选用错误，不是切分问题；按 BF-54 逐字证据处理。
7. **D23（提案）**：内容闸判据拟改「源墨保真度」，未定稿前沿用内容闸 18/35 的披露口径。

---

## 5. 规则 → 实现 → 数据 → 验证（对读表）

| 规则 | 实现 | 数据/产物 | 验证 |
|---|---|---|---|
| 半版/阅读序 | `build_page_geometry`、`page_frames.page_gutter` | `page_geometry.jsonl` | `page_geometry_gate` |
| 版框正文区 | `page_frames.detect_content_quads`、`clip_mask_page` | `page_geometry.jsonl`（M/Minv） | `page_geometry_gate`（box in quad） |
| 2×2 格块 | `font_build.block_for_box`、`make_block_mapping` | `mapping_block_v271.jsonl` | `page_geometry_gate`（块∩quad） |
| 只收字头 | D15、`provenance/lead_strict_headwords`（历史）、mapping 选用 | manifest v262（17,005，全 real） | `provenance_gate`、`font_qa` |
| pre-cut | `font_build` + `font_norm` + `precut_masks` + bands | `page_line_bands.json`、`page_geometry.jsonl` | `glyph_frame_gate`、`scan_frame_escape` |
| 归一化 | `font_norm.normalize` | TTF 轮廓 | `font_qa` bbox/EM 检查 |
| 缺件 | `scan_missing_parts`（E36 复刻链；E40 修复扫描侧 precut fail-open） | `missing_scan_v262.jsonl`（v2.6.2）；E40 重扫 19/20 组件 | 缺件扫描（披露阈值；BF-06 仍 open） |
| 内容 | `content_loss_gate` | `content-loss-v258-v262.json` | 内容闸（D23 待定） |

---

## 6. 复算命令（看规则是否真的这样执行）

```bash
# 页几何（半版/quad/lattice）
.venv/bin/python scripts/page_geometry_gate.py --manifest work/font/build/manifest_v262.json \
  --mapping work/lead/mapping_block_v271.jsonl --geometry work/lead/page_geometry.jsonl \
  --stats work/font/build/KangXiKai-v2.6.2.build_stats.json
# 框均匀性/同框/QA
.venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-v2.6.2.ttf \
  --manifest work/font/build/manifest_v262.json --outdir /tmp/qa_layout
# 缺件/框线
.venv/bin/python scripts/scan_missing_parts.py work/font/build/KangXiKai-v2.6.2.ttf \
  work/font/build/manifest_v262.json /tmp/missing_check.jsonl
.venv/bin/python scripts/scan_frame_escape.py --manifest work/font/build/manifest_v262.json \
  --out /tmp/frame_check.jsonl
```

---

## 7. 术语（与 GLOSSARY 一致）

- **半版**：跨页扫描图的 L/R 一半；**字头**：2×2 小字格块的大字；**注文**：正文小字；
- **格点/lattice**：小字格周期与相位；**content_quad**：版框正文区（旋转空间）；**block/框**：2×2 格块∩正文区；
- **pre-cut**：二值化前/掩膜前按几何排除版面；**block mapping**：box=2×2 块∩quad 的字头定位；
- **empty_assign**：有 quad 无 mapping 半版；**隔离字**：不进发布字表、随包说明的字。

> 本文若与代码行为不一致，以 `docs/PIPELINE.md` + 可复算命令为准；发现不一致先记 `docs/ERRATA.md`，再改文档/代码，禁止只改口头。
