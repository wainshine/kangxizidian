#!/usr/bin/env python3
"""内容缺失闸（P0-1；v2.6.4 契约版）。

用法: python scripts/content_loss_gate.py <old.ttf> <new.ttf> <old_manifest> <out.json>
指标：ink_ratio = new_ink/old_ink（同 256px 渲染，字形都归一到 760）；iou = 配准后 IoU。
掉墨：ink_ratio < 0.50 或 (ink_ratio < 0.80 且 iou < 0.70) 记为疑似内容缺损。

v2.6.4 契约（审计5代 H1 / E42）：
- **字符宇宙 = baseline font cmap ∩ new font cmap**（两侧都真实可渲染的字）；
- 新增字（new - baseline）、删除字（baseline - new）**单列**，不计入 damaged；
- 输出 JSON 对象（不再是无字段列表），固定字段：
  contract_version / n_expected / n_ok / n_error / damaged / added_chars /
  removed_chars / universe_manifest + sha / gate_pass / exit_code；
- 退出码：2 = 覆盖不足/逐字异常（不可复用）；3 = damaged 超阈值；0 = PASS；
- sidecar 绑定输入 + `extra.out_sha256` 与判定结果（复用方必须校验，失败产物不得复用）。
"""

# --- 并发守卫（AGENTS.md：≤10 workers / CPU≤2000%；先限线程再导入重库）---
import os as _os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
try:
    import cv2 as _cv2
    _cv2.setNumThreads(1)
except Exception:
    pass


import datetime
import hashlib
import json
import os
import sys
import numpy as np, cv2
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_VERSION = 1


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _font_chars(path):
    sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
    from fontTools.ttLib import TTFont
    f = TTFont(path)
    try:
        cmap = set(chr(cp) for cp in f.getBestCmap().keys())
    finally:
        f.close()
    return cmap


def job(args):
    old_font, new_font, chars = args
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))
    from fidelity_eval import glyph_mask_from_font, register_iou
    out = []
    n_ok = 0
    for ch in chars:
        try:
            a = glyph_mask_from_font(old_font, ch)
            b = glyph_mask_from_font(new_font, ch)
            ia, ib = int(a.sum()), int(b.sum())
            if ia == 0:
                # 基线字体实际没有该字（与 universe 取自 cmap 后不应出现）；记 error 由主进程处理
                out.append({"char": ch, "error": "baseline has no ink"})
                continue
            ratio = ib / ia
            iou, _ = register_iou(b, a)
            # 内容缺损判定：明显掉墨且形状不符（高 IoU 的掉墨多为笔画粗细差异，非缺件）
            n_ok += 1
            if ratio < 0.50 or (ratio < 0.80 and iou < 0.70):
                out.append({"char": ch, "ink_old": ia, "ink_new": ib,
                            "ink_ratio": round(ratio, 3), "iou": round(iou, 3)})
        except Exception as e:
            out.append({"char": ch, "error": str(e)[:80]})
    return n_ok, out


def main():
    old_font, new_font, man_path, out_path = sys.argv[1:5]
    max_damaged = int(os.environ.get("CONTENT_LOSS_MAX_DAMAGED", "0"))
    baseline_manifest = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))["chars"]
    baseline_set = set(baseline_manifest)
    old_cmap = _font_chars(old_font)
    new_cmap = _font_chars(new_font)
    common = sorted(old_cmap & new_cmap)
    added = sorted(new_cmap - old_cmap)
    removed = sorted(old_cmap - new_cmap)
    manifest_not_in_old_font = sorted(baseline_set - old_cmap)
    new_chars_not_in_manifest = sorted(new_cmap - baseline_set)

    n = max(1, (len(common) + 7) // 8)
    chunks = [(old_font, new_font, common[i:i + n]) for i in range(0, len(common), n)]
    rows = []
    n_ok_total = 0
    with ProcessPoolExecutor(max_workers=8) as ex:
        for n_ok, res in ex.map(job, chunks):
            n_ok_total += n_ok
            rows.extend(res)
    errors = [r for r in rows if r.get("error")]
    damaged = [r for r in rows if "ink_ratio" in r]
    damaged.sort(key=lambda r: r.get("ink_ratio", 1.0))
    n_error = len(errors)
    coverage_ok = (n_ok_total == len(common) and n_error == 0)
    threshold_ok = len(damaged) <= max_damaged
    gate_pass = coverage_ok and threshold_ok
    exit_code = 0 if gate_pass else (2 if not coverage_ok else 3)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "baseline_font": old_font,
        "new_font": new_font,
        "universe_manifest": man_path,
        "universe_manifest_sha256": _sha256(os.path.join(ROOT, man_path)),
        "universe": "baseline_cmap ∩ new_cmap",
        "n_baseline_cmap": len(old_cmap),
        "n_new_cmap": len(new_cmap),
        "n_expected": len(common),
        "n_ok": n_ok_total,
        "n_error": n_error,
        "coverage_ok": coverage_ok,
        "added_chars": added,
        "removed_chars": removed,
        "manifest_not_in_baseline_font": manifest_not_in_old_font,
        "new_chars_not_in_manifest": new_chars_not_in_manifest,
        "damaged": damaged,
        "threshold": max_damaged,
        "threshold_ok": threshold_ok,
        "gate_pass": gate_pass,
        "exit_code": exit_code,
        "errors": errors,
    }
    out_abs = out_path if os.path.isabs(out_path) else os.path.join(ROOT, out_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w", encoding="utf-8") as fo:
        json.dump(summary, fo, ensure_ascii=False, indent=1)
    out_sha = _sha256(out_abs)

    # 输入绑定 sidecar（BF-12/BF-44 + v2.6.4 判定结果绑定）
    import gate_binding as GB
    GB.write_sidecar(out_abs, GB.build_binding(
        files={"baseline": old_font, "font": new_font, "manifest": man_path},
        scripts=["content_loss_gate.py", "fidelity_eval.py"],
        extra={"contract_version": CONTRACT_VERSION, "out_sha256": out_sha,
               "decision": {"gate_pass": gate_pass, "n_expected": len(common),
                            "n_ok": n_ok_total, "n_error": n_error,
                            "damaged": len(damaged)}}))

    print(json.dumps({"n_expected": len(common), "n_ok": n_ok_total,
                      "n_error": n_error, "damaged": len(damaged),
                      "added_skipped": len(added), "removed_skipped": len(removed),
                      "threshold": max_damaged, "gate_pass": gate_pass,
                      "sample": damaged[:15]}, ensure_ascii=False))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
