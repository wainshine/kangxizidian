# SESSION-HANDOFF · 2026-11-08 接手会话后交接

> **新会话第一步：读本文件 → `docs/TAKEOVER.md`（诊断+v3架构）→ `docs/V3-STATUS.md`（成果/卡点/数字）。
> 本文件取代 2026-11-08 晚 GLM 版交接；旧 T2 路线（DP 对齐 + 所有者逐页读数）已作废。**

## 1. 一句话状态

v3「结构性标注」架构已被实证打通到框级（0006-0009：11 条框↔条目 11/11 正确，3 个书眉校验点 0 不一致），
全量数据/工具就位（正典序 42,302 条、全 3,869 页页角色、全 12 卷 3,266 body 页候选检测、
32 字 demo 字体可安装 && 可复现）。**当前唯一阻塞：书眉（版心）读数识别未过门 →
无法在全量范围做逐页校验/纠错 → 全量标注与全量字体未产出。**

## 2. 下一会话第一优先级（按序，每步有门）

### P0 书眉读数（0.5 天，**先做这个**）
- 输入：`work/lead/page_roles.jsonl`（只读 body 页，3,528 页）；`work/t2/margin_labels_full.json`（owner 20 页真值）
- 目标：每页 (部名, 画数[1-2 字段])，全量覆盖 ≥85%，对 owner 20 页 **集名/部名/画数 100%**
- 已知可行路径（本会话试错结论）：
  1. **版心柱**：L 半版左缘 → 第一根竖版框线（300dpi 下见 §4 几何）；按页自适应，不要写死 167 宽（会带进正文列）
  2. **切格**：水平投影，小间隙合并；宽格按竖直投影拆（十+二 粘连）
  3. **识别**：楷体模板匹配（`~/Library/Fonts/GuanGeKai-Regular.ttf`）优于 PP-OCR（PP-OCRv5 对刻本楷体 misread 严重：pilot 20 页 集名 19/20、部名 15/19、画数 11/18 未过门；且 resolved 的 bu 全回退「一部」是 bug）
     - 关键字符集小：214 部首 + 数字（一二三四五六七八九十廿卅卌百）+ 部/畫 + 康熙字典/集名
     - 固定槽位解析：康熙字典(4) / 集名卷(3) / 部名(2) / 画数(1-2 字段) / 葉码(1-3)
     - 集名卷**不用识别**：`work/lead/volume_sections.json` 卷界表直接给；葉码=册内扫描页−5（PDF01-12 实测）
  4. **只识别画数也能用**：画数字段 + 预测组（来自计数累计）比对即可做校验点（部名可选；部变化时预测也会跟着变）
- 备选：只识别「畫」+ 数字（不识别部名），solver 用 `hua_only` 模式（bu=null → 只校验 bu_strokes 集合）
- 输出格式（solver 已支持）：`work/seq/headers.jsonl`，每行
  `{"page":"01_0006","half":"L","ji":"子集上","bu":"一部","hua":[1,2],"leaf_no":1,"conf":0.9,"errors":[]}`

### P1 计数偏差三方对账（0.5 天，依赖 P0 可用）
- 现象：检测器 `count_headword`（argmax=headword 且分≥0.8）全卷合计比正典序少 **~10%**
  （vol01 2374/2633、vol02 2564/2901、vol03 2337/2597）；但 0006-0009 八半版与 truth 完全一致。
- 已知解释一部分：正典序重出/异体重复条目占 3.4-3.8%（子集 90/丑集 110/寅集 68 条）——需确认是否应计入。
- 剩余 6-8% 必须判定：①检测漏计 ②正典序含未印条目 ③边界页归属
  - 做法：用 P0 headers 跑 `scripts/lead_solver2.py`，取首个 mismatch 窗口（≤2 页）→ 人工三方对账
    （detector 候选 vs 人工目检 vs 正典序 kx 切片），结论写 `docs/COUNT-RECONCILE.md`
  - 注意方向：计数偏差有正有负（子集上 6-41 页检测 246 vs 正典 176 = 超计 40%；全卷却是少计）→ 不能全局缩放

