# 外部审计报告 · v2.6 梳理交接摘要审查（第三轮；基线 v2.5.6）

- 被审对象：①项目方「v2.6 梳理交接摘要」（190→48+142 归档、原计划解决状态、6 处更优方法、3 个陷阱）；②v2.5.5/v2.5.6 发布包（HEAD `837dede`）；③新门禁脚本（release_gate/check_release_docs/stamp_version）与 font_build `--repair-overlay`；④归档质量（`scripts/_archive/`）；⑤`docs/SCRIPTS.md`、`docs/PLAN-v2.6.md`、`audit/AUDIT-REBUTTAL-v2.5.4.md` 与核验台账更新
- 审计方：代码审计 2 代（第三轮；lead + release-verifier + code-auditor + docs-auditor）
- 审计时间：2026-11-12 06:20+（Asia/Shanghai）
- 方法：逐条声明核验（可数声明全部实测）+ 发布包全量复算（SHA/zip/cmap==manifest/QA 256px 全量复跑/content_loss/覆盖率 canonical 复算）+ 新脚本逐行审 + import 闭包扫描 + 文档断链扫描 + 上轮 P0 修复落实复核
- 证据底稿：`work/audit-v26/release-verify.md`、`work/audit-v26/code-audit.md`、`work/audit-v26/docs-audit.md`
- 分级沿用项目惯例：P0=发布阻断级；P1=重要须限期修；P2=轻微/建议。本报告只发现问题与改进方案，未修改任何被审文件

---

## 〇、一句话总评

**交接摘要的骨架与全部可数声明属实（190=48+142、git mv 保留历史、3,869 页候选、5,839 未对齐、42.2%、3,352→1,109、五份旧脚本描述相符、缺口 6,298），上一轮两个 P0 在 v2.5.5 已确认修复（版本盖章 2.55/2.56、三件套数字/引用全对、release_gate 7/7、22 项 SHA）；但摘要里有 3 处不实或误导声明（「4 个危险开关默认关闭」「重建 glyf 差异=0」「layout_lattice_boxes 基本全空」），且归档动作打断了现行复现链（DATA.md 复现链③ 必 ImportError）——「梳理」本身引入了一个 P1 断链。**

---

## 一、判定总表

