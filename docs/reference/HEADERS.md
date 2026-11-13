> **文档状态：数据层参考（非现行管线输入）**。书眉读数/解析用于历史校验（正典序/锚点），现行字体构建不依赖书眉；本文旧「页码 = 2×扫描页−11」已按 D14 标注作废（PDF01–12 葉码 = 扫描页 − 5）。
> 产物文件名更正：早期版写 `work/seq/headers_full_raw.jsonl（历史名 headers_raw.jsonl）` / `headers.jsonl`，实际落盘为 **`headers_full_raw.jsonl`**（全量原始读数）与 **`headers_01_02.jsonl` / `headers_13_probe.jsonl`** 等分册文件；`hdr_page_obs.jsonl` 为统一后的逐页观测。

# HEADERS · 书眉读数（A2）

> 脚本：`scripts/provenance/header_read.py`（单页读数，可跑 `--pdf/--pages/--eval-gold/--workers`）
> \+ `scripts/_archive/header_resolve.py`（序列约束后处理）。产物：`work/seq/headers_full_raw.jsonl`（逐页原始读数）、
> `work/seq/hdr_page_obs.jsonl`（统一逐页观测）、本文件的数字。
> 上游口径：`docs/_history/TAKEOVER.md` §2.D/§5、`docs/DECISIONS.md` D14、`work/t2/margin_labels_full.json`
>（owner 20 页真值）。

## 1. 口径（owner 20 页实证标定）

- 扫描页 = 跨页；**书眉竖排在 L 半版左缘版心**（x≈[页缘, 版框左线]），R 半版右缘被裁不读。
- 字段序（自上而下，固定槽位）：
  `康熙字典`(4 字，左侧常被扫描裁切) → `集名卷`(3 字，如 子集中) → `部名`(部首字+「部」)
  → `画数`(1–2 个字段，每字段=数词+「畫」) → `葉码`(1–3 数字)。
- **书眉画数 = 部外笔画数**；跨分界页有两个画数字段。语义实测（05_0017 目检）：
  **第一字段 = R 半版组、第二字段 = L 半版组**（阅读序每跨页先 R 后 L）。
- **葉码 = 该册内叶序，PDF01–12 实测 葉码 = 扫描页 − 5**（owner 20 页全部自洽：
  0006→一(=1)、0027→廿二、0110→百五、0155→百五(?)、…；每册页码按册内重排）。
  故 01–12 册 leaf_no 用公式给（高置信），13 册按分节另读。
- **集名以刻本版心为准，且与数据集集卷划分一致**：A2b 已逐卷读 36 个刻本卷扉页，
  12 集×上中下的卷↔部首映射与数据集 path 集名划分 **100% 一致**（214 部首各归一卷，
  见 `docs/reference/STRUCTURE.md`）。本文件 §4 旧记录中「03_0015=山部」为目检误读，实为 **宀部**
  （宀∈寅集上，与数据集一致；owner「卜部?」亦误），已更正。集名卷仍建议由册号（子…亥）+
  `work/lead/page_roles.jsonl` 的 body 段（上/中/下）给出；PDF13 按「補遺 12 节 → 備考 12 节」定节。

## 2. 方法

1. `fitz` clip 300dpi 渲染左缘条（宽 40pt，全页高），本地中值背景归一化 + 去长竖/横线。
2. **版心列带定位**：版框左竖线（x 65–135 内竖墨段）右界；行块粗切后按墨迹 x 范围聚类，
   取块数最多且 x 范围一致的簇为内容列（解决 01_0027 这类左边距偏移页：内容列在 x≈55–93，
   而康熙字典四字更左且被裁）。康熙字典四字与顶部墨污不参与解析。
3. **切字格**：行投影 + 同字碎片合并（缝≤2 且高≤100，或 缝≤34 且高≤74）。
4. **OCR**：PaddleOCR `PP-OCRv5_server_rec` 单字格识别（批量）。
5. **解析**：以「集」「部」OCR 为锚点；集名卷由卷号+卷界给出（只校验）；部名取「上/中/下」
   与「部」之间整段墨迹合并 OCR（防「山」类碎字）；画数以「畫」字为字段界（OCR + 笔画
   几何双票：畫 h≥73, w≥70, 竖画带≥2, 墨率≥0.20）；数词用 OCR + 扁平数词笔画几何
   （一/二/三/十/廿/卅 的横竖带计数）；葉码 01–12 用页−5 公式、13 用尾巴段整段 OCR。
6. **序列约束后处理**（`header_resolve.py`）：部名 214 部首序单调 DP（发射=OCR 命中，
   允许跳 1–3 部罚分）；画数每部内单调 DP（状态 0–44，双字段页第一字段=上一页 L 组约束，
   发射权重视读数来源：ocr 2.8 / region 1.2 / flat 0.4）；集名卷如上；葉码公式。

