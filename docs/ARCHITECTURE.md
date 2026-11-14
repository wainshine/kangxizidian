# ARCHITECTURE · 项目架构与文件夹层级

> 适用对象：接手的开发者 / 审计者 / 未来的自己。
> 本文回答三个问题：**项目由哪些层组成、每层放什么、新增东西该放哪里**。
> 数据细节见 `docs/DATA.md`；管线参数与复现命令见 `docs/PIPELINE.md`（唯一权威）；
> 流程纪律见 `docs/WORKFLOW.md`；文档索引见 `docs/README.md`。

## 1. 总体架构（从扫描到发布）

```
康熙字典内府刊本 PDF（14 册 / 3,869 页，12G，gitignored）
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ S1 页级几何  scripts/build_page_geometry.py + page_frames.py      │
│   格点拟合 / 正文区 content_quad / 版框与界行检测                  │
│   产物：work/lead/page_geometry.jsonl（唯一真源，3,869 行）        │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ S2 字头 mapping  make_block_mapping.py（+ oneoff 数据修复工具）    │
│   正典序 → 页/半版 → 2×2 字头格块（box = 2×2 块 ∩ content_quad）  │
│   产物：work/lead/mapping_block_v271.jsonl（17,005 字，唯一真源）  │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ S3 字形构建  font_build.py + font_norm.py                         │
│   300dpi 渲染 → 二值化 → pre-cut（quad/mask/线条带）→ 2×2 块掩膜  │
│   → 主簇清理 → potrace → 归一化（UPM 1000）→ 边缘清理             │
│   产物：work/font/build/KangXiKai-v<ver>.ttf + manifest + stats    │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ S4 闸（fail-closed，输入绑定 sidecar）                             │
│   font_qa · content_loss_gate · glyph_frame_gate · provenance_gate │
│   page_geometry_gate · scan_missing_parts · scan_frame_escape      │
│   编排：fast_gate.py（快闸 8 项） / release_gate.py（全闸 17 项）  │
│   产物：work/lead/gate-report-v<tag>.json + 各闸 json/jsonl+sha256 │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ S5 发布  font_package.py + make_release_extras.py + release_gate   │
│   clean-tree 打包 → SHA256SUMS → zip 自校验 → finalize（SHA 覆盖   │
│   gate-report，冻结）                                              │
│   产物：release/KangXiKai-v<ver>/ + .zip                           │
└──────────────────────────────────────────────────────────────────┘
```

关键架构约束（详见 `docs/PIPELINE.md` / `docs/DECISIONS.md`）：

- **单一真源**：mapping / page_geometry / page_line_bands / manifest 是数据真源；修复必须回写这些文件，禁止 overlay/restore 拷贝旧字形。
- **pre-cut**：版框/界行/页边黑带在二值化前排除；禁止「切进来再擦」。
- **闸 fail-closed**：闸输出旁写 `<out>.sha256`（font/manifest/mapping/geometry/bands/reffont/脚本 sha + argv + git）；复用前必须校验。
- **候选/正式分层**：候选不打包；正式包必须 clean git tree、SHA 覆盖 gate-report、finalize 后冻结。

## 2. 仓库目录层级（顶层）

```
kangxizidian/
├── AGENTS.md                 # 入口约束：先读什么、硬性规则、当前状态、最短验证
├── README.md                 # 项目介绍（给使用者/发布页）
├── LICENSE / OFL.txt         # 代码 MIT / 字体 OFL 1.1
├── scripts/                  # 代码（4 层，见 §3）
├── docs/                     # 文档（现行在根，历史在 _history，见 §4）
├── work/                     # 工作区（gitignored，37G）：真源、构建、证据（见 §5 / WORK-MAP.md）
├── release/                  # 发布包（gitignored，只放正式包 + 历史正式包）
├── audit/                    # 审计报告与证据（现行在根，历史在 _history）
├── data/                     # 参考数据：gold-certified / ref / unihan / base（部分 gitignored）
└── 康熙字典/                 # 扫描源 PDF（12G，gitignored，不随仓库分发）
```

| 目录 | 是否入库 | 职责 | 生命周期规则 |
|---|---|---|---|
| `scripts/` | 是 | 可执行代码：现行管线 + 一次性 + provenance + 冻结历史 | 见 §3；新一次性脚本只能进 `oneoff/` |
| `docs/` | 是 | 规范/架构/管线/决策/计划/发布记录 | 现行放根；过期进 `_history/`（不改写） |
| `work/` | 否 | 数据真源、构建产物、闸证据、复核材料 | **不可盲删**，见 `docs/reference/WORK-MAP.md` |
| `release/` | 否（历史正式包按需留档） | 正式发布包与 zip | 只放正式包；预览放 `release/_preview/`；失效包进 `_withdrawn/` |
| `audit/` | 是 | 审计报告/回应/证据 | 现行在根；历史在 `audit/_history/` |
| `data/` | 部分 | 参考字表/unicode/认证样本/骨架字体 | 大文件与第三方数据 gitignored；许可文本保留 |
| `康熙字典/` | 否 | 原始 PDF 扫描件 | 只读输入；不修改、不删除 |

