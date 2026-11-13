# PIPELINE · 现行管线架构 / 原理 / 流程（v2.6.2 候选，2026-11-13）

> 本文是**唯一现行管线说明**。旧文档状态：`FONT-BUILD.md` 的 §0–§11 是 demo 阶段（已过期），`TAKEOVER.md`/`V3-STATUS.md` 是历史编年。
> 本文与 `docs/WORKFLOW.md`（流程纪律）、`docs/DECISIONS.md`（口径决策）、`docs/VERSION-HISTORY.md`（逐版变更）配套。

---

## 0. 一句话

**PDF 页面 → 页级几何（格点/正文区）→ 字头 mapping（框=2×2 格块）→ 裁切阶段排除版框/邻墨 → 矢量化 + 归一化 → TTF → 自动闸 + 人工复核 → 里程碑发布。**

当前基线：**v2.6.2 正式发布候选**（E37 后，sha `a8bb87d9…`），17,005 字形，基本区 10,267 = 48.91%（目标表 61.97%，缺口 6,300）；fast_gate **8/8 PASS**；全闸 **9 PASS / 2 FAIL**（缺件 165、empty_assign 1,173，均为披露已知债）。

---

## 1. 目标与不可违反的约束

| # | 约束 | 来源 |
|---|---|---|
| 1 | **只收字头真迹**（headword-only），不收注文小字；不补假字形 | D15 |
| 2 | 字头 = **2×2 小字格块**；框面积由排版决定，同页应几乎一致 | owner |
| 3 | **版框线/页边黑带/界行在裁切阶段排除**，严禁「切进来再擦」 | owner |
| 4 | **同类问题类级修**，不按单字打补丁；禁止 restore/overlay 整字拷贝 | owner / 审计 |
| 5 | 数字必须来自闸输出（可复算）；没有证据的结论不写 | 流程 |
| 6 | 正式包必须来自 **clean git tree**，SHA 覆盖 gate-report，finalize 后不改包 | 流程 |
| 7 | 只有里程碑发正式包；候选 `cYYYYMMDD-n` 不进 release/ | WORKFLOW |

---

## 2. 数据与坐标约定

| 项 | 约定 |
|---|---|
| 扫描件 | `康熙字典/康熙字典.NN.*.pdf`（**14 个 PDF：00 总目/检字 + 01–12 正文 + 13 补遗/备考**，3,869 页）；`work/t2/pdf_map.json`：卷号 `01..13` → 文件名 |
| 页 key | `NN_PPPP`（如 `02_0074`） |
| 一页 = 跨页 | 左/右半版 `L`/`R`；gutter 由列投影取 42–58% 区间最小值定位 |
| 坐标 dpi | **150dpi 坐标系**（lattice/box/manifest 全部用它）；渲染裁片用 **300dpi**（`dpi_scale=2.0`） |
| 字框 box | `[x0,y0,x1,y1]` @150dpi，`(x0,y0)` 左上 |
| 产物根 | `work/`（不入 git，见 `docs/WORK-MAP.md`）；发布物 `release/` |

---

## 3. 管线总览（四层 + 两闸）

```
12 PDF (3869 页)
   │  S0 页面角色（body 页 3,266 / 卷首 / 目录 / 牌记 …）      scripts/_archive/lead_page_roles.py（已归档，产物 work/lead/page_roles.jsonl）, t1 detector(冻结)
   ▼
S1 页级几何 G（每页一次，缓存）                                  scripts/build_page_geometry.py
   lattice: 小字格点 (px,py,phx,phy)（每半版）                  → work/lead/page_geometry.jsonl
   text_bbox / content_quad(版框正文区, 含旋转 M/Minv)             3,869 行；3,526 页有 quad
   ▼
S2 字头 mapping M（单一真源）                                   work/lead/mapping_verified_all33.jsonl
   正典序 → 页面半版 → box；修复（扩框/重定位）回写 mapping      → mapping_block_v270.jsonl（box=2×2 块∩正文区）
   ▼
S3 字形构建 F（脏集增量；cache key = geometry×box×算法 tag）    scripts/font_build.py + scripts/font_norm.py
   每字：300dpi 渲染 → 二值化 → content clip → 裁片框线排除
        → 2×2 块掩膜 → 主簇清理 → 2× 描迹 → 归一化(长边760)     → work/font/build/KangXiKai-v<ver>.ttf
   ▼
C 候选（字体 + 快闸 + 人工复核包，不打包）                       docs/WORKFLOW.md
   ├─ L1 快闸 fast_gate（QA/版本/字符diff/内容闸/box均匀性/文档/SHA，≤3min）
   └─ L2 全闸 full_gate（缺件/框线/几何校验/映射审计，仅在里程碑前）
   ▼
R 正式包（里程碑）                                               scripts/font_package.py + scripts/release_gate.py
   字体 + manifest/provenance/coverage/QA + gate-report + 明细
   + build_recipe(git commit/算法版本) + SHA256SUMS + zip（SHA 覆盖报告，finalize 后不改）
```