| ID | 级别 | 位置 | 问题 |
|---|---|---|---|
| H1 | **P1** | 交接摘要 + QA.md/PROVENANCE/README/RELEASE-NOTES/coverage-detail/COUNTS/PLAN 共 7 处 | 「重建与 v2.5.5 glyf 轮廓差异=0（17,007 全检）」与证据矛盾：独立复算 v2.5.5 vs v2.5.6 轮廓点有 **974 字不同**（全部 ≤2 单位、无结构差异），与项目自己的 `work/lead/v256_rebuild_diff.json`（974 字）100% 一致；`v256_outline_diff.json=[]` 无口径说明（发布 TTF 与重建 TTF sha 相同，很可能是「重建 vs 已发布 v2.5.6」的平凡恒等）。PLAN-v2.6 验收原文「与 v2.5.5 逐字 sha 差异=0、不允许轮廓差异」**未达标**。建议：如实表述为「974 字有 ≤2 单位数值差、无结构差异」或补齐 overlay 后重验，并删除/标注 974 字中间文件 |
| H2 | **P1** | scripts/lead_char_align14.py:7 | 归档打断现行复现链：顶层 `from t1_count_v3 import is_head_v3`，而 t1_count_v3.py 已入 _archive → docs/DATA.md 复现链第③步直接 ImportError（lead_solver2.py:461 懒加载同断）；另 HEADERS.md（header_resolve）、STRUCTURE.md:192（hdr_page_obs）两处现行命令失效。SCRIPTS.md「26 模块 import 自检通过」名不副实（实测闭包 24，且断链就在自检对象里） |
| H3 | **P1** | 交接摘要「3 个陷阱」第 1 条 | 「font_norm 4 个危险开关默认关闭」不实：enable_line_swt/ref_filter/normalize_main_cluster 默认 False ✓，但 **enable_edge_strip 默认仍 True**（v2.4.16–19 P0 根因的那个开关），只靠 font_build 显式传 False 关闭；旧调用方（lead_finalize_union11.py:52 等）不传参即默认启用。应翻转签名默认值（一处改动）而非依赖调用方 |
| H4 | **P1** | docs/SCRIPTS.md §8-4 | 「layout_lattice_boxes.jsonl 基本全空、勿引用」与实测相反：3,869 页中 **3,582 页有候选**（12.5MB）——该结论会误导放弃一个潜在候选源，与摘要「缺口回收评测」目标相悖 |
| H5 | **P1** | scripts/ 全库 | 1,602 字 repair_overlay（load-bearing）的**提取器未入库**：全 scripts（含 _archive）无任何写 endPts/points 的生成器；meta.json 只记 sha256。该产物只能靠会话内联脚本再生，与「可复现口径」承诺冲突 |
| H6 | **P1** | release PROVENANCE.md（v2.5.6） | 引用 `work/review/owner-provenance-100-v256*` 断链——该系列实际只到 v254；check_release_docs 只校验包内文件引用，包外引用失真漏网 |
| H7 | **P1** | check_release_docs.py:37-51 | 文档数字校验存在漏洞：数字白名单放行 **17,013/17,029**（正是 v2.5.4 stale 正文的旧值，同款复发可过）；覆盖率 pct 与缺口 gap 读取后**从未参与校验**；包外引用无法校验（见 H6） |
| H8 | **P1** | audit 流程 | 半修：台账已补轮次 5/6（要点式）但顶部「当前状态基准：v2.4.3」横幅未更新；audit/README 索引仍缺 20 份 AUDIT-SELF（现存 26 份仅 7 行）+ REPORT-v2.4.19 + REPORT-v2.5.4 + 2 份 RESPONSE，且 REBUTTAL 行误插进「命名规则」4 列表破坏表结构；docs/README「20 项 SHA（21 文件）」三轮未修（v2.5.6 实为 22/23） |
| H9 | P2 | release_gate.py | char_diff 缺 `--prev-manifest` 时静默 PASS；quarantine 硬编码两路径且 break 只取第一个；`allow_fail`/`--skip-scan` 为死参数（7 步内无扫描步）；version_stamp 步是**校验非盖章**，stamp_version.py 无任何调用者，v2.5.6 盖章步不在 build_recipe 内；build_release.py 未接入 overlay/stamp/gate（已陈旧）；build_recipe-v256.json 为散文格式不可执行（"release/v2.5.5 ttf" 非真实路径） |
| H10 | P2 | repair_offset per_char_gate | 2a 反驳成立（ratio≥0.95 且 IoU≥0.75 自动回退已内置），但 gate **无上限**（ratio=1.5 吞邻墨可通过）、kept/rejected 清单不落盘（仅 stdout）——347/478 仍无法离线复算 |
| H11 | P2 | content_loss_gate.py | 2c 反驳部分成立：覆盖率下限 exit 2 与新 manifest 遍历语义 ✓；但 damaged>0 仍 exit 0（不拦损伤）、docstring 判据（0.80/0.55）仍与代码不符；「不存在 .notdef 比较路径」表述不严谨（fidelity_eval 无 cmap 检查，.notdef 实测 2 轮廓实心框，旧 manifest 用法下整字移除仍可被 tofu 掩盖） |
| H12 | P2 | repair_overlay-v256.jsonl | 结构偏离 PLAN §0.1 方案（仅 {char,endPts,points}，无 page/half/box/script/version/contours_sha256）；「1,109+347 去重=1,602」不可由两候选清单复算（并集仅覆盖 818/1,602，784 字需靠 v252 大清单解释） |
| H13 | P2 | residual-quarantine-v255/v256.json | 隔离清单不完整：仟/禦/絞 自 v2.4.22 隔离、至今不在 cmap，但清单只列 6 字——字符集差集门禁的 quarantine 数据源有漏 |
| H14 | P2 | 交接摘要/SCRIPTS.md | mapping 版本三处不一（摘要「23/32」、PLAN「32+修复框」、recipe「all33」，实测 all33 与 all32 box 零差异=复制品）；§3 缺口分解式算错（6+5,839+374+1=6,220≠6,298）；§1.6「19」实列 22；「26 模块闭包」实测 24 且无定义 |
| H15 | P2 | snap_box.py（_archive） | 「更优方法」第 2 条部分成立：support−λ×extra 实装，但 **μ×块外墨项未实现**（注释自称有）、half_lattice 是 pass 桩、含 if False 死分支——A/B 前必须补齐 |
| H16 | P2 | 遗留未修（第三轮连续） | scan_missing_parts fail-open（refgate import 失败→跳过参考过滤，误报 3 倍）；name[0]「demo v0」；charset_scope.note v24x 死引用；README-v2.5.6 文件清单漏 6 项；v256_rebuild_diff.json 与 outline_diff.json 并存无口径说明 |
| H17 | P2 | validate_anchors2 判据 B | 「39/39 锚点循环论证」批评方向成立：判据 B 以锚点自身中心定块再验证自身（近似循环）；825 字偏移 >0.18 格独立实测支持该批评——建议 SCRIPTS.md §8-3 补脚本出处 |
| OK1 | ✅ | 交接摘要全部可数声明 | 190=48+142（git mv 142 个 rename、历史保留）；layout_big_boxes=3,869 且 layout_thick_detect 确无 mapping 依赖（仅 pdf_map+PDF）；E_never_aligned=5,839；347/822=42.2%；missing_scan 3,352→1,109；五文件（t0_rectify/class_eval/postscale_glyphs/ref_filter_crop/snap_box）在 _archive 存在且描述相符；缺口 6,298；17,007 字 |
| OK2 | ✅ | 上轮两个 P0 修复确认 | v2.5.5/2.5.6 name5="Version 2.5.5/2.5.6"、fontRevision 2.55/2.56；三件套数字 17,007/10,269/61.98%/48.92%/6,298 全对、引用正确；SHA 20/20（v2.5.5）+22/22（v2.5.6）全过；zip 逐字节一致；cmap==manifest；QA 全量复跑（256px 渲染 17,007 字）PASS 且与包内 qa-stats 全 19 字段一致；content_loss 复跑=0；check_release_docs 复跑 PASS；canonical 独立复算全吻合；gate-report 7/7；overlay 1,602 行 sha 48c611ab 一致；build_recipe/隔离清单/overlay/gate-report 随包 |
| OK3 | ✅ | REBUTTAL 裁决 | **2a 成立**（347/478 校验已脚本化为 per_char_gate，残留 H10 两处 P2）；**2b 部分成立**（v2.5.3 确有独立源覆盖闸，但「列为常规闸」至今未落地——release_gate 7 步无扫描步）；**2c 部分成立**（新 manifest 接线成立、覆盖率下限存在，但「不存在 .notdef 路径」与代码不符，且字符集差集只在 release_gate 检查、content_loss 自身仍失明） |

