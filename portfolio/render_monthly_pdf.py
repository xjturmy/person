"""把 .temp/monthly_review_YYYY-MM.md 渲染为 PDF。

使用 weasyprint(纯 Python,系统依赖 cairo/pango)。
若 weasyprint 不可用,降级到 markdown → 简单 HTML 后用浏览器打印(给出指引)。

用法:
    .venv/bin/python .tools/portfolio/render_monthly_pdf.py --month 2026-04
    .venv/bin/python .tools/portfolio/render_monthly_pdf.py --md path/to/x.md --out path/to/x.pdf
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMP_DIR = ROOT / ".temp"
PDF_OUT_DIR = ROOT / ".temp" / "pdf"


_HTML_HEAD = """<!doctype html><html><head><meta charset="utf-8"><style>
@page { size: A4; margin: 18mm 16mm; @bottom-right { content: counter(page) "/" counter(pages); font-size: 9pt; color: #888; } }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 10.5pt; line-height: 1.55; color: #333; }
h1 { color: #1f2937; border-bottom: 3px solid #6366F1; padding-bottom: 6px; font-size: 19pt; }
h2 { color: #4338CA; margin-top: 22px; font-size: 14pt; }
h3 { color: #6366F1; font-size: 12pt; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.5pt; }
th, td { border: 1px solid #d1d5db; padding: 5px 8px; text-align: left; }
th { background: #f3f4f6; font-weight: 600; }
code { background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 9.5pt; }
blockquote { border-left: 3px solid #6366F1; padding-left: 12px; color: #6b7280; margin: 10px 0; }
.footer { color: #9ca3af; font-size: 9pt; text-align: center; margin-top: 24px; border-top: 1px solid #e5e7eb; padding-top: 8px; }
</style></head><body>
"""

_HTML_FOOT = (
    '<div class="footer">preson 月度持仓体检 · 自动生成 · '
    'render_monthly_pdf.py</div></body></html>'
)


def md_to_html(md_text: str) -> str:
    """优先用 markdown 库,失败降级到简单替换。"""
    try:
        import markdown as _md
        body = _md.markdown(md_text, extensions=["tables", "fenced_code"])
    except ImportError:
        # 极简降级:仅把 ## 标题、---、表格转换
        import re
        body = md_text
        body = re.sub(r"^# (.+)$", r"<h1>\1</h1>", body, flags=re.M)
        body = re.sub(r"^## (.+)$", r"<h2>\1</h2>", body, flags=re.M)
        body = re.sub(r"^### (.+)$", r"<h3>\1</h3>", body, flags=re.M)
        body = body.replace("\n\n", "</p><p>")
        body = "<p>" + body + "</p>"
    return _HTML_HEAD + body + _HTML_FOOT


def render_pdf(md_path: Path, pdf_path: Path) -> tuple[bool, str]:
    """返回 (成功标志, 信息)。"""
    if not md_path.exists():
        return False, f"❌ markdown 不存在:{md_path}"

    md_text = md_path.read_text(encoding="utf-8")
    html = md_to_html(md_text)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(pdf_path))
        return True, f"✅ PDF 已生成:{pdf_path}({pdf_path.stat().st_size/1024:.1f} KB)"
    except ImportError:
        # 降级:写 HTML 让用户用浏览器打印
        html_path = pdf_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        return False, (
            f"⚠️  weasyprint 未安装,已写 HTML 替代:{html_path}\n"
            f"   方案 A:`pip install weasyprint`(需要系统 cairo/pango)\n"
            f"   方案 B:用浏览器打开 HTML → 打印 → 另存 PDF"
        )
    except Exception as e:
        return False, f"❌ PDF 生成失败:{e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM(默认本月)")
    ap.add_argument("--md", help="自定义 markdown 路径(覆盖 --month)")
    ap.add_argument("--out", help="自定义 PDF 输出路径")
    args = ap.parse_args()

    if args.md:
        md_path = Path(args.md)
        out = Path(args.out) if args.out else md_path.with_suffix(".pdf")
    else:
        ym = args.month or date.today().strftime("%Y-%m")
        md_path = TEMP_DIR / f"monthly_review_{ym}.md"
        out = Path(args.out) if args.out else PDF_OUT_DIR / f"monthly_review_{ym}.pdf"

    ok, msg = render_pdf(md_path, out)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
