#!/usr/bin/env python3
"""无拷贝 provenance 闸（BF-01 三闸之一，fail-closed）。

目的：证明 build_stats 的每个字形都能追溯回「当前 mapping 的裁片」，而不是
restore/overlay 旧字形拷贝；同时保证 manifest / mapping / stats 三者自洽。

检查项（任一 FAIL → 退出码 3）：
  1 input_mapping_binding      stats.input_mapping_sha256 == 当前 mapping sha256；
                               stats.input_mapping 路径 == --mapping（允许相对路径）
  2 char_set_manifest_mapping  manifest 字集 == mapping assigned 字集
  3 glyph_coverage_label       stats.glyphs 覆盖 manifest 全部字；label_source 必须
                               严格为 "mapping"（空/repair_overlay/override/... 均 FAIL）
  4 forbidden_copy_markers     stats JSON 序列化全文不得出现 __overlay__ /
                               repair_overlay / contours_override / from_v201_glyph
                               等拷贝通道标记；overlay_n / override_n 必须为 0
  5 glyph_geometry_binding     每字 stats.glyphs[ch].{page,half,box} == manifest[ch]
                               （box 用 tuple(round(v)) 比较，容忍 float/int）
  6 same_box_conflict          同 (page,half,box) 多字 → warning（由 font_qa 判 FAIL，
                               本闸不重复 FAIL）
  7 unknown_stats_chars        stats.glyphs 出现 manifest 之外的字 → FAIL

无拷贝口径：只读 manifest/mapping/stats 三个输入，不读 TTF、不读缓存、不写输入。

用法：
  .venv/bin/python scripts/provenance_gate.py \
      --manifest work/font/build/manifest_v261.json \
      --mapping  work/lead/mapping_block_v270.jsonl \
      --stats    work/font/build/KangXiKai-v2.6.1.build_stats.json \
      --out      work/lead/provenance-gate.json

退出码：0=PASS，3=违规，1=运行错误（输入缺失/JSON 损坏/无法写出报告）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = "work/lead/provenance-gate.json"

# stats 里出现即视为「拷贝通道可用/被使用」的标记（D15/D20/BF-01）
FORBIDDEN_MARKERS = (
    "__overlay__",
    "repair_overlay",
    "repair-overlay",
    "contours_override",
    "from_v201_glyph",
    "restore_overlay",
)
# 计数键：出现且 != 0 即 FAIL（不存在视为 0）
COUNTER_KEYS = ("overlay_n", "override_n", "n_overlay", "n_override")
SAMPLE_LIMIT = 20


class GateError(Exception):
    """运行错误（退出码 1），不是判定违规。"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_input(path_str: str) -> Path:
    """相对路径按项目根解析（与现有闸一致）；不存在也返回可报错的绝对路径。"""
    p = Path(path_str).expanduser()
    if p.is_absolute():
        return p.resolve()
    rooted = ROOT / p
    if rooted.exists():
        return rooted.resolve()
    cwd = Path.cwd() / p
    if cwd.exists():
        return cwd.resolve()
    return rooted.resolve()