---

## 二、交接摘要逐条核验（详情）

### 2.1 「原计划问题大多已解决」表 —— 属实（含 1 处版本号漂移）

| 摘要声明 | 实测 | 结论 |
|---|---|---|
| 正典序 42,302 条/映射定稿 | canonical.jsonl 42,302 行 ✓；mapping_verified_all33.jsonl 存在且与 all32 box 零差异 | ✅（版本号说法 23/32/33 三处不一，H14） |
| 字头-only 17,007 字 | cmap=17,007、manifest n_chars=17,007 ✓ | ✅ |
| 2×2 格块 + v2.5.6 overlay 回写 | font_build --repair-overlay 实现正确、overlay 1,602 字随包、meta 明示必须携带 | ✅（提取器未入库 H5） |
| 双闸 + 修复 1,109 + 回写 | content_loss_gate 覆盖率下限 + per_char_gate 均已落地；repair_overlay 回写完成 | ✅ |
| 构建可复现/版本/文档（release_gate 7 项） | gate-report-v256 7/7 PASS 随包 | ✅（「重建差异=0」口径问题 H1） |
| 缺口 6,298 未解决 | coverage-detail v256：6,298 ✓ | ✅ |
| 09–11/13 锚点、100 字签核未解决 | 待办记录一致 | ✅ |

### 2.2 「6 处更优方法」—— 5 处相符、1 处部分相符

