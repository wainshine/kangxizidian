# ERRATA · 勘误与已知历史错误

> 目的：记录**不再更正的历史错误**，避免每个接手的人重新考古。现状以 `docs/PIPELINE.md` / `docs/DECISIONS.md` 为准。
> 记录规则：只写「错在哪、影响范围、现在以什么为准」；历史文档原文不改写。

## E1. v2.6.0 的 restore/overlay 层把旧框线带回（版本已失效）

- v2.6.0 为「修复」375 个字，从 v2.5.8 字体**整字拷贝**旧字形；旧字形是「切后擦线」时代产物，自带框线。
- 实测：`勤`（01_0194 L）新架构基座字形干净，restore 回来的旧字形带顶部框线。
- 现口径：**禁止 restore/overlay**；修复必须回写 mapping 重切。v2.6.0 已从 release/ 删除，仅留失败证据。

## E2. 「切后擦框线」路线（含 v2.5.9 候选）方法层错误

- 现象：嗃/勤 等反复回归；线进入二值图后只能靠形状启发式补救，漏擦/误擦循环。
- 现口径：**pre-cut**（content clip + 裁片外带规则），主链不再做「按形状删框线」。
- v2.5.9 后处理候选已撤回、包已删除。

## E3. 缺件/框线数字的新旧口径不可直接比较

| 指标 | 旧口径（墨迹紧框） | 新口径（block 几何，v2.6.1 首次全量） |
|---|---|---|
| 缺件扫描 | 564 | **1,200** |
| 框线逃逸 | 60 | **153** |
| 内容闸 | 0（restore 层掩盖后） | **35** |

旧数字来自 `work/lead` 历史扫描文件（已保留）；新数字来自 block 几何。**不要混用或宣称「清零」**。
另：缺件扫描的「邻字隔离」尚未修正（block 内邻字组件会被计入），所以 1,200 偏高，属已知口径债。

## E4. 历史版本的 manifest 版本字段错标

- `KangXiKai-v2.1.1`、`v2.1.2`、`v2.2.0` 的 manifest 版本字段曾写成 `2.1.0`。
- 这些目录已在 2026-11-12 清理中删除；元数据留档见 `audit/RELEASE-HISTORY.jsonl`。

## E5. 历史 release 的 SHA 校验 BAD 版本

- 2026-11-12 清理前实测 SHA 校验失败：`v2.2.0`、`v2.3.0`、`v2.4.7`、`v2.4.11`、`v2.4.13`、`v2.4.14`。
- 已删除；不要再引用这些版本的 SHA 作为证据。

## E6. 早期文档/聊天里的数字与现行不符（以 PIPELINE §7 为准）

| 旧说法 | 阶段 | 现行 |
|---|---|---|
| 7,807 字 / 47.1% | v1.1 | 17,007 字 / 48.92%（基本区）/ 61.98%（目标字表） |
| 20,611 字 / 70.51% | v2.0（含注文小字，口径错误） | 同上（headword-only） |
| 17,121 字 / 62.46% | v2.4.5 | 同上 |
| 14 册 PDF 中的「12 册」 | 聊天/摘要口误 | 实际 **14 个 PDF**（00–13），3,869 页；DATA.md 正确 |
| 页码 = 2×扫描页−11 | 早期 | 叶码 = 扫描页 −5（D14） |

## E7. 早期时间戳/数字存在臆造（COUNTS 已自记）

- `docs/_history/COUNTS.md` 早期节的标题时间是我写作时估的，不是事实；以文件 mtime 与复算命令为准（该文件顶部有勘误）。

## E8. 系统宋体（Songti）依赖：仅报告用途，不得作为决策依据

- `font_qa.py`（孔洞对照）、`scan_missing_parts.py`（参考校验）、`owner_defect_sheet.py`（复核图占位）使用 macOS 系统宋体。
- 这是**专有字体**；按项目约束（沿用馆阁体标准）：不新增依赖，现有引用只能用于报告/对照，**不得作为发布/签收的唯一依据**。
- **已解决（2026-11-12，D21）**：全管线参考字体统一为 **霞鹜文楷（OFL）**，唯一来源 `scripts/reffont.py`
  （`font_qa` 孔洞对照已删除；`scan_missing_parts`/`refgate`/`fidelity_eval`/复核图/legacy 标注脚本均已切换）。
  macOS 宋体不再被任何构建/闸/报告脚本引用；`lead_t1v2_frozen.py` 等 legacy 脚本仅替换了标注字体，方法未变。
