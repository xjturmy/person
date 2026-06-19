"""technicals.compute_indicators / summarize_signals 离线单测(不联网)。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from holdings.technicals import (  # noqa: E402
    compute_indicators,
    summarize_signals,
    is_a_share,
)


def _make_df(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D").date,
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [10000] * n,
        "turnover": [c * 10000 for c in closes],
        "turnover_rate": [1.5] * n,
    })


def test_is_a_share():
    assert is_a_share("600000") is True
    assert is_a_share("000001") is True
    assert is_a_share("300750") is True
    assert is_a_share("00700") is False     # 港股
    assert is_a_share("") is False
    assert is_a_share("abcdef") is False


def test_ma_basic():
    df = _make_df([10, 11, 12, 13, 14, 15, 16, 17, 18, 19] * 8)
    out = compute_indicators(df)
    # MA5 在第 5 行起为完整窗口
    assert out["MA5"].iloc[4] == pytest.approx(12.0, abs=1e-9)
    assert "MA20" in out.columns and "MA60" in out.columns


def test_rsi_extremes():
    # 全部上涨 → RSI 接近 100
    df_up = _make_df([100 + i for i in range(50)])
    out = compute_indicators(df_up)
    assert out["RSI14"].iloc[-1] > 95
    # 全部下跌 → RSI 接近 0
    df_down = _make_df([100 - i * 0.5 for i in range(50)])
    out2 = compute_indicators(df_down)
    assert out2["RSI14"].iloc[-1] < 10


def test_macd_columns_present():
    df = _make_df([100 + (i % 5) for i in range(60)])
    out = compute_indicators(df)
    for c in ("MACD_DIF", "MACD_DEA", "MACD_HIST"):
        assert c in out.columns


def test_summarize_signals_bullish():
    # 持续上涨 → MA 多头 + RSI 偏高
    df = _make_df([100 + i * 0.5 for i in range(80)])
    df = compute_indicators(df)
    sig = summarize_signals(df)
    assert sig.ma_arrangement == "多头"
    assert sig.rsi14 is not None and sig.rsi14 > 70


def test_summarize_signals_empty():
    sig = summarize_signals(pd.DataFrame())
    assert sig.rsi14 is None
    assert sig.macd_state == "无"