layout_thick_detect（无 mapping 依赖 ✓、3,869 页候选 ✓）、ref_filter_crop（像素参考过滤 ✓）、class_eval（阳性/阴性 harness ✓）、postscale_glyphs（长边 760 归一化 ✓；「主簇 bbox」是提案非现状）、t0_rectify（版框四角透视 H ✓；「只映射坐标不重采样」是提案非现状）——**描述与代码相符**；snap_box 的 μ×块外墨项未实现且为半成品（H15），A/B 前须补齐。另注意 §8-4 对 layout_lattice_boxes 的「基本全空」结论与实测相反（H4）——同一份清单里对「旧候选源」的否定结论本身可能误导缺口回收。

### 2.3 「3 个陷阱」—— 2 个属实、1 个不实

- 「font_norm 4 个危险开关默认关闭」：**不实**（enable_edge_strip 默认 True，H3）——幸好只是声明不实而非修复缺失，把默认值翻转即可；
- 「scan_missing_parts fail-open」：属实（H16，已入 PLAN P0 待办未修）；
- 「39/39 锚点循环论证」：方向成立（H17）。

### 2.4 「已执行」清单 —— 基本属实

- 142 个归档使用 `git mv`（git show 837dede 显示 142 个 rename、0 行改动）✓ 历史保留；
- `scripts/_archive/README.md` 存在，声明「不参与现行管线、不保证可运行」✓（但只声明归档侧 import 失效，未声明现行侧断链 H2）；
- `docs/SCRIPTS.md`（199 行）与 `docs/PLAN-v2.6.md` 已落盘，PLAN 执行记录除「重建差异=0」（H1）外全部属实；
- 「现行 26 模块 import 自检通过」：**不实**——实测闭包 24 个，且 lead_char_align14.py:7 的顶层 import 断链就在其中（H2）；「py_compile 48/48」属实 ✓（48+142 全量通过）。

---

## 三、v2.5.5/v2.5.6 发布物：上轮 P0 确认修复（OK2）

两个 P0 的修复链路完整落地并被独立复核：stamp_version.py 实现正确（nameID 3/5 + fontRevision + recalcTimestamp=False）；v2.5.5/2.5.6 实测盖章正确；QA.md 从 4 条硬闸扩到 9 条（新增版本盖章、字符集差集、文档校验、可复现校验）；PROVENANCE 恢复 84.6%（n=13，CI 57.8–95.7%）披露并点名 100 字签核未完成；README 点名 法/刃 重定位最高优先；content_loss 覆盖率下限、per_char_gate、check_release_docs 全部落地。**这两个 P0 与绝大多数 P1 的处置方向、执行与验收都是合格的，予以确认。**

---

## 四、新门禁脚本审计要点（H7/H9/H10/H11）

- release_gate.py 7 步链路正确、主路径 fail-closed ✓；但「盖章」不在 gate 内（stamp_version 无调用者、build_recipe 无此步）→ 发布仍有内联成分；char_diff 缺 prev-manifest 静默 PASS；quarantine 硬编码。
- check_release_docs.py 能抓「只改标题不改正文」复发（版本号子串检查）✓；但白名单放行旧 stale 值、pct/gap 不校验 → 同款复发仍可漏网（H7）。
- per_char_gate 与 content_loss 覆盖率下限：REBUTTAL 2a/2c 的核心修复成立；残留无上限、不落盘、damaged 不拦、docstring 陈旧（H10/H11）。
- build_release.py 与 build_recipe 散文格式：机器可执行性不足（H9）。

---

## 五、归档质量与文档断链（H2/H5/H6/H8/H14/H16）

- 归档动作本身干净（git mv、数量对账、py_compile 全过、现行脚本无 import _archive 残留）；
- 但**引入现行链断链**：lead_char_align14.py:7 顶层 import 已归档的 t1_count_v3 → docs/DATA.md 复现链第③步必 ImportError；HEADERS.md、STRUCTURE.md:192 现行命令同样失效；SCRIPTS.md 的「import 自检通过」声明名不副实；
- 63 个归档脚本被 18 份文档引用（多数在已声明历史的章节，可接受），但现行文档中的引用需逐一改为 `_archive/` 路径或标注；
- PROVENANCE-v2.5.6 引用 work/review/owner-provenance-100-v256* 断链（系列只到 v254）——新 doc-check 未覆盖包外引用。

