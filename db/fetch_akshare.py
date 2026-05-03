"""AkShare 增量抓取 - 写入 .tools/db/cache/。

- prices/{ticker}.csv: A 股日行情(后复权),港股 best-effort
- industry_pe.csv: 中证行业 PE 日频快照

增量策略:
- 已有 cache 文件:从 max(date)+1 抓到今天
- 无 cache:抓最近 N 年(--years,默认 10)

用法:
    .venv/bin/python .tools/db/fetch_akshare.py             # 增量抓全部
    .venv/bin/python .tools/db/fetch_akshare.py --years 1   # 重抓近 1 年
    .venv/bin/python .tools/db/fetch_akshare.py --skip-prices --skip-industry
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
CACHE_DIR = ROOT / ".tools" / "db" / "cache"
PRICES_DIR = CACHE_DIR / "prices"


def _load_companies() -> pd.DataFrame:
    df = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
    return df.rename(columns={"stock": "ticker"})


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _existing_max_date(csv_path: Path) -> date | None:
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, usecols=["date"])
        if df.empty:
            return None
        return pd.to_datetime(df["date"]).dt.date.max()
    except Exception:
        return None


PRICE_OUT_COLS = ["ticker", "date", "open", "close", "high", "low",
                  "volume", "turnover", "pct_change", "turnover_rate"]


def _sina_symbol(ticker: str) -> str:
    """A 股 ticker 转 新浪 symbol (sh/sz 前缀)。"""
    if ticker.startswith("6"):
        return f"sh{ticker}"
    return f"sz{ticker}"


def fetch_one_price(ticker: str, category: str, start: date, end: date,
                    retries: int = 2) -> pd.DataFrame:
    """抓一只股票的日 K(后复权)。

    数据源策略:
    - A 股:新浪 stock_zh_a_daily(列: date/open/high/low/close/volume/amount/turnover)
            -> 映射 amount->turnover, turnover->turnover_rate, pct_change 留空
    - 港股:暂不支持(akshare 港股接口走 eastmoney 当前不稳定)
    """
    if category == "hk":
        raise RuntimeError("hk price source unavailable (eastmoney unstable)")

    last_err = None
    for attempt in range(retries + 1):
        try:
            raw = ak.stock_zh_a_daily(
                symbol=_sina_symbol(ticker),
                start_date=_ymd(start), end_date=_ymd(end),
                adjust="hfq",
            )
            if raw is None or raw.empty:
                return pd.DataFrame()
            df = raw.copy()
            df = df.rename(columns={"amount": "turnover", "turnover": "turnover_rate"})
            df["pct_change"] = (df["close"].pct_change() * 100).round(4)
            df["ticker"] = ticker
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
            for c in ("open", "close", "high", "low", "turnover", "turnover_rate", "pct_change"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            return df[PRICE_OUT_COLS]
        except Exception as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"akshare fetch failed for {ticker}: {last_err}")


def merge_and_write(csv_path: Path, new_df: pd.DataFrame) -> int:
    """合并新数据到 cache(去重,按 date 升序)。返回新增行数。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if new_df.empty:
        return 0
    if csv_path.exists():
        old = pd.read_csv(csv_path, dtype={"ticker": str})
        old["date"] = pd.to_datetime(old["date"]).dt.date
        before = len(old)
        merged = pd.concat([old, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["ticker", "date"], keep="last")
        merged = merged.sort_values(["ticker", "date"]).reset_index(drop=True)
        merged.to_csv(csv_path, index=False)
        return len(merged) - before
    new_df = new_df.sort_values(["ticker", "date"]).reset_index(drop=True)
    new_df.to_csv(csv_path, index=False)
    return len(new_df)


def fetch_prices(years: int) -> dict:
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    default_start = today - timedelta(days=365 * years)
    companies = _load_companies()

    summary = {"ok": 0, "skipped": [], "added": 0}
    for _, row in companies.iterrows():
        ticker = row["ticker"]
        category = row.get("category") or "non_financial"
        csv_path = PRICES_DIR / f"{ticker}.csv"
        max_d = _existing_max_date(csv_path)
        start = max_d + timedelta(days=1) if max_d else default_start
        if start > today:
            summary["ok"] += 1
            continue
        try:
            df = fetch_one_price(ticker, category, start, today)
            added = merge_and_write(csv_path, df)
            summary["added"] += added
            summary["ok"] += 1
            print(f"  [prices] {ticker} ({row['name']:<8}) {start}~{today}: +{added} rows")
        except Exception as exc:
            summary["skipped"].append((ticker, str(exc)))
            print(f"  [prices] {ticker} ({row['name']:<8}) SKIP: {exc}")
        time.sleep(0.4)
    return summary


INDUSTRY_COL_MAP = {
    "变动日期": "date",
    "行业层级": "level",
    "行业编码": "industry_code",
    "行业名称": "industry_name",
    "公司数量": "n_companies",
    "静态市盈率-加权平均": "pe_weighted",
    "静态市盈率-中位数": "pe_median",
    "静态市盈率-算术平均": "pe_arith",
}


def fetch_industry_pe(days_back: int) -> int:
    """抓最近 N 个交易日的行业 PE 快照(中证标准)。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = CACHE_DIR / "industry_pe.csv"
    today = date.today()
    max_d = _existing_max_date(csv_path)
    start = max_d + timedelta(days=1) if max_d else today - timedelta(days=days_back)

    pulled: list[pd.DataFrame] = []
    cursor = today
    fetched_dates = 0
    # 节假日 / 周末 akshare 抛 "Length mismatch" — 当作无数据继续往前
    while cursor >= start and fetched_dates < days_back:
        # 跳过周末
        if cursor.weekday() >= 5:
            cursor -= timedelta(days=1)
            continue
        try:
            raw = ak.stock_industry_pe_ratio_cninfo(symbol="证监会行业分类",
                                                    date=_ymd(cursor))
            if raw is not None and not raw.empty:
                df = raw.rename(columns=INDUSTRY_COL_MAP)
                keep = [c for c in INDUSTRY_COL_MAP.values() if c in df.columns]
                df = df[keep].copy()
                df["date"] = pd.to_datetime(df["date"]).dt.date
                df["level"] = pd.to_numeric(df["level"], errors="coerce").astype("Int64")
                df["n_companies"] = pd.to_numeric(df["n_companies"], errors="coerce").astype("Int64")
                pulled.append(df)
                fetched_dates += 1
                print(f"  [industry_pe] {cursor}: {len(df)} rows")
        except ValueError as exc:
            if "Length mismatch" in str(exc):
                print(f"  [industry_pe] {cursor}: holiday/no-data, skip")
            else:
                print(f"  [industry_pe] {cursor}: skip ({type(exc).__name__})")
        except Exception as exc:
            print(f"  [industry_pe] {cursor}: skip ({type(exc).__name__})")
        cursor -= timedelta(days=1)
        time.sleep(0.3)

    if not pulled:
        return 0
    new_df = pd.concat(pulled, ignore_index=True)
    if csv_path.exists():
        old = pd.read_csv(csv_path)
        old["date"] = pd.to_datetime(old["date"]).dt.date
        old["level"] = pd.to_numeric(old["level"], errors="coerce").astype("Int64")
        old["n_companies"] = pd.to_numeric(old["n_companies"], errors="coerce").astype("Int64")
        before = len(old)
        merged = pd.concat([old, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date", "industry_code"], keep="last")
        merged.to_csv(csv_path, index=False)
        return len(merged) - before
    new_df.to_csv(csv_path, index=False)
    return len(new_df)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=10,
                        help="无 cache 时回抓多少年(默认 10)")
    parser.add_argument("--industry-days", type=int, default=10,
                        help="行业 PE 回抓多少天(默认 10)")
    parser.add_argument("--skip-prices", action="store_true")
    parser.add_argument("--skip-industry", action="store_true")
    args = parser.parse_args()

    if not args.skip_prices:
        print("== fetch prices ==")
        s = fetch_prices(args.years)
        print(f"\n  prices summary: ok={s['ok']}/{s['ok']+len(s['skipped'])} added={s['added']}")
        if s["skipped"]:
            print(f"  skipped: {[t for t,_ in s['skipped']]}")

    if not args.skip_industry:
        print("\n== fetch industry_pe ==")
        n = fetch_industry_pe(args.industry_days)
        print(f"\n  industry_pe added: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
