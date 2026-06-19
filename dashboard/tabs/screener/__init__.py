"""tabs.screener · v2.9 选股四格流程.

四个子 Tab 由 ``render()`` 内 ``st.tabs`` 分发(与 spec 一致):
  prelim       → 初步筛选 (多维度过滤,结果写 FUNNEL_SCREENER_PRELIM)
  lynch_pick   → 林奇选股 (六类分类器)
  graham_pick  → 格雷厄姆选股 (四类 + 可选 Buffett 引擎)
  confirm      → 选股确定 (三路命中合并草稿 + 写 watchlist)

公共 universe: ``_universe.get_or_block`` — focus 为空时阻断 + 跳转引导。
"""
from __future__ import annotations

import streamlit as st

import navigation as nav
from navigation import (
    SUB_SCREENER_CONFIRM,
    SUB_SCREENER_GRAHAM,
    SUB_SCREENER_LYNCH,
    SUB_SCREENER_PRELIM,
)

from . import _universe, confirm, graham_pick, lynch_pick, prelim


def _industry_tickers(industry: str) -> set[str]:
    """行业名 → leaders ticker 集合(读 industry_master.yaml)。"""
    return _universe.industry_tickers(industry)


def render(companies=None, db_mtime: float = 0.0) -> None:
    """选股页入口 — app.py ``PAGE_SCREENER`` 调用。"""
    _sub_tab_hint = None
    try:
        from navigation import consume_intent as _consume_intent
        _intent = _consume_intent()
        if _intent and _intent.get("sub_tab"):
            _sub_tab_hint = _intent["sub_tab"]
    except Exception:
        pass
    if _sub_tab_hint:
        st.info(f"👉 请点击 sub-tab:**{_sub_tab_hint}**")

    tab_prelim, tab_lynch, tab_value, tab_confirm = st.tabs([
        f"🧮 {SUB_SCREENER_PRELIM}",
        f"🌱 {SUB_SCREENER_LYNCH}",
        f"📐 {SUB_SCREENER_GRAHAM}",
        f"✅ {SUB_SCREENER_CONFIRM}",
    ])
    with tab_prelim:
        prelim.render(companies, db_mtime)
    with tab_lynch:
        lynch_pick.render(companies, db_mtime)
    with tab_value:
        graham_pick.render(companies, db_mtime)
    with tab_confirm:
        confirm.render(companies, db_mtime)


__all__ = [
    "_universe", "prelim", "lynch_pick", "graham_pick", "confirm",
    "render", "nav", "_industry_tickers",
]