- 覆盖对比（对 17,007 字集）：霞鹜文楷 12,427（73.07%）> 旧系统宋体 TC 12,155（71.47%），换字体不降覆盖率。

## E9. 早期「8/8/9/9 闸 PASS」不代表字形无框线

- v2.5.8、v2.6.0 的 gate 通过只覆盖源图级扫描，**不检查 TTF 输出字形**；v2.6.0 因此放行了带框线字形。
- 现口径：里程碑前必须加字形级框线闸（CS1 待实现）。

## E10. 并发跑满 CPU 的历史问题

- 2026-11-12 多次 8–10 workers 并行时未设线程守卫，CPU 峰值接近 100%（截图确认）。
- 现口径：见 `AGENTS.md` 并发上限；jobrun 需先设 `OMP/MKL/OPENBLAS=1`，worker 内 `cv2.setNumThreads(1)`。

## E11. 旧 release 清理（2026-11-12）

- release/ 曾堆积 52 个版本目录+52 个 zip（2.5GB），仅 4 个有 PASS 闸报告。
- 已清理：保留 v2.5.8（基线）与 v2.6.1（重构后首版）；留档 `audit/RELEASE-HISTORY.jsonl` 与 `audit/release-evidence/`。

## E12. v2.6.1 包的 finalize 缺陷（第 3 代审计发现）

- 旧 finalize 顺序：先建 zip → 再写最终报告/SHA ⇒ **zip 内 gate-report 自称 finalized:false、SHA 也是旧的**；`sha_verified_after_final_report` 为硬编码 true。
- 代码已在《审计响应》中修（zip 改为 SHA 冻结后重建、该字段改实测）；**v2.6.1 包本身仍是旧产物**，保持「过程版本、不签收」，不重新打包。

## E13. v2.6.1 有 2 对同框同轮廓字形（已由修复后的 font_qa 如实暴露）

- 沓/𦧟（08_0319 R，box [1171,855,1272,953]）；䛱/忠（10_0081 R，box [1490,1273,1593,1370]）。
- 这是 mapping 指派冲突（两个字共用一个 crop），不是字形问题；修复后 font_qa 会让 v2.6.1 门禁 FAIL。
- 处置：CS1.5/CS3 改 mapping（类级：全库同框冲突检测 + 重指派），不得用改字形绕过。

## E14. S1 几何缓存曾从未被 S3 消费（第 3 代审计发现，已修）

- `font_build.WORK` 指向 `work/font`，`_GEOM_PATH=work/font/lead/page_geometry.jsonl` 不存在 ⇒ 每页仍从 PDF 现算 lattice/quad（这也是「缓存命中重建 242–251s」的真正原因）。
- 已修：路径改为 `work/lead/page_geometry.jsonl`；启动加载 3,869 页；缓存键改为算法 sha + 几何 sha 自动版本化。

## E15. 旧门禁可被「换包」绕过（已修）

- 旧 release_gate 只用 `--font` 做 QA，从不校验包内 TTF；把 v2.6.0 字体塞进 v2.6.1 包副本仍 6/6 PASS。
- 已修：finalize 增加 `pkg_font_sha`（包内 TTF sha 必须 == --font），负测试已复现 FAIL。


## E16. 孔洞/连通分量结构判据作废（2026-11-12，D21）

- `font_qa.py` 曾用「孔洞对照宋体」「连通分量>24 判坏」「碎片率 soft flag」评估字形结构；口径错误：
  **刻本为雕刻常把笔画刻断**，孔洞缺失/连通分量偏多不是缺陷信号，反而会误伤真迹。
- 已删除：孔洞对照、soft flag、基于连通分量/细长线的 `render_bad`；字体 QA 只保留与连通性无关的
  表/cmap/空字形/bbox/advance/fontRevision/同框检查。字形级框线检测改由 `glyph_frame_gate`
  的线段几何判据承担（不数孔洞）。
- 回归证据（2026-11-12 重跑 v2.6.1）：17,007 字，空字形 0、tiny 0、超 em 0、advance 0、render 空 0，
  唯一 FAIL = 同框 2 对（沓/𦧟、䛱/忠，映射问题）。


## E17. 字形级框线 23 字：不是旧缓存，是自适应 pad 路径（2026-11-12 更正）

