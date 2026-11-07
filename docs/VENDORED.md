# 从 guangeti 复制的代码清单

> 来源仓库：`/Users/wainshine/newAI/guangeti`
> 上游版本：A v1.7.2 / B v1.2.4 / C v1.2.0（2026-10-30）
> **原则**：复制后各自演进，不跨目录 import；上游修 bug 时按 diff 手动移植。

| 文件 | 来源 commit | 复制日期 | 本项目的改动 |
|---|---|---|---|
| `scripts/fontbuild.py` | 待填 | 待填 | 改 VERSION / 家族名；保留 `recalcTimestamp=False` |
| `scripts/punct_set.py` | 待填 | 待填 | 原样使用（20,992 + 42 = 21,034） |
| `scripts/13_extend_punct.py` | 待填 | 待填 | 原样使用 |
| `scripts/13_qa.py` | 待填 | 待填 | 改断言里的期望值 |
| `scripts/71_holes.py` | 待填 | 待填 | 原样使用 |
| `scripts/14_package.py` | 待填 | 待填 | 改包名/版本；**保持 SHA256SUMS 最后重算** |
| `scripts/06_norm.py` | 待填 | 待填 | 原样使用 |
| `scripts/08_make_pairs.py` | 待填 | 待填 | 原样使用（S=256） |
| `scripts/21_train_gan.py` | 待填 | 待填 | 移植已知坑修复（MPS val、best_dice 持久化、显式 --ckpt） |

**复制命令示例**

```bash
cd /Users/wainshine/newAI/kangxizidian
mkdir -p scripts
cp ../guangeti/scripts/{punct_set.py,13_extend_punct.py,71_holes.py,06_norm.py,08_make_pairs.py} scripts/
git -C ../guangeti rev-parse --short HEAD   # 填进上表
```

## 外部思想来源（未复制代码）

| 来源 | 许可 | 用在哪 | 记录 |
|---|---|---|---|
| [vModou 兀雨墨斗](https://github.com/shanleiguang/vModou)（shanleiguang，2025） | MIT | 版面纠偏思路：版框四角顶点 → 拉正。本项目用 Python 重实现为自动化步骤（强横线端点定角 + 透视变换），未复制其 Perl 代码 | `scripts/t0_rectify.py`，2026-11-07；效果见 `docs/PROBE.md` §7 |
