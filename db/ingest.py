"""DuckDB 入库脚本 - 全量重建。

读取 02_companies/{folder}/01_基本面数据/历史数据/*.csv,
melt 成长表 (ticker, date, metric, value) 后写入 data/preson.duckdb。

用法:
    .venv/bin/python .tools/db/ingest.py
    .venv/bin/python .tools/db/ingest.py --only 06_贵州茅台,13_伊利股份,12_招商银行
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "preson.duckdb"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
COMPANIES_DIR = ROOT / "02_companies"
CACHE_DIR = ROOT / ".tools" / "db" / "cache"

TABLE_MAP = {
    "估值.csv": "valuation",
    "盈利.csv": "profitability",
    "成长.csv": "growth",
    "现金流.csv": "cashflow",
    "安全性.csv": "safety",
}

DDL = """
CREATE TABLE companies (
    ticker   VARCHAR PRIMARY KEY,
    folder   VARCHAR NOT NULL,
    name     VARCHAR NOT NULL,
    category VARCHAR
);

CREATE TABLE valuation (
    ticker VARCHAR NOT NULL,
    date   DATE    NOT NULL,
    metric VARCHAR NOT NULL,
    value  DOUBLE,
    PRIMARY KEY (ticker, date, metric)
);
CREATE TABLE profitability (
    ticker VARCHAR NOT NULL,
    date   DATE    NOT NULL,
    metric VARCHAR NOT NULL,
    value  DOUBLE,
    PRIMARY KEY (ticker, date, metric)
);
CREATE TABLE growth (
    ticker VARCHAR NOT NULL,
    date   DATE    NOT NULL,
    metric VARCHAR NOT NULL,
    value  DOUBLE,
    PRIMARY KEY (ticker, date, metric)
);
CREATE TABLE cashflow (
    ticker VARCHAR NOT NULL,
    date   DATE    NOT NULL,
    metric VARCHAR NOT NULL,
    value  DOUBLE,
    PRIMARY KEY (ticker, date, metric)
);
CREATE TABLE safety (
    ticker VARCHAR NOT NULL,
    date   DATE    NOT NULL,
    metric VARCHAR NOT NULL,
    value  DOUBLE,
    PRIMARY KEY (ticker, date, metric)
);