## 3. 产物与格式

`work/seq/hdr_page_obs.jsonl`（每页一行；全量 3,869 页，R 半版不输出）：
```json
{"page":"05_0017","half":"L","ji":"辰集上","bu":"日部","hua":[5,6],"hua_l":6,
 "leaf_no":12,"conf":0.93,"errors":[],"section":"zheng"}
```
- `page` = `NN_NNNN`（NN=册号 00–13，NNNN=该册内扫描页号=fitz 索引+1）。
- `bu` 带「部」；`hua` 为 int 数组（1 或 2 个，语义见 §1.3/1.4）；`hua_l`=该页 L 半版组。
- `leaf_no` = 叶码（01–12 由页−5 公式；13 由读数，可能 null）；`conf`=0–1；`errors`=诊断码
  （`no_ji`/`no_bu`/`ji_char_unread`/`rad_unread`/`suffix_unread`/`no_after` 等）。
- `work/seq/headers_full_raw.jsonl（历史名 headers_raw.jsonl）` 另含逐页 cells（y0/y1/OCR text/score）与 `hua_basis`
  （读数来源），供复核。

## 4. 当前准确率（owner 20 页真值逐项对照）

> 对照真值 `work/t2/margin_labels_full.json`；**owner 真值有 2 处经目检确认的疑误**，
> 下表按刻本原字校正后计：
> - `03_0015`：版心实为「寅集上·**宀**部·二畫」（owner 记「卜部?」；此前把部首字「宀」误读为「山」，
>   经 A2b 卷扉页结构（宀部∈寅集上）+ 300dpi 放大已更正）；
> - `04_0017`：画数实为「**五**畫」（owner 记「六畫?」；刻本字形三横一竖为「五」）。

**原始读数（未做序列修正，`headers_raw.jsonl`）**：

| 字段 | 对/总 | 备注 |
|---|---|---|
| 集名卷 | **19/20** | 唯一失败 01_0027：版心顶部墨污+左边距偏移页，切格碎（该页 ji 可由卷界确定 = 子集上） |
| 部名 | **15/19** | 失败多为碎字/低分（03_0015 宀→无、03_0027 宀→误、01_0006 一扁平、01_0027 无锚点） |
| 画数 | **11/18** | 失败类型：数字粘连（十二→士/11）、扁平数词碎片、六→大一横（08_0020） |
| 葉码（页−5 公式） | **17/18** | 唯一未过是 13_0163（13 册分节页码，不适用册内页−5） |

**序列修正后（`headers.jsonl`，全量跑批后回填本节最终数字）**：
- 集名卷：由卷界给出 → 01–12 册确定性；13 册单调 DP。
- 部名：214 部首单调 DP（全量约束）→ 待回填。
- 画数：部内单调 DP → 待回填。
- 葉码：01–12 公式 → 3,691 页确定性；13 册读数可能 null。

## 5. 失败类型与下一步

1. **版心顶部墨污/印章/鱼尾**（01_0027 类）：行块聚类+簇选已挡大部分；残余页用「集」
   锚点存在性判低置信 → 交给序列 DP/卷界补。
2. **数字粘连**（「十+二」印刷近贴，gap 2–34px）：多档碎片合并 + 扁平笔画几何可解一部分；
   残余（如 05_0030 十二→11、04_0030 六→16）留待「画数部内单调 DP」修正。
3. **碎字**（山/川/口/一 等字内分离）：部名改为整段合并 OCR 后显著改善；残余低置信→null。
4. **13 册（補遺/備考）**：书眉无部名/画数，只有集名+叶码；集名节序按「補遺 12 节→備考
   12 节」单调 DP，叶码用尾巴段 OCR（低置信，页码无公式）。
5. **下一步（下一会话）**：
   a) 版心柱按 Lead 建议取 [页缘, 版心第一根竖线]（本版已实现动态列带，但 01_0027 类
      仍需按竖线位置硬裁）→ 应可把集名原始读数拉到 20/20；
   b) 部名/畫/数字改用**刻本自建模板匹配**（从本批高置信字格收集模板，楷体模板 + NCC），
      预期部名 ≥95%、画数 ≥99%（Lead 判断）；
   c) 画数双字段页语义（R 组/L 组）在 solver 里按 hua[-1] 校验；
   d) 补遺/備考叶码：需先定 PDF13 分节页界（page_roles 的 title_page 段）再核。

## 6. 复现

