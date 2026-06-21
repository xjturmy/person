"""P0 阶段 2 — Agent B:验证「选股 → 公司研究」跨页跳转协议。"""
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
    import streamlit as st
    try:
        for k in list(st.session_state.keys()):
            del st.session_state[k]
    except Exception:
        pass
    yield


def test_goto_company_with_company_and_sub_tab():
    import navigation as nav
    import streamlit as st

    nav.goto(nav.PAGE_COMPANY, company="贵州茅台", sub_tab="lynch")
    intent = st.session_state.get("nav_intent")
    assert intent is not None
    assert intent["page"] == nav.PAGE_COMPANY
    assert intent["company"] == "贵州茅台"
    assert intent["sub_tab"] == "lynch"


def test_consume_returns_full_payload():
    import navigation as nav

    nav.goto(nav.PAGE_COMPANY, company="新华保险", sub_tab="lynch")
    consumed = nav.consume_intent()
    assert consumed["page"] == nav.PAGE_COMPANY
    assert consumed["company"] == "新华保险"
    assert consumed["sub_tab"] == "lynch"


def test_overwrite_intent_keeps_latest():
    """连续两次 goto,只保留最后一次(契约)。"""
    import navigation as nav

    nav.goto(nav.PAGE_COMPANY, company="A")
    nav.goto(nav.PAGE_COMPANY, company="B", sub_tab="lynch")
    consumed = nav.consume_intent()
    assert consumed["company"] == "B"
    assert consumed["sub_tab"] == "lynch"


def test_screener_module_imports_nav():
    """轻量结构性断言:tabs/screener.py 已 import navigation 并暴露 PAGE_COMPANY 跳转点。"""
    import tabs.screener as scr
    assert hasattr(scr, "nav"), "tabs.screener 应 import navigation as nav"
    assert scr.nav.PAGE_COMPANY.endswith("公司研究")
    assert scr.nav.PAGE_SCREENER.endswith("选股")
