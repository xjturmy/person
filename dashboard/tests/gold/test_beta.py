"""离线测试 gold_stock_beta.py(v2.6 主题 3 板块 G)。

运行:
    cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate
    pytest .tools/dashboard/test_gold_stock_beta.py -v

注意:Agent-DATA 的板块 F 可能尚未把 `gold_stock_etf_master` /
`gold_stock_etf_prices` 写进 ensure_db 的 ALL_DDLS;本测试 fixture 自建表,
完全脱钩。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pytest

# 让 gold_stock_beta 可直接 import(同目录,绕过 .tools.dashboard 包路径)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# 让 .tools.db.gold_schema 可 import(用于 ensure_db 建已有 10 表)
_REPO_ROOT = _THIS_DIR.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gold.beta import GoldStockBeta, compute_all, compute_beta  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────


def _make_dates(n: int, end: date | None = None) -> list[date]:
    """生成 n 个连续工作日的 date 列表(简化:用连续日历日,β 计算不依赖日历)。"""
    end = end or date(2026, 5, 10)
    return [end - timedelta(days=n - 1 - i) for i in range(n)]


def _seed_db(db_path: Path,
             gold_close: np.ndarray,
             stock_close: np.ndarray | None = None,
             stock_code: str = "159562",
             gold_code: str = "518880",
             include_master: bool = True,
             create_stock_table: bool = True) -> None:
    """建临时 gold.duckdb,塞合成数据。

    Parameters
    ----------
    gold_close, stock_close : np.ndarray
        价格序列(同长度)
    create_stock_table : bool
        False 则不创建 gold_stock_etf_prices(测试表缺失场景)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        # 黄金 ETF 价格表(已有 schema)
        con.execute("""
            CREATE TABLE IF NOT EXISTS gold_etf_prices (
                etf_code      VARCHAR NOT NULL,
                date          DATE    NOT NULL,
                open          DOUBLE,
                close         DOUBLE,
                high          DOUBLE,
                low           DOUBLE,
                volume        BIGINT,
                turnover      DOUBLE,
                pct_change    DOUBLE,
                turnover_rate DOUBLE,
                PRIMARY KEY (etf_code, date)
            )
        """)
        if create_stock_table:
            # 板块 F 的金股 ETF 价格表(本测试自建,不依赖 Agent-DATA)
            con.execute("""
                CREATE TABLE IF NOT EXISTS gold_stock_etf_prices (
                    etf_code      VARCHAR NOT NULL,
                    date          DATE    NOT NULL,
                    open          DOUBLE,
                    close         DOUBLE,
                    high          DOUBLE,
                    low           DOUBLE,
                    volume        BIGINT,
                    turnover      DOUBLE,
                    pct_change    DOUBLE,
                    turnover_rate DOUBLE,
                    PRIMARY KEY (etf_code, date)
                )
            """)
        if include_master:
            con.execute("""
                CREATE TABLE IF NOT EXISTS gold_stock_etf_master (
                    etf_code     VARCHAR PRIMARY KEY,
                    etf_name     VARCHAR,
                    exchange     VARCHAR,
                    manager      VARCHAR,
                    tracking     VARCHAR,
                    fee_rate     DOUBLE,
                    listing_date DATE
                )
            """)

        dates = _make_dates(len(gold_close))
        gold_rows = [(gold_code, d, float(c)) for d, c in zip(dates, gold_close)]
        con.executemany(
            "INSERT INTO gold_etf_prices(etf_code, date, close) VALUES (?, ?, ?)",
            gold_rows,
        )
        if stock_close is not None and create_stock_table:
            stock_rows = [(stock_code, d, float(c)) for d, c in zip(dates, stock_close)]
            con.executemany(
                "INSERT INTO gold_stock_etf_prices(etf_code, date, close) "
                "VALUES (?, ?, ?)",
                stock_rows,
            )
    finally:
        con.close()