## 3. `scripts/` 分层（2026-11-14 重构后）

> 原则：**顶层 = 现行管线（主进程）**；一次性脚本从开始就放子目录；`_archive/` 只冻结历史、不再日常归档。

```
scripts/
├── *.py                  # 28 个 = 现行管线（构建 / 闸 / 打包 / 复核 / 发布工具）
├── oneoff/               # 26 个 + README = 一次性脚本（4 组，见 SCRIPTS.md §0.1）
├── provenance/           # 24 个 + README = 数据 provenance（映射/字表/部界历史求解链）
├── _archive/             # 141 个 .py + README = 冻结历史（v2.6.2 之前，不再新增）
└── jobrun.sh             # 后台任务包装（pipefail + EXIT 状态）
```

| 层 | 数量 | 职责 | 规则 |
|---|---|---|---|
| 顶层 `*.py` | 28 | 现行管线：`font_build/font_norm/build_page_geometry/make_block_mapping/page_frames/detect_blocks/precut_masks/fidelity_eval/reffont/make_manifest_from_stats` + 各 gate + `fast_gate/release_gate/font_package/check_release_docs/stamp_version` + `review_sheet/make_round_pack/make_release_extras/release_metrics/make_readme_images` | **禁止** import `oneoff/`、`provenance/`、`_archive/`；改这里会动构建/闸/缓存/绑定 |
| `oneoff/` | 26 | A 当前真源生成（E30 quad 扩张、E23 同块修复、mapping 重建等）· B 旧修复/诊断链 · C 旧复核/出图 · D 历史配方/实验/维护 | **新增的一次性脚本一律放这里**；可 import `scripts/` 顶层；不参与每次构建 |
| `provenance/` | 24 | mapping/正典序/部界/书眉历史求解链，结果已固化进真源 | 保留不跑、不得删除；**不是死代码** |
| `_archive/` | 141 | v2.6.2 之前的冻结历史（含被 ERRATA/changesets 引用的审计证据） | 只读；**不再新增**；删缓存可以，删 `.py` 不可以 |

命名约定：脚本名用 `snake_case`；`oneoff/` 里按用途分组写在 README；临时实验脚本也不要放顶层，直接 `oneoff/`。

## 4. `docs/` 分层

```
docs/
├── README.md                 # 文档索引（先看它）
├── ARCHITECTURE.md           # 本文：架构与目录层级
├── LAYOUT.md                 # 原书版式 / 切分 / 选用规则（文字版规则）
├── METHOD.md                 # 技术路线（可读版，面向非开发者）
├── PROJECT-STATE.md          # 30 秒现状 / 已知缺陷 / 独立审计
├── PIPELINE.md               # 管线唯一权威（参数 / 命令 / 失败模式）
├── WORKFLOW.md               # 流程纪律（候选/正式、闸、里程碑、复核）
├── DATA.md                   # 数据来源/许可/校验和/复现链
├── DECISIONS.md              # 口径决策（唯一权威）
├── GLOSSARY.md               # 术语（冲突时以它为准）
├── ERRATA.md                 # 历史错误/作废数字/考古避坑
├── VERSION-HISTORY.md        # 逐版变更
├── BACKLOG.md                # 唯一待办清单
├── SCRIPTS.md                # 脚本清单/分层/旧方法评估
├── WORK-MAP.md / WORK-CLEANUP*.md
├── releases/                 # 正式版发布记录（每版一个子目录）
│   ├── README.md
│   └── v2.6.2/{RELEASE.md, KNOWN-DEBTS.md, SELF-AUDIT.md}
├── plans/                    # 滚动计划：2.6 补丁线（PLAN-v2.6.3）/ v2.7.0
├── reference/                # 查阅型：SCRIPTS / WORK-MAP / WORK-CLEANUP / RELEASE-METRICS /
│   │                          EXPERIMENTS / CANONICAL-ORDER / STRUCTURE / HEADERS
├── images/                   # README/发布图（扫描书影注明权利）
└── _history/                 # 历史文档（不改写，仅供考古；含 PROJECT-AUDIT-2026-11-12）
```

文档规则：
1. **唯一权威**：数据口径看 `DECISIONS.md`，管线看 `PIPELINE.md`，流程看 `WORKFLOW.md`，术语看 `GLOSSARY.md`；
2. 根目录只放现行文档；过期文档移入 `_history/`，并在 `docs/README.md` 登记；
3. 每个正式版：`docs/releases/v<ver>/RELEASE.md` + `KNOWN-DEBTS.md` + `SELF-AUDIT.md` + `VERSION-HISTORY.md` 一行 + `work/changesets/` + `work/lead/version-artifacts-v<ver>.jsonl`；
4. 数字必须来自闸输出或可复算命令，无证据写「待验证」。

## 5. `work/` 分层（数据真源与证据）

> 完整地图与清理规则见 `docs/reference/WORK-MAP.md`；这里只列架构位置。

