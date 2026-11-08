# CANONICAL-ORDER · 正典阅读序 + 组表（A1 正式版）

> 复算：`.venv/bin/python scripts/seq_order.py`（纯本地数据，无 OCR；~20 s）
> 产物：`work/seq/canonical.jsonl`、`groups.json`、`buqi.jsonl`、`beikao.jsonl`、
> `outliers.json`、`seqorder_stats.json`。数字全部落盘见 `seqorder_stats.json`。
> 上游权威口径：`docs/TAKEOVER.md` §1.1/§2.A/§2.B；本文件为其正式实现与实测数字。

## 1. 一句话

正集 42,302 条按 **(部首, 部外笔画)** 组分块，组内按 **Unihan kKangXi (page, position)**
升序 → 42,302 条、**3,563 组**、部首序违反 **0**、组内 kKangXi 序违反 **0**（离群清洗 112 条）。
已知目检样本 05_0017 得 `昴→昵→昶→昷`（ci 11343–11346），与刻本一致；数据集序
`昶→昴→昵` 被推翻（本文档给出量化矛盾率 43.4%）。

## 2. 输入与分母

| 项 | 值 |
|---|---|
| 数据集条目 `work/t2/entry_sequence.jsonl` | 48,708 行 |
| 正集（path 不以【補遺】/【備考】开头） | **42,302** |
| 補遺（path 以【補遺】开头） | **1,769**（独立序列） |
| 備考（path 以【備考】开头） | **4,637**（独立序列） |
| Unihan `Unihan_DictionaryIndices.txt` kKangXi | 70,337 字符（5 字符双位置：`U+4945 关 𣕑 𥏬 𩆆` 等） |
| kRSUnicode / kTotalStrokes | `Unihan_IRGSources.txt`（仅作交叉校验，见 §5） |

## 3. 方法（可复算）

1. **部首笔画表**：康熙字典 214 部首按部首表分画组（radical 1–6=1画，7–29=2画，30–60=3画，
   61–94=4画，95–117=5画，118–146=6画，147–166=7画，167–175=8画，176–186=9画，
   187–194=10画，195–200=11画，201–204=12画，205–208=13画，209–210=14画，211=15画，
   212–213=16画，214=17画）。校验：214 部部首自字条目的 stroke 与该表逐一对上
   （唯「玄」无自字条目；「犬=4」「里=7」「禸=5」按部首表，非 Unihan kTotalStrokes）。
2. **部外笔画 bu** = 数据集 `stroke` − 部首笔画。
   实测数据集笔划口径 = **部首全形笔画 + 部外笔画**（例：茶 stroke 9 = 艸6+余3；
   汀 stroke 5 = 水4+丁1；忉 stroke 6 = 心4+刀2），故该减法即刻本版心画数。
   允许 bu<0 的 19 条（部首自字的异体形，如 王 在 玉部、𡿨 在 巛部）：16 个组，照实保留
   （刻本把它们放在部首自字块，版心不印画数）。
3. **排序**：`key = (radical_number, bu, kKangXi_page, kKangXi_position, 数据集pos)`。
   组 = (radical, bu)；同 (page, position) 平局用数据集 pos tie-break，重出行保留独立槽位
   （同字重复条目 1,890 个额外槽位，字面不合并）。
4. **离群清洗**：kKangXi 页落在本组页中位数 ±6 以外的条目 = 离群（kKangXi 索引为近似/虚拟
   位置或错页），共 **112** 条：组内位置改为按数据集序在已知 kKangXi 坐标间线性插值；
   动作逐条落盘 `outliers.json`。kKangXi 多值条目 4 条（关/𣕑/𥏬/𩆆/䥅 类）：在候选位置中
   选与组页中位数最近者（`multi_valued_kx_used=4`）。
5. **kKangXi 位置语义**（UAX #38，与 kDaeJaweon 同文档口径）：位置 = 10×阅读序秩 + 标志位；
   末位 0 = 该版实际条目，末位 1 = 「未见于该版、为排序指派的虚拟位置」。数据集正集条目中
   虚拟位置 **88** 条（清洗后 73 条仍在组内排序），主要是异体/简体形；本文档不拿它们
   定义组边界，只在组内占槽位。
