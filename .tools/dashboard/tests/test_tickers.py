"""tickers.normalize_ticker 单测 — 单一可信源行为锁定。"""

from __future__ import annotations

import pytest

from tickers import normalize_ticker


@pytest.mark.parametrize("raw,expected", [
    # ── A 股:补 0 到 6 位 ─────────────────────────────────────
    ("600519", "600519"),         # 已 6 位
    ("000858", "000858"),         # 已 6 位带前导零
    ("858",    "000858"),         # 旧 CSV 缺前导零
    ("333",    "000333"),         # 美的
    ("1",      "000001"),         # 平安银行极简
    ("63",     "000063"),         # 中兴通讯
    ("300750", "300750"),         # 创业板
    ("688981", "688981"),         # 科创板
    ("000001", "000001"),         # 新 44 家平安
    ("000651", "000651"),         # 新 44 家格力
    # ── 港股:5 位首位 0 保留 ─────────────────────────────────
    ("02097",  "02097"),          # 蜜雪
    # ── 整数输入 ─────────────────────────────────────────────
    (858,      "000858"),
    (600519,   "600519"),
    # ── 防御性 ───────────────────────────────────────────────
    ("",       ""),
    (None,     ""),
    ("  600519  ", "600519"),
])
def test_normalize_ticker_default(raw, expected):
    assert normalize_ticker(raw) == expected


def test_normalize_ticker_explicit_hk():
    # market='hk' 显式时强制 5 位
    assert normalize_ticker("2097", market="hk") == "02097"
    assert normalize_ticker("700", market="hk") == "00700"


def test_normalize_ticker_non_digit_passthrough():
    # 非纯数字串原样返回(防御性,通常不会发生)
    assert normalize_ticker("ABC") == "ABC"
