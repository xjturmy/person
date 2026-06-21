"""v2.6 主题 3 板块 F · 金股 ETF 数据层

抓取 4 只主流金股 ETF(金矿股票挂钩)的日 K 与静态信息。

相对实物黄金 ETF(518880 等)是 β 放大工具(通常 1.5-2.5 倍),
跟踪沪深港金属矿业 / 中证有色金属 等股票指数,不再是上海金。

候选 ETF(2026-05):
- 159562  永赢黄金股 ETF             SZ
- 517400  南方有色金矿 ETF           SH
- 159830  华夏中证沪深港金属矿业 ETF  SZ
- 588120  国泰中证沪深港金属矿业 ETF  SH

注:实际名称/管理人以 ak.fund_etf_fund_em() 全市场表为准。
若某只 code 抓不到,先把它换成同主题可用 code(在本表 STOCK_ETF_MASTER
顶部注释里说明)再跑全量。

数据源:
- 日 K  ak.fund_etf_hist_em(symbol, period='daily', adjust='qfq')

写入:
- gold_stock_etf_master(4 行静态)
- gold_stock_etf_prices(日 K,默认 1y)

用法:
    .venv/bin/python .tools/db/fetch_gold_stock_etf.py            # 4 只 ETF 1y
    .venv/bin/python .tools/db/fetch_gold_stock_etf.py --years 2  # 拉 2 年
    .venv/bin/python .tools/db/fetch_gold_stock_etf.py --only 159562
    .venv/bin/python .tools/db/fetch_gold_stock_etf.py --smoke
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
sys.path.insert(0, str(ROOT / ".tools" / "db"))
from gold_schema import DB_PATH, ensure_db  # noqa: E402


# 金股 ETF 静态信息 — 默认 4 只
# 若某只 code 漂移/退市,将该行替换为同主题可用 ETF 并在此注释列明替换原因。
STOCK_ETF_MASTER: list[dict] = [
    {"etf_code": "159562", "etf_name": "永赢黄金股ETF",
     "exchange": "SZ", "manager": "永赢",
     "tracking_index": "中证沪深港黄金产业股票", "fee_rate": 0.50,
     "listing_date": "2024-04-09"},
    {"etf_code": "517400", "etf_name": "南方有色金矿ETF",
     "exchange": "SH", "manager": "南方",
     "tracking_index": "中证有色金属矿业主题", "fee_rate": 0.50,
     "listing_date": "2022-04-13"},
    {"etf_code": "159830", "etf_name": "华夏中证沪深港金属矿业ETF",
     "exchange": "SZ", "manager": "华夏",
     "tracking_index": "中证沪深港金属与采矿业", "fee_rate": 0.50,
     "listing_date": "2022-08-30"},
    {"etf_code": "588120", "etf_name": "国泰中证沪深港金属矿业ETF",
     "exchange": "SH", "manager": "国泰",
     "tracking_index": "中证沪深港金属与采矿业", "fee_rate": 0.50,
     "listing_date": "2023-05-23"},
]


def _retry(fn, attempts: int = 3, sleep: float = 1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last  # type: ignore[misc]


# ───── master ──────────────────────────────────────────────────────────


def upsert_master(con: duckdb.DuckDBPyConnection) -> int:
    df = pd.DataFrame(STOCK_ETF_MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"]).dt.date
    con.register("stock_master_df", df)
    con.execute("""
        INSERT INTO gold_stock_etf_master (etf_code, etf_name, exchange, manager,
                                           tracking_index, fee_rate, listing_date)
        SELECT etf_code, etf_name, exchange, manager, tracking_index, fee_rate, listing_date
        FROM stock_master_df
        ON CONFLICT (etf_code) DO UPDATE SET
            etf_name=EXCLUDED.etf_name, exchange=EXCLUDED.exchange,
            manager=EXCLUDED.manager, tracking_index=EXCLUDED.tracking_index,
            fee_rate=EXCLUDED.fee_rate, listing_date=EXCLUDED.listing_date
    """)
    # last_update 单独 UPDATE(ON CONFLICT 不能写 CURRENT_TIMESTAMP 字面值)
    con.execute(
        "UPDATE gold_stock_etf_master SET last_update=CURRENT_TIMESTAMP "
        "WHERE etf_code IN (SELECT etf_code FROM stock_master_df)"
    )
    con.unregister("stock_master_df")
    return len(df)


# ───── prices ──────────────────────────────────────────────────────────


def _exchange_of(etf_code: str) -> str:
    """从 STOCK_ETF_MASTER 查所属交易所;未匹配按首位猜(5/6→SH,1→SZ)。"""
    for m in STOCK_ETF_MASTER:
        if m["etf_code"] == etf_code:
            return str(m["exchange"]).upper()
    return "SH" if etf_code.startswith(("5", "6")) else "SZ"


def _fetch_sina(etf_code: str, years: int = 1) -> pd.DataFrame:
    """sina 接口 — eastmoney 挂时主用。

    sina 返回 date/open/high/low/close/volume/amount(无 pct_change / turnover_rate)。
    本地补 pct_change = close.pct_change() * 100;turnover_rate 留 None。
    """
    import akshare as ak
    sina_symbol = ("sh" if _exchange_of(etf_code) == "SH" else "sz") + etf_code
    df = _retry(lambda: ak.fund_etf_hist_sina(symbol=sina_symbol), attempts=2, sleep=1.0)
    if df is None or df.empty:
        raise ValueError(f"sina empty for {sina_symbol}")

    df = df.rename(columns={"amount": "turnover"}).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    for c in ("open", "close", "high", "low", "turnover"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

    # 截取最近 N 年
    cutoff = date.today() - timedelta(days=365 * years)
    df = df[df["date"] >= cutoff].sort_values("date").reset_index(drop=True)

    df["pct_change"] = df["close"].pct_change() * 100
    df["turnover_rate"] = pd.NA  # sina 无,留空
    df["etf_code"] = etf_code
    return df.dropna(subset=["date"])


def _fetch_eastmoney(etf_code: str, years: int = 1) -> pd.DataFrame:
    """eastmoney 接口 — 字段更全(含 turnover_rate),但常挂。"""
    import akshare as ak
    end = date.today()
    start = end - timedelta(days=365 * years)

    df = _retry(lambda: ak.fund_etf_hist_em(
        symbol=etf_code, period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq",
    ), attempts=2, sleep=1.0)
    if df is None or df.empty:
        raise ValueError(f"eastmoney empty for {etf_code}")

    rename = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "turnover", "涨跌幅": "pct_change",
        "换手率": "turnover_rate",
    }
    df = df.rename(columns=rename)
    keep = ["date", "open", "close", "high", "low", "volume", "turnover",
            "pct_change", "turnover_rate"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    for c in ("open", "close", "high", "low", "turnover", "pct_change", "turnover_rate"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
    df["etf_code"] = etf_code
    return df.dropna(subset=["date"])


def fetch_etf_one(etf_code: str, years: int = 1) -> pd.DataFrame:
    """先 sina(稳)→ eastmoney 兜底(字段全但常挂)。

    memory「AkShare 数据源:eastmoney 易挂走新浪」— ETF 历史走 sina 主路径。
    """
    try:
        return _fetch_sina(etf_code, years=years)
    except Exception as e_sina:
        try:
            return _fetch_eastmoney(etf_code, years=years)
        except Exception as e_em:
            raise ValueError(
                f"both sources failed for {etf_code} "
                f"(sina: {type(e_sina).__name__}; em: {type(e_em).__name__}: {e_em})"
            ) from e_em


def upsert_prices(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["etf_code", "date", "open", "close", "high", "low",
            "volume", "turnover", "pct_change", "turnover_rate"]
    df = df[[c for c in cols if c in df.columns]].copy()
    con.register("stock_prices_df", df)
    placeholders = ", ".join(c for c in cols if c in df.columns)
    con.execute(f"""
        INSERT OR REPLACE INTO gold_stock_etf_prices ({placeholders})
        SELECT {placeholders} FROM stock_prices_df
    """)
    con.unregister("stock_prices_df")
    return len(df)


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_etf_prices(etf_code: str) -> pd.DataFrame:
    """不联网的合成日 K(5 天),用于测试。"""
    today = date.today()
    return pd.DataFrame({
        "etf_code": etf_code,
        "date": [today - timedelta(days=k) for k in range(5)],
        "open":   [1.020, 1.015, 1.030, 1.045, 1.038],
        "close":  [1.045, 1.030, 1.015, 1.038, 1.045],
        "high":   [1.058, 1.040, 1.045, 1.052, 1.060],
        "low":    [1.010, 1.008, 1.010, 1.030, 1.025],
        "volume": [5000000, 4800000, 5300000, 5100000, 4900000],
        "turnover": [5200000.0, 4900000.0, 5450000.0, 5300000.0, 5100000.0],
        "pct_change": [1.46, -1.44, -1.46, 2.27, 0.68],
        "turnover_rate": [2.50, 2.30, 2.65, 2.55, 2.45],
    })


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--years", type=int, default=1,
                    help="拉几年(默认 1,金股 ETF 上市较新)")
    ap.add_argument("--only", help="单只 ETF code")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    print(f"⛏️  抓金股 ETF → {db_path}")
    if args.smoke:
        print("   (smoke 模式,不联网)")

    # 1. master
    n_master = upsert_master(con)
    print(f"   ✅ {'gold_stock_etf_master':<24} {n_master:>6} 行(静态)")

    # 2. 日 K
    if args.only:
        targets = [args.only]
    else:
        targets = [m["etf_code"] for m in STOCK_ETF_MASTER]
    rows_total = 0
    failures: list[tuple[str, str]] = []
    for code in targets:
        try:
            if args.smoke:
                df = smoke_etf_prices(code)
            else:
                df = fetch_etf_one(code, years=args.years)
            n = upsert_prices(con, df)
            print(f"   ✅ {code} ETF{'':<16} {n:>6} 行")
            rows_total += n
            time.sleep(0.5)
        except Exception as e:
            tb = traceback.format_exc().splitlines()[-1]
            failures.append((code, f"{type(e).__name__}: {e} · {tb}"))
            print(f"   ❌ {code} ETF{'':<16} {type(e).__name__}: {e}", file=sys.stderr)

    # 总结
    n_master_db = con.execute("SELECT COUNT(*) FROM gold_stock_etf_master").fetchone()[0]
    n_prices_db = con.execute("SELECT COUNT(*) FROM gold_stock_etf_prices").fetchone()[0]
    con.close()

    print(f"\n📊 stock ETF master {n_master_db} / prices {n_prices_db}")
    if failures:
        print(f"\n⚠️  {len(failures)} 项失败:")
        for code, err in failures:
            print(f"   {code}: {err}")
        # 至少 1 只成功就允许部分通过(master 已写)
        return 1 if rows_total == 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