- `glyph_frame_gate` 扫 v2.6.1：**23 字**带细长直线（勿/哺/喀/敦/捕…），v2.6.0 为 10 字（勤 命中），v2.5.8 为 19 字。
- 首次全量重建（自动缓存键，v2.6.2，sha `58fd9235…`）后仍是**同样的 23 字** → **推翻「旧缓存混入」解释**；这是当前管线行为。
- 根因（实测）：`vectorize_box` 的自适应 pad 判定把「横贯 crop 的框线/界行残段」也算作触边大字 → 误把 pad 从 6 放大到 18；pad=18 时 `strip_border_lines` 的贴边/孤立判据失效，框线留在字形里。23 字中 18 字走的是 pad=18 路径。
- 试修（同一 v2.6.2 变更集内部实验，未采用）：改为只看主字簇触边 → 15 字但仍脏，且 夸/𣫁 掉墨 ~45%（真字身笔画在 pad=6 被裁），属内容回归 → **回退**，见 E21。
- 处置：**交给 CS2** 用页级几何/pre-cut（版框/界行线先在页级 mask 掉）解决；在 `glyph_frame_gate=0` 之前不得宣称框线已清。

## E18. 页级几何闸首次基线（S1×S2）

- 覆盖：geometry 3,869 页；有 quad 3,526 页/6,868 半版；无 quad 343 页；无 lattice 355 页。
- `box_in_quad`（必须用 quad.M 做 page→rot 变换）：1px 容差 **198** 字越界；0 容差 **360**（与 audit BUILD-04 完全一致）；max 8.803px。Minv 反向口径 248 仅作核对。
- **空指派半版 1,173**（mapping 无行）：00/13 卷 504；01–12 卷 669（其中 652 有 lattice）；含 **01_0006 L**（「一」的字头页）。这是 mapping 覆盖缺口候选，CS3 triage；不区分「本无字头」与「漏映射」之前不得当缺口全部可补。

## E19. 字形缓存切换命名空间（2026-11-12）

- 旧 `work/font/build/cache/` 为 flat 目录（人工 tag v350，混入甲/乙/丙 3 条测试条目，17,010≠17,007）。
- 现改为 `cache/<_CACHE_VER>/`（算法 sha8+几何 sha12）；旧 flat 目录不再被读取，保留作历史证据，待清理脚本删除（不影响新构建）。

## E20. v2.6.1 build_stats 从 /tmp 恢复

- `work/font/build/KangXiKai-v2.6.1.build_stats.json` 曾在清理中缺失；2026-11-12 从 `/private/tmp/v261_full.build_stats.json` 恢复，
  已验证其 `sha256 == c73c3023…`（与交付 TTF 一致）、`input_mapping_sha256 == c522d1ce…`（与当前 mapping 一致）。
- provenance 闸正测试即用该 stats；后续候选由构建器直接产出 stats。


## E21. v2.6.2 变更集内部 pad 实验作废（内容回归，未成为版本）

- 目的：修 E17 的 pad 误判（只看主字簇触边）。
- 结果：glyph_frame_gate 23→15（13 字变干净、3 字新增框线），但同版本内 content 对比报 **2 字掉墨**：
  𣫁 ink 8134→4353（0.535）、夸 6963→4030（0.579）——pad=6 裁掉了伸到 crop 边外的真笔画。
- 按「内容优先」原则回退该改动；失败实验只留证据：`work/lead/glyph-frame-gate-padexp.json`、`work/lead/content-loss-padexp.json`；**不得当候选/发布**。内部迭代曾用 2.6.3/2.6.4 标签，按 owner 指示统一归入 v2.6.2，冗余 TTF/构建产物已清理。
- 教训：pad 判定同时影响「框线是否被裁掉」与「字身是否被裁」；单看触边面积/主簇都会顾此失彼。正确路线是页级 pre-cut（CS2），而不是在单字层反复调启发式。


## E22. 构建耗时实测更正（2026-11-12）

- 旧文档写「缓存命中重建 ~20 秒」（PIPELINE/AGENTS 旧值）——**作废**。同一 v2.6.2 变更集实测（10 workers）：
  - 全量 0 命中：**402s（6m42s）**，其中矢量化 158.6s，其余为字体装配；
  - 缓存 17,007 全命中：**232s（3m52s）**（矢量化 15.5s，装配占大头）。审计测得的 242–251s 与实测一致。
