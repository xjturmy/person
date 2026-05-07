"""黄金分析模块共享 DDL — data/gold.duckdb 8 表。

设计原则(对齐 macro/turnover/etf 三库):
- 独立小库,避免与主 preson.duckdb 写锁冲突
- 长表(metrics)+ 宽表(ratios/percentiles/etf_*)混用,各取所长
- 所有表 idempotent CREATE,可反复 ensure_db()

8 张表:
1. gold_metrics             — 长表,所有时序指标(10+ 项)
2. gold_ratios              — 派生宽表(金油比/金银比/实际利率)
3. gold_percentiles         — 分位快照(metric × window × as_of)
4. gold_etf_master          — ETF 静态信息(518880 等 4 只)
5. gold_etf_prices          — ETF 日 K
6. gold_etf_metrics         — ETF 月度规模/跟踪误差
7. gold_paradigm_signals    — Phase 2.4 范式投票 15 信号当前快照
8. gold_paradigm_history    — Phase 2.4 范式投票历史(每周一行)
"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "gold.duckdb"


# 长表 — 时序数据,新增指标无需改 schema
DDL_METRICS = """
CREATE TABLE IF NOT EXISTS gold_metrics (
    indicator VARCHAR NOT NULL,   -- GOLD_SGE_AU99 / SILVER_SGE_AG99 / OIL_WTI /
                                  -- US_10Y_NOMINAL / US_CPI_YOY / US_REAL_RATE /
                                  -- SPDR_HOLDINGS / GOLD_USD_DERIVED ...
    date      DATE    NOT NULL,
    value     DOUBLE,
    unit      VARCHAR,            -- CNY/g, USD/oz, USD/bbl, %, tonnes, x ...
    frequency VARCHAR,            -- D / M / Q
    source    VARCHAR DEFAULT 'akshare',
    PRIMARY KEY (indicator, date)
);
CREATE INDEX IF NOT EXISTS idx_gold_metrics_date ON gold_metrics(date);
"""

# 宽表 — 派生比率(便于绘图叠加)
DDL_RATIOS = """
CREATE TABLE IF NOT EXISTS gold_ratios (
    date          DATE PRIMARY KEY,
    gold_oil      DOUBLE,         -- 金价 USD/oz / WTI USD/bbl
    gold_silver   DOUBLE,         -- 沪金 CNY/g  / 沪银 CNY/g
    real_rate     DOUBLE,         -- US 10Y - US CPI YoY (%)
    nominal_10y   DOUBLE,         -- US 10Y(% 冗余,便于查)
    cpi_yoy       DOUBLE          -- US CPI YoY(% 冗余)
);
"""

# 分位快照 — 每周一次(metric, window) 二维主键
DDL_PERCENTILES = """
CREATE TABLE IF NOT EXISTS gold_percentiles (
    metric       VARCHAR NOT NULL,  -- gold_oil / gold_silver / real_rate / spdr ...
    window_label VARCHAR NOT NULL,  -- '5y' / '10y' / '20y'(window 是 DuckDB 保留字)
    as_of        DATE    NOT NULL,
    value        DOUBLE,            -- 当前值
    percentile   DOUBLE,            -- 0-1
    n_obs        INTEGER,           -- 窗口内观测数
    PRIMARY KEY (metric, window_label, as_of)
);
"""

# ETF 静态
DDL_ETF_MASTER = """
CREATE TABLE IF NOT EXISTS gold_etf_master (
    etf_code     VARCHAR PRIMARY KEY,
    etf_name     VARCHAR,
    exchange     VARCHAR,         -- SH / SZ
    manager      VARCHAR,         -- 华安 / 博时 / 易方达 / 国泰
    tracking     VARCHAR,         -- 上海金 AU99.99
    fee_rate     DOUBLE,          -- 总费用率(0.6 = 0.6%)
    listing_date DATE,
    last_update  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ETF 日 K
DDL_ETF_PRICES = """
CREATE TABLE IF NOT EXISTS gold_etf_prices (
    etf_code   VARCHAR NOT NULL,
    date       DATE    NOT NULL,
    open       DOUBLE,
    close      DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    volume     BIGINT,
    turnover   DOUBLE,
    pct_change DOUBLE,
    PRIMARY KEY (etf_code, date)
);
CREATE INDEX IF NOT EXISTS idx_gold_etf_date ON gold_etf_prices(date);
"""

# ETF 月度指标
DDL_ETF_METRICS = """
CREATE TABLE IF NOT EXISTS gold_etf_metrics (
    etf_code         VARCHAR NOT NULL,
    month            DATE    NOT NULL,  -- 月末日期
    aum_cny          DOUBLE,            -- 规模(亿元)
    avg_volume_30d   DOUBLE,            -- 30 日均成交额(亿元)
    tracking_error   DOUBLE,            -- 30 日跟踪误差(年化 %)
    PRIMARY KEY (etf_code, month)
);
"""

# Phase 2.4 范式信号当前快照
DDL_PARADIGM_SIGNALS = """
CREATE TABLE IF NOT EXISTS gold_paradigm_signals (
    paradigm   VARCHAR NOT NULL,        -- 'economic' / 'tech' / 'great_power'
    signal_id  VARCHAR NOT NULL,        -- 'kondratiev_phase' / 'vix' / ...
    name       VARCHAR,
    value      VARCHAR,                 -- 当前值(字符串通用)
    threshold  VARCHAR,                 -- 激活阈值
    active     BOOLEAN,                 -- 是否激活
    as_of      DATE NOT NULL,
    PRIMARY KEY (paradigm, signal_id, as_of)
);
"""

# Phase 2.4 范式投票历史
DDL_PARADIGM_HISTORY = """
CREATE TABLE IF NOT EXISTS gold_paradigm_history (
    date            DATE PRIMARY KEY,
    p1_active_count INTEGER,            -- 范式一激活信号数(0-5)
    p2_active_count INTEGER,
    p3_active_count INTEGER,
    p1_active       BOOLEAN,            -- 是否 ≥ 3
    p2_active       BOOLEAN,
    p3_active       BOOLEAN,
    dominant_id     VARCHAR,            -- safe_haven / inflation_hedge / cycle / mixed
    suggested_pct   DOUBLE              -- 建议黄金占比(%)
);
"""

ALL_DDLS = [
    DDL_METRICS,
    DDL_RATIOS,
    DDL_PERCENTILES,
    DDL_ETF_MASTER,
    DDL_ETF_PRICES,
    DDL_ETF_METRICS,
    DDL_PARADIGM_SIGNALS,
    DDL_PARADIGM_HISTORY,
]


def ensure_db(db_path: Path = DB_PATH) -> None:
    """idempotent — 多次调用安全。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        for ddl in ALL_DDLS:
            con.execute(ddl)
    finally:
        con.close()


def show_schema(db_path: Path = DB_PATH) -> None:
    """打印当前所有表 + 行数(运维诊断用)。"""
    if not db_path.exists():
        print(f"❌ DB 不存在:{db_path}")
        return
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
        print(f"📊 {db_path}")
        for (tbl,) in rows:
            n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"   {tbl:30s} {n:>10} 行")
    finally:
        con.close()


if __name__ == "__main__":
    import sys
    ensure_db()
    show_schema()
    sys.exit(0)
