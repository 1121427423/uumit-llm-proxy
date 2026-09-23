#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 DOCUMENTATION.md 渲染成离线单文件 HTML（DOCUMENTATION.html）。

用法：
    python3 tools/render_doc.py            # DOCUMENTATION.md -> DOCUMENTATION.html
    python3 tools/render_doc.py 输入.md 输出.html

依赖： markdown（pip install --break-system-packages markdown）
特点： 单文件、无外链、无脚本依赖；深色排版与 index.html 一致；表格/代码块/目录锚点齐备。
"""
import html
import os
import re
import sys

try:
    import markdown
except ImportError:  # pragma: no cover
    raise SystemExit("需要 markdown 库：pip install --break-system-packages markdown")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 0 80px;
  background: radial-gradient(120% 80% at 50% 0%, #17243c 0%, #0a0d14 55%, #05070b 100%);
  color: #e6ecf5; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  line-height: 1.75; font-size: 15px;
}
.wrap { max-width: 980px; margin: 0 auto; padding: 40px 22px 0; }
h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: .3px; }
h2 { font-size: 22px; margin: 44px 0 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,.10); }
h3 { font-size: 17.5px; margin: 28px 0 8px; color: #cfe0ff; }
h4 { font-size: 15.5px; margin: 22px 0 6px; color: #cfe0ff; }
p, li { color: #d6deea; }
a { color: #7fb0ff; text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: rgba(255,255,255,.07); padding: 1.5px 5px; border-radius: 5px;
       font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 13px; color: #ffd9a8; }
pre { background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.09);
      border-radius: 11px; padding: 14px 16px; overflow-x: auto; }
pre code { background: none; padding: 0; color: #d8e6ff; font-size: 12.8px; line-height: 1.6; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 13.8px; }
th, td { border: 1px solid rgba(255,255,255,.10); padding: 7px 10px; text-align: left; vertical-align: top; }
th { background: rgba(120,170,255,.12); font-weight: 600; }
tr:nth-child(even) td { background: rgba(255,255,255,.018); }
blockquote { margin: 14px 0; padding: 10px 16px; border-left: 3px solid #7fb0ff;
             background: rgba(120,170,255,.07); border-radius: 0 9px 9px 0; color: #cfdcf0; }
blockquote p { margin: 4px 0; }
hr { border: none; border-top: 1px solid rgba(255,255,255,.10); margin: 34px 0; }
img { max-width: 100%; border-radius: 10px; }
.back { display: inline-block; margin-bottom: 18px; padding: 6px 12px; border-radius: 8px;
        background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.10); }
.meta { color: #93a4bb; font-size: 13px; margin-bottom: 8px; }
"""


def render(md_path: str, out_path: str) -> None:
    with open(md_path, encoding="utf-8") as f:
        text = f.read()

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
        extension_configs={"toc": {"permalink": False}},
    )
    body = md.convert(text)

    # 首行大标题交给 h1，其余按原样
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    title = html.escape(title_match.group(1).strip()) if title_match else "制作文档"
    if title_match:  # 避免与 h1 重复
        body = body.replace(f"<h1>{title_match.group(1).strip()}</h1>", "", 1)

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<a class="back" href="./index.html">← 返回播放页</a>
<div class="meta">离线单文件渲染自 <code>{os.path.basename(md_path)}</code> · 重新生成：<code>python3 tools/render_doc.py</code></div>
{body}
</div>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"✓ {os.path.relpath(md_path, ROOT)} → {os.path.relpath(out_path, ROOT)}  "
          f"（{len(doc):,} 字节，{doc.count('<h2')} 个一级小节）")


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "DOCUMENTATION.md")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "DOCUMENTATION.html")
    render(src, dst)


if __name__ == "__main__":
    main()