6. **補遺/備考**：Unihan kKangXi 不索引其版面（其页码体系只覆盖正集），且补遗/备考
   为「部首+画数」重排的独立体例 → 按**数据集原序**输出独立序列（`buqi.jsonl`/`beikao.jsonl`，
   字段注明 `order:"dataset"`）。理由：无独立的机器可读真序来源，且这两部分不参与 v3
   正集映射；若后续要核验，需单独读书眉（备考书眉无部名/画数，只有集名+叶码，见 HEADERS.md）。

## 4. 数字（`work/seq/seqorder_stats.json`）

| 指标 | 值 |
|---|---|
| 正集条目 | 42,302 |
| 组数 | **3,563** |
| 组大小 均值 / 中位 / 最大 | 11.9 / 4 / 199 |
| 部首序违反（组序列） | **0** |
| 组内 kKangXi 序违反（清洗后） | **0** |
| 离群清洗 | 112 |
| kpos 平局组 / 条目 | 1,886 / 3,774（另 4 条双位置条目视位置选择会移动 1 组/8 字） |
| kKangXi 覆盖（含多值修复） | 42,302 / 42,302（原始 42,298，4 条双值） |
| 数据集序 vs 正典序：相邻两两倒挂率 | **43.39%**（18,356/42,301） |
| 同字重复槽位（重出行） | 1,890 |
| 05_0017 样本 | 昴 11343 → 昵 11344 → 昶 11345 → 昷 11346 ✅ |

注：组大小中位数 4 小于 TAKEOVER 里的 ~12.7 是口径差异——那里是按「部」平均；本表按
(部,部外画数) 组统计，大部首的组数多、长尾组多。

## 5. 与其它数据源的矛盾/残余风险

1. **数据集序不可当真序（量化）**：数据集相邻对在正典序中倒挂 43.39%。样本 05_0017
   数据集序 昶→昴→昵 vs 刻本/kKangXi 序 昴→昵→昶。这是 T2 DP 路线作废的直接证据。
2. **kKangXi 页体系 ≠ 本扫描件页体系**：kKangXi 页码是通行影印本（约 1,427 页），本扫描
   3,869 跨页，页数不可换算；只用其**序**。本刻本卷↔部首划分已由 A2b 逐卷扉页核验
   （docs/STRUCTURE.md），与数据集 path 集名划分一致 → 组表只由「部首+部外笔画」定义，
   不依赖页码。
3. **bu 口径**：本文 bu 来自数据集 stroke 口径（已实测 = 部首全形+部外）。与 Unihan
   kRSUnicode 的 residual 不同（后者按字内部首形计，如 氵=3、艹=3），两者在 214 部上
   有 ~1,500 条差异，全部属于「部首全形 vs 字内形」的口径差，非错误；本表以刻本版心
   一致的口径为准，待 HEADERS.md 的书眉画数逐页验证。
4. **离群 112 条**是「kKangXi 页离群」，其组内相对位置靠数据集序插值（±1–2 槽位误差），
   若后续需要精确，用书眉画数/逐页计数定位（v3 流程）。
5. 補遺/備考序未核（独立序列，见 §3.6）。

## 6. 复现

```bash
.venv/bin/python scripts/seq_order.py
# 校验
python - <<'EOF'
import json
st=json.load(open('work/seq/seqorder_stats.json'))
assert st['n_zheng']==42302 and st['n_groups']==3563
assert st['radical_order_violations']==0
assert st['sample_05_0017_ok']
print('OK', st['outliers_cleaned'])
EOF
```

产物字段：`canonical.jsonl` = {ci, char, rad, stroke_total, bu_strokes, gi, kx, kx_outlier,
mt_pos, mt_i, path, group}; `groups.json` = [{gi, rad, rad_i, bu_strokes, start, end, size}]。