def _synth_pair(n: int, true_beta: float, noise_sigma: float = 0.002,
                seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """生成 (gold_close, stock_close) 满足 R_stock = β·R_gold + 噪声。"""
    rng = np.random.default_rng(seed)
    gold_ret = rng.normal(0.0, 0.01, n)
    noise = rng.normal(0.0, noise_sigma, n)
    stock_ret = true_beta * gold_ret + noise
    gold_close = 100.0 * np.cumprod(1.0 + gold_ret)
    stock_close = 100.0 * np.cumprod(1.0 + stock_ret)
    return gold_close, stock_close


# ── tests ────────────────────────────────────────────────────────────


def test_synthetic_beta_2x(tmp_path):
    """R_stock = 2 × R_gold + 微噪声 → β ≈ 2.0(±0.1)。"""
    db = tmp_path / "gold.duckdb"
    gold, stock = _synth_pair(n=250, true_beta=2.0, noise_sigma=0.002, seed=1)
    _seed_db(db, gold, stock)

    res = compute_beta("159562", db_path=db)
    assert isinstance(res, GoldStockBeta)
    assert res.beta_30d is not None
    assert res.beta_60d is not None
    assert res.beta_180d is not None
    # 主验证窗口:180 日最稳
    assert abs(res.beta_180d - 2.0) < 0.1, f"β_180d={res.beta_180d}"
    assert abs(res.beta_60d - 2.0) < 0.15, f"β_60d={res.beta_60d}"


def test_synthetic_beta_1x(tmp_path):
    """R_stock = R_gold + 噪声 → β ≈ 1.0。"""
    db = tmp_path / "gold.duckdb"
    gold, stock = _synth_pair(n=250, true_beta=1.0, noise_sigma=0.002, seed=2)
    _seed_db(db, gold, stock)

    res = compute_beta("159562", db_path=db)
    assert res.beta_180d is not None
    assert abs(res.beta_180d - 1.0) < 0.1, f"β_180d={res.beta_180d}"


def test_synthetic_beta_negative(tmp_path):
    """反向相关:R_stock = -1.5 × R_gold + 噪声 → β ≈ -1.5。"""
    db = tmp_path / "gold.duckdb"
    gold, stock = _synth_pair(n=250, true_beta=-1.5, noise_sigma=0.002, seed=3)
    _seed_db(db, gold, stock)

    res = compute_beta("159562", db_path=db)
    assert res.beta_180d is not None
    assert abs(res.beta_180d - (-1.5)) < 0.1, f"β_180d={res.beta_180d}"


def test_insufficient_data_returns_none(tmp_path):
    """只插 10 行 → 30/60/180 都 None,不抛。"""
    db = tmp_path / "gold.duckdb"
    gold, stock = _synth_pair(n=10, true_beta=2.0, seed=4)
    _seed_db(db, gold, stock)

    res = compute_beta("159562", db_path=db)
    assert res.beta_30d is None
    assert res.beta_60d is None
    assert res.beta_180d is None
    assert res.r_squared_60d is None
    assert "缺数据" in res.note or res.n_obs_max < 30


def test_table_missing_returns_none(tmp_path):
    """gold_stock_etf_prices 表不存在 → 返回 dataclass,不抛。"""
    db = tmp_path / "gold.duckdb"
    gold, _ = _synth_pair(n=250, true_beta=2.0, seed=5)
    _seed_db(db, gold, stock_close=None, create_stock_table=False,
             include_master=False)

    res = compute_beta("159562", db_path=db)
    assert isinstance(res, GoldStockBeta)
    assert res.beta_30d is None and res.beta_60d is None and res.beta_180d is None
    assert res.r_squared_60d is None
    assert "缺数据" in res.note


def test_r_squared_in_range(tmp_path):
    """R² 必须在 [0, 1] 区间;高噪声场景 R² 应明显 < 1。"""
    db = tmp_path / "gold.duckdb"
    # 高噪声 → R² 偏低
    gold, stock = _synth_pair(n=250, true_beta=2.0, noise_sigma=0.02, seed=6)
    _seed_db(db, gold, stock)
    res = compute_beta("159562", db_path=db)
    assert res.r_squared_60d is not None
    assert 0.0 <= res.r_squared_60d <= 1.0, f"R²={res.r_squared_60d}"

    # 低噪声 → R² 应接近 1
    db2 = tmp_path / "gold2.duckdb"
    gold2, stock2 = _synth_pair(n=250, true_beta=2.0, noise_sigma=1e-5, seed=7)
    _seed_db(db2, gold2, stock2)
    res2 = compute_beta("159562", db_path=db2)
    assert res2.r_squared_60d is not None
    assert res2.r_squared_60d > 0.95, f"低噪声 R² 应 >0.95,实测 {res2.r_squared_60d}"


def test_compute_all_iterates_master(tmp_path):
    """master 里 3 只 → compute_all 返回 3 个 GoldStockBeta。"""
    db = tmp_path / "gold.duckdb"
    gold, stock = _synth_pair(n=250, true_beta=2.0, seed=8)
    _seed_db(db, gold, stock, stock_code="159562")

    # 再塞两只
    con = duckdb.connect(str(db))
    try:
        _, stock_b = _synth_pair(n=250, true_beta=1.8, seed=9)
        _, stock_c = _synth_pair(n=250, true_beta=2.2, seed=10)
        dates = _make_dates(250)
        for code, close_series in [("159399", stock_b), ("517520", stock_c)]:
            rows = [(code, d, float(c)) for d, c in zip(dates, close_series)]
            con.executemany(
                "INSERT INTO gold_stock_etf_prices(etf_code, date, close) "
                "VALUES (?, ?, ?)",
                rows,
            )
        con.executemany(
            "INSERT INTO gold_stock_etf_master(etf_code, etf_name) VALUES (?, ?)",
            [("159562", "金股A"), ("159399", "金股B"), ("517520", "金股C")],
        )
    finally:
        con.close()

    results = compute_all(db_path=db)
    assert len(results) == 3
    codes = {r.etf_code for r in results}
    assert codes == {"159562", "159399", "517520"}
    for r in results:
        assert isinstance(r, GoldStockBeta)
        assert r.beta_180d is not None


def test_compute_all_empty_when_no_db(tmp_path):
    """DB 文件不存在 → compute_all 返回 []。"""
    db = tmp_path / "nonexistent.duckdb"
    assert compute_all(db_path=db) == []


def test_compute_all_empty_when_no_master(tmp_path):
    """master 表缺失 → 返回 []。"""
    db = tmp_path / "gold.duckdb"
    gold, stock = _synth_pair(n=100, true_beta=2.0, seed=11)
    _seed_db(db, gold, stock, include_master=False)
    assert compute_all(db_path=db) == []


def test_zero_variance_gold_returns_none(tmp_path):
    """黄金 ETF 收盘价恒定(Var=0) → β 应 None,不抛。"""
    db = tmp_path / "gold.duckdb"
    gold = np.full(200, 100.0)  # 恒定价格 → 收益率全 0,Var=0
    rng = np.random.default_rng(99)
    stock_ret = rng.normal(0, 0.01, 200)
    stock = 100.0 * np.cumprod(1.0 + stock_ret)
    _seed_db(db, gold, stock)

    res = compute_beta("159562", db_path=db)
    assert res.beta_30d is None and res.beta_60d is None and res.beta_180d is None
