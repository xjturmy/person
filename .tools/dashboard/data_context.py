"""Unified data freshness context for the dashboard.

This module is intentionally read-only and Streamlit-free.  It answers one
small question for the rest of the dashboard: what data period are we looking
at right now?
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError:  # pragma: no cover - exercised only in minimal envs
    duckdb = None


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "preson.duckdb"
FINANCIAL_TABLES = ("profitability", "growth", "cashflow", "safety")

EMPTY_PERIOD = {"date": None, "label": "—"}


@dataclass(frozen=True)
class DataContext:
    financial_period: dict[str, Any] = field(default_factory=lambda: dict(EMPTY_PERIOD))
    annual_year: int | None = None
    valuation_date: dict[str, Any] = field(default_factory=lambda: dict(EMPTY_PERIOD))
    price_date: dict[str, Any] = field(default_factory=lambda: dict(EMPTY_PERIOD))
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _empty_period() -> dict[str, Any]:
    return dict(EMPTY_PERIOD)


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def _financial_label(value: Any) -> str:
    d = _coerce_date(value)
    if d is None:
        return "—"
    if d.month == 12 and d.day == 31:
        return f"{d.year} 年报"
    quarter = ((d.month - 1) // 3) + 1
    return f"{d.year}Q{quarter}"


def _date_label(value: Any) -> str:
    d = _coerce_date(value)
    return d.isoformat() if d is not None else "—"


def _connect(db_path: Path | str):
    if duckdb is None:
        return None, "duckdb unavailable"
    path = Path(db_path)
    if not path.exists():
        return None, f"database not found: {path}"
    try:
        return duckdb.connect(str(path), read_only=True), None
    except Exception as exc:  # noqa: BLE001 - this is a dashboard guardrail
        return None, f"database open failed: {exc}"


def _max_date(
    con: Any,
    table: str,
    where: str = "",
    params: list[Any] | None = None,
) -> date | None:
    suffix = f" WHERE {where}" if where else ""
    try:
        row = con.execute(f"SELECT max(date) FROM {table}{suffix}", params or []).fetchone()
    except Exception:  # noqa: BLE001 - missing tables/columns should not break UI
        return None
    return _coerce_date(row[0]) if row else None


def _ticker_where(ticker: str) -> tuple[str, list[Any]]:
    return ("ticker = ?", [ticker]) if ticker else ("", [])


def _latest_financial_period_from_conn(con: Any, ticker: str = "") -> dict[str, Any]:
    where, params = _ticker_where(ticker)
    dates = [_max_date(con, table, where, params) for table in FINANCIAL_TABLES]
    latest = max((d for d in dates if d is not None), default=None)
    if latest is None:
        return _empty_period()
    return {"date": latest, "label": _financial_label(latest)}


def _latest_annual_year_from_conn(con: Any, ticker: str = "") -> int | None:
    params: list[Any] = []
    where = "month(date) = 12 AND day(date) = 31"
    if ticker:
        where += " AND ticker = ?"
        params.append(ticker)
    dates = [
        _max_date(con, table, where, params)
        for table in FINANCIAL_TABLES
    ]
    latest = max((d for d in dates if d is not None), default=None)
    return latest.year if latest is not None else None


def _latest_date_from_conn(con: Any, table: str) -> dict[str, Any]:
    latest = _max_date(con, table)
    if latest is None:
        return _empty_period()
    return {"date": latest, "label": _date_label(latest)}


def latest_financial_period(
    db_path: Path | str = DEFAULT_DB_PATH,
    ticker: str = "",
) -> dict[str, Any]:
    con, _note = _connect(db_path)
    if con is None:
        return _empty_period()
    try:
        return _latest_financial_period_from_conn(con, ticker)
    finally:
        con.close()


def latest_annual_year(
    db_path: Path | str = DEFAULT_DB_PATH,
    ticker: str = "",
) -> int | None:
    con, _note = _connect(db_path)
    if con is None:
        return None
    try:
        return _latest_annual_year_from_conn(con, ticker)
    finally:
        con.close()


def latest_valuation_date(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    con, _note = _connect(db_path)
    if con is None:
        return _empty_period()
    try:
        return _latest_date_from_conn(con, "valuation")
    finally:
        con.close()


def latest_price_date(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    con, _note = _connect(db_path)
    if con is None:
        return _empty_period()
    try:
        return _latest_date_from_conn(con, "prices")
    finally:
        con.close()


def build_data_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    ticker: str = "",
) -> DataContext:
    notes: list[str] = []
    con, note = _connect(db_path)
    if con is None:
        if note:
            notes.append(note)
        return DataContext(notes=notes)

    try:
        financial_period = _latest_financial_period_from_conn(con, ticker)
        annual_year = _latest_annual_year_from_conn(con, ticker)
        valuation_date = _latest_date_from_conn(con, "valuation")
        price_date = _latest_date_from_conn(con, "prices")
    finally:
        con.close()

    if financial_period["date"] is None:
        notes.append("financial statement tables unavailable or empty")
    if annual_year is None:
        notes.append("annual report period unavailable")
    if valuation_date["date"] is None:
        notes.append("valuation table unavailable or empty")
    if price_date["date"] is None:
        notes.append("prices table unavailable or empty")

    return DataContext(
        financial_period=financial_period,
        annual_year=annual_year,
        valuation_date=valuation_date,
        price_date=price_date,
        notes=notes,
    )


def _print_summary(context: DataContext) -> None:
    annual_label = f"{context.annual_year} 年报" if context.annual_year else "—"
    print("Data context")
    print(f"- 财报期: {context.financial_period['label']}")
    print(f"- 最新年报: {annual_label}")
    print(f"- 估值交易日: {context.valuation_date['label']}")
    print(f"- 价格交易日: {context.price_date['label']}")
    if context.notes:
        print("- 备注: " + "; ".join(context.notes))


if __name__ == "__main__":
    _print_summary(build_data_context())
