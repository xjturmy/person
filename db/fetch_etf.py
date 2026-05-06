"""ETF 行业对标 数据层:AkShare fund_etf_hist_em 抓 ETF K 线 + 入独立 etf.duckdb.

设计:
- 独立 DB(.data/etf.duckdb),与主 preson.duckdb / macro.duckdb 解耦,
  避免 ingest.py 全量重建主库时覆盖 ETF 数据
- 配置在 .config/peers_etf.csv:每家公司 ≥3 个候选 ETF
- 仅拉日 K 净值(open/close/high/low/volume),不拉估值
- 增量:每只 ETF 默认拉近 2 年,首次跑用 --years 5 拉久一点

用法:
    .venv/bin/python .tools/db/fetch_etf.py                  # 全量(45 只 ETF · 近 2 年)
    .venv/bin/python .tools/db/fetch_etf.py --years 5        # 近 5 年
    .venv/bin/python .tools/db/fetch_etf.py --only 512800    # 单只
    .venv/bin/python .tools/db/fetch_etf.py --smoke          # 不联网,插假数据
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "etf.duckdb"
PEERS_CSV = ROOT / ".config" / "peers_etf.csv"

DDL = """
CREATE TABLE IF NOT EXISTS etf_prices (
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
CREATE INDEX IF NOT EXISTS idx_etf_date ON etf_prices(date);

CREATE TABLE IF NOT EXISTS etf_meta (
    etf_code   VARCHAR PRIMARY KEY,
    etf_name   VARCHAR,
    etf_type   VARCHAR,
    last_update DATE
);
"""


def _ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(DDL)
    finally:
        con.close()


def _retry(fn, attempts: int = 3, sleep: float = 1.5):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(sleep * (i + 1))
    if last:
        raise last


def fetch_one(etf_code: str, etf_name: str, years: int = 2) -> pd.DataFrame:
    """拉单只 ETF 历史日 K(qfq 前复权)。失败抛异常。"""
    import akshare as ak
    end = date.today()
    start = end - timedelta(days=365 * years)

    def _call():
        return ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )

    df = _retry(_call)
    if df is None or df.empty:
        raise ValueError(f"empty response for {etf_code}")

    rename = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "turnover", "涨跌幅": "pct_change",
    }
    df = df.rename(columns=rename)
    df = df[["date", "open", "close", "high", "low", "volume", "turnover", "pct_change"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df.insert(0, "etf_code", etf_code)
    return df


def upsert(df: pd.DataFrame, etf_name: str, etf_type: str) -> int:
    if df.empty:
        return 0
    con = duckdb.connect(str(DB_PATH))
    try:
        con.register("etf_df", df)
        con.execute(
            "INSERT OR REPLACE INTO etf_prices "
            "SELECT etf_code, date, open, close, high, low, volume, turnover, pct_change "
            "FROM etf_df"
        )
        con.execute(
            "INSERT OR REPLACE INTO etf_meta VALUES (?, ?, ?, ?)",
            [df["etf_code"].iloc[0], etf_name, etf_type, df["date"].max()],
        )
        return len(df)
    finally:
        con.close()


def smoke_insert() -> None:
    """插假数据,验证 schema + dashboard 联通,不联网。"""
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(DDL)
        rows = []
        for code in ["512800", "512820", "515020"]:
            for i in range(5):
                d = date.today() - timedelta(days=i)
                rows.append((code, d, 1.0 + i * 0.01, 1.01 + i * 0.01,
                             1.02 + i * 0.01, 0.99 + i * 0.01, 100000, 100000.0, 0.5))
        con.executemany(
            "INSERT OR REPLACE INTO etf_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute(
            "INSERT OR REPLACE INTO etf_meta VALUES "
            "('512800', '银行ETF华宝', 'sector', current_date), "
            "('512820', '银行ETF华夏', 'sector', current_date), "
            "('515020', '银行ETF华润', 'sector', current_date)"
        )
        print(f"smoke: inserted 15 rows + 3 meta")
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--only", help="只抓单只 etf_code(如 512800)")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    _ensure_db()
    if args.smoke:
        smoke_insert()
        return 0

    if not PEERS_CSV.exists():
        print(f"❌ {PEERS_CSV} 不存在", file=sys.stderr)
        return 2

    df_cfg = pd.read_csv(PEERS_CSV, dtype={"etf_code": str})
    # 去重(多家公司可能共享同一只 ETF,如酒 ETF)
    unique = df_cfg.drop_duplicates(subset=["etf_code"])[
        ["etf_code", "etf_name", "etf_type"]
    ].reset_index(drop=True)

    if args.only:
        unique = unique[unique["etf_code"] == args.only]
        if unique.empty:
            print(f"❌ {args.only} 不在 peers_etf.csv", file=sys.stderr)
            return 2

    print(f"准备抓 {len(unique)} 只 ETF · 历史 {args.years} 年")
    ok, fail = 0, 0
    for _, r in unique.iterrows():
        code, name, etf_type = r["etf_code"], r["etf_name"], r["etf_type"]
        try:
            df = fetch_one(code, name, years=args.years)
            n = upsert(df, name, etf_type)
            print(f"  ✅ {code} {name:18s} {n} 行")
            ok += 1
        except Exception as e:
            print(f"  ❌ {code} {name:18s} {type(e).__name__}: {e}")
            fail += 1
            traceback.print_exc(file=sys.stderr)
        time.sleep(0.3)  # 友好限速

    print(f"\n完成:✅ {ok} · ❌ {fail} · 库:{DB_PATH}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
