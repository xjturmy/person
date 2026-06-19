"""tabs.screener._universe · focus 行业 → screener universe 薄封装.

get_or_block:
  - focus 为空 → 警告 + 引导按钮 + st.stop;不抛异常,正常返回 None(若未 stop)
  - 否则返回 DataFrame(ticker/name/industry_l2)

get_ticker_industry_map:
  - 从 universe 抽 ticker→industry_l2 dict
  - 同时把 dict 写入 funnel.session.FUNNEL_SCREENER_TICKER_INDUSTRY
    给 confirm 写 watchlist 时反查 source_industry。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[4]
_INDUSTRY_MASTER = _ROOT / ".config" / "industry_master.yaml"

# 延迟 import streamlit 让离线测试可 import 本模块的纯函数
try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover
    st = None  # type: ignore


def get_or_block() -> Optional[pd.DataFrame]:
    """取 universe;focus 为空 → 警告 + 跳转按钮 + st.stop()。

    返回 DataFrame 或 None(只在 st 不可用且 universe 空时返回 None)。
    """
    try:
        from funnel import layers as _layers
    except Exception as e:
        if st is not None:
            st.error(f"funnel.layers 加载失败:{e}")
            st.stop()
        return None

    df = _layers.get_screener_universe()
    if df is None or df.empty:
        if st is not None:
            st.warning(
                "⚠️ 请先完成「行业确定」 — 选股 universe 来自聚焦行业展开,"
                "focus 为空时无法继续。"
            )
            if st.button("→ 去行业确定", key="screener_goto_industry_confirm",
                         type="primary"):
                try:
                    from navigation import (
                        goto, PAGE_MARKET_HUB, SUB_INDUSTRY_CONFIRM,
                    )
                    goto(PAGE_MARKET_HUB, sub_tab=SUB_INDUSTRY_CONFIRM)
                except Exception as nav_e:
                    st.error(f"跳转失败:{nav_e}")
            st.stop()
        return None

    # 顺便把 ticker→industry 映射写入 funnel.session 草稿(供 confirm 反查)
    try:
        _publish_ticker_industry_map(df)
    except Exception:
        pass

    return df


def get_ticker_industry_map(universe_df: Optional[pd.DataFrame] = None) -> dict[str, str]:
    """返回 ticker→industry_l2 dict;同时写入 session 草稿。"""
    if universe_df is None:
        try:
            from funnel import layers as _layers
            universe_df = _layers.get_screener_universe()
        except Exception:
            return {}
    if universe_df is None or universe_df.empty:
        return {}
    mp = {
        str(r["ticker"]).zfill(6): str(r.get("industry_l2", "") or "")
        for _, r in universe_df.iterrows()
        if r.get("ticker")
    }
    _publish_session(mp)
    return mp


def _publish_ticker_industry_map(universe_df: pd.DataFrame) -> None:
    mp = {
        str(r["ticker"]).zfill(6): str(r.get("industry_l2", "") or "")
        for _, r in universe_df.iterrows()
        if r.get("ticker")
    }
    _publish_session(mp)


def _publish_session(mp: dict[str, str]) -> None:
    try:
        from funnel import session as _session
        _session.set_draft(_session.FUNNEL_SCREENER_TICKER_INDUSTRY, mp)
    except Exception:
        pass


def industry_tickers(industry: str) -> set[str]:
    """行业名 → leaders ticker 集合(读 industry_master.yaml)。"""
    if not industry or not _INDUSTRY_MASTER.exists():
        return set()
    try:
        import yaml
        data = yaml.safe_load(_INDUSTRY_MASTER.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    for item in data.get("industries") or []:
        if str(item.get("name", "")).strip() == industry.strip():
            leaders = item.get("leaders") or []
            return {str(t).strip().zfill(6) for t in leaders if t}
    return set()


__all__ = ["get_or_block", "get_ticker_industry_map", "industry_tickers"]
