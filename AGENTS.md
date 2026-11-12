# AGENTS.md — 给接手的 agent（康熙字典 楷书字体重建项目）

> 本文件是**入口约束**：先按顺序读文档，再动手。项目数据/过程知识在 `docs/` 与 `work/`，**不要凭聊天记录开工**。

## 0. 先读这几个文件（按顺序）

1. `docs/PROJECT-STATE.md` —— 30 秒现状、已知缺陷、如何独立审计
2. `docs/PIPELINE.md` —— 现行管线架构/原理/流程/参数/复现命令（唯一权威）
3. `docs/WORKFLOW.md` —— 流程纪律：候选/正式分层、变更集、闸分层、里程碑发版、7 张复核图
4. `docs/VERSION-HISTORY.md` —— 每版改了什么、探索 vs 修补
5. `docs/WORK-MAP.md` —— `work/` 痕迹地图（**不能盲删**）
6. `docs/DECISIONS.md` —— 口径决策（唯一权威，D1–D22+更正注记）
7. `docs/GLOSSARY.md` —— 术语（冲突时以它为准）

## 1. 硬性约束（违反即事故）

- **git 写操作**：默认**不要** add/commit/reset/checkout/push；由 owner 本人提交。owner 明确说「提交」时才提交，并写清 commit message。
- **禁止专有/商业字体作为依据**（含系统自带宋体/黑体）：全管线唯一参考字体 = **霞鹜文楷（LXGW WenKai，OFL）**，由 `scripts/reffont.py` 统一提供（默认 `work/font/_fonts/LXGWWenKai-Regular.ttf`，不随包分发）；任何脚本不得再新增专有字体路径。
- **不数孔洞/连通分量评判字形**（D21）：刻本为雕刻常断笔，孔洞缺失/连通分量偏多/碎片都是工艺特征，不是缺陷信号；字形质量由 pre-cut 几何 + `glyph_frame_gate`（线段几何）+ 内容/缺件闸承担。
- **并发上限**：同时最多 **10 个 worker**，总 CPU ≤ 2000%。多进程脚本必须设 `OMP_NUM_THREADS=MKL_NUM_THREADS=OPENBLAS_NUM_THREADS=1`，worker 内 `cv2.setNumThreads(1)`；启动后核对 CPU。默认 `FONT_BUILD_WORKERS=10`。
- **大文件不入库**：PDF、`work/`、模型、TTF 构建产物、zip 都在 `.gitignore`。
- **`work/` 不可盲删**：JSON/JSONL 是方法核心成果，一律保留；只清图片/数组/纯缓存（见 `docs/WORK-CLEANUP.md`）。
- **字表口径**：headword-only（只收字头真迹，不收注文小字、不补假字形；D15）；字头 = **2×2 小字格块**。
- **版面排除**：版框/页边黑带/界行必须在**裁切阶段**排除（pre-cut），禁止「切进来再擦」（owner 明令）。
- **修复纪律**：一类问题一次修（类级）；**禁止单字补丁**；**禁止 restore/overlay 整字拷贝旧字形**（会把旧框线带回）。
- **数字来源**：任何写进文档/报告的数字必须来自闸输出或可复算命令；没有证据就写「待验证」。
- **发布口径**：候选不进 `release/`；只有**里程碑**才打正式包；正式包必须来自 **clean git tree**，SHA 覆盖 gate-report，finalize 后不再改包内文件。

## 2. 当前状态（2026-11-12）

- 当前基线：**v2.6.1**（过程版本，不签收）；`release/` 仅保留 v2.5.8（重构前基线）与 v2.6.1。
- 字形 **17,007**（headword-only 真迹）；基本区 10,269/20,992 = **48.92%**；目标字表 10,269/16,567 = **61.98%**；缺口 **6,298**（高频缺 23）。
- 闸：font_qa 仅同框 2 对 FAIL；内容闸 35（阈值 35）；缺件 1,200（旧参考口径，待重扫）、源图框线 153；**字形级框线 23**（v2.6.1 mixed cache，待重建复测）、**页级几何 bad_boxes 198 / 空指派半版 1,173**（已知债）。
- 构建：`work/lead/mapping_block_v270.jsonl` + `work/lead/page_geometry.jsonl` + **自动缓存版本**（算法 sha8 + 几何 sha12，人工 tag v350 已废）；全量重建 ~9.3 分钟（10 workers，缓存 0 命中时，修复前记录）；缓存命中耗时待重建实测（BF-22）。
- 隔离 9 字：刃/榍/法/紆/総/荹/仟/禦/絞。
- 进度：CS0 ✅（参考字体/QA 判据）→ **CS1-A ✅**（三闸 + 输入绑定 + 构建硬化；BF-01/09/12/43/45/46/48/50）→ **下一步 CS1-B：一次全量重建**（新缓存键；字形变更批次）→ CS1.5 映射/坐标增量重建 → CS2 pre-cut/页级几何（含摘除 strip，D22）→ CS3 内容/缺件。

