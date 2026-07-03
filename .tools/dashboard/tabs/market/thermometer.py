"""市场 Tab · ③ 5 项宏观时序温度计(M2 / CPI / 10Y / USDCNY / A_FULL_PE)。"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ._helpers import (
    LIGHT_BAND_FILL,
    LIXINGER_LINE_COLOR,
    _apply_lixinger_layout,
    _current_band,
    _load_macro_series,
)


def _section_thermometer_trends(db_path: str, mtime: float) -> None:
    """5 项宏观时序 — 左标右图布局 + 图上画红绿灯阈值带。

    左列(1/4 宽):指标名 / 当前值 / 含义 / 阈值列表(当前档位高亮)
    右列(3/4 宽):时序折线 + 横向 hrect 红绿灯带
    """
    try:
        from ui.thermometer import INDICATORS
    except Exception:
        st.warning("⚠️ 无法加载 header_thermometer.INDICATORS,跳过宏观时序")
        return

    have_any = False
    for ind in INDICATORS:
        df = _load_macro_series(db_path, ind["key"], mtime, years=5)
        if df.empty:
            st.caption(f"({ind['label']} 无数据)")
            continue
        have_any = True

        cur = float(df.iloc[-1]["value"])
        cur_date = df.iloc[-1]["date"].strftime("%Y-%m-%d")
        bands = ind.get("bands", []) or []
        cur_band = _current_band(cur, bands)
        cur_emoji = (cur_band or {}).get("emoji", "⚪")
        cur_label = (cur_band or {}).get("label", "—")

        meta_col, chart_col = st.columns([1, 4])

        with meta_col:
            st.markdown(
                f"<div style='font-size:20px;font-weight:800;margin-bottom:10px;"
                f"color:#1a1a1a'>{ind['label']}</div>",
                unsafe_allow_html=True,
            )
            if bands:
                for b in bands:
                    is_cur = (b is cur_band)
                    style = ("font-weight:700;color:#000;background:#fff3cd;"
                             "padding:3px 8px;border-radius:4px;"
                             "border:1px solid #ffd96a") if is_cur else (
                             "color:#666;padding:3px 8px;background:#fafafa;"
                             "border-radius:4px;border:1px solid #eee")
                    st.markdown(
                        f"<div style='font-size:13px;{style};margin:5px 0;"
                        f"line-height:1.55'>"
                        f"{b['emoji']} {b['label']}{' ← 当前' if is_cur else ''}</div>",
                        unsafe_allow_html=True,
                    )

        with chart_col:
            fig = go.Figure()
            # 数据范围 + 8% padding(贴紧数据,色带 clip 到可见区域)
            y_min = float(df["value"].min())
            y_max = float(df["value"].max())
            data_range = max(y_max - y_min, 0.5)
            pad = max(data_range * 0.08, 0.25)
            y_lo = y_min - pad
            y_hi = y_max + pad

            # 浅色实心色带(opacity=1.0)+ 右侧深色档位标签
            for b in bands:
                lo = b.get("lo"); hi = b.get("hi")
                y0 = lo if lo is not None else y_lo
                y1 = hi if hi is not None else y_hi
                seg_lo = max(y0, y_lo)
                seg_hi = min(y1, y_hi)
                if seg_hi <= seg_lo:
                    continue
                light_fill = LIGHT_BAND_FILL.get(b["fill"], "#f5f5f5")
                fig.add_hrect(y0=seg_lo, y1=seg_hi, fillcolor=light_fill,
                              opacity=1.0, line_width=0, layer="below")

            # 折线 — 2.8px spline,深沉金融蓝
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["value"],
                mode="lines", name=ind["label"],
                line=dict(width=2.6, color=LIXINGER_LINE_COLOR,
                          shape="spline", smoothing=0.6),
                hovertemplate="%{x|%Y-%m-%d}<br>" + ind["label"] + ": %{y:.2f}<extra></extra>",
            ))
            # 当前点突出
            fig.add_trace(go.Scatter(
                x=[df.iloc[-1]["date"]], y=[cur],
                mode="markers",
                marker=dict(size=11, color=LIXINGER_LINE_COLOR,
                            line=dict(color="white", width=2.5)),
                showlegend=False, hoverinfo="skip",
            ))
            _apply_lixinger_layout(
                fig, height=210,
                margin_t=8, margin_b=22, margin_l=42, margin_r=14,
                y_range=[y_lo, y_hi],
            )
            st.plotly_chart(fig, width="stretch")

        # 全宽底部卡片(脱离左右两列,从最左侧贯穿到最右)
        # 一行展开:数值 + 日期 + 档位 + 含义 + intro 介绍
        meaning = ind.get("meaning", "")
        intro = ind.get("intro", "")
        meaning_html = (
            "<span style='color:#555;margin-left:14px;padding-left:14px;"
            "border-left:1px solid #d6dde5'>"
            f"💡 <b>含义:</b>{meaning}</span>"
        ) if meaning else ""
        intro_html = (
            "<div style='margin-top:6px;padding-top:6px;border-top:1px dashed #e2e6ea;"
            "font-size:13px;color:#555;line-height:1.55'>"
            f"📘 <b>是什么:</b>{intro}</div>"
        ) if intro else ""
        st.markdown(
            "<div style='margin-top:-6px;padding:10px 14px;background:#f8f9fa;"
            "border-left:3px solid #0d6efd;border-radius:3px'>"
            # 第一行:数值 / 日期 / 档位 / 含义 一字排开
            "<div style='display:flex;align-items:center;gap:14px;flex-wrap:wrap'>"
            f"<span style='font-size:22px;font-weight:700;color:#0d6efd;line-height:1'>"
            f"{ind['fmt'].format(cur)}</span>"
            f"<span style='font-size:12px;color:#888'>{cur_date}</span>"
            f"<span style='font-size:14px;font-weight:700;padding-left:14px;"
            f"border-left:1px solid #d6dde5'>{cur_emoji} {cur_label}</span>"
            f"{meaning_html}"
            "</div>"
            # 第二行:📘 是什么(M2 长介绍)
            f"{intro_html}"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div style='border-bottom:1px dashed #e0e0e0;margin:14px 0 18px'></div>",
                    unsafe_allow_html=True)

    if not have_any:
        st.info("📭 macro 表暂无数据。先跑:`.venv/bin/python .tools/db/fetch_macro.py`")
