#!/usr/bin/env python3
"""Build an external price reference audit for active holdings."""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools"))
sys.path.insert(0, str(ROOT / ".tools" / "dashboard"))

from portfolio.loader import load_portfolio  # noqa: E402
from valuation.external_reference import compare_with_internal  # noqa: E402
from valuation.price_range import compute_by_school  # noqa: E402


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_price(v: float | None) -> str:
    return "" if v is None else f"{v:.2f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return ""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.1f}%"


def _is_stock_holding(h) -> bool:
    name = str(getattr(h, "name", "") or "")
    ticker = str(getattr(h, "ticker", "") or "")
    position_band = getattr(h, "position_band", None) or {}
    company_type = ""
    if isinstance(position_band, dict):
        company_type = str(position_band.get("company_type") or "")
    text = f"{name} {company_type}".upper()
    if "ETF" in text:
        return False
    return ticker.isdigit() and len(ticker) in (5, 6)


def _internal_price(h) -> tuple[float | None, str]:
    band = getattr(h, "price_band", None) or {}
    if isinstance(band, dict):
        fair = _num(band.get("fair_price"))
        if fair is not None:
            return fair, "portfolio.price_band.fair_price"
    try:
        sf = compute_by_school(h.ticker, h.school, name=h.name)
        return sf.fair, sf.method
    except Exception as exc:
        return None, f"内部估值失败:{type(exc).__name__}"


def build_rows() -> list[dict]:
    portfolio = load_portfolio()
    rows: list[dict] = []
    for h in portfolio.active():
        if not _is_stock_holding(h):
            continue
        internal, internal_source = _internal_price(h)
        check = compare_with_internal(h.ticker, h.name, internal)
        ref = check.external
        rows.append({
            "代码": h.ticker,
            "名称": h.name,
            "当前价": _fmt_price(getattr(h, "last_price", None)),
            "内部合理价": _fmt_price(internal),
            "内部口径": internal_source,
            "外部来源": "" if ref is None else ref.source,
            "外部日期": "" if ref is None or ref.as_of is None else ref.as_of.isoformat(),
            "外部目标价": "" if ref is None else _fmt_price(ref.target_mid),
            "外部低/高": "" if ref is None else f"{_fmt_price(ref.target_low)} / {_fmt_price(ref.target_high)}",
            "外部上行": "" if ref is None else _fmt_pct(ref.upside_pct),
            "内外差异": _fmt_pct(check.diff_pct),
            "结论": check.verdict_label,
            "动作": check.action_hint,
        })
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "代码", "名称", "当前价", "内部合理价", "内部口径", "外部来源", "外部日期",
        "外部目标价", "外部低/高", "外部上行", "内外差异", "结论", "动作",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_md(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 外部价格参考审计（{date.today().isoformat()}）",
        "",
        "> 口径:内部合理价为主,外部目标价只做校验;外部明显更乐观时不自动抬高买入线。",
        "",
        "| 标的 | 当前价 | 内部合理价 | 外部目标价 | 内外差异 | 结论 | 动作 |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['名称']} {r['代码']} | {r['当前价']} | {r['内部合理价']} | "
            f"{r['外部目标价'] or '待补'} | {r['内外差异']} | {r['结论']} | {r['动作']} |"
        )
    lines.extend([
        "",
        "## 使用规则",
        "",
        "- 内外差异在 10% 以内:内部估值通过外部交叉验证。",
        "- 外部高于内部超过 10%:只说明市场更乐观,先复核增长假设,不直接提高买入线。",
        "- 外部低于内部超过 10%:优先收紧加仓条件,复核内部估值是否过度乐观。",
        "- ETF 不纳入本表;ETF 用动态价格区间和配置纪律管理。",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成持仓外部目标价审计")
    parser.add_argument(
        "--out-dir",
        default="01_knowledge/05_实战案例与持仓/持仓统计与复盘",
        help="输出目录",
    )
    args = parser.parse_args()
    out_dir = ROOT / args.out_dir
    rows = build_rows()
    csv_path = out_dir / f"{date.today().isoformat()}_外部价格参考审计.csv"
    md_path = out_dir / f"{date.today().isoformat()}_外部价格参考审计.md"
    write_csv(rows, csv_path)
    write_md(rows, md_path)
    print(f"完成: {len(rows)} 只股票")
    print(f"CSV: {csv_path}")
    print(f"MD : {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
