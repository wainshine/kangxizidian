#!/usr/bin/env python3
"""闸输入绑定：为扫描/闸输出写 sidecar（输入 sha256 + 脚本 sha256 + 命令行 + git 状态），复用前校验。

背景（审计 BF-12/BF-44）：扫描结果不能只按「字体 sha」复用——参考字体、mapping、page_geometry、
脚本本身变化都会让旧结果失效；旧实现会让换参考字体后的缺件扫描静默复用宋体口径结果。

sidecar 约定：输出文件 `<out>` 的绑定写在 `<out>.sha256`（JSON，非普通 shasum 文件）。
校验失败 = fail-closed（不得当 PASS，也不得静默重跑后不记录）。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDE_SUFFIX = ".sha256"


def sha256_file(path):
    if not path:
        return None
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def rel(path):
    try:
        return os.path.relpath(_abs(path), ROOT)
    except Exception:
        return str(path)


def script_sha(name):
    return sha256_file(os.path.join(ROOT, "scripts", name))


def ref_font_info():
    """参考字体（霞鹜文楷 OFL，唯一来源 reffont.py）；不可用返回 None（调用方决定是否必需）。"""
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import reffont
        p = reffont.path()
        return {"path": rel(p), "sha256": sha256_file(p)}
    except Exception:
        return None


def git_state():
    out = {"commit": None, "dirty": None, "status_n": None}
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode == 0:
            out["commit"] = (r.stdout or "").strip()
        r2 = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, text=True)
        if r2.returncode == 0:
            lines = [ln for ln in (r2.stdout or "").splitlines() if ln.strip()]
            out["status_n"] = len(lines)
            out["dirty"] = bool(lines)
    except Exception:
        pass
    return out


def build_binding(files=None, scripts=(), include_reffont=False, argv=None, extra=None):
    """构造绑定记录。

    files: {逻辑名: 路径}；值是实际输入（font/manifest/mapping/geometry/baseline...）。
    scripts: 参与产出的脚本文件名列表（scripts/ 下）。
    """
    b = {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "argv": list(argv if argv is not None else sys.argv),
        "git": git_state(),
        "files": {},
        "scripts": {},
        "sha256": {},
    }
    for name, path in (files or {}).items():
        if not path:
            b["files"][name] = None
            b["sha256"][name] = None
            continue
        b["files"][name] = {"path": rel(path), "sha256": sha256_file(path)}
        b["sha256"][name] = sha256_file(path)
    for s in scripts:
        b["scripts"][s] = script_sha(s)
    if include_reffont:
        info = ref_font_info()
        b["files"]["reffont"] = info
        b["sha256"]["reffont"] = info["sha256"] if info else None
    if extra:
        b["extra"] = extra
    return b


def sidecar_path(out_path):
    return _abs(out_path) + SIDE_SUFFIX


def write_sidecar(out_path, binding):
    p = sidecar_path(out_path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        json.dump(binding, fo, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def read_sidecar(out_path):
    try:
        with open(sidecar_path(out_path), encoding="utf-8") as fo:
            return json.load(fo)
    except Exception:
        return None


def validate_reuse(out_path, files=None, scripts=(), include_reffont=False,
                   require_out_sha=False, check_git=False):
    """复用前校验：输出存在、sidecar 存在、输入/脚本 sha 一致、判定结果可复用。

    v2.6.4 契约（审计5代 P0-1/P1-4）：
    - `extra.out_sha256` 必须与**当前输出文件**一致（防手工改产物后复用）；
    - sidecar 不得出现期望集合之外的文件 sha（防「多传一个输入」绕过）；
    - 复用失败产物（sidecar.extra.decision 存在时）必须 gate_pass 且 n_error==0；
    - 可选 check_git：clean 状态的 sidecar 跨 commit 复用需显式允许（默认不查）。

    返回 {"ok": bool, "reason": str, "missing": [...], "mismatch": {...}}。
    """
    detail = {"ok": False, "reason": "", "missing": [], "mismatch": {}}
    if not os.path.exists(_abs(out_path)):
        detail["reason"] = "输出文件不存在"
        return detail
    sc = read_sidecar(out_path)
    if sc is None:
        detail["reason"] = "缺少 sidecar（<out>.sha256），无法证明输入一致"
        return detail
    expect = build_binding(files=files, scripts=scripts, include_reffont=include_reffont)
    for name, sha in (expect.get("sha256") or {}).items():
        got = (sc.get("sha256") or {}).get(name)
        if got is None:
            detail["missing"].append(name)
        elif got != sha:
            detail["mismatch"][name] = {"sidecar": got[:12] if got else None,
                                        "current": sha[:12] if sha else None}
    for name, sha in (expect.get("scripts") or {}).items():
        got = (sc.get("scripts") or {}).get(name)
        if got is None:
            detail["missing"].append(f"script:{name}")
        elif got != sha:
            detail["mismatch"][f"script:{name}"] = {"sidecar": (got or "")[:12],
                                                    "current": (sha or "")[:12]}
    # 不允许 sidecar 出现期望之外的输入（旧工具多传输入时曾造成口径漂移）
    allowed = set((expect.get("sha256") or {}).keys()) | {"reffont"}
    for name, got in (sc.get("sha256") or {}).items():
        if name not in allowed:
            detail["mismatch"][f"extra_input:{name}"] = {"sidecar": (got or "")[:12],
                                                         "current": None}
    # 输出自身 sha（防产物被手工修改后复用）
    extra = sc.get("extra") or {}
    out_sha = sha256_file(out_path)
    if extra.get("out_sha256"):
        if extra["out_sha256"] != out_sha:
            detail["mismatch"]["out_file"] = {"sidecar": str(extra["out_sha256"])[:12],
                                              "current": (out_sha or "")[:12]}
    elif require_out_sha:
        detail["missing"].append("extra:out_sha256")
    # 失败产物不可复用（content 闸等写入 decision）
    dec = extra.get("decision")
    if isinstance(dec, dict):
        if not dec.get("gate_pass") or int(dec.get("n_error") or 0) != 0 \
                or int(dec.get("n_ok") or 0) != int(dec.get("n_expected") or 0):
            detail["mismatch"]["decision"] = {"sidecar": dec, "current": "must be gate_pass/coverage_ok"}
    if check_git:
        cur = git_state()
        sg = sc.get("git") or {}
        if sg.get("commit") and cur.get("commit") and sg["commit"] != cur["commit"]:
            detail["mismatch"]["git"] = {"sidecar": sg["commit"][:12],
                                         "current": cur["commit"][:12]}
    detail["ok"] = not detail["missing"] and not detail["mismatch"]
    if not detail["ok"]:
        detail["reason"] = "sidecar 与当前输入/输出不一致（输入/脚本/产物已变）"
    return detail
