"""M6 彼得林奇分析法 · 5 步成长投资框架(sub-package 入口)。

6 sub-tabs + 综合结论:
  ① 公司分类(六类判断)+ 故事脚本
  ② 成长核查(CAGR / 季度连续性 / 增长来源)
  ③ 财务护栏(高增长不烧钱)
  ④ PEG 估值(成长合理性)
  ⑤ 故事更新(每季 ping)
  ⑥ ABCD/12345 评级
  🎯 综合结论 + Markdown 导出

入口:
  from tabs.lynch_analysis import render
  render(companies, selected, db_mtime, decisions_db, folder_to_ticker_fn)
"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from masters.lynch.classifier import CLASS_META, ClassificationResult  # noqa: E402

from ._helpers import _classify_cached, _metrics_cached, _quarterly_yoy
from .step1_classify import _step_1_classification
from .step2_growth import _step_2_growth_check
from .step3_guardrails import _step_3_financial_guardrails
from .step4_peg import _step_4_peg_valuation
from .step5_story import _step_5_story_update
from .step6_abcd import _step_6_abcd_evaluation
from .summary import _step_6_summary


def _method_hint(m: dict, cls: ClassificationResult) -> tuple[bool, str, str, str]:
    industry = f"{m.get('industry_sw_l1') or ''} {m.get('industry_sw_l2') or ''}"
    category = (m.get("category") or "").lower()
    if cls.cls_id == "not_applicable" or cls.extra.get("lynch_six_class_misfit"):
        framework = cls.extra.get("recommended_framework")
        focus = cls.extra.get("recommended_focus")
        if framework and focus:
            return True, framework, cls.reason, focus
        if "保险" in industry or category == "insurance":
            return True, "保险价值修复法", "保险不是典型林奇成长股,PEG/负债率护栏容易误导。", "低 PB/PEV + EV/NBV 修复 + 偿付能力 + 投资收益率 + 股息回报"
        if "银行" in industry or category == "bank":
            return True, "银行价值评估法", "银行不是典型林奇成长股,高负债率是行业特性。", "低 PB + ROE/息差 + 不良率/拨备 + 分红稳定性"
        if "证券" in industry or category in ("security", "other_financial"):
            return True, "券商周期估值法", "券商受资本市场周期影响大,不适合按普通成长股 PEG 评估。", "PB 分位 + 净资本 + 自营/经纪/投行业务周期"
        return True, "行业专属评估框架", "该公司不适合直接套用林奇六类和 PEG 体系。", "先判断行业核心驱动,再选择对应估值锚。"
    return False, "", "", ""


def _render_method_not_applicable(reason: str, framework: str, focus: str) -> None:
    st.info(
        f"**不符合彼得林奇通用评估方法**\n\n"
        f"{reason}\n\n"
        f"建议切换到:**{framework}**\n\n"
        f"核心观察:{focus}"
    )


def _sync_company(source_key: str) -> None:
    company = st.session_state.get(source_key)
    if not company:
        return
    for key in ("company", "lynch_company", "graham_company", "munger_company", "dc_company"):
        st.session_state[key] = company
    st.session_state["_last_sidebar_company"] = company


def render(companies: list[str], selected: str, db_mtime: float,
           decisions_db=None, folder_to_ticker_fn=None) -> None:
    st.subheader("🌱 彼得林奇分析法 · 成长投资五步框架")

    company = st.session_state.get("company", selected)
    st.caption(f"当前公司:{company} · 评估年份:2026")

    # ticker 解析
    if folder_to_ticker_fn:
        f2t = folder_to_ticker_fn if isinstance(folder_to_ticker_fn, dict) else folder_to_ticker_fn
        ticker = f2t.get(company, "")
    else:
        # fallback:从 helpers 加载
        from dashboard_helpers import _folder_to_ticker
        ticker = _folder_to_ticker(db_mtime).get(company, "")

    if not ticker:
        st.error(f"⚠️ 未找到 {company} 的 ticker 映射")
        return

    # 加载分类 + metrics
    cls_dict = _classify_cached(ticker, db_mtime)
    m = _metrics_cached(ticker, db_mtime)

    if cls_dict is None or m is None:
        st.error(f"⚠️ {company} ({ticker}) 数据加载失败")
        return

    # 重建 ClassificationResult(从 dict)
    cls = ClassificationResult(
        cls_id=cls_dict["cls_id"],
        cls_name=cls_dict["cls_name"],
        cls_emoji=cls_dict["cls_emoji"],
        confidence=cls_dict["confidence"],
        reason=cls_dict["reason"],
        key_metrics=cls_dict["key_metrics"],
        notes=cls_dict["notes"],
        extra=cls_dict.get("extra", {}),
    )

    not_applicable, framework, reason, focus = _method_hint(m, cls)
    if not_applicable:
        _render_method_not_applicable(reason, framework, focus)
        return

    # 顶部 banner:类型徽章 + 一句话定位
    st.markdown(
        f'<div style="padding:12px 16px;border-radius:8px;'
        f'background:linear-gradient(90deg,#0d6efd 0%, #198754 100%);'
        f'color:white;margin:8px 0">'
        f'<span style="font-size:24px">{cls.cls_emoji}</span> '
        f'<span style="font-size:20px;font-weight:700;margin-left:8px">'
        f'当前阶段:{cls.cls_name}</span>'
        f'<span style="margin-left:16px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'置信度 {cls.confidence*100:.0f}%</span>'
        f'<div style="font-size:13px;opacity:0.9;margin-top:6px">'
        f'📍 林奇视角:{CLASS_META[cls.cls_id][2]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 6 sub-tabs(增 ⑥ ABCD/12345 评级)
    tab1, tab2, tab3, tab4, tab5, tab6, tab_sum = st.tabs([
        "① 公司分类", "② 成长核查", "③ 财务护栏",
        "④ PEG 估值", "⑤ 故事更新", "⑥ ABCD 评级", "🎯 综合结论",
    ])

    with tab1:
        _step_1_classification(ticker, cls, m, company)

    # 用户覆盖后的类型
    cls_id_used = st.session_state.get(f"lynch_type_{ticker}", cls.cls_id)

    with tab2:
        _step_2_growth_check(ticker, m, cls_id_used)

    with tab3:
        _step_3_financial_guardrails(ticker, m, cls_id_used)

    with tab4:
        _step_4_peg_valuation(ticker, m, cls_id_used)

    with tab5:
        _step_5_story_update(ticker, m, cls_id_used)

    with tab6:
        _step_6_abcd_evaluation(ticker, m, cls_id_used)

    with tab_sum:
        _step_6_summary(ticker, company, cls, cls_id_used, m, decisions_db)


__all__ = ["render"]
