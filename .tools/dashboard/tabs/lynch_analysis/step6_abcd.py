"""Lynch step 6 — ABCD 评级与矩阵决策。"""
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


def _step_6_abcd_evaluation(ticker: str, m: dict, cls_id_used: str) -> None:
    """⑥ ABCD/12345 综合评级 — 文档同源:02_彼得林奇投资法/。

    三类适用(stalwart / fast_grower / cyclical),其它类型显示提示。
    评分流程:
      1. 自动分(财报数据驱动)+ 主观分(slider)+ 调整因子(checkbox)
      2. 公司质量 → A/B/C/D / 价格吸引力 → 1/2/3/4/5
      3. 4×5 矩阵决策(全力出击 / 减仓 / 卖出 / ...)
      4. 若有次类型(双特征),按主/次权重加权综合分,矩阵决策用综合分
    """
    _section_banner("⑥", "🎯", "ABCD/12345 综合评级",
                    "公司质量 × 价格吸引力 → 4×5 矩阵决策",
                    color="#0EA5E9")

    try:
        from masters.lynch.scorer import score_abcd, applicable, MATRIX
    except Exception as e:
        st.error(f"ABCD 评分引擎加载失败:{e}")
        return

    # ─── 读取主次拆分(① 类型编辑器写到 session_state)──────────────────
    secondary = st.session_state.get(f"lynch_secondary_{ticker}", "")
    weight = st.session_state.get(f"lynch_weight_{ticker}", 100) if secondary else 100

    if not applicable(cls_id_used):
        cls_label = CLASS_META.get(cls_id_used, ("?",))[0]
        # 若主类型不适用但次类型适用 → 退化用次类型
        if secondary and applicable(secondary):
            st.info(
                f"💡 主类型 **{cls_label}** 暂未实现 ABCD,改用次类型 "
                f"**{CLASS_META[secondary][0]}** 评分(权重 100%)"
            )
            cls_id_used = secondary
            secondary = ""
            weight = 100
        else:
            st.info(
                f"💡 当前类型 **{cls_label}** 暂未实现 ABCD/12345 双维评估。\n\n"
                "已支持:🛡️ 稳健增长 / 🚀 快速增长 / 🔄 周期型 三类\n\n"
                "请回到 ① 公司分类调整为以上三类之一,或参考 "
                "[02_彼得林奇投资法/01_六类公司分类法.md](../../../01_knowledge/03_投资策略与选股/02_彼得林奇投资法/01_六类公司分类法.md) "
                "手动评估。"
            )
            return

    # ─── session 持久化 manual 输入(主类型自己一份,次类型一份)──────
    manual_key = f"lynch_abcd_manual_{ticker}_{cls_id_used}"
    manual = st.session_state.get(manual_key, {})

    # 预跑主类型
    result = score_abcd(ticker, m, cls_id_used, manual=manual)
    if result is None:
        st.error("评分计算失败")
        return

    # 主次拆分提示
    if secondary and applicable(secondary):
        sec_meta = CLASS_META[secondary]
        st.success(
            f"🎯 **双特征综合评分**:主 {result.cls_emoji} {result.cls_name} "
            f"({weight}%) + 次 {sec_meta[1]} {sec_meta[0]} ({100-weight}%) — "
            f"下方两套打分独立,综合分 = 主×{weight}% + 次×{100-weight}%",
            icon="🎯",
        )
    elif secondary:
        st.caption(f"次类型 {CLASS_META[secondary][0]} 暂未实现 ABCD,综合评分仅用主类型")
        secondary = ""
        weight = 100

    st.markdown(
        f"📚 **方法论**:[02_{result.cls_name}_ABCD评估.md]"
        f"(../../../01_knowledge/03_投资策略与选股/02_彼得林奇投资法/) · "
        f"📐 评分细则同源,改文档不改代码"
    )
    st.divider()

    # ═══ 主类型评分 ═══
    if secondary:
        st.markdown(f"## 🥇 主类型评分 · {result.cls_emoji} {result.cls_name} ({weight}%)")

    st.markdown("### 🏛️ 公司质量评分(好公司)")
    new_manual_company = _render_score_panel(
        result.company_items, result.company_adjusts,
        prefix=f"{manual_key}_company", manual=manual,
    )

    st.markdown("### 💰 价格吸引力评分(好价格)")
    new_manual_price = _render_score_panel(
        result.price_items, result.price_adjusts,
        prefix=f"{manual_key}_price", manual=manual,
    )

    merged = {**manual, **new_manual_company, **new_manual_price}
    if merged != manual:
        st.session_state[manual_key] = merged
        result = score_abcd(ticker, m, cls_id_used, manual=merged)

    # ═══ 次类型评分(若双特征)═══
    sec_result = None
    if secondary:
        st.divider()
        sec_meta = CLASS_META[secondary]
        st.markdown(f"## 🥈 次类型评分 · {sec_meta[1]} {sec_meta[0]} ({100-weight}%)")
        sec_manual_key = f"lynch_abcd_manual_{ticker}_{secondary}"
        sec_manual = st.session_state.get(sec_manual_key, {})
        sec_result = score_abcd(ticker, m, secondary, manual=sec_manual)
        if sec_result is None:
            st.error("次类型评分失败")
        else:
            st.markdown("### 🏛️ 公司质量评分(次类型口径)")
            sec_new_company = _render_score_panel(
                sec_result.company_items, sec_result.company_adjusts,
                prefix=f"{sec_manual_key}_company", manual=sec_manual,
            )
            st.markdown("### 💰 价格吸引力评分(次类型口径)")
            sec_new_price = _render_score_panel(
                sec_result.price_items, sec_result.price_adjusts,
                prefix=f"{sec_manual_key}_price", manual=sec_manual,
            )
            sec_merged = {**sec_manual, **sec_new_company, **sec_new_price}
            if sec_merged != sec_manual:
                st.session_state[sec_manual_key] = sec_merged
                sec_result = score_abcd(ticker, m, secondary, manual=sec_merged)

    st.divider()

    # ═══ 矩阵决策(综合分 / 单一分)═══
    final_result = _combine_results(result, sec_result, weight) if sec_result else result
    if sec_result:
        st.markdown(f"### 🎯 综合定位({result.cls_name} {weight}% + {sec_result.cls_name} {100-weight}%)")
    _render_matrix_decision(final_result)


