"""统一跳转协议 — P0 阶段 1 基础设施。

各 Tab 想跨页跳转时调用 `goto(...)`,把意图写入 `st.session_state["nav_intent"]` 并触发 rerun。
路由层(app.py)在 sub-tab radio 渲染前 `consume_intent()` 写入持久 key;
`st.tabs` 无法跨 rerun 记住选中项,市场 & 行业页改用带 session key 的 `st.radio`。

PAGE_* 常量值必须与 app.py 中同名常量完全一致(emoji + 中文标签),
否则路由比较会失配。这里 mirror,**不**改 app.py 的值。
"""
from __future__ import annotations

from typing import Any, Optional

import streamlit as st


# ─── 与 app.py 一一对齐(emoji + 中文)─────────────────────────────────
PAGE_MARKET_HUB = "🌡️ 市场 & 行业"
PAGE_SCREENER   = "🔍 选股"
PAGE_COMPANY    = "🏢 公司研究"
PAGE_GOLD       = "🥇 黄金"
PAGE_DC         = "💼 决策中心"

# v2.9 P0b: PAGE_MARKET_HUB 的 4 个 sub-tab 标签(与 app.py st.radio 选项 1:1)
SUB_MARKET_JUDGE       = "市场研判"
SUB_INDUSTRY_ANALYSIS  = "行业分析"
SUB_INDUSTRY_PRESELECT = "行业预选"
SUB_INDUSTRY_CONFIRM   = "行业确定"

MARKET_HUB_SUB_TAB_KEY = "market_hub_sub_tab"

# v2.9 P1: PAGE_SCREENER 的 4 个 sub-tab 标签(与 tabs/screener/__init__.py st.tabs 一致,不含 emoji)
SUB_SCREENER_PRELIM    = "初步筛选"
SUB_SCREENER_LYNCH     = "林奇选股"
SUB_SCREENER_GRAHAM    = "格雷厄姆选股"
SUB_SCREENER_CONFIRM   = "选股确定"

# v2.9: PAGE_DC 的 4 个 sub-tab 标签(与 decision_center.py st.tabs 文案一致,不含 emoji)
SUB_DC_HOLDINGS = "持仓总览"
SUB_DC_TRACKER  = "持仓跟踪"
SUB_DC_LOG      = "决策日志"
SUB_DC_REPORTS  = "月报历史"

_INTENT_KEY = "nav_intent"


def goto(
    page: str,
    *,
    company: Optional[str] = None,
    sub_tab: Optional[str] = None,
    focus: Optional[dict] = None,
    prefill: Optional[dict] = None,
) -> None:
    """写入 nav_intent 并 st.rerun()。多次调用覆盖语义(只保留最后一次)。"""
    intent: dict[str, Any] = {"page": page}
    if company is not None:
        intent["company"] = company
    if sub_tab is not None:
        intent["sub_tab"] = sub_tab
    if focus is not None:
        intent["focus"] = dict(focus)
    if prefill is not None:
        intent["prefill"] = dict(prefill)
    st.session_state[_INTENT_KEY] = intent
    try:
        st.rerun()
    except Exception:
        # 离线 / 测试环境下 st.rerun 可能不可用 — 写入已成功,直接吞。
        pass


def consume_intent() -> Optional[dict]:
    """取出并清空 nav_intent。返回 dict 或 None。"""
    return st.session_state.pop(_INTENT_KEY, None)


def peek_intent() -> Optional[dict]:
    """只读不清空。路由层用。"""
    val = st.session_state.get(_INTENT_KEY, None)
    return val if val else None


__all__ = [
    "PAGE_MARKET_HUB", "PAGE_SCREENER", "PAGE_COMPANY", "PAGE_GOLD", "PAGE_DC",
    "SUB_MARKET_JUDGE", "SUB_INDUSTRY_ANALYSIS",
    "SUB_INDUSTRY_PRESELECT", "SUB_INDUSTRY_CONFIRM",
    "MARKET_HUB_SUB_TAB_KEY",
    "SUB_SCREENER_PRELIM", "SUB_SCREENER_LYNCH",
    "SUB_SCREENER_GRAHAM", "SUB_SCREENER_CONFIRM",
    "SUB_DC_HOLDINGS", "SUB_DC_TRACKER", "SUB_DC_LOG", "SUB_DC_REPORTS",
    "goto", "consume_intent", "peek_intent",
]