CREATE TABLE prices (
    ticker        VARCHAR NOT NULL,
    date          DATE    NOT NULL,
    open          DOUBLE,
    close         DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    volume        BIGINT,
    turnover      DOUBLE,
    pct_change    DOUBLE,
    turnover_rate DOUBLE,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE industry_pe (
    date          DATE    NOT NULL,
    industry_code VARCHAR NOT NULL,
    industry_name VARCHAR,
    level         INTEGER,
    pe_weighted   DOUBLE,
    pe_median     DOUBLE,
    pe_arith      DOUBLE,
    n_companies   INTEGER,
    PRIMARY KEY (date, industry_code)
);

-- dash-01:宏观温度计 5 项(M2 / CPI / 10Y / USDCNY / A50_PE)
-- 由 .tools/db/fetch_macro.py 维护,与 ingest 全量重建解耦
CREATE TABLE macro (
    indicator VARCHAR NOT NULL,
    date      DATE    NOT NULL,
    value     DOUBLE,
    unit      VARCHAR,
    frequency VARCHAR,
    source    VARCHAR DEFAULT 'akshare',
    PRIMARY KEY (indicator, date)
);
CREATE INDEX idx_macro_date ON macro(date);
"""


def normalize_ticker(raw, category: str | None = None) -> str:
    """统一 ticker 为 6 位 zero-padded(A 股)/5 位(港股)字符串。

    - companies.csv 中的 stock 列历史上被 Excel 等工具去掉了前导 0
      (如 '333'/'1'/'63'),新批次又保留了前导 0(如 '000002')。
    - 这里统一:A 股 → zfill(6);港股(category='hk') → zfill(5)。
    - 非纯数字(理论上不会出现) → 原样返回。
    """
    s = str(raw).strip()
    if not s.isdigit():
        return s
    if category == "hk":
        return s.zfill(5)
    return s.zfill(6)


def load_companies() -> pd.DataFrame:
    df = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
    df = df.rename(columns={"stock": "ticker"})
    df["ticker"] = df.apply(lambda r: normalize_ticker(r["ticker"], r.get("category")), axis=1)
    return df[["ticker", "folder", "name", "category"]]


def melt_csv(csv_path: Path, ticker: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "date" not in df.columns or df.empty:
        return pd.DataFrame(columns=["ticker", "date", "metric", "value"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"])
    long = df.melt(id_vars=["date"], var_name="metric", value_name="value")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value"])
    long["ticker"] = ticker
    long = long.drop_duplicates(subset=["ticker", "date", "metric"], keep="last")
    return long[["ticker", "date", "metric", "value"]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build preson DuckDB from per-company CSVs.")
    parser.add_argument("--db", default=str(DB_PATH), help="DuckDB output path")
    parser.add_argument("--only", help="Comma-separated company folders (e.g. 06_贵州茅台,12_招商银行)")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (db_path, db_path.with_suffix(".duckdb.wal")):
        if stale.exists():
            stale.unlink()

    print(f"build {db_path}")
    con = duckdb.connect(str(db_path))
    con.execute(DDL)

    companies = load_companies()
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        companies = companies[companies["folder"].isin(wanted)].reset_index(drop=True)

    con.register("companies_df", companies)
    con.execute(
        "INSERT INTO companies SELECT ticker, folder, name, category FROM companies_df"
    )

    stats: dict[str, int] = {t: 0 for t in TABLE_MAP.values()}
    skipped: list[tuple[str, str]] = []

    for _, row in companies.iterrows():
        ticker = row["ticker"]
        folder = row["folder"]
        hist_dir = COMPANIES_DIR / folder / "01_基本面数据" / "历史数据"
        if not hist_dir.exists():
            skipped.append((folder, "no 历史数据/"))
            continue

        for csv_name, table in TABLE_MAP.items():
            csv_path = hist_dir / csv_name
            if not csv_path.exists():
                skipped.append((f"{folder}/{csv_name}", "missing"))
                continue
            try:
                long = melt_csv(csv_path, ticker)
            except Exception as exc:
                skipped.append((f"{folder}/{csv_name}", f"parse error: {exc}"))
                continue
            if long.empty:
                continue
            con.register("long_df", long)
            con.execute(
                f"INSERT OR IGNORE INTO {table} "
                "SELECT ticker, date, metric, value FROM long_df"
            )
            stats[table] += len(long)

    # ---- AkShare 缓存:prices + industry_pe ----
    prices_dir = CACHE_DIR / "prices"
    if prices_dir.exists():
        for csv_path in sorted(prices_dir.glob("*.csv")):
            ticker = csv_path.stem
            try:
                pdf = pd.read_csv(csv_path, dtype={"ticker": str})
                if pdf.empty:
                    continue
                pdf["date"] = pd.to_datetime(pdf["date"], errors="coerce").dt.date
                pdf = pdf.dropna(subset=["date"])
                pdf = pdf.drop_duplicates(subset=["ticker", "date"], keep="last")
                con.register("prices_df", pdf)
                con.execute(
                    "INSERT OR IGNORE INTO prices "
                    "SELECT ticker, date, open, close, high, low, volume, "
                    "turnover, pct_change, turnover_rate FROM prices_df"
                )
                stats.setdefault("prices", 0)
                stats["prices"] += len(pdf)
            except Exception as exc:
                skipped.append((f"prices/{ticker}", f"load error: {exc}"))

    industry_csv = CACHE_DIR / "industry_pe.csv"
    if industry_csv.exists():
        try:
            idf = pd.read_csv(industry_csv)
            idf["date"] = pd.to_datetime(idf["date"], errors="coerce").dt.date
            idf = idf.dropna(subset=["date", "industry_code"])
            idf = idf.drop_duplicates(subset=["date", "industry_code"], keep="last")
            con.register("ipe_df", idf)
            con.execute(
                "INSERT OR IGNORE INTO industry_pe "
                "SELECT date, industry_code, industry_name, level, "
                "pe_weighted, pe_median, pe_arith, n_companies FROM ipe_df"
            )
            stats["industry_pe"] = len(idf)
        except Exception as exc:
            skipped.append(("industry_pe.csv", f"load error: {exc}"))

    print()
    print("ingest done")
    print(f"  companies     {len(companies):>10}")
    for t, n in stats.items():
        print(f"  {t:<14}{n:>10,} rows")
    if skipped:
        print(f"\nskipped {len(skipped)} entries (first 10):")
        for s in skipped[:10]:
            print(f"  - {s[0]}: {s[1]}")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
