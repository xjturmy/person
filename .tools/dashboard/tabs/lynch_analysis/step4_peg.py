"""Lynch step 4 — PEG 估值(成长合理性)。"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from datetime import timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
DB_PATH = ROOT / "data" / "preson.duckdb"
COMPANIES_DIR = ROOT / "02_companies"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from masters.lynch.classifier import (  # noqa: E402
    CLASS_META, LYNCH_DIM_SCHEMA, ClassificationResult,
    QuarterlyContinuity,
    classify_ticker, compute_lynch_dims, load_metrics_from_db, overall_lynch,
    quarterly_continuity,
)

from ._helpers import (
    GUARDRAIL_THRESHOLDS, PEG_BY_TYPE, LAYER3_INDUSTRY_NA,
    _quarterly_continuity_cached, _qc_from_dict,
    _section_banner, _badge_pill, _confidence_color,
    _classify_cached, _metrics_cached, _deduct_metrics,
    _company_category, _quarterly_yoy,
    _fmt_pct, _fmt_num,
    derive_key_indicators, derive_story,
    _render_type_editor, _editable_list,
)


def _step_4_peg_valuation(ticker: str, m: dict, cls_id_used: str) -> None:
    """④ PEG 估值 — 类型决定是否适用。

    口径校准(2026-05-06,与理杏仁页面对齐):
      PEG = PE-TTM ÷ (净利润 3y CAGR × 100)
      其中 3y CAGR 使用**倒数第二份年报作 end**(滞后一年保稳定),
      避免最新年报刚披露带来的 PEG 跳变。
      美的实测对齐:14.0 / 10.50% = **1.33** ✅(与理杏仁页面一致)
    """
    _section_banner("④", "📐", "PEG 估值(成长合理性核心)",
                    "PEG = PE-TTM ÷ (净利润 3y CAGR × 100) · 理杏仁同口径",
                    color="#6f42c1")

    peg_cfg = PEG_BY_TYPE.get(cls_id_used, PEG_BY_TYPE["stalwart"])

    if not peg_cfg["applicable"]:
        st.info(f"💡 **{CLASS_META[cls_id_used][0]}** {peg_cfg['note']}", icon="ℹ️")
        # 替代方案
        if cls_id_used == "slow_grower":
            dy = m.get("dividend_yield")
            pe = m.get("pe_ttm")
            st.markdown("**替代估值口径**")
            c1, c2 = st.columns(2)
            if dy is not None:
                rating = "🟢 高股息" if dy >= 0.04 else "🟡 中性" if dy >= 0.025 else "🔴 偏低"
                c1.metric("股息率", f"{dy*100:.2f}%", delta=rating)
            if pe is not None:
                rating = "🟢" if pe < 12 else "🟡" if pe < 18 else "🔴"
                c2.metric("PE-TTM", f"{pe:.1f}",
                          delta=f"{rating} 缓慢增长 PE 上限 12")
        elif cls_id_used == "cyclical":
            pb = m.get("pb")
            st.markdown("**替代估值口径(周期股看 PB)**")
            if pb is not None:
                rating = "🟢 周期底部" if pb < 1 else "🟡 中性" if pb < 2 else "🔴 周期顶部"
                st.metric("PB", f"{pb:.2f}", delta=rating)
        elif cls_id_used == "asset_play":
            cash_mc = m.get("cash_to_market_cap")
            st.markdown("**替代估值口径(看 NAV/现金)**")
            if cash_mc is not None:
                st.metric("现金/市值", f"{cash_mc*100:.1f}%")
            else:
                st.caption("(现金/市值数据未装配)")
        return

    pe = m.get("pe_ttm")
    np_yoy = m.get("np_ttm_yoy")           # 百分数 33.0 = 33%
    peg_lx = m.get("peg_lixinger")          # 直接复用 peg_curve 算好的 PEG

    if pe is None or np_yoy is None or np_yoy <= 0:
        # 兜底退化:净利 3y CAGR 不可用时退到营收 CAGR(明确告知)
        cagr_3y = m.get("rev_cagr_3y")
        cagr_5y = m.get("rev_cagr_5y")
        cagr = cagr_3y or cagr_5y
        if pe is None or cagr is None or cagr <= 0:
            st.warning(
                "⚠️ PE-TTM 或增长率数据缺失,无法算 PEG。"
                "(理杏仁口径需净利润 3y CAGR > 0)",
                icon="⚠️",
            )
            return
        peg = pe / (cagr * 100)
        st.warning(
            f"⚠️ 净利润 3y CAGR 不可用({np_yoy or 0:.1f}%) — "
            f"退化用营收 5y CAGR={cagr*100:.1f}% 兜底,"
            f"**与理杏仁页面会有差异**。",
            icon="⚠️",
        )
        growth_label = f"营收 CAGR({'3y' if cagr_3y else '5y'},兜底)"
        growth_value_str = f"{cagr*100:.1f}%"
    else:
        peg = peg_lx if peg_lx is not None else pe / (np_yoy / 100 * 100)
        growth_label = "净利润 3y CAGR"
        growth_value_str = f"{np_yoy:+.1f}%"

    target = peg_cfg["target"]

    # 顶部大数字
    c1, c2, c3 = st.columns(3)
    c1.metric("PE-TTM", f"{pe:.1f}")
    c2.metric(growth_label, growth_value_str,
              help="理杏仁标准:净利润 3 年 CAGR(年报数据,end=倒数第二份年报)")
    peg_rating = (
        "🟢🟢 极度低估" if peg < 0.5 else
        "🟢 合理偏低" if peg < 1.0 else
        "🟡 略贵" if peg < 1.5 else
        "🔴 高估" if peg < 2.0 else
        "🔴🔴 严重高估"
    )
    c3.metric("PEG", f"{peg:.2f}", delta=peg_rating,
              delta_color="normal" if peg < target else "inverse",
              help="PEG = PE-TTM ÷ (净利润 3y CAGR × 100) · 理杏仁同口径")

    # 评级表
    st.markdown("**📊 PEG 评级表**")
    rating_data = [
        {"PEG 区间": "< 0.5", "评级": "🟢🟢 极度低估", "建议": "重仓买入"},
        {"PEG 区间": "0.5 - 1.0", "评级": "🟢 合理偏低", "建议": "买入"},
        {"PEG 区间": "1.0 - 1.5", "评级": "🟡 略贵", "建议": "观望"},
        {"PEG 区间": "1.5 - 2.0", "评级": "🔴 高估", "建议": "减仓"},
        {"PEG 区间": "> 2.0", "评级": "🔴🔴 严重高估", "建议": "清仓"},
    ]
    rating_df = pd.DataFrame(rating_data)

    # 高亮当前所在档
    def _highlight_current(row):
        rng = row["PEG 区间"]
        is_current = (
            (rng == "< 0.5" and peg < 0.5) or
            (rng == "0.5 - 1.0" and 0.5 <= peg < 1.0) or
            (rng == "1.0 - 1.5" and 1.0 <= peg < 1.5) or
            (rng == "1.5 - 2.0" and 1.5 <= peg < 2.0) or
            (rng == "> 2.0" and peg >= 2.0)
        )
        return ["background-color:#d4edda; font-weight:700" if is_current else ""] * len(row)

    styled = rating_df.style.apply(_highlight_current, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # 结论
    if peg < target:
        st.success(f"✅ PEG {peg:.2f} ≤ 目标 {target} — 估值合理", icon="✅")
    elif peg < target * 1.3:
        st.warning(f"⚠️ PEG {peg:.2f} 略高于 {target} 目标 — 需观望", icon="⚠️")
    else:
        st.error(f"🔴 PEG {peg:.2f} 远超 {target} 目标 — 估值过高", icon="🚨")

