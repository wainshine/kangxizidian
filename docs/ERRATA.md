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

- `font_qa.py`（孔洞对照）、`scan_missing_parts.py`（参考校验）、`scripts/oneoff/owner_defect_sheet.py`（复核图占位）使用 macOS 系统宋体。
- 这是**专有字体**；按项目约束（沿用馆阁体标准）：不新增依赖，现有引用只能用于报告/对照，**不得作为发布/签收的唯一依据**。
- **已解决（2026-11-12，D21）**：全管线参考字体统一为 **霞鹜文楷（OFL）**，唯一来源 `scripts/reffont.py`
  （`font_qa` 孔洞对照已删除；`scan_missing_parts`/`refgate`/`fidelity_eval`/复核图/legacy 标注脚本均已切换）。
  macOS 宋体不再被任何构建/闸/报告脚本引用；`scripts/provenance/lead_t1v2_frozen.py` 等 legacy 脚本仅替换了标注字体，方法未变。
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
- 处置（类级规则，`scripts/oneoff/fix_mapping_sameblock.py`）：同块多字时保留原始 ink box 面积最大者，
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


## E30. content quad 扩张覆盖全部字头 box（BF-03，2026-11-13）

- 问题：`page_geometry_gate.bad_boxes` = manifest box 四角经 quad.M 变换后越出 quad["box"]：
  198@1px / **360@0** / max 8.803px；越界处字头可能被 clip mask 裁到。
- 类级修法：新脚本 `scripts/oneoff/expand_quads_to_cover_boxes.py` —— 对每个 (page,half) 把 quad["box"]
  在旋转空间扩到覆盖该半版**全部 assigned box 四角**（只扩不缩，+0.5px 余量），写回
  `work/lead/page_geometry.jsonl`（原文件留档 `page_geometry_v1.jsonl`，sha `42da3c0f…`）。
  受影响 **5,695 个半版**，单边最大扩张 **9.303px**；报告 `work/lead/quad-expand-report.json`。
- 结果（重建候选 sha `852f3193…`，17,005 字，全量 10m34s）：
  - `bad_boxes` **198→0**（零容差 360→0，max overflow 8.803→**0.0**）；bad_blocks=0；
  - content_loss_gate（上候选→本候选）**0 damaged**；vs v2.5.8 damaged **34→32**（两个原本被裁掉的字恢复）；
  - font_qa PASS；glyph_frame **0**；`page_geometry_gate` 唯一 FAIL 只剩 **empty_assign_halves 1,173**（mapping 覆盖缺口，非几何）；
  - 全库扫描随新字体重跑：缺件 1,153→**1,155**、源图框线 153→**158**（扩张后裁片含更多源墨，两数仍属已知债口径，方向已披露）。
- 结论：BF-03 关闭；页几何残差只剩「有 quad 无 mapping 行」的 1,173 半版（需 CS3 重跑检测/映射，见 `work/lead/empty-assign-triage-v262.json`）。


## E31. 内容闸 32 标记的归因：跨架构归一化差异（2026-11-13，CS3 分析）

- 现象：`content_loss_gate`（v2.5.8 → v2.6.2 候选）32 damaged，多数字 `iou` 极低（0.08–0.4）。
- 复核（`work/lead/content-aspect-analysis-v262.json`）：v2.5.8 旧架构按**格块/方形归一**，v2.6.2 按**源墨 bbox 归一**；
  32 字中 **12 个** 旧字形长宽比相对源墨 bbox 偏差 >15%（愈 偏差 111%、閧 35.8%、藚 31.7%、公 23.7%…），
  旧字形一律 ~1.0 方形 → 跨架构比较的 iou 失真。例：公 源墨 bbox 宽高比 1.322，旧 1.008；
  新字形轮廓经反投影核对**与源墨迹完全重合**（`work/lead/content-triage-v262.json`）。
- 结论：**内容闸 32 不是 32 个真实缺笔**；它度量的是架构差异。里程碑若沿用该闸，永远无法靠修字形归零。
- 提案（D23，待 owner 确认）：内容判据改为「**源墨保真度**」= 字形投影与其自身 source ink（同 pre-cut 口径）
  的配准 IoU；旧字体 delta 仅保留为回归告警（ratio 阈值），不再作里程碑硬条件。
