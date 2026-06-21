"""funnel.session · 草稿 key 常量 + session_state 读写薄包装.

草稿 key 命名约定:
  全部以 ``FUNNEL_`` 开头;按导航前缀分组(industry/screener/company/dc/gold),
  ``clear_all_for_nav(nav)`` 按前缀批清。

设计:
  - ``import streamlit`` 延迟到函数体内,确保离线测试 (无 streamlit runtime)
    也能 import 本模块。
"""
from __future__ import annotations

from typing import Any

# ─── 草稿 key 常量 ──────────────────────────────────────────────────────

FUNNEL_INDUSTRY_DRAFT = "funnel_industry_draft"
"""list[dict]: [{industry, type, weight, note}] — 行业聚焦待提交草稿."""

FUNNEL_SCREENER_PRELIM = "funnel_screener_prelim"
"""list[str]: 初筛通过 ticker."""

FUNNEL_SCREENER_LYNCH = "funnel_screener_lynch_hits"
"""list[str]: 林奇命中 ticker."""

FUNNEL_SCREENER_GRAHAM = "funnel_screener_graham_hits"
"""list[str]: 格雷厄姆命中 ticker."""

FUNNEL_SCREENER_BUFFETT = "funnel_screener_buffett_hits"
"""list[str]: 巴菲特命中 ticker."""

FUNNEL_SCREENER_TICKER_INDUSTRY = "funnel_screener_ticker_industry"
"""dict[str, str]: ticker → industry_l2;供 watchlist source_industry 反查."""


# 导航前缀映射 — clear_all_for_nav 按此清理
_NAV_PREFIX: dict[str, str] = {
    "industry": "funnel_industry_",
    "screener": "funnel_screener_",
    "company": "funnel_company_",
    "dc": "funnel_dc_",
    "gold": "funnel_gold_",
}


def _session_state() -> Any:
    """延迟 import streamlit.session_state;无 runtime 时返回 None。"""
    try:
        import streamlit as st  # noqa: WPS433
    except Exception:
        return None
    try:
        return st.session_state
    except Exception:
        return None


# ─── 草稿读写 ──────────────────────────────────────────────────────────


def get_draft(key: str, default: Any = None) -> Any:
    ss = _session_state()
    if ss is None:
        return default
    try:
        return ss.get(key, default)
    except Exception:
        return default


def set_draft(key: str, value: Any) -> None:
    ss = _session_state()
    if ss is None:
        return
    try:
        ss[key] = value
    except Exception:
        pass


def clear_draft(key: str) -> bool:
    """删除单个 key;不存在返回 False。"""
    ss = _session_state()
    if ss is None:
        return False
    try:
        if key in ss:
            del ss[key]
            return True
    except Exception:
        return False
    return False


def clear_all_for_nav(nav: str) -> int:
    """按导航前缀批量清理草稿;返回清理条数。

    nav ∈ {"industry","screener","company","dc","gold"}.
    未知 nav → 0。
    """
    prefix = _NAV_PREFIX.get(nav)
    if not prefix:
        return 0
    ss = _session_state()
    if ss is None:
        return 0
    try:
        keys = [k for k in list(ss.keys()) if isinstance(k, str) and k.startswith(prefix)]
    except Exception:
        return 0
    n = 0
    for k in keys:
        try:
            del ss[k]
            n += 1
        except Exception:
            pass
    return n


__all__ = [
    "FUNNEL_INDUSTRY_DRAFT",
    "FUNNEL_SCREENER_PRELIM",
    "FUNNEL_SCREENER_LYNCH",
    "FUNNEL_SCREENER_GRAHAM",
    "FUNNEL_SCREENER_BUFFETT",
    "FUNNEL_SCREENER_TICKER_INDUSTRY",
    "get_draft",
    "set_draft",
    "clear_draft",
    "clear_all_for_nav",
]
