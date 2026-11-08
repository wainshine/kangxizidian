# V3-STATUS · 接手会话（2026-11-08 下午）成果与遗留

> 本会话按 `docs/TAKEOVER.md` 的 v3 架构（结构性标注）推进。**先读 TAKEOVER.md**，本文件记录
> 已落地的东西、实测数字、卡点与下一步。术语按 D1。旧文件不改，历史留痕。

## 1. 本会话结论（一句话）

**v3 架构被证明可行且必要**，换掉了旧 T2 的「数据集序 + 逐页人工校准」路线；核心链
「正典序 + 逐半页候选计数 + 书眉校验 + 局部纠错」已逐环打通到「框↔条目」级（0006-0009 实证 11/11 正确），
**但两个工程门未过：①书眉读数准确率不足；②检测器半版计数与正典序在卷级有 ~10% 偏差**。
因此**全量标注/全量字体本轮未产出**——但管线、数据、判据、demo 字体全部就位，下一会话按 §5 执行即可。

## 2. 已交付产物（可直接用）

| 产物 | 路径 | 状态/数字 |
|---|---|---|
| 接手诊断 + v3 架构 | `docs/TAKEOVER.md` | 权威口径；含旧路线错因实证 |
| **demo TTF（可安装）** | `work/font/demo/KangXiKai-demo-v0.1.0.ttf` | 32 字真迹，UPM1000，OFL1.1，两次构建 sha256 同 |
| demo 样张 / 对照 | `work/font/demo/specimen.png`、`work/font/qa/crop_vs_font.png` | Lead 目检通过 |
| 字体构建链（dual CLI+断点续跑） | `scripts/font_norm.py`、`font_build.py`、`font_qa.py`；`docs/FONT-BUILD.md` | 23.6ms/字 + 5.3ms/字 |
| 正典序原型（42,302 条/3,563 组） | `work/lead/canonical_proto.jsonl`、`groups_proto.json`；`scripts/lead_canonical_proto.py` | 一部/日部/乙部书序实证一致 |
| 页角色表（全 3,869 页） | `work/lead/page_roles.jsonl`；`scripts/lead_page_roles.py` | body 3,528 / blank 162 / title_page 99 / cover 80 |
| 卷界表（12 卷 × 上中下 + 補遺/備考） | `work/lead/volume_sections.json` | 每卷 3 段 body 页区间 |
| 映射求解器 | `scripts/lead_solver2.py` | 候选→计数→书眉硬约束→±1 局部纠错→框级指派；0006-0009 demo 通过 |
| 字形抽取器 | `scripts/lead_extract.py` | mapping→300dpi 裁切→`work/glyphs/` 索引；已验证 10 字 |
| 检测器 v2 | `scripts/t1_v2.py`；`docs/DETECTOR-V2.md`；冻结副本 `scripts/lead_t1v2_frozen.py` | 候选召回 1.0、head 类召回 1.0、4 页 8 半版计数 exact=1.0 |
| 全量检测（12 卷 3,266 body 页） | `work/lead/boxes300/`（3,266 JSON / 234,346 候选）；`scripts/lead_run_detect.py` | **已完成**；150dpi 直渲染路径，0006-0009 八半版计数 exact；coords=150dpi 当量 |
| 书眉读数（未过门） | `scripts/header_read.py`+`header_resolve.py`（seq）、`work/seq/headers_pilot*.jsonl`、`docs/HEADERS.md` | pilot 20 页：集名 19/20、部名 15/19、画数 11/18（未过门）；全量 raw 本轮未跑完（部分在 work/seq/parts/） |
| 检测器 30 页评审图 | `work/detect2/montage_v1/`、`work/detect2/report.json` | 供下一会话复核 |

## 3. 本会话新增的关键实测事实（下一会话直接用，别重测）

1. **数据集序 ≠ 书序，Unihan kKangXi 序 = 书序**：05_0017 书序 昴→昵→昶→昷，数据集序 昶→昴→昵。
   `work/t2/dp_alignment*.json` 一律不得再作标签依据；连「owner ✓ 验收集」在框级也不可靠
   （11 个里 1 个错：時 的框实为「晋」）。
2. **重出行真实存在**：世 第二次出现时注文 = 「【集韻】同，上」——数据集同字重复行（1,888 组）对应印刷重出，
   **计入字头数**（不是数据噪声）。古文大字变体（弌/𠆤/弎）不是数据集条目，**不计入**。
3. **页结构**：每卷卷界有 7-8 页非正文（集扉页/书衣/空白）；body 页 = 跨页，阅读序 **R→L**；
   版心在 L 半版最左缘（300dpi 下 x≈[10,92]，与正文列的分界竖线在 x≈80±5）。
4. **书眉字段**（上→下）：康熙字典(4格) / 集名卷(3格) / 部名(2格) / 画数(1-2字段，数字+畫) / 葉码(1-3格)。
   集名由 `volume_sections.json` 直接定（**不要用数据集路径的集卷**——D14 已知不符）；葉码 = 册内扫描页−5（PDF01-12 成立）。
5. 检测器当前已知偏差（final 全量跑）：strict 计数合计 **36,923 / 正典 42,302 = −12.7%**；
   vol01 2,374/2,633、vol02 2,564/2,901、vol03 2,337/2,597；但 0006-0009 八半版与 truth 完全一致；
   子集上（6-41 页）反而超计 246 vs 176。**方向有正有负 → 必须靠书眉逐页对账，不能全局缩放**。