- 说明：S1 几何缓存路径修复后，缓存命中仍受「装配整字体」限制；后续若需更快，应优化装配而非扫描。


## E23. 同块冲突 2 对已清（BF-02，2026-11-12）

- 冲突：08_0319R 沓/𦧟、10_0081R 䛱/忠 共用同一 2×2 块。
- 复核：原始 verified box 显示被丢的两个是**片段框**（沓 48×78、忠 45×70；对应真字为 83×78、77×77），
  且 沓 属水部、忠 属心部，本不应出现在舌部/言部页——是 canonical 对齐把邻字片段/注文提及误标成字头。
- 处置（类级规则，`scripts/fix_mapping_sameblock.py`）：同块多字时保留原始 ink box 面积最大者，
  其余删除并写 residual 声明（`work/lead/v262_sameblock_residual.json`）；
  沓/忠 进入缺口（目标区 10,269→10,267，缺口 6,298→6,300），交给 CS3 从对应部首页重新定位。
- 结果：mapping 17,007→17,005 字；`font_qa` 同框=0 **PASS**；重建（17,005 cached）耗时 3m50s。


## E24. 页级 pre-cut 直线 mask（CS2 v1，2026-11-12）

- 新增 `font_build.get_page_line_mask`（长直线：竖 ≥0.10 页高 / 横 ≥0.12 页宽，全局）
  与 `get_page_thin_line_mask`（细短直线：厚 ≤~4px@150dpi、长 ≥0.02 页，仅用于字身 box+margin 之外）。
  在 `vectorize_box` 裁切阶段按页 mask 清零（pre-cut），不按字形形状删线。
- 效果（23 字字形级框线 → 14）：修复 9 字（哺/廋/犇/由/輮/逗/訏/𥻍/𦆍 等页面底部框线）；
  `content_loss_gate`（上一候选→本候选）**0 damaged**；vs v2.5.8 damaged 35→**33**。
- 待办：剩余 14 字（㰹/勿/喀/挕/捕/敦/敭/曀/瓶/磴/葡/驏/𡾜/𥰭）的残线在**检测框内部**，
  页级 mask 不能碰（会误伤字身）；下一步用 verified tight ink bbox 作为 keep 区
  （块框只用于 2×2 掩膜），或修这些页的 content quad。
- 构建耗时：全量 17,005 字 **636s（10m36s）**（含每页一次 page_gray 渲染）；缓存命中重建预计 ~4–5 分钟。


## E25. verified tight box 作 keep 区：实验回退（2026-11-13）

- 目的：E24 剩余 14 字残线在检测块框内，尝试用 mapping_verified 的 tight ink bbox 作为 keep 区
  （keep 区内不应用细线 mask），清掉框内残线。新增 `mapping_block_v272`（每字带 verified_box）、
  `font_norm.vectorize_box(keep_box150=...)`、`font_build` 实验通道（env `FONT_VERIFIED_KEEP=1`）。
- 结果（3 次全量重建）：
  1) keep=verified（无过滤）：字形框线 23→**5**，但内容闸抓到 **去 -25%、蘇 -21%**（IoU 0.13/0.09）→ 真笔画被当线删掉；
  2) 加面积比可靠性门槛（≥0.6×块框）：框线 8，但 **緅 -32%**（ratio 恰 0.60，仍是片段框）；
  3) 回退：`FONT_VERIFIED_KEEP` 默认 **0**，候选恢复 `eec49c4e…`（14 字框线、内容安全、内容闸 33/35）。
- 教训：verified bbox 对不少字是**片段框**（正常字头 ink bbox 也只占 2×2 块框 50–70%，面积比无法区分真假完整）；
  不能用它直接做 ROI。下一步：由**字形自身 thick ink**（腐蚀掉细线后的墨迹 bbox）反推 keep 区（二次 pass），
  并以内容闸 0 damaged 为硬条件。
- 产物：`mapping_block_v272.jsonl`（verified_box，留作后续；候选仍用 v271）；失败构建 d960daeb/cb586213 弃用。


## E26. 由 thick ink 反推 ROI：同样失败并回退（2026-11-13）