def _combine_results(primary, secondary, weight: int):
    """主+次类型加权合成最终 AbcdResult。weight = 主类型权重(50-95)。"""
    from masters.lynch.scorer import AbcdResult, MATRIX

    w1, w2 = weight / 100.0, (100 - weight) / 100.0
    # 加权综合分(分数项 + 调整因子合成的最终分)
    company_combined = primary.company_final_score * w1 + secondary.company_final_score * w2
    price_combined = primary.price_final_score * w1 + secondary.price_final_score * w2

    # 重新算等级 + 决策
    from masters.lynch.scorer import _grade_company, _grade_price
    c_grade = _grade_company(company_combined)
    p_grade = _grade_price(price_combined)
    decision, color = MATRIX[c_grade][p_grade]

    return AbcdResult(
        cls_id=f"{primary.cls_id}+{secondary.cls_id}",
        cls_name=f"{primary.cls_name}{weight}% + {secondary.cls_name}{100-weight}%",
        company_items=primary.company_items + secondary.company_items,
        company_adjusts=primary.company_adjusts + secondary.company_adjusts,
        company_base_score=company_combined,
        company_adjust_total=0,
        company_final_score=company_combined,
        company_grade=c_grade,
        company_max=110,
        price_items=primary.price_items + secondary.price_items,
        price_adjusts=primary.price_adjusts + secondary.price_adjusts,
        price_base_score=price_combined,
        price_adjust_total=0,
        price_final_score=price_combined,
        price_grade=p_grade,
        price_max=110,
        matrix_decision=decision,
        matrix_color=color,
    )


