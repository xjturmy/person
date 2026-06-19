"""tabs.industry.analysis · 只读分析卡(v2.9 重构).

来源:
  - 4 区行业卡(A 速览 / B Top7 / C ETF / D 知识)直接复用 tabs.industry_focus._render_industry_card
  - 21 SW L1 全景复用 tabs.industry_overview.render(用 expander 收起)

信息密度按 v2.9 计划:
  - 默认展开「估值速览 + Top7」(_render_industry_card 内 expander expanded=True)
  - ETF / 知识 已在原 _render_industry_card 中以 divider 分段(原样保留)
  - 21 SW L1 全景 收 1 层 expander
"""
from __future__ import annotations

import importlib

import streamlit as st


def render() -> None:
    """主入口 — 只读分析,不写 focus."""
    # 直接复用原 industry_focus 的渲染逻辑;sidebar editor 与 _save 操作仍走原文件,
    # 这里只调展示函数,不调 _render_sidebar_editor(v2.9 把编辑全挪到 confirm/preselect)。
    import tabs.industry_focus as _focus
    _focus = importlib.reload(_focus)

    # 顶部估值矩阵(粗类热力图 + 细类下钻)
    try:
        st.caption("粗类矩阵看宏观轮动；SW 全景看 A 股行业对标")
        _focus._render_valuation_matrix()
        st.markdown("---")
    except Exception as e:
        st.caption(f"⚠️ 行业估值矩阵加载失败:{e}")

    focus_list = []
    try:
        from funnel import layers as _layers
        focus_list = list(_layers.get_focus_industries() or [])
    except Exception:
        focus_list = []

    if not focus_list:
        st.warning(
            "尚未配置聚焦行业 — 切到「🎯 行业预选」勾选,再到「✅ 行业确定」落盘"
        )
    else:
        try:
            _focus._render_top_banner(focus_list)
        except Exception as e:
            st.caption(f"⚠️ 顶部 banner 失败:{e}")
        for f in focus_list:
            try:
                _focus._render_industry_card(f)
            except Exception as e:
                st.warning(f"行业卡 {f.get('industry')} 渲染失败:{e}")

    # 21 SW L1 全景 — 收 1 层 expander
    with st.expander("🌐 21 SW L1 行业估值全景(全市场视角)", expanded=False):
        st.caption("粗类矩阵看宏观轮动；SW 全景看 A 股行业对标")
        try:
            from tabs import industry_overview as _overview
            _overview.render()
        except Exception as e:
            st.warning(f"21 SW L1 全景加载失败:{e}")


__all__ = ["render"]
