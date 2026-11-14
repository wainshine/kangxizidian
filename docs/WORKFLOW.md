# 流程重构：候选/正式分层 + 变更集 + 增量验证（2026-11-12）

> 背景：已发 50+ 个「版本」，每个打包 20–30 分钟，多数发完即失效；单字补丁导致回归；owner 时间被大量浪费。
> 本文替换旧流程（「改一版→打包→发现问题→再打包」），从下一轮开始执行。

---

## 0. 旧流程错在哪（逐条对应事实）

| 问题 | 事实 | 后果 |
|---|---|---|
| 没有「候选/正式」分层 | 每次改动都走 publish/package | 50+ 版本，20–30 分钟/次，全部占 release 目录 |
| 没有变更集边界 | 谁发现谁修、按字补 | restore/overlay 层反复把旧框线带回（勤 事件） |
| 没有增量判定 | 每次全量重切 17,007 字 | 9–11 分钟/次，叠加打包 → 一轮半小时 |
| 没有固定人工验收入口 | 每次给 owner 的图格式不同 | owner 找不到重点，标了也没被系统化处理 |
| 没有自动闸优先级 | 发版后才发现问题 | 版本发完即失效 |
| 没有下一轮方向决策机制 | 缺陷源多、无 triage | 反复修同一类问题 |

---

## 1. 三层状态（从今往后唯一合法路径）

```
[G] 页级几何快照（3869 页：lattice / 正文 bbox / content quad / 质量分）   ← 仅在检测算法变化时重算
        │  版本号 g<date>-<n>，带质量报告，存 work/geometry/g-*.jsonl
        ▼
[F] 字体构建（17,007 字）  ← 仅当 (G, mapping, 算法) 变化时；字级缓存，按脏集重切
        │  内部文件 work/font/build/f-<date>-<n>.ttf，不打包、不叫版本
        ▼
[C] 候选（candidate）= {F + 自动闸报告 + 人工复核包}   ← 每轮只出一个，内部编号 cYYYYMMDD-n
        │  只有 owner 明确通过 → 才进入 R
        ▼
[R] 正式发布包（release vX.Y.Z）   ← 含字体 + 全部材料 + 闸报告 + SHA；只有 R 才能进 release/
```

**硬规则**
- `release/` 只允许放正式包；候选/中途版一律不进 `release/`；
- 候选版本号 `cYYYYMMDD-n`，不对外叫「版本」；正式版本号只升 `vX.Y.Z`；
- 一个候选 = 一个**变更集**（见 §2），不混入无关修复。

---

## 2. 变更集（Change Set）——每轮唯一的输入单位

每个变更集落盘 `work/changesets/cs-<id>.jsonl`，字段：

```json
{"id":"cs-20261112-1","class":"frame_precut","scope":{"pages":[...],"chars":[...]},
 "root_cause":"mapping box 来自墨迹紧框而非 2×2 格块","fix":"block-based mapping",
 "affected_stage":["mapping"],"expected":"框面积统一；框线逃逸↓",
 "verification":{"auto":["box_uniformity","frame_escape","content_gate"],
                 "human":"02-class-sample + 01-changes"}}
```

**规则**
- 一个变更集只解决**一类**问题；发现新问题 → 记入 backlog，不开新分支混修；
- 每个变更集必须写清「影响阶段」：geometry / mapping / 算法 / 材料——决定增量还是全量（§4）；
- 说清楚验证方式（自动闸 + 人工看哪张图）。

---

## 3. AI 与人如何交互（明确边界）

| 情形 | AI 做什么 | 是否问人 |
|---|---|---|
| 明确的类级缺陷（可复现、有证据） | 直接按变更集修 + 自动验证 | 不问，只在轮次报告里说明 |
| 需要取舍（先修 A 类还是 B 类、阈值放宽多少） | 给出 2–3 个选项 + 影响 | **问**（1 次，带默认建议） |
| 标签/字形是否正确（如 愈 裁片内容与标签不符） | 只做「疑似」清单，不擅自改 | **问**（owner 标 ✓/✗/?） |
| 闸失败 | 自动修到过闸；过不去就停并报告原因 | 不问（除非需放宽阈值） |
| 正式发布 go/no-go | 给复核包 + 数据 | **问**（唯一发布决策点） |
| 探索性方案（如新检测算法） | 先出小样本对照（≤50 字）再定 | 可以问，但不打包 |

**提问规范**：一次最多 3 个问题；必须带默认选项和代价说明；不重复问已答复的问题。

---

