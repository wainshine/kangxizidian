# 外部审计报告 · v2.5.4（第二轮：几何体检/切偏修复版）

- 被审对象：`release/KangXiKai-v2.5.4/`（19 文件）与 zip、`scripts/` 全部 188 个 .py（HEAD `20e7ae5`）、v2.4.20→v2.5.4 新增/重写代码（scan_*/repair_* 管线、content_loss_gate、detect_blocks、build_release、font_build 重写版）、`docs/` 与 `audit/` 现行文档、六份新 AUDIT-SELF（v2.4.22/v2.5.0–v2.5.4）与两份新 AUDIT-RESPONSE 的声明
- 审计方：代码审计 2 代（第二轮；lead + release-verifier + code-auditor + docs-auditor）
- 审计时间：2026-11-11 22:00+（Asia/Shanghai）；上一轮审计（v2.4.19）于同日 15:20 交付
- 方法：发布包逐文件校验 + fontTools 实测 + QA 全量复跑（256px 渲染 17,007 字）+ content_loss_gate 复跑 + canonical.jsonl 独立复算 + 版本序列差分 + 静态通读/引用扫描/py_compile + 上轮发现修复落实矩阵复查
- 证据底稿：`work/audit-v254/release-verify.md`、`work/audit-v254/code-audit.md`、`work/audit-v254/docs-audit.md`（本报告为三份底稿的汇总与裁决）
- 分级沿用项目惯例：P0=发布阻断级；P1=重要须限期修；P2=轻微/建议
- 本报告只发现问题与改进方案，未修改任何被审文件

---

## 〇、一句话总评

**字体数据与校验链依然过硬（SHA/zip/cmap==manifest/QA 全量复跑/覆盖率独立复算全部 PASS，六份新自审计数字全部可复算、无手抄）；但本轮出现两个新 P0——字体内部版本停在 2.5.1（发布 2.5.4，修复链不重盖章+打包链不校验），以及上一轮 P0 的同类问题在 QA/PROVENANCE 上复发（v2.4.22 旧正文五版只改标题）。根因同源：打包链只机器校验 stats/README 类产物，字体内部元数据与 QA/PROVENANCE 文本不在校验范围内；且 v2.5.2–2.5.4 的核心 QC 步（347/478 逐字校验）无脚本实现、无落盘，不可复现。**

---

## 一、判定总表

