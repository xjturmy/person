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
        primary_emoji = CLASS_META.get(result.cls_id, ("", "", ""))[1]
        st.success(
            f"🎯 **双特征综合评分**:主 {primary_emoji} {result.cls_name} "
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
        primary_emoji = CLASS_META.get(result.cls_id, ("", "", ""))[1]
        st.markdown(f"## 🥇 主类型评分 · {primary_emoji} {result.cls_name} ({weight}%)")

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


def _fmt_price(value: float | None) -> str:
    return f"¥{value:.2f}" if value is not None else "—"


def _range_label(low: float | None, high: float | None) -> str:
    if low is None and high is None:
        return "—"
    if low is None:
        return f"≤ {_fmt_price(high)}"
    if high is None:
        return f"> {_fmt_price(low)}"
    return f"{_fmt_price(low)} - {_fmt_price(high)}"


@st.cache_data(ttl=600, show_spinner=False)
def _lynch_price_inputs_cached(ticker: str, mtime: float) -> dict[str, Any]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        def latest(table: str, metric: str) -> tuple[float | None, Any]:
            row = con.execute(
                f"SELECT value, date FROM {table} "
                f"WHERE ticker=? AND metric=? AND value IS NOT NULL "
                f"ORDER BY date DESC LIMIT 1",
                [ticker, metric],
            ).fetchone()
            return (float(row[0]), row[1]) if row else (None, None)

        pe, pe_date = latest("valuation", "PE-TTM")
        pb, pb_date = latest("valuation", "PB")
        price, price_date = latest("valuation", "股价(港币)")
        if price is None:
            price, price_date = latest("valuation", "股价(元)")
        mcap, mcap_date = latest("valuation", "市值(元)")
        if mcap is None:
            mcap, mcap_date = latest("valuation", "市值(港币)")
        eps, eps_date = latest("growth", "基本每股收益")
        ni, ni_date = latest("growth", "归属于母公司普通股股东的净利润")

        market_price, market_price_date = (None, None)
        if len(str(ticker)) == 5:  # 港股 prices.close 是未复权收盘价;A 股表内 close 多为复权价,不能混用。
            row = con.execute(
                "SELECT close, date FROM prices "
                "WHERE ticker=? AND close IS NOT NULL "
                "ORDER BY date DESC LIMIT 1",
                [ticker],
            ).fetchone()
            if row:
                market_price, market_price_date = float(row[0]), row[1]
    finally:
        con.close()

    current = None
    anchor_price = None
    if price is not None and price > 0:
        current = price
        anchor_price = price
    elif mcap is not None and eps is not None and ni is not None and eps > 0 and ni > 0:
        current = mcap / (ni / eps)
        anchor_price = current

    price_source = "valuation"
    if market_price is not None and market_price > 0:
        current = market_price
        price_source = "prices"

    price_ratio = 1.0
    if current is not None and anchor_price is not None and anchor_price > 0:
        price_ratio = current / anchor_price
        if pe is not None:
            pe *= price_ratio
        if pb is not None:
            pb *= price_ratio

    return {
        "current": current,
        "pe": pe,
        "pb": pb,
        "as_of": market_price_date if price_source == "prices" else price_date or pe_date or pb_date or mcap_date or eps_date or ni_date,
        "valuation_as_of": price_date or pe_date or pb_date or mcap_date or eps_date or ni_date,
        "price_source": price_source,
        "price_ratio": price_ratio,
    }


@st.cache_data(ttl=600, show_spinner=False)
def _valuation_quantiles_cached(ticker: str, mtime: float) -> dict[str, dict[str, float]]:
    cutoff = (_date_cls.today() - timedelta(days=365 * 10)).isoformat()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    out: dict[str, dict[str, float]] = {}
    try:
        for metric in ("PE-TTM", "PB", "股息率"):
            df = con.execute(
                """
                SELECT value FROM valuation
                WHERE ticker=? AND metric=? AND value IS NOT NULL AND date>=?
                ORDER BY date
                """,
                [ticker, metric, cutoff],
            ).fetchdf()
            if df.empty:
                continue
            s = pd.to_numeric(df["value"], errors="coerce").dropna()
            if s.empty:
                continue
            out[metric] = {
                f"q{int(q * 100)}": float(s.quantile(q))
                for q in (0.1, 0.2, 0.5, 0.7)
            }
    finally:
        con.close()
    return out


def _peg_price_at(current: float, current_peg: float, target_peg: float) -> float:
    return current * target_peg / current_peg


def _pb_price_at(current: float, current_pb: float, target_pb: float) -> float:
    return current * target_pb / current_pb


def _pe_price_at(current: float, current_pe: float, target_pe: float) -> float:
    return current * target_pe / current_pe


def _yield_price_at(current: float, current_yield: float, target_yield: float) -> float:
    return current * current_yield / target_yield


def _as_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100 if value > 1 else value


def _metric_items(
    current: float,
    as_of: Any,
    key_label: str,
    key_value: str,
    key_help: str,
    buy_line: float,
    sell_line: float,
) -> list[tuple[str, str, str]]:
    return [
        ("当前价", _fmt_price(current), f"数据日:{as_of or '—'}"),
        (key_label, key_value, key_help),
        ("买入观察线", _fmt_price(buy_line), "低于该价格进入林奇方案买入观察区"),
        ("减仓/卖出线", _fmt_price(sell_line), "高于该价格需重新评估故事与估值"),
    ]


def _render_mature_value_price_zones(
    ticker: str,
    current: float,
    pe: float | None,
    pb: float | None,
    div_yield: float | None,
    as_of: Any,
    current_peg: float | None,
    np3: float | None,
    reason: str,
) -> None:
    db_mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0
    quantiles = _valuation_quantiles_cached(ticker, db_mtime)

    metrics = [
        ("当前价", _fmt_price(current), f"数据日:{as_of or '—'}"),
        ("理杏仁 PEG", "—" if current_peg is None else f"{current_peg:.2f}", "PEG 失真时不用于倒推价格"),
        ("净利 3y CAGR", "—" if np3 is None else f"{np3:.2f}%", "低增速成熟股不适合用 PEG 定价"),
        ("当前股息率", "—" if div_yield is None else f"{div_yield*100:.2f}%", "成熟现金流型辅助锚"),
    ]

    rows: list[dict[str, str]] = []
    pe_q = quantiles.get("PE-TTM") or {}
    if pe and pe > 0 and pe_q:
        for label, key in (("PE 低位(10%)", "q10"), ("PE 低位(20%)", "q20"),
                           ("PE 中位", "q50"), ("PE 偏高(70%)", "q70")):
            target = pe_q.get(key)
            if target is not None:
                rows.append({
                    "锚": label,
                    "目标倍数/收益率": f"{target:.2f}x",
                    "对应价格": _fmt_price(_pe_price_at(current, pe, target)),
                    "用途": "成熟现金流型主参考",
                })

    pb_q = quantiles.get("PB") or {}
    if pb and pb > 0 and pb_q:
        for label, key in (("PB 低位(10%)", "q10"), ("PB 低位(20%)", "q20"),
                           ("PB 中位", "q50")):
            target = pb_q.get(key)
            if target is not None:
                rows.append({
                    "锚": label,
                    "目标倍数/收益率": f"{target:.2f}x",
                    "对应价格": _fmt_price(_pb_price_at(current, pb, target)),
                    "用途": "资产/ROE 辅助校验",
                })

    if div_yield and div_yield > 0:
        for label, target in (("股息率 4%", 0.04), ("股息率 3.5%", 0.035),
                              ("股息率 3%", 0.03)):
            rows.append({
                "锚": label,
                "目标倍数/收益率": f"{target*100:.1f}%",
                "对应价格": _fmt_price(_yield_price_at(current, div_yield, target)),
                "用途": "收息回报辅助校验",
            })

    st.warning(f"{reason} 已切换为成熟现金流/历史估值口径。", icon="⚠️")
    c1, c2, c3, c4 = st.columns(4)
    for col, item in zip((c1, c2, c3, c4), metrics):
        col.metric(item[0], item[1], help=item[2])
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption(
            "PEG 失真时,合理价格用 PE/PB 十年分位与股息率交叉验证。"
            "通常低位分位对应观察/分批区,中位附近对应合理持有区。"
        )
    else:
        st.info("历史估值或股息率数据不足,暂不能形成成熟现金流价格锚。")


def _render_lynch_price_zones(ticker: str, cls_id: str, m: dict) -> None:
    """Render Lynch-method buy/hold/sell price zones below the final decision."""
    db_mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0
    try:
        inputs = _lynch_price_inputs_cached(ticker, db_mtime)
    except Exception as exc:  # noqa: BLE001 - price zones should not break the decision tab
        st.warning(f"林奇价格区间暂不可用:{exc}")
        return

    current = inputs.get("current")
    pe = inputs.get("pe") or m.get("pe_ttm")
    pb = inputs.get("pb") or m.get("pb")
    as_of = inputs.get("as_of")
    price_ratio = inputs.get("price_ratio") or 1.0
    price_source = inputs.get("price_source") or "valuation"

    st.markdown("### 💵 林奇价格区间")
    if current is None:
        st.info("当前价基础数据不足,暂不能形成林奇买入 / 卖出价格区间。")
        return
    try:
        stale_days = (_date_cls.today() - as_of).days if as_of else None
    except Exception:
        stale_days = None
    if stale_days is not None and stale_days > 7:
        st.warning(
            f"价格数据日为 {as_of},距今天 {_date_cls.today()} 已 {stale_days} 天;"
            "当前价格区间仅作历史估值参考,建议先更新行情/估值数据。",
            icon="⚠️",
        )
    elif price_source == "prices":
        st.caption(f"当前价读取最新行情收盘价,数据日:{as_of}。")

    rows: list[dict[str, str]] = []
    metrics: list[tuple[str, str, str]] = [("当前价", _fmt_price(current), f"数据日:{as_of or '—'}")]
    caption = ""

    if PEG_BY_TYPE.get(cls_id, {}).get("applicable"):
        current_peg = m.get("peg_lixinger")
        if current_peg is not None:
            current_peg *= price_ratio
        if current_peg is None or current_peg <= 0:
            st.info("理杏仁 PEG 数据不足,暂不能按林奇 PEG 形成价格区间。")
            return
        if current_peg <= 0:
            st.info("当前 PEG 无法计算,暂不能形成价格区间。")
            return

        if cls_id == "fast_grower":
            safe_peg, buy_peg, hold_peg, sell_peg = 1.0, 1.5, 2.0, 2.0
            scheme = "快速增长型:PEG ≤ 1.0 安全,≤ 1.5 可买,> 2.0 需要减仓/卖出"
        else:
            safe_peg, buy_peg, hold_peg, sell_peg = 0.8, 1.2, 1.8, 1.8
            scheme = "稳健增长型:PEG ≤ 0.8 安全,0.8-1.2 分批,> 1.8 需要减仓/卖出"

        np3 = m.get("np_ttm_yoy")
        div_yield = _as_ratio(m.get("dividend_yield"))
        if (np3 is not None and np3 < 8) or current_peg > 3:
            if np3 is not None and np3 < 5:
                reason = f"净利润 3y CAGR 仅 {np3:.2f}%,PEG 分母过小,倒推价格会失真。"
            elif np3 is not None and np3 < 8:
                reason = f"净利润 3y CAGR {np3:.2f}% 偏低,PEG 只适合作辅助观察。"
            else:
                reason = f"理杏仁 PEG {current_peg:.2f} 过高,直接倒推价格会失真。"
            _render_mature_value_price_zones(
                ticker, current, pe, pb, div_yield, as_of, current_peg, np3, reason
            )
            return

        safe_price = _peg_price_at(current, current_peg, safe_peg)
        buy_price = _peg_price_at(current, current_peg, buy_peg)
        hold_price = _peg_price_at(current, current_peg, hold_peg)

        metrics.extend([
            ("当前 PEG", f"{current_peg:.2f}", "理杏仁 PEG 口径"),
            ("安全买入线", _fmt_price(safe_price), f"PEG {safe_peg:.1f}"),
            ("减仓/卖出线", _fmt_price(sell_price := hold_price), f"PEG {sell_peg:.1f}"),
        ])
        rows = [
            {"区间": "安全买入", "价格范围": _range_label(None, safe_price), "动作": "林奇好公司遇到好价格,可重点建仓"},
            {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "价格仍匹配成长,按仓位计划买入"},
            {"区间": "合理持有", "价格范围": _range_label(buy_price, hold_price), "动作": "等待故事兑现,不追高加仓"},
            {"区间": "减仓/卖出", "价格范围": _range_label(sell_price, None), "动作": "除非成长率上修,否则优先降风险"},
        ]
        caption = (
            f"{scheme}。本区间只按理杏仁 PEG 口径换算:价格变动会等比例改变 PE 和 PEG。"
        )

    elif cls_id == "slow_grower":
        div_yield = _as_ratio(m.get("dividend_yield"))
        if div_yield is not None and div_yield > 0:
            safe_price = _yield_price_at(current, div_yield, 0.05)
            buy_price = _yield_price_at(current, div_yield, 0.04)
            hold_price = _yield_price_at(current, div_yield, 0.03)
            metrics = _metric_items(
                current, as_of,
                "当前股息率", f"{div_yield*100:.2f}%", "缓慢增长型以股息率作为主要价格锚",
                buy_price, hold_price,
            )
            rows = [
                {"区间": "高股息买入", "价格范围": _range_label(None, safe_price), "动作": "股息率 ≥ 5%,偏防御型建仓区"},
                {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "股息率 4%-5%,可按现金流配置"},
                {"区间": "收益持有", "价格范围": _range_label(buy_price, hold_price), "动作": "股息率 3%-4%,以收息和稳定性为主"},
                {"区间": "减仓/卖出", "价格范围": _range_label(hold_price, None), "动作": "股息率 < 3%,缓慢增长股吸引力下降"},
            ]
            caption = "缓慢增长型不看 PEG。本区间只按林奇收息型口径,用股息率反推价格。"
        elif pe is not None and pe > 0:
            safe_price = _pe_price_at(current, pe, 10)
            buy_price = _pe_price_at(current, pe, 12)
            hold_price = _pe_price_at(current, pe, 18)
            metrics = _metric_items(
                current, as_of,
                "当前 PE", f"{pe:.1f}", "股息率缺失时退化为缓慢增长股 PE 上限",
                buy_price, hold_price,
            )
            rows = [
                {"区间": "低 PE 买入", "价格范围": _range_label(None, safe_price), "动作": "PE ≤ 10,防御性较强"},
                {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "PE 10-12,可小步配置"},
                {"区间": "合理持有", "价格范围": _range_label(buy_price, hold_price), "动作": "PE 12-18,主要看股息和稳定性"},
                {"区间": "减仓/卖出", "价格范围": _range_label(hold_price, None), "动作": "PE > 18,缓慢增长股性价比不足"},
            ]
            caption = "股息率缺失,临时退化为林奇缓慢增长股 PE 口径。"
        else:
            st.info("缓慢增长型需要股息率或 PE-TTM 才能形成价格区间。")
            return

    elif cls_id == "cyclical":
        if pb is None or pb <= 0:
            st.info("周期型公司需要 PB 数据来判断周期位置,当前数据不足。")
            return
        safe_price = _pb_price_at(current, pb, 1.0)
        buy_price = _pb_price_at(current, pb, 1.5)
        hold_price = _pb_price_at(current, pb, 2.0)
        metrics.extend([
            ("当前 PB", f"{pb:.2f}", "周期型按 PB 判断周期位置"),
            ("周期底部线", _fmt_price(safe_price), "PB 1.0"),
            ("周期顶部线", _fmt_price(hold_price), "PB 2.0"),
        ])
        rows = [
            {"区间": "周期底部买入", "价格范围": _range_label(None, safe_price), "动作": "PB 低位,结合行业景气反转建仓"},
            {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "确认产品价格/利润拐点后买入"},
            {"区间": "景气持有", "价格范围": _range_label(buy_price, hold_price), "动作": "跟踪库存、价格和盈利弹性"},
            {"区间": "周期顶部卖出", "价格范围": _range_label(hold_price, None), "动作": "PB 高位时不恋战,优先兑现"},
        ]
        caption = "周期型不使用 PEG。本区间只按林奇周期股口径,用 PB 作为周期位置代理。"

    elif cls_id == "turnaround":
        if pb is not None and pb > 0:
            safe_price = _pb_price_at(current, pb, 0.8)
            buy_price = _pb_price_at(current, pb, 1.2)
            hold_price = _pb_price_at(current, pb, 2.0)
            metrics = _metric_items(
                current, as_of,
                "当前 PB", f"{pb:.2f}", "困境反转型以资产折价和破产风险作为价格锚",
                buy_price, hold_price,
            )
            rows = [
                {"区间": "深度反转买入", "价格范围": _range_label(None, safe_price), "动作": "PB ≤ 0.8,但必须确认生存风险可控"},
                {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "PB 0.8-1.2,等待经营拐点确认"},
                {"区间": "反转持有", "价格范围": _range_label(buy_price, hold_price), "动作": "PB 1.2-2.0,看利润修复兑现"},
                {"区间": "兑现/卖出", "价格范围": _range_label(hold_price, None), "动作": "PB > 2.0,反转预期大多已反映"},
            ]
            caption = "困境反转型不用 PEG。本区间只按林奇反转股口径,用 PB 折价作为安全边际代理。"
        elif pe is not None and pe > 0:
            safe_price = _pe_price_at(current, pe, 8)
            buy_price = _pe_price_at(current, pe, 12)
            hold_price = _pe_price_at(current, pe, 20)
            metrics = _metric_items(
                current, as_of,
                "当前 PE", f"{pe:.1f}", "PB 缺失时退化为反转股 PE 重估线",
                buy_price, hold_price,
            )
            rows = [
                {"区间": "反转买入", "价格范围": _range_label(None, safe_price), "动作": "低 PE 且经营拐点明确才考虑"},
                {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "PE 8-12,小仓位验证"},
                {"区间": "反转持有", "价格范围": _range_label(buy_price, hold_price), "动作": "PE 12-20,看利润修复持续性"},
                {"区间": "兑现/卖出", "价格范围": _range_label(hold_price, None), "动作": "PE > 20,不再便宜"},
            ]
            caption = "PB 缺失,临时退化为林奇困境反转 PE 重估口径。"
        else:
            st.info("困境反转型需要 PB 或 PE-TTM 才能形成价格区间。")
            return

    elif cls_id == "asset_play":
        if pb is not None and pb > 0:
            safe_price = _pb_price_at(current, pb, 0.8)
            buy_price = _pb_price_at(current, pb, 1.0)
            hold_price = _pb_price_at(current, pb, 1.3)
            metrics = _metric_items(
                current, as_of,
                "当前 PB", f"{pb:.2f}", "资产隐蔽型以账面资产折价作为价格锚",
                buy_price, hold_price,
            )
            rows = [
                {"区间": "资产折价买入", "价格范围": _range_label(None, safe_price), "动作": "PB ≤ 0.8,隐蔽资产安全边际较足"},
                {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "PB 0.8-1.0,等待催化重估"},
                {"区间": "重估持有", "价格范围": _range_label(buy_price, hold_price), "动作": "PB 1.0-1.3,观察资产释放或重估进展"},
                {"区间": "兑现/卖出", "价格范围": _range_label(hold_price, None), "动作": "PB > 1.3,资产折价优势减弱"},
            ]
            caption = "资产隐蔽型不使用 PEG。本区间只按林奇资产股口径,用 PB/NAV 折价代理安全边际。"
        else:
            cash_mc = _as_ratio(m.get("cash_to_market_cap"))
            if cash_mc is None or cash_mc <= 0:
                st.info("资产隐蔽型需要 PB 或现金/市值数据才有价格锚。")
                return
            safe_price = _yield_price_at(current, cash_mc, 0.40)
            buy_price = _yield_price_at(current, cash_mc, 0.30)
            hold_price = _yield_price_at(current, cash_mc, 0.20)
            metrics = _metric_items(
                current, as_of,
                "现金/市值", f"{cash_mc*100:.1f}%", "PB 缺失时用现金/市值作为资产折价代理",
                buy_price, hold_price,
            )
            rows = [
                {"区间": "现金折价买入", "价格范围": _range_label(None, safe_price), "动作": "现金/市值 ≥ 40%,资产保护较强"},
                {"区间": "分批买入", "价格范围": _range_label(safe_price, buy_price), "动作": "现金/市值 30%-40%,等待催化"},
                {"区间": "重估持有", "价格范围": _range_label(buy_price, hold_price), "动作": "现金/市值 20%-30%,谨慎持有"},
                {"区间": "兑现/卖出", "价格范围": _range_label(hold_price, None), "动作": "现金/市值 < 20%,资产折价不明显"},
            ]
            caption = "PB 缺失,临时退化为现金/市值口径。"

    else:
        if pe is None or pe <= 0:
            st.info(f"{CLASS_META.get(cls_id, ('当前类型',))[0]} 暂缺 PE-TTM,无法形成兜底价格区间。")
            return
        safe_price = _pe_price_at(current, pe, 10)
        buy_price = _pe_price_at(current, pe, 15)
        hold_price = _pe_price_at(current, pe, 25)
        metrics = _metric_items(
            current, as_of,
            "当前 PE", f"{pe:.1f}", "未知林奇类型的兜底 PE 价格线",
            buy_price, hold_price,
        )
        rows = [
            {"区间": "谨慎买入", "价格范围": _range_label(None, safe_price), "动作": "仅作兜底参考,需先校准林奇类型"},
            {"区间": "观察买入", "价格范围": _range_label(safe_price, buy_price), "动作": "小仓位验证故事"},
            {"区间": "合理持有", "价格范围": _range_label(buy_price, hold_price), "动作": "等待类型和故事进一步确认"},
            {"区间": "减仓/卖出", "价格范围": _range_label(hold_price, None), "动作": "类型不清且估值偏高,优先降风险"},
        ]
        caption = "当前类型未匹配到专属公式,使用林奇页面兜底 PE 价格线。"

    c1, c2, c3, c4 = st.columns(4)
    for col, item in zip((c1, c2, c3, c4), metrics):
        col.metric(item[0], item[1], help=item[2])
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(caption)


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
