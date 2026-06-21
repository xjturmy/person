#!/usr/bin/env python3
"""
将理杏仁脚本输出的公司档案 CSV 转为同名 Markdown（管道表格），与知识库既有 .md 风格一致：
- 首行标题 `# {文件名不含扩展名}`
- 表格列与 CSV 一致；单元格内数值去掉前导 `=`（与 Excel 导出习惯兼容）
- 表头之后、列数不一致的行作为「脚注」附在表格后（若存在）
"""

from __future__ import annotations

import csv
from pathlib import Path


def _strip_formula_prefix(cell: str) -> str:
    s = (cell or "").strip()
    if s.startswith("="):
        return s[1:]
    return s


def _escape_cell(s: str) -> str:
    t = s.replace("\n", " ").replace("\r", "")
    return t.replace("|", "\\|")


def csv_to_markdown(csv_path: Path) -> str:
    csv_path = Path(csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return f"# {csv_path.stem}\n\n（空文件）\n"

    headers = rows[0]
    n = len(headers)
    body: list[list[str]] = []
    foot: list[str] = []

    for r in rows[1:]:
        if len(r) == n:
            body.append(r)
        else:
            foot.append(",".join(r).strip())

    title = csv_path.stem
    lines: list[str] = [f"# {title}", ""]

    esc_header = [_escape_cell(_strip_formula_prefix(h)) for h in headers]
    lines.append("| " + " | ".join(esc_header) + " |")
    lines.append("| " + " | ".join(["---"] * n) + " |")

    for r in body:
        padded = list(r) + [""] * max(0, n - len(r))
        cells = [_escape_cell(_strip_formula_prefix((padded[i] or "").strip())) for i in range(n)]
        lines.append("| " + " | ".join(cells) + " |")

    if foot:
        lines.append("")
        lines.append("## 脚注")
        for line in foot:
            if line:
                lines.append(line)

    lines.append("")
    return "\n".join(lines)


def write_md_sidecar(csv_path: str | Path) -> Path:
    """在 CSV 同目录生成同名 `.md`，覆盖写入。"""
    csv_path = Path(csv_path)
    md_path = csv_path.with_suffix(".md")
    md_path.write_text(csv_to_markdown(csv_path), encoding="utf-8")
    return md_path