| ID | 级别 | 位置 | 问题 |
|---|---|---|---|
| V1 | **P0** | TTF name 表 / fontRevision | 字体内部版本停 2.5.1（name[3]「…2.5.1」、name[5]="Version 2.5.1"、fontRevision=2.51），发布版本 2.5.4。根因链：v2.5.1 是最后一次 font_build 全量构建（唯一盖章点）；v2.5.2–2.5.4 全走 repair 脚本 TTFont 原地 save 不重盖章（repair_offset.py:93-111 等）；font_package.py:432 无 name_version==--version 校验；font_qa.py:208 的 fontRevision_ok 只比对 head↔name5 内部自洽 → 假通过。用户字体管理器将显示 2.5.1，四个发布物无法靠元数据区分 |
| V2 | **P0** | 包内 QA.md / PROVENANCE.md | 数字失真复发：与 v2.4.22 版 diff **仅标题一行**（v2.5.0–2.5.4 五版同一份正文）。QA.md 声称 cmap==manifest（17,013，实测 17,007）、参考闸 pre 1,226→3（v2.5.1 起实为 1,222→6）、内容缺失 vs v2.4.21/2.4.15（本版应为 vs v2.5.3）；PROVENANCE.md 声称 17,013 字、引用包内不存在的 provenance-detail-v2422.json、谎称「从头重建 cache v310 全量重矢量化」（v2.5.4 实为增量修复，现行缓存键 v312_）。上一轮 P0（R1）修好 README 后，同类问题在 QA/PROVENANCE 复发，且 QA.md 是硬闸声明文档 |
| V3 | P1 | content_loss_gate.py | 「内容缺失闸」对字符整体移除失明：v2.5.0→v2.5.1 移除 6 字但 content-loss-v250-v251.json=[]——被移除字渲染 .notdef，墨量比原字还大（刃 ratio=1.73、法 1.64）恒不触发；闸只覆盖「同字掉墨」，不覆盖「字表缩水」。另：exit 恒 0 从不阻断、逐字吞异常+基线路径错→假 PASS、docstring 判据与代码不一致（P2） |
| V4 | P1 | repair_offset 的 QC | 「逐字校验（墨量≥95%、IoU≥0.75）：347 保留/478 回退」在 scripts/ **无任何实现、无落盘证据**（全库 grep 0.95/0.75 零命中）；repair_offset.py 替换循环只查 res["ok"]。v2.5.4 核心 QC 步为会话内联命令，不可复现（违反 QA §4「数字由脚本生成」） |
| V5 | P1 | repair_* 三脚本 | 修复不回写 manifest/mapping/cache：实测 manifest-v251 vs v254 全部 box 零差异、cache v312 仍是修复前旧轮廓 → **任何全量重建（bump v313）会静默回滚 1,109+347 字修复**；TTF/cache/manifest 三处状态分叉 |
| V6 | P1 | AUDIT-RESPONSE-BUILD-FROM-SCRATCH 声明 | 「清理链无损化」与代码矛盾：strip_border_lines（edge-band 长细组件删除+孤立直线删除）仍在 font_norm.py:724 无条件运行；mask_to_block 硬擦除块外全部墨且无擦除前后墨量对比、lattice 拟合失败→静默无掩膜（P2）。与造成 v2.4.16–19 P0 的删除启发式同类，残余风险未披露 |
| V7 | P1 | v2.5.x 构建配方 | build_recipe 全部缺失（仅 v2.4.21 一份）；build_release.py 声称「固化全序+输入/输出 sha256」，实际只记命令串与 TTF sha256、不做打包，v2.4.22 起未再使用 → 「构建可复核」声明无 artifact 支撑 |
| V8 | P1 | 6 字剔除披露 | v2.5.0→v2.5.1 移除 刃/榍/法/紆/総/荹（含常用字「法」「刃」），RELEASE-NOTES-v251 **有披露**（「参考闸 1,222→6 隔离」）但零解释（为何常用字被隔离、复核结论、重定位计划），v2.5.2–2.5.4 各版不再提及；docs/README:10 称隔离清单随包，v2.5.4 包内已无该文件（仅 v2.5.1 包有）→ 披露链断。另 仟/禦/絞 于 v2.4.21→v2.4.22 剔除（RELEASE-NOTES-v2422 有披露） |
| V9 | P1 | release PROVENANCE.md 406B | 精度敞口披露回归：原「VLM 指纹 84.6%、n=13、CI 57.8–95.7%、错标敞口 429–4,188（点估计 1,500）」整段丢失；docs/README:12 与 DECISIONS D16 仍指向它取数 → 披露断链，违反 D16 自设披露义务 |
| V10 | P1 | docs/README.md:10-13 | 速查残存旧值：仍写「20 项 SHA256SUMS 全过（21 文件）」（实测 18/19）、「发布物：v2.4.3（d0107b11…）」（应 v2.5.4 6d2db75b…）、「隔离清单随包 residual-quarantine-v251.json」（不在 v2.5.4 包）——上一轮 P1（R7）基本未修 |
| V11 | P1 | audit 流程 | 两轮未修且缺口扩大：AUDIT-VERIFICATION-LOG.md 仍停轮次 4（v2.4.0）；audit/README.md 索引仍缺 v2.4.8–v2.5.4 共 **18** 份 AUDIT-SELF + AUDIT-REPORT-v2.4.19.md + 两份新 RESPONSE；RESPONSE-v2.4.19 声称的「台账/文档正在统一校订」未完成 |
| V12 | P2 | 上轮遗留 | cache 键仍手动 v312_（R4 未修）；refgate.py:12/refgate2.py:7 仍硬编码 SONGTI（R6 半修）；refgate_scan.py:19-20 仍吞异常当干净（R12 未修）；refgate2_scan.py:17 `if False` 死分支（R13 未修，全库共 6 处）；36 个孤立 lead_* 未归档（R14 未修）；owner_review_color.py 默认仍 v2.4.17.ttf（R15 半修）；stats.json note 仍引用 v24x-strict-report/gan_targets（R16 未修）；name[0] 仍「demo v0」（R17 未修）；cache 18.7 万文件无清理（R19 未修）；无 tests/（R20 未建） |
| V13 | P2 | 新脚本卫生 | content_loss_gate.py:33 `os.path.join(ROOT, out_path)` 把绝对路径拼进仓库根（复跑时误建 repo/tmp/）；新 scan/repair 脚本 11 处吞异常；scan_missing_parts.py 参考支持检查 fail-open（refgate import 失败→跳过过滤→误报放大 3,352→1,109 差 3 倍）；repair 替换循环零校验、零回退机制、无失败清单；detect_blocks.py docstring（留边≥4%）与实现矛盾 |
| V14 | P2 | 文档/元数据收尾 | 三份编年横幅仍 v2.4.3、SESSION-HANDOFF 停在 §1v（缺 5 节）、RELEASE-PLAN「当前版本 v2.4.15」、DECISIONS 无 D20/D21 且 D19 数字脱节、docs/README 文档清单漏 D19、COUNTS §67 未解释「复扫 806≠825−347」、README 模板三路径并存（内置模板 ≠ release_extras/README.tpl.md 含 v2.4.5 旧数 ≠ 包内手工 README）、release/latest 软链未建、head 时间戳四版相同导致元数据无法区分版本 |

