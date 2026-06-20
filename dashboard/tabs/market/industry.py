"""市场 Tab · ⑤ 行业 PE 热力图(下钻已迁至 tabs.industry._drilldown / 行业预选)。"""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from ._helpers import _load_industry_pe_latest


def _section_industry_heatmap(db_path: str, mtime: float) -> None:
    """段 ⑤:申万一级 28 行业 PE 中位数,从低到高条形图。"""
    df = _load_industry_pe_latest(db_path, mtime)
    if df.empty:
        st.caption("(industry_pe 表无数据)")
        return
    if "level" in df.columns and df["level"].notna().any():
        df1 = df[df["level"] == 1].copy()
        if df1.empty:
            df1 = df.copy()
    else:
        df1 = df.copy()
    df1 = df1.sort_values("pe_median")
    fig = px.bar(
        df1, x="industry_name", y="pe_median",
        color="pe_median", color_continuous_scale="RdYlGn_r",
        hover_data=["pe_weighted", "pe_arith", "n_companies", "date"],
    )
    fig.update_layout(
        height=460, xaxis_tickangle=-40,
        title=f"{len(df1)} 个行业 · PE 中位数(从低到高 · 绿=低估 / 红=高估)",
        xaxis_title="", yaxis_title="PE 中位数",
        margin=dict(t=50, b=140),
        coloraxis_colorbar=dict(title="PE"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "⚠️ 上图为国民经济行业分类(GB/T 4754,19 粗类)。"
        "申万二级深度下钻(ETF / 龙头 Top5 / 知识)已迁至 🎯 **行业预选**。"
    )


def _section_industry_drilldown() -> None:
    """兼容旧 import — 完整下钻请用 tabs.industry._drilldown。"""
    from tabs.industry._drilldown import (
        build_industry_rank_df,
        load_name_to_meta,
        render_industry_drilldown,
        render_rank_table,
    )

    name_to_meta = load_name_to_meta()
    if not name_to_meta:
        st.info("未配置 industry_master.yaml,跳过下钻区")
        return

    rank_df = build_industry_rank_df(name_to_meta)
    if rank_df.empty:
        st.info("分位计算无可用行业")
        return

    render_rank_table(rank_df)
    options = rank_df["行业"].tolist()
    pick = st.selectbox(
        "🎯 选择行业深入了解(默认为分位最低)",
        options,
        index=0,
        key="market_industry_drilldown_pick",
    )
    if pick:
        meta = name_to_meta[pick]
        render_industry_drilldown(
            pick,
            type_=meta.get("type", "stalwart"),
            rank_df=rank_df,
            interactive_watchlist=False,
            key_prefix="market_drill",
            show_footer_hint=True,
        )
