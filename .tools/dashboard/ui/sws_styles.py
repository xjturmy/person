"""SWS(Simply Wall St)风格视觉语言 + 雷达 + 维度卡片 helper。

- 视觉常量:SWS_DIM_KEYS / SWS_COLORS / SWS_ICONS / SWS_PRIMARY / SWS_BORDER 等
- 函数:_sws_score_pill / _radar_chart / _sws_dim_card_html
- 全局 CSS 字符串:_SWS_CSS

由 app.py `from ui.sws_styles import *` 引入,自动通过 globals() 传给 tabs/company.py。
"""
from __future__ import annotations

import plotly.graph_objects as go

import ui.score_card as sc


# ───── Simply Wall St 视觉语言:调色 + 图标 + Pill ─────────────────────
SWS_DIM_KEYS = ["valuation", "profitability", "growth", "cashflow", "safety"]
SWS_COLORS = {
    "valuation":     "#00C9A7",  # Teal — 估值
    "profitability": "#FFB800",  # Gold — 盈利
    "growth":        "#B968F2",  # Purple — 成长
    "cashflow":      "#5B7CFA",  # Blue — 现金流
    "safety":        "#FF6B6B",  # Coral — 安全
}
SWS_ICONS = {
    "valuation":     "💎",
    "profitability": "📈",
    "growth":        "🚀",
    "cashflow":      "💧",
    "safety":        "🛡️",
}
SWS_PRIMARY = "#6366F1"      # Indigo — 主色
SWS_PRIMARY_2 = "#8B5CF6"    # Purple — 渐变
SWS_TEXT = "#111827"
SWS_MUTED = "#6B7280"
SWS_BORDER = "#E5E7EB"
SWS_BG_SOFT = "#F9FAFB"


def _sws_score_pill(score: float | None) -> tuple[str, str]:
    """根据综合分返回 (中文标签, 主题色)。"""
    if score is None:
        return ("无数据", "#9CA3AF")
    if score >= 75:
        return ("优秀", "#10B981")
    if score >= 60:
        return ("良好", "#3B82F6")
    if score >= 45:
        return ("一般", "#F59E0B")
    return ("较差", "#EF4444")