---

## 二、通过项（独立复算，全部为真）

1. **SHA256SUMS 18/18 全过**；zip 完整性 + 与目录逐字节一致（19 文件）。✅
2. **cmap==manifest 硬闸**：双向差集 0；cmap 17,007、glyf 17,008；qa-report 复核 missing/extra/同框冲突全 0。✅
3. **QA 全量复跑 PASS**（含 256px 渲染全 17,007 字），与包内 qa-stats-v254.json 全 19 字段逐字段一致（render_bad=[]/tiny=[]/holes lost=520/fewer=1666）。✅
4. **覆盖率独立复算吻合**：canonical.jsonl（42,302 条/基本区 16,567）→ 基本区已收 10,269；10,269/16,567=61.98%；48.92%；缺口 6,298/10,723。与 coverage-detail/README/RELEASE-NOTES 一致。✅
5. **content_loss_gate 复跑 = 0**，与包内 2 字节 `[]` 一致（但闸有 V3 盲区，见下）。✅
6. **v2.5.4 发布 README 数字全部正确**（17,007/10,269/61.98%/6,298/825/147/347/478）——上一轮 P0（R1）已修复。✅
7. **六份新自审计数字全部可复算、无手抄**：refgate_v22.jsonl=1,226/after=3、refgate_v251=1,222/after=6、missing_scan_v252b=1,109（无过滤版 3,352，验证参考过滤价值）、offset_scan_v253=825（>0.35 格 147）、offset_scan_v254=806、aspect_scan 7,775 行中 glyph_aspect>1.3 为 0、distort_scan=20 行（𠯑 1.78 唯一>1.75）。✅
8. **上轮部分修复已落地**：recalcTimestamp=False 全链统一（postscale/refgate_clean/repair_apply*/repair_missing_chars/repair_offset，四版 TTF head 时间戳一致）；REF_FONT env+fail-fast 落地（font_norm.py:34/639-640）；并行构建实现正确（idx 键控、主进程写缓存、页级去重，v2.5.1 实测 586s）；package_summary.json 与包内一致。✅

---

## 三、P0 详述

### P0-V1：字体版本未盖章（v2.5.2/2.5.3/2.5.4 的字体内部仍是 2.5.1）

