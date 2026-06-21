"""navigation.py 单元测试 — goto/consume/peek 语义。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1]
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

import streamlit as st  # noqa: E402

import navigation as nav  # noqa: E402


@pytest.fixture(autouse=True)
def clear_session():
    # streamlit session_state 在脚本外行为类似 dict;每个测试前清空。
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    yield
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def test_goto_writes_session_state():
    nav.goto(nav.PAGE_COMPANY, company="美的集团", sub_tab="lynch")
    intent = st.session_state.get("nav_intent")
    assert intent is not None
    assert intent["page"] == nav.PAGE_COMPANY
    assert intent["company"] == "美的集团"
    assert intent["sub_tab"] == "lynch"


def test_goto_optional_args_omitted():
    nav.goto(nav.PAGE_SCREENER)
    intent = st.session_state["nav_intent"]
    assert intent == {"page": nav.PAGE_SCREENER}


def test_goto_focus_and_prefill_are_dicts():
    nav.goto(nav.PAGE_SCREENER, focus={"industry": "白酒"})
    nav.goto(nav.PAGE_DC, company="贵州茅台", prefill={"price": 1500.0})
    # 覆盖语义:只保留最后一次
    intent = st.session_state["nav_intent"]
    assert intent["page"] == nav.PAGE_DC
    assert intent["company"] == "贵州茅台"
    assert intent["prefill"] == {"price": 1500.0}
    assert "focus" not in intent


def test_peek_intent_does_not_clear():
    nav.goto(nav.PAGE_COMPANY, company="X")
    first = nav.peek_intent()
    second = nav.peek_intent()
    assert first is not None and first["company"] == "X"
    assert second is not None and second["company"] == "X"
    assert "nav_intent" in st.session_state


def test_consume_intent_clears():
    nav.goto(nav.PAGE_COMPANY, company="Y")
    val = nav.consume_intent()
    assert val is not None and val["company"] == "Y"
    assert "nav_intent" not in st.session_state
    assert nav.consume_intent() is None


def test_no_intent_returns_none():
    assert nav.peek_intent() is None
    assert nav.consume_intent() is None


def test_page_constants_match_app_strings():
    # 保证与 app.py 同名常量值一致(emoji + 中文)。app.py 用对齐空格,需 regex 抽。
    import re
    app_py = (DASHBOARD / "app.py").read_text(encoding="utf-8")
    for name, val in [
        ("PAGE_MARKET_HUB", nav.PAGE_MARKET_HUB),
        ("PAGE_SCREENER", nav.PAGE_SCREENER),
        ("PAGE_COMPANY", nav.PAGE_COMPANY),
        ("PAGE_GOLD", nav.PAGE_GOLD),
        ("PAGE_DC", nav.PAGE_DC),
    ]:
        m = re.search(rf'^{name}\s*=\s*"([^"]*)"', app_py, re.M)
        assert m is not None, f"{name} 未在 app.py 中找到"
        assert m.group(1) == val, f"{name} 不一致: {m.group(1)!r} vs {val!r}"
