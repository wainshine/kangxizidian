# PLAN v2.7.0 —— GAN + 帯状扫掠（ribbon）回退补齐

> 背景（2026-11-13 owner 指示）：v2.7.0 需要实现 **GAN** 和 **帯状扫掠（ribbon）** 生成/回退，
> 相关代码参考**馆阁体项目**（`/Users/wainshine/newAI/guangeti`）。
> 本文只做方案与验收口径；实现前必须先经 owner 确认（涉及 D15 headword-only 口径扩展与 D4 provenance 新增状态）。

## 0. 现状与目标

- v2.6.2 候选：**17,005 个真实字头**（headword-only 真迹），缺口 **6,300**（目标表 16,567），
  其中 empty_assign 1,173 半版未完成字头定位；高频缺 23（一/王/法…）。
- 2.6 补丁线（v2.6.3 起）：先把**真实字头**补到上限（mapping 审计/补映射），不补假字；做不完顺延 v2.6.4/2.6.5…。
- **v2.7.0**：对「确实无法从刻本取到真迹」的缺口字，用生成字形补齐（provenance 标注不可混淆），
  目标是把基本区覆盖从 48.91% 提升到接近/达到 100%（是否承诺 20,992 由 owner 定）。

## 1. 参考实现（馆阁体项目）

| 能力 | 参考文件（guangeti 仓库） | 说明 |
|---|---|---|
| GAN 训练（zi2zi 配方 PyTorch 重实现） | `21_train_gan.py`（馆阁体仓库） | U-Net generator + PatchGAN/DCGAN 判别器、L1+adv+feature matching；Apache-2.0 配方（kaonashi-tyc/zi2zi） |
| GAN 评估（等墨量/拓扑） | `22_eval_gan.py`（馆阁体仓库）、`33_struct_metrics.py`（馆阁体仓库）、`32_eval_clean.py`（馆阁体仓库） | Dice + 墨量比 + 骨架 chamfer/端点/交叉点 |
| 带状扫掠（ribbon）渲染器 | `brush_lib.py`（馆阁体仓库）、`generate_lib.py`（馆阁体仓库） | 骨架→笔画图→逐点笔宽模型→变宽渲染（带斜切端头） |
| 全量生成/回退组装 | `36_fill_fallback.py`（馆阁体仓库）、`20_corner_knock.py`（馆阁体仓库）、`10_generate.py`（馆阁体仓库） | 生成字形 + 必填回退策略 |
| 合并进字体 | `11_build_full.py`（馆阁体仓库）、`fontbuild.py` | real/gar 分层合并、打包 |
| 方法与实验记录 | `docs/reference/EXPERIMENTS.md` E15（ribbon）/E16（GAN）/E20（GAN+拓扑闸门）/E23/E26/E27/E29 | 结论与指标口径（Dice/ST） |
| 发布包结构 | `14_package.py`（馆阁体仓库）、`release/*` | 两档发布：Real（仅真迹）/ 全量（真迹+生成） |

> guangeti 的结论（可直接借鉴）：ribbon 端帽/笔锋好但结构粗；GAN 更接近真迹（E29：GAN 0.540 vs ribbon 0.413），
> 但需**结构闸门**（拓扑/骨架）筛选输出，否则会出现结构崩坏（E16：缺字拓扑 116/150）。

## 2. 本项目落地方案

### 2.1 生成管线（v2.7.0）

```
真实字头（17k，v2.6.x 产出）
  → 参考骨架：霞鹜文楷（OFL；仅作结构骨架，不复制轮廓）【D21 口径需 owner 确认是否允许】
  → 带状扫掠 ribbon 渲染：按刻本笔宽分布（从 17k 真迹统计）合成墨形
  → 叠加 GAN 精修（zi2zi 配方）：以「真迹对」训练，输入参考骨架/ribbon 初稿，输出精修字形
  → 结构/拓扑闸门：骨架 chamfer、端点/交叉点统计、拓扑一致率（参照 guangeti E24/E29 判据）
  → 通过则标 provenance=gan（或 ribbon_fb 回退），否则回退 ribbon
  → 与真实字头合并构建：真实字头永不被覆盖（label_source=mapping）
```

### 2.2 口径（必须 owner 确认）

1. **D15 扩展**：v2.7.0 的「生成字形」是补齐字表的程序化字形，不是刻本真迹；发布包必须两档
   （`KangXiKai-Real` 仅真迹 / `KangXiKai` 含生成）或至少逐字标注 provenance；
2. **D21 参考字体用途扩展**：霞鹜文楷可用于「结构骨架」生成（不复制轮廓），需更新 D21 注记；
3. **D4 provenance**：沿用 guangeti 四态 `real/gan/ribbon_fb/mapped_traditional`；
4. 生成字不得进入「真迹覆盖率」数字；README/包内分别给「真迹数/生成数/合计覆盖」。

### 2.3 验收（v2.7.0 硬条件）

- 真实字头部分：与 v2.6.x 完全一致（content/glyph/frame 闸不退化）；
- 生成部分：
  - 结构闸门通过率 ≥ 95%（拓扑一致率/骨架 chamfer 相对阈值，参照 guangeti E29）；
  - 等墨量 Dice ≥ ribbon 基线（留出真迹集；不得只看 Dice，必须同时报墨量比）；
  - 小字号（8–12px）可区分性抽样 PASS；
  - 生成字 provenance 100% 标注、package 内 manifest 可查；
- 包结构：Real 包与全量包分别构建、分别 gate-report；不得混用「真迹覆盖率」口径；
- 许可：GAN 训练代码为 Apache-2.0 配方重实现（合规）；参考字体 OFL；生成字形按 OFL 发布。

### 2.4 里程碑与工作量

| 阶段 | 内容 | 预估 |
|---|---|---|
| P0 准备 | 从 guangeti vendored 复制 `21_train_gan.py`/`brush_lib.py`/`generate_lib.py`（保留 Apache-2.0/OFL 头），适配 em 框/UPM | 1 天 |
| P1 ribbon 基线 | 用 17k 真迹统计笔宽/端帽参数 → 渲染留出集 → 基线指标（Dice/墨量/骨架） | 1–2 天 |
| P2 GAN 精修 | 真迹 pair 数据（同一字多例/参考骨架→刻本墨形）→ 训练/评估 → 结构闸门 | 3–5 天 |
| P3 合并/闸 | Real/全量双档构建 + provenance + 全闸 + 包 | 1–2 天 |
| P4 发布 | 复核包 + owner 签核 + 正式包 | 1 天 |

## 3. 风险与兜底

- GAN 产生「像字但结构错」的字 → **必须结构闸门 + 回退 ribbon**；闸门不过的字进隔离清单披露；
- 参考字体骨架可能带现代字形结构 → 与刻本结构差异（D21）需抽样评估；若不可接受，v2.7.0 只用 ribbon（无参考字体骨架，按真迹骨架模板拼接）；
- 生成字永不覆盖真实字头；发布材料分口径披露，避免「覆盖 100%」误导。
