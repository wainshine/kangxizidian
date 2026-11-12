# PROJECT-STATE · 项目状态与交接（2026-11-12）

> 新会话读这一页即可知道「现在到哪了、什么是真的、下一步干什么」。细节分别见：
> `PIPELINE.md`（怎么做）、`WORKFLOW.md`（怎么走流程）、`VERSION-HISTORY.md`（从哪来）、`WORK-MAP.md`（work/ 里有什么）、`ERRATA.md`（哪些旧说法作废）。

## 0. 三十秒快速开始

- 当前基线：**v2.6.2 工程候选**（sha `eec49c4e…`；fast_gate 仅字形框线 **14** 一项 FAIL：框内残线；同框 0、内容 33/35）；`release/` 仍只保留 v2.5.8（重构前基线）与 v2.6.1（过程版）。
- 字形 **17,007**（headword-only 真迹）；基本区 10,269/20,992 = **48.92%**；目标字表 10,269/16,567 = **61.98%**；缺口 **6,298**。
- 闸（候选 v2.6.2）：font_qa 同框 2 对 FAIL；字形级框线 **23** FAIL；内容闸 **33**（阈值 35）PASS；provenance PASS；页级几何 bad_boxes 198@1px/空指派 1,173（候选阈值 PASS，里程碑严格 0）；缺件 1,200（旧参考口径，待重扫）。
- 构建：`mapping_block_v270` + `page_geometry` + 自动缓存版本（算法 sha8+几何 sha12）；全量 ~9.3 分钟（修复前记录）；缓存命中耗时待重建实测（BF-22），**不再引用旧「~20 秒」声明**。
- 隔离 9 字：刃/榍/法/紆/総/荹/仟/禦/絞；高频缺 23 字（一/在/為/你…）。

## 1. 目标与已确认决策

- 目标：从《康熙字典》康熙五十五年内府刊本扫描件重建**只收字头真迹**的楷书字体，覆盖 CJK 基本区；缺口不补假字形（D15）。
- 关键决策：`docs/DECISIONS.md` D1–D21 + 更正注记。不要另立口径。
- 字头 = 2×2 小字格块；框面积应均匀（当前块宽 99–103、高 95–100，同页 σ≈0.4px）。

## 2. 当前交付物

| 产物 | 路径 | 状态 |
|---|---|---|
| 当前候选 | `work/font/build/KangXiKai-v2.6.2.ttf`（sha `58fd9235…`） | CS1-B 重建；缓存命中重建已验证（3m52s，与 v2.6.2 字形一致）；未过闸 |
| 过程基线 | `work/font/build/KangXiKai-v2.6.1.ttf`（sha `c73c3023…`） | 旧缓存 key 产物，仅历史 |
| 重构前基线 | `release/KangXiKai-v2.5.8/` | 8 项闸 PASS；内容闸基线 |
| 当前过程包 | `release/KangXiKai-v2.6.1/`（旧 finalize 产物；按现行闸会 FAIL） | 过程版本，不签收；不重打（ACCEPT） |
| 构建输入 | `work/lead/page_geometry.jsonl`、`mapping_verified_all33.jsonl`、`mapping_block_v270.jsonl`、`manifest_v261.json` | 唯一真源；不可从零重建 mapping |
| 缺陷/复核 | `work/review/defect-history-v260/`、`round-001`、owner 核验表 | 供 owner 标记 |
| 历史版本 | `audit/RELEASE-HISTORY.jsonl` + `audit/release-evidence/` | 52 版元数据 + 4 版闸证据 |

## 3. 已知缺陷（按严重度）

