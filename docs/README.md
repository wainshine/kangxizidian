# docs/ 文档索引与状态（2026-11-10 校订）

> 本目录只放项目文档；**审计文件在 `../audit/`**（外部 AUDIT-REPORT / 自审计 AUDIT-SELF / 回应 AUDIT-RESPONSE）。
> 下文「现行」= 与当前代码/发布物一致；「历史」= 阶段记录（数字/口径为当时状态，不作为现行依据）。

## 现行口径速查（以 DECISIONS 为唯一权威）

- 发布：`release/KangXiKai-v2.4.14/`（zip 同目录；**参考结构闸 v2（配准+结构失配）**：1,340 flagged→清 1,329 字形→复扫剩 27；16 个结构失配字隔离（含 一）；17,035 字；QA PASS；不签收）
- 字表：**17,051 字形，全部头级真迹**（headword-only，D15；v2.4.11 隔离 35 个框线污染字）；基本区∩16,567 = **10,348 = 62.46%**
- 缺口：**6,214**（分桶清单 `v245-gan-targets.json`：B 374 / B2 1 / E 5,839；B/E 不许直接进 GAN）
- QA：PASS（render_bad/tiny/同框=0）；发布包 **20 项** SHA256SUMS 全过（21 文件）
- 精度敞口：指纹来源字 ~84.6%（n=13，宽 CI）→ 约 1,400-1,500 字级风险（见 release `PROVENANCE.md`）
- 版本语义/发布流程：D18 / D17；现行发布计划：`RELEASE-PLAN.md`；发布物：v2.4.3（sha256 `d0107b11…`）

## 文档清单

| 文档 | 状态 | 说明 |
|---|---|---|
| `DECISIONS.md` | **现行（唯一权威）** | D1–D18 + 更正注记：术语/家族名/覆盖边界/provenance/headword-only/自动标签/发布流程/版本号 |
| `RELEASE-PLAN.md` | **现行** | 发布计划、元数据定稿、打包链、检查清单（旧 cmap 承诺方案见附录 A 作废） |
| `COUNTS.md` | 编年（顶部有现行口径横幅+过期条目索引） | 逐节计数/方法/发布记录；需要真实状态时读最新节或 release |
| `V3-STATUS.md` | 编年（同上） | v3 阶段推进记录 |
| `SESSION-HANDOFF.md` | 编年（同上） | 每轮会话交接；最后几节 = 最新状态 |
| `CANONICAL-ORDER.md` | 现行（数据层） | 正典序 42,302 条 / 3,563 组；16,567 唯一基本区字的来源 |
| `STRUCTURE.md` | 现行（结构层）+ §11 部界锚点为历史 | 36 卷/214 部/PDF13 分节；部界锚点现行实现见 `scripts/lead_bu_dp3.py` |
| `HEADERS.md` | 现行（书眉数据） | 书眉字段/葉码/解析；页码公式旧说法已按 D14 标注作废 |
| `DATA.md` | **现行** | 数据来源/许可/校验和/生成物/复现链（含现行主链与环境） |
| `FONT-BUILD.md` | 部分过期（§12 为现行链路） | §0–§11 = demo 阶段历史；§12 = v2.4.x 现行构建链 |
| `VENDORED.md` | 部分过期 | guangeti 复制记录 + 现行差异注记 |
| `OCR-OPTIONS.md` | 历史调研 + 补充结论 | OCR 基准（v5 69% 等）；最终解法为 VLM 注文指纹（见文末补记） |
| `DETECTOR-V2.md` | 历史设计（检测思路仍用） | t1_v2 冻结版作候选生成；现行是字符级对齐 |
| `PROBE.md` | 历史（T0 探测） | 版面参数实测；页码公式已作废（D14） |
| `T2-EXP30.md` | 历史实验 | 三分支决策依据；现行路线为字符级对齐+指纹 |
| `HEADWORD-COVERAGE.md` | 历史（T0.0 覆盖盘点） | 30,992→实测 16,567；缺口策略已被 D15 取代 |
| `TAKEOVER.md` | 历史（接手诊断） | 优先级声明已作废，DECISIONS 为唯一权威 |
| `PROMPT.md` | 任务书原文（保留） | 顶部已注：cmap 20,992/T4 留出等已被 D15/D12 修正 |
| `../audit/README.md` | 现行 | 审计文件命名/流程约定 + 索引（含当时结论与后续去向、路径迁移提示） |
| `../audit/AUDIT-VERIFICATION-LOG.md` | 现行 | 各轮审计声明的核验结论（✅/⚠️/❌）与当前去向台账 |

## 校订记录（2026-11-10，本轮）

本轮的文档校订目标：**以当前代码为基准，消除过期与互相冲突的表述**。处理方式：
- 现行文档（DATA/RELEASE-PLAN/CANONICAL-ORDER/HEADERS/STRUCTURE）→ 直接改正文到与代码一致；
- 历史文档（PROBE/HEADWORD-COVERAGE/T2-EXP30/TAKEOVER/DETECTOR-V2/FONT-BUILD 前段/VENDORED/OCR-OPTIONS）
  → 顶部加「文档状态」横幅 + 过期点逐条标注/更正，**不篡改历史正文**；
- 编年文档（COUNTS/V3-STATUS/SESSION-HANDOFF）→ 顶部加「现行口径 + 过期条目索引」横幅；
- DECISIONS → 追加 D15–D18 现行决策 + 对 D3/D10/D11/D12 的更正注记；
- 新增本索引，明确每个文档的状态与替代关系。