## 4. 什么时候全量重跑，什么时候只跑一部分

判定依据 = 变更集影响阶段：

| 变更类型 | 失效范围 | 构建方式 | 耗时（实测） |
|---|---|---|---|
| 只改材料/文档/报告 | 无 | 不重建 | 0 |
| 改单字裁切算法（cleaning 等） | 算法哈希变化 → 全部字 | 全量（10 workers） | 6m42s（实测） |
| 改 mapping box / 标签 | 该字集合 | 脏集增量 | 1–3 min |
| 改页级几何（lattice/quad） | 仅受影响页上的字 | 脏页增量 | 2–5 min |
| 新增一页锚点/修正一页 | 该页 | 单页增量 | <30 s |
| 发布前最终确认 | 全量扫一遍 | 全量扫描（不重建） | ~10 min |
| 缓存全部命中 | 无 | 直接复用（装配字体） | 3m52s（实测） |

**缓存键**（必须显式版本化）：`<cache_ver>_<page><half>_<char>_<box>`，`cache_ver = sha8(算法脚本) + sha12(page_geometry)`；缓存按 `work/font/build/cache/<cache_ver>/` 分目录（人工 tag 已废）。
只有键变化才重切；未变字直接命中缓存（当前 ~20 s 完成整字体组装）。

---

## 5. 自动验证（每次构建后自动跑，按变更集裁剪）

| 级别 | 内容 | 耗时 | 何时跑 |
|---|---|---|---|
| L0 单元 | 变更字的 mask 变化、空字形、越界 | <10 s | 每次 |
| L1 快闸 | QA、版本、字符差集+隔离清单、内容闸（binding 复用）、box 均匀性（median+p95）、**字形级框线闸**、**provenance 闸**、**页级几何闸**（候选允许已披露已知债阈值）、包文档/SHA | 3–5 min | 每次构建 |
| L2 全扫 | 缺件扫描、框线逃逸（源图级）、三闸严格阈值、mapping 指派审计 | 5–25 min | 候选定稿 / 发布前 |
| L3 材料 | 文档数字机器校验、SHA、包自检、输入归因 | 1–2 min | 正式打包 |

**闸必须数字化**：每个闸输出 `{pass, flagged, threshold, sample}`；阈值只允许逐版收紧，放宽必须在报告里写明原因并经 owner 同意。阈值=观测值时必须标 `zero_margin` 并披露。

**闸输入绑定（BF-12）**：扫描/内容闸输出旁必须有 `<out>.sha256` sidecar（输入 font/manifest/mapping/geometry/参考字体/脚本 sha + argv + git）；复用前校验，缺失或不匹配 → FAIL（不再按字体 sha 单一缓存静默复用）。

**finalize 纪律（GATE-08/13）**：release_gate 未全部 PASS 时**绝不改动包**（只写 work/lead 失败报告）；finalize 前强制 clean git tree + 缺件/框线扫描 + 内容基线；`--allow-dirty`/`--allow-missing-scans` 仅调试且写进报告。

---

## 6. 人工验证：每轮只给 3 样（少即是多）

输出目录 `work/review/round-<id>/`，**只有 3 种文件**（一条命令生成）：

| 文件 | 回答的问题 | 用法 |
|---|---|---|
| `01-changes-001.png …` | 本轮改动/待确认字**对不对** | 100 字/页；每格三要素：**左上=成品字形（项目字体，被审对象）**、**右上=Unicode 参照字形（霞鹜文楷 OFL，独立字体）+ #编号 + U+码位**、**下=原书裁片**；底部 页/框/来源。只用参照字体渲染标签，**禁止用项目字体做标签**（自举）。只报编号 + `✓/✗/?` |
| `02-random100.png` | 没改到的字**有没有回归** | 全字体固定种子盲抽 100 字，同一版式；发现 ✗ 报编号 |
| `ledger.tsv` | 编号**翻回**具体字/页/框 | 机器可读映射；AI 据此定位修复 |

生成命令：
```bash
python scripts/make_round_pack.py --font work/font/build/KangXiKai-v<ver>.ttf \
  --manifest work/font/build/manifest_v<ver>.json \
  --ledger work/lead/round<id>_ledger.jsonl --outdir work/review/round-<id>
```

**按需再加**（默认不加，避免文件爆炸）：受影响整页预览（几何/mapping 变更时）、前后对照图（发版前）、owner 历史标记字清单（签核轮）。不要为凑「7 张图」生成重复内容。

## 7. 什么时候可以打正式包（owner 已定：**只在里程碑发正式包**）

