"""Lynch step 2 — 成长核查(CAGR / 季度连续性 / 增长来源)。"""
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


def _step_2_growth_check(ticker: str, m: dict, cls_id_used: str) -> None:
    """② 成长核查 — 三层证据。"""
    _section_banner("②", "📈", "成长核查(增长真假 + 持续性 + 来源)",
                    "三层证据:CAGR 速率 / 季度连续 / 销量驱动", color="#1b8a3a")

    if cls_id_used in ("slow_grower", "cyclical", "asset_play", "turnaround"):
        st.info(f"💡 当前类型 {CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]} "
                f"非典型成长股,本步骤侧重数据展示而非判定")

    # 层 1:CAGR 速率
    st.markdown("**层 1:CAGR 速率**")
    rev_5y = m.get("rev_cagr_5y")
    np_yoy = m.get("np_yoy_recent")

    threshold_cagr = 0.25 if cls_id_used == "fast_grower" else 0.10 if cls_id_used == "stalwart" else 0.05
    threshold_label = "快速 ≥25%" if cls_id_used == "fast_grower" else "稳健 ≥10%" if cls_id_used == "stalwart" else "缓慢 ≥5%"

    db_mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0
    deduct = _deduct_metrics(ticker, db_mtime)
    dnp_yoy = deduct.get("dnp_yoy_recent")
    dnp_ratio = deduct.get("dnp_to_np_ratio")

    c1, c2, c3, c4 = st.columns(4)
    if rev_5y is not None:
        delta_color = "normal" if rev_5y >= threshold_cagr else "inverse"
        c1.metric("营收 5y CAGR", f"{rev_5y*100:.1f}%",
                  delta=f"{threshold_label} 阈值",
                  delta_color=delta_color)
    else:
        c1.metric("营收 5y CAGR", "—", delta="数据缺失")

    if m.get("rev_cagr_3y") is not None:
        c2.metric("营收 3y CAGR", f"{m['rev_cagr_3y']*100:.1f}%")
    else:
        c2.metric("营收 3y CAGR", "—")

    if np_yoy is not None:
        c3.metric("归母净利 YoY", f"{np_yoy*100:.1f}%",
                  delta="加速" if np_yoy > 0.20 else "稳" if np_yoy > 0 else "下滑",
                  delta_color="normal" if np_yoy > 0 else "inverse")
    else:
        c3.metric("归母净利 YoY", "—")

    # ⭐ 第 4 列:扣非净利 YoY(2026-05-06 新增 — 衡量"非一次性"利润的真实增速)
    if dnp_yoy is not None:
        # 极端值(|yoy| > 200%)通常源于扣非基数过小或翻负→翻正,显示提醒而非误导数字
        if abs(dnp_yoy) > 2.0:
            c4.metric("扣非净利 YoY ⭐", "极端值",
                      delta="基数小/翻正翻负",
                      delta_color="off",
                      help=f"派生 yoy = {dnp_yoy*100:.0f}%,"
                           f"通常因上年同期扣非基数过小或翻负→翻正所致;"
                           f"建议看下方近 8 季单季趋势图")
        else:
            c4.metric("扣非净利 YoY ⭐", f"{dnp_yoy*100:.1f}%",
                      delta="加速" if dnp_yoy > 0.20 else "稳" if dnp_yoy > 0 else "下滑",
                      delta_color="normal" if dnp_yoy > 0 else "inverse",
                      help="sina IS 派生(非理杏仁权威值,与官方差 5-10%):"
                           "净利 - 投资收益 - 公允价值变动 - 政府补助 - 资产处置 - 营业外收入 + 营业外支出,"
                           "再用 25% 简化税率调整")
    else:
        c4.metric("扣非净利 YoY ⭐", "—",
                  help="non_recurring_items 表无此公司数据,跑 fetch_non_recurring.py 补")

    # 差异警报:扣非 vs 归母差距大 → 一次性损益占比高(剔除极端值场景)
    if dnp_yoy is not None and np_yoy is not None and abs(dnp_yoy) <= 2.0:
        diff = abs(dnp_yoy - np_yoy)
        if diff > 0.30:
            direction = "高估" if np_yoy > dnp_yoy else "低估"
            st.warning(
                f"⚠️ 归母 yoy 与扣非 yoy 相差 {diff*100:.1f}pp(归母 {direction}真实增速)— "
                f"利润对一次性损益依赖度大,看扣非更可信",
                icon="⚠️",
            )

    # 扣非占比卡(显示在 metric 下面)
    if dnp_ratio is not None:
        if dnp_ratio >= 0.90:
            ratio_msg = f"🟢 扣非占比 {dnp_ratio*100:.1f}% — 主业纯净,几乎无一次性损益"
            st.caption(ratio_msg)
        elif dnp_ratio >= 0.70:
            ratio_msg = f"🟡 扣非占比 {dnp_ratio*100:.1f}% — 中等依赖一次性损益(政府补助/投资收益)"
            st.caption(ratio_msg)
        else:
            st.error(
                f"🔴 扣非占比仅 {dnp_ratio*100:.1f}% — **重度依赖一次性损益**!"
                f"若一次性损益消失,真实利润会大幅缩水",
                icon="🚨",
            )

    # 层 2:季度连续性(db_mtime 在层 1 已计算)— 8 季单季 YoY 滑窗
    qc = _qc_from_dict(_quarterly_continuity_cached(ticker, db_mtime, n_quarters=8))
    threshold_yoy = 0.20 if cls_id_used == "fast_grower" else 0.10
    threshold_label = ">20%" if cls_id_used == "fast_grower" else ">10%"
    st.markdown(f"**层 2:连续性(近 8 季营收 YoY,{threshold_label} 绿区)**")

    if qc is None:
        st.caption("(growth 表无营收数据,跳过季度连续性)")
    else:
        dates = [s for s, _ in qc.series]
        yoys = [y for _, y in qc.series]
        ymax = max(yoys) if yoys else 0
        ymin = min(yoys) if yoys else 0

        fig = go.Figure()
        fig.add_hrect(y0=threshold_yoy, y1=ymax + 0.10 if ymax > threshold_yoy else 0.5,
                      fillcolor="#1b8a3a", opacity=0.08, line_width=0,
                      annotation_text=f"林奇阈值 {threshold_label}",
                      annotation_position="top right", annotation_font_size=10)
        fig.add_hrect(y0=ymin - 0.05 if ymin < 0 else -0.1, y1=0,
                      fillcolor="#d9534f", opacity=0.06, line_width=0)
        fig.add_trace(go.Scatter(
            x=dates, y=yoys, mode="lines+markers",
            line=dict(color="#0d6efd", width=2),
            marker=dict(size=8),
            name="单季营收 YoY",
            hovertemplate="<b>%{x}</b><br>YoY %{y:.1%}<extra></extra>",
        ))
        fig.update_layout(
            height=240, margin=dict(t=20, b=20, l=10, r=10),
            yaxis_tickformat=".0%", showlegend=False,
            yaxis_title="单季营收 YoY",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        # 命中数 + 类型铁律达标判断 + 退化提示
        n, h20, h10 = qc.n_quarters, qc.hits_20pct, qc.hits_10pct
        c_a, c_b, c_c, c_d = st.columns(4)
        c_a.metric("8 季中 >20% 命中", f"{h20}/{n}")
        c_b.metric("8 季中 >10% 命中", f"{h10}/{n}")
        if qc.median_yoy is not None:
            c_c.metric("中位 YoY", f"{qc.median_yoy*100:+.1f}%")
        if qc.latest_yoy is not None:
            delta_color = "normal" if qc.latest_yoy > 0 else "inverse"
            c_d.metric("最新季 YoY", f"{qc.latest_yoy*100:+.1f}%",
                       delta_color=delta_color)

        if cls_id_used == "fast_grower":
            if qc.fast_grower_pass():
                st.success(f"✅ 快速增长铁律达标 — 近 {n} 季 {h20}/{n} >20%(≥6/8)", icon="✅")
            elif h10 >= 6:
                st.warning(
                    f"⚠️ 已退化为稳健 — 快速铁律未达(仅 {h20}/{n} >20%)但 {h10}/{n} >10% "
                    f"满足稳健铁律;建议把分类改为 stalwart 重评",
                    icon="⚠️",
                )
            elif h20 >= 4:
                st.warning(f"⚠️ 快速增长边缘 — 近 {n} 季 {h20}/{n} >20%(铁律要求 ≥6/8)",
                           icon="⚠️")
            else:
                st.error(
                    f"🔴 快速增长属性丧失 — 近 {n} 季仅 {h20}/{n} >20% / {h10}/{n} >10%;"
                    f"建议重新分类为 缓慢增长型 / 周期型 / 困境反转型",
                    icon="🚨",
                )
        elif cls_id_used == "stalwart":
            if qc.stalwart_pass():
                st.success(f"✅ 稳健增长铁律达标 — 近 {n} 季 {h10}/{n} >10%(≥6/8)", icon="✅")
            elif h10 >= 4:
                st.warning(f"⚠️ 稳健增长边缘 — 近 {n} 季 {h10}/{n} >10%(铁律要求 ≥6/8)",
                           icon="⚠️")
            elif qc.hits_0 >= 6:
                st.info(f"ℹ️ 增长缓慢但未断档 — 近 {n} 季 {qc.hits_0}/{n} 季正增长",
                        icon="ℹ️")
            else:
                st.error(
                    f"🔴 稳健属性丧失 — 近 {n} 季仅 {h10}/{n} >10%;建议重新分类",
                    icon="🚨",
                )
        else:
            st.caption(f"近 {n} 季中:{h20} 季 >20% / {h10} 季 >10% / {qc.hits_0} 季 ≥0%")

        if qc.source == "derived":
            st.caption("📐 数据派生口径:营业收入累计 → 单季还原(Q1=累计;Q2/Q3/Q4=当期-上期);"
                       "YoY = 单季今年 / 单季去年同期 - 1")

    # 层 3:增长来源(简化版,行业适配)
    st.markdown("**层 3:增长来源(质量)**")
    cat = _company_category(ticker, db_mtime)
    na_msg = LAYER3_INDUSTRY_NA.get(cat)
    if na_msg:
        st.info(na_msg)
    else:
        st.caption("⚠️ 销量 vs 提价拆解 / 海外占比 / 市占率 — 当前数据层未装配,需手工补"
                   "(可在 02_companies/{N}_{name}/01_基本面数据/摘要.md 末尾手动补,"
                   "或后续用 Claude vision 解析年报 PDF)")

    # 自动结论
    st.divider()
    if rev_5y is not None and rev_5y >= threshold_cagr:
        st.success(f"✅ 成长核查 — 营收 5y CAGR {rev_5y*100:.1f}% 达标 ({threshold_label})", icon="✅")
    elif rev_5y is not None:
        st.warning(f"⚠️ 营收 5y CAGR {rev_5y*100:.1f}% 未达 {threshold_label}", icon="⚠️")
    else:
        st.info("ℹ️ 数据不足,建议人工确认")

