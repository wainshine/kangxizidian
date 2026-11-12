# PROJECT-STATE · 项目状态与交接（2026-11-12）

> 新会话读这一页即可知道「现在到哪了、什么是真的、下一步干什么」。细节分别见：
> `PIPELINE.md`（怎么做）、`WORKFLOW.md`（怎么走流程）、`VERSION-HISTORY.md`（从哪来）、`WORK-MAP.md`（work/ 里有什么）、`ERRATA.md`（哪些旧说法作废）。

## 0. 三十秒快速开始

- 当前基线：**v2.6.1**（过程版本，不签收）；`release/` 只保留 v2.5.8（重构前基线）与 v2.6.1。
- 字形 **17,007**（headword-only 真迹）；基本区 10,269/20,992 = **48.92%**；目标字表 10,269/16,567 = **61.98%**；缺口 **6,298**。
- 闸：QA PASS；内容闸 **35**（阈值 35）；缺件 **1,200**、框线逃逸 **153**（block 几何首次全量基线，未清零）。
- 构建：`mapping_block_v270` + `page_geometry` + 缓存 tag **v350**；全量 ~9.3 分钟、缓存命中 ~20 秒（10 workers）。
- 隔离 9 字：刃/榍/法/紆/総/荹/仟/禦/絞；高频缺 23 字（一/在/為/你…）。

## 1. 目标与已确认决策

- 目标：从《康熙字典》康熙五十五年内府刊本扫描件重建**只收字头真迹**的楷书字体，覆盖 CJK 基本区；缺口不补假字形（D15）。
- 关键决策：`docs/DECISIONS.md` D1–D18 + 更正注记。不要另立口径。
- 字头 = 2×2 小字格块；框面积应均匀（当前块宽 99–103、高 95–100，同页 σ≈0.4px）。

## 2. 当前交付物

| 产物 | 路径 | 状态 |
|---|---|---|
| 当前字体 | `work/font/build/KangXiKai-v2.6.1.ttf`（sha `c73c3023…`） | 可复现（缓存命中重建 sha 一致） |
| 重构前基线 | `release/KangXiKai-v2.5.8/` | 8 项闸 PASS；内容闸基线 |
| 当前过程包 | `release/KangXiKai-v2.6.1/`（9 项闸 PASS，阈值披露） | 过程版本，不签收 |
| 构建输入 | `work/lead/page_geometry.jsonl`、`mapping_verified_all33.jsonl`、`mapping_block_v270.jsonl`、`manifest_v261.json` | 唯一真源；不可从零重建 mapping |
| 缺陷/复核 | `work/review/defect-history-v260/`、`round-001`、owner 核验表 | 供 owner 标记 |
| 历史版本 | `audit/RELEASE-HISTORY.jsonl` + `audit/release-evidence/` | 52 版元数据 + 4 版闸证据 |

## 3. 已知缺陷（按严重度）

| 级别 | 缺陷 | 现状/计划 |
|---|---|---|
| P0 类 | 框线逃逸 **153**；内容闸 **35** | CS2 页级几何 / CS3 mapping 指派；**不得用单字补丁** |
| P0 类 | 门禁盲区：缺字形级框线闸、无 provenance 闸 | CS1 补两个闸 |
| P1 | 缺件扫描 1,200 含邻字组件（口径未隔离） | CS1 修正扫描隔离 |
| P1 | mapping 生成链未脚本化（仅数据保留） | 长期：补脚本或用 charalign 重跑；当前保留全部 map JSON |
| P1 | 343 页无 content_quad（走兜底） | 页级几何校验时按页修 |
| P1 | 高频缺 23、隔离 9、100 字签核未完成 | 里程碑前处理 |
| P2 | 参考字形依赖系统宋体（专有） | 只做报告用途；待换 OFL 字体 |
| P2 | 09–11/13 卷锚点缺失 | 记录在案 |

## 4. 下一步（按顺序）

1. **CS1**：字形级框线闸（扫 TTF 输出）+ 无拷贝 provenance 闸 + 页级几何校验闸；缺件扫描邻字隔离修正；
2. **CS2**：页级几何类修（343 页 quad / 框线 153→0），先出 50 字小样本；
3. **CS3**：mapping 指派审计（内容 35→0）；
4. **CS4**：缺件 1,200 triage（能补则补，不能补入已知债）；
5. **CS5**：高频缺 23 / 隔离 9 / 100 字签核；
6. 里程碑条件满足 → 正式包（按 WORKFLOW §7）。

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
