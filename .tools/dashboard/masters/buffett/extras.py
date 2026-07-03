"""Buffett scoring helpers.

This module backs the legacy ``masters.buffett`` public API. It intentionally
uses only local DuckDB/YAML data; full Owner Earnings remains a placeholder
until depreciation, capex and working-capital fields are available.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"
QUALITATIVE_PATH = ROOT / ".config" / "buffett_qualitative.yaml"


@dataclass
class BuffettExtraResult:
    value: float | None
    score: float | None = None
    verified: bool = False
    note: str = ""


def apply_grades(value: float | None, grades: dict[str, dict[str, Any]], *,
                 direction: str = "normal") -> float:
    """Map a numeric value to the configured 5-grade score."""
    if value is None:
        return 0.0

    ordered = ("excellent", "good", "fair", "weak", "fail")
    for key in ordered:
        grade = grades.get(key)
        if not grade:
            continue
        threshold = grade.get("threshold")
        if threshold in ("-inf", "-Inf"):
            threshold = float("-inf")
        elif threshold in ("inf", "Inf"):
            threshold = float("inf")

        if direction == "reverse":
            if value <= float(threshold):
                return float(grade.get("score", 0.0))
        elif value >= float(threshold):
            return float(grade.get("score", 0.0))
    return 0.0


def _series(ticker: str, table: str, metric: str, db_path: Path | str = DB_PATH):
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            f"""
            SELECT date, value
            FROM {table}
            WHERE ticker = ? AND metric = ? AND value IS NOT NULL
            ORDER BY date
            """,
            [ticker, metric],
        ).fetchdf()
    finally:
        con.close()


def _latest(ticker: str, table: str, metric: str, db_path: Path | str = DB_PATH) -> float | None:
    df = _series(ticker, table, metric, db_path)
    if df.empty:
        return None
    return float(df.iloc[-1]["value"])


def _annual_points(df):
    if df.empty:
        return df
    out = df.copy()
    out["year"] = out["date"].dt.year
    return out.groupby("year", as_index=False).tail(1).sort_values("date")


def _cagr(values: list[float], years: int) -> float | None:
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2 or vals[0] == 0:
        return None
    start, end = vals[0], vals[-1]
    if start < 0 and end > 0:
        return None
    ratio = end / start
    if ratio < 0:
        return None
    return ratio ** (1 / max(years, 1)) - 1


def simple_owner_earnings(ticker: str, *, years: int = 10,
                          db_path: Path | str = DB_PATH) -> BuffettExtraResult:
    """Simplified Owner Earnings: use local free cash flow as the proxy."""
    df = _annual_points(_series(ticker, "cashflow", "自由现金流量", db_path))
    if len(df) < 2:
        return BuffettExtraResult(None, None, False, "自由现金流量数据不足")
    window = df.tail(years + 1)
    span = max(int(window.iloc[-1]["date"].year - window.iloc[0]["date"].year), len(window) - 1)
    value = _cagr(window["value"].tolist(), span)
    if value is None:
        return BuffettExtraResult(None, None, False, "自由现金流 CAGR 不可计算")
    return BuffettExtraResult(value, None, True, f"FCF {span} 年 CAGR")


def compute_owner_earnings(ticker: str, *,
                           db_path: Path | str = DB_PATH) -> BuffettExtraResult:
    return BuffettExtraResult(
        None,
        None,
        False,
        "P3 阻塞:缺折旧摊销、维持性 CapEx、营运资金变化字段",
    )


_BANK_GRADES = {
    "excellent": {"threshold": 0.15, "score": 2.0},
    "good": {"threshold": 0.12, "score": 1.5},
    "fair": {"threshold": 0.10, "score": 1.0},
    "weak": {"threshold": 0.07, "score": 0.5},
    "fail": {"threshold": float("-inf"), "score": 0.0},
}


def industry_alt_oe_score(ticker: str, industry_type: str, *,
                          db_path: Path | str = DB_PATH) -> BuffettExtraResult:
    return industry_alt_score(ticker, industry_type, db_path=db_path)


def industry_alt_score(ticker: str, industry_type: str, *,
                       db_path: Path | str = DB_PATH) -> BuffettExtraResult:
    if industry_type == "bank":
        roe = _latest(ticker, "profitability", "净资产收益率(ROE)", db_path)
        pb = _latest(ticker, "valuation", "PB", db_path)
        if roe is None or pb in (None, 0):
            return BuffettExtraResult(None, None, False, "银行 PB-ROE 数据不足")
        value = roe / pb
        return BuffettExtraResult(value, apply_grades(value, _BANK_GRADES), True, "银行 PB-ROE 替代评分")
    if industry_type == "insurance":
        return BuffettExtraResult(None, None, False, "P3 阻塞:缺保险 EV/NBV 字段")
    if industry_type == "high_rd_tech":
        return BuffettExtraResult(None, None, False, "P3 阻塞:缺研发费用资本化还原字段")
    return BuffettExtraResult(None, None, False, f"未知替代行业类型:{industry_type}")


def retained_earnings_breakdown(ticker: str, *, years: int = 10,
                                db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    eps_df = _annual_points(_series(ticker, "growth", "基本每股收益", db_path)).tail(years + 1)
    if eps_df.empty:
        return []

    pe_df = _annual_points(_series(ticker, "valuation", "PE-TTM", db_path))
    div_df = _annual_points(_series(ticker, "valuation", "股息率", db_path))
    pe_by_year = {int(r["date"].year): float(r["value"]) for _, r in pe_df.iterrows()}
    div_by_year = {int(r["date"].year): float(r["value"]) for _, r in div_df.iterrows()}

    rows: list[dict[str, Any]] = []
    prev_eps: float | None = None
    for _, r in eps_df.iterrows():
        year = int(r["date"].year)
        eps = float(r["value"])
        pe = pe_by_year.get(year)
        div_yield = div_by_year.get(year)
        dividend_per_share = None
        if pe is not None and div_yield is not None:
            dividend_per_share = max(eps * pe * div_yield, 0.0)
        retained_eps = eps - dividend_per_share if dividend_per_share is not None else eps
        rows.append({
            "year": year,
            "eps": eps,
            "retained_eps": retained_eps,
            "dividend_per_share": dividend_per_share,
            "eps_growth_yoy": None if prev_eps in (None, 0) else eps / prev_eps - 1,
        })
        prev_eps = eps
    return rows


def retained_earnings_return_rate(ticker: str, *, years: int = 10,
                                  db_path: Path | str = DB_PATH) -> BuffettExtraResult:
    rows = retained_earnings_breakdown(ticker, years=years, db_path=db_path)
    if len(rows) < 2:
        return BuffettExtraResult(None, None, False, "EPS 数据不足")
    eps_delta = rows[-1]["eps"] - rows[0]["eps"]
    retained = sum(max(float(r["retained_eps"] or 0.0), 0.0) for r in rows[:-1])
    if retained <= 0:
        return BuffettExtraResult(None, None, False, "留存 EPS 不可计算")
    return BuffettExtraResult(eps_delta / retained, None, True, "EPS 增量 / 留存 EPS")


def _empty_qualitative() -> dict[str, Any]:
    return {
        "brand": None,
        "switching_cost": None,
        "network_effect": None,
        "economies_of_scale": None,
        "intangible_assets": None,
        "total": None,
        "updated_at": None,
        "notes": None,
    }


def load_qualitative_score(ticker: str, *, path: Path | str = QUALITATIVE_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return _empty_qualitative()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    item = (data.get("companies") or {}).get(str(ticker))
    if not item:
        return _empty_qualitative()
    scores = item.get("scores") or {}
    out = _empty_qualitative()
    for key in ("brand", "switching_cost", "network_effect", "economies_of_scale", "intangible_assets"):
        out[key] = scores.get(key)
    out["total"] = sum(v for v in (out[k] for k in scores.keys() if k in out) if isinstance(v, (int, float)))
    out["updated_at"] = item.get("updated_at")
    out["notes"] = item.get("notes")
    return out


def save_qualitative_score(ticker: str, scores: dict[str, int | float], *,
                           notes: str = "", path: Path | str = QUALITATIVE_PATH) -> bool:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None
    if not isinstance(data, dict):
        data = {}
    data.setdefault("companies", {})
    clean = {
        key: int(scores.get(key, 0))
        for key in ("brand", "switching_cost", "network_effect", "economies_of_scale", "intangible_assets")
    }
    data["companies"][str(ticker)] = {
        "scores": clean,
        "updated_at": date.today().isoformat(),
        "notes": notes,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return True


__all__ = [
    "BuffettExtraResult",
    "apply_grades",
    "compute_owner_earnings",
    "industry_alt_oe_score",
    "industry_alt_score",
    "load_qualitative_score",
    "retained_earnings_breakdown",
    "retained_earnings_return_rate",
    "save_qualitative_score",
    "simple_owner_earnings",
]