- 实测：`name[3]='KangXi Kai Regular 2.5.1'`、`name[5]='Version 2.5.1'`、`head.fontRevision=2.50999…`，而文件名为 `KangXiKai-Regular-v2.5.4.ttf`、stats.json version=2.5.4（stats 自身已暴露矛盾：name_version 字段诚实记录为 2.5.1）。
- 根因链（三段式）：① v2.5.1 是最后一次走 font_build 的全量构建（唯一盖章点，font_build.py:178-196）；② v2.5.2–2.5.4 全部走 TTFont 原地修补链（repair_missing_chars/repair_all_missing/repair_offset），只 `fonts.save()`，从不重设 name5/fontRevision（repair_missing_chars 的 `--version` 参数解析后从未使用，是死参数）；③ font_package.py 原样复制字体（:462），无「name 表版本==发布版本」校验，`font_qa.py:208` 的 `fontRevision_ok` 只比对 head↔name5 的**内部**自洽 → 恒真。
- 后果：用户安装后字体管理器显示 2.5.1；v2.5.1–2.5.4 四个发布物无法靠字体元数据区分；QA.md 自设硬闸「fontRevision 与版本一致」名不副实。
- **改进**：① 三个 repair 脚本增加 `--version` 并保存前重盖 name5+fontRevision（或统一收口 `stamp_version.py`，修复链末尾强制调用）；② font_package.py 加硬闸 `name_version != args.version → ABORT`；③ font_qa.py 的 fontRevision_ok 增加 `--expected-version`，打包链必传。

### P0-V2：QA.md/PROVENANCE.md 五版未更新（v2.4.22 正文只改标题）

- 证据：`diff release/KangXiKai-v2.4.22/{QA,PROVENANCE}.md release/KangXiKai-v2.5.4/{QA,PROVENANCE}.md` → 仅第 1 行标题不同，正文逐字节相同。
- 具体失真：QA.md「cmap == manifest（17,013）」vs 实测 17,007；「参考闸 pre 1,226→清 1,223→余 3」vs v2.5.1 起实为 1,222→1,216→6；「内容缺失 vs v2.4.21=0、vs v2.4.15=0」vs 本版应为 vs v2.5.3=0；PROVENANCE「字表 17,013 字」vs 17,007；「逐字来源见 provenance-detail-v2422.json」vs 包内是 v254 文件；「从头重建（cache v310 全量重矢量化）」vs v2.5.4 是增量修复（且代码缓存键已到 v312_）。
- 根因：release_extras/QA.md 与 PROVENANCE.md 是**静态手工文件**，font_package.py 只经 `--extra` 原样复制（:510-516），无生成逻辑、无数字校验——README 模板化后，这两个文件成了新的失真洼地；五版发布者只手工改了标题行。
- **改进**：① 废弃静态文件，QA/PROVENANCE 由 font_package 从 qa-stats/coverage-detail/stats 渲染（cmap 数、refgate 数、内容缺失基线、provenance-detail 文件名全部注入）；② 打包闸：生成后校验「cmap 数==stats.json」「引用的 provenance-detail-*.json 存在」，不符 ABORT；③ 版本号在文档中禁止手工改名（本轮「五版只改标题」正是手工改名病灶的典型样本）。

---

## 四、版本史与字表变化核查

v2.4.19=17,007 → v2.4.20=17,017（回滚基线）→ v2.4.21=17,016（−椼）→ v2.4.22=17,013（−仟/禦/絞，RELEASE-NOTES-v2422 已披露）→ v2.5.0=17,013（仅改版本号）→ **v2.5.1=17,007（−刃/榍/法/紆/総/荹）** → v2.5.2/2.5.3/2.5.4=17,007。

