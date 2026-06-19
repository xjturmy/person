"""funnel.session 单测 — 用 dict 模拟 st.session_state."""
from __future__ import annotations

import pytest

from funnel import session as fs


class _FakeState(dict):
    """模拟 st.session_state — dict 接口够用."""
    pass


@pytest.fixture
def fake_ss(monkeypatch):
    fake = _FakeState()
    monkeypatch.setattr(fs, "_session_state", lambda: fake)
    return fake


def test_get_default_when_missing(fake_ss):
    assert fs.get_draft("foo", default=42) == 42


def test_set_and_get(fake_ss):
    fs.set_draft("funnel_industry_draft", [{"industry": "白酒"}])
    assert fs.get_draft("funnel_industry_draft") == [{"industry": "白酒"}]
    assert fake_ss["funnel_industry_draft"] == [{"industry": "白酒"}]


def test_clear_draft(fake_ss):
    fs.set_draft("funnel_industry_draft", "x")
    assert fs.clear_draft("funnel_industry_draft") is True
    assert "funnel_industry_draft" not in fake_ss
    # 再次 clear 返回 False
    assert fs.clear_draft("funnel_industry_draft") is False


def test_clear_all_for_nav_industry_isolated(fake_ss):
    fs.set_draft(fs.FUNNEL_INDUSTRY_DRAFT, "a")
    fs.set_draft(fs.FUNNEL_SCREENER_PRELIM, ["600519"])
    fs.set_draft(fs.FUNNEL_SCREENER_LYNCH, ["000333"])
    fs.set_draft("unrelated_key", "keep")

    n = fs.clear_all_for_nav("industry")
    assert n == 1
    assert fs.FUNNEL_INDUSTRY_DRAFT not in fake_ss
    # screener 区不动
    assert fs.FUNNEL_SCREENER_PRELIM in fake_ss
    assert fs.FUNNEL_SCREENER_LYNCH in fake_ss
    assert "unrelated_key" in fake_ss


def test_clear_all_for_nav_screener(fake_ss):
    fs.set_draft(fs.FUNNEL_SCREENER_PRELIM, ["a"])
    fs.set_draft(fs.FUNNEL_SCREENER_LYNCH, ["b"])
    fs.set_draft(fs.FUNNEL_SCREENER_GRAHAM, ["c"])
    fs.set_draft(fs.FUNNEL_SCREENER_TICKER_INDUSTRY, {"a": "x"})
    fs.set_draft(fs.FUNNEL_INDUSTRY_DRAFT, "keep")

    n = fs.clear_all_for_nav("screener")
    assert n == 4
    assert fs.FUNNEL_INDUSTRY_DRAFT in fake_ss


def test_clear_all_for_nav_unknown(fake_ss):
    fs.set_draft(fs.FUNNEL_INDUSTRY_DRAFT, "a")
    assert fs.clear_all_for_nav("bogus") == 0
    assert fs.FUNNEL_INDUSTRY_DRAFT in fake_ss


def test_no_streamlit_runtime_returns_default(monkeypatch):
    """_session_state() 返回 None 时,api 应静默降级."""
    monkeypatch.setattr(fs, "_session_state", lambda: None)
    assert fs.get_draft("x", default="d") == "d"
    fs.set_draft("x", 1)  # 不抛
    assert fs.clear_draft("x") is False
    assert fs.clear_all_for_nav("industry") == 0
