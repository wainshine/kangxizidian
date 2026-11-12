# WORK-MAP · `work/` 探索痕迹地图（为什么不能盲删）

> owner 原则：**`work/` 里的很多历史探索痕迹不能删**——要能回答「哪版是全新探索、哪版只是挑了几个图修补」。
> 本文给出目录地图 + 版本↔痕迹对应 + 安全清理规则。**清理前必须先对照本文并生成留档清单。**

---

## 1. 顶层目录地图（2026-11-12 实测）

| 目录 | 大小 | 文件数 | 内容 | 可重建性 | 建议 |
|---|---|---|---|---|---|
| `work/models` | **13G** | — | PaddleOCR / 检测等模型与权重 | 可重下但很慢 | **保留**（重下成本高） |
| `work/font` | **22G** | — | 字体构建：`build/`（历史 TTF 63 个 + **cache 约 34 万文件/约 18G**）、crops/glyphs/demo/qa | cache 可重建（**重切全量 ~9min/10 workers**，但会失去各代构建痕迹） | **保留 build/*.ttf 与 qa**；cache 按 tag 清理（见 §3） |
| `work/map` | **2.7G** | 66 个子版本 | mapping 探索：`charalign2..16`、`ca16*`、`bu_*`、`v3full`、`split*/iter*` 等 | 不可重建（历史探索） | **保留**（这是「探索痕迹」主体之一） |
| `work/lead` | **1.3G** | 598 | 每版扫描/修复/审计 jsonl 与诊断图：`content-loss-*`、`missing/offset/frame_scan_*`、`repair_overlay_v256`、`defect-ledger-v258`、`mapping_verified_all*`、`page_geometry.jsonl`、`mapping_block_v270` 等 | 部分可重跑（耗时长），历史结论不可重建 | **保留**（版本证据核心） |
| `work/seq` | **867M** | 43 | 正典序/书眉/对齐数据、pkl 中间件 | 部分可重建 | 保留；pkl 可再生成但慢 |
| `work/t00` | **851M** | — | T0 阶段页面渲染缓存 | 可重建（慢） | 可清理（建议先留 30 天） |
| `work/detect2` | **525M** | — | 检测器 v2 输出 | 可重建 | 同上 |
| `work/t2` | **418M** | — | 对齐/DP/校订中间结果（`pdf_map.json` 现行依赖） | **部分不可重建** | **保留**（`pdf_map.json` 是现行输入） |
| `work/paddlex_cache` + `work/uvcache` | 1.4G | — | 工具缓存 | 可重建 | 可清理 |
| `work/review` | 227M | 97 | 人工复核图：缺陷历史台账、owner 标记核验表、round 复核包 | 可按脚本重生成 | 保留（复核证据） |
| `work/t1`、`work/audit-v2419`、`work/audit-v254` 等 | 小 | — | 检测器/审计现场 | 历史证据 | 保留 |

---

## 2. 版本 ↔ 痕迹对应（回答「这版是探索还是修补」）

| 版本段 | 性质 | 痕迹/证据（示例路径） |
|---|---|---|
| v0.3–v1.2 | 探索（挖字/OCR/指纹） | `work/font/build/KangXiKai-v0.*`、`KangXiKai-v1.*`；`work/map/charalign*` 早期；`work/seq` 书眉/对齐中间件 |
| v2.0–v2.3 | 探索+结构（VLM 突破/注文过滤） | `work/map/v3full`、`charalign9..16`；`work/font/build/KangXiKai-v2.0*..v2.3*`；`work/t2/alignment*` |
| v2.4.0–v2.4.22 | **大量修补**（切框/清理/闸，逐类缩小） | `work/lead/*v24xx*.jsonl`（content-loss/repair/scan）；`work/audit-v2419`、`work/audit-v254`；`work/review` 早期核验图 |
| v2.5.0–v2.5.8 | 结构+材料（2×2 格块/门禁/发布） | `work/lead/mapping_verified_all*.jsonl`、`repair_overlay_v256.jsonl`、`scan_missing/offset_*`、`frame_escape_scan_v258`、`defect-ledger-v258`；`work/font/build` 对应 TTF |
| v2.6.0 | 架构（切前排除，但 restore 层失败） | `frame_escape_scan_v260`、`precut-restore` 相关 jsonl、`mapping_verified_all40`、`work/review/defect-history-v260` |
| v2.6.1（当前） | **重构后首版（全量）** | `work/lead/page_geometry.jsonl`、`mapping_block_v270.jsonl`、`work/font/build/manifest_v261.json`、`cache v350`、`work/gates/*`、`work/lead/fast-gate-v261.json`、`work/review/round-001` |
| 已删除版本 | 元数据留档 | `audit/RELEASE-HISTORY.jsonl`（52 版）+ `audit/release-evidence/`（4 版闸报告+SHA） |

**判断「探索 vs 修补」的经验规则**
- **探索版**：有新的 mapping 目录（`work/map/<新方案>`）、新算法脚本、负结果记录（如渲染模板判别力负结果）；
- **修补版**：只有 `work/lead` 下新增的扫描/修复 jsonl + `work/font/build` 新 TTF，没有新 mapping 方案；
- **结构版**：mapping 方案换代 + 全量重建 + 闸口径变化（如 v2.4.16 的 2×2、v2.6.1 的 block mapping）。

---

## 3. 安全清理规则（先出清单，再删）

1. **不可删**：`work/map`（历史探索）、`work/lead` 的扫描/修复/审计日志、`work/font/build/*.ttf` 与 qa、`work/review`、`work/seq` 正典序/书眉数据、`work/t2/pdf_map.json`；
2. **可删但记录**（重建成本已知）：
   - `work/font/build/cache`：按 tag 清理，仅保留 **v350**（当前）+ 需要回归的 tag；清理前统计各 tag 文件数并写入留档；
   - `work/t00`、`work/detect2`、`work/paddlex_cache`、`work/uvcache`：可重建；
3. **每版留档**：清理/发布前生成 `work/lead/version-artifacts-v<ver>.jsonl`：该版涉及的 map/lead/font/review 文件清单 + sha256（大文件可只记路径+大小+mtime）；
4. 任何删除动作必须先 `--dry-run` 出清单给 owner 确认。

---

## 4. 与流程的关系（防止再次失忆）

- 新会话恢复顺序：`docs/PIPELINE.md` → `docs/WORKFLOW.md` → `docs/VERSION-HISTORY.md` → 本文 → `audit/SELF-AUDIT-2026-11-12.md` → 当前轮 `work/changesets/`；
- 每次变更集结束：更新 `docs/VERSION-HISTORY.md` + 生成 `work/changesets/cs-*.jsonl` + `work/lead/version-artifacts-v<ver>.jsonl`（见 `docs/WORKFLOW.md` §10）。