**里程碑定义**（必须同时满足，才允许开一次正式包）：
1. 累计完成的类级变更集 ≥1 个「结构类」（如裁切/几何/mapping 管线）且 P0 类回归清零；
2. 已知债清单冻结（新增已知债均为 P2 单字级，且逐条登记）；
3. owner 完成一轮批量签核（`04-owner-history` 无新增 ✗）；
4. 字体结构本里程碑内不再变化（后续只有材料/参数小修）。

**正式包硬条件**（缺一不发）

必须**同时**满足（缺一不发）：

1. L1–L3 闸全 PASS：QA、内容闸 0、框线逃逸 0（或经 owner 同意的披露阈值且比上版下降）、几何校验、mapping 指派审计无未解释项、文档数字机器校验；
2. 本轮变更集人工复核：`01-changes` 中 ✗ ≤ 2%，`02-class-sample` 全 ✓（或 ✗ 均已归因+记录为已知债）；
3. `03-regression-random-100`：✓ ≥ 98%；
4. owner 历史标记清单：无新增 ✗；已知债清单与本轮报告一致；
5. 包内容齐全（§8），SHA 覆盖 gate-report，zip 自检通过；
6. 仅此一项允许调高版本号；候选版本号不升。

---

## 8. 正式包必须包含什么（固定清单）

```
release/KangXiKai-vX.Y.Z/
  KangXiKai-Regular-vX.Y.Z.ttf
  manifest-v<tag>.json                 # 字表+来源
  provenance.json / provenance-detail-v<tag>.json   # 逐码位 / 逐字 page/half/box/来源
  coverage.txt / coverage-detail-v<tag>.json        # 覆盖数字 + 分类别统计
  stats.json / qa-report-v<tag>.json / qa-stats-v<tag>.json   # 字体 QA + 构建证据
  gate-report-v<tag>.json              # L1–L3 全闸（含阈值/sample + 扫描产物 sha 绑定）
  content-loss-v<prev>-v<tag>.json     # 内容闸明细（对比上一正式版）
  residual-quarantine-v<tag>.json      # 隔离字 + 理由
  KNOWN-DEBTS.md / known-debt-v<tag>.md   # 已知债（数字须与 gate-report 对账）
  PROVENANCE.md / QA.md / README.md
  RELEASE-NOTES-v<ver>.md / RELEASE-METRICS.md / release-metrics.json
  build_recipe-v<tag>.json             # 可复现构建步骤：从 build_stats 派生 cache_ver / 构建时
                                       #   git commit+dirty / 真实构建时间 / 输入 mapping sha /
                                       #   geometry sha / 算法脚本 sha / 扫描产物 sha（禁止手抄）
  KangXiKai-vX.Y.Z.build_stats.json    # 构建统计原始证据（随包冻结）
  missing_scan_v<tag>.jsonl + .sha256  # 缺件扫描产物 + 输入绑定 sidecar（font/manifest/geometry/
                                       #   bands/build_stats/reffont/脚本 sha；复用前必须校验）
  frame_scan_v<tag>.jsonl + .sha256    # 框线逃逸扫描产物 + sidecar
  FINALIZE.json                        # finalize 只读凭证（font/gate-report/扫描产物 sha、git、
                                       #   created_utc、finalize_version；自指字段见 §8bis）
  review/                              # 本轮人工复核包快照（round-005：owner 亲标 11 字 + 邻字 10）
  SHA256SUMS
release/KangXiKai-vX.Y.Z.zip
release/KangXiKai-vX.Y.Z.FINALIZE.json  # 包外 detached 终验：sha_final_ok/zip_ok/实际 zip_sha256/
                                        #   package_finalize_sha256（自指不可内嵌，故不在包内）
release/KangXiKai-vX.Y.Z.zip.sha256     # 实际分发 zip 的 sha256（一行 shasum 格式）
```

> **§8bis finalize 证据链（v2.6.3 T4 起）**：`release_gate.py` finalize 为 **staging 原子流程**——
> 全部写包动作（终版 gate-report / FINALIZE.json / SHA256SUMS / zip）先在同一文件系统的临时目录完成并
> 全验（SHA 覆盖、目录==zip、doc_check、verify_release），通过后才原子替换包目录与 zip；任一步失败
> **零写包**（`--inject-fail sha|zip|pre-swap` 可在 `/tmp` 做失败注入自测）。包内 `FINALIZE.json` 的
> `sha_final_ok/zip_ok/zip_sha256` 因自指不可内嵌而记 null + scope 说明，实际终验值只写包外 detached
> `release/<pkg>.FINALIZE.json` 与 `release/<pkg>.zip.sha256`；机器验证用 `scripts/verify_release.py`
> （目录==zip、SHA256SUMS 覆盖全部非 SHA 文件、无多余文件、FINALIZE 字段与 sha 一致）。
> `release/RELEASE-INVENTORY.tsv` + `package_summary.json` 由 `scripts/release_inventory.py` 现场计算生成
> （zip sha / 文件数 / finalize 状态 / 真实 UTC），禁止手写。

