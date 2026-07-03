from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import duckdb


MODULE_PATH = Path(__file__).resolve().parents[1] / "data_context.py"
spec = importlib.util.spec_from_file_location("data_context", MODULE_PATH)
data_context = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["data_context"] = data_context
spec.loader.exec_module(data_context)


def _make_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        for table in data_context.FINANCIAL_TABLES:
            con.execute(f"CREATE TABLE {table} (ticker VARCHAR, date DATE, metric VARCHAR, value DOUBLE)")
        con.execute("CREATE TABLE valuation (ticker VARCHAR, date DATE, metric VARCHAR, value DOUBLE)")
        con.execute("CREATE TABLE prices (ticker VARCHAR, date DATE, close DOUBLE)")

        con.execute("INSERT INTO profitability VALUES ('000001', DATE '2025-12-31', 'ROE', 0.1)")
        con.execute("INSERT INTO growth VALUES ('000001', DATE '2026-03-31', '收入增长', 0.2)")
        con.execute("INSERT INTO valuation VALUES ('000001', DATE '2026-06-08', 'PE-TTM', 10.0)")
        con.execute("INSERT INTO prices VALUES ('000001', DATE '2026-07-03', 12.3)")
    finally:
        con.close()


def test_build_data_context_labels(tmp_path):
    db_path = tmp_path / "preson.duckdb"
    _make_db(db_path)

    ctx = data_context.build_data_context(db_path)

    assert ctx.financial_period["label"] == "2026Q1"
    assert ctx.annual_year == 2025
    assert ctx.valuation_date["label"] == "2026-06-08"
    assert ctx.price_date["label"] == "2026-07-03"
    assert ctx.notes == []


def test_financial_context_can_be_scoped_to_ticker(tmp_path):
    db_path = tmp_path / "preson.duckdb"
    _make_db(db_path)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("INSERT INTO profitability VALUES ('000002', DATE '2024-12-31', 'ROE', 0.1)")
    finally:
        con.close()

    ctx = data_context.build_data_context(db_path, ticker="000002")

    assert ctx.financial_period["label"] == "2024 年报"
    assert ctx.annual_year == 2024


def test_missing_database_returns_safe_empty_values(tmp_path):
    ctx = data_context.build_data_context(tmp_path / "missing.duckdb")

    assert ctx.financial_period == {"date": None, "label": "—"}
    assert ctx.annual_year is None
    assert ctx.valuation_date == {"date": None, "label": "—"}
    assert ctx.price_date == {"date": None, "label": "—"}
    assert ctx.notes
