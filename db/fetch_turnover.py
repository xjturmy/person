"""林奇财务护栏 · 周转率派生指标(从 sina BS+IS 派生)。

林奇护栏 5 项中,以下 3 项理杏仁未提供 metric,转用 sina 财报派生:
- inventory_turnover_days     存货周转天数 = days × avg(存货) / 营业成本
- receivables_turnover_days   应收账款周转天数 = days × avg(应收账款) / 营业收入
- total_asset_turnover        总资产周转率 = 营业收入 / avg(资产合计)(年化)

派生口径:
- avg(...) 取期初+期末/2;首期数据用单期值近似(误差最大 5-10%)
- 累积期天数:Q1=90 / Q2=180 / Q3=270 / Q4=365 — 自动按报告日识别
- 银行/保险跳过(无存货 + 营业成本口径不同)
- 应收账款 = "应收票据及应收账款" + "应收款项融资"(若有)

写入**独立 `data/turnover.duckdb`**(与 etf/macro/decisions 同模式,
避免与主 preson.duckdb 写锁冲突;Dashboard 在跑也不影响)。
表结构:turnover_metrics(ticker, date, metric, value)
metric 取值:"存货周转天数" / "应收账款周转天数" / "总资产周转率"

用法:
    .venv/bin/python .tools/db/fetch_turnover.py                  # 全部 13 家非银/保险
    .venv/bin/python .tools/db/fetch_turnover.py --ticker 600519  # 单家
    .venv/bin/python .tools/db/fetch_turnover.py --csv-only       # 不入库
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
# 独立小库:与主 preson.duckdb 写锁解耦
DB_PATH = ROOT / "data" / "turnover.duckdb"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
CSV_DIR = ROOT / ".temp" / "turnover"

SKIP_CATEGORIES = {"bank", "insurance", "hk"}  # 银行/保险/港股不抓

DDL = """
CREATE TABLE IF NOT EXISTS turnover_metrics (
    ticker  VARCHAR NOT NULL,
    date    DATE    NOT NULL,
    metric  VARCHAR NOT NULL,
    value   DOUBLE,
    PRIMARY KEY (ticker, date, metric)
);
CREATE INDEX IF NOT EXISTS idx_turnover_ticker ON turnover_metrics(ticker);
CREATE INDEX IF NOT EXISTS idx_turnover_metric ON turnover_metrics(metric);
"""


def _ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(DDL)
    finally:
        con.close()


def _sina_symbol(ticker: str) -> str:
    if ticker.startswith(("60", "688")):
        return f"sh{ticker}"
    return f"sz{ticker}"


def _to_float(v) -> float | None:
    try:
        if v is None or pd.isna(v):
            return None
        f = float(v)
        return f if f != 0 else None
    except Exception:
        return None


def _accum_days(report_date: pd.Timestamp) -> int:
    """季报累积天数:Q1=90 / Q2=181 / Q3=273 / Q4=365"""
    m = report_date.month
    if m == 3:
        return 90
    if m == 6:
        return 181
    if m == 9:
        return 273
    return 365


def _avg(curr, prev):
    """期初+期末/2;prev 缺失返回 curr 单值。"""
    if curr is None:
        return None
    if prev is None:
        return curr
    return (curr + prev) / 2


def fetch_one_company(ticker: str) -> pd.DataFrame:
    """返回长表 [date, metric, value],已派生周转 3 项。"""
    import akshare as ak

    sym = _sina_symbol(ticker)
    bs = ak.stock_financial_report_sina(stock=sym, symbol="资产负债表")
    is_ = ak.stock_financial_report_sina(stock=sym, symbol="利润表")

    # 报告日类型对齐
    bs["报告日"] = pd.to_datetime(bs["报告日"], format="%Y%m%d", errors="coerce")
    is_["报告日"] = pd.to_datetime(is_["报告日"], format="%Y%m%d", errors="coerce")
    bs = bs.dropna(subset=["报告日"]).sort_values("报告日").set_index("报告日")
    is_ = is_.dropna(subset=["报告日"]).sort_values("报告日").set_index("报告日")

    out: list[dict] = []
    dates = sorted(set(bs.index) & set(is_.index))
    for i, d in enumerate(dates):
        bs_row = bs.loc[d]
        is_row = is_.loc[d]

        # BS:存货 + 应收账款合并(应收票据及应收账款 + 应收款项融资)
        inv_curr = _to_float(bs_row.get("存货"))
        ar_a = _to_float(bs_row.get("应收票据及应收账款"))
        ar_b = _to_float(bs_row.get("应收款项融资"))
        ar_curr = (ar_a or 0) + (ar_b or 0) if (ar_a or ar_b) else None
        ta_curr = _to_float(bs_row.get("资产总计")) or _to_float(bs_row.get("资产合计"))

        # 期初值(取上一期 BS,如有)
        if i > 0:
            d_prev = dates[i - 1]
            bs_prev = bs.loc[d_prev]
            inv_prev = _to_float(bs_prev.get("存货"))
            ar_a_p = _to_float(bs_prev.get("应收票据及应收账款"))
            ar_b_p = _to_float(bs_prev.get("应收款项融资"))
            ar_prev = (ar_a_p or 0) + (ar_b_p or 0) if (ar_a_p or ar_b_p) else None
            ta_prev = _to_float(bs_prev.get("资产总计")) or _to_float(bs_prev.get("资产合计"))
        else:
            inv_prev = ar_prev = ta_prev = None

        # IS:营业收入 + 营业成本
        rev = _to_float(is_row.get("营业收入"))
        cost = _to_float(is_row.get("营业成本"))

        days = _accum_days(d)

        # 1. 存货周转天数 = days × avg_inv / cost
        avg_inv = _avg(inv_curr, inv_prev)
        if avg_inv and cost:
            inv_days = days * avg_inv / cost
            out.append({"date": d.date(), "metric": "存货周转天数", "value": inv_days})

        # 2. 应收账款周转天数 = days × avg_ar / rev
        avg_ar = _avg(ar_curr, ar_prev)
        if avg_ar and rev:
            ar_days = days * avg_ar / rev
            out.append({"date": d.date(), "metric": "应收账款周转天数", "value": ar_days})

        # 3. 总资产周转率(年化) = rev × (365/days) / avg_ta
        avg_ta = _avg(ta_curr, ta_prev)
        if avg_ta and rev:
            tat = rev * (365.0 / days) / avg_ta
            out.append({"date": d.date(), "metric": "总资产周转率", "value": tat})

    return pd.DataFrame(out)


def upsert(ticker: str, df: pd.DataFrame, db_path: Path = DB_PATH) -> int:
    """upsert 到独立 turnover.duckdb / turnover_metrics 表。"""
    if df.empty:
        return 0
    con = duckdb.connect(str(db_path))
    try:
        df = df.assign(ticker=ticker)[["ticker", "date", "metric", "value"]]
        con.register("turnover_df", df)
        con.execute(
            "INSERT OR REPLACE INTO turnover_metrics "
            "SELECT ticker, date, metric, value FROM turnover_df"
        )
        return len(df)
    finally:
        con.close()


def load_companies() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    with open(COMPANIES_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cat = (row.get("category") or "").strip()
            if cat in SKIP_CATEGORIES:
                continue
            out.append((row["stock"].strip(), row["name"].strip(), cat))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="单家 ticker(如 600519)")
    ap.add_argument("--csv-only", action="store_true", help="只导 CSV 不入 DuckDB")
    args = ap.parse_args()

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    if not args.csv_only:
        _ensure_db()
    targets = (
        [(args.ticker, "?", "non_financial")]
        if args.ticker
        else load_companies()
    )
    print(f"准备派生周转指标 · {len(targets)} 家(跳过 {SKIP_CATEGORIES})")

    ok, fail = 0, 0
    total_rows = 0
    for ticker, name, cat in targets:
        try:
            df = fetch_one_company(ticker)
            if df.empty:
                print(f"  ⚠️ {ticker} {name:8s} 无数据")
                fail += 1
                continue
            csv_path = CSV_DIR / f"{ticker}_turnover.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            n = 0 if args.csv_only else upsert(ticker, df)
            print(
                f"  ✅ {ticker} {name:8s} "
                f"{len(df)} 行 / 涉及 {df['metric'].nunique()} 项 / "
                f"{df['date'].min()} → {df['date'].max()}"
                + (f" → {n} 行入库" if not args.csv_only else "")
            )
            ok += 1
            total_rows += len(df)
        except Exception as e:
            print(f"  ❌ {ticker} {name:8s} {type(e).__name__}: {e}")
            fail += 1
        time.sleep(0.5)

    print(f"\n完成:✅ {ok} · ❌ {fail} · 共 {total_rows} 行 · CSV → {CSV_DIR}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