- 产物：`work/lead/content-triage-v262.json`、`work/lead/content-aspect-analysis-v262.json`。


## E32. 扫描闸与构建 pre-cut 口径对齐（2026-11-13）

- 问题：缺件/框线逃逸扫描只做 content clip + 裁片外带排除，不含构建已有的页级直线 mask、细线 mask
  和页级已验证线条带 → 构建已排除的框线/注文框线被算作缺件/框线逃逸（口径不一致）。
- 修法：新增 `scripts/precut_masks.py`（与 `font_build` 构建同口径的 pre-cut 掩膜：长线/细线/线条带），
  缺件与框线逃逸扫描在比较前统一调用；页级 mask 每页只算一次（worker 内缓存，避免 per-char 重算）；
  扫描 sidecar 绑定新增 `precut_masks.py`、`page_line_bands.json`、`page_geometry.jsonl`。
- 结果（候选 sha `852f3193…` 复测）：
  - 缺件扫描 **1,155 → 1,117**（38 个「实为已排除框线」的误报消除）；
  - 框线逃逸 **158 → 43**（115 个误报消除；剩余 43 个为块边缘的 1–3px@300 亚像素界行残边）。
- 附注：扫描变慢（每页多算一次页级 mask），当前全库双扫描约 20–25 分钟；后续可给页 mask 加磁盘缓存。


## E33. 极细直线（亚像素界行/框线残边）pre-cut 清除（2026-11-13）

- 问题：E32 后框线逃逸剩 43 个、缺件 1,117；残线多为块边缘 1–3px@300 的界行亚像素残边。
- 第一次尝试（**失败，被内容闸拦下**）：用 `distanceTransform <= 1.6` 判「细」——
  笔画的边界 rim 的 dist 也是 1，导致把每笔边缘当细线挖掉：全量重建后 **961 字掉墨 40–60%**
  （content 对上一候选 damaged=961）。回退。
- 第二次（采用）：用「**垂直方向 opening 去掉宽≥3px 结构后的残渣**」判细线（不与笔画边界重叠），
  再做长轴 opening（≥0.012 页 ≈20px）：
  - `㨜` 等 43 个残线（+page_line_bands 未覆盖的细界行）在 pre-cut 阶段清除；
  - 预览：43 个 frame 字符剩 1；150 随机字中仅 7 个 ink 变化 5–7%（非损坏）；
- 结果（候选 sha `b73e9f01…`，17,005 字，全量 8m? 实测约 10m30s）：
  - 缺件扫描 **1,117 → 827**；框线逃逸 **43 → 1**（仅 㨜，块右缘 3px@300 界行，kernel=3 差 1px 未覆盖，已知债）；
  - content（上一候选→本候选）**0 damaged**；vs v2.5.8 32 → **29**；
  - fast_gate **8/8 PASS**；全闸基线 8 PASS / 3 FAIL（缺件 827、框线 1、页几何 empty_assign 1,173）。
- 附注：kernel 加宽到 4 可清掉 㨜，但会多删 2px@150 细结构，收益/风险不值得（留 known debt）。

## E34. 扫描闸提速注记（2026-11-13）

- E32 后扫描每页多算一次页级 mask（长线/细线/线条带），全库双扫描约 **20–25 分钟**（原 3.5 分钟）。
- 优化方向（未做）：页级 mask 落盘缓存（按 page_geometry+bands sha 命名）；或用 `FONT_PAGE_LINE_MASK=0` 时跳过。


## E35. 缺件扫描配准错误（827 的来源，2026-11-13）

- 背景：E32/E33 后缺件仍 827。BF-06 triage 发现 827 中 **707 个字符只有 edge_sliver/line_like 组件**、
  74 个含「likely_stroke」组件；进一步复核发现扫描的**配准**有结构性错误：
  - 扫描用「最大单组件」把输出字形配准到源图。pre-cut mask 会把源图字身切成多块（细线穿过处），
    最大单组件只对应其中一块 → 字形被放大错位，其余块被误判「缺件」。
- 第一次修正（main-cluster bbox 配准）后全量 824，但与旧集合仅 35 重叠（换了一批误报）→ 说明配准仍不精确。
- 结论：缺件扫描必须复刻构建的**最终墨迹链**才能可靠比较（见 E36）。

