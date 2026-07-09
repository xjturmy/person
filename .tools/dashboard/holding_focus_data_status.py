#!/usr/bin/env python3
"""检查“我的持仓视角”的数据缺口，并输出统一补数命令。

原则:
- 股票 / 港股 / 保险公司:走现有理杏仁公司数据管线。
- 普通 ETF:优先走理杏仁 ETF 管线,写入 data/etf.duckdb;行情源脚本兜底。
- 黄金 / 金股 / 有色金矿 ETF:走 data/gold.duckdb 的黄金专项管线。

本脚本默认只检查，不联网、不写库。加 --commands 输出可复制命令。
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
sys.path.insert(0, str(DASHBOARD_DIR))

from tabs.decision.holding_focus import FOCUS_HOLDINGS  # noqa: E402

PRESON_DB = ROOT / "data" / "preson.duckdb"
ETF_DB = ROOT / "data" / "etf.duckdb"
GOLD_DB = ROOT / "data" / "gold.duckdb"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
PEERS_ETF_CSV = ROOT / ".config" / "peers_etf.csv"

GOLD_ETF_CODES = {"518880"}
GOLD_STOCK_ETF_CODES = {"159562", "517400"}
FRESHNESS_DAYS = 14


@dataclass
class DataStatus:
    name: str
    ticker: str
    kind: str
    pipeline: str
    in_company_config: bool
    in_etf_config: bool
    latest_price: str
    latest_valuation: str
    missing: list[str]


def _read_companies() -> dict[str, dict[str, str]]:
    if not COMPANIES_CSV.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with COMPANIES_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stock = str(row.get("stock") or "").strip()
            if not stock:
                continue
            keys = {stock, stock.zfill(5), stock.zfill(6)}
            for key in keys:
                out[key] = row
    return out


def _read_etf_codes() -> set[str]:
    if not PEERS_ETF_CSV.exists():
        return set()
    with PEERS_ETF_CSV.open(encoding="utf-8-sig", newline="") as f:
        return {
            str(row.get("etf_code") or "").strip()
            for row in csv.DictReader(f)
            if str(row.get("etf_code") or "").strip()
        }


def _latest_from_table(
    db_path: Path,
    table: str,
    code_col: str,
    ticker: str,
    value_col: str = "close",
) -> str:
    if not db_path.exists():
        return ""
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            row = con.execute(
                f"""
                SELECT date, {value_col}
                FROM {table}
                WHERE {code_col} = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                [ticker],
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return ""
    if not row:
        return ""
    dt, value = row
    return f"{dt} / {value}"


