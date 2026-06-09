"""v2.6 主题 3 板块 F · 金股 ETF 数据层离线测试。

完全离线运行 — 不调用 AkShare。所有 fixture 用 tmp_path 建独立 duckdb。
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "db"))

import fetch_gold_stock_etf as fgse  # noqa: E402
from gold_schema import ensure_db  # noqa: E402


# ───── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """每个测试一个独立 duckdb 文件,schema 已 ensure。"""
    db = tmp_path / "gold_test.duckdb"
    ensure_db(db)
    return db


# ───── tests ───────────────────────────────────────────────────────────


def test_smoke_etf_prices_shape():
    """smoke_etf_prices 返回 5 行 DataFrame,列齐全。"""
    df = fgse.smoke_etf_prices("159562")
    assert len(df) == 5
    required = {"etf_code", "date", "open", "close", "high", "low",
                "volume", "turnover", "pct_change", "turnover_rate"}
    assert required.issubset(set(df.columns))
    assert (df["etf_code"] == "159562").all()


def test_master_idempotent(tmp_db: Path):
    """upsert_master 跑 2 次行数不重复。"""
    con = duckdb.connect(str(tmp_db))
    try:
        n1 = fgse.upsert_master(con)
        n2 = fgse.upsert_master(con)
        assert n1 == n2 == len(fgse.STOCK_ETF_MASTER)
        rows = con.execute(
            "SELECT COUNT(*) FROM gold_stock_etf_master"
        ).fetchone()[0]
        assert rows == len(fgse.STOCK_ETF_MASTER)
    finally:
        con.close()


def test_prices_idempotent(tmp_db: Path):
    """upsert_prices 跑 2 次同样数据,行数不翻倍。"""
    con = duckdb.connect(str(tmp_db))
    try:
        df = fgse.smoke_etf_prices("159562")
        n1 = fgse.upsert_prices(con, df)
        n2 = fgse.upsert_prices(con, df)
        assert n1 == n2 == 5
        rows = con.execute(
            "SELECT COUNT(*) FROM gold_stock_etf_prices WHERE etf_code='159562'"
        ).fetchone()[0]
        assert rows == 5
    finally:
        con.close()


def test_smoke_mode_writes_db(tmp_path):
    """main(['--smoke', '--db', tmp]) 退出码 0,master 4 行,prices 20 行。"""
    db = tmp_path / "gold_smoke.duckdb"
    rc = fgse.main(["--smoke", "--db", str(db)])
    assert rc == 0

    con = duckdb.connect(str(db), read_only=True)
    try:
        n_master = con.execute(
            "SELECT COUNT(*) FROM gold_stock_etf_master"
        ).fetchone()[0]
        n_prices = con.execute(
            "SELECT COUNT(*) FROM gold_stock_etf_prices"
        ).fetchone()[0]
        assert n_master == 4
        assert n_prices == 20  # 4 ETF × 5 天
    finally:
        con.close()


def test_schema_compatible(tmp_db: Path):
    """ensure_db 后 2 张新表都存在。"""
    con = duckdb.connect(str(tmp_db), read_only=True)
    try:
        tables = {
            r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main'"
            ).fetchall()
        }
        assert "gold_stock_etf_master" in tables
        assert "gold_stock_etf_prices" in tables
    finally:
        con.close()


def test_only_filter(tmp_path):
    """--only 159562 仅写一只 ETF 的日 K(master 仍写 4 行)。"""
    db = tmp_path / "gold_only.duckdb"
    rc = fgse.main(["--smoke", "--db", str(db), "--only", "159562"])
    assert rc == 0

    con = duckdb.connect(str(db), read_only=True)
    try:
        codes = [
            r[0] for r in con.execute(
                "SELECT DISTINCT etf_code FROM gold_stock_etf_prices"
            ).fetchall()
        ]
        assert codes == ["159562"]
        n_prices = con.execute(
            "SELECT COUNT(*) FROM gold_stock_etf_prices"
        ).fetchone()[0]
        assert n_prices == 5
    finally:
        con.close()


def test_master_columns_v26(tmp_db: Path):
    """gold_stock_etf_master 列含 tracking_index(而非 tracking)。"""
    con = duckdb.connect(str(tmp_db), read_only=True)
    try:
        cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='gold_stock_etf_master'"
            ).fetchall()
        }
        assert "tracking_index" in cols
        assert "tracking" not in cols  # 实物金的字段名,不该出现在金股表
    finally:
        con.close()