---

## 六、改进方案（按优先级）

### 第一优先（P1 修复）
1. **「重建差异=0」口径纠正**：把 verify_rebuild 脚本化（重建→与基线逐字比对→输出差异清单+量化）；7 处文档改为如实口径（「974 字 ≤2 单位数值差、无结构差异」或补齐后归零）；删除或标注 v256_rebuild_diff.json 的语义（中间失败尝试）；
2. **修现行链断链**：t1_count_v3.py 移回 scripts/（或改 lead_char_align14/lead_solver2 的 import 路径），重跑 DATA.md 复现链③；SCRIPTS.md「26 模块自检」改为可复现的闭包测试并声明结果；
3. **危险开关默认值翻转**：font_norm enable_edge_strip 默认改 False（兑现摘要声明），删除或 @deprecated strip_edge_* 函数体；
4. **overlay 提取器入库**：新增 scripts/extract_repair_overlay.py（TTF+chars→jsonl），写入 build_recipe；overlay 重复 char 告警；
5. **check_release_docs 补校验**：pct/gap 必须与 coverage-detail 相等；白名单剔除 17,013/17,029（或限定历史章节）；包外引用加显式白名单（work/review/ 等）；
6. **SCRIPTS.md §8-4 更正**：layout_lattice_boxes 实为 3,582/3,869 页有候选，重新评估其缺口回收价值；§3 缺口分解式重算（6,220≠6,298 的差额来源须说明）；mapping 版本号三处统一；「26 模块」改实测口径。

### 第二优先（P2 收紧）
7. release_gate：char_diff 缺 prev-manifest 时 FAIL；quarantine 改参数传入并合并多文件；删死参数；stamp_version 显式接入流程并写进 build_recipe；build_release.py 接入 overlay/stamp/gate 或标注废弃；content_loss damage>0 在 report 顶部标注 DAMAGED；
8. per_char_gate 加上限（ratio≤1.15 或 new_extra 判据）+ kept/rejected 明细落盘 work/lead/；
9. content_loss_gate docstring 同步代码判据；damaged>0 时 exit 1（或由 release_gate 决策阻断）；
10. 隔离清单合并仟/禦/絞（v2.4.22 起隔离、从未回收）并统一 quarantince 数据源；README 文件清单补齐漏 6 项；
11. snap_box 补齐 μ×块外墨项、half_lattice 桩、去死分支后再做 A/B；
12. 审计流程收尾：台账顶部基准横幅刷新 + 轮次 5/6 转表格式；audit/README 索引补 20 份 AUDIT-SELF + 2 份 REPORT + 2 份 RESPONSE 并把 REBUTTAL 行移出命名规则表；docs/README「20 项 SHA」改为 22/23。

### 工程建议
13. scan_missing_parts fail-open 改 fail-closed（P0 待办执行）；name[0] 去 demo v0；charset_scope.note 改真实路径；`--repair-overlay` 未命中 char 告警；fontTools 私有 API 注入加版本钉住注释。

---

## 七、遗留与限制

- 本轮未在非 macOS 实测；QA 复跑用系统 python3 + fontTools 4.61；「重建差异」为 release-verifier 独立复算（974 字 ≤2 单位）与项目自身 v256_rebuild_diff.json 交叉验证，未做第二轮全量重建（耗时 586s+，非必要）。
- 交接摘要的整体质量**明显高于前两轮的自审计**（可数声明全部属实、执行记录可核对、敢于承认已知债），主要问题集中在「细节声明不经实测」（4 开关默认值、lattice 空、26 模块自检、差异=0）——建议项目方今后此类交接摘要的每一条「结论性声明」都附一条可复现的验证命令，这正是本报告 H1-H4 想传达的方法论。
- 上一轮两个 P0 与 gate 化方向确认修复合格；本报告无新 P0。
- 本报告未改动任何被审文件；三份分项底稿留存于 `work/audit-v26/`，供核验台账复算引用。
