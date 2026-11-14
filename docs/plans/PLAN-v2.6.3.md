# PLAN 2.6 补丁线（下一批 v2.6.3 起）

> 本文件是 **v2.6.x 系列（2.6 补丁线）的滚动计划**，不是「一次做完才发版」的 v2.6.3 里程碑清单。
> 版本策略（owner 2026-11-14）：**v2.6.x = 2.6 系列补丁线**——修复/口径/材料类改动持续发
> **v2.6.3、v2.6.4、v2.6.5……**；一批没做完的计划项**顺延到下一个 patch**，不阻塞本系列发版。
> **v2.7.0 只留给结构性新增**（GAN / 带状扫掠生成回退、字表口径重大变化）。
> 只有 `docs/WORKFLOW.md` §7 的里程碑硬条件全部满足时，才把**当时那个 patch 版本**定为里程碑正式版；
> 在此之前，2.6.x 每个 patch 都是「披露已知债的小版本」。

## 0. 已发布基线

- **v2.6.2 正式包（2026-11-14）**：`release/KangXiKai-v2.6.2/` + `.zip`；
  font sha256 `a8bb87d9c4a623d5fe88ae55c2f710a36827052c7cd3594fe70113f56ca18d5b`，
  zip sha256 见 `release/RELEASE-INVENTORY.tsv`；finalize 17/17 PASS；SHA 覆盖 32 文件（含 `review/`）。
- 覆盖：基本区 48.91%（10,267/20,992）、目标表 61.97%（10,267/16,567）、缺口 6,300；
  字形框线 0、框线逃逸 0、内容 18/35、缺件 165、empty_assign 1,173（后两项随包披露）。
- 历史预览包 `release/_preview/` 保留备查。

## 1. 下一批：v2.6.3（当前进行中）

**本批只承诺做这两项；做完即出 v2.6.3，不等其它项。**

1. **BF-06 缺件 165**（重定义，T1 已执行）：构建侧插桩+独立扫描对照已定位主因=**扫描侧 precut crossing 过滤 fail-open（E40）**并修复：v2.6.2 字体重扫 **165→19 字/20 组件**（error 0）；残余 17 prune_loss + 5 clean_ink_loss（旧集）+ 3 scan 残差 → 类级修/披露；BF-06 修复完成前保持 open；不得再按「165/prune 边缘口径」调参；
2. **BF-54 标签错配 11 字**：按页重定位真迹字头（OCR 交叉核对），无法定位的移出字表并逐字披露；
3. 文档/版本策略（本文件与 WORKFLOW §10）随批提交。

**v2.6.3 发布条件**：上述完成项重建 → 快闸/全闸 → 复核包（01/02/03）→ clean-tree `font_package` → finalize。
**不要求**本批完成 empty_assign、D23、里程碑硬条件——它们留在 §2 池子里滚动。

## 2. 后续 patch 候选池（滚动，每个 patch 取已完成的一批）

### A. 数据/覆盖
- empty_assign 1,173：669 个 vol 01–12 有 lattice 半版重跑检测/映射（先 01_0006 L「一」）；
  504 个 vol 00/13 口径待 owner；40 个无 lattice 核对；交付 mapping v272+ 与覆盖重算；
- 高频缺 23（一/王/法…）与 A1 同批重定位；7 个异体口径字给 owner 结论；
- 缺口 6,300 策略（BF-41）：headword-only 不补 vs D19 重定位，写入 DECISIONS。

### B. 口径（需 owner）
- D23 内容判据：改「源墨保真度」（字形投影 vs 自身 source ink 配准 IoU）+ 基线；
- 缺件口径：E40（扫描侧 fail-open 修复后 165→19；残余 prune_loss 17/clean_ink 5/scan 残差 3）；扫描闸阈值模式（BF-10）；
- 页几何 empty_assign 披露阈值口径（与 §A 联动）。

### C. 闸/流程/材料（可执行）
- BF-10/17/18/24/44/47/49/51/25/28/36/38/39/42：闸契约、材料数字同源、三件套强制、
  扫描/构建归因、audit 现状文档、脚本 keep/archive、降级标记、文档清理、check_terms、milestone.json、new_candidate；
- 版本指标补全（v2.5.8 缺件/框线未按现行口径重跑、v2.6.1 相对变化字数未实测）；
- 标签审计方法：参考字体 IoU 噪声大 → OCR 交叉核对（`work/lead/ocr_*`）。

### D. 里程碑硬条件（满足后，当批 patch 定为里程碑正式版）
- BF-29 隔离 9 字结论；BF-30 100 字 owner 签核；BF-31 部界锚点（09–11/13 卷）；
  BF-32 标签精度分层抽样披露；BF-33 DATA 影印/扫描者/许可细节进包 PROVENANCE。

## 3. 每个 patch 的发布流程（固定）

```
认领本批 item → 变更集 cs-*.json → 构建（全量/缓存）→ 快闸 fast_gate
→ 全闸 release_gate（披露阈值写入 gate-report）→ 复核包 work/review/round-*
→ owner 抽看 → clean-tree font_package → release_gate finalize → 冻结 v2.6.N
```

- 每批必须：`docs/VERSION-HISTORY.md` 一行 + `work/changesets/cs-*.json` + `work/lead/version-artifacts-v2.6.N.jsonl`；
- 已知债只增不减的批次不发：新回归先修或降级为 ACCEPT 并写明理由；
- patch 版本号连续递增（v2.6.3 → v2.6.4 → …），候选不占版本号。

## 4. 不做什么

- 不为了「一次全绿」把 2.6 系列卡住不发；也不把结构性生成（GAN/带状扫掠）塞进 2.6.x——那是 v2.7.0；
- 不做单字补丁；不补假字形（D15）；不把「切后擦」重新引入（D22）；不绕过闸降低阈值而不披露。