| 子目录 | 内容 | 地位 |
|---|---|---|
| `work/lead/` | page_geometry / mapping_block_v* / page_line_bands / 闸报告 / 扫描 jsonl / 复核反馈 | **真源 + 证据**（不可盲删） |
| `work/font/build/` | TTF、manifest、build_stats、缓存 | 构建产物（TTF/manifest 可重建，cache 可清） |
| `work/map/` | mapping 历史探索版本（charalign* 等） | 历史探索证据（保留） |
| `work/seq/` | 正典序 canonical / 书眉数据 | 数据真源输入 |
| `work/t2/` | 对齐/DP 中间结果，`pdf_map.json` 现行依赖 | **不可删**（pdf_map） |
| `work/review/` | 复核包（round-*/、标记图、feedback） | 复核证据 |
| `work/changesets/` | 变更集 cs-*.json | 版本变更记录 |
| `work/gates/`、`work/models/`、`work/t00/`、`work/detect2/` 等 | 闸/模型/检测缓存 | 按 WORK-MAP 清理规则 |

## 6. 数据流与关键产物

| 产物 | 路径 | 生产者 | 消费者 | 绑定/版本 |
|---|---|---|---|---|
| 页级几何 | `work/lead/page_geometry.jsonl` | `build_page_geometry.py` | mapping / 构建 / 页几何闸 | sha 进 sidecar |
| mapping | `work/lead/mapping_block_v271.jsonl` | `make_block_mapping.py` + oneoff 修复 | 构建 / provenance 闸 | sha 进 sidecar / build_recipe |
| 线条带 | `work/lead/page_line_bands.json` | E27 数据（含 oneoff 反算） | 构建 pre-cut / 扫描 | sha 进缓存键 + sidecar |
| 字体 | `work/font/build/KangXiKai-v<ver>.ttf` | `font_build.py` | 闸 / 打包 | 字体 sha256 |
| manifest / stats | `work/font/build/manifest_v*.json` / `*.build_stats.json` | `make_manifest_from_stats.py` | 闸 / 打包 / 复核 | 同字体版本 |
| 闸报告 | `work/lead/gate-report-v<tag>.json` | `release_gate.py` | 打包 finalize | 输入 sha + git + 阈值 |
| 发布包 | `release/KangXiKai-v<ver>/` + `.zip` | `font_package.py` + `release_gate finalize` | 分发 | SHA256SUMS + attestation |

## 7. 依赖方向（禁止反向依赖）

```
docs/  ──说明──▶ scripts/  ──读写──▶ work/（真源/产物）  ──打包──▶ release/
  ▲                  │
  └──── 证据引用 ─────┘（audit / work/lead 的闸报告与变更记录）

scripts/ 顶层（管线） ──可以──▶ scripts/oneoff（仅人工运行，不 import）
scripts/oneoff ──可以 import──▶ scripts/ 顶层
scripts/provenance / _archive ──只读历史，禁止被顶层 import
```

- 管线脚本**不得** import `oneoff/`、`provenance/`、`_archive/`；
- `oneoff/` 可以 import 顶层库（已修 `ROOT`/`sys.path`），但**不参与构建**；
- 文档路径引用脚本时必须带层级（如 `scripts/oneoff/expand_quads_to_cover_boxes.py`）。

## 8. 新增文件放哪里（决策表）

| 你要加的东西 | 放哪 | 备注 |
|---|---|---|
| 新的构建/闸/发布工具 | `scripts/` 顶层 | 要进 `release_gate`/`fast_gate` 的脚本清单与文档 |
| 一次性数据修复/体检/实验/迁移 | `scripts/oneoff/` | 从开始就放这里，**不要放顶层、不要用后丢 archive** |
| 要保留的数据求解链（已固化） | `scripts/provenance/` | 不得删除；不保证与现行 API 同步 |
| v2.6.2 之前的历史脚本 | `scripts/_archive/` | 只读冻结，不再新增 |
| 现行文档 | `docs/` 根 | 并更新 `docs/README.md` 索引 |
| 过期文档 | `docs/_history/` | 顶部加「历史」横幅，不改写原文 |
| 正式版发布记录 | `docs/releases/v<ver>/RELEASE.md` | 与 `VERSION-HISTORY.md` 对应 |
| 数据真源/闸证据/复核材料 | `work/lead/`、`work/review/` 等 | 见 `docs/reference/WORK-MAP.md`，不盲删 |
| 正式包 | `release/KangXiKai-v<ver>/` | clean tree 才可 finalize |

## 9. 架构层面的「不要做」

1. 不要把一次性脚本放 `scripts/` 顶层，也不要用完就丢 `_archive/`；
2. 不要让管线 import `oneoff/provenance/_archive`；
3. 不要改 `release/` 里已 finalize 的包内文件（SHA/zip 立刻失效）；
4. 不要绕过 pre-cut 在切后擦框线，不要 restore/overlay 整字拷贝；
5. 不要在文档里写不可复算的数字（闸输出/可复算命令为准）；
6. 不要用系统宋体/黑体做参考（唯一参考 = 霞鹜文楷 OFL，D21）。