## E36. 缺件扫描按构建最终墨迹链重写（827 → 32，2026-11-13）

- 重写内容（`scripts/scan_missing_parts.py`）：
  1. 用 build_stats 的逐字 `pad150` 渲染同一 crop；
  2. 复刻构建的最终墨迹链：`mask_to_block → remove_specks → clean_cluster(box=box 矩形) → clean_ink(center=box 矩形)`
     （此前漏了 `center=(pad_px,…,size-pad_px)` 的 box 口径，导致误删组件）；
  3. 配准用「TTF glyph bbox → 256 画布 bbox」反推画布变换，再把 **stats bbox（normalize 口径，prune 前）**
     映射到 ink_final bbox，处理 `prune_edge_contours` 造成的 bbox 差；
  4. 只把「**fin_frac ≥ 0.6**（组件像素被 ink_final 保留）」的组件算缺件；管线按设计丢弃的块内邻墨/注文不算。
- 结果（全量 5,695 页半版，8 workers）：
  - 缺件 **827 → 32**（`work/lead/missing_scan_v262.jsonl`；sidecar 绑定新增 build_stats sha）；
  - 32 个全部可解释：**11 个 edge_pruned**（组件贴 ink bbox 边，`prune_edge_contours` 按设计删除的边缘碎片）
    + **22 个 sliver**（宽或高 ≤20px 的小碎片）；**interior=0**——未发现「字身内部真实缺笔」；
  - 分类报告：`work/lead/missing-32-triage.json`。
- 遗留：缺件数字的里程碑口径（是否把 prune-by-design 边缘碎片排除）归入 BF-06/D23 类口径决策；
  当前按 **32** 披露，不宣称清零。


## E37. owner 复核反馈驱动的三类缺陷修复（2026-11-13，v2.6.2 内）

- 输入：owner 在 `work/review/round-003-v262/` 上标注 77 格，反馈三类：
  1. **边角料混入**（49 格）：成品字形含注文/邻墨小碎片（例 䘿 顶部残笔、檀 底部残笔）；
  2. **过滤多了 / 切丢部件**（17 格）：上下都圈，多为上下结构中较细的横画被删（頁/言/辰 类）；
  3. **字和 Unicode 对不上**（11 格，打 ❌）：映射标签错误（例 急→实际滓/滎类、愈→注文「愈孟」）。
  标注解析：`work/lead/review-feedback-v262.json`（红色标注按格归类；编号经 ledger 翻回字/页/框）。
- 诊断（`work/lead/defect-diagnostics-v262.json`）：17 个「过滤多了」字在**关闭 ultra-thin 线 mask** 后 ink 全部恢复
  → 根因 = E33 的极细直线 pass 把字身内部细横画当页级直线删除（它在块内，不应删）。
- 修复（类级，均在 pre-cut/主链，无单字补丁）：
  1. **细线只删「穿越字身块边界」的组件**：`font_norm._filter_line_mask_to_crossing`——页级直线 mask 组件
     若完全落在 2×2 块内部（含 2px 余量），视为字身笔画保留；只有贴/穿块边界的线才删；
  2. **page_line_bands 与 crossing filter 解耦**：新增 `vectorize_box(frame_mask_extra=...)`，已验证线条带
     （27 rect，新增 萩 一处）无条件应用，不受 crossing filter 影响；
  3. **clean_ink 增「远离主体碎片」规则**：非主体、面积 <5% 主体、距主体 bbox >15px 的孤立成分剔除
     （修 49 格边角料；例 䘿/檀/呈 的注文残笔消失）。
- 结果（新候选 sha `a8bb87d9…`，17,005 字，全量约 10m40s）：
  - `glyph_frame_gate` **0 PASS**（修复后未引入新的字形级框线）；
  - content（上一候选→本候选）**0 damaged**；vs v2.5.8 damaged **29 → 18**（细笔画恢复使更多字形贴近旧基线）；
  - font_qa PASS；`frame_escape` 口径同时收紧：厚度 ≤3px@300 的亚像素线不计（见扫描脚本 MIN_THICK=4）。
