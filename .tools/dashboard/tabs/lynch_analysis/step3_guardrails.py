"""Lynch step 3 — 财务护栏(高增长不烧钱)。"""
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
    guardrail_thresholds_for,
    _quarterly_continuity_cached, _qc_from_dict,
    _section_banner, _badge_pill, _confidence_color,
    _classify_cached, _metrics_cached, _deduct_metrics,
    _company_category, _quarterly_yoy,
    _fmt_pct, _fmt_num,
    derive_key_indicators, derive_story,
    _render_type_editor, _editable_list,
)


def _step_3_financial_guardrails(ticker: str, m: dict, cls_id_used: str) -> None:
    """③ 财务护栏 — 类型驱动阈值。"""
    _section_banner("③", "🛡️", "财务护栏(高增长不烧钱)",
                    f"林奇原话:'快速增长公司的资产负债率超过 40%,我会立刻卖出'",
                    color="#f0ad4e")

    # 金融业(银行/保险/证券)短路:林奇财务护栏不适用 — 高负债率是行业特性
    industry = (m.get("industry_sw_l1") or "").strip()
    FINANCIAL_INDUSTRIES = {"银行", "非银金融", "保险", "证券"}
    if industry in FINANCIAL_INDUSTRIES:
        st.info(
            f"📌 金融业「{industry}」**不适用林奇财务护栏** — "
            f"负债率 {(m.get('debt_ratio') or 0)*100:.1f}% 是行业特性(银行靠存款、保险靠保费),"
            f"不能套用快速/稳健增长股的负债率阈值。\n\n"
            f"建议改看:**净息差/不良率/ROE/拨备覆盖率**(银行) · **内含价值/赔付率**(保险)"
        )
        return

    th = guardrail_thresholds_for(cls_id_used, industry)
    st.caption(f"📌 当前阈值口径:**{th['label']}**")

    rows: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    edge_count = 0
    na_count = 0

    def _verdict(passed: bool | None, edge: bool = False) -> str:
        nonlocal pass_count, fail_count, edge_count, na_count
        if passed is None:
            na_count += 1
            return "⚪"
        if passed:
            pass_count += 1
            return "✅"
        if edge:
            edge_count += 1
            return "⚠️"
        fail_count += 1
        return "🔴"

    # 1. 资产负债率(越低越好)
    debt = m.get("debt_ratio")
    if debt is not None:
        max_th = th["debt_ratio_max"]
        passed = debt <= max_th
        edge = (not passed) and (debt <= max_th + 0.05)
        rows.append({
            "指标": "资产负债率",
            "当前值": f"{debt*100:.1f}%",
            "林奇阈值": f"≤ {max_th*100:.0f}%",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "资产负债率", "当前值": "—",
                     "林奇阈值": f"≤ {th['debt_ratio_max']*100:.0f}%",
                     "状态": _verdict(None)})

    # 2. 流动比率(越高越好)
    cr = m.get("current_ratio")
    if cr is not None:
        min_th = th["current_ratio_min"]
        passed = cr >= min_th
        edge = (not passed) and (cr >= max(1.0, min_th - 0.2))
        rows.append({
            "指标": "流动比率",
            "当前值": f"{cr:.2f}",
            "林奇阈值": f"≥ {min_th:.1f}",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "流动比率", "当前值": "—",
                     "林奇阈值": f"≥ {th['current_ratio_min']:.1f}",
                     "状态": _verdict(None)})

    # 3. 经营现金流/净利润(越高越好;> 1 表示利润有现金支撑)
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is not None:
        min_th = th["cfo_to_ni_min"]
        passed = cfo_ni >= min_th
        edge = (not passed) and (cfo_ni >= min_th - 0.15)
        rows.append({
            "指标": "经营现金流/净利润",
            "当前值": f"{cfo_ni:.2f}",
            "林奇阈值": f"≥ {min_th:.2f}",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "经营现金流/净利润", "当前值": "—",
                     "林奇阈值": f"≥ {th['cfo_to_ni_min']:.2f}",
                     "状态": _verdict(None)})

    # 4. 库存周转天数(越低越好)
    inv_d = m.get("inventory_turnover_days")
    inv_max = th.get("inv_days_max")
    if inv_d is not None:
        if inv_max is None:
            rows.append({"指标": "库存周转天数",
                         "当前值": f"{inv_d:.0f} 天",
                         "林奇阈值": "—(此类型不卡)",
                         "状态": "—"})  # 不计入
        else:
            passed = inv_d <= inv_max
            edge = (not passed) and (inv_d <= inv_max * 1.15)
            rows.append({
                "指标": "库存周转天数",
                "当前值": f"{inv_d:.0f} 天",
                "林奇阈值": f"≤ {inv_max} 天",
                "状态": _verdict(passed, edge),
            })
    else:
        rows.append({"指标": "库存周转天数", "当前值": "—",
                     "林奇阈值": f"≤ {inv_max} 天" if inv_max else "—",
                     "状态": _verdict(None)})

    # 5. 应收账款周转天数(越低越好)
    ar_d = m.get("receivables_turnover_days")
    ar_max = th.get("ar_days_max")
    if ar_d is not None and ar_max is not None:
        passed = ar_d <= ar_max
        edge = (not passed) and (ar_d <= ar_max * 1.2)
        rows.append({
            "指标": "应收账款周转天数",
            "当前值": f"{ar_d:.0f} 天",
            "林奇阈值": f"≤ {ar_max} 天",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "应收账款周转天数", "当前值": "—",
                     "林奇阈值": f"≤ {ar_max} 天" if ar_max else "—",
                     "状态": _verdict(None)})

    df = pd.DataFrame(rows)

    def _style_status(v):
        if v == "✅": return "background-color:#d4edda; font-weight:600"
        if v == "⚠️": return "background-color:#fff3cd; font-weight:600"
        if v == "🔴": return "background-color:#f8d7da; font-weight:600"
        return ""

    styler = df.style.map(_style_status, subset=["状态"])
    st.dataframe(styler, width="stretch", hide_index=True)

    # 整体结论
    total_evaluated = pass_count + fail_count + edge_count
    if total_evaluated == 0:
        st.info("ℹ️ 5 项护栏数据全缺失,无法判断", icon="ℹ️")
    elif fail_count == 0 and edge_count == 0:
        st.success(
            f"✅ 财务护栏 {pass_count}/{total_evaluated} 项全部通过 — 健康"
            + (f" · {na_count} 项数据缺" if na_count else ""),
            icon="✅",
        )
    elif fail_count == 0:
        st.warning(
            f"⚠️ {pass_count}/{total_evaluated} 通过 + {edge_count} 边缘 — 需关注",
            icon="⚠️",
        )
    else:
        st.error(
            f"🔴 {pass_count} 通过 / {edge_count} 边缘 / {fail_count} 不合格 — 护栏失守,警示信号",
            icon="🚨",
        )

    # 数据来源说明
    st.caption(
        "📊 数据来源:`资产负债率/流动比率`(safety) · `CFO/NI`(cashflow) · "
        "`存货周转/应收周转天数`(独立 turnover.duckdb,sina 财报派生)"
    )
