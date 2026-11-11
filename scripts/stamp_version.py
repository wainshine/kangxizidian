#!/usr/bin/env python3
"""为 TTF 盖章版本号（修复「原地修补后内部仍是旧版本」问题）。

用法: python scripts/stamp_version.py --font in.ttf --out out.ttf --version 2.5.5
同时写 nameID 5（Version x.y.z）与 head.fontRevision，并保留 created/modified 不变。
"""
import argparse, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "work", "font", "_pylibs"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", required=True)
    args = ap.parse_args()
    from fontTools.ttLib import TTFont
    f = TTFont(args.font, recalcTimestamp=False)
    name = f["name"]
    v = args.version
    # nameID 5: "Version x.y.z"; nameID 3: unique id
    name.setName(f"Version {v}", 5, 3, 1, 0x409)
    name.setName(f"Version {v}", 5, 1, 0, 0)
    family = name.getDebugName(1) or "KangXi Kai"
    style = name.getDebugName(2) or "Regular"
    name.setName(f"{family} {style} {v}", 3, 3, 1, 0x409)
    name.setName(f"{family} {style} {v}", 3, 1, 0, 0)
    # head.fontRevision: 2.55 之类
    try:
        parts = (v.split(".") + ["0", "0"])[:3]
        f["head"].fontRevision = int(parts[0]) + int(parts[1]) / 10.0 + int(parts[2]) / 100.0
    except Exception:
        pass
    f.save(args.out)
    print("stamped", v, "->", args.out)


if __name__ == "__main__":
    main()
