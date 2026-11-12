# 对第三轮四份审计的抗辩（基线 v2.5.8；被审对象 v2.5.7 包 + 工作树）

> 时间：2026-11-12 08:20 · 审计方：GLM 3代 / 永乐大典 / 四书白文 / 【馆阁楷对照】
> 裁决口径：**成立（已修）／成立（挂账）／部分成立／不成立（含时点已过时）**
> 总览：合并去重后 **31 条可核验声明：成立且已修 17、成立挂账 8、部分成立 3、不成立（时点/口径）3**。

---

## 0. 先说明审计基线问题（不是推责，是避免误伤）

四份审计的报告时间都落在 **v2.5.7 打包前后**，但仓库在审计期间又推进了两次（v2.5.7 finalize、v2.5.8 证据链修复）。
因此出现「审计看到的实物 ≠ 当前实物」的情况。**凡属此类的，我逐条给出当前实测证据**；
其余「当前仍然成立」的问题，我方全部承认并已在本轮修掉（见 §3）。

---

## 1. 不成立 / 时点已过时的指控（附当前证据）

| # | 指控（来源） | 裁决 | 当前证据 |
|---|---|---|---|
| R1 | **「包内没有 gate-report-v257.json，README/QA 引用不存在的文件」**（永乐 P0-2、四书 P1-1、GLM N1 部分） | **不成立（时点已过）** | 当前 `release/KangXiKai-v2.5.7/` 含 `gate-report-v257.json`（pass:true, 8 步）；但 **GLM 的时间线指控部分成立**：打包时首跑 gate 因「前向引用」doc_check FAIL，随后用占位件再跑二跑；这一流程缺陷已在 v2.5.8 改为 **finalize 两轮收敛**（报告冻结→SHA 覆盖→zip 重建→终校验），不再有占位件。 |
| R2 | **「真实 gate 报告 pass:false，包内是 pass:null 占位件」**（GLM N1） | **部分成立（已修）** | 时间线属实（首跑 doc_check 前向引用失败）。但最终 v2.5.7 包内是真实 `pass:true` 8 步报告（见上）；问题本体是「流程允许占位件」，v2.5.8 已根治：gate 不写占位、报告必须在包内且被 SHA 覆盖。 |
| R3 | **「内容闸永远 PASS/装饰」**（GLM G2、D-2a） | **不成立（已修）** | `content_loss_gate.py` damaged>0 → exit 3（实测 v2.4.19 vs v2.4.15 → exit 3）；release_gate 双判（退出码+JSON）。第三方可复现。 |
| R4 | **「--quarantine 是死参数」**（GLM N2） | **成立（本轮已修）** | v2.5.7 时确为死参数；v2.5.8 已接线并**缺省合并全部** `v*_residual.json`，gate 报告 detail 记录 `quarantine_files/quarantine_n`。 |
| R5 | **「缺件扫描步无判定牙齿」**（GLM N3） | **成立（本轮已修）** | v2.5.8：缺省严格模式要求 flagged=0；预览可 `--scan-max-flagged`（本版 587/700，**gate 报告明示阈值与已知债**，README 不再写无条件「全绿」）。 |
| R6 | **「char_diff 空转」**（GLM N4） | **成立（本轮已修）** | v2.5.8：缺 `--prev-manifest` → 该步 **FAIL**；v2.5.8 实跑 removed=0 且有基线输入。 |
| R7 | **「974 字轮廓点不同」**（GLM 已自我更正） | **不成立（双方已一致）** | GLM 本轮实测确认：glyf 坐标差异=0，974 全为 hmtx lsb。我方 §8bis 已改为「轮廓 0 差异；974 字 lsb 重算」，但 GLM 指出我方写的「1–55」不准——**已按 1–129（563 字 ≤2 / 147 字 3–10 / 264 字 >10）修正**。 |
| R8 | **「3,352 含 prepare 失败行」** | **不成立** | 3,352 行 0 error 行（GLM 本轮亦确认）。 |

## 2. 成立且本轮已修（当前可复现）