## 3. 最短验证命令

```bash
# 字体 QA（当前状态预期 FAIL：同框 2 对 沓/𦧟、䛱/忠）
.venv/bin/python scripts/font_qa.py --font work/font/build/KangXiKai-v2.6.1.ttf \
  --manifest work/font/build/manifest_v261.json --outdir work/font/build/qa_check
# 快闸（新增三闸+绑定，约 1–2 分钟内容闸/4 分钟全量；缺基线参数即 FAIL）
.venv/bin/python scripts/fast_gate.py --font work/font/build/KangXiKai-v2.6.1.ttf \
  --manifest work/font/build/manifest_v261.json --version 2.6.1 \
  --baseline work/font/build/KangXiKai-v2.5.8.ttf \
  --baseline-manifest work/font/build/manifest_v258.json \
  --pkg-dir release/KangXiKai-v2.6.1 --content-max-damaged 35
# 缓存命中重建（应 17,007 cached；旧 sha c73c3023 是修复前 key 产物，新 key 重建后重测，不作验收基线）
FONT_BUILD_WORKERS=10 .venv/bin/python scripts/font_build.py \
  --mapping work/lead/mapping_block_v270.jsonl --out /tmp/check.ttf --version 2.6.1
```

## 4. 发布流程（顺序固定，勿跳步）

```
改代码/数据 → 变更集 cs-*.jsonl → 脏集增量构建（或全量）→ 快闸 fast_gate
→ （里程碑前）全闸 release_gate（缺件/框线/内容/文档/SHA/zip）
→ 人工复核包（work/review/round-*/ 7 张图）→ owner 标 ✓/✗/?
→ 里程碑条件满足 → font_package（clean-tree 闸）→ release_gate finalize（SHA 覆盖报告）→ 冻结
```

发布前核对：`release/` 只放正式包；包内数字与 `docs/VERSION-HISTORY.md`/闸报告一致；`build_recipe.json` 记录 git commit/dirty/cache tag。

## 5. 文档约定

- `README.md`（发布包内）面向使用者；`docs/` 与 `AGENTS.md` 用简体中文。
- 表格只对**数字/判定**加粗；正文不用 emoji；结论直接写。
- 每出一个候选/正式版：必须追加 `docs/VERSION-HISTORY.md` 一行 + `work/changesets/cs-*.jsonl` + `work/lead/version-artifacts-v<ver>.jsonl`（见 WORKFLOW §10bis）。
- 历史审计在看 `audit/_history/`（不改写）；现行审计只看 `audit/` 顶层。

## 6. 常见坑（我们踩过的，别再踩）

1. **框线「切后擦」必回归**：线进入二值图后只能靠形状启发式补救，漏擦/误擦反复（嗃/勤）。只用 pre-cut。
2. **restore/overlay 整字拷贝**：把旧架构字形（含框线）带回，造成双真源。已删除，禁止恢复。
3. **门禁盲区**：v2.6.0 字形带框线却 9/9 PASS——因为闸只扫源图不扫输出字形。必须补字形级闸。
4. **单字打补丁**：每修一次就写回修复列表 → 版本发完即失效；必须类级 + 回写 mapping。
5. **`| tail` 吞退出码**：后台任务失败却显示成功。用 `scripts/jobrun.sh`（pipefail + status 标记 + EXIT 行）。
6. **未提交代码就打包**：hash 不可复现。`font_package` 已有 clean-tree 闸。
7. **finalize 后改包**：SHA/zip 立刻失效。定稿→冻结，冻结后不改。
8. **扫描结果不复用**：字体没变却重跑 25 分钟全库扫描。快/全闸分离 + 按字体 SHA 缓存。
9. **内容闸 35 / 缺件 1,200 / 框线 153 不是零**：不要写成「已清零」；新口径数字与旧值不可直接比较（口径已改）。
10. **会话失忆**：不要从聊天记录开工；先读 §0 文档。
