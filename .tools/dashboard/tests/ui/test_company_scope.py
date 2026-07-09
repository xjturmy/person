"""公司研究页 company_scope 过滤辅助单测。"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
import sys

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from tabs.company import company_scope as cs  # noqa: E402


COMPANIES = ["01_新华保险", "06_贵州茅台", "07_美的集团", "98_候选股"]
FOLDER_TO_TICKER = {
    "01_新华保险": "601336",
    "06_贵州茅台": "600519.SH",
    "07_美的集团": "000333",
    "98_候选股": "1234",
}


class FakeHolding:
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker


@pytest.fixture(autouse=True)
def reset_sources(monkeypatch):
    monkeypatch.setattr(cs, "load_active_portfolio_tickers", lambda: set())
    monkeypatch.setattr(cs, "load_watch_tickers", lambda: set())


def test_all_scope_returns_original_list():
    out, hint = cs.filter_companies_by_scope(
        COMPANIES, FOLDER_TO_TICKER, cs.SCOPE_ALL
    )

    assert out == COMPANIES
    assert "全部公司" in hint


def test_active_scope_filters_by_portfolio_active(monkeypatch):
    monkeypatch.setattr(
        cs, "load_active_portfolio_tickers", lambda: {"600519", "601336"}
    )

    out, hint = cs.filter_companies_by_scope(
        COMPANIES, FOLDER_TO_TICKER, cs.SCOPE_ACTIVE
    )

    assert out == ["01_新华保险", "06_贵州茅台"]
    assert "匹配 2 家" in hint


def test_active_scope_empty_keeps_fallback_message():
    out, hint = cs.filter_companies_by_scope(
        COMPANIES, FOLDER_TO_TICKER, cs.SCOPE_ACTIVE
    )

    assert out == []
    assert "当前持仓为空" in hint
    assert "降级显示全部公司" in hint


def test_watch_scope_combines_watch_sources(monkeypatch):
    monkeypatch.setattr(cs, "load_watch_tickers", lambda: {"000333", "600519"})

    out, hint = cs.filter_companies_by_scope(
        COMPANIES, FOLDER_TO_TICKER, cs.SCOPE_WATCH
    )

    assert out == ["06_贵州茅台", "07_美的集团"]
    assert "观察池" in hint


def test_watch_scope_empty_allows_fallback():
    out, hint = cs.filter_companies_by_scope(
        COMPANIES, FOLDER_TO_TICKER, cs.SCOPE_WATCH
    )

    assert out == []
    assert "观察池为空" in hint
    assert "降级显示全部公司" in hint


def test_unknown_scope_falls_back_to_all_companies():
    out, hint = cs.filter_companies_by_scope(COMPANIES, FOLDER_TO_TICKER, "别的")

    assert out == COMPANIES
    assert "未知范围" in hint


def test_ticker_normalization_supports_objects_and_short_codes():
    assert cs._ticker_set([FakeHolding("1234"), FakeHolding("600519.SH")]) == {
        "001234",
        "600519",
    }