> 生成方式（2026-11-13 起，v2.6.3 更新）：`scripts/make_release_extras.py` 生成 staging（manifest/
> coverage/provenance/QA/known-debt/RELEASE-NOTES/PROVENANCE.md/QA.md/build_recipe/build_stats/扫描
> 产物+sidecar/review 等），再由 `scripts/font_package.py --extra-dir-flat <staging> --extra-dir <review>`
> 打包并重算 SHA256SUMS/zip；`release_gate.py` finalize 后必须 `check_release_docs.py`（数值对账 +
> 篡改测试）与 `verify_release.py` 双 PASS，再跑 `release_inventory.py` 更新清单。

## 9. 如何决定下一轮修改方向（闭环）

每轮结束自动产出 `backlog/defects-<date>.jsonl`（缺陷源：owner 标记、各闸 flagged、mapping 审计、缺件扫描），AI 做 triage：

| 优先级 | 判据 | 处理 |
|---|---|---|
| P0 类级回归 | 同一类问题 ≥3 例且可复现 | 下一轮必须修，开变更集 |
| P1 系统性债 | 单类占比 >0.5% 或影响高频字 | 排入下轮/下下轮 |
| P2 单字/低频 | 无类特征 | 只入已知债，不做单字补丁 |
| P3 标签疑点 | 裁片与标签不符 | 交 owner 标 ✓/✗/? 后处理 |

**方向决策权**：AI 只维护 triage 与建议，owner 每轮只看一页 `backlog 摘要`（P0/P1 列表 + 影响字数 + 建议顺序），确认或调整后 AI 开下一轮变更集。

---

## 10. 版本与文件规范（立即生效）

- 候选：`work/font/build/f-<date>-<n>.ttf` + `work/review/round-<id>/`，**不打包**；
- 正式：仅 `release/KangXiKai-vX.Y.Z/`，每次打包前先自动校验 §7 清单；
- 失效版本：移入 `release/_withdrawn/` 并注明原因（v2.5.9 已如此处理）；
- 版本号语义（owner 2026-11-14 明确）：
  - **v2.6.x = 2.6 系列补丁线**：修复/口径/材料类改动持续发 v2.6.3、v2.6.4……**不要求 v2.6.3 一次做完所有计划项**；
    计划项未完成就顺延到下一个 patch 号发布，不阻塞本系列小版本；
  - **minor（v2.7.0）只留给结构性新增**（如 GAN / 带状扫掠生成回退、字表口径重大变化）；
  - 候选不占版本号；正式包才递增。

---

## 11. 立即执行的动作

1. 现有 `release/` 里未签收的 v2.6.x 全部标记为 withdrawn，只保留上一正式基线（v2.5.8）供对比；
2. 下一轮以**变更集 cs1 = 页级几何校验 + mapping 指派审计**开始：先出 50 字级小样本对照，再决定是否全量；
3. 每轮只交：`candidate .ttf + round-<id>/ 7 张图 + 1 页摘要`，不再交「半个正式包」；
4. 打包脚本改为「清单校验 + 一次性打包」，正式包 5 分钟内完成，不再 20–30 分钟。

## 10bis 每版必须留下的记录（防失忆）

每完成一个候选/正式版本，必须同时产出以下三样，缺一不发版：

1. `docs/VERSION-HISTORY.md` 追加一行：版本 / 日期 / 类型（探索/结构/修补/材料）/ 本版变更 / 章节目录 / 现状；
2. `work/changesets/cs-<id>.jsonl`：本版变更集（scope/root_cause/fix/verification，见 §2）；
3. `work/lead/version-artifacts-v<ver>.jsonl`：本版涉及的 mapping/scan/字形/复核文件清单
   （路径 + sha256 或 大小+mtime），供未来判断「这一版的痕迹是什么」。

另：发布包 `build_recipe.json` 必须记录 `git_commit / git_dirty / cache_tag / 扫描数字来源`。
