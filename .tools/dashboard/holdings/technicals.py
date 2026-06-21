"""短期技术指标 — A 股日 K + MA/RSI/MACD/换手率。

数据源:akshare.stock_zh_a_daily(adjust='qfq' 前复权 — 技术指标用前复权更合理)
缓存:5 分钟 TTL(配合 Streamlit @cache_data,本模块只暴露纯函数)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd


def _sina_symbol(ticker: str) -> Optional[str]:
    """A 股 ticker → 新浪 symbol (sh/sz);非 6 位数字代码返回 None。"""
    t = (ticker or "").strip()
    if len(t) != 6 or not t.isdigit():
        return None
    return f"sh{t}" if t.startswith("6") else f"sz{t}"


def is_a_share(ticker: str) -> bool:
    return _sina_symbol(ticker) is not None


def fetch_recent_klines(ticker: str, days: int = 180) -> pd.DataFrame:
    """抓近 days 天日 K(前复权),返回 columns: date / open / close / high / low / volume / turnover / turnover_rate。

    非 A 股或抓取失败返回空 DataFrame。
    """
    sym = _sina_symbol(ticker)
    if sym is None:
        return pd.DataFrame()

    try:
        import akshare as ak
    except Exception:
        return pd.DataFrame()

    end = date.today()
    start = end - timedelta(days=days + 30)  # 多抓 30 天垫底,防节假日
    try:
        raw = ak.stock_zh_a_daily(
            symbol=sym,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
    except Exception:
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.rename(columns={"amount": "turnover", "turnover": "turnover_rate"})
    for c in ("open", "close", "high", "low", "turnover", "turnover_rate"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce").fillna(0).astype("int64")
    df = df.sort_values("date").reset_index(drop=True)
    return df.tail(days).reset_index(drop=True)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """喂日 K 算 MA5/MA20/MA60、RSI14(Wilder)、MACD(12/26/9)。

    输入需有 close 列,date 升序。返回新增多列的 df。
    """
    if df is None or df.empty or "close" not in df.columns:
        return df

    out = df.copy()
    close = out["close"].astype(float)

    out["MA5"] = close.rolling(5, min_periods=1).mean()
    out["MA20"] = close.rolling(20, min_periods=1).mean()
    out["MA60"] = close.rolling(60, min_periods=1).mean()

    # RSI14 Wilder 平滑
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    # avg_loss=0 时 RSI=100;avg_gain=0 时 RSI=0
    rs = avg_gain / avg_loss.where(avg_loss > 0, 1e-12)
    out["RSI14"] = 100 - (100 / (1 + rs))

    # MACD(12/26/9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["MACD_DIF"] = ema12 - ema26
    out["MACD_DEA"] = out["MACD_DIF"].ewm(span=9, adjust=False).mean()
    out["MACD_HIST"] = (out["MACD_DIF"] - out["MACD_DEA"]) * 2

    return out


@dataclass
class TechSignals:
    rsi14: Optional[float]
    macd_state: str          # "金叉" / "死叉" / "无"
    ma_arrangement: str      # "多头" / "空头" / "纠缠"
    turnover_rate_20: Optional[float]   # 20 日均换手率(%)


def summarize_signals(df: pd.DataFrame) -> TechSignals:
    if df is None or df.empty or "close" not in df.columns:
        return TechSignals(None, "无", "纠缠", None)
    if "MA5" not in df.columns:
        df = compute_indicators(df)

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    rsi = float(last["RSI14"]) if pd.notna(last.get("RSI14")) else None

    # MACD 金叉/死叉
    macd_state = "无"
    if pd.notna(last.get("MACD_DIF")) and pd.notna(prev.get("MACD_DIF")):
        dif_now, dea_now = last["MACD_DIF"], last["MACD_DEA"]
        dif_prev, dea_prev = prev["MACD_DIF"], prev["MACD_DEA"]
        if dif_prev <= dea_prev and dif_now > dea_now:
            macd_state = "金叉"
        elif dif_prev >= dea_prev and dif_now < dea_now:
            macd_state = "死叉"

    # MA 排列
    ma5, ma20, ma60 = last.get("MA5"), last.get("MA20"), last.get("MA60")
    ma_arr = "纠缠"
    if all(pd.notna(x) for x in (ma5, ma20, ma60)):
        if ma5 > ma20 > ma60:
            ma_arr = "多头"
        elif ma5 < ma20 < ma60:
            ma_arr = "空头"

    tr20 = None
    if "turnover_rate" in df.columns:
        tail = df["turnover_rate"].tail(20)
        if not tail.empty:
            tr20 = float(tail.mean())

    return TechSignals(rsi14=rsi, macd_state=macd_state,
                       ma_arrangement=ma_arr, turnover_rate_20=tr20)


__all__ = [
    "is_a_share",
    "fetch_recent_klines",
    "compute_indicators",
    "summarize_signals",
    "TechSignals",
]