### P2 全量映射（依赖 P0+P1）
```bash
.venv/bin/python scripts/lead_solver2.py \
  --canonical work/seq/canonical.jsonl --groups work/seq/groups.json \
  --boxes-dir work/lead/boxes300 --headers work/seq/headers.jsonl \
  --roles work/lead/page_roles.jsonl --out work/map/full
```
- 门：每卷 headers 一致性 ≥95%；卷末 consumed == 正典该卷累计；mismatch 窗口人工清完
- mapping 格式：每行 `{page,half,assigned:[{char,cand:{box}}]}`（box=150dpi 页坐标，直接喂 font_build）

### P3 全量字形 + 字体
```bash
.venv/bin/python scripts/lead_extract.py --mapping work/map/full/mapping.jsonl   # → work/glyphs/
.venv/bin/python scripts/font_build.py --mapping work/map/full/mapping.jsonl \
   --out work/font/build/KangXiKai-v0.1.0.ttf                                   # 32 字 demo 同链路
```
- 目标：16,567 个基本区真迹字（正集 unique 基本区；另有 224 个仅见補遺/備考，暂缓）
- 缺 4,201 个基本区码位：mapped_traditional（~2,175 经 Unihan kTraditionalVariant）+ ribbon 回落 + 披露；
  補遺/備考 6,406 条、GAN 后置（D3/D4 口径不变）

## 3. 本会话交付（详见 docs/V3-STATUS.md §2）

demo 字体 `work/font/demo/KangXiKai-demo-v0.1.0.ttf`（32 字，sha256 两次一致）；
正典序 `work/seq/canonical.jsonl`（seq 正式版）/ `work/lead/canonical_proto.jsonl`（Lead 原型）；
页角色/卷界表；检测器 v2 + 全量检测（`work/lead/boxes300/` 3,266 页）/ 候选 234k；
solver/extractor/review 工具；文档 TAKEOVER/V3-STATUS/DETECTOR-V2/FONT-BUILD/VENDORED/HEADERS(seq)。

## 4. 关键技术事实（违反即返工）

1. **书序真源 = Unihan kKangXi (page,position)**；数据集序不是书序（05_0017 实证）。旧 `t2_dpalign*` 结论全部作废。
2. **阅读序**：每跨页先 R 后 L；版内列右→左、列内上→下。R 半版无书眉（被裁），书眉在 L 半版左缘。
3. **重出行计入**（书上印两次，第二次注文常「【集韻】同，上」）；**古文大字变体不计入**（弌/𠆤/弎 等，前方有小字「古文」标签）。
4. **页面几何**：1 PDF 页 = 跨页; L 半版 版心柱 ≈ 页左缘~第一竖框线（300dpi 下 x≈[4,~90]，页页浮动）；
   书眉字段自上而下（见 P0）；正文列距 ~47px@150；注文小字 h0=37px@150；字头 ~2.08×h0。
5. **体例**：每卷卷界有 7-8 页非正文（集扉页/书衣/空白）；`page_roles.jsonl` 已分类（body 3,528）。
6. **检测**：必须 `--dpi 300` + render_dpi=**150**（直渲染）；300→150 降采样路径会让分类分漂移（0007/0009 实测计数出错）。
7. **坐标**：所有 box 统一 150dpi 当量页坐标；字形裁切时 ×2 渲染 300dpi。
8. **数据集/旧标签可靠性**：`work/t2/dp_alignment*.json` 除 owner 明确逐框确认外不可信（本会话又抓一例：
   「時」框实为「晋」）；gold50.json 无 char 字段（切格金标）；t2_review_ids 标签 24/25 错。
9. 硬约束沿用 PROMPT §6：不做 git 写操作；大文件只进 work/；并发 ≤10；术語刻本体例。
10. 本会话环境事实：`.venv/bin/python` 3.12；fontTools/potracer 装在 `work/font/_pylibs`；
    PaddleOCR 可用但刻本楷体识别差；`~/Library/Fonts/GuanGeKai-Regular.ttf` 可作楷体模板。

## 5. 所有者（用户）沟通备注

- 所有者读刻本强；但**本方案已不再要求逐页读数**——只在 P1 收尾时抽 10-20 个计数不一致窗口做终审。
- 本会话已用目检目视核实：0006-0009 逐半版字头序列；05_0017 书序；世/時 重出；丁+古文𠆤；一+古文弌。
- 所有者倾向：方向对就推进、关键节点落文档、git 由所有者操作。
- **文档权威顺序**（冲突时）：`DECISIONS.md` > `TAKEOVER.md` > `V3-STATUS.md` > 本文件 > `PROMPT.md`（历史）。
