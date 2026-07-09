"""段 1 Hero:SWS Hero banner + 投资判断预览。"""
from __future__ import annotations

from html import escape

try:
    import streamlit as st
    if st.runtime.exists():
        _cache_data = st.cache_data
    else:
        raise RuntimeError("no streamlit runtime")
except Exception:
    def _cache_data(*a, **kw):
        def deco(fn):
            return fn
        return deco


from ui.invest_ui import (
    inject_invest_ui_css,
)
from .investment_judgement import build_preview_judgement, render_preview

_OVERVIEW_COMPACT_CSS = """
<style>
.sws-hero {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-left: 4px solid #94A3B8;
    border-radius: 8px;
    box-shadow: none;
    margin: 0 0 8px;
    padding: 12px 14px;
    color: #111827;
}
.sws-hero-row {
    align-items: center;
}
.sws-hero-name {
    color: #111827;
    font-family: var(--preson-font-report, "Songti SC", "STSong", serif);
    font-size: 22px;
    font-weight: 700;
}
.sws-hero-ticker {
    background: #F3F4F6;
    color: #374151;
}
.sws-hero-cat {
    color: #6B7280;
    font-size: 12px;
    margin-top: 4px;
}
.sws-hero-score-label {
    color: #6B7280;
    font-size: 10px;
}
.sws-hero-score-num {
    color: #111827;
    font-size: 28px;
}
.sws-hero-score-suffix {
    color: #6B7280;
    font-size: 13px;
}
.sws-hero-score-pill {
    background: #F3F4F6;
    color: #374151;
    padding: 2px 9px;
}
.company-locator-badge {
    margin: 6px 0 8px !important;
    padding: 6px 9px !important;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 6px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    height: 28px;
    padding-left: 2px;
    padding-right: 2px;
}
[data-testid="stTabs"] [data-baseweb="tab"] p {
    font-size: 13px;
}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {
    padding-top: 4px;
}
[data-testid="stTabs"] [data-testid="stVerticalBlock"] {
    gap: 0.25rem;
}
</style>
"""

def render() -> None:
    # ─── 段 1:公司识别条 + 投资判断预览 ────────────────────────
    st.markdown(_SWS_CSS, unsafe_allow_html=True)
    st.markdown(_OVERVIEW_COMPACT_CSS, unsafe_allow_html=True)
    inject_invest_ui_css()
    folder_to_ticker_home = _folder_to_ticker(DB_MTIME)
    ticker = folder_to_ticker_home.get(selected, "")
    # ─── PE 分位口径(统一为 10y 全周期) ────────────────────────────
    # 主显示固定 10y(权威口径,与 graham/lynch/决策中心/screener 完全一致;
    # 与理杏仁内置「PE-TTM_分位点」差异 < 1pp,实测对齐)。
    # 5y/3y/1y 仅作"近 N 年"对照参考,显示在 expander 内,不影响主评分。
    home_window = "10y"
    st.session_state["home_window"] = home_window
    _latest_period = latest_financial_period(DB_MTIME, ticker)
    _annual_year = latest_annual_year(DB_MTIME, ticker)

    score_dict = _company_score(ticker, home_window, DB_MTIME)
    if score_dict is None:
        st.error(f"⚠️ 无法加载评分(ticker={ticker or '未映射'})")
    else:
        ov = score_dict["overall"] or 0.0
        ov_label, _ov_color = _sws_score_pill(ov)

        # ─── 公司识别条(评分退到辅助位,判断条优先)──────────────
        st.markdown(
            f'<div class="sws-hero">'
            f'  <div class="sws-hero-row">'
            f'    <div>'
            f'      <h1 class="sws-hero-name">{score_dict["name"]}'
            f'<span class="sws-hero-ticker">{score_dict["ticker"]}</span></h1>'
            f'      <div class="sws-hero-cat">'
            f'{(score_dict["category"] or "通用").upper()} · 分位窗口 {home_window}</div>'
            f'    </div>'
            f'    <div class="sws-hero-score-block">'
            f'      <div class="sws-hero-score-label">★ Snowflake 综合评分</div>'
            f'      <div><span class="sws-hero-score-num">{ov:.0f}</span>'
            f'<span class="sws-hero-score-suffix">/100</span></div>'
            f'      <div class="sws-hero-score-pill">{ov_label}</div>'
            f'    </div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        try:
            _judgement = build_preview_judgement(ticker, score_dict, _latest_period)
            render_preview(_judgement)
        except Exception as _judge_exc:
            st.caption(f"(当前投资判断预览渲染失败:{_judge_exc})")

    write_context(selected)