def _latest_stock_valuation(ticker: str) -> str:
    if not PRESON_DB.exists():
        return ""
    try:
        con = duckdb.connect(str(PRESON_DB), read_only=True)
        try:
            row = con.execute(
                """
                SELECT date, value
                FROM valuation
                WHERE ticker = ? AND metric = 'PE-TTM'
                ORDER BY date DESC
                LIMIT 1
                """,
                [ticker],
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return ""
    if not row:
        return ""
    dt, value = row
    return f"{dt} / PE {value}"


def _is_stale(latest: str, days: int = FRESHNESS_DAYS) -> bool:
    if not latest or latest == "缺失" or " / " not in latest:
        return False
    raw_date = latest.split(" / ", 1)[0].strip()
    try:
        dt = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return False
    return dt < date.today() - timedelta(days=days)


def _pipeline_for(kind: str, ticker: str) -> str:
    if kind == "股票":
        return "lixinger_company"
    if ticker in GOLD_ETF_CODES:
        return "gold_etf"
    if ticker in GOLD_STOCK_ETF_CODES:
        return "gold_stock_etf"
    return "etf"


def collect_status() -> list[DataStatus]:
    companies = _read_companies()
    etf_codes = _read_etf_codes()
    out: list[DataStatus] = []

    for item in FOCUS_HOLDINGS:
        pipeline = _pipeline_for(item.kind, item.ticker)
        missing: list[str] = []
        in_company_config = item.ticker in companies
        in_etf_config = item.ticker in etf_codes

        if pipeline == "lixinger_company":
            latest_price = _latest_from_table(PRESON_DB, "prices", "ticker", item.ticker)
            latest_val = _latest_stock_valuation(item.ticker)
            if not in_company_config:
                missing.append("companies.csv")
            if not latest_price:
                missing.append("股票行情")
            elif _is_stale(latest_price):
                missing.append("股票行情过旧")
            if not latest_val:
                missing.append("PE-TTM估值")
        elif pipeline == "gold_etf":
            latest_price = _latest_from_table(GOLD_DB, "gold_etf_prices", "etf_code", item.ticker)
            latest_val = "ETF不适用"
            if not latest_price:
                missing.append("黄金ETF行情")
            elif _is_stale(latest_price):
                missing.append("黄金ETF行情过旧")
        elif pipeline == "gold_stock_etf":
            latest_price = _latest_from_table(GOLD_DB, "gold_stock_etf_prices", "etf_code", item.ticker)
            latest_val = "ETF不适用"
            if not latest_price:
                missing.append("金股/有色ETF行情")
            elif _is_stale(latest_price):
                missing.append("金股/有色ETF行情过旧")
        else:
            latest_price = _latest_from_table(ETF_DB, "etf_prices", "etf_code", item.ticker)
            latest_val = "ETF不适用"
            if not in_etf_config:
                missing.append("peers_etf.csv")
            if not latest_price:
                missing.append("ETF行情")
            elif _is_stale(latest_price):
                missing.append("ETF行情过旧")

        out.append(
            DataStatus(
                name=item.name,
                ticker=item.ticker,
                kind=item.kind,
                pipeline=pipeline,
                in_company_config=in_company_config,
                in_etf_config=in_etf_config,
                latest_price=latest_price or "缺失",
                latest_valuation=latest_val or "缺失",
                missing=missing,
            )
        )
    return out


def print_table(rows: list[DataStatus]) -> None:
    print("标的,代码,类型,补数管线,最新价,估值,缺口")
    for row in rows:
        gap = " / ".join(row.missing) if row.missing else "OK"
        print(
            f"{row.name},{row.ticker},{row.kind},{row.pipeline},"
            f"{row.latest_price},{row.latest_valuation},{gap}"
        )


def print_commands(rows: list[DataStatus]) -> None:
    stock_missing = [r for r in rows if r.pipeline == "lixinger_company" and r.missing]
    etf_missing = [
        r for r in rows
        if r.pipeline == "etf" and ("ETF行情" in r.missing or "ETF行情过旧" in r.missing)
    ]
    gold_missing = [r for r in rows if r.pipeline == "gold_etf" and r.missing]
    gold_stock_missing = [r for r in rows if r.pipeline == "gold_stock_etf" and r.missing]

    print("\n# 1. 股票/港股/保险:理杏仁公司数据管线")
    if stock_missing:
        print(
            ".venv/bin/python .tools/lixinger-archiver/run_full_pipeline.py "
            "--companies-csv .config/companies.csv --base-dir 02_companies "
            "--days 365 --years 10 --clean-existing"
        )
        print(".venv/bin/python .tools/data_consolidator/consolidate.py")
        print(".venv/bin/python .tools/analytics/precompute.py")
    else:
        print("# 当前持仓股票侧暂无理杏仁数据缺口")

    print("\n# 2. 普通 ETF:理杏仁 ETF 管线优先,行情源兜底")
    if etf_missing:
        for row in etf_missing:
            print(f".venv/bin/python .tools/lixinger-archiver/fetch_lixinger_etf.py --only {row.ticker} --years 5")
            print(f"# 若理杏仁 ETF 端点不可用,再兜底:")
            print(f".venv/bin/python .tools/db/fetch_etf.py --only {row.ticker} --years 5")
    else:
        print("# 普通 ETF 行情暂无缺口")

    print("\n# 3. 黄金 ETF")
    if gold_missing:
        for row in gold_missing:
            print(f".venv/bin/python .tools/db/fetch_gold_etf.py --only {row.ticker} --years 5 --skip-spdr")
    else:
        print("# 黄金 ETF 行情暂无缺口")

    print("\n# 4. 金股 / 有色金矿 ETF")
    if gold_stock_missing:
        for row in gold_stock_missing:
            print(f".venv/bin/python .tools/db/fetch_gold_stock_etf.py --only {row.ticker} --years 5")
    else:
        print("# 金股 / 有色金矿 ETF 行情暂无缺口")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commands", action="store_true", help="同时输出补数命令")
    args = parser.parse_args()

    rows = collect_status()
    print_table(rows)
    if args.commands:
        print_commands(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