```bash
# 单页/区间
.venv/bin/python scripts/provenance/header_read.py --pdf 05 --pages 17 --out work/seq/x.jsonl
# owner 20 页自带对账
.venv/bin/python scripts/provenance/header_read.py --eval-gold --out work/seq/headers_pilot_raw.jsonl
# 全量（8 进程，约 10–15 分钟）
.venv/bin/python scripts/provenance/header_read.py --workers 8 --out work/seq/headers_full_raw.jsonl（历史名 headers_raw.jsonl）
# 序列约束 → solver 口径
.venv/bin/python scripts/_archive/header_resolve.py --raw work/seq/headers_full_raw.jsonl（历史名 headers_raw.jsonl） \
    --out work/seq/hdr_page_obs.jsonl（历史名 headers.jsonl） --eval-gold
```

依赖：`.venv`（paddleocr 3.7 / PP-OCRv5_server_rec 已缓存；fitz/opencv/numpy），不新增依赖；
不写 `.venv`。并发 ≤8 进程、每进程 OMP/MKL=1。

## 7. 本轮未完成（2026-11-08 收口记录）

### 7.1 覆盖与全量进度
- 本轮 raw 实跑覆盖：**500 页 = PDF01 全 242 页 + PDF02 全 258 页**（其余 3,369 页未跑）。
  产物 `work/seq/headers_raw_partial.jsonl`（500 行）→ resolver 后 `work/seq/headers_partial.jsonl`
  （500 行，含非正文页 null 占位）+ `headers_lowconf.jsonl`（307 行低置信/含错误码）。
- 全量命令已就绪：`.venv/bin/python scripts/provenance/header_read.py --workers 8 --out work/seq/headers_full_raw.jsonl（历史名 headers_raw.jsonl）`
  预计 **10–15 分钟**（8 进程、约 1.2 s/页/进程）。本轮最后一次全量跑在合并阶段因 worker 返回
  None 的排序 bug 崩溃（已完成全部页面但未落盘）；**该 bug 已修**（None 过滤 + 每 worker 增量
  写 `work/seq/parts/`（历史中间分片目录），崩溃也不丢已完成页段）。
- 本轮 partial 的 resolved 数字（raw 直读，未做全量序列修正）：
  ji 451/500（非正文页 null）、bu 376/500、hua 346/500、leaf 490/500；
  owner 页在 01–02 册内的 5 页对账：集名 5/5、部名 3/5、画数 2/4、叶码 3/3。

### 7.2 pilot（owner 20 页）数字汇总
| 字段 | raw 读数（`headers_pilot_raw.jsonl`） | 说明 |
|---|---|---|
| 集名卷 | 19/20 | 失败 01_0027（版心顶部墨污/左边距偏移）；该页集名可由卷界确定 |
| 部名 | 15/19 | 失败：01_0006(一,扁平)/01_0027(无锚点)/03_0015(宀,碎字)/03_0027(宀误) |
| 画数 | 11/18 | 失败：数字粘连（十二→11/16）、六→大(08_0020) |
| 葉码 | 17/18 | 01–12 册页−5 公式；13 册不适用 |

owner 真值经目检校正 2 处：03_0015 部名实为「宀」（owner「卜部?」；数据集集名 寅集上 亦一致），04_0017 画数实为「五畫」
（owner「六畫?」）。

### 7.3 「resolved 输出 bu 全回退成一部」问题（下一会话先修）
- 现象：本轮早期 `headers_pilot_resolved.jsonl` 里 bu 全部 = 一部。**不是读取 bug**，是
  `header_resolve.py` 的全书部名单调 DP 在**只有 20 个离散页**输入时退化（无连续页约束，
  单调 DP 选择停在首状态）。
- 已加护栏：raw 行数 < 3,000 时不做部名单调 DP（直接用 raw 读取），≥3,000（全量）才做 DP；
  同时画数 DP 同样只对全量启用（partial 用 raw）。因此 `headers_partial.jsonl` 的 bu/hua 是
  诚实直读值，不再出现全 一部。
- 全量跑完后仍需验证部名 DP 在 3,541 正集页上的效果（预期显著优于 raw 15/19）。

### 7.4 下一会话 P0（按 Lead handoff 建议）
1. **楷体模板匹配 + 固定槽位**替代 PP-OCR 主识别：从本轮 500 页高置信字格收集刻本模板
   （部名/畫/数字/集名字），NCC 匹配；PP-OCR 只作第二票。目标：画数 ≥99%、部名 ≥95%，
   owner 20 页 100%。
2. 固定槽位解析（康熙字典4 → 集名卷3 → 部名2 → 画数1–2 + 葉码1–3），槽位由「集/部/畫」
   三锚点定，不再自由切格。
3. 版心柱硬裁：[页缘, 第一根竖版框线]，解决 01_0027 类偏移页。
4. 全量 3,869 页 + 部名/画数序列 DP + 低置信清单，交 solver。
