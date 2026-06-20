"""tabs.industry.analysis · 全市场扫描台(只读,不依赖 focus).

职责:
  - 行业估值矩阵(粗类热力图 + 细类下钻)
  - 21 SW L1 全景(默认展开) — 发现低估行业
  - L2 知识块内可「加入预选」
  不含已 focus 行业的 4 区重卡(迁至「行业确定」档案区)。
"""
from __future__ import annotations

import importlib
import os

import streamlit as st

from tabs.industry.preselect import _load_kondratieff


def _render_kondratieff_hint() -> None:
    """一行引用市场研判结论,不重复完整 banner."""
    kdf = _load_kondratieff()
    if not kdf:
        return
    phase = kdf.get("phase") or "—"
    emoji = kdf.get("phase_emoji") or "🔴"
    strategy = kdf.get("strategy_summary") or ""
    st.caption(
        f"{emoji} 当前康波 **{phase}**"
        + (f" — {strategy}" if strategy else "")
        + " · 完整解读见「📊 市场研判」"
    )


def render() -> None:
    """主入口 — 全市场只读扫描,不写 focus."""
    st.markdown("### 🏭 行业分析 · 全市场扫描")
    st.caption(
        "从估值矩阵和 SW 全景发现机会 → 勾选/加入预选 → 到「🎯 行业预选 · 初步筛选行业」深度研判"
    )
    _render_kondratieff_hint()

    from tabs import industry_focus as _focus
    if os.getenv("PRESON_DEV_RELOAD"):
        _focus = importlib.reload(_focus)

    try:
        _focus._render_valuation_matrix()
        st.markdown("---")
    except Exception as e:
        st.caption(f"⚠️ 行业估值矩阵加载失败:{e}")

    st.markdown("#### 🌐 21 SW L1 行业估值全景")
    try:
        from tabs import industry_overview as _overview
        _overview.render(show_preselect_actions=True)
    except Exception as e:
        st.warning(f"21 SW L1 全景加载失败:{e}")


__all__ = ["render"]
