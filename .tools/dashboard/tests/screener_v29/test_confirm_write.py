"""tabs.screener.confirm.write_selected_to_watchlist · source_industry 反查写入正确."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def redirect_watchlist(tmp_path, monkeypatch):
    import watchlist as wl
    monkeypatch.setattr(wl, "WATCHLIST_YAML", tmp_path / "watchlist.yaml")
    monkeypatch.setattr(wl, "LEGACY_MD", tmp_path / "watchlist.md")


def test_write_with_session_industry_map(monkeypatch):
    from funnel import session as _session
    from tabs.screener import confirm as _confirm
    import watchlist as wl

    # 用 dict 模拟 session_state
    fake_ss = {
        _session.FUNNEL_SCREENER_TICKER_INDUSTRY: {
            "600519": "白酒",
            "000858": "白酒",
        }
    }
    monkeypatch.setattr(_session, "_session_state", lambda: fake_ss)

    n = _confirm.write_selected_to_watchlist(
        ["600519", "000858"],
        preset_label="v2.9 选股确定",
        name_lookup={"600519": "贵州茅台", "000858": "五粮液"},
    )
    assert n == 2

    entries = wl.load()
    by = {e.ticker: e for e in entries}
    assert by["600519"].source_industry == "白酒"
    assert by["000858"].source_industry == "白酒"
    assert by["600519"].name == "贵州茅台"
    assert by["600519"].preset == "v2.9 选股确定"


def test_write_ticker_missing_in_map_defaults_unknown(monkeypatch):
    from funnel import session as _session
    from tabs.screener import confirm as _confirm
    import watchlist as wl

    fake_ss = {
        _session.FUNNEL_SCREENER_TICKER_INDUSTRY: {"600519": "白酒"}
    }
    monkeypatch.setattr(_session, "_session_state", lambda: fake_ss)

    n = _confirm.write_selected_to_watchlist(
        ["600519", "999999"],
        preset_label="t",
        name_lookup={"600519": "茅台"},
    )
    assert n == 2
    by = {e.ticker: e for e in wl.load()}
    assert by["600519"].source_industry == "白酒"
    assert by["999999"].source_industry == "unknown"


def test_merge_draft_hits_tagging(monkeypatch):
    from funnel import session as _session
    from tabs.screener import confirm as _confirm

    fake_ss = {
        _session.FUNNEL_SCREENER_PRELIM: ["600519", "000858"],
        _session.FUNNEL_SCREENER_LYNCH:  ["000858", "002594"],
        _session.FUNNEL_SCREENER_GRAHAM: ["600519"],
    }
    monkeypatch.setattr(_session, "_session_state", lambda: fake_ss)

    out = _confirm._merge_draft_hits()
    by = {r["ticker"]: r["sources"] for _, r in out.iterrows()}
    assert by["600519"] == "P+G"
    assert by["000858"] == "P+L"
    assert by["002594"] == "L"
