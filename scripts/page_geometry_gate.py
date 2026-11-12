#!/usr/bin/env python3
"""page_geometry_gate.py — 页级几何校验闸（BF-01 三闸之③，S1 几何 × S2 mapping）。

只读 JSON（不渲染 PDF），校验：
  1. 覆盖：geometry 行 / 有 quad 的页与半版 / 无 quad 页 / 无 lattice 页；
  2. 字级：manifest 每个字的 page/half 必须有 quad；
  3. box-in-quad：manifest box（150dpi 原空间）四角变换到 quad 旋转空间，
     判断是否落在 quad["box"] 内（容差 1px）；
  4. 有 quad 但 0 指派：geometry 的每个 quad 半版在 mapping 中是否有 assigned；
  5. 块一致性：font_build.block_for_box(lattice[half], box) 的 2×2 块与 quad
     求交，面积 <50% 或不相交即 bad_blocks；
  6. 同页半版 mapping 框宽/高标准差（只报告 median/p95，不硬判）。

坐标口径（关键，勿反）：
  page_frames.detect_content_quads 返回的 quad["box"] 在**旋转空间**；
  quad["M"]    把 150dpi 原图坐标 -> 旋转空间（page_frames.clip_mask_page 用的就是 M）；
  quad["Minv"] 把旋转空间 -> 原图坐标。
  因此 box-in-quad 必须用 M。用 Minv 等于把方向弄反，会得到不同的越界数；
  本闸在报告里保留 Minv 反向口径的计数作为交叉核对（不参与阈值）。

退出码：0=全部阈值内；3=超阈值（详细计数写入 --out）；1=运行错误。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GEOMETRY = "work/lead/page_geometry.jsonl"
DEFAULT_MAPPING = "work/lead/mapping_block_v271.jsonl"
DEFAULT_MANIFEST = "work/font/build/manifest_v261.json"
DEFAULT_OUT = "work/lead/page-geometry-gate.json"

BOX_TOL_PX = 1.0          # box 四角越界容差（150dpi px）
BAD_BLOCK_RATIO = 0.5     # 2×2 块与 quad 的交集面积下限
HALF_NAMES = ("L", "R")


class GateError(Exception):
    """运行错误（退出码 1）。"""


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (ROOT / p)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except Exception:
        return str(path)


def _read_jsonl(path: Path, what: str) -> list[dict]:
    if not path.is_file():
        raise GateError(f"{what} 不存在: {path}")
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GateError(f"{what} 第 {lineno} 行 JSON 解析失败: {exc}") from exc
                if not isinstance(row, dict):
                    raise GateError(f"{what} 第 {lineno} 行不是 JSON object")
                rows.append(row)
    except OSError as exc:
        raise GateError(f"{what} 读取失败: {exc}") from exc
    if not rows:
        raise GateError(f"{what} 为空: {path}")
    return rows


def _pct(values: list[float], p: float):
    """nearest-rank 百分位（p in [0,1]）。"""
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


def _round(value, digits: int = 4):
    return None if value is None else round(float(value), digits)


def _box4(raw):
    """规范化为 float [x0,y0,x1,y1]；非法返回 None。"""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    if x1 < x0 or y1 < y0:
        return None
    return [x0, y0, x1, y1]


def _mat3(raw):
    """2×3 仿射矩阵 -> [[a,b,c],[d,e,f]]；非法返回 None。"""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        a, b, c = (float(v) for v in raw[0])
        d, e, f = (float(v) for v in raw[1])
    except (TypeError, ValueError, IndexError):
        return None
    mat = [[a, b, c], [d, e, f]]
    if not all(math.isfinite(v) for row in mat for v in row):
        return None
    return mat


def _transform(mat, point):
    x, y = point
    return (mat[0][0] * x + mat[0][1] * y + mat[0][2],
            mat[1][0] * x + mat[1][1] * y + mat[1][2])


def _transform_poly(mat, poly):
    return [_transform(mat, p) for p in poly]


def _box_corners(box):
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _poly_area(poly) -> float:
    if len(poly) < 3:
        return 0.0
    area2 = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        area2 += x1 * y2 - x2 * y1
    return abs(area2) / 2.0


def _clip_poly_rect(poly, rect):
    """Sutherland–Hodgman：凸多边形 × 轴对齐矩形（返回旋转空间多边形）。"""
    x0, y0, x1, y1 = rect

    def clip_edge(points, inside, intersect):
        if not points:
            return []
        out = []
        prev = points[-1]
        prev_in = inside(prev)
        for cur in points:
            cur_in = inside(cur)
            if cur_in:
                if not prev_in:
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif prev_in:
                out.append(intersect(prev, cur))
            prev, prev_in = cur, cur_in
        return out

    def ix_left(p, q):
        t = (x0 - p[0]) / (q[0] - p[0]) if q[0] != p[0] else 0.0
        return (x0, p[1] + t * (q[1] - p[1]))

    def ix_right(p, q):
        t = (x1 - p[0]) / (q[0] - p[0]) if q[0] != p[0] else 0.0
        return (x1, p[1] + t * (q[1] - p[1]))

    def iy_top(p, q):
        t = (y0 - p[1]) / (q[1] - p[1]) if q[1] != p[1] else 0.0
        return (p[0] + t * (q[0] - p[0]), y0)

    def iy_bottom(p, q):
        t = (y1 - p[1]) / (q[1] - p[1]) if q[1] != p[1] else 0.0
        return (p[0] + t * (q[0] - p[0]), y1)

    out = list(poly)
    out = clip_edge(out, lambda p: p[0] >= x0, ix_left)
    out = clip_edge(out, lambda p: p[0] <= x1, ix_right)
    out = clip_edge(out, lambda p: p[1] >= y0, iy_top)
    out = clip_edge(out, lambda p: p[1] <= y1, iy_bottom)
    return out


# --------------------------------------------------------------------------- #
# 输入解析
# --------------------------------------------------------------------------- #
def _half_lattice(row, half):
    if not isinstance(row, dict):
        return None
    raw = (row.get("lattice") or {}).get(half)
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        lat = tuple(float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in lat):
        return None
    return lat


def _half_quad(row, half):
    """返回规范化 quad：{"box": [..], "M":.., "Minv":.., "theta":..}；没有/非法返回 None。"""
    if not isinstance(row, dict):
        return None
    raw = (row.get("quads") or {}).get(half)
    if not isinstance(raw, dict):
        return None
    box = _box4(raw.get("box"))
    mat = _mat3(raw.get("M"))
    if box is None or mat is None:
        return None
    return {"box": box, "M": mat, "Minv": _mat3(raw.get("Minv")), "theta": raw.get("theta")}


def _load_font_build():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import font_build as fb  # noqa: WPS433 （项目内模块，只读）
    except Exception as exc:  # pragma: no cover - 环境错误
        raise GateError(f"import font_build 失败: {exc}") from exc
    return fb.block_for_box


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run(args) -> int:
    geometry_path = _resolve(args.geometry)
    mapping_path = _resolve(args.mapping)
    manifest_path = _resolve(args.manifest)
    out_path = _resolve(args.out)

    if not manifest_path.is_file():
        raise GateError(f"manifest 不存在: {manifest_path}")
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"manifest 读取失败: {exc}") from exc
    chars = manifest.get("chars") if isinstance(manifest, dict) else None
    if not isinstance(chars, dict) or not chars:
        raise GateError(f"manifest 缺少非空 chars: {manifest_path}")

    block_for_box = _load_font_build()

    geom_rows = _read_jsonl(geometry_path, "geometry")
    mapping_rows = _read_jsonl(mapping_path, "mapping")

    # ---- geometry 覆盖 -----------------------------------------------------
    geom = {}
    geometry_error_rows = 0
    duplicate_geometry_pages = 0
    for row in geom_rows:
        if "error" in row or not row.get("page"):
            geometry_error_rows += 1
            continue
        page = str(row["page"])
        if page in geom:
            duplicate_geometry_pages += 1
        geom[page] = row

    quad_halves = []
    for page in sorted(geom):
        row = geom[page]
        for half in HALF_NAMES:
            if _half_quad(row, half) is not None:
                quad_halves.append((page, half))

    pages_with_quad = {page for page, _ in quad_halves}
    quad_halves_by_half = Counter(half for _, half in quad_halves)
    pages_with_lattice = {
        page for page, row in geom.items()
        if any(_half_lattice(row, half) is not None for half in HALF_NAMES)
    }
    quad_halves_with_lattice = [
        key for key in quad_halves if _half_lattice(geom[key[0]], key[1]) is not None
    ]

    coverage = {
        "geometry_lines": len(geom_rows),
        "geometry_pages": len(geom),
        "geometry_error_rows": geometry_error_rows,
        "duplicate_geometry_pages": duplicate_geometry_pages,
        "pages_with_quad": len(pages_with_quad),
        "pages_without_quad": len(geom) - len(pages_with_quad),
        "halves_with_quad": len(quad_halves),
        "halves_with_quad_L": quad_halves_by_half.get("L", 0),
        "halves_with_quad_R": quad_halves_by_half.get("R", 0),
        "pages_without_lattice": len(geom) - len(pages_with_lattice),
        "quad_halves_without_lattice": len(quad_halves) - len(quad_halves_with_lattice),
    }

    # ---- 字级：quad 覆盖 / box-in-quad / 2×2 块 -----------------------------
    missing_quad = []
    bad_boxes = []
    bad_boxes_strict = 0
    bad_boxes_over_2px = 0
    bad_boxes_over_5px = 0
    max_box_overflow = 0.0
    minv_bad = 0
    minv_max_overflow = 0.0
    malformed_manifest_boxes = 0

    bad_blocks = []
    block_ratios = []
    chars_without_lattice = 0
    block_missing = 0
    block_clip_error = 0

    for char in sorted(chars):
        rec = chars[char]
        if not isinstance(rec, dict):
            malformed_manifest_boxes += 1
            continue
        page = str(rec.get("page"))
        half = rec.get("half")
        box = _box4(rec.get("box"))
        if box is None:
            malformed_manifest_boxes += 1
            continue

        row = geom.get(page)
        quad = _half_quad(row, half) if row is not None else None
        if quad is None:
            missing_quad.append({"char": char, "page": page, "half": half})
            continue

        qbox = quad["box"]
        rot_corners = _transform_poly(quad["M"], _box_corners(box))
        overflow = 0.0
        for px, py in rot_corners:
            overflow = max(overflow, qbox[0] - px, px - qbox[2],
                           qbox[1] - py, py - qbox[3])
        max_box_overflow = max(max_box_overflow, overflow)

        if overflow > BOX_TOL_PX + 1e-9:
            bad_boxes.append({
                "char": char,
                "page": page,
                "half": half,
                "box": box,
                "quad_box": qbox,
                "overflow_px": round(overflow, 3),
                "theta": quad.get("theta"),
            })
        if overflow > 1e-9:
            bad_boxes_strict += 1
        if overflow > 2.0:
            bad_boxes_over_2px += 1
        if overflow > 5.0:
            bad_boxes_over_5px += 1

        # 反向口径交叉核对：Minv 是 rot->page，用它做 box->rot 是错的；只报告。
        if quad["Minv"] is not None:
            minv_corners = _transform_poly(quad["Minv"], _box_corners(box))
            minv_overflow = 0.0
            for px, py in minv_corners:
                minv_overflow = max(minv_overflow, qbox[0] - px, px - qbox[2],
                                    qbox[1] - py, py - qbox[3])
            minv_max_overflow = max(minv_max_overflow, minv_overflow)
            if minv_overflow > BOX_TOL_PX + 1e-9:
                minv_bad += 1

        # 2×2 块 × quad：块在原图空间，变换到旋转空间后与 quad box 求交。
        lat = _half_lattice(row, half)
        if lat is None:
            chars_without_lattice += 1
            continue
        block = block_for_box(lat, box)
        if block is None:
            block_missing += 1
            continue
        bx0, by0, bx1, by1 = (float(v) for v in block)
        block_area = (bx1 - bx0) * (by1 - by0)
        if block_area <= 0:
            block_clip_error += 1
            continue
        block_poly = [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]
        try:
            inter = _clip_poly_rect(_transform_poly(quad["M"], block_poly), qbox)
        except Exception:
            block_clip_error += 1
            continue
        inter_area = _poly_area(inter)
        ratio = inter_area / block_area
        block_ratios.append(ratio)
        if inter_area <= 1e-9 or ratio < BAD_BLOCK_RATIO:
            bad_blocks.append({
                "char": char,
                "page": page,
                "half": half,
                "box": box,
                "block": [round(v, 3) for v in block],
                "quad_box": qbox,
                "intersection_area": round(inter_area, 3),
                "block_area": round(block_area, 3),
                "area_ratio": round(ratio, 4),
            })

    bad_boxes.sort(key=lambda d: (-d["overflow_px"], d["char"]))
    bad_blocks.sort(key=lambda d: (d["area_ratio"], d["char"]))
    missing_quad.sort(key=lambda d: (d["page"], str(d["half"]), d["char"]))

    box_in_quad = {
        "transform": "quad.M: 150dpi page -> rotated space (page_frames.clip_mask_page)",
        "tolerance_px": BOX_TOL_PX,
        "bad_boxes": len(bad_boxes),
        "bad_boxes_zero_tolerance": bad_boxes_strict,
        "bad_boxes_over_2px": bad_boxes_over_2px,
        "bad_boxes_over_5px": bad_boxes_over_5px,
        "max_overflow_px": round(max_box_overflow, 3),
        "minv_crosscheck": {
            "note": "Minv 是 rot->page；反向使用仅作核对，不参与阈值",
            "bad_boxes_tolerance_px": minv_bad,
            "max_overflow_px": round(minv_max_overflow, 3),
        },
        "samples": bad_boxes[:20],
    }

    block_consistency = {
        "criterion": "2x2 block ∩ quad; bad if intersection empty or area_ratio < 0.5",
        "transform": "block corners use quad.M -> rotated space",
        "gated": False,
        "note": "报告项：CLI 无 bad_blocks 阈值，不参与退出码",
        "bad_blocks": len(bad_blocks),
        "bad_blocks_no_intersection": sum(1 for d in bad_blocks if d["intersection_area"] <= 1e-9),
        "chars_without_lattice": chars_without_lattice,
        "block_missing": block_missing,
        "block_clip_error": block_clip_error,
        "n_chars_checked": len(block_ratios),
        "min_area_ratio": _round(min(block_ratios)) if block_ratios else None,
        "p01_area_ratio": _round(_pct(block_ratios, 0.01)),
        "median_area_ratio": _round(_pct(block_ratios, 0.50)),
        "samples": bad_blocks[:20],
    }

    # ---- mapping：空指派 ---------------------------------------------------
    mapping_idx = {}
    duplicate_mapping_keys = 0
    mapping_empty_rows = 0
    mapping_assigned_total = 0
    for row in mapping_rows:
        page = str(row.get("page"))
        half = row.get("half")
        key = (page, half)
        if key in mapping_idx:
            duplicate_mapping_keys += 1
        mapping_idx[key] = row
        assigned = row.get("assigned") or []
        mapping_assigned_total += len(assigned)
        if not assigned:
            mapping_empty_rows += 1

    empty_halves = []
    for page, half in quad_halves:
        row = mapping_idx.get((page, half))
        if row is None:
            empty_halves.append({"page": page, "half": half, "reason": "mapping_row_missing"})
        elif not (row.get("assigned") or []):
            empty_halves.append({"page": page, "half": half, "reason": "assigned_empty"})

    empty_with_lattice = sum(
        1 for item in empty_halves
        if _half_lattice(geom.get(item["page"]), item["half"]) is not None
    )
    empty_by_volume = Counter(item["page"][:2] for item in empty_halves)
    empty_by_half = Counter(item["half"] for item in empty_halves)
    mapping_halves_without_quad = sum(
        1 for page, half in mapping_idx
        if _half_quad(geom.get(page), half) is None
    )

    empty_assign = {
        "definition": "geometry 有 quad 的半版，在 mapping 中无行或 assigned 为空",
        "empty_assign_halves": len(empty_halves),
        "mapping_row_missing": sum(1 for x in empty_halves if x["reason"] == "mapping_row_missing"),
        "assigned_empty": sum(1 for x in empty_halves if x["reason"] == "assigned_empty"),
        "empty_halves_with_lattice": empty_with_lattice,
        "empty_halves_without_lattice": len(empty_halves) - empty_with_lattice,
        "empty_halves_vol_01_12": sum(
            1 for item in empty_halves if item["page"][:2] not in ("00", "13")
        ),
        "empty_halves_vol_01_12_with_lattice": sum(
            1 for item in empty_halves
            if item["page"][:2] not in ("00", "13")
            and _half_lattice(geom.get(item["page"]), item["half"]) is not None
        ),
        "by_half": dict(sorted(empty_by_half.items())),
        "by_volume": dict(sorted(empty_by_volume.items())),
        "mapping_rows": len(mapping_rows),
        "mapping_assigned": mapping_assigned_total,
        "mapping_rows_empty_assigned": mapping_empty_rows,
        "duplicate_mapping_keys": duplicate_mapping_keys,
        "mapping_halves_without_quad": mapping_halves_without_quad,
        "includes_01_0006_L": any(
            item["page"] == "01_0006" and item["half"] == "L" for item in empty_halves
        ),
        "halves_first_100": empty_halves[:100],
        # 00/13 卷是总目/补遗，是否应被 mapping 覆盖需口径决策；另给一份排除后的前 100。
        "halves_first_100_vol_01_12": [
            item for item in empty_halves if item["page"][:2] not in ("00", "13")
        ][:100],
    }

    # ---- 同页半版 mapping 框宽/高标准差（只报告，不硬判）-------------------
    per_half = defaultdict(list)
    for row in mapping_rows:
        page = str(row.get("page"))
        half = row.get("half")
        for assigned in row.get("assigned") or []:
            char = assigned.get("char")
            cand = assigned.get("cand") or {}
            box = _box4(cand.get("box") or assigned.get("box"))
            if char and box is not None:
                per_half[(page, half)].append((box[2] - box[0], box[3] - box[1]))

    width_stds = []
    height_stds = []
    all_widths = []
    all_heights = []
    single_box_halves = 0
    for values in per_half.values():
        widths = [w for w, _ in values]
        heights = [h for _, h in values]
        all_widths.extend(widths)
        all_heights.extend(heights)
        if len(values) < 2:
            single_box_halves += 1
            continue
        mean_w = sum(widths) / len(widths)
        mean_h = sum(heights) / len(heights)
        width_stds.append(math.sqrt(sum((w - mean_w) ** 2 for w in widths) / len(widths)))
        height_stds.append(math.sqrt(sum((h - mean_h) ** 2 for h in heights) / len(heights)))

    box_stability = {
        "unit": "px @150dpi",
        "std_method": "population std (ddof=0), per page/half",
        "n_halves": len(per_half),
        "n_halves_ge2": len(width_stds),
        "n_single_box_halves": single_box_halves,
        "n_boxes": len(all_widths),
        "width_std_median": _round(_pct(width_stds, 0.50)),
        "width_std_p95": _round(_pct(width_stds, 0.95)),
        "width_std_max": _round(max(width_stds)) if width_stds else None,
        "height_std_median": _round(_pct(height_stds, 0.50)),
        "height_std_p95": _round(_pct(height_stds, 0.95)),
        "height_std_max": _round(max(height_stds)) if height_stds else None,
        "width_p5": _round(_pct(all_widths, 0.05)),
        "width_p50": _round(_pct(all_widths, 0.50)),
        "width_p95": _round(_pct(all_widths, 0.95)),
        "height_p5": _round(_pct(all_heights, 0.05)),
        "height_p50": _round(_pct(all_heights, 0.50)),
        "height_p95": _round(_pct(all_heights, 0.95)),
        "gated": False,
        "note": "只报告（mapping 质量指标），不参与退出码；p95 为 nearest-rank",
    }

    # ---- 汇总 / 阈值 / 输出 ------------------------------------------------
    counts = {
        # 1) 覆盖
        "geometry_lines": coverage["geometry_lines"],
        "geometry_pages": coverage["geometry_pages"],
        "pages_with_quad": coverage["pages_with_quad"],
        "pages_without_quad": coverage["pages_without_quad"],
        "halves_with_quad": coverage["halves_with_quad"],
        "pages_without_lattice": coverage["pages_without_lattice"],
        "quad_halves_without_lattice": coverage["quad_halves_without_lattice"],
        # 2) 字级
        "manifest_chars": len(chars),
        "missing_quad_chars": len(missing_quad),
        "malformed_manifest_boxes": malformed_manifest_boxes,
        # 3) box-in-quad
        "bad_boxes": len(bad_boxes),
        "bad_boxes_zero_tolerance": bad_boxes_strict,
        "max_box_overflow_px": box_in_quad["max_overflow_px"],
        # 4) 空指派
        "empty_assign_halves": len(empty_halves),
        "empty_assign_mapping_row_missing": empty_assign["mapping_row_missing"],
        "empty_assign_assigned_empty": empty_assign["assigned_empty"],
        # 5) 块一致性（报告项，不参与阈值）
        "bad_blocks": len(bad_blocks),
        # 6) mapping 质量（报告项）
        "box_width_std_median": box_stability["width_std_median"],
        "box_width_std_p95": box_stability["width_std_p95"],
        "box_height_std_median": box_stability["height_std_median"],
        "box_height_std_p95": box_stability["height_std_p95"],
    }

    thresholds = {
        "missing_quad_chars": args.max_missing_quad_chars,
        "bad_boxes": args.max_bad_boxes,
        "empty_assign_halves": args.max_empty_assign_halves,
    }
    checks = {
        "missing_quad_chars": counts["missing_quad_chars"] <= thresholds["missing_quad_chars"],
        "bad_boxes": counts["bad_boxes"] <= thresholds["bad_boxes"],
        "empty_assign_halves": counts["empty_assign_halves"] <= thresholds["empty_assign_halves"],
    }
    ok = all(checks.values())
    exit_code = 0 if ok else 3

    report = {
        "gate": "page_geometry_gate",
        "version": 1,
        "inputs": {
            "geometry": _rel(geometry_path),
            "mapping": _rel(mapping_path),
            "manifest": _rel(manifest_path),
            "manifest_version": manifest.get("version") if isinstance(manifest, dict) else None,
        },
        "coverage": coverage,
        "missing_quad_chars": {
            "count": len(missing_quad),
            "samples": missing_quad[:100],
        },
        "box_in_quad": box_in_quad,
        "empty_assign_halves": empty_assign,
        "block_consistency": block_consistency,
        "mapping_box_stability": box_stability,
        "counts": counts,
        "thresholds": thresholds,
        "checks": checks,
        "ok": ok,
        "exit_code": exit_code,
        "limitations": [
            "box-in-quad 用 quad.M（page->rot）；Minv 是反向，审计 BUILD-04 的 360 越界即 0 容差 M 口径。",
            "empty_assign_halves 按 geometry 全部 quad 半版计，含 00/13 卷与无 lattice 半版；不能区分「无字头」与「漏映射」。",
            "missing_quad_chars 只看 manifest（其字均已落在有 quad 的半版）；canonical 中受缺 quad 影响的字未计入。",
            "块一致性只验 2×2 块与 quad 的几何交集，不验字形墨迹是否真的在块内。",
            "同页框宽/高 σ 仅报告；2 字半版的 σ 会被放大，p95 偏保守。",
        ],
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        raise GateError(f"写出 {out_path} 失败: {exc}") from exc

    summary = {
        "gate": "page_geometry_gate",
        "ok": ok,
        "exit_code": exit_code,
        "counts": counts,
        "thresholds": thresholds,
        "out": _rel(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if not ok:
        for name, passed in checks.items():
            if not passed:
                print(f"FAIL {name}: {counts[name]} > {thresholds[name]}", file=sys.stderr)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="页级几何校验闸（BF-01③）：geometry × mapping × manifest，只读 JSON。",
    )
    parser.add_argument("--geometry", default=DEFAULT_GEOMETRY,
                        help=f"S1 页级几何 JSONL（默认 {DEFAULT_GEOMETRY}）")
    parser.add_argument("--mapping", default=DEFAULT_MAPPING,
                        help=f"S2 mapping JSONL（默认 {DEFAULT_MAPPING}）")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST,
                        help=f"字表 manifest（默认 {DEFAULT_MANIFEST}）")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"闸报告输出（默认 {DEFAULT_OUT}）")
    parser.add_argument("--max-missing-quad-chars", type=int, default=0,
                        help="缺 quad 字数的上限（默认 0）")
    parser.add_argument("--max-bad-boxes", type=int, default=0,
                        help="box 越界字数的上限（默认 0）")
    parser.add_argument("--max-empty-assign-halves", type=int, default=0,
                        help="有 quad 但 0 指派半版数的上限（默认 0）")
    try:
        args = parser.parse_args()
    except SystemExit as exc:  # argparse: --help=0, 参数错误=2 -> 统一运行错误 1
        return 0 if exc.code == 0 else 1

    try:
        return run(args)
    except GateError as exc:
        print(f"[page_geometry_gate] ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - 兜底，避免 traceback 混入 stdout
        print(f"[page_geometry_gate] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
