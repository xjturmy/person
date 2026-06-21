"""funnel.layers 单测 — focus → ticker → universe 链路 + 缓存."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from funnel import layers as fl


@pytest.fixture(autouse=True)
def clear_caches():
    fl._clear_cache()
    yield
    fl._clear_cache()


@pytest.fixture
def fake_companies_csv(tmp_path, monkeypatch):
    """构造一个临时 companies.csv 替换默认路径."""
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(
        "folder,stock,name,category,industry,industry_l2\n"
        "01,600519,贵州茅台,non_financial,食品饮料,白酒\n"
        "02,000333,美的集团,non_financial,家电,白色家电\n"
        "03,603259,药明康德,non_financial,医药生物,化学制药\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fl, "_COMPANIES_CSV", csv_path)
    return csv_path


@pytest.fixture
def fake_master_yaml(tmp_path, monkeypatch):
    yml = tmp_path / "industry_master.yaml"
    yml.write_text("industries: []\n", encoding="utf-8")
    monkeypatch.setattr(fl, "_INDUSTRY_MASTER_YAML", yml)
    return yml


def test_empty_focus_returns_empty_universe(monkeypatch, fake_companies_csv, fake_master_yaml):
    import state as _state
    monkeypatch.setattr(_state, "get_focus_list", lambda: [])
    monkeypatch.setattr(_state, "get_focus_names", lambda: set())

    df = fl.get_screener_universe()
    assert df.empty
    assert list(df.columns) == ["ticker", "name", "industry_l2"]


def test_focus_expands_via_csv_fallback(monkeypatch, fake_companies_csv, fake_master_yaml):
    """industry.screener 返回空 → 走 companies.csv fallback."""
    import state as _state
    monkeypatch.setattr(_state, "get_focus_list",
                        lambda: [{"industry": "白酒", "type": "stalwart"}])
    monkeypatch.setattr(_state, "get_focus_names", lambda: {"白酒"})

    # 强制 screener.list_industry_candidates 返回空,触发 csv fallback
    from industry import screener as _scr
    monkeypatch.setattr(_scr, "list_industry_candidates",
                        lambda industry, **kw: [])

    tickers = fl.expand_focus_to_tickers({"白酒"})
    assert "600519" in tickers

    df = fl.get_screener_universe()
    assert "600519" in df["ticker"].tolist()
    row = df[df["ticker"] == "600519"].iloc[0]
    assert row["name"] == "贵州茅台"
    assert row["industry_l2"] == "白酒"


def test_focus_expands_via_screener(monkeypatch, fake_companies_csv, fake_master_yaml):
    """screener 返回非空 → 直接用,不走 fallback."""
    import state as _state
    monkeypatch.setattr(_state, "get_focus_list",
                        lambda: [{"industry": "白酒", "type": "stalwart"}])
    monkeypatch.setattr(_state, "get_focus_names", lambda: {"白酒"})

    from industry import screener as _scr
    monkeypatch.setattr(
        _scr, "list_industry_candidates",
        lambda industry, **kw: [
            {"ticker": "600519", "name": "贵州茅台",
             "market_cap": 2e12, "data_source": "market.duckdb"},
            {"ticker": "000858", "name": "五粮液",
             "market_cap": 5e11, "data_source": "market.duckdb"},
        ],
    )

    tickers = fl.expand_focus_to_tickers({"白酒"})
    assert tickers == {"600519", "000858"}


def test_cache_invalidated_on_mtime_change(monkeypatch, fake_companies_csv, fake_master_yaml):
    import state as _state
    monkeypatch.setattr(_state, "get_focus_list",
                        lambda: [{"industry": "白酒", "type": "stalwart"}])
    monkeypatch.setattr(_state, "get_focus_names", lambda: {"白酒"})

    calls = {"n": 0}

    def _stub(industry, **kw):
        calls["n"] += 1
        return [{"ticker": "600519", "name": "贵州茅台",
                 "market_cap": 1, "data_source": "x"}]

    from industry import screener as _scr
    monkeypatch.setattr(_scr, "list_industry_candidates", _stub)

    fl.expand_focus_to_tickers({"白酒"})
    fl.expand_focus_to_tickers({"白酒"})  # 命中缓存
    assert calls["n"] == 1

    # 改 mtime → 缓存失效
    now = os.path.getmtime(fake_companies_csv) + 100
    os.utime(fake_companies_csv, (now, now))

    fl.expand_focus_to_tickers({"白酒"})
    assert calls["n"] == 2


def test_get_focus_names_delegates_to_state(monkeypatch, fake_companies_csv, fake_master_yaml):
    import state as _state
    monkeypatch.setattr(_state, "get_focus_names",
                        lambda: {"白酒", "保险"})
    assert fl.get_focus_names() == {"白酒", "保险"}


def test_get_watchlist_tickers(monkeypatch):
    import watchlist as _wl

    class _E:
        def __init__(self, t):
            self.ticker = t

    monkeypatch.setattr(_wl, "load", lambda: [_E("600519"), _E("000333")])
    assert fl.get_watchlist_tickers() == {"600519", "000333"}
