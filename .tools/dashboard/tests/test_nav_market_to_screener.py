"""P0 阶段 2 — Agent B:验证「市场/行业 → 选股」跨页跳转协议。

不强依赖 streamlit AppTest;直接 import navigation 并断言:
  - 调 goto(PAGE_SCREENER, focus={"industry": X}) 把 intent 写入 session_state
  - peek_intent / consume_intent 行为符合契约
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DASH = ROOT / ".tools" / "dashboard"
if str(DASH) not in sys.path:
    sys.path.insert(0, str(DASH))


@pytest.fixture(autouse=True)
def _clear_state():
    """每个测试前清空 streamlit session_state。"""
    import streamlit as st
    try:
        for k in list(st.session_state.keys()):
            del st.session_state[k]
    except Exception:
        pass
    yield


def test_goto_screener_with_industry_focus_writes_intent():
    import navigation as nav
    import streamlit as st

    nav.goto(nav.PAGE_SCREENER, focus={"industry": "白酒"})
    intent = st.session_state.get("nav_intent")
    assert intent is not None
    assert intent["page"] == nav.PAGE_SCREENER
    assert intent["focus"]["industry"] == "白酒"


def test_peek_does_not_clear_intent():
    import navigation as nav
    import streamlit as st

    nav.goto(nav.PAGE_SCREENER, focus={"industry": "电池"})
    peek1 = nav.peek_intent()
    peek2 = nav.peek_intent()
    assert peek1 == peek2
    assert st.session_state.get("nav_intent") is not None


def test_consume_clears_intent():
    import navigation as nav
    import streamlit as st

    nav.goto(nav.PAGE_SCREENER, focus={"industry": "保险"})
    consumed = nav.consume_intent()
    assert consumed is not None
    assert consumed["focus"]["industry"] == "保险"
    assert "nav_intent" not in st.session_state
    assert nav.consume_intent() is None


def test_industry_master_lookup_returns_tickers():
    """选股入口用 _industry_tickers 把行业名 → leaders tickers 集合。"""
    from tabs.screener import _industry_tickers

    tickers = _industry_tickers("白酒")
    assert isinstance(tickers, set)
    # industry_master 中白酒至少有 600519(茅台)
    assert "600519" in tickers, f"白酒 leaders 应含茅台,实际:{tickers}"


def test_unknown_industry_returns_empty_set():
    from tabs.screener import _industry_tickers
    assert _industry_tickers("__不存在的行业__") == set()
