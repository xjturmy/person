"""黄金分析模块共享 DDL — data/gold.duckdb 12 表。

设计原则(对齐 macro/turnover/etf 三库):
- 独立小库,避免与主 preson.duckdb 写锁冲突
- 长表(metrics)+ 宽表(ratios/percentiles/etf_*)混用,各取所长
- 所有表 idempotent CREATE,可反复 ensure_db()

12 张表(含 v2.4 step-D 新增 2 + v2.6 主题 3 板块 F 新增 2):
1. gold_metrics             — 长表,所有时序指标(10+ 项)
2. gold_ratios              — 派生宽表(金油比/金银比/实际利率)
3. gold_percentiles         — 分位快照(metric × window × as_of)
4. gold_etf_master          — ETF 静态信息(518880 等 4 只实物金 ETF)
5. gold_etf_prices          — ETF 日 K(v2.4 加 turnover_rate %)
6. gold_etf_metrics         — ETF 月度规模/跟踪误差
7. gold_paradigm_signals    — Phase 2.4 范式投票 15 信号当前快照
8. gold_paradigm_history    — Phase 2.4 范式投票历史(每周一行)
9. gold_etf_share           — v2.4 step-D · ETF 份额时序(基金资金流入信号)
10. gold_overheat_history   — v2.4 step-D · 短期过热投票历史(每周一行)
11. gold_stock_etf_master   — v2.6 主题 3 板块 F · 金股 ETF 静态(4 只,金矿股 β 放大)
12. gold_stock_etf_prices   — v2.6 主题 3 板块 F · 金股 ETF 日 K
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

# ETF 日 K(v2.4 step-D 加 turnover_rate %,通过 ALTER 兼容旧库)
DDL_ETF_PRICES = """
CREATE TABLE IF NOT EXISTS gold_etf_prices (
    etf_code      VARCHAR NOT NULL,
    date          DATE    NOT NULL,
    open          DOUBLE,
    close         DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    volume        BIGINT,
    turnover      DOUBLE,            -- 成交额(元)
    pct_change    DOUBLE,
    turnover_rate DOUBLE,            -- v2.4 · 换手率(%),fund_etf_hist_em 字段「换手率」
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

# v2.4 step-D · ETF 份额时序(资金流入流出信号)
DDL_ETF_SHARE = """
CREATE TABLE IF NOT EXISTS gold_etf_share (
    etf_code        VARCHAR NOT NULL,
    date            DATE    NOT NULL,
    share           DOUBLE,             -- 基金份额(亿份)
    share_change_5d DOUBLE,             -- 5 日份额变化率(%)
    PRIMARY KEY (etf_code, date)
);
CREATE INDEX IF NOT EXISTS idx_gold_etf_share_date ON gold_etf_share(date);
"""

# v2.4 step-D · 短期过热投票历史(每周一行)
DDL_OVERHEAT_HISTORY = """
CREATE TABLE IF NOT EXISTS gold_overheat_history (
    date           DATE PRIMARY KEY,
    red_count      INTEGER,            -- 红灯信号数(0-6)
    yellow_count   INTEGER,
    green_count    INTEGER,
    verdict_id     VARCHAR,            -- pause / hold / add
    verdict_label  VARCHAR
);
"""

# v2.6 主题 3 板块 F · 金股 ETF 静态(金矿股票挂钩,β 放大 ~1.5-2.5x 实物金)
# 注意:tracking_index 而非 tracking — 金股 ETF 跟踪沪深港金属矿业指数,不再是上海金
DDL_STOCK_ETF_MASTER = """
CREATE TABLE IF NOT EXISTS gold_stock_etf_master (
    etf_code       VARCHAR PRIMARY KEY,
    etf_name       VARCHAR,
    exchange       VARCHAR,           -- SH / SZ
    manager        VARCHAR,           -- 永赢 / 南方 / 华夏 / 国泰
    tracking_index VARCHAR,           -- 沪深港金属矿业 / 中证有色金属 等
    fee_rate       DOUBLE,
    listing_date   DATE,
    last_update    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# v2.6 主题 3 板块 F · 金股 ETF 日 K(列同 gold_etf_prices)
DDL_STOCK_ETF_PRICES = """
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
);
CREATE INDEX IF NOT EXISTS idx_gold_stock_etf_date ON gold_stock_etf_prices(date);
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
    DDL_ETF_SHARE,
    DDL_OVERHEAT_HISTORY,
    DDL_STOCK_ETF_MASTER,
    DDL_STOCK_ETF_PRICES,
]


def _migrate_v24_step_d(con: duckdb.DuckDBPyConnection) -> None:
    """v2.4 step-D 旧库迁移:gold_etf_prices 加 turnover_rate 列。

    DuckDB ALTER ADD COLUMN 不支持 IF NOT EXISTS,这里用 information_schema 检测。
    """
    cols = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='gold_etf_prices'"
    ).fetchall()
    col_names = {c[0] for c in cols}
    if "turnover_rate" not in col_names:
        con.execute("ALTER TABLE gold_etf_prices ADD COLUMN turnover_rate DOUBLE")


def ensure_db(db_path: Path = DB_PATH) -> None:
    """idempotent — 多次调用安全。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        for ddl in ALL_DDLS:
            con.execute(ddl)
        _migrate_v24_step_d(con)
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