---

## 4. 分阶段详解

### S1 页级几何（`scripts/build_page_geometry.py`，10 workers，一次性 10–13 分钟）

- **lattice 拟合**：小字组件中心（h 24–54, w 9–60, area 40–1200）→ 对 x/y 分别拟合周期 `(px,py)` 与相位 `(phx,phy)`；输出每半版 `(px,py,phx,phy)`；
- **text_bbox**：正文墨迹 bbox 内缩 5px（版框外沿≈bbox）；
- **content_quad（版框正文区）**：`scripts/page_frames.py`
  1) Hough 长线估计页面微旋转 θ（本批 0.2–0.4°），旋转校正；
  2) 近轴（±2.5°）线段聚类，得竖线簇 x / 横线簇 y；
  3) 每半版取「靠边但最靠内」的框线簇作为版框内边界，再内缩 4px；
  4) 小字 bbox ±60px 兜底、页边黑带钳制、框线缺失侧用 lattice 兜底（`fallback_quad_from_lattice`）；
  5) 保留旋转矩阵 `M/Minv`，供裁切时把 150dpi 点映射到旋转空间；
- 产物：`work/lead/page_geometry.jsonl`（3,869 行；3,526 页有 content_quad；343 页无 quad → 走兜底/裁片外带规则）。

### S2 字头 mapping（`work/lead/mapping_block_v270.jsonl`）

- 正典序 `work/seq/canonical.jsonl` → 42,302 条 → 3,266 body 页定位 → `mapping_verified_all33.jsonl`（5,695 页半版、17,007 字）→ block mapping v271（17,005 字，同块 2 对已清 E23）；
- **box = 2×2 格块 ∩ content_quad**（`scripts/make_block_mapping.py`；v271 起 mapping 带 verified_box 字段，仅实验通道用）：
  `block_for_box(lat, box)` 由字框中心取 2×2 格（半格偏移 + 3px 余量），再与 content_quad 求交；
- 结果：框宽 p5/p50/p95 = 99/102/103，框高 95/98/100（同页 σ≈0.4px）——面积口径与排版一致；
- **单一真源**：修复（缺件扩框/切偏重选）必须回写到 mapping，不再用 overlay/restore 把旧字形拷回（v2.6.0 的 375 字 restore 已废弃）。

### S3 字形构建（`scripts/font_build.py` → `scripts/font_norm.py`）

每字流程（`vectorize_box`）：

1. **渲染**：PDF 300dpi 直渲染 box+pad（`render_pdf_crop`，pad 150dpi 6px；若触边自动加大 pad 重渲一次）；
2. **二值化**：中值背景相减（`binarize`）；
3. **切前排除（核心）**：
   - `content_quad`（唯一来源：`font_build.get_page_content_quads`，含页级缓存与 lattice fallback）→ `clip_mask_page`：**二值化后、掩膜前**把版框正文区外的像素置零（框线/黑带/角部楔形从不进入后续掩膜）；
   - `trim_crop_frame_edges`：裁片外带若出现贯穿长线，把该边整条裁掉（只动外带）；
   - `strip_crop_frame_bands`：删除贯穿裁片边界、触到两侧的整行/整列墨带（字形笔画不会触到裁片两侧）；
   - **E37 细线 crossing 过滤**（`font_norm._filter_line_mask_to_crossing`）：页级直线 mask 组件只有
     「贴/穿 2×2 块边界」时才删；完全落在块内的细长组件视为字身笔画（頁/言/辰 类细横）保留；
   - **E37 线条带解耦**：已验证的页级线条带（`page_line_bands.json`）作为 `frame_mask_extra`
     无条件应用，不受 crossing 过滤影响（26→27 rect，新增 萩）；
4. **2×2 块掩膜**：只保留该字 2×2 格块内墨（块外邻字/注文丢弃，3px 余量）；
5. **主簇清理**（`clean_ink`）：取最大主组件及邻近组件，去孤立碎片/贴边残片；`enable_edge_strip=False`（危险开关默认关）；
   **E37 碎片规则**：非主体、面积 <5% 主体、距主体 bbox >15px 的孤立成分剔除（注文/邻墨残笔）；