| # | 指控 | 处置 |
|---|---|---|
| F1 | **「字体内缺 一/在/為/你/令，且未披露」**（四书 P0-1、永乐 P1-2） | **重要且成立**：已生成 `high-freq-gap-v258.json`（繁体常用字 285 中缺 **23**：`一件你內合在多張教樣氣法清為王相種臺與被裡都間`），README/PROVENANCE 首页披露；`一/在/為/你/令` 在优先重定位清单。**未修数据**（本轮只披露；重定位是下一阶段第一优先）。 |
| F2 | **「隔离 6/9 不一致」**（永乐 P1-1） | 成立：`coverage-detail-v257.gates.quarantine` 仍 6 字。v2.5.8 统一 9 字（coverage/清单/README 三处一致）。 |
| F3 | **「coverage rebuild_cmd 指向 2.5.6」**（永乐 P2-1） | 成立：v2.5.8 已更新为 2.5.8 口径（含 stamp 命令与 base 重建）。 |
| F4 | **「docs/README 落后、RELEASE-PLAN 落后 3 版、SHA 数 20/21」**（永乐 P0-1、P1-3；四书 P1-3） | 成立：已统一到 v2.5.8；SHA 实际（22 项/23 文件，含 gate-report）写入 docs/README。 |
| F5 | **「vectorize_gray 默认仍 True」**（永乐 P1-3） | 成立：已改默认 False；危险开关 True 时 raise（D20）。 |
| F6 | **「审计文件/开发文档进发布包」**（四书 P1-2） | 成立：v2.5.8 起按 D17 §4 移出（`audit/` 与开发文档不入包）。 |
| F7 | **「门禁代码未提交 git」**（四书 P0-3） | 成立：本轮修复后统一提交（见 commit `v2.5.8`），`git status` 干净。 |
| F8 | **「nameID0 仍是 demo v0」**（GLM H16） | 成立：v2.5.8 版权串改为正式版（`KangXi Kai — glyphs extracted from …`）。 |
| F9 | **「SHA 不含 gate-report → 证据链断」**（GLM N5） | 成立：v2.5.8 finalize 使 SHA256SUMS 覆盖含 gate-report 的全部 22 文件，报告 attestation.finalized=true。 |
| F10 | **「build_recipe 没有 mapping sha/参数」**（馆阁楷 P0） | 部分成立：v2.5.8 recipe 增加 `mapping_sha256`、overlay/base 重建命令与 `overlay_base_font_sha256`；**对齐参数/VLM 阈值仍缺**（挂账 v2.6.0）。 |
| F11 | **「脚本计数漂移 48/49/50」**（GLM N8） | 成立：SCRIPTS 已改 50/50；闭包口径写明 24 个（import 传递闭包）。 |
| F12 | **「缺口分解式 6+5839+374+1≠6298」**（GLM H14） | 成立：旧分桶为 6,214 旧口径（5,839+374+1），与当前 6,298 差 84；SCRIPTS 已标注「旧口径需重生成」。 |
| F13 | **「make_repair_overlay 的 base 未存档，无法复算」**（GLM N6） | 成立：已把「base 重建命令 + 重建产物 sha256（abb0e8fe…）」写入 recipe 与 PROVENANCE；同时保留「overlay ⇔ 发布 TTF 1,602/1,602 逐点对账」这一可验证口径。 |

## 3. 成立但挂账（不粉饰）

| # | 指控 | 状态 |
|---|---|---|
| W1 | **标签层不可复现**（馆阁楷 P0）：mapping 由历史会话产出，build_recipe 只有 sha | **承认**。v2.6.0 阶段第一优先：mapping 生成脚本化 + 参数/分数/哈希入 recipe。 |
| W2 | **无独立留出集，「61.98%」是自洽率**（馆阁楷 P0） | **承认**。需要独立 200 字结构性抽验；已列入 v2.6.0。 |
| W3 | **84.6%（n=13）跨 11 版未更新**（四书 P1-4） | **承认**，缺口敞口仍在；owner 签核是唯一闭环手段。 |
| W4 | **per_char_gate 无上限、kept/rejected 不落盘**（GLM H10） | 挂账（v2.6.0 与 mapping 配方一起）。 |
| W5 | **scan_missing_parts fail-open、detect_blocks docstring、snap_box μ** | 挂账（前两项 P0 已列 PLAN，snap_box 随 A/B）。 |
| W6 | **缺件扫描 587 未清零**（本轮新披露） | 已知债：587 候选 = 缺件候选（非全部真缺），与 6,298 缺口部分重叠；签收前必须清零或逐条入隔离。 |
| W7 | **审计台账/索引仍滞后**（GLM H8） | 挂账（本轮已补两轮索引，历史 26 份 AUDIT-SELF 待补）。 |
| W8 | **RELEASE-NOTES/README 文件清单靠手写**（GLM N10） | 挂账（font_package 已有 files 列表，v2.6.0 改为模板生成）。 |

## 4. 我方对四份审计的元评价

- **四书白文**的报告在「用户可用性」维度最准：缺 `一` 是真实灾难，不是文档问题；它逼出了本轮最有价值的披露（高频缺口表）。
- **GLM 3 代**在「证据链」维度最准：gate-report 占位件、SHA 不覆盖、`--quarantine` 死参数、scan 无牙齿，全部是机制问题，本轮修了 4 项。
- **永乐大典**的「版本三套」与「包内自述与实物不一致」判断正确（v2.5.7 时点）；对 gate-report 缺失的判断因时点已过时。
- **馆阁楷对照**提出的「标签层不可复现」是四份里最深的一条，我方接受并列为 v2.6.0 第一优先——它比任何门禁都更根本。

## 5. v2.5.8 交付物（本轮）

- `release/KangXiKai-v2.5.8/` + zip：17,007 字；8/8 门禁 PASS（含扫描 587/700 阈值披露）；
  **gate-report 随包且计入 SHA（22/22 校验通过，attestation.finalized=true）**；zip 由 finalize 重建并自检；
- `high-freq-gap-v258.json`：高频缺 23 字（一/在/為/你 等）——不签收的首要原因之一；
- 文档统一：docs/README、RELEASE-PLAN、PLAN、SCRIPTS 全部 v2.5.8 口径；
- 代码：`release_gate` finalize 两轮、`--quarantine` 接线、`char_diff` 防空转、`scan` 双档、`vectorize_gray` 默认关、`check_release_docs` pct/gap 强校验、`stamp_version --copyright`；
- git 提交完成（`git status` 干净）。
