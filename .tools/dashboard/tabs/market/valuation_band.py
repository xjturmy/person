"""市场 Tab · ④ A 股全指 PE-TTM 分位带(全周期 20/50/80 分位横线)。"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ._helpers import (
    LIXINGER_FONT,
    LIXINGER_LINE_COLOR,
    _apply_lixinger_layout,
    _load_macro_series,
)


def _section_a_full_band(db_path: str, mtime: float) -> None:
    """段 ④:A 股全指 PE-TTM 分位带 — 当前值 + 全周期 20/50/80 分位横线。"""
    df = _load_macro_series(db_path, "A_FULL_PE", mtime, years=10)
    if df.empty or len(df) < 30:
        st.caption("(A_FULL_PE 数据不足。先跑 "
                   "`.venv/bin/python .tools/db/fetch_macro.py --only A_FULL_PE`)")
        return
    cur = df.iloc[-1]["value"]
    cur_date = df.iloc[-1]["date"]
    series = df["value"].dropna()
    p20, p50, p80 = (
        float(series.quantile(0.2)),
        float(series.quantile(0.5)),
        float(series.quantile(0.8)),
    )
    pct = float((series <= cur).sum()) / len(series)
    if pct <= 0.20:
        verdict, color = "🟢 低位(便宜)", "#1b8a3a"
    elif pct <= 0.50:
        verdict, color = "🟢 偏低", "#1b8a3a"
    elif pct <= 0.80:
        verdict, color = "🟡 中性", "#f0ad4e"
    else:
        verdict, color = "🔴 高位(贵)", "#d9534f"

    # 数据范围 + 8% padding
    y_min = float(series.min()); y_max = float(series.max())
    data_range = max(y_max - y_min, 0.5)
    pad = max(data_range * 0.05, 0.4)
    y_lo, y_hi = y_min - pad, y_max + pad

    # 4 段分位带(浅色实心) + 右侧深色档位标签
    BAND_DEFS = [
        (y_lo, p20,  "#e6faee", "#1e8449", "低估 (≤20%)"),
        (p20,  p50,  "#f2fcf6", "#27ae60", "偏低 (20-50%)"),
        (p50,  p80,  "#fffdf2", "#b58a00", "中性 (50-80%)"),
        (p80,  y_hi, "#fef5f4", "#c0392b", "高位 (>80%)"),
    ]

    fig = go.Figure()
    for lo, hi, fill, label_color, label_text in BAND_DEFS:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=fill, opacity=1.0,
                      line_width=0, layer="below")
        fig.add_annotation(
            xref="paper", yref="y", x=0.995, y=(lo + hi) / 2,
            text=f"<b>{label_text}</b>",
            showarrow=False, xanchor="right", yanchor="middle",
            font=dict(size=11, color=label_color, family=LIXINGER_FONT),
        )

    # 主线 — 2.8px spline
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["value"], name="A 股全指 PE",
        line=dict(color=LIXINGER_LINE_COLOR, width=2.8,
                  shape="spline", smoothing=0.6),
        hovertemplate="%{x|%Y-%m-%d}<br>PE: %{y:.2f}x<extra></extra>",
    ))

    # 当前点 + 数字气泡(单一强调)
    fig.add_trace(go.Scatter(
        x=[cur_date], y=[cur], mode="markers",
        marker=dict(size=14, color=LIXINGER_LINE_COLOR,
                    line=dict(color="white", width=2.5)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(
        x=cur_date, y=cur,
        text=f"<b>{cur:.1f}x · {pct*100:.0f}% 分位</b>",
        showarrow=True, arrowhead=0, arrowwidth=1.2,
        arrowcolor=LIXINGER_LINE_COLOR,
        ax=-50, ay=-32,
        font=dict(size=12, color=LIXINGER_LINE_COLOR, family=LIXINGER_FONT),
        bgcolor="rgba(255,255,255,0.95)",
        bordercolor=LIXINGER_LINE_COLOR, borderwidth=1, borderpad=3,
    )

    _apply_lixinger_layout(fig, height=340, y_title="PE-TTM (x)",
                           y_range=[y_lo, y_hi])

    st.markdown(
        f"<div style='font-size:13px;color:#444;margin:2px 0 6px'>"
        f"全周期分位 <b>{pct*100:.0f}%</b> · 评级 <b>{verdict}</b> · "
        f"P20={p20:.1f}x / P50={p50:.1f}x / P80={p80:.1f}x</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, width="stretch")