6. **描迹**：2× 超采样（避免描迹偏移），得轮廓；
7. **归一化**：以**字墨 bbox（全部轮廓的像素包围盒）**为基准，最长边 → **760 font units**，bbox 中心映射到 (500,400)；EM=1000（v2.6 起口径；旧文档写「按 box 边距对齐」是 v2.5 旧行为，见 BUILD-12）；
8. **轮廓整理**：`orient_contours`（方向/回字规则）、prune 短轮廓；
9. **cache**：key = `<自动缓存版本>_<page><half>_<char>_<box>`（版本 = 算法脚本 sha8 + geometry sha12 + **page_line_bands sha12**，人工 tag 已废）；未变字直接命中。

构建参数：`FONT_BUILD_WORKERS=10`；17,005 字全量约 **10m30s**（含页级 pre-cut mask；无 mask 记录见 E22）；旧人工 tag 缓存已不参与。

### S4 闸（自动验证）

| 闸 | 脚本 | 判据/口径 | 当前基线 |
|---|---|---|---|
| 字体 QA | `font_qa.py` | 表/cmap==manifest/空字形/bbox(tiny,超 em)/advance/fontRevision/同框=0；**不数孔洞/连通分量**（D21） | **PASS**（同框 0） |
| 内容缺失 | `content_loss_gate.py` | 新旧字形 ink_ratio/IoU（vs v2.5.8；跨架构归一化差异见 E31/D23） | **18**（阈值 35；D23 判据待定） |
| 缺件扫描 | `scan_missing_parts.py` | 源块组件未被字形覆盖；**复刻构建最终墨迹链配准**（E36：build_stats pad / block mask / clean_cluster+clean_ink box 口径 / fin_frac≥0.6；参考字体=霞鹜文楷 OFL；E37 起 pre-cut 与构建同口径 crossing 过滤） | **165**（E37 后：恢复的细笔画被 `prune_edge_contours` 边缘清理；旧 32/827/1,200 不可比） |
| 框线逃逸（源图级） | `scan_frame_escape.py` | 块内贯穿线残留（同 pre-cut 口径 E32/E33；E37 起厚度 ≤3px@300 亚像素线不计） | **0 PASS**（E37 口径；旧 153/158/43/1 均为历史） |
| 字形级框线闸 | `glyph_frame_gate.py` | 扫 **TTF 输出字形**：细长直线（厚≤3px@256、长≥max(0.5 字宽,128px)）；只用线段几何，不数孔洞（D21） | **0 PASS**（E24/E27/E29/E37） |
| 无拷贝 provenance 闸 | `provenance_gate.py` | manifest/mapping/stats 三者自洽；`label_source=="mapping"`；无 `__overlay__`/`repair_overlay`/`contours_override` 标记 | v2.6.1 PASS（同框 2 对为 warning） |
| 页级几何闸 | `page_geometry_gate.py` | 有 quad 覆盖/manifest box 用 `M` 变换进旋转空间/bad box/空指派半版/2×2 块∩quad | bad_boxes **0**（E30）、空指派半版 **1,173**（唯一严格 FAIL；01_0006 L 含「一」） |
| 快闸 | `fast_gate.py` | QA/版本/字符diff+隔离/内容(binding 复用)/box 均匀/字形框线/provenance/页几何；缺参数即 FAIL | **8/8 PASS**（候选；页几何用已披露阈值） |
| 全闸（候选基线） | `release_gate.py` | 上述 + 缺件/框线扫描（finalize 强制）+ 三闸严格 0 + **包内 TTF sha == --font** + clean-tree + 输入归因 + SHA + zip；**pre-finalize 失败绝不改包** | **9 PASS / 2 FAIL**：缺件 165、empty_assign 1,173（披露已知债；可通过 `--scan-max-flagged/--page-geometry-max-empty-assign` 显式披露） |

- **扫描/闸结果绑定**：输出旁写 `<out>.sha256` sidecar（输入 font/manifest/mapping/geometry/参考字体/脚本 sha + argv + git）；复用前必须校验，输入或脚本变化即 FAIL（BF-12）。内容闸缓存 `work/gates/<font_sha12>/` 同样有 sidecar。
- `jobrun.sh` 包装后台任务：写 `work/jobs/<name>.status`（START/DONE/KILLED/FAILED + EXIT），pipefail 不再被 `| tail` 掩盖。

### S5 打包与发布

- `font_package.py`：**freshness**（字体须比 manifest 新）+ **clean-tree**（工作区必须干净，否则 ABORT；调试可 `--allow-dirty`）+ QA + 材料 + SHA + zip；
- `release_gate.py`：全部步骤 PASS 才写 gate-report → 重算 SHA（覆盖含报告）→ 终校验 → zip 自检；失败只写 `work/lead` 报告、**不动包**；finalize 前强制 clean git tree + 缺件/框线扫描 + 内容基线；
- `build_recipe.json` 记录 **git commit / dirty / cache tag / 算法脚本 sha / 扫描数字**，保证可复现；
- 正式包**只在里程碑**发（`docs/WORKFLOW.md` §7）；候选只给字体+复核包+快闸。

