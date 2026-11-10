# 自审计报告（文档与审计目录校订 + v2.4.2 基线）  [2026-11-10 11:30]

自查范围：
- `docs/` 全部 19 份文档（本轮按「当前代码为基准」逐份校订后的状态）；
- `audit/` 全部 9 份文件（外部报告 3 / 回应 3 / 自审计 1 / 索引 / 核验台账）；
- 发布基线 `release/KangXiKai-v2.4.2/`（文件/数字/冻结状态）。
全部结论可复现；抽样命令见文末。

## 一、通过项

| 检查 | 结果 |
|---|---|
| 文档状态标记 | 19/19 份均有「文档状态/现行/历史/编年」标记（0 缺失） |
| 索引完整性 | `docs/README.md` 覆盖全部 19 份；`audit/README.md` 覆盖全部 9 份（含新增核验台账） |
| 路径引用 | 无「非历史」断链；仅存的旧路径均为**已登记的历史引用/迁移条目**（见 `audit/README.md` 路径迁移表） |
| 时间戳 | docs+audit 全部无未来时间戳（0 命中） |
| 关键数字 | 「17,121」在 README/RELEASE-PLAN/DATA/DECISIONS/COUNTS/V3-STATUS/SESSION-HANDOFF 全部一致；覆盖 10,348 / 62.46% / 缺口 6,219 与 release `stats.json`/`coverage-detail` 一致 |
| 决策现行性 | D15（headword-only）/D16（自动标签+精度敞口）/D17（发布流程）/D18（版本号）齐备；D3/D4/D5/D6/D10-D13 均已加「被取代」内联标记 |
| 审计台账证据 | 芡/芍 框号不同页（12_0234 vs 09_0008）→「芡=芍」标 ❌ 有据；v2.3.1 挂起 195/回填 241/圈号 4、v2.3.2 smallsrc 356、v2.4.0 剔除 397/缺口 6,219 均与产物一致 |
| 发布基线 | v2.4.2：cmap 17,121、provenance 全 real、**SHA256SUMS 18/18 OK、0 FAILED**（未受影响） |
| 元数据声明 | RELEASE-PLAN 的 name5/fontRevision 2.42/cmap 格式 4+12/unicodeRange2 0x38000000/codePage 0x140000 与字体实测一致 |
| 空值/小字/同框 | v2.4.2 manifest：smallsrc 残留 **0**、同框冲突 **0** |

## 二、发现的问题与处置

### P2-1 文档数量声明偏差（已修）
`docs/DATA.md` 写 `work/models/` 约 13.5 GB，实测 `du -sh` = **13 GB** → 已改为「约 13 GB」。
其余声明（PDF 12 GB / 3,869 页 / 48,710 行 / 46,815 唯一字 / 16,567 唯一基本区 / 42,302 条）均复核实测一致。

### P2-2 历史路径引用（不修，已登记）
审计记录中保留的 `docs/AUDIT-RESPONSE-3.md`、`work/lead/alt_verify.json`、`docs/QA.md` 等旧路径，
是**外部审计原文/历史引用的留痕**（记录不改写原则），已在 `audit/README.md` 的路径迁移表统一对照，不构成断链。

### P2-3 索引维护流程（记录）
新增文档必须同步更新 `docs/README.md` / `audit/README.md` 索引；本轮之后把这条写入
`docs/DECISIONS.md` D17 的发布检查清单（已含「文档同步」项）。

## 三、结论

文档/审计目录与当前代码（v2.4.2）**一致**：无 P0/P1 问题；1 个 P2 大小声明已修，
其余为历史留痕（已登记）。
本轮变更仅为文档与审计材料 → 按 D18 以 **patch** 版本发布（v2.4.3，字体内容不变，仅内部版本号/材料更新）。

## 四、复算抽样

```
# 发布基线冻结
cd release/KangXiKai-v2.4.2 && shasum -a 256 -c SHA256SUMS        # 18/18 OK
# 文档状态/断链/未来时间
.venv/bin/python - <<'EOF' ... (见本轮自审计脚本) EOF
# 台账数字
python -c "import json;print(json.load(open('work/lead/v231_fix_report.json'))['suspended'])"
```
