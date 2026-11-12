#!/usr/bin/env python3
"""字形级框线闸（审计 BF-01 缺失三闸之一）：扫描最终 TTF 的每个字形，抓「版框/界行线被裁进字形」。

背景：v2.6.0 曾 9/9 PASS 却字形带框线（勤 等），因为旧闸只扫源图不扫输出字形。
本闸只看**输出 TTF 的渲染结果**，判据只用线段几何；按 D21 **不数孔洞、不用连通分量评判字形结构**
（连通域只用于把「线状残迹」切成线段，不参与字形质量判定）。

判据（render_size 默认 256，与 scripts/font_qa.py 历史口径一致）：
  1. 渲染：PIL ImageFont(size=render_size)，位置 (size//2, int(0.88*size))，anchor="ms"，二值化 >127；
     逐字循环 manifest（TTF cmap 键是码位，不能按字形名循环）。
  2. 薄：3×3 腐蚀 it 次再膨胀 it 次重建「厚区」，mask−厚区 = 细笔画候选；
     线段厚度用原 mask 在 bbox 内的行/列墨迹中位数度量（倾斜线退回「离线段中心最近的连续段」），
     要求 ≤ thin_max_px（256 时为 3px）。单字粗横/粗竖（厚 >3px）天然被排除，不会因「一」这类字误报。
  3. 长：长度 ≥ max(0.5×墨迹 bbox 长边, 0.5×render_size)；256 时下限为 128px。
  4. 线状残迹：候选集先沿垂直方向膨胀 bridge_px（容忍扫描轻微倾斜/锯齿），再分别做
     水平 (L×1) / 竖直 (1×L) 长核开运算；对开运算结果做连通域统计，输出线段 bbox/厚度/长度/方向。
  5. flagged 数 > --max-flagged → 退出码 3（默认 0，即任一 flagged 即 FAIL）；否则 0；
     运行错误/契约不满足 → 1（fail-closed，异常不会变成 PASS）。

用法：
  .venv/bin/python scripts/glyph_frame_gate.py \
      --font work/font/build/KangXiKai-v2.6.1.ttf \
      --manifest work/font/build/manifest_v261.json \
      --out work/lead/glyph-frame-gate-v261.json

性能：17k 字约 2.1ms/字（单核），--workers 8 时 <1min（≤3min 预算）。
并发：--workers 默认 8、硬上限 10；OMP/MKL/OPENBLAS 等线程数置 1，worker 内 cv2.setNumThreads(1)。

已知局限：
  - 阈值按 256px 标定；--render-size 仅调试用，改大时厚度阈值按比例缩放，但 AA/hinting 变化会漏检。
  - 断成多段且每段 < L 的虚线框线会漏检；只抓「连续 ≥L 的细长线」。
  - 只扫 manifest 内的字，不扫 .notdef / 非 manifest 字形（cmap 覆盖由 font_qa 负责）。
  - 框线的判定是字形级回归信号，不是「框线逃逸」源图级闸（scan_frame_escape.py）的替代。
"""

from __future__ import annotations

# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:  # pragma: no cover - cv2 缺失时在 main 里 fail-closed
    _cv2 = None
cv2 = _cv2

import argparse
import hashlib
import json
import math
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "font" / "_pylibs"))

DEFAULT_OUT = "work/lead/glyph-frame-gate.json"
WORKER_HARD_CAP = 10
CHUNK = 128
BINARIZE = 127
BASELINE_FRAC = 0.88
THIN_MAX_AT_256 = 3.0       # px
THICKNESS_TOL = 0.5         # px（二值化/取整容差）
LENGTH_FRAC = 0.5
BRIDGE_AT_256 = 5           # px，垂直方向膨胀量（容忍约 ±1.5° 倾斜/锯齿）

# worker 进程内复用
_FONT = None
_SIZE = None
_THIN_MAX = None