- 目的（BF-53）：细线 mask 只在「字形厚墨 ROI」外应用，清掉框内残线而保护笔画。
- 实现：`font_norm.thick_roi()`（distanceTransform 取厚墨最大连通域 bbox+margin），`vectorize_box(use_thick_roi=...)`；全量重建（sha 3ab7001d…）。
- 结果：字形框线 15（未清零），**内容闸 2,596 damaged**（大量字掉墨 ~50%）。
  根因：**细笔画本来就不在 thick mask 里**（厚墨腐蚀后细撇/细横被排除），因此 thin-line mask 会把字头细笔画当框线删掉——方法自相矛盾。
- 处置：`use_thick_roi` 默认 **False**；候选恢复 `eec49c4e…`（14 字框线、内容安全、内容闸 33/35）。
- 结论：单字层「ROI + 细线 mask」两条路线（verified box / thick ink）都不可行（E25/E26）。
  剩余 14 字改走**页级几何**：修这些字所在页的 content quad / text bbox（框线/界行应在 quad/裁切带外），
  属 BF-11/CS2 的按页几何修复，不做单字补丁。


## E27. 页级「已验证线条带」清掉最后 14 处框线（CS2 v3，2026-11-13）

- 前两轮单字 ROI（E25/E26）失败后改数据驱动：把 14 个残留线段的**页坐标 rect** 反算出来
  （用 glyph_frame_gate 的 line bbox + 该字归一化参数逆变换 → 页 150dpi 坐标），核对后写成
  `work/lead/page_line_bands.json`（页级、14 个 rect，含来源字与朝向）。
- 构建时 `font_build` 读该表，把这些 rect 并入页级 line mask（pre-cut 清零，只影响这 14 页）。
- 结果（sha `19d103cc…`，全量 10m34s）：
  - glyph_frame_gate **0 flagged PASS**（14→0）；
  - content_loss_gate（上一候选→本候选）**0 damaged**；
  - fast_gate **8/8 PASS**（含 content 33/35、provenance、页几何候选阈值）——**首个全过快闸的候选**。
- 说明：这是「页级几何数据修复」而非单字补丁；rect 由残线本身反算、页级作用域；后续若页级几何（quad/text bbox）修好，
  这些 bands 可删除并复测 glyph_frame=0。


## E28. 全闸首次基线（v2.6.2 候选，2026-11-13）

- `release_gate`（不打包，候选基线）：**8 PASS / 3 FAIL**。
  - PASS：font_qa、version_stamp、char_diff、content_loss_gate（33/35）、missing_reuse_binding、frame_reuse_binding、**glyph_frame_gate（0）**、provenance_gate；
  - FAIL：`scan_missing_parts` **1,153**、`frame_escape` **153**、`page_geometry_gate`（198@1px / 1,173 空指派，严格 0）。
- 缺件数字口径已变：**1,153 是霞鹜文楷参考口径**（D21 后第一次全量重扫），与旧宋体口径 1,200 **不可直接比较**；旧值仅作历史。
- 框线逃逸 153 是**源图块内**扫描（非字形级）；字形级已是 0（E27）。
- 报告：`work/lead/gate-report-v262.json`；扫描 sidecar 已生成（missing/frame），复用校验 PASS。


## E29. strip_border_lines 摘除 A/B（D22 验收，2026-11-13）

- 目的：pre-cut 已能把字形级框线清零（E27），验证「切后擦」strip 是否可摘除。
- 步骤与结果（同输入、仅差 strip 开关）：
  1. `FONT_STRIP_BORDER=0` 全量重建：glyph_frame **12 flagged**（错误 䘿/䛲/凛/垝/担/泞/熄/籜/絭/緈/𦯣/𩧆），content（对 strip 版）0 damaged；
  2. 用 E27 同法把这 12 处反算成页坐标 rect，并入 `work/lead/page_line_bands.json`（14→**26** rect；bands 内容已纳入缓存 key）；
  3. 再全量重建（strip 关）：**glyph_frame 0 PASS**；content（对 strip 版）**0 damaged**；font_qa PASS；
- 采用：strip 默认关闭（`scripts/font_build.py` worker `strip_border=False`；env `FONT_STRIP_BORDER=1` 仅供复现历史 A/B），候选更新为 sha `f901c9d4…`（17,005 字）。
- 新候选闸况：fast_gate **8/8 PASS**（content 34/35，余量 1，已披露）；全闸基线仍 8 PASS / 3 FAIL（缺件 1,153、源图框线 153、页几何严格）；全库扫描复测数字不变（missing 1,153 / frame 153）。
