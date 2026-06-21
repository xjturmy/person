"""行业下钻 + watchlist 写入单测."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest


def test_build_industry_leaders_intro_no_scores():
    from tabs.industry._drilldown import build_industry_leaders_intro, load_name_to_meta

    meta = load_name_to_meta().get("消费电子")
    if not meta:
        pytest.skip("no 消费电子 in industry_master")
    df = build_industry_leaders_intro("消费电子", meta, top_n=5)
    assert not df.empty
    assert list(df.columns) == ["序号", "代码", "名称", "备注"]
    assert "score" not in df.columns
    assert "rating" not in df.columns


def test_build_industry_rank_df_smoke():
    from tabs.industry._drilldown import build_industry_rank_df, load_name_to_meta

    meta = load_name_to_meta()
    if not meta:
        pytest.skip("no industry_master")
    df = build_industry_rank_df(meta)
    assert not df.empty
    assert "行业" in df.columns
    assert "PE 分位(10y)" in df.columns


def test_add_leader_to_watchlist_new_entry(monkeypatch):
    from tabs.industry import _drilldown as dd

    calls: list = []

    def fake_add(df, preset):
        calls.append((df.copy(), preset))
        return 1

    monkeypatch.setattr(dd, "_watchlist_ticker_set", lambda: set())
    monkeypatch.setattr("watchlist.add", fake_add)

    row = {
        "ticker": "600519",
        "name": "贵州茅台",
        "score": 88.0,
        "rating": "A",
    }
    n = dd.add_leader_to_watchlist("白酒", row)
    assert n == 1
    assert len(calls) == 1
    df, preset = calls[0]
    assert preset == "行业预选·白酒"
    assert df.iloc[0]["ticker"] == "600519"
    assert df.iloc[0]["source_industry"] == "白酒"


def test_add_leader_to_watchlist_dedup(monkeypatch):
    from tabs.industry import _drilldown as dd

    monkeypatch.setattr(dd, "_watchlist_ticker_set", lambda: {"600519"})
    monkeypatch.setattr("watchlist.add", MagicMock(return_value=1))

    row = {"ticker": "600519", "name": "贵州茅台", "score": 88.0, "rating": "A"}
    assert dd.add_leader_to_watchlist("白酒", row) == 0


def test_add_leader_to_watchlist_empty_ticker(monkeypatch):
    from tabs.industry import _drilldown as dd

    monkeypatch.setattr(dd, "_watchlist_ticker_set", lambda: set())
    assert dd.add_leader_to_watchlist("白酒", {"ticker": "", "name": "x"}) == 0


def test_add_etf_to_watchlist(monkeypatch):
    from tabs.industry import _drilldown as dd
    from screening.etf_recommender import ETFCandidate

    calls: list = []

    def fake_add(df, preset):
        calls.append((df.copy(), preset))
        return 1

    monkeypatch.setattr(dd, "_watchlist_ticker_set", lambda: set())
    monkeypatch.setattr("watchlist.add", fake_add)

    etf = ETFCandidate(
        code="512480", name="半导体ETF", theme="半导体",
        liquidity_score=85.0, rationale="流动性好",
    )
    n = dd.add_etf_to_watchlist("消费电子", etf)
    assert n == 1
    df, preset = calls[0]
    assert preset == "行业预选·消费电子·ETF"
    assert df.iloc[0]["ticker"] == "512480"
    assert df.iloc[0]["source_industry"] == "消费电子"


def test_add_leader_accepts_series(monkeypatch):
    from tabs.industry import _drilldown as dd

    monkeypatch.setattr(dd, "_watchlist_ticker_set", lambda: set())
    monkeypatch.setattr("watchlist.add", lambda df, preset: 1)

    row = pd.Series({"ticker": "000333", "name": "美的集团", "score": 75.0, "rating": "B"})
    assert dd.add_leader_to_watchlist("白色家电", row) == 1

    from tabs.industry import _drilldown as dd

    monkeypatch.setattr(dd, "_watchlist_ticker_set", lambda: set())
    monkeypatch.setattr("watchlist.add", lambda df, preset: 1)

    row = pd.Series({"ticker": "000333", "name": "美的集团", "score": 75.0, "rating": "B"})
    assert dd.add_leader_to_watchlist("白色家电", row) == 1