| 级别 | 缺陷 | 现状/计划 |
|---|---|---|
| P0 类 | 框线逃逸 **153**；内容闸 **35** | CS2 页级几何 / CS3 mapping 指派；**不得用单字补丁** |
| P0 类 | 门禁盲区：缺字形级框线闸、无 provenance 闸、无页级几何闸 | CS1 补三个闸 |
| P0 类 | v2.6.1 有 2 对同框冲突（沓/𦧟、䛱/忠）→ 修复后的 font_qa 会 FAIL | CS1.5 改 mapping（不得改字形绕过） |
| 已完成 | 第 3 代审计的 14 项修复（缓存版本化/几何路径/fail-closed/换包闸/finalize 顺序/同框闸/limit 等） | 见 `audit/AUDIT-RESPONSE-v2.6.1-audit3.md` |
| 已完成 | **三闸**（glyph_frame/provenance/page_geometry）+ 扫描输入绑定 + 构建硬化（失败即非 0/worker clamp/overlay 删除/缓存命名空间/clean-tree/finalize 不改包） | CS1-A，2026-11-12；证据见 BACKLOG BF-01/09/12/43/45/46/48/50 |
| P0 待重建 | 字形级框线 **23** 字（v2.6.1，mixed cache 旧字形）；首次全量重建后复测 | CS1-B |
| P1 已知债 | 页级几何：bad_boxes **198@1px**（0 容差 360）、空指派半版 **1,173**（01_0006 L=「一」） | CS2/CS3 triage |
| P1 | 缺件扫描 1,200（含邻字组件；**旧宋体参考口径**，D21 换霞鹜文楷后须重扫重定基线） | CS1 修扫描-参考字体 SHA 绑定后重扫 |
| P1 | 高频缺 23 含最常用字 一/王/法；**已验证** 01_0006 L 为一之字头页（有 quad）但无 mapping 行；其余 22 字均不在 mapping | CS3 增加「有 quad 但 0 指派」覆盖检查；命中页重新检测（真迹），不补假字 |
| P1 | mapping 生成链未脚本化（仅数据保留） | 长期：补脚本或用 charalign 重跑；当前保留全部 map JSON |
| P1 | 343 页无 content_quad（走兜底） | 页级几何校验时按页修 |
| P1 | 高频缺 23、隔离 9、100 字签核未完成 | 里程碑前处理 |
| ✅ 已解决 | 参考字体统一霞鹜文楷（OFL，`scripts/reffont.py`）；孔洞/连通分量判据已删除（D21） | 2026-11-12；QA 重跑 v2.6.1 仅同框 2 对 FAIL |
| P2 | 09–11/13 卷锚点缺失 | 记录在案 |

## 4. 下一步（按顺序；唯一清单见 `docs/BACKLOG.md`）

0. **CS0（度量与依据层）✅ 2026-11-12**：参考字体唯一化霞鹜文楷（OFL，`scripts/reffont.py`）；font_qa 删除孔洞/连通分量判据（D21）；
1. **CS1-A ✅ 2026-11-12**：三闸 + 输入绑定 + 构建硬化（BF-01/09/12/43/45/46/48/50）；剩余 BF-10/17/18/20/44 部分项；
2. **CS1-B ✅ 2026-11-12**：v2.6.2 全量重建（6m42s → 10m36s 含页 mask），候选可复现（缓存命中重建 sha 一致）；
3. **CS1.5 ✅ 2026-11-12**：同块冲突 2 对清除（BF-02/E23），字表 17,005；
4. **CS2 v1 ✅ 2026-11-12**：页级 pre-cut 直线 mask（E24），字形框线 23→14、内容 35→33；单字 ROI 两法实验失败已回退（E25 verified box / E26 thick ink）；
5. **CS2 v2（进行中）**：剩余 14 字框内残线改**页级几何修**（BF-53/BF-11：修所在页 content quad/text bbox）；页级几何 198/360、1,173 空指派 triage；之后摘除 strip（D22）；
6. **CS3**：内容 33→0、缺件新参考口径重扫（BF-06）、沓/忠 重定位（E23）、半版 0 指派覆盖检查；
7. **CS4/CS5**：高频缺 23 / 隔离 9 / 100 字签核；
8. 里程碑条件满足 → 正式包（按 WORKFLOW §7）。

## 5. 如何独立审计（不信任任何人写下的数字）

```bash
# 1) 字体存在性与 sha
shasum -a 256 work/font/build/KangXiKai-v2.6.1.ttf
# 2) 快闸（会打印 7 项 PASS/FAIL；内容闸阈值 35）
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.1.ttf \
  --manifest work/font/build/manifest_v261.json --version 2.6.1 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json \
  --pkg-dir release/KangXiKai-v2.6.1 --content-max-damaged 35
# 3) 复现构建（缓存命中，应 17,007 cached，sha=c73c3023…）
FONT_BUILD_WORKERS=10 .venv/bin/python scripts/font_build.py \
  --mapping work/lead/mapping_block_v270.jsonl --out /tmp/audit.ttf --version 2.6.1
# 4) 抽查字形（渲染或看发布包 random120-v260.png / specimen.png）
# 5) 阅读：release/KangXiKai-v2.6.1/gate-report-v261.json（每步 ok/阈值/明细）
```

审计原则：**只信闸输出与复算命令**；文档里的数字若与闸不一，以闸为准。发现文档不符 → 记入 `ERRATA.md`。

## 6. 时间线与历史

- 逐版变更：`docs/VERSION-HISTORY.md`（v0.3→v2.6.1，探索/修补分类）；
- 编年记录：`docs/_history/COUNTS.md`、`docs/_history/V3-STATUS.md`（历史，不作现行依据）；
- 审计：`audit/`（现行结论）+ `audit/_history/`（历史审计存档，不改写）。
