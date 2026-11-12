#!/usr/bin/env python3
"""唯一参考字体（OFL）：霞鹜文楷 LXGW WenKai。

用途：**对比分析/参考校验**（`scan_missing_parts`、`fidelity_eval`、复核图等）。
不是发布依据，不随发布包分发。

规则（DECISIONS D21 / AGENTS.md §1）：
  - 参考字体只允许 OFL：默认 `work/font/_fonts/LXGWWenKai-Regular.ttf`
    （复制自馆阁体项目 vendored 文件，OFL 1.1）。
  - 覆盖优先 `REF_FONT_PATH`，其次 `REVIEW_REF_FONT`，再默认路径；仍必须 OFL。
  - **禁止系统宋体/黑体等专有字体**作为参照或依据；不得在脚本里再新增专有字体路径。
  - 不可用 → fail-closed（RuntimeError）；调用方不得静默回退到其他字体。
  - 不数孔洞/连通分量：刻本为雕刻常断笔，这类结构指标不作质量判据（D21）。

覆盖事实（2026-11-12 实测）：对本项目 17,007 字集，霞鹜文楷覆盖 12,427 字（73.07%）；
旧 macOS 宋体 TC 为 12,155 字（71.47%）。换参考字体不会降低覆盖率。

用法：
  from reffont import path as ref_path, index as ref_index, has_char, raster
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULT = os.path.join(ROOT, "work/font/_fonts/LXGWWenKai-Regular.ttf")
_CANDIDATES = (
    os.environ.get("REF_FONT_PATH", ""),
    os.environ.get("REVIEW_REF_FONT", ""),
    _DEFAULT,
    "/Users/wainshine/newAI/guangeti/data/base/LXGWWenKai-Regular.ttf",
)

_PATH = None
_INDEX = None
_CMAP = None


def path() -> str:
    """参考字体路径；不可用即报错（fail-closed，不静默换字体）。"""
    global _PATH
    if _PATH is None:
        for p in _CANDIDATES:
            if p and os.path.exists(p):
                _PATH = p
                break
        if _PATH is None:
            raise RuntimeError(
                "缺少 OFL 参考字体：请把 LXGWWenKai-Regular.ttf 放到 "
                "work/font/_fonts/ 或设置 REF_FONT_PATH（只允许 OFL 字体）")
    return _PATH


def index() -> int:
    """TTC 内的字体索引（TTF 恒为 0；TTC 可用 REF_FONT_INDEX 覆盖）。"""
    global _INDEX
    if _INDEX is None:
        _INDEX = int(os.environ.get("REF_FONT_INDEX") or 0) if path().lower().endswith(".ttc") else 0
    return _INDEX


def _ensure_pylibs():
    p = os.path.join(ROOT, "work", "font", "_pylibs")
    if p not in sys.path:
        sys.path.insert(0, p)


def cmap() -> dict:
    """参考字体 cmap（码位 -> 字形名），带缓存。"""
    global _CMAP
    if _CMAP is None:
        _ensure_pylibs()
        from fontTools.ttLib import TTFont
        fp = path()
        f = TTFont(fp, fontNumber=index()) if fp.lower().endswith(".ttc") else TTFont(fp)
        _CMAP = f.getBestCmap() or {}
    return _CMAP


def has_cp(cp: int) -> bool:
    try:
        return int(cp) in cmap()
    except Exception:
        return False


def has_char(ch: str) -> bool:
    if not ch:
        return False
    return has_cp(ord(ch))


def raster(ch: str, size: int = 256, top: float = 0.88):
    """渲染参考字形为 bool mask（PIL，字号/基线口径与历史参照脚本一致）。"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(path(), int(size), index=index())
    im = Image.new("L", (int(size), int(size)), 0)
    ImageDraw.Draw(im).text((int(size) // 2, int(top * size)), ch, fill=255, font=f, anchor="ms")
    return np.array(im) > 127
