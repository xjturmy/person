"""funnel · Dashboard v2.9 漏斗式数据层 (P0a).

公开接口:
  - session:  草稿 key 常量 + get/set/clear 草稿
  - layers:   聚焦行业 → 候选 ticker → screener universe
  - orphans:  watchlist 中游离于 focus 之外的标的检测

设计原则:
  - 不依赖 streamlit runtime (import-time);单测可离线 import
  - 模块级 mtime 缓存,不使用 @st.cache_data
"""
from __future__ import annotations

from .session import (
    FUNNEL_INDUSTRY_DRAFT,
    FUNNEL_SCREENER_PRELIM,
    FUNNEL_SCREENER_LYNCH,
    FUNNEL_SCREENER_GRAHAM,
    FUNNEL_SCREENER_TICKER_INDUSTRY,
    get_draft,
    set_draft,
    clear_draft,
    clear_all_for_nav,
)
from .layers import (
    get_focus_industries,
    get_focus_names,
    expand_focus_to_tickers,
    get_screener_universe,
    get_watchlist_tickers,
    _clear_cache,
)
from .orphans import find_orphan_watchlist

__all__ = [
    # session
    "FUNNEL_INDUSTRY_DRAFT",
    "FUNNEL_SCREENER_PRELIM",
    "FUNNEL_SCREENER_LYNCH",
    "FUNNEL_SCREENER_GRAHAM",
    "FUNNEL_SCREENER_TICKER_INDUSTRY",
    "get_draft",
    "set_draft",
    "clear_draft",
    "clear_all_for_nav",
    # layers
    "get_focus_industries",
    "get_focus_names",
    "expand_focus_to_tickers",
    "get_screener_universe",
    "get_watchlist_tickers",
    "_clear_cache",
    # orphans
    "find_orphan_watchlist",
]
