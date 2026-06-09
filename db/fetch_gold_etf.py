"""黄金分析模块 · Phase 2.2-3:抓黄金 ETF + (可选)SPDR 持仓

国内 4 只黄金 ETF(全部跟踪上海金 AU99.99):
- 518880  华安黄金 ETF      上交所  ⭐ 规模最大、流动性最好
- 159937  博时黄金 ETF      深交所
- 159934  易方达黄金 ETF    深交所
- 518800  国泰黄金 ETF      上交所

数据源:
- ETF 日 K  ak.fund_etf_hist_em(symbol, period='daily', adjust='qfq')
- SPDR 持仓  ak.macro_cons_gold(jin10.com)— 中国 IP 频繁挂,**走手填 CSV 备选**:
             .config/spdr_holdings_manual.csv  (列:date,tonnes,value_usd)

写入:
- gold_etf_master(4 行静态)
- gold_etf_prices(日 K)
- gold_metrics 增 SPDR_HOLDINGS(若 SPDR 走 AkShare 或手填 CSV 任一成功)

用法:
    .venv/bin/python .tools/db/fetch_gold_etf.py            # 4 只 ETF + 试拉 SPDR
    .venv/bin/python .tools/db/fetch_gold_etf.py --years 5  # 拉 5 年
    .venv/bin/python .tools/db/fetch_gold_etf.py --only 518880
    .venv/bin/python .tools/db/fetch_gold_etf.py --skip-spdr
    .venv/bin/python .tools/db/fetch_gold_etf.py --smoke
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

SPDR_MANUAL_CSV = ROOT / ".config" / "spdr_holdings_manual.csv"

# ETF 静态信息(实际规模/费率随市场变化,这里写常量,Phase 2.3 时由 Tab 显示提示)
ETF_MASTER: list[dict] = [
    {"etf_code": "518880", "etf_name": "华安黄金ETF",   "exchange": "SH",
     "manager": "华安",   "tracking": "上海金AU99.99", "fee_rate": 0.60,
     "listing_date": "2013-07-29"},
    {"etf_code": "159937", "etf_name": "博时黄金ETF",   "exchange": "SZ",
     "manager": "博时",   "tracking": "上海金AU99.99", "fee_rate": 0.60,
     "listing_date": "2014-08-13"},
    {"etf_code": "159934", "etf_name": "易方达黄金ETF", "exchange": "SZ",
     "manager": "易方达", "tracking": "上海金AU99.99", "fee_rate": 0.60,
     "listing_date": "2013-12-26"},
    {"etf_code": "518800", "etf_name": "国泰黄金ETF",   "exchange": "SH",
     "manager": "国泰",   "tracking": "上海金AU99.99", "fee_rate": 0.60,
     "listing_date": "2013-07-26"},
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


# ───── ETF master ──────────────────────────────────────────────────────


def upsert_master(con: duckdb.DuckDBPyConnection) -> int:
    df = pd.DataFrame(ETF_MASTER)
    df["listing_date"] = pd.to_datetime(df["listing_date"]).dt.date
    con.register("master_df", df)
    con.execute("""
        INSERT INTO gold_etf_master (etf_code, etf_name, exchange, manager,
                                     tracking, fee_rate, listing_date)
        SELECT etf_code, etf_name, exchange, manager, tracking, fee_rate, listing_date
        FROM master_df
        ON CONFLICT (etf_code) DO UPDATE SET
            etf_name=EXCLUDED.etf_name, exchange=EXCLUDED.exchange,
            manager=EXCLUDED.manager, tracking=EXCLUDED.tracking,
            fee_rate=EXCLUDED.fee_rate, listing_date=EXCLUDED.listing_date
    """)
    # last_update 单独 UPDATE(ON CONFLICT 不能写 CURRENT_TIMESTAMP 字面值)
    con.execute(
        "UPDATE gold_etf_master SET last_update=CURRENT_TIMESTAMP "
        "WHERE etf_code IN (SELECT etf_code FROM master_df)"
    )
    con.unregister("master_df")
    return len(df)


# ───── ETF prices ──────────────────────────────────────────────────────


def fetch_etf_one(etf_code: str, years: int = 3) -> pd.DataFrame:
    """单只 ETF 日 K 历史(qfq 前复权)。"""
    import akshare as ak
    end = date.today()
    start = end - timedelta(days=365 * years)

    df = _retry(lambda: ak.fund_etf_hist_em(
        symbol=etf_code, period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq",
    ))
    if df is None or df.empty:
        raise ValueError(f"empty for {etf_code}")

    rename = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "turnover", "涨跌幅": "pct_change",
        "换手率": "turnover_rate",  # v2.4 step-D · 过热信号 1
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


def upsert_prices(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["etf_code", "date", "open", "close", "high", "low",
            "volume", "turnover", "pct_change", "turnover_rate"]
    df = df[[c for c in cols if c in df.columns]].copy()
    con.register("prices_df", df)
    placeholders = ", ".join(c for c in cols if c in df.columns)
    con.execute(f"""
        INSERT OR REPLACE INTO gold_etf_prices ({placeholders})
        SELECT {placeholders} FROM prices_df
    """)
    con.unregister("prices_df")
    return len(df)


# ───── SPDR 持仓 ───────────────────────────────────────────────────────


def fetch_spdr_akshare() -> pd.DataFrame:
    """走 AkShare 抓 SPDR 持仓 — jin10.com 在中国 IP 经常挂。"""
    import akshare as ak
    df = _retry(lambda: ak.macro_cons_gold(), attempts=2, sleep=2.0)
    # 列名可能是 ['日期', '总库存(吨)', '增持/减持', '总价值(美元)' 等]
    date_col = next((c for c in df.columns if "日期" in c), None)
    holding_col = next((c for c in df.columns if "库存" in c or "总库存" in c), None)
    if not date_col or not holding_col:
        raise RuntimeError(f"未识别 SPDR 列结构:{df.columns.tolist()}")
    out = df[[date_col, holding_col]].rename(columns={date_col: "date", holding_col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "SPDR_HOLDINGS"
    out["unit"] = "tonnes"
    out["frequency"] = "D"
    out["source"] = "akshare:jin10"
    return out


def fetch_spdr_manual_csv() -> pd.DataFrame:
    """从 .config/spdr_holdings_manual.csv 读用户手填的 SPDR 数据。

    CSV 格式:date(YYYY-MM-DD),tonnes(数字)
    """
    if not SPDR_MANUAL_CSV.exists():
        return pd.DataFrame()

    df = pd.read_csv(SPDR_MANUAL_CSV)
    cols_lower = {c.lower(): c for c in df.columns}
    date_col = cols_lower.get("date") or "date"
    holding_col = cols_lower.get("tonnes") or "tonnes"
    if date_col not in df.columns or holding_col not in df.columns:
        print(f"   ⚠️ {SPDR_MANUAL_CSV.name} 列结构错(需要 date,tonnes)")
        return pd.DataFrame()
    out = df[[date_col, holding_col]].rename(columns={date_col: "date", holding_col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "SPDR_HOLDINGS"
    out["unit"] = "tonnes"
    out["frequency"] = "D"
    out["source"] = "manual_csv"
    return out


def fetch_spdr() -> pd.DataFrame:
    """先试 AkShare,挂了走手填 CSV。"""
    try:
        df = fetch_spdr_akshare()
        if not df.empty:
            return df
    except Exception as e:
        print(f"   ⚠️ AkShare SPDR 失败:{type(e).__name__} → 改读手填 CSV")
    return fetch_spdr_manual_csv()


def upsert_spdr_metric(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["indicator", "date", "value", "unit", "frequency", "source"]
    df = df[cols].copy()
    con.register("spdr_df", df)
    con.execute(
        "INSERT OR REPLACE INTO gold_metrics "
        "(indicator, date, value, unit, frequency, source) "
        "SELECT * FROM spdr_df"
    )
    con.unregister("spdr_df")
    return len(df)


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_etf_prices(etf_code: str) -> pd.DataFrame:
    today = date.today()
    return pd.DataFrame({
        "etf_code": etf_code,
        "date": [today - timedelta(days=k) for k in range(5)],
        "open":   [4.20, 4.18, 4.22, 4.25, 4.21],
        "close":  [4.25, 4.20, 4.18, 4.22, 4.25],
        "high":   [4.28, 4.23, 4.24, 4.26, 4.27],
        "low":    [4.18, 4.16, 4.16, 4.20, 4.20],
        "volume": [10000000, 9500000, 11000000, 10500000, 9800000],
        "turnover": [42500000, 39900000, 45980000, 46110000, 41160000],
        "pct_change": [1.19, -1.18, -0.48, 0.96, 1.36],
        "turnover_rate": [1.85, 1.62, 2.10, 1.78, 1.55],  # %
    })


def smoke_spdr() -> pd.DataFrame:
    today = date.today()
    return pd.DataFrame({
        "indicator": "SPDR_HOLDINGS",
        "date": [today - timedelta(days=k) for k in range(5)],
        "value": [870, 868, 872, 869, 871],
        "unit": "tonnes",
        "frequency": "D",
        "source": "smoke",
    })


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--years", type=int, default=3, help="拉几年(默认 3)")
    ap.add_argument("--only", help="单只 ETF code")
    ap.add_argument("--skip-spdr", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    print(f"💰 抓黄金 ETF + SPDR → {db_path}")
    if args.smoke:
        print("   (smoke 模式,不联网)")

    # 1. master
    n_master = upsert_master(con)
    print(f"   ✅ {'gold_etf_master':<22} {n_master:>6} 行(静态)")

    # 2. 4 只 ETF 日 K
    targets = [args.only] if args.only else [m["etf_code"] for m in ETF_MASTER]
    rows_total = 0
    failures: list[tuple[str, str]] = []
    for code in targets:
        try:
            if args.smoke:
                df = smoke_etf_prices(code)
            else:
                df = fetch_etf_one(code, years=args.years)
            n = upsert_prices(con, df)
            print(f"   ✅ {code} ETF{'':<14} {n:>6} 行")
            rows_total += n
            time.sleep(0.5)
        except Exception as e:
            tb = traceback.format_exc().splitlines()[-1]
            failures.append((code, f"{type(e).__name__}: {e} · {tb}"))
            print(f"   ❌ {code} ETF{'':<14} {type(e).__name__}: {e}", file=sys.stderr)

    # 3. SPDR 持仓
    if not args.skip_spdr:
        try:
            df = smoke_spdr() if args.smoke else fetch_spdr()
            if df.empty:
                print("   ⚪ SPDR_HOLDINGS         0 行(AkShare/手填 CSV 都无数据)")
                print(f"      → 手填 CSV:{SPDR_MANUAL_CSV.relative_to(ROOT)}")
            else:
                n = upsert_spdr_metric(con, df)
                print(f"   ✅ {'SPDR_HOLDINGS':<22} {n:>6} 行 (源:{df['source'].iloc[0]})")
                rows_total += n
        except Exception as e:
            failures.append(("SPDR_HOLDINGS", f"{type(e).__name__}: {e}"))
            print(f"   ❌ SPDR_HOLDINGS         {type(e).__name__}: {e}", file=sys.stderr)
    else:
        print("   ⏩ 跳过 SPDR")

    # 总结
    n_master_db = con.execute("SELECT COUNT(*) FROM gold_etf_master").fetchone()[0]
    n_prices_db = con.execute("SELECT COUNT(*) FROM gold_etf_prices").fetchone()[0]
    n_spdr_db = con.execute(
        "SELECT COUNT(*) FROM gold_metrics WHERE indicator='SPDR_HOLDINGS'"
    ).fetchone()[0]
    con.close()

    print(f"\n📊 ETF master {n_master_db} / prices {n_prices_db} / SPDR {n_spdr_db}")
    if failures:
        print(f"\n⚠️  {len(failures)} 项失败:")
        for code, err in failures:
            print(f"   {code}: {err}")
        return 1 if rows_total == 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