6. 渲染路径敏感：检测必须 `--dpi 300` + render_dpi=**150 直渲染**；300→150 降采样会让分类分漂移
   （0007/0009 计数出错，实测）。
7. 书眉 partial（seq，覆盖 PDF01-02 全 500 页）已入 solver 实跑：
   703 个校验点 / 577 不一致，**首个不一致在 01_0010L**（预测已进 部外3，书眉=部外2）——
   即早期页检测计数偏高 1-2；±1 局部纠错原型不足以收敛（缺口在多个连续半版），
   **必须先修计数精度/换更强纠错（见 SESSION-HANDOFF P1）**。
8. 候选数据要「宁多勿少」：多出的候选可由「组大小精确已知 + 书眉校验」剔除，漏检无法恢复。

## 4. 卡点（按阻塞程度）

| # | 卡点 | 现状 | 下一步最小动作 |
|---|---|---|---|
| 1 | **书眉读数** | pilot 未过门（集名19/20、部名15/19、画数11/18）；且 resolved 输出 bu 全回退「一部」（solver 不可用）；全量 raw 未跑完 | 用楷体模板匹配（GuanGeKai 62 字候选集：214 部首+数字+部/畫），版心柱 x=[10,92]@300dpi，按固定槽位解析；20 页 owner 真值必须 100% |
| 2 | **检测计数 vs 正典序 10% 偏差** | 方向混合、未定因 | 用 headers + 部界/卷界，跑 solver 找首个 mismatch，目检 2-3 个 mismatch 窗口判定是漏计还是正典多计 |
| 3 | 全量映射/字体 | 未跑（依赖 1+2） | solver 全量跑通后：extract（42k crops）→ font_build（16.5k 真迹）→ QA |
| 4 | 補遺/備考 6,406 条 | 本轮**主动排除**（仅 224 个基本区独有字，收益低） | 作为 v1.1；正集先行 |
| 5 | GAN/ribbon 缺字 | 未开始；缺 4,201 个基本区码位（其中 ~2,175 可 mapped_traditional） | 字体发布前用 ribbon 回落优先；GAN 后置 |

## 5. 下一会话执行清单（建议顺序，每步有验收）

```
S1 书眉读数 v2（0.5 天）
   - 输入：work/lead/page_roles.jsonl（只读 body 页）
   - 方法：版心柱 [10,92]@300dpi → 水平投影切格 → 固定槽位解析（康熙/集名/部名/画数/葉码）
           识别：部名=214 部首模板匹配；画数=数字模板匹配+几何（十+二粘连用宽格拆）
           模板字体：~/Library/Fonts/GuanGeKai-Regular.ttf（楷体，已装）
   - 门：owner 20 页（work/t2/margin_labels_full.json）集名/部名/画数 100%；
         全量覆盖 ≥85%，低置信置 null 不瞎猜
S2 全量检测（~20 分钟，8 进程）
   - .venv/bin/python scripts/lead_run_detect.py --vols 01..12 --pages body --dpi 300 --workers 8
   - 注意：冻结版 lead_t1v2_frozen.py 与 t1_v2.py 保持同版；detector 若改分类另存 v3
S3 对账 + 纠错（核心，0.5-1 天）
   - .venv/bin/python scripts/lead_solver2.py --boxes-dir ... --headers ... --roles ...
   - 门：每卷书眉一致性 ≥95%，剩余 mismatch 逐窗口目检解决；每卷末 consumed == 正典累计
   - 若差异坐实是「检测漏计」→ 用候选 soft 分/降低阈值补；若是「正典多计」→ 修 canonical（记录修法）
S4 全量字形 + 字体
   - mapping → scripts/lead_extract.py → work/glyphs（~42k 真迹样本，16,567 基本区字）
   - scripts/font_build.py --mapping <mapping.jsonl> → work/font/build/KangXiKai-v0.1.0.ttf
   - QA（覆盖率/空字形/孔洞）+ 视觉对照 + SHA256SUMS（顺序：字体→stats→SHA→zip）
S5 发布链：cmap 20,992+42；缺字 mapped_traditional（Unihan kTraditionalVariant，~2,175）+ ribbon 回落；
   README 披露缺口；docs/DATA.md 来源/许可；OFL 文本；不得用他人 RFN。
```

## 6. 复算命令（关键）

```bash
# 正典序原型
.venv/bin/python scripts/lead_canonical_proto.py
# 页角色（全量 3,869 页，8 进程，~2 分钟）
.venv/bin/python scripts/lead_page_roles.py
# 全量检测（示例 vol 01；body 页来自 page_roles）
.venv/bin/python scripts/lead_run_detect.py --vols 01 --pages body --dpi 300 --workers 8
# solver demo（0006-0009，人工 truth 计数 + demo 书眉）
.venv/bin/python scripts/lead_solver2.py --boxes-dir work/detect2/boxes300 \
  --counts work/lead/counts_truth_0006_0009.json --headers work/lead/headers_demo.jsonl \
  --limit 8 --out work/lead/map_proof
# demo 字体重建（两次哈希一致）
.venv/bin/python scripts/font_build.py --manifest work/font/demo/manifest.json \
  --out /tmp/KangXiKai-demo.ttf
```