---

## 5. 不变量（改代码前先看）

1. **框 = 2×2 格块 ∩ content**，面积必须均匀；不要退回「字内墨迹紧框」。
2. **mapping 是唯一真源**；修复回写 mapping，禁止 overlay/restore 拷贝旧字形。
3. **版框类只在裁切阶段排除**；主链不做「按形状删框线」的补救。
4. 闸阈值只允许逐版收紧；放宽必须在包内报告写明原因并经 owner 同意。
5. cache key 必须含几何/mapping/box/算法版本；只重建脏集。
6. 无证据不写数字；每次变更追加 `docs/VERSION-HISTORY.md` + `work/changesets/`。

---

## 6. 复现命令

```bash
# 0) 一次性：页级几何（10 workers）
.venv/bin/python scripts/build_page_geometry.py

# 1) block mapping（box=2×2 块∩正文区，8 workers）
.venv/bin/python scripts/make_block_mapping.py \
  --mapping work/lead/mapping_verified_all33.jsonl \
  --out work/lead/mapping_block_v270.jsonl --workers 8

# 2) 全量重建（10 workers；缓存 tag 变更即全量）
FONT_BUILD_WORKERS=10 .venv/bin/python scripts/font_build.py \
  --mapping work/lead/mapping_block_v270.jsonl \
  --out work/font/build/KangXiKai-v2.6.1.ttf --version 2.6.1

# 3) 快闸（≤3 分钟；每次候选）
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.1.ttf \
  --manifest work/font/build/manifest_v261.json --version 2.6.1 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json \
  --pkg-dir release/KangXiKai-v2.6.1 --content-max-damaged 35

# 4) 全闸 + finalize（里程碑前；可用已有扫描结果复用）
.venv/bin/python scripts/release_gate.py --version 2.6.1 \
  --font work/font/build/KangXiKai-v2.6.1.ttf --manifest work/font/build/manifest_v261.json \
  --prev work/font/build/KangXiKai-v2.5.8.ttf --prev-manifest work/font/build/manifest_v258.json \
  --pkg-dir release/KangXiKai-v2.6.1 --zip release/KangXiKai-v2.6.1.zip \
  --scan --frame-scan --content-max-damaged 35 --tag v261
```

---

## 7. 当前数字（v2.6.1，可复算）

| 项 | 值 |
|---|---|
| 字形数 | **17,005**（headword-only 真迹；同块冲突剔除 沓/忠，E23） |
| 基本区覆盖 | 10,267 / 20,992 = **48.91%**；目标字表 10,267 / 16,567 = **61.97%** |
| 缺口 | **6,300**（其中高频 23 + 忠 待重新定位） |
| 隔离 | 9（刃/榍/法/紆/総/荹/仟/禦/絞） |
| 全量构建 | 17,005 字 / **402s**（无页 mask）/ **634s**（含页级 pre-cut mask，最新）；缓存命中 **232s**（10 workers） |
| 闸（v2.6.2 候选，E37 后） | font_qa **PASS**（同框 0）；字形级框线 **0**；框线逃逸 **0**；内容 **18**（阈值 35）；provenance PASS；页级几何 bad_boxes 0 / empty_assign 1,173；缺件 **165**（prune 边缘口径）；fast_gate **8/8** |
| 已知结构债 | 343 页无 content_quad；缺件扫描邻字隔离待修正；页级几何按页修；09–11/13 卷锚点；100 字签核 |

---

## 8. 失败模式与教训（不要再踩）

| 失败模式 | 现象 | 现行对策 |
|---|---|---|
| 切后擦框线 | 反复回归（嗃/勤） | 切前排除（content clip + 裁片外带规则） |
| restore/overlay 整字拷贝 | 旧框线回流、双真源 | 删除该层；修复回写 mapping |
| 门禁盲区 | v2.6.0 带坏字形 9/9 PASS | 必须加字形级/几何级闸；数字来自闸输出 |
| 墨迹紧框 | 面积不一致、左大右漏 | block mapping（框=2×2 块） |
| 小修重跑全库扫描 | 27 分钟/次、发版失效 | 闸分层 + 按字体 SHA 复用 + 脏集重建 |
| `| tail` 吞退出码 | 失败显示成功 | jobrun + pipefail + status 标记 |
| 未提交代码打包 | hash 不可复现 | clean-tree 打包闸 + build_recipe 记录 commit |