- 修复后全库数字：font_qa PASS、glyph_frame **0**、frame_escape **0**（新口径）、content vs v2.5.8 **18**/35；
  缺件扫描 165（=把 165 字在块内细笔画恢复后，prune_edge_contours 又在字墨 bbox 边缘删掉的组件；
  属「恢复 vs 边缘清理」的下一轮口径问题，已入 v2.6.3 首批（BF-06），见 `docs/plans/PLAN-v2.6.3.md` §1）。
  - **更正（2026-11-14，audit4 DATA-402 / E39）**：上述「prune_edge_contours 边缘删除」归因**不成立**——
    234 个缺件组件中 **0** 个满足 prune 的 thin+ring+area 删除条件（结构性互斥）；165 的真实丢失阶段
    待 v2.6.3 构建侧插桩定位。本句保留为历史记录，不再作为修复依据。
- **未修（进 v2.6.3）**：11 个「字与 Unicode 不对应」= mapping 标签错误（例：04_0014 R 标注「愈」的框实为注文
  「愈孟」两小字；06_0080 R 标注「急」的框实为「滓」）。修复需按页重定位真迹字头（禁止补假字）——
  归入 v2.6.3 批 mapping 审计（BF-54 / BF-16 扩展）；本候选不宣称此 11 字已解决。


## E38. 目录重构后的 stale 绑定（2026-11-14，自审计发现）

- 现象：scripts 分层（refgate 等移入 `scripts/oneoff/`）后，`scan_missing_parts.py` 与 `release_gate.py` 的
  输入绑定脚本清单仍列 `refgate.py`；现路径不存在 → sha 为空 → `missing_reuse_binding` FAIL（fail-closed 正确生效）。
- 修复：从两处绑定清单删除 stale 的 `refgate.py`（该脚本早已不参与缺件扫描）；重扫缺件/框线并复验：
  全闸 11/11 PASS、边界值不变（缺件 165、框线 0）。
- 教训：移动/归档脚本时，必须同步检查 `gate_binding` 的 `scripts=` 清单与 sidecar 复用校验；
  代码布局变更后按「重建→快闸→扫描→全闸→打包干跑」跑一遍全链。

## E39. 第 4 代审计（audit4）确认的作废数字/口径（2026-11-14，v2.6.3 前置）

- 来源：`audit/AUDIT-REPORT-v2.6.2-audit4.md`、`audit/AUDIT4-FINDINGS-v2.6.2.jsonl`（76 条：P1 20 条/15 组，P2 35，P3 21）。
- 本节只记录**作废/更正**，不改写历史记录；已发布记录（`docs/releases/v2.6.2/*`）按 D7 只读。

1. **「缺件 165 = `prune_edge_contours` 边缘清理删除」作废**（DATA-402）（根因见 **E40**：扫描侧 precut fail-open）：234 个缺件组件中 **0** 个满足 prune 的
   thin+ring+area 删除条件（结构性互斥：组件最小边 ≥8px vs prune 细线阈值 5.0–6.8px）；165 的**真实丢失阶段
   未定**，v2.6.3 用「构建侧逐阶段插桩 + 独立扫描对照」定位（BF-06 重定义）。E37 对应句已加更正注记。
   复算：`work/review/audit4/data/recompute/m_prune.py`。
2. **「617 变化字」作废**（DATA-401）：617 = `work/lead/diff-v261-v262.json` 行数（旧候选 b73e9f01 的阈值筛集，
   mtime 早于最终字体）；对发布字体 a8bb87d9 的**精确 glyf 轮廓差异 = 3,351**（audit4 + Lead 复算，32.7s）。
   新维护者不得把 617 当变化规模；v2.6.3 起该指标必须由精确轮廓 diff 脚本生成。
3. **v2.6.2 发布 provenance 记录不成立**（BUILD-401/DATA-404）：字体实际由 **dirty 工作树**构建
   （`build_stats.git={commit 8ac16dfe, dirty:true, status_n:9}`，`cache_ver=ae10c121_0bf0dfce1496_d70038dd4d52`），
   而包内 `build_recipe` 记录的是**打包时刻** clean commit `8622ba89`；`build_stats` 未随包；
   README「构建时间 22:36:22Z」实为打包/统计写入时刻（真实构建 UTC 2026-11-13T14:33:31Z）。
   复算：`.venv/bin/python -c "import json;print(json.load(open('work/font/build/KangXiKai-v2.6.2.build_stats.json'))['git'])"`。