- 6 字剔除发生在 v2.5.0→v2.5.1，均系「参考闸隔离」；v2.5.1 RELEASE-NOTES 有披露（更正：本审计员在侦查阶段曾判断「未披露」，release-verifier 复核后确认 RELEASE-NOTES-v251 有「1,222→6（隔离 刃/榍/法/紆/総/荹）」表述，特此更正）。
- 但披露质量不足（V8）：① 常用字「法」「刃」为何被参考闸隔离（参考字体是否缺字、误隔离复核结论）零解释、无重定位计划；② v2.5.2–2.5.4 三版发布说明不再提及；③ docs/README 称隔离清单随包，v2.5.4 包内已无 residual-quarantine-v251.json（系列停在 v251）。
- 连带风险（V3）：content_loss_gate 对这类「字符整体移除」完全失明（.notdef 墨量比原字大，ratio 恒 >0.8），6 字移除时 gate 报 0——「内容零缺损」的声明覆盖不了字表缩水。

---

## 五、代码审计要点（新管线）

### 5.1 修复管线：检测可复算、修复不可复现（V4/V5）

- **检测层合格**：scan_missing_parts/scan_offset/scan_aspect/scan_distort 判据与文档一致，落盘清单与自审计数字全部对上（§二.7）。
- **修复层不合格**：
  1. v2.5.4 的核心 QC「墨量≥95% + IoU≥0.75 逐字校验，347 保留/478 回退」在 scripts/ 中**没有任何实现**（grep 0.95/0.75 零命中），无 kept/reverted 清单落盘——回退动作靠外部人工，AUDIT-SELF-v2.5.4 的这一声明不可复现（违反 QA §4）。
  2. repair_all_missing/repair_offset 替换循环零校验（`if res.get("ok")` 只代表有轮廓）、worker 逐字吞异常（lattice 失败→block=None→**无掩膜重矢量化**，可吸收邻墨，且该字静默跳过、无失败清单）、无回退机制（公/瘚 的回退是事后人工发现）。
  3. **不回写**：manifest/mapping/cache 均不更新（manifest-v251 vs v254 box 零差异；cache v312 存的是修复前轮廓）→ 未来任何一次 bump v313 全量重建都会静默回滚 1,109+347 字修复。这是本轮最危险的技术债：TTF 现状 ≠ manifest ≠ cache 三方分叉。
  4. 不重盖章 name5/fontRevision（P0-V1 根因）。

### 5.2 构建链与「无损化」声明（V6/V7）

- 「清理链无损化（停用外带删除/直线删除/像素参考过滤）」与代码不符：停用的只有 edge strip（enable_edge_strip=False ✅）与 ref_filter/line_swt（默认关 ✅）；**strip_border_lines 仍无条件运行**（18% 边带长细组件删除 + 孤立直线删除），主组件免疫但独立断笔（三/目类、辶 独立捺尾）在块边时理论可中招；mask_to_block 硬擦除块外全部墨、无擦除前后墨量对比、lattice 失败静默跳过（页面级不一致）。RESPONSE 顶部应加更正注记（「无损」→「低损 + 双基线内容闸兜底」）。
- build_release.py：只跑 font_build→可选 refgate_clean→font_qa→可选 content_loss_gate，不做打包；docstring 承诺的「输入/输出 sha256」只记了 TTF；v2.4.22 起未再使用，v2.5.x 无任何 build_recipe → 「固化全序」只兑现了一次。
- content_loss_gate：exit 恒 0（检测器不是闸）；基线路径错→逐字异常全吞→假 PASS 空 []；与 font_qa/font_package 无接线。**「发布前必跑」只兑现了「跑」，没兑现「闸」。**

### 5.3 上轮修复落实矩阵（R1–R20）