def _radar_chart(dims: dict, name: str) -> go.Figure:
    """SWS Snowflake:每轴 5 色 marker + 渐变填充。"""
    labels = [sc.DIM_LABEL.get(k, k) for k in SWS_DIM_KEYS]
    scores = [(dims[k]["score"] if dims[k]["score"] is not None else 0) for k in SWS_DIM_KEYS]
    colors = [SWS_COLORS[k] for k in SWS_DIM_KEYS]

    labels_closed = labels + [labels[0]]
    scores_closed = scores + [scores[0]]
    colors_closed = colors + [colors[0]]

    fig = go.Figure(go.Scatterpolar(
        r=scores_closed,
        theta=labels_closed,
        mode="lines+markers",
        line=dict(color=SWS_PRIMARY, width=2.2),
        fill="toself",
        fillcolor="rgba(99,102,241,0.14)",
        marker=dict(size=14, color=colors_closed,
                    line=dict(color="white", width=2)),
        hovertemplate="<b>%{theta}</b><br>%{r:.0f}/100<extra></extra>",
        showlegend=False,
        name=name,
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[20, 40, 60, 80, 100],
                ticktext=["", "", "", "", ""],
                gridcolor="#EEF1F5",
                linecolor="#EEF1F5",
                tickfont=dict(size=10, color="#9CA3AF"),
            ),
            angularaxis=dict(
                gridcolor="#F3F4F6",
                linecolor=SWS_BORDER,
                tickfont=dict(size=14, color=SWS_TEXT, family="Inter, -apple-system, sans-serif"),
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=420,
        margin=dict(l=60, r=60, t=24, b=24),
        showlegend=False,
    )
    return fig


def _sws_dim_card_html(key: str, dim: dict) -> str:
    """一张 SWS 风格的维度详细卡(图标+渐进条+pill)。"""
    color = SWS_COLORS[key]
    icon = SWS_ICONS[key]
    score = dim["score"]
    score_str = f"{score:.0f}" if score is not None else "—"
    pill_label, pill_color = _sws_score_pill(score)
    fill_pct = score if score is not None else 0
    label = dim["label"]
    note = dim["note"] or ""
    return (
        f'<div class="sws-dim-card">'
        f'  <div class="sws-dim-row">'
        f'    <div class="sws-dim-left">'
        f'      <div class="sws-dim-icon" style="background:{color}1A;color:{color};">{icon}</div>'
        f'      <div>'
        f'        <div class="sws-dim-name">{label}</div>'
        f'        <div class="sws-dim-note">{note}</div>'
        f'      </div>'
        f'    </div>'
        f'    <div class="sws-dim-right">'
        f'      <div class="sws-dim-score">{score_str}<span class="sws-dim-score-suffix">/100</span></div>'
        f'      <div class="sws-pill" style="background:{pill_color}1A;color:{pill_color};">{pill_label}</div>'
        f'    </div>'
        f'  </div>'
        f'  <div class="sws-progress"><div class="sws-progress-fill" '
        f'style="background:{color};width:{fill_pct}%;"></div></div>'
        f'</div>'
    )


_SWS_CSS = """
<style>
.sws-hero {
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 60%, #EC4899 120%);
    border-radius: 18px;
    padding: 30px 36px;
    margin: 4px 0 22px 0;
    color: white;
    box-shadow: 0 18px 38px -18px rgba(99,102,241,0.55);
    font-family: -apple-system, "Inter", "PingFang SC", sans-serif;
}
.sws-hero-row { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; flex-wrap:wrap; }
.sws-hero-name { font-size: 30px; font-weight: 700; line-height: 1.15; margin: 0; }
.sws-hero-ticker {
    display:inline-block; background: rgba(255,255,255,0.22);
    padding: 3px 12px; border-radius: 999px;
    font-size: 12px; font-weight: 500; margin-left: 10px; vertical-align: middle;
    letter-spacing: 0.04em;
}
.sws-hero-cat { color: rgba(255,255,255,0.82); font-size: 13px; margin-top: 6px; }
.sws-hero-score-block { text-align: right; line-height: 1; }
.sws-hero-score-label { font-size: 11px; opacity: 0.85; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 4px; }
.sws-hero-score-num { font-size: 56px; font-weight: 800; }
.sws-hero-score-suffix { font-size: 20px; opacity: 0.7; font-weight: 500; margin-left: 2px; }
.sws-hero-score-pill {
    display: inline-block;
    background: rgba(255,255,255,0.25);
    padding: 4px 14px; border-radius: 999px;
    font-size: 12px; font-weight: 600; margin-top: 4px;
}
.sws-card {
    background: white; border: 1px solid #E5E7EB;
    border-radius: 14px; padding: 22px 24px; margin: 0 0 14px 0;
    font-family: -apple-system, "Inter", "PingFang SC", sans-serif;
}
.sws-summary-title { font-size: 11px; color: #6B7280; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 14px; }
.sws-summary-line {
    padding: 11px 0;
    border-bottom: 1px solid #F3F4F6;
    display: flex; align-items: center; gap: 10px;
    font-size: 14px;
}
.sws-summary-line:last-child { border-bottom: none; }
.sws-summary-icon { font-size: 18px; }
.sws-summary-name { flex: 1; color: #111827; font-weight: 500; }
.sws-summary-note { color: #6B7280; font-size: 12px; max-width: 55%; text-align: right; }
.sws-summary-score { font-weight: 700; min-width: 36px; text-align: right; }
.sws-section-header {
    font-size: 13px; font-weight: 700; color: #6B7280;
    margin: 28px 0 12px 0; text-transform: uppercase; letter-spacing: 0.1em;
}
.sws-dim-card {
    background: white; border: 1px solid #E5E7EB;
    border-radius: 14px; padding: 18px 22px; margin-bottom: 12px;
    transition: transform 0.15s, box-shadow 0.15s;
    font-family: -apple-system, "Inter", "PingFang SC", sans-serif;
}
.sws-dim-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px -10px rgba(0,0,0,0.08);
}
.sws-dim-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 12px; }
.sws-dim-left { display:flex; align-items:center; gap:14px; min-width: 0; }
.sws-dim-icon {
    width: 42px; height: 42px; border-radius: 11px;
    display:flex; align-items:center; justify-content:center;
    font-size: 20px; flex-shrink: 0;
}
.sws-dim-name { font-size: 15px; font-weight: 600; color: #111827; }
.sws-dim-note { font-size: 12px; color: #6B7280; margin-top: 2px; }
.sws-dim-right { display:flex; align-items: center; gap: 12px; flex-shrink: 0; }
.sws-dim-score { font-size: 26px; font-weight: 700; color: #111827; line-height: 1; }
.sws-dim-score-suffix { font-size: 13px; color: #9CA3AF; font-weight: 500; margin-left: 2px; }
.sws-pill {
    font-size: 11px; font-weight: 600;
    padding: 4px 12px; border-radius: 999px;
    letter-spacing: 0.02em; white-space: nowrap;
}
.sws-progress {
    background: #F3F4F6; height: 6px;
    border-radius: 3px; overflow: hidden;
}
.sws-progress-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
.sws-mini-cap { font-size: 12px; color: #9CA3AF; margin-top: 12px; line-height: 1.6; }

/* ─── v2.7 持仓档案卡 ──────────────────────────────────────────── */
.position-card {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border: 1.5px solid #d97706;
    border-radius: 12px;
    padding: 14px 20px;
    margin: 4px 0 18px 0;
    font-family: -apple-system, "Inter", "PingFang SC", sans-serif;
    box-shadow: 0 6px 18px -10px rgba(217,119,6,0.45);
}
.position-card-title {
    font-size: 13px;
    font-weight: 700;
    color: #78350f;
    letter-spacing: 0.02em;
    margin-bottom: 8px;
}
.position-card-school {
    display: inline-block;
    background: rgba(255,255,255,0.55);
    color: #92400e;
    padding: 1px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    margin-left: 4px;
    letter-spacing: 0.04em;
}
.position-card-row {
    font-size: 14px;
    color: #451a03;
    line-height: 1.65;
    margin: 4px 0;
}
.position-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
}
</style>
"""
