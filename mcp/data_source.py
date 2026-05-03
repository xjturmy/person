"""
数据源抽象层(DuckDB 后端)。

读取 data/preson.duckdb,函数签名稳定,server.py 通过统一异常获得错误语义。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import yaml

from errors import (
    BadArgument,
    MetricNotFound,
    NoData,
    TickerNotFound,
    freshness,
)

BASE_DIR = Path(__file__).parent.parent.parent
DB_PATH = BASE_DIR / "data" / "preson.duckdb"
MCP_DIR = Path(__file__).parent

CATEGORY_TABLES = {
    "valuation": "valuation",
    "profitability": "profitability",
    "growth": "growth",
    "cashflow": "cashflow",
    "safety": "safety",
}

_metric_map: dict = {}
_ticker_map: dict = {}
_con: Optional[duckdb.DuckDBPyConnection] = None


def _load_config() -> None:
    global _metric_map, _ticker_map
    if not _metric_map:
        with open(MCP_DIR / "metric_map.yaml", encoding="utf-8") as f:
            _metric_map = yaml.safe_load(f)
    if not _ticker_map:
        with open(MCP_DIR / "ticker_map.yaml", encoding="utf-8") as f:
            _ticker_map = yaml.safe_load(f)


def _conn() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        if not DB_PATH.exists():
            raise NoData(
                f"DuckDB 不存在,先跑入库脚本",
                db_path=str(DB_PATH),
                hint=".venv/bin/python .tools/db/ingest.py",
            )
        _con = duckdb.connect(str(DB_PATH), read_only=True)
    return _con


def resolve_ticker(ticker_or_name: str) -> tuple[str, dict]:
    _load_config()
    key = ticker_or_name.strip()
    if key in _ticker_map and key != "name_to_ticker":
        return key, _ticker_map[key]
    name_map = _ticker_map.get("name_to_ticker", {})
    if key in name_map:
        t = name_map[key]
        return t, _ticker_map[t]
    raise TickerNotFound(
        f"找不到公司:{ticker_or_name}",
        available=list(name_map.keys()),
    )


def resolve_metric(metric_alias: str) -> tuple[str, str, str]:
    """返回 (category, file_stem, col_name)。col_name 即 DuckDB metric 列取值。"""
    _load_config()
    alias = metric_alias.strip()

    aliases = _metric_map.get("aliases", {})
    if alias in aliases:
        alias = aliases[alias]

    skip = {"aliases"}
    for cat, metrics in _metric_map.items():
        if cat in skip:
            continue
        if alias in metrics:
            m = metrics[alias]
            return cat, m["file"], m["col"]

    all_metrics = []
    for cat, metrics in _metric_map.items():
        if cat in skip:
            continue
        all_metrics.extend(metrics.keys())
    raise MetricNotFound(
        f"找不到指标:{metric_alias}",
        zh_aliases=list(aliases.keys()),
        en_aliases=all_metrics,
    )


def _period_to_cutoff(period: str) -> Optional[datetime]:
    period = period.strip().lower()
    if period in ("all", "max"):
        return None
    try:
        if period.endswith("y"):
            return datetime.now() - timedelta(days=365 * int(period[:-1]))
        if period.endswith("m"):
            return datetime.now() - timedelta(days=30 * int(period[:-1]))
    except ValueError:
        pass
    raise BadArgument(
        f"无法解析 period:{period}",
        accepted=["1y", "3y", "5y", "10y", "1m", "6m", "all", "max"],
    )


def query_metric(ticker: str, metric: str, period: str = "3y") -> dict:
    """
    查询单一指标时间序列。

    返回:
      {
        "rows": [{"date": "...", "value": ...}, ...],   # 降序
        "meta": {latest_date, lag_days, freshness, ticker, metric, col, period, count}
      }
    """
    t, info = resolve_ticker(ticker)
    cat, _file, col = resolve_metric(metric)
    table = CATEGORY_TABLES[cat]
    cutoff = _period_to_cutoff(period)

    sql = f"SELECT date, value FROM {table} WHERE ticker = ? AND metric = ?"
    params: list = [t, col]
    if cutoff is not None:
        sql += " AND date >= ?"
        params.append(cutoff.date())
    sql += " ORDER BY date DESC"

    df = _conn().execute(sql, params).df()
    if df.empty:
        raise NoData(
            f"无数据:{info['name']} ({t}) / {metric} ({col}) / period={period}",
            ticker=t,
            metric=metric,
            period=period,
        )

    rows = [
        {"date": r["date"].strftime("%Y-%m-%d"), "value": float(r["value"])}
        for _, r in df.iterrows()
    ]
    meta = {
        "ticker": t,
        "name": info["name"],
        "metric": metric,
        "col": col,
        "period": period,
        "count": len(rows),
        **freshness(rows[0]["date"]),
    }
    return {"rows": rows, "meta": meta}


def percentile(ticker: str, metric: str, window: str = "all") -> dict:
    """
    计算某指标当前值在指定窗口内的历史分位。

    返回:
      {
        "current": float,
        "min": float, "max": float, "mean": float, "median": float,
        "percentile": float (0-100),
        "sample_size": int,
        "window": str,
        "meta": {latest_date, lag_days, freshness, ...}
      }
    """
    t, info = resolve_ticker(ticker)
    cat, _file, col = resolve_metric(metric)
    table = CATEGORY_TABLES[cat]
    cutoff = _period_to_cutoff(window)

    sql = f"SELECT date, value FROM {table} WHERE ticker = ? AND metric = ?"
    params: list = [t, col]
    if cutoff is not None:
        sql += " AND date >= ?"
        params.append(cutoff.date())
    sql += " ORDER BY date DESC"

    df = _conn().execute(sql, params).df()
    if df.empty:
        raise NoData(
            f"无数据:{info['name']} ({t}) / {metric} ({col}) / window={window}",
            ticker=t,
            metric=metric,
            window=window,
        )

    cur = float(df.iloc[0]["value"])
    cur_date = df.iloc[0]["date"]
    vals = df["value"].astype(float)
    pct = 100.0 * (vals <= cur).sum() / len(vals)

    return {
        "current": cur,
        "min": float(vals.min()),
        "max": float(vals.max()),
        "mean": float(vals.mean()),
        "median": float(vals.median()),
        "percentile": round(pct, 1),
        "sample_size": len(vals),
        "window": window,
        "meta": {
            "ticker": t,
            "name": info["name"],
            "metric": metric,
            "col": col,
            **freshness(cur_date),
        },
    }


def latest_snapshot(ticker: str) -> dict:
    """返回最新一期的五维快照。每个指标取自身最新可得日期。"""
    _load_config()
    t, info = resolve_ticker(ticker)

    snapshot: dict = {
        "company": info["name"],
        "ticker": t,
        "valuation": {},
        "profitability": {},
        "growth": {},
        "cashflow": {},
        "safety": {},
        "meta": {},
    }
    val_latest: Optional[datetime] = None
    overall_latest: Optional[datetime] = None
    found_any = False
    con = _conn()

    for cat_key, table in CATEGORY_TABLES.items():
        cat_metrics = _metric_map.get(cat_key, {})
        wanted_cols = {spec["col"]: alias for alias, spec in cat_metrics.items()}
        if not wanted_cols:
            continue

        sql = f"""
        WITH ranked AS (
          SELECT metric, value, date,
                 ROW_NUMBER() OVER (PARTITION BY metric ORDER BY date DESC) AS rn
          FROM {table}
          WHERE ticker = ? AND metric IN ({','.join(['?'] * len(wanted_cols))})
        )
        SELECT metric, value, date FROM ranked WHERE rn = 1
        """
        params = [t, *wanted_cols.keys()]
        df = con.execute(sql, params).df()

        result: dict = {}
        cat_latest: Optional[datetime] = None
        for _, r in df.iterrows():
            alias = wanted_cols.get(r["metric"])
            if alias is None:
                continue
            try:
                result[alias] = float(r["value"])
            except (TypeError, ValueError):
                result[alias] = r["value"]
            if cat_latest is None or r["date"] > cat_latest:
                cat_latest = r["date"]

        snapshot[cat_key] = result
        if result:
            found_any = True
        if cat_key == "valuation":
            val_latest = cat_latest
        if cat_latest and (overall_latest is None or cat_latest > overall_latest):
            overall_latest = cat_latest

    if not found_any:
        raise NoData(f"无数据:{info['name']} ({t})", ticker=t)

    snapshot["meta"] = {
        "ticker": t,
        "name": info["name"],
        "valuation_latest": freshness(val_latest)["latest_date"],
        **freshness(overall_latest),
    }
    return snapshot


def compare_peers(tickers: list[str], metric: str, period: str = "1y") -> dict:
    """横向对比多家公司同一指标。"""
    _cat, _file, col = resolve_metric(metric)
    out: dict = {
        "metric": metric,
        "col": col,
        "period": period,
        "companies": {},
    }
    latest_overall: Optional[str] = None

    for raw in tickers:
        try:
            t, info = resolve_ticker(raw)
            res = query_metric(raw, metric, period)
            out["companies"][f"{info['name']} ({t})"] = {
                "rows": res["rows"],
                "meta": res["meta"],
            }
            ld = res["meta"]["latest_date"]
            if ld and (latest_overall is None or ld > latest_overall):
                latest_overall = ld
        except (TickerNotFound, MetricNotFound, NoData, BadArgument) as e:
            out["companies"][raw] = {"error": e.code, "message": e.message}

    out["meta"] = freshness(latest_overall)
    return out
