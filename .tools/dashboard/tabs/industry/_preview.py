"""行业轻量预览 — 预选展开详情 + 行内 Top1/ETF 摘要."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[4]

try:
    from tabs.industry_focus import (
        LAYER_CN,
        PHASE_EMOJI,
        TYPE_METHODOLOGY,
        _cached_cycle,
        _cached_etf,
        _cached_percentile,
        _cached_top7,
        _format_num,
        _format_pct,
        _industry_master_dict,
    )
except ImportError:
    LAYER_CN = {}
    PHASE_EMOJI = {}
    TYPE_METHODOLOGY = {}


def top1_company_line(industry: str, type_: str) -> str:
    """行内摘要: Top1 公司名 + 分数."""
    try:
        df = _cached_top7(industry, type_, top_n=1)
        if df is None or df.empty:
            return "—"
        row = df.iloc[0]
        score = row.get("score")
        score_s = f"{score:.0f}" if score is not None and pd.notna(score) else "—"
        name = str(row.get("name") or "—")
        return f"{name} ({score_s})"
    except Exception:
        return "—"


def top1_etf_line(industry: str) -> str:
    """行内摘要: 推荐 ETF 代码."""
    try:
        etfs = _cached_etf(industry, top_n=1)
        if not etfs:
            return "—"
        c = etfs[0]
        code = c.get("code") or "—"
        name = c.get("name") or ""
        return f"{code} {name}".strip()
    except Exception:
        return "—"


def render_card_lite(industry: str, type_: str, *, key_prefix: str) -> None:
    """A/B/C/D 轻量详情 — 预选行内 expander 用."""
    pct = _cached_percentile(industry)
    cyc = _cached_cycle(industry)
    master = _industry_master_dict().get(industry, {})

    st.markdown("##### A · 估值与周期")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "周期",
        f"{PHASE_EMOJI.get(cyc.get('phase'), '❓')} {cyc.get('phase_cn', '—')}",
    )
    c2.metric(
        "PE 中位",
        _format_num(pct.get("pe_median")),
        f"第 {_format_pct(pct.get('pe_percentile_10y'))}",
    )
    c3.metric(
        "PB 中位",
        _format_num(pct.get("pb_median")),
        f"第 {_format_pct(pct.get('pb_percentile_10y'))}",
    )
    st.caption(cyc.get("rationale") or "—")

    st.markdown("##### B · Top 3 公司")
    try:
        top_df = _cached_top7(industry, type_, top_n=3)
        if top_df.empty:
            st.caption("暂无评分候选")
        else:
            show = top_df[["rank", "ticker", "name", "score", "rating"]].copy()
            show["score"] = show["score"].apply(
                lambda x: f"{x:.0f}" if pd.notna(x) else "—"
            )
            show.columns = ["排名", "代码", "名称", "分数", "评级"]
            st.dataframe(show, hide_index=True, width="stretch")
    except Exception as ex:
        st.caption(f"评分不可用: {ex}")

    st.markdown("##### C · 推荐 ETF")
    etfs = _cached_etf(industry, top_n=2)
    if not etfs:
        st.caption("暂无 ETF 配置")
    else:
        etf_df = pd.DataFrame([{
            "代码": c["code"],
            "名称": c["name"],
            "1y": f"{c['return_1y']:+.1%}" if c.get("return_1y") is not None else "—",
            "层级": LAYER_CN.get(c.get("layer"), "—"),
        } for c in etfs])
        st.dataframe(etf_df, hide_index=True, width="stretch")
        target = etfs[0].get("target_pct")
        if target:
            st.caption(f"建议配置 {target[0]}-{target[1]}%")

    st.markdown("##### D · 行业要点")
    summary = (master.get("summary") or "").strip()
    if summary:
        st.markdown(summary[:400] + ("…" if len(summary) > 400 else ""))
    indicators = (master.get("cycle_attrs") or {}).get("key_indicators") or []
    if indicators:
        st.markdown("**关键指标**: " + " · ".join(indicators[:5]))
    label, kpath = TYPE_METHODOLOGY.get(
        type_, ("评分方法论", "01_knowledge/03_投资策略与选股/")
    )
    st.caption(f"方法论: {label}")


__all__ = [
    "top1_company_line",
    "top1_etf_line",
    "render_card_lite",
]