def rel_or_abs(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path, what: str):
    if not path.is_file():
        raise GateError(f"{what} 不存在: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise GateError(f"{what} JSON 解析失败: {path}: {e}") from e
    except OSError as e:
        raise GateError(f"{what} 读取失败: {path}: {e}") from e


def load_manifest(path: Path) -> dict:
    data = load_json(path, "manifest")
    chars = data.get("chars") if isinstance(data, dict) else None
    if not isinstance(chars, dict):
        raise GateError("manifest 结构不是 {chars: {char: {...}}}: " + str(path))
    out = {}
    for ch, rec in chars.items():
        if not isinstance(rec, dict):
            raise GateError(f"manifest 字 {ch!r} 的记录不是对象")
        out[str(ch)] = rec
    if not out:
        raise GateError("manifest 字集为空，无法做 provenance 校验")
    return out


def load_mapping(path: Path) -> tuple[dict, dict]:
    """返回 (char -> first record, meta)。重复字/坏 assigned 项都记录，不静默。"""
    if not path.is_file():
        raise GateError(f"mapping 不存在: {path}")
    chars: dict[str, dict] = {}
    duplicates = []
    invalid = []
    n_rows = 0
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                n_rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    raise GateError(f"mapping 第 {lineno} 行 JSON 解析失败: {e}") from e
                if not isinstance(row, dict):
                    invalid.append({"line": lineno, "reason": "row_not_object"})
                    continue
                assigned = row.get("assigned")
                if assigned is None:
                    invalid.append({"line": lineno, "reason": "no_assigned"})
                    continue
                if not isinstance(assigned, list):
                    invalid.append({"line": lineno, "reason": "assigned_not_list"})
                    continue
                for a in assigned:
                    if not isinstance(a, dict) or not a.get("char"):
                        invalid.append({"line": lineno, "reason": "assigned_item_without_char"})
                        continue
                    ch = str(a["char"])
                    cand = a.get("cand") if isinstance(a.get("cand"), dict) else {}
                    box = cand.get("box") or a.get("box")
                    rec = {"page": row.get("page"), "half": row.get("half"), "box": box}
                    if ch in chars:
                        duplicates.append(ch)
                        continue
                    chars[ch] = rec
    except OSError as e:
        raise GateError(f"mapping 读取失败: {path}: {e}") from e
    meta = {
        "rows": n_rows,
        "duplicate_chars": duplicates,
        "invalid_entries": invalid,
    }
    return chars, meta


def box_tuple(box):
    """box → tuple(round(v))；非法返回 None（fail-closed 由调用方记不匹配）。"""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        return tuple(round(float(v)) for v in box)
    except (TypeError, ValueError, OverflowError):
        return None


def walk_counters(obj, path="$"):
    """递归找 overlay_n/override_n 等计数键；返回 [(path, key, value)]。"""
    hits = []
    stack = [(path, obj)]
    while stack:
        cur_path, cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                p = f"{cur_path}.{k}"
                if k in COUNTER_KEYS:
                    hits.append((p, k, v))
                stack.append((p, v))
        elif isinstance(cur, list):
            for i, v in enumerate(cur):
                stack.append((f"{cur_path}[{i}]", v))
    return hits


def marker_context(blob: str, marker: str, width: int = 60) -> str:
    pos = blob.find(marker)
    if pos < 0:
        return ""
    start = max(0, pos - width)
    end = min(len(blob), pos + len(marker) + width)
    return blob[start:end].replace("\n", " ")


def check_record(cid: str, name: str, ok: bool, detail: str, counts=None, samples=None,
                 severity: str = "error") -> dict:
    return {
        "id": cid,
        "name": name,
        "severity": severity,
        "pass": bool(ok),
        "detail": detail,
        "counts": counts or {},
        "samples": samples or [],
    }


def run_gate(manifest_path: Path, mapping_path: Path, stats_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    manifest_chars = set(manifest)
    mapping_chars, mapping_meta = load_mapping(mapping_path)
    mapping_set = set(mapping_chars)
    stats = load_json(stats_path, "build stats")
    if not isinstance(stats, dict):
        raise GateError("build stats 顶层不是对象: " + str(stats_path))
    glyphs = stats.get("glyphs")
    if not isinstance(glyphs, dict):
        raise GateError("build stats 缺少 glyphs 对象: " + str(stats_path))

    mapping_sha = sha256_file(mapping_path)
    stats_sha = sha256_file(stats_path)
    manifest_sha = sha256_file(manifest_path)
    checks = []
    counts = {}

    # ---- 1. stats 绑定当前 mapping（路径 + sha256）----
    declared_sha = stats.get("input_mapping_sha256")
    declared_path = stats.get("input_mapping")
    sha_ok = isinstance(declared_sha, str) and declared_sha.strip().lower() == mapping_sha
    declared_abs = None
    path_ok = False
    if isinstance(declared_path, str) and declared_path.strip():
        declared_abs = resolve_input(declared_path)
        path_ok = declared_abs == mapping_path
    c1 = check_record(
        "input_mapping_binding",
        "stats 绑定当前 mapping（路径 + sha256）",
        sha_ok and path_ok,
        "stats.input_mapping_sha256 与当前 mapping 文件 sha256 一致，且 stats.input_mapping "
        "解析后与 --mapping 为同一文件",
        counts={
            "declared_path": declared_path,
            "declared_path_resolved": rel_or_abs(declared_abs) if declared_abs else None,
            "expected_mapping": rel_or_abs(mapping_path),
            "path_match": path_ok,
            "declared_sha256": declared_sha,
            "actual_sha256": mapping_sha,
            "sha_match": sha_ok,
        },
        samples=[] if (sha_ok and path_ok) else [{
            "sha_match": sha_ok,
            "path_match": path_ok,
            "declared_path": declared_path,
            "expected_mapping": rel_or_abs(mapping_path),
            "declared_sha256": declared_sha,
            "actual_sha256": mapping_sha,
        }],
    )
    checks.append(c1)

    # ---- 2. manifest 字集 == mapping assigned 字集 ----
    missing_in_mapping = sorted(manifest_chars - mapping_set)
    extra_in_mapping = sorted(mapping_set - manifest_chars)
    set_ok = not missing_in_mapping and not extra_in_mapping
    c2_counts = {
        "manifest_chars": len(manifest_chars),
        "mapping_assigned_chars": len(mapping_set),
        "missing_in_mapping": len(missing_in_mapping),
        "extra_in_mapping": len(extra_in_mapping),
        "mapping_rows": mapping_meta["rows"],
        "mapping_duplicate_chars": len(mapping_meta["duplicate_chars"]),
        "mapping_invalid_entries": len(mapping_meta["invalid_entries"]),
    }
    c2_samples = []
    for ch in missing_in_mapping[:SAMPLE_LIMIT]:
        c2_samples.append({"char": ch, "issue": "missing_in_mapping"})
    for ch in extra_in_mapping[:SAMPLE_LIMIT]:
        c2_samples.append({"char": ch, "issue": "extra_in_mapping"})
    c2_detail = "manifest 字集与 mapping assigned 字集相等"
    if not set_ok:
        c2_detail = "manifest 与 mapping assigned 字集不一致（fail-closed）"
    c2 = check_record("char_set_manifest_mapping", "manifest 字集 == mapping assigned 字集",
                      set_ok, c2_detail, counts=c2_counts, samples=c2_samples)
    if mapping_meta["duplicate_chars"]:
        c2["counts"]["mapping_duplicate_sample"] = mapping_meta["duplicate_chars"][:SAMPLE_LIMIT]
    if mapping_meta["invalid_entries"]:
        c2["counts"]["mapping_invalid_sample"] = mapping_meta["invalid_entries"][:SAMPLE_LIMIT]
    checks.append(c2)

    # ---- 3. stats.glyphs 覆盖 + label_source 严格为 mapping ----
    glyph_keys = set(glyphs)
    missing_in_stats = sorted(manifest_chars - glyph_keys)
    bad_label = []
    label_counts = {}
    for ch, rec in glyphs.items():
        src = rec.get("label_source") if isinstance(rec, dict) else None
        key = src if isinstance(src, str) and src else "<missing>"
        label_counts[key] = label_counts.get(key, 0) + 1
        if key != "mapping":
            bad_label.append({"char": ch, "label_source": src})
    coverage_ok = not missing_in_stats
    label_ok = not bad_label
    c3 = check_record(
        "glyph_coverage_label_source",
        "stats.glyphs 覆盖 manifest 全部字且 label_source == 'mapping'",
        coverage_ok and label_ok,
        "stats.glyphs 覆盖 manifest 全部字；每个 label_source 严格为 'mapping'",
        counts={
            "manifest_chars": len(manifest_chars),
            "stats_glyphs": len(glyphs),
            "missing_in_stats": len(missing_in_stats),
            "bad_label_source": len(bad_label),
            "label_source_counts": label_counts,
        },
        samples=(
            [{"char": ch, "issue": "missing_in_stats"} for ch in missing_in_stats[:SAMPLE_LIMIT]]
            + bad_label[:SAMPLE_LIMIT]
        ),
    )
    checks.append(c3)

    # ---- 4. 全文拷贝通道标记 + overlay_n/override_n ----
    try:
        blob = json.dumps(stats, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as e:
        raise GateError(f"stats 无法序列化做全文标记扫描: {e}") from e
    marker_hits = {}
    for m in FORBIDDEN_MARKERS:
        n = blob.count(m)
        if n:
            marker_hits[m] = {"count": n, "context": marker_context(blob, m)}
    counter_hits = walk_counters(stats)
    bad_counters = [{"path": p, "key": k, "value": v} for (p, k, v) in counter_hits
                    if not (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0)]
    markers_ok = not marker_hits and not bad_counters
    c4 = check_record(
        "forbidden_copy_markers",
        "stats 全文无拷贝通道标记，overlay_n/override_n == 0",
        markers_ok,
        "stats JSON 序列化全文不含 __overlay__/repair_overlay/contours_override/"
        "from_v201_glyph 等标记；overlay_n/override_n 均为 0",
        counts={
            "forbidden_markers": list(FORBIDDEN_MARKERS),
            "marker_hits": marker_hits,
            "counter_keys_present": len(counter_hits),
            "bad_counters": len(bad_counters),
        },
        samples=(
            [{"issue": "forbidden_marker", "marker": m, **v} for m, v in marker_hits.items()]
            + bad_counters[:SAMPLE_LIMIT]
        ),
    )
    checks.append(c4)

    # ---- 5. 每字 page/half/box 与 manifest 一致 ----
    mismatch = []
    n_compared = 0
    for ch in sorted(manifest_chars & glyph_keys):
        exp = manifest[ch]
        rec = glyphs.get(ch)
        if not isinstance(rec, dict):
            mismatch.append({"char": ch, "issue": "glyph_record_not_object"})
            continue
        n_compared += 1
        exp_box = box_tuple(exp.get("box"))
        act_box = box_tuple(rec.get("box"))
        page_ok = rec.get("page") == exp.get("page")
        half_ok = rec.get("half") == exp.get("half")
        box_ok = exp_box is not None and act_box is not None and exp_box == act_box
        if not (page_ok and half_ok and box_ok):
            mismatch.append({
                "char": ch,
                "page_match": page_ok,
                "half_match": half_ok,
                "box_match": box_ok,
                "expected": {"page": exp.get("page"), "half": exp.get("half"),
                             "box": list(exp_box) if exp_box else exp.get("box")},
                "actual": {"page": rec.get("page"), "half": rec.get("half"),
                           "box": list(act_box) if act_box else rec.get("box")},
            })
    c5 = check_record(
        "glyph_geometry_binding",
        "每字 stats.{page,half,box} == manifest（box 用 tuple(round(v))）",
        not mismatch,
        "逐字比对 stats.glyphs[ch] 与 manifest[ch] 的 page/half/box；box 容忍 float/int",
        counts={
            "compared": n_compared,
            "mismatch": len(mismatch),
            "manifest_chars": len(manifest_chars),
        },
        samples=mismatch[:SAMPLE_LIMIT],
    )
    checks.append(c5)

    # ---- 6. 同框多字 → warning（不 FAIL）----
    by_box = {}
    for ch, rec in glyphs.items():
        if not isinstance(rec, dict):
            continue
        b = box_tuple(rec.get("box"))
        if b is None:
            continue
        key = (rec.get("page"), rec.get("half"), b)
        by_box.setdefault(key, []).append(ch)
    same_box_groups = [{"page": k[0], "half": k[1], "box": list(k[2]), "chars": sorted(v)}
                       for k, v in sorted(by_box.items(), key=lambda kv: str(kv[0])) if len(v) > 1]
    same_box_chars = sum(len(g["chars"]) for g in same_box_groups)
    c6 = check_record(
        "same_box_conflict",
        "同 (page,half,box) 多字（warning，不重复 FAIL）",
        True,
        "同框冲突由 font_qa 判定；本闸只单列 warning，不计入 FAIL",
        counts={"groups": len(same_box_groups), "chars": same_box_chars},
        samples=same_box_groups[:SAMPLE_LIMIT],
        severity="warning",
    )
    checks.append(c6)

    # ---- 7. stats 出现 manifest 之外的字 → FAIL ----
    unknown = sorted(glyph_keys - manifest_chars)
    c7 = check_record(
        "unknown_stats_chars",
        "stats.glyphs 不含 manifest 之外的字",
        not unknown,
        "stats.glyphs 的每个字都必须出现在 manifest；多出的字视为来源不明",
        counts={"stats_glyphs": len(glyphs), "manifest_chars": len(manifest_chars),
                "unknown": len(unknown)},
        samples=[{"char": ch, "issue": "not_in_manifest"} for ch in unknown[:SAMPLE_LIMIT]],
    )
    checks.append(c7)

    hard_fail = [c for c in checks if c["severity"] == "error" and not c["pass"]]
    # warning 只在确有发现时进顶层 warnings；检查项本身始终在 checks 里（pass=true）
    warnings = [c for c in checks
                if c["severity"] == "warning" and c["counts"].get("groups", 0) > 0]
    passed = not hard_fail

    counts.update({
        "manifest_chars": len(manifest_chars),
        "mapping_assigned_chars": len(mapping_set),
        "stats_glyphs": len(glyphs),
        "stats_missing_manifest_chars": len(missing_in_stats),
        "stats_unknown_chars": len(unknown),
        "bad_label_source": len(bad_label),
        "geometry_mismatch": len(mismatch),
        "same_box_groups": len(same_box_groups),
        "same_box_chars": same_box_chars,
        "forbidden_marker_types": len(marker_hits),
        "bad_overlay_counters": len(bad_counters),
        "checks_total": len(checks),
        "checks_failed": len(hard_fail),
        "warnings": len(warnings),
    })

    return {
        "gate": "provenance_gate",
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pass": passed,
        "exit_code": 0 if passed else 3,
        "verdict": "PASS" if passed else "FAIL",
        "inputs": {
            "manifest": {"path": rel_or_abs(manifest_path), "sha256": manifest_sha},
            "mapping": {"path": rel_or_abs(mapping_path), "sha256": mapping_sha},
            "stats": {"path": rel_or_abs(stats_path), "sha256": stats_sha},
            "stats_declared_input_mapping": declared_path,
        },
        "counts": counts,
        "checks": checks,
        "warnings": warnings,
        "failed_checks": [c["id"] for c in hard_fail],
    }


def write_report(result: dict, out_path: Path) -> None:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_name(out_path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
            f.write("\n")
        tmp.replace(out_path)
    except OSError as e:
        raise GateError(f"报告写出失败: {out_path}: {e}") from e


def print_summary(result: dict) -> None:
    print(f"provenance_gate: {result['verdict']}  "
          f"(manifest={result.get('counts', {}).get('manifest_chars')} "
          f"stats={result.get('counts', {}).get('stats_glyphs')} "
          f"warnings={result.get('counts', {}).get('warnings')})")
    for c in result.get("checks", []):
        flag = "PASS" if c["pass"] else "FAIL"
        if c["severity"] == "warning":
            flag = "WARN"
        print(f"  [{flag}] {c['id']}: {c['detail']}")
        if c["counts"]:
            print(f"         counts={json.dumps(c['counts'], ensure_ascii=False)[:300]}")
    for w in result.get("warnings", []):
        if w["counts"].get("groups"):
            print(f"  warning {w['id']}: {json.dumps(w['samples'], ensure_ascii=False)[:500]}")
    if result.get("failed_checks"):
        print("  failed_checks=" + ",".join(result["failed_checks"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="无拷贝 provenance 闸（fail-closed）")
    ap.add_argument("--manifest", required=True, help="manifest_v*.json（{chars:{...}}）")
    ap.add_argument("--mapping", required=True, help="mapping_block_v*.jsonl")
    ap.add_argument("--stats", required=True, help="<font>.build_stats.json")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help=f"报告输出（默认 {DEFAULT_OUT}；相对路径按项目根）")
    args = ap.parse_args(argv)

    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    try:
        manifest_path = resolve_input(args.manifest)
        mapping_path = resolve_input(args.mapping)
        stats_path = resolve_input(args.stats)
        result = run_gate(manifest_path, mapping_path, stats_path)
        write_report(result, out_path)
    except GateError as e:
        result = {
            "gate": "provenance_gate",
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pass": False,
            "exit_code": 1,
            "verdict": "ERROR",
            "error": str(e),
            "inputs": {
                "manifest": str(args.manifest),
                "mapping": str(args.mapping),
                "stats": str(args.stats),
            },
            "counts": {},
            "checks": [],
            "warnings": [],
            "failed_checks": [],
        }
        try:
            write_report(result, out_path)
        except GateError as we:
            print(f"provenance_gate: ERROR: {e}; 且报告写出失败: {we}", file=sys.stderr)
            return 1
        print(f"provenance_gate: ERROR: {e}", file=sys.stderr)
        return 1

    print_summary(result)
    return 0 if result["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