| 上轮编号 | 内容 | 本轮状态 |
|---|---|---|
| R1 README 数字/断链（P0） | ✅ **已修**（模板化+渲染；v2.5.4 README 数字全对）——但 QA/PROVENANCE 复发（V2） |
| R2 PROVENANCE stale | ⚠️ v2.4.20 重写过一次；v2.5.x 回归 stale（V2/V9） |
| R3 26 字对照图断链 | ✅ 已消除（v2.5.4 不再声称） |
| R4 cache 键人工版本号 | ❌ 未修（仍 v312_，且修复不回写后危害放大） |
| R5 打包字节复现 | ⚠️ 部分：recalcTimestamp=False 全链统一 ✅；built_at_utc 仍 date.today()、zip 时间戳仍 mtime |
| R6 REF_FONT 硬编码 | ⚠️ 半修：font_norm env+fail-fast ✅；refgate.py/refgate2.py 仍硬编码 |
| R7 docs 速查旧数字 | ❌ 基本未修（发布行已更，其余 20 项/21 文件、v2.4.3 发布物、横幅仍旧） |
| R8 核验台账停更 | ❌ 未修 |
| R9 audit 索引缺行 | ❌ 未修 |
| R10/R11 strip_edge 判据 | ⚠️ 停用（撤回）✅ 但未删除、默认参数 True（旧调用仍启用） |
| R12 refgate_scan 吞异常 | ❌ 未修 |
| R13 refgate2 死分支 | ❌ 未修（全库共 6 处 `if False`） |
| R14 死代码归档 | ❌ 未修（36 个孤立文件仍在） |
| R15 签核工具硬编码 | ⚠️ 半修（env 有、默认仍 v2.4.17） |
| R16 stats note 死引用 | ❌ 未修 |
| R17 QA.md 陈旧/nameID0 demo | ❌ 未修（QA.md 更严重，见 V2） |
| R18 refgate 证据单点 | ⚠️ 部分改善：work/lead 落盘齐全可复算；但包内 qa-stats 仍无 refgate 字段，QA.md 引用的反而是旧数字 |
| R19 cache 清理 | ❌ 未修 |
| R20 tests/ | ❌ 未建（新管线仍零测试） |

### 5.4 静态检查

188/188 py_compile 通过；0 `shell=True`；0 `/Users/wainshine` 硬编码；新脚本 11 处吞异常（关键点：content_loss_gate 假 PASS、repair worker 静默跳过失败字）；content_loss_gate.py:33 输出路径拼接 bug（绝对路径拼进 ROOT）；scan_missing_parts 参考支持 fail-open（refgate import 失败→跳过过滤）；detect_blocks docstring 与实现矛盾（留边 ≥4% vs 实际不设阈值）。

---

## 六、文档与审计流程

- **披露回归（V9，P1）**：v2.5.4 包内 PROVENANCE.md 406 字节，原 84.6%/n=13/CI/错标敞口 429–4,188 整段消失；docs/README:12 与 DECISIONS D16 仍指向它取数。敞口事实未变（标签管线未重做），披露义务被短文悄悄丢掉。
- **docs 残存旧值（V10，P1）**：docs/README 速查三处旧值（20 项 SHA/21 文件、发布物 v2.4.3、residual-quarantine-v251.json 断链）；三份编年顶部横幅仍 v2.4.3；SESSION-HANDOFF 停更 5 节；RELEASE-PLAN「当前版本 v2.4.15」；DECISIONS 无 D20/D21（格块掩膜/内容缺失闸未沉淀为决策），D19 数字脱节且文档清单漏列。
- **审计流程（V11，P1）**：核验台账仍停轮次 4；索引缺 18 份 AUDIT-SELF + 本轮新文件；RESPONSE-v2.4.19 声称的「台账/文档统一校订」未完成——审计流程断裂进入第三轮（若算上 v2.4.19 那轮是两轮未修）。
- **两份 RESPONSE 声称核对结论**：recalcTimestamp ✅ 全落地；REF_FONT fail-fast 半真（refgate 两处漏网）；README 模板机制在但 release_extras/README.tpl.md 模板正文仍含 v2.4.5 旧数字、本轮未启用（潜伏复发源）；「无损清理链」与代码矛盾（§5.2）；「build_recipe 固化」只兑现一次（V7）。

---

## 七、改进方案（按优先级）

