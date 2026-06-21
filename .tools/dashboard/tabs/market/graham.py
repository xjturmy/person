"""市场 Tab · ② 格雷厄姆指数(差值法,理杏仁口径)+ 历史参照。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ._helpers import (
    GRAHAM_HISTORY,
    GRAHAM_WINDOWS,
    _graham_rating,
    _load_graham_diff_series,
    _load_macro_latest,
)


def _section_graham_index(macro_path: str, macro_mtime: float) -> None:
    """格雷厄姆指数(差值法,理杏仁口径):

       graham_diff = (1 / A股全指 PE-TTM 市值加权) − 10Y 国债收益率
                   = 盈利收益率 − 无风险利率(单位 %)
    """
    hs = _load_macro_latest(macro_path, "A_FULL_PE", macro_mtime)
    yld = _load_macro_latest(macro_path, "10Y_YIELD", macro_mtime)

    if not (hs and yld) or hs["value"] <= 0 or yld["value"] <= 0:
        st.caption("(A_FULL_PE 或 10Y_YIELD 缺数据。先跑 "
                   "`.venv/bin/python .tools/db/fetch_macro.py --only A_FULL_PE,10Y_YIELD`)")
        return

    pe = hs["value"]
    bond_pct = yld["value"]                    # 已是 %
    ey_pct = (1.0 / pe) * 100.0
    graham_diff = ey_pct - bond_pct
    label, badge, eq_lo, eq_hi = _graham_rating(graham_diff)

    diff_series_full = _load_graham_diff_series(macro_path, macro_mtime)

    with st.container(border=True):
        # ─── 顶部 3 列:核心指标卡(紧凑 2×2)+ 阈值红绿灯(含当前位置) ───
        c1, c2, c3 = st.columns([1.1, 1.1, 2.2])

        # 两列 metric 容器与 c3 红绿灯做等高对齐:c3 = 1 标题 + 4 档位 ≈ 175px
        STAT_COL_HEIGHT = 175

        def _stat(label: str, value: str, tip: str = "") -> str:
            tip_attr = f' title="{tip}"' if tip else ""
            return (
                f"<div style='flex:1;display:flex;flex-direction:column;"
                f"justify-content:center'>"
                f"<div style='font-size:13px;color:#888;font-weight:400'{tip_attr}>"
                f"{label}</div>"
                f"<div style='font-size:28px;font-weight:600;"
                f"line-height:1.15;margin-top:4px'>{value}</div>"
                f"</div>"
            )

        def _stat_col(*cards: str) -> str:
            return (
                f"<div style='min-height:{STAT_COL_HEIGHT}px;display:flex;"
                f"flex-direction:column;justify-content:space-between;gap:6px'>"
                f"{''.join(cards)}</div>"
            )

        with c1:
            st.markdown(
                _stat_col(
                    _stat("A 股全指 PE-TTM", f"{pe:.2f}",
                          f"最新 {hs['date']} · 中证全指 000985 市值加权 · 理杏仁 API"),
                    _stat("盈利收益率 1/PE", f"{ey_pct:.2f}%"),
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _stat_col(
                    _stat("10Y 国债收益率", f"{bond_pct:.2f}%", f"最新 {yld['date']}"),
                    _stat("股债差(格雷厄姆)", f"{graham_diff:+.2f}%",
                          "盈利收益率 − 国债收益率 · 与理杏仁制图同口径"),
                ),
                unsafe_allow_html=True,
            )
        with c3:
            # 4 档显示(≥6 极度吸引合并入 ≥4 高度吸引)— UI 简化,判定仍走原 5 档
            BANDS_UI = [
                ("🟢", "≥4%   高度吸引",  4.0),
                ("🟡", "2-4%  吸引",       2.0),
                ("🟠", "0-2%  中性",       0.0),
                ("🔴", "&lt;0%   不吸引", -99.0),
            ]
            cur_idx = next(
                (i for i, (_b, _t, lo) in enumerate(BANDS_UI) if graham_diff >= lo),
                len(BANDS_UI) - 1,
            )
            rows_html = [
                "<div style='font-weight:600;font-size:14px'>"
                "📐 阈值红绿灯(差值法,单位 %)</div>"
            ]
            for i, (b, t, _lo) in enumerate(BANDS_UI):
                if i == cur_idx:
                    rows_html.append(
                        f"<div style='font-weight:600;color:#111'>"
                        f"{b} {t}  ← 当前 <b>{graham_diff:+.2f}%</b> "
                        f"· 建议权益 <b>{eq_lo}-{eq_hi}%</b></div>"
                    )
                else:
                    rows_html.append(
                        f"<div style='color:#555'>{b} {t}</div>"
                    )
            st.markdown(
                f"<div style='min-height:{STAT_COL_HEIGHT}px;display:flex;"
                f"flex-direction:column;justify-content:space-between;gap:4px'>"
                f"{''.join(rows_html)}</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            # 注入局部 CSS:压缩本容器内 element-container 默认间距
            "<style>"
            "div[data-testid='stVerticalBlock'] > div[data-testid='element-container']"
            ":has(.js-plotly-plot){margin-top:-4px !important;margin-bottom:-8px !important}"
            "</style>"
            "<div style='border-top:1px dashed #ccc;margin:6px 0 2px'></div>"
            "<div style='font-size:13px;color:#444;margin-bottom:0'>"
            "<b>📈 历史走势 + 当前位置</b> "
            "<span style='color:#888;font-size:11px;margin-left:8px'>"
            "选时间窗口 → 看当前差值在该区间的相对位置(色带=阈值红绿灯)</span></div>",
            unsafe_allow_html=True,
        )

        # ─── 时间窗口选择 ───
        win_labels = [w[0] for w in GRAHAM_WINDOWS]
        sel_label = st.radio(
            "时间窗口", win_labels, index=2, horizontal=True,
            label_visibility="collapsed", key="graham_window",
        )
        win_days = dict(GRAHAM_WINDOWS)[sel_label]

        # ─── 截取窗口内的差值时序 + 算分位 ───
        if diff_series_full.empty:
            st.caption("(股债差时序数据缺失)")
            return
        if win_days is None:
            df_win = diff_series_full
        else:
            cutoff = pd.Timestamp(date.today() - timedelta(days=win_days))
            df_win = diff_series_full[diff_series_full["date"] >= cutoff].copy()
        if df_win.empty or len(df_win) < 5:
            st.caption(f"(窗口 {sel_label} 数据不足,样本 {len(df_win)} 条)")
            return

        rank_pct = float((df_win["diff"] <= graham_diff).sum()) / len(df_win)
        win_min = float(df_win["diff"].min())
        win_max = float(df_win["diff"].max())
        win_med = float(df_win["diff"].median())

        # ─── 窗口统计小条 ───
        s1, s2, s3, s4 = st.columns(4)
        s1.metric(f"{sel_label}内当前分位", f"{rank_pct*100:.1f}%",
                  help=f"在 {len(df_win)} 个样本中,有 {rank_pct*100:.1f}% 的样本 ≤ 当前 {graham_diff:+.2f}%")
        s2.metric(f"{sel_label}内中位数", f"{win_med:+.2f}%")
        s3.metric(f"{sel_label}内最低", f"{win_min:+.2f}%")
        s4.metric(f"{sel_label}内最高", f"{win_max:+.2f}%")

        # ─── 主图:理杏仁风格(浅色实心色带 + 单一折线 + 当前点) ───
        BAND_EDGES = [-15, 0, 2, 4, 6, 15]   # 阈值法五档边界
        # 浅色实心色带(opacity=1)— 不与折线/散点产生颜色叠加
        BAND_FILLS = ["#fef5f4", "#fff7f0", "#fffdf2", "#f2fcf6", "#e6faee"]
        BAND_LABEL_COLORS = ["#c0392b", "#d35400", "#b58a00", "#27ae60", "#1e8449"]
        BAND_LABELS = ["不吸引", "中性", "吸引", "高度吸引", "极度吸引"]
        FONT_FAMILY = ('"PingFang SC","Helvetica Neue","Microsoft YaHei",'
                       '"Hiragino Sans GB","Noto Sans CJK SC",sans-serif')

        # 是否叠加历史散点(默认关闭,保持图面清爽)
        show_hist = st.checkbox("叠加 HS300 历史关键时点(◇)", value=False,
                                key="graham_show_hist")
        hist_pts: list[dict] = []
        if show_hist:
            x_min = df_win["date"].min()
            x_max = df_win["date"].max()
            for h in GRAHAM_HISTORY:
                d = pd.to_datetime(h["date"] + "-15", errors="coerce")
                if pd.notna(d) and x_min <= d <= x_max:
                    hist_pts.append({"date": d, "diff": h["diff"], "note": h["note"]})

        data_min = min(win_min, graham_diff)
        data_max = max(win_max, graham_diff)
        if hist_pts:
            data_min = min(data_min, min(p["diff"] for p in hist_pts))
            data_max = max(data_max, max(p["diff"] for p in hist_pts))
        data_range = max(data_max - data_min, 0.5)
        pad = max(data_range * 0.08, 0.25)
        y_lo = data_min - pad
        y_hi = data_max + pad

        fig = go.Figure()
        # 浅色实心色带 — opacity 拉满,纯背景作用
        for (lo, hi, fill, lab, lab_color) in zip(
            BAND_EDGES[:-1], BAND_EDGES[1:], BAND_FILLS, BAND_LABELS, BAND_LABEL_COLORS,
        ):
            seg_lo = max(lo, y_lo)
            seg_hi = min(hi, y_hi)
            if seg_hi <= seg_lo:
                continue
            fig.add_hrect(y0=seg_lo, y1=seg_hi, fillcolor=fill,
                          opacity=1.0, line_width=0, layer="below")
            mid_y = (seg_lo + seg_hi) / 2
            fig.add_annotation(
                xref="paper", yref="y", x=0.995, y=mid_y,
                text=f"<b>{lab}</b>",
                showarrow=False, xanchor="right", yanchor="middle",
                font=dict(size=11, color=lab_color, family=FONT_FAMILY),
            )

        # 折线 — 加粗到 2.8px,样条平滑
        fig.add_trace(go.Scatter(
            x=df_win["date"], y=df_win["diff"],
            mode="lines", name="股债差",
            line=dict(color="#1f4e9c", width=2.8, shape="spline", smoothing=0.6),
            hovertemplate="%{x|%Y-%m-%d}<br>股债差: %{y:.2f}%<extra></extra>",
        ))

        # 历史散点(可选,默认关闭)
        if hist_pts:
            fig.add_trace(go.Scatter(
                x=[p["date"] for p in hist_pts],
                y=[p["diff"] for p in hist_pts],
                mode="markers+text",
                text=[p["note"][:2] for p in hist_pts],
                textposition="top center",
                textfont=dict(size=14, family=FONT_FAMILY),
                marker=dict(size=11, color="#fff",
                            line=dict(color="#555", width=1.5),
                            symbol="diamond"),
                name="历史时点",
                hovertemplate=("%{x|%Y-%m}<br>股债差: %{y:.2f}%<br>"
                               "<extra>HS300 历史对照</extra>"),
                showlegend=False,
            ))

        # 当前值 — 单一蓝圆 + 数字气泡(无水平线、无中位线)
        cur_x = df_win["date"].iloc[-1]
        fig.add_trace(go.Scatter(
            x=[cur_x], y=[graham_diff],
            mode="markers",
            marker=dict(size=14, color="#1f4e9c",
                        line=dict(color="white", width=2.5),
                        symbol="circle"),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_annotation(
            x=cur_x, y=graham_diff,
            text=f"<b>{graham_diff:+.2f}%</b>",
            showarrow=True, arrowhead=0, arrowwidth=1.2, arrowcolor="#1f4e9c",
            ax=-36, ay=-26,
            font=dict(size=13, color="#1f4e9c", family=FONT_FAMILY),
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#1f4e9c", borderwidth=1, borderpad=3,
        )

        fig.update_layout(
            height=340, margin=dict(t=8, b=30, l=55, r=20),
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(
                range=[y_lo, y_hi], fixedrange=False,
                title=dict(text="股债差 (%)",
                           font=dict(size=13, color="#333", family=FONT_FAMILY),
                           standoff=6),
                tickfont=dict(size=12, color="#333", family=FONT_FAMILY),
                showgrid=True, gridcolor="#f0f0f0", gridwidth=1,
                zeroline=False, showline=False,
                ticks="",
            ),
            xaxis=dict(
                title="",
                tickfont=dict(size=12, color="#333", family=FONT_FAMILY),
                showgrid=False,            # 关闭 vertical grid
                zeroline=False, showline=False,
                ticks="outside", tickcolor="#ddd", ticklen=4,
            ),
            hovermode="x unified", showlegend=False,
            font=dict(family=FONT_FAMILY, color="#333"),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            f"<div style='margin-top:-4px;font-size:12px;color:#666;"
            f"line-height:1.5;font-family:{FONT_FAMILY}'>"
            f"💡 当前 <b>{graham_diff:+.2f}%</b> 在 <b>{sel_label}内</b> 处于 "
            f"<b>{rank_pct*100:.1f}% 分位</b> · 评级 <b>{badge} {label}</b> · "
            "色带=阈值档位 / 蓝点=当前</div>",
            unsafe_allow_html=True,
        )

        # ─── 沪深 300 历史标记点(知识库归档) ───
        with st.expander("📜 沪深 300 历史参照点(知识库手工归档,辅助对照)", expanded=False):
            hist_df = pd.DataFrame(GRAHAM_HISTORY)
            hist_df["diff"] = hist_df["diff"].round(2)
            hist_df.columns = ["日期", "HS300 PE", "10Y 国债 %", "股债差 %", "实际走势"]
            st.dataframe(hist_df, hide_index=True, use_container_width=True)
            st.caption("数据源:01_knowledge/02_权益类动态调整/04_格雷厄姆指数.md")
