#!/usr/bin/env python3
"""Lead · 全量生产 driver（分批）：渲染→检测→统一坐标→计数/候选准备。

用法：
  .venv/bin/python scripts/lead_run_detect.py --vols 01 --pages body --dpi 300 --workers 8 \
      --out work/detect2/boxes300 --coord-dpi 150
说明：
  --pages body  用 work/lead/page_roles.jsonl 的 body 页；也可写 "6-40" 或 "6,7,8"。
  --coord-dpi 150 时，输出 box 统一折算成 150dpi 当量坐标（与 T1/GLM 约定一致），
  同时保留 dpi 字段标明原始检测 dpi。
输出：<out>/<vol>_<page>.json  （沿用 t1_v2 格式，halves.R/L.cands[*].box 已折算）
"""
import argparse, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "work", "detect2", "_pylibs"))

import importlib
try:
    import lead_t1v2_frozen as t1_v2  # 冻结版，避免与 detector 并行改文件冲突
except ImportError:
    import t1_v2  # noqa: E402


def body_pages(vol):
    roles = []
    for line in open(os.path.join(ROOT, "work/lead/page_roles.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["vol"] == vol and r["role"] == "body":
            roles.append(r["page"])
    return sorted(roles)


def parse_pages(spec, vol):
    if spec == "body":
        return body_pages(vol)
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def convert_coords(path, src_dpi, dst_dpi):
    if src_dpi == dst_dpi:
        return
    from PIL import Image
    r = json.load(open(path))
    f = dst_dpi / src_dpi
    for half in ("R", "L"):
        h = r["halves"].get(half, {})
        for c in h.get("cands", []):
            c["box"] = [int(round(v * f)) for v in c["box"]]
        h["dpi_src"] = src_dpi
    r["dpi"] = dst_dpi
    json.dump(r, open(path, "w"), ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vols", default="01")
    ap.add_argument("--pages", default="body")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, "work/detect2/boxes300"))
    ap.add_argument("--coord-dpi", type=int, default=150)
    ap.add_argument("--montage", default=None)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    for vol in args.vols.split(","):
        pages = parse_pages(args.pages, vol)
        print(f"=== vol {vol}: {len(pages)} pages ===", flush=True)
        # render_dpi=150：实测与 t00 缓存逐像素一致，且 truth 页计数 exact=1.0
        # （300→150 降采样路径会让分类分漂移，0007/0009 计数出错——2026-11-08 实测）
        t1_v2.run_pages(vol, pages, args.dpi, args.out, None, args.montage, 1.0, args.workers,
                        150)
        # 注意：冻结版 t1_v2 内部已统一输出 150dpi 当量坐标（stats.coord_dpi=150），
        # 不要再做二次换算（2026-11-08 修：曾误除 2 导致坐标错误）。
        for p in pages:
            f = os.path.join(args.out, f"{vol}_{p:04d}.json")
            if os.path.exists(f) and args.coord_dpi != 150:
                convert_coords(f, 150, args.coord_dpi)
    print(f"all done in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