class GateError(RuntimeError):
    """前置契约不满足：直接 exit 1，不产出可被误读为 PASS 的报告。"""


# ---------------------------------------------------------------- 渲染 / 检测
def _raster(ch: str, size: int):
    from PIL import Image, ImageDraw
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).text((size // 2, int(BASELINE_FRAC * size)), ch,
                            fill=255, font=_FONT, anchor="ms")
    return np.asarray(im, dtype=np.uint8) > BINARIZE


def _run_len_nearest(a, center: int):
    """1D bool 数组里，离 center 最近的连续 True 段长度（无则 0）。

    用于量线的厚度：取包含/最靠近线段中心的墨迹连续段，避免把窗口内邻近的粗笔画算进来；
    倾斜线（comp bbox 只有 1px 宽）也能量到真实厚度。
    """
    d = np.diff(np.concatenate(([0], a.astype(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    best = 0
    best_dist = None
    for s, e in zip(starts, ends):
        if s <= center < e:
            dist = 0
        else:
            dist = min(abs(s - center), abs(e - 1 - center))
        if best_dist is None or dist < best_dist or (dist == best_dist and e - s > best):
            best_dist, best = dist, int(e - s)
    return best


def _line_thickness(mask, x0, y0, x1, y1, orient, bridge):
    """量线厚度：优先 bbox 内逐列/逐行墨迹中位数；倾斜线 bbox 只有 1–2px 宽时退回最近连续段。"""
    patch = mask[y0:y1 + 1, x0:x1 + 1]
    if orient == "H":
        vals = patch.sum(axis=0)
    else:
        vals = patch.sum(axis=1)
    t_bbox = float(np.median(vals)) if len(vals) else 0.0
    if t_bbox > 0:
        return t_bbox

    # 倾斜线：开运算只保留中心列，回到原 mask 取离线段中心最近的连续段
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    runs = []
    if orient == "H":
        lo = max(0, y0 - bridge)
        hi = min(mask.shape[0], y1 + bridge + 1)
        for x in range(x0, x1 + 1):
            r = _run_len_nearest(mask[lo:hi, x], cy - lo)
            if r:
                runs.append(r)
    else:
        lo = max(0, x0 - bridge)
        hi = min(mask.shape[1], x1 + bridge + 1)
        for y in range(y0, y1 + 1):
            r = _run_len_nearest(mask[y, lo:hi], cx - lo)
            if r:
                runs.append(r)
    return float(np.median(runs)) if runs else None


def _detect_lines(mask, size: int, length_min: int, thin_max: float):
    """在字形二值 mask 上找「长的、薄的」水平/竖直线段；返回线段列表。"""
    m = mask.astype(np.uint8)
    # 薄候选：腐蚀 it 次再膨胀 it 次重建厚区；厚区之外即厚度 ≤ 2*it 的细笔画
    it = max(1, int(math.ceil(thin_max / 2.0)))
    k = np.ones((3, 3), np.uint8)
    thick = cv2.dilate(cv2.erode(m, k, iterations=it), k, iterations=it)
    thin = (m > 0) & (thick == 0)
    tm = thin.astype(np.uint8)

    # 垂直方向轻度膨胀后再开运算：容忍扫描线的微小倾斜/锯齿（不改变厚度度量，厚度回原 mask 量）
    bridge = max(3, int(round(BRIDGE_AT_256 * size / 256.0)))
    h_opened = cv2.morphologyEx(
        cv2.dilate(tm, np.ones((bridge, 1), np.uint8)), cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (length_min, 1)))
    v_opened = cv2.morphologyEx(
        cv2.dilate(tm, np.ones((1, bridge), np.uint8)), cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, length_min)))

    lines = []
    for orient, opened in (("H", h_opened), ("V", v_opened)):
        n, _labels, stats, _cent = cv2.connectedComponentsWithStats(opened, 8)
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < length_min:
                continue
            # 厚度回原 mask 量：取最靠近线段中心的墨迹连续段，中位数抗交叉笔画
            if orient == "H":
                length = w
            else:
                length = h
            thickness = _line_thickness(m, x, y, x + w - 1, y + h - 1, orient, bridge)
            if thickness is None:
                continue
            if thickness > thin_max + THICKNESS_TOL:
                continue            # 其实是粗笔画，不是线
            if length < length_min:
                continue
            lines.append({
                "bbox": [x, y, x + w - 1, y + h - 1],
                "thickness": round(thickness, 1),
                "length": int(length),
                "orient": orient,
            })
    lines.sort(key=lambda d: (-d["length"], d["orient"]))
    return lines


def _ink_bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def _scan_chunk(chars):
    """worker：返回 (flagged_local, errors)。clean 字不返回，减少 IPC。"""
    flagged, errors = [], []
    for ch in chars:
        try:
            mask = _raster(ch, _SIZE)
            bb = _ink_bbox(mask)
            if bb is None:
                errors.append({"char": ch, "error": "render_empty"})
                continue
            length_min = max(int(round(LENGTH_FRAC * max(bb[2] - bb[0] + 1,
                                                          bb[3] - bb[1] + 1))),
                             int(round(LENGTH_FRAC * _SIZE)))
            lines = _detect_lines(mask, _SIZE, length_min, _THIN_MAX)
            if lines:
                flagged.append({"char": ch, "ink_bbox": bb, "lines": lines})
        except Exception as e:  # 单字异常必须显式失败，不静默当通过
            errors.append({"char": ch, "error": f"{type(e).__name__}: {e}"[:200]})
    return flagged, errors


def _init_worker(font_path: str, size: int, thin_max: float):
    global _FONT, _SIZE, _THIN_MAX
    from PIL import ImageFont
    cv2.setNumThreads(1)
    _FONT = ImageFont.truetype(font_path, size)
    _SIZE = size
    _THIN_MAX = thin_max


# ---------------------------------------------------------------- 输入 / 输出
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise GateError(f"manifest 读取失败: {path}: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("chars"), dict):
        raise GateError("manifest 格式错误：缺少 chars 对象")
    chars = data["chars"]
    if not chars:
        raise GateError("manifest.chars 为空")
    for ch, meta in chars.items():
        if len(ch) != 1:
            raise GateError(f"manifest 字符键不是单码位: {ch!r}")
        if not isinstance(meta, dict) or not all(k in meta for k in ("page", "half", "box")):
            raise GateError(f"manifest[{ch}] 缺 page/half/box")
        box = meta["box"]
        if not (isinstance(box, (list, tuple)) and len(box) == 4):
            raise GateError(f"manifest[{ch}].box 格式错误: {box!r}")
    return chars


def _outline_bounds(glyphset, gname):
    """fontTools 取单个 glyph outline 的 bbox；空 outline 返回 None。

    只对 flagged / 渲染为空的少数码位调用：全量 expand glyf（17k）约 9s，
    而本闸的判据来自渲染 mask，不需要逐字 outline。
    """
    from fontTools.pens.boundsPen import BoundsPen
    bp = BoundsPen(glyphset)
    glyphset[gname].draw(bp)
    if not bp.bounds:
        return None
    return [int(round(v)) for v in bp.bounds]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path.resolve())


def main() -> int:
    ap = argparse.ArgumentParser(description="字形级框线闸：扫 TTF 字形里残留的版框/界行线")
    ap.add_argument("--font", required=True, help="待检 TTF")
    ap.add_argument("--manifest", required=True,
                    help='{"chars": {char: {page,half,box,label_source}}}')
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"输出 JSON（默认 {DEFAULT_OUT}）")
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 字（调试）")
    ap.add_argument("--render-size", type=int, default=256, help="渲染边长 px（默认 256）")
    ap.add_argument("--workers", type=int, default=8, help=f"进程数（默认 8，硬上限 {WORKER_HARD_CAP}）")
    ap.add_argument("--max-flagged", type=int, default=0, help="允许的 flagged 字数（默认 0）")
    args = ap.parse_args()

    if cv2 is None:
        raise GateError("cv2 不可用")
    if not (64 <= args.render_size <= 2048):
        raise GateError(f"--render-size 越界: {args.render_size}")
    if args.limit < 0:
        raise GateError("--limit 不能为负")
    if args.max_flagged < 0:
        raise GateError("--max-flagged 不能为负")

    font_path = Path(args.font)
    if not font_path.is_absolute():
        font_path = ROOT / font_path
    if not font_path.is_file():
        raise GateError(f"字体不存在: {font_path}")
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    if not manifest_path.is_file():
        raise GateError(f"manifest 不存在: {manifest_path}")
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    size = args.render_size
    if size != 256:
        print("[glyph_frame_gate] 注意：判据按 256px 标定，--render-size != 256 仅供调试，"
              "结果不作闸判定", file=sys.stderr)
    workers = max(1, min(args.workers, WORKER_HARD_CAP))
    if workers != args.workers:
        print(f"[glyph_frame_gate] --workers {args.workers} 超过硬上限，钳到 {workers}",
              file=sys.stderr)

    thin_max = max(THIN_MAX_AT_256, float(round(THIN_MAX_AT_256 * size / 256.0)))
    bridge = max(3, int(round(BRIDGE_AT_256 * size / 256.0)))
    iters = max(1, int(math.ceil(thin_max / 2.0)))

    t0 = time.time()
    chars_meta = _load_manifest(manifest_path)

    from fontTools.ttLib import TTFont
    tt = TTFont(str(font_path), lazy=True)
    cmap = tt.getBestCmap()
    n_glyphs = tt["maxp"].numGlyphs
    glyphset = tt.getGlyphSet()

    manifest_chars = set(chars_meta)
    font_chars = {chr(cp) for cp in cmap}
    missing_in_font = sorted(manifest_chars - font_chars)
    if missing_in_font:
        raise GateError(
            f"manifest 有 {len(missing_in_font)} 字不在字体 cmap（如 "
            f"{''.join(missing_in_font[:20])}）；cmap 覆盖应由 font_qa 先保证")
    todo = sorted(manifest_chars)
    if args.limit:
        todo = todo[:args.limit]
    total = len(todo)

    print(f"[glyph_frame_gate] font={_rel(font_path)} glyphs={n_glyphs} "
          f"manifest={len(chars_meta)} scan={total} "
          f"size={size} workers={workers} thin_max={thin_max:g}px", file=sys.stderr)

    flagged, errors = [], []
    done = 0
    next_tick = 2048
    if workers == 1:
        _init_worker(str(font_path), size, thin_max)
        for i in range(0, total, CHUNK):
            f, e = _scan_chunk(todo[i:i + CHUNK])
            flagged.extend(f)
            errors.extend(e)
            done = min(i + CHUNK, total)
            if done >= next_tick:
                print(f"[glyph_frame_gate] {done}/{total} flagged={len(flagged)}", file=sys.stderr)
                next_tick += 2048
    else:
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                                 initializer=_init_worker,
                                 initargs=(str(font_path), size, thin_max)) as ex:
            futs = [ex.submit(_scan_chunk, todo[i:i + CHUNK])
                    for i in range(0, total, CHUNK)]
            for fut in as_completed(futs):
                try:
                    f, e = fut.result()
                except Exception as exc:  # 进程崩溃/异常 → fail-closed
                    raise GateError(f"worker 异常: {type(exc).__name__}: {exc}")
                flagged.extend(f)
                errors.extend(e)
                done = min(done + CHUNK, total)
                if done >= next_tick:
                    print(f"[glyph_frame_gate] {done}/{total} flagged={len(flagged)}",
                          file=sys.stderr)
                    next_tick += 2048

    # 渲染为空：outline 也为空 → 空字形（font_qa 管）；outline 非空 → 渲染错误（fail-closed）
    hard_errors = [e for e in errors if e["error"] != "render_empty"]
    empty = []
    for e in errors:
        if e["error"] != "render_empty":
            continue
        ch = e["char"]
        try:
            ob = _outline_bounds(glyphset, cmap[ord(ch)])
        except Exception as exc:
            hard_errors.append({"char": ch, "error": f"outline:{type(exc).__name__}: {exc}"[:200]})
            continue
        if ob is None:
            empty.append(ch)
        else:
            hard_errors.append({"char": ch, "error": "render_empty_but_outline_nonempty"})

    flagged.sort(key=lambda d: ord(d["char"]))
    for item in flagged:
        meta = chars_meta[item["char"]]
        item["page"] = meta.get("page")
        item["half"] = meta.get("half")
        item["box"] = meta.get("box")
        try:
            ob = _outline_bounds(glyphset, cmap[ord(item["char"])])
        except Exception:
            ob = None
        if ob is not None:
            item["outline_bbox"] = ob
        item["reason"] = "long_thin_lines:%d" % len(item["lines"])

    n_lines = sum(len(d["lines"]) for d in flagged)
    counts = {
        "manifest_chars": len(chars_meta),
        "glyphs_scanned": total - len(empty) - len(hard_errors),
        "glyphs_flagged": len(flagged),
        "lines": n_lines,
        "empty_glyphs": len(empty),
        "missing_in_font": 0,
        "render_errors": len(hard_errors),
        "workers": workers,
        "duration_s": round(time.time() - t0, 1),
        "max_flagged": args.max_flagged,
    }
    report = {
        "font": _rel(font_path),
        "font_sha256": _sha256(font_path),
        "n_glyphs": n_glyphs,
        "thresholds": {
            "render_size": size,
            "binarize": f">{BINARIZE}",
            "anchor": "ms",
            "baseline_y": int(BASELINE_FRAC * size),
            "thin_max_px": thin_max,
            "thin_max_at_256": THIN_MAX_AT_256,
            "thickness_tolerance_px": THICKNESS_TOL,
            "length_min_rule": "max(0.5*ink_bbox_long_side, 0.5*render_size)",
            "length_min_floor_px": int(round(LENGTH_FRAC * size)),
            "bridge_px": bridge,
            "erode_iterations": iters,
        },
        "flagged": flagged,
        "counts": counts,
    }
    if empty:
        report["empty_glyph_chars"] = empty[:200]
    if hard_errors:
        report["errors"] = hard_errors[:200]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    print(f"[glyph_frame_gate] flagged={len(flagged)} lines={n_lines} "
          f"scanned={counts['glyphs_scanned']} errors={counts['render_errors']} "
          f"{counts['duration_s']}s -> {_rel(out_path)}", file=sys.stderr)
    if flagged:
        sample = ", ".join(
            "%s(%s)" % (d["char"], "+".join("%s%dpx" % (l["orient"], l["length"])
                                            for l in d["lines"][:2]))
            for d in flagged[:12])
        print(f"[glyph_frame_gate] sample: {sample}", file=sys.stderr)

    if counts["render_errors"]:
        print("[glyph_frame_gate] FAIL(exit 1): 存在渲染错误，结果不完整", file=sys.stderr)
        return 1
    if len(flagged) > args.max_flagged:
        print(f"[glyph_frame_gate] FAIL(exit 3): {len(flagged)} > max_flagged={args.max_flagged}",
              file=sys.stderr)
        return 3
    print("[glyph_frame_gate] PASS(exit 0)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GateError as e:
        print(f"[glyph_frame_gate] ERROR(exit 1): {e}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        print("[glyph_frame_gate] ERROR(exit 1): 未预期异常（fail-closed）", file=sys.stderr)
        sys.exit(1)
