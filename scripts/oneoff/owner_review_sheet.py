#!/usr/bin/env python3
"""生成 owner 审核表：100 字 provenance 核验（成品字形 + 原书裁片 + 页码/框 + 来源标签）。

版式代码统一在 `scripts/review_sheet.py`（owner-provenance 版式），本脚本只做取样与输出。
输出：work/review/owner-provenance-100-<ver>.html/.png/.json/.tsv
"""
import json, os, sys, base64, random, io
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from review_sheet import crop_png, glyph_png, build_sheet, write_tsv  # noqa: E402


def main():
    font = os.environ.get("OWNER_FONT", "work/font/build/KangXiKai-v2.5.8.ttf")
    man_path = os.environ.get("OWNER_MANIFEST", "work/lead/manifest-v258.json")
    ver = os.environ.get("OWNER_VERSION", "v258")
    man = json.load(open(os.path.join(ROOT, man_path), encoding="utf-8"))
    chars = man["chars"]
    basic = [c for c in sorted(chars) if 0x4E00 <= ord(c) <= 0x9FFF]
    random.seed(2026)
    sample = random.sample(basic, min(100, len(basic)))
    rows = []
    for i, ch in enumerate(sample, 1):
        r = chars[ch]
        rows.append({"no": i, "char": ch, "page": r["page"], "half": r.get("half", ""),
                     "box": r["box"], "label_source": r.get("label_source", "")})
    # HTML
    html = ["<html><head><meta charset='utf-8'><style>",
            "body{font-family:-apple-system,sans-serif;margin:20px}",
            "table{border-collapse:collapse}td{border:1px solid #ccc;padding:4px;text-align:center;font-size:13px}",
            "img{display:block}</style></head><body>",
            f"<h2>Owner provenance 核验表（{len(rows)} 字，{ver}）</h2>",
            "<p>每格：左=成品字形；中=原书同字墨迹裁片；右为 编号/字/页码-框/来源标签。",
            "请逐字确认：① 是该字的真迹墨迹（非注文/GAN/拼接）；② 无框线/邻字残片；③ 无缺笔。</p>",
            "<table>"]
    for r in rows:
        g = glyph_png(os.path.join(ROOT, font), r["char"])
        c = crop_png(r["page"], r["box"])
        b1 = io.BytesIO(); g.save(b1, "PNG")
        b2 = io.BytesIO(); c.save(b2, "PNG")
        d1 = base64.b64encode(b1.getvalue()).decode(); d2 = base64.b64encode(b2.getvalue()).decode()
        html.append(f"<tr><td><img src='data:image/png;base64,{d1}'></td>"
                    f"<td><img src='data:image/png;base64,{d2}'></td>"
                    f"<td>#{r['no']}<br>{r['char']}<br>{r['page']} {r['half']}<br>框={r['box']}<br>{r['label_source']}</td></tr>")
    html.append("</table></body></html>")
    out_html = os.path.join(ROOT, f"work/review/owner-provenance-100-{ver}.html")
    open(out_html, "w", encoding="utf-8").write("\n".join(html))
    out_png = os.path.join(ROOT, f"work/review/owner-provenance-100-{ver}.png")
    build_sheet(rows, os.path.join(ROOT, font), out_png)
    json.dump(rows, open(os.path.join(ROOT, f"work/review/owner-provenance-100-{ver}.json"), "w"),
              ensure_ascii=False, indent=1)
    write_tsv(rows, os.path.join(ROOT, f"work/review/owner-provenance-100-{ver}.tsv"))
    print(json.dumps({"html": out_html, "png": out_png, "n": len(rows)}))


if __name__ == "__main__":
    main()
