"""融资融券 — 单 ticker 近 N 个交易日时序。

数据源:akshare.stock_margin_detail_sse(沪)/ stock_margin_detail_szse(深)
按 6 开头路由到沪市,否则深市。港股 / 非 A 股返回空。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd


def _route(ticker: str) -> Optional[str]:
    """返回 'sse' / 'szse',非 A 股返回 None。"""
    t = (ticker or "").strip()
    if len(t) != 6 or not t.isdigit():
        return None
    return "sse" if t.startswith("6") else "szse"


@dataclass
class MarginSummary:
    series: pd.DataFrame                  # date / 融资余额 / 融券余额 / 融资买入额 / 融资偿还额
    latest_rzye: Optional[float]          # 最新融资余额(元)
    pct_change_20d: Optional[float]       # 20 个交易日变化%
    net_buy_5d: Optional[float]           # 近 5 日融资净买入(买入 - 偿还)
    latest_date: Optional[date]


def _fetch_sse(ticker: str, days_back: int) -> pd.DataFrame:
    """沪市:逐日抓 stock_margin_detail_sse(akshare 该接口按 date 入参)。"""
    import akshare as ak
    end = date.today()
    rows = []
    # 沪深两融数据 T+1 发布,扫近 days_back 个自然日,过滤到目标 ticker
    for i in range(1, days_back + 1):
        d = end - timedelta(days=i)
        try:
            df = ak.stock_margin_detail_sse(date=d.strftime("%Y%m%d"))
        except Exception:
            continue
        if df is None or df.empty:
            continue
        if "标的证券代码" in df.columns:
            sub = df[df["标的证券代码"].astype(str).str.zfill(6) == ticker]
            if not sub.empty:
                row = sub.iloc[0].to_dict()
                row["date"] = d
                rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out


def _fetch_szse(ticker: str, days_back: int) -> pd.DataFrame:
    """深市:逐日抓 stock_margin_detail_szse。"""
    import akshare as ak
    end = date.today()
    rows = []
    for i in range(1, days_back + 1):
        d = end - timedelta(days=i)
        try:
            df = ak.stock_margin_detail_szse(date=d.strftime("%Y%m%d"))
        except Exception:
            continue
        if df is None or df.empty:
            continue
        if "证券代码" in df.columns:
            sub = df[df["证券代码"].astype(str).str.zfill(6) == ticker]
            if not sub.empty:
                row = sub.iloc[0].to_dict()
                row["date"] = d
                rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


# 列名归一化映射(沪深字段不同)
_COL_RENAME = {
    # 沪
    "融资余额(元)": "融资余额",
    "融资买入额(元)": "融资买入额",
    "融资偿还额(元)": "融资偿还额",
    "融券余量金额(元)": "融券余额",
    # 深
    "融资余额": "融资余额",
    "融资买入额": "融资买入额",
    "融资偿还额": "融资偿还额",
    "融券余额": "融券余额",
}


def fetch_margin_series(ticker: str, days_back: int = 30) -> MarginSummary:
    """抓近 days_back 个自然日的两融数据。

    走逐日扫描接口慢(每天 1 次 HTTP),days_back 默认 30 已够 20 个交易日。
    非 A 股 / 抓不到数据返回空 series。
    """
    route = _route(ticker)
    if route is None:
        return MarginSummary(pd.DataFrame(), None, None, None, None)

    raw = _fetch_sse(ticker, days_back) if route == "sse" else _fetch_szse(ticker, days_back)
    if raw.empty:
        return MarginSummary(pd.DataFrame(), None, None, None, None)

    # 归一化列名
    df = raw.rename(columns=_COL_RENAME).copy()
    keep = ["date", "融资余额", "融券余额", "融资买入额", "融资偿还额"]
    for c in keep[1:]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.NA
    df = df[keep].sort_values("date").reset_index(drop=True)

    latest = df.iloc[-1]
    latest_rzye = float(latest["融资余额"]) if pd.notna(latest["融资余额"]) else None
    latest_date = latest["date"]

    pct_20 = None
    if latest_rzye is not None and len(df) >= 20:
        prev = df.iloc[-20]["融资余额"]
        if pd.notna(prev) and prev:
            pct_20 = (latest_rzye - float(prev)) / float(prev)

    net5 = None
    tail5 = df.tail(5)
    if not tail5.empty:
        buy = tail5["融资买入额"].sum(skipna=True)
        repay = tail5["融资偿还额"].sum(skipna=True)
        if pd.notna(buy) and pd.notna(repay):
            net5 = float(buy - repay)

    return MarginSummary(
        series=df,
        latest_rzye=latest_rzye,
        pct_change_20d=pct_20,
        net_buy_5d=net5,
        latest_date=latest_date,
    )


__all__ = ["MarginSummary", "fetch_margin_series"]