def _render_score_panel(items, adjusts, *, prefix: str, manual: dict) -> dict:
    """渲染评分项 + 调整因子。返回新 manual 输入 dict。"""
    new_manual: dict = {}

    # 评分项
    for it in items:
        c1, c2, c3 = st.columns([3, 1.2, 4], gap="small")
        with c1:
            tag = ("🤖 自动" if it.source == "auto"
                   else "✍️ 主观" if it.source == "manual"
                   else "❓ 待填" if it.source == "missing"
                   else "")
            st.markdown(
                f"**{it.label}** "
                f"<span style='color:#9CA3AF;font-size:11px'>{tag}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            color = ("#16A34A" if it.score >= it.max_score * 0.8
                     else "#EAB308" if it.score >= it.max_score * 0.5
                     else "#DC2626" if it.source != "missing"
                     else "#9CA3AF")
            st.markdown(
                f"<div style='text-align:center;font-size:18px;font-weight:700;"
                f"color:{color}'>{it.score:.0f}<span style='color:#9CA3AF;"
                f"font-weight:400;font-size:12px'>/{it.max_score:.0f}</span></div>",
                unsafe_allow_html=True,
            )
        with c3:
            if it.source in ("manual", "missing"):
                # slider 让用户输入
                cur_v = manual.get(it.key)
                v = st.slider(
                    f"_slider_{it.key}",
                    min_value=0, max_value=int(it.max_score),
                    value=int(cur_v) if cur_v is not None else 0,
                    step=1,
                    key=f"{prefix}_{it.key}",
                    label_visibility="collapsed",
                )
                new_manual[it.key] = v
                st.caption(it.detail.replace("⚠️ 需手动评分:", "").replace("用户评分", "已确认"))
            else:
                st.caption(it.detail)

    # 调整因子
    if adjusts:
        st.markdown("**📌 调整因子**(勾选触发的)")
        cols = st.columns(2)
        for i, adj in enumerate(adjusts):
            with cols[i % 2]:
                # auto 触发的(如 ROE ≥20% 自动判定)直接显示
                key_id = f"adj_{adj.key}"
                if any(p in adj.detail for p in ["当前 ROE", "PEG"]) and adj.triggered:
                    # 自动判断触发的
                    badge = "🟢" if adj.polarity == "bonus" else "🔴"
                    st.markdown(
                        f"{badge} **{adj.label}** {adj.delta:+d} 分 "
                        f"<span style='color:#9CA3AF;font-size:11px'>(自动触发)</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(adj.detail)
                else:
                    # 用户 checkbox
                    cur = bool(manual.get(key_id, False))
                    new_v = st.checkbox(
                        f"{adj.label} ({adj.delta:+d})",
                        value=cur,
                        key=f"{prefix}_{key_id}",
                        help=adj.detail,
                    )
                    new_manual[key_id] = new_v

    # 小计
    total_items = sum(it.score for it in items)
    total_adj = sum(a.delta for a in adjusts)
    final = total_items + total_adj
    adj_color = "#16A34A" if total_adj >= 0 else "#DC2626"
    st.markdown(
        f"<div style='background:#F3F4F6;padding:6px 12px;border-radius:6px;"
        f"margin:8px 0;font-size:13px'>"
        f"基础分 <b>{total_items:.0f}</b> / "
        f"{sum(it.max_score for it in items):.0f} · "
        f"调整 <b style='color:{adj_color}'>{total_adj:+d}</b> · "
        f"<b style='font-size:16px'>最终 {final:.0f}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    return new_manual


def _render_matrix_decision(result) -> None:
    """渲染 ABCD/12345 + 4×5 矩阵决策 banner。"""
    from masters.lynch.scorer import MATRIX

    # 大数字徽章 — 三列:公司质量 / 价格吸引力 / 矩阵决策
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        grade_color = {"A": "#16A34A", "B": "#65A30D",
                        "C": "#EAB308", "D": "#DC2626"}[result.company_grade]
        st.markdown(
            f"<div style='text-align:center;background:white;border:2px solid {grade_color};"
            f"border-radius:14px;padding:12px;'>"
            f"<div style='font-size:11px;color:#6B7280;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>公司质量</div>"
            f"<div style='font-size:48px;font-weight:800;color:{grade_color};"
            f"line-height:1.1'>{result.company_grade}</div>"
            f"<div style='font-size:13px;color:#374151'>"
            f"{result.company_final_score:.0f}<span style='color:#9CA3AF'>/110</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        grade_color = {1: "#16A34A", 2: "#65A30D",
                        3: "#EAB308", 4: "#F97316", 5: "#DC2626"}[result.price_grade]
        st.markdown(
            f"<div style='text-align:center;background:white;border:2px solid {grade_color};"
            f"border-radius:14px;padding:12px;'>"
            f"<div style='font-size:11px;color:#6B7280;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>价格吸引力</div>"
            f"<div style='font-size:48px;font-weight:800;color:{grade_color};"
            f"line-height:1.1'>{result.price_grade}</div>"
            f"<div style='font-size:13px;color:#374151'>"
            f"{result.price_final_score:.0f}<span style='color:#9CA3AF'>/110</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div style='background:linear-gradient(90deg,{result.matrix_color}22 0%,white 100%);"
            f"border-left:5px solid {result.matrix_color};"
            f"padding:12px 16px;border-radius:8px;height:100%;display:flex;"
            f"flex-direction:column;justify-content:center'>"
            f"<div style='font-size:11px;color:#6B7280;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>矩阵决策</div>"
            f"<div style='font-size:18px;font-weight:700;color:{result.matrix_color};"
            f"margin-top:4px;line-height:1.3'>{result.matrix_decision}</div>"
            f"<div style='font-size:11px;color:#6B7280;margin-top:4px'>"
            f"{result.cls_name}{' · 文档定义'} · 公司 {result.company_grade} 级 × 价格 {result.price_grade} 级"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    # 4×5 矩阵热力图(本格高亮)
    with st.expander("📊 完整 4×5 决策矩阵(当前位置高亮)", expanded=False):
        cur_g, cur_p = result.company_grade, result.price_grade
        rows_html = ""
        for grade in ["A", "B", "C", "D"]:
            cells = "".join(
                _matrix_cell_html(grade, p, cur_g == grade and cur_p == p)
                for p in [1, 2, 3, 4, 5]
            )
            rows_html += (
                f"<tr><td style='font-weight:700;padding:8px;background:#F9FAFB;"
                f"border:1px solid #E5E7EB;width:80px'>{grade} 级</td>{cells}</tr>"
            )
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:12px'>"
            f"<tr><th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'></th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>1 级<br>低估</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>2 级</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>3 级<br>合理</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>4 级</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>5 级<br>高估</th>"
            f"</tr>{rows_html}</table>",
            unsafe_allow_html=True,
        )


def _matrix_cell_html(grade: str, price: int, highlight: bool) -> str:
    from masters.lynch.scorer import MATRIX
    decision, color = MATRIX[grade][price]
    if highlight:
        return (
            f"<td style='padding:8px;border:3px solid {color};background:{color}33;"
            f"font-weight:700;color:{color};text-align:center;font-size:11px'>"
            f"📍 当前<br>{decision}</td>"
        )
    return (
        f"<td style='padding:8px;border:1px solid #E5E7EB;"
        f"text-align:center;font-size:11px;color:{color}'>{decision}</td>"
    )