4. **SELF-AUDIT §4 的 clean-tree commit `c199945` 错误**（DOCS-401）：实际打包 commit 为 `8622ba8`
   （gate-report/build_recipe/package_summary 三处一致）。按发布记录只读规则，`docs/releases/v2.6.2/SELF-AUDIT.md`
   不改写，以本条为准。
5. **finalize 终验证据口径**（LEAD4-001）：包内 gate-report 是 finalize **前**写定的报告，不含
   `sha_final_ok/zip_ok`；work/lead 的 out 报告可被后续审计/复核重跑覆盖。v2.6.3 起 finalize 另写只读
   `FINALIZE.json`（sha_final_ok/zip_ok/zip sha/扫描产物 sha）。
6. **`check_release_docs` 不核对闸数字**（LEAD4-005 / GATE-10）：把 QA.md「18/35」改成「999/35」、
   KNOWN-DEBTS「165」改成 100 仍 PASS；v2.6.3 T4 修（数值对账 + 篡改测试）。
7. **扫描证据在 finalize 后被重写**（DATA-403/GATE-404）：`work/lead/missing_scan_v262.jsonl.sha256` /
   `frame_scan_v262.jsonl.sha256` 的 created_utc 晚于 finalize、git 为 dirty；包内无扫描产物/绑定快照。
   设计缺陷（可变证据 + 无产物 sha 锚定 + sidecar TOCTOU）成立；v2.6.3 起扫描产物随包 + FINALIZE 记录 sha。

## E40. BF-06 根因：扫描侧 precut crossing 过滤 fail-open（2026-11-14，v2.6.3 T1）

- 现象：v2.6.2 缺件披露 **165 字/234 组件**；audit4 DATA-402 已证伪「prune 边缘清理」归因但未定位根因。
- 根因（代码级）：`scripts/precut_masks.py::apply_precut_masks()` 在 E37 后调用
  `font_norm._filter_line_mask_to_crossing`，但**模块级未 `import numpy as np`**（仅 `_to_crop()` 局部导入）
  → 函数内 `np` 触发 NameError → 被 `except Exception: pass` 吞掉 → 页级线 mask **完全未过滤**即整体清零
  （比构建多删块内细笔画）。后果链：扫描 `src` 比构建多删墨 → 扫描侧 `ink_final` bbox 偏小
  → E36 配准（用 ink_final bbox 缩放 TTF）错位 → cov<0.45 → **缺件误报**。
- 修复（扫描侧类级，T1.4 branch C）：模块级导入 numpy；过滤失败改 `raise`（fail-closed，worker 落 error 行计入 flagged）。
- 复算（v2.6.2 字体，未重建）：
  - 全库重扫：**165 字/234 组件 → 19 字/20 组件**（error 0，9m11s；解析 150 字，交集 15，新增 4）；
  - 候选集并排对照（同一渲染）：V_old 165 字/238 组件 → V_fix 15 字/16 组件；Jaccard 组件 **0.0672**、字 **0.0909**；
  - 旧 234 组件构建侧归因（unknown=0）：**214（91.5%）扫描误报**、15 prune_loss、5 clean_ink_loss；
  - 新 20 组件归因（unknown=0）：**17 prune_loss、3 scan 残差**（㓚/譵）。
- 影响：v2.6.2 已发布 KNOWN-DEBTS 的 165 中约 150 为扫描误报（发布记录只读，以本 E 为准）；
  v2.6.3 缺件数字以新扫描为准（T2 重建字体后重扫）。真实残余：17 prune_loss + 5 clean_ink_loss（旧集）+ 3 scan 残差，
  BF-06 保持 open。
- 同步重扫框线逃逸（同一 `apply_precut_masks`）：**0 flagged / 0 error（8m56s）**，与修复前结论一致（非回归）。
- 复现/证据：`work/lead/v263-T1-BF06-report.md`、`work/lead/missing_scan_v263-t1fix.jsonl`、
  `work/lead/missing-165-stage-attribution.jsonl`、`work/lead/missing-19-stage-attribution.jsonl`、
  `work/lead/bf06-variant-candidates.jsonl`；脚本 `scripts/oneoff/diag_missing_stage.py`、
  `scripts/oneoff/bf06_scan_variant_candidates.py`。