### 第一优先（P0 修复，对外发布前）
1. **版本盖章三件套**：repair 脚本 `--version` 激活并重盖 name5/fontRevision（或统一 stamp_version.py 收口）；font_package 加 `name_version != version → ABORT` 硬闸；font_qa 的 fontRevision_ok 增加 `--expected-version` 必传。
2. **QA/PROVENANCE 模板化**：废弃 release_extras 静态文件，由 font_package 从 qa-stats/coverage-detail/stats 渲染；打包闸校验「cmap 数==stats」「引用文件存在」；标题版本由模板注入、禁止手工改名。

### 第二优先（P1）
3. **content_loss_gate 补「字表差集」检查**：old cmap − new cmap 非空直接报 removed（渲染前先查 cmap，避免 .notdef 干扰）；damaged>0 时 exit 1 并在 build_release 强制接线；修复路径拼接 bug 与 docstring。
4. **347/478 校验固化**：新增 validate_repair.py（墨量≥95% 且 IoU≥0.75 逐字对比，kept/reverted 清单落盘），repair_offset 替换前先过校验——否则 AUDIT-SELF 数字永远不可复现。
5. **修复回写**：repair 脚本同步更新 manifest（box）+ 写新 cache 键（或 build 时 --no-cache 并记录「cache 仅对 v2.5.1 有效」），消除 TTF/cache/manifest 三方分叉。
6. **兑现「无损化」声明**：RESPONSE 顶部加更正注记（无损→低损+双基线闸）；strip_border_lines 加 block 感知或停用；mask_to_block 加擦除前后墨量对比（<0.8 自动弃用并告警）。
7. **build_recipe 恢复并扩展**：修复链每步也记录输入/输出 TTF sha256 到 release_extras/build_recipe-vNNN.json，打包校验本版 recipe 存在。
8. **披露修复**：PROVENANCE 恢复 84.6%/n=13/CI/429–4,188 敞口段（或模板必填字段，缺失 ABORT）；docs/README 速查三处旧值修正；隔离字（尤其 法/刃）在 RELEASE-NOTES 附原因与重定位计划，隔离清单文件纳入打包固定清单。
9. **审计流程恢复（第三轮重申）**：台账每版必入账、索引脚本自动生成，列为发布门禁；补 v2.4.2→v2.5.4 全部轮次。

### 第三优先（P2 收尾）
10. 上轮欠账：cache 键加代码/输入 hash（废 v312_）；refgate.py/refgate2.py SONGTI env 化；refgate_scan 异常计数；36 个孤立文件 + 一次性 repair 快照归档 scripts/archive/；owner_review_color 默认改 env 必填；stats note 死引用与 nameID0 "demo v0" 清理；cache 加 --prune。
11. 文档收尾：三份横幅刷至 v2.5.4；HANDOFF 补 5 节；RELEASE-PLAN 刷新；DECISIONS 补 D20（格块掩膜）/D21（内容缺失闸=发布硬闸）与 D19 去时点化；COUNTS §67 补「复扫 806」说明；README 模板三合一；release/latest 软链。
12. 新建 tests/：修复链 golden 测试（修复前后逐字对比）、content_loss 字表差集用例、cache 失效冒烟。

---

## 八、遗留与限制

- 本轮未在非 macOS 实测（REF_FONT 跨平台行为仍为静态分析结论）；QA 复跑用系统 python3 + fontTools 4.61。
- 「09–11/13 卷锚点」「100 字签核」「残余碎片/框线」为持续未完成项，本轮确认根因未变（人工金标缺口/owner 动作未闭环），无新阻塞。
- 上一轮 v2.4.19 审计之后项目 6 小时内连发 9 版（v2.4.20→v2.5.4）并完成一次事故处置（1,132 字掉墨回滚+重建），流程改进（build_release/content_loss_gate/README 模板）方向正确，但**全部只落地了「生成」，没有落地「校验与持续」**——本轮两个 P0 与六个 P1 均源于此。建议项目把「发布闸=机器校验、每版必跑」作为 v2.5.x 余下工作的最高优先级，而非继续加功能。
- 本报告未改动任何被审文件；三份分项底稿留存于 `work/audit-v254/`，供核验台账复算引用。
