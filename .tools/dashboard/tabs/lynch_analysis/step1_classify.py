"""Lynch step 1 — 公司分类(六类判断)+ 故事脚本。"""
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


def _step_1_classification(ticker: str, cls: ClassificationResult, m: dict,
                           folder: str) -> None:
    """① 公司分类 + 故事脚本(新版三段式:类型编辑器 → 自动理由 → 核心指标 → 故事)。"""
    _section_banner("①", "🔍", "公司分类(决定后续四步用什么口径)",
                    "林奇核心:先定性,后定量 — 误判 = 灾难", color="#0d6efd")

    # 📖 林奇六类速读
    with st.expander("📖 林奇六类公司速读(展开看)", expanded=False):
        for cid, (cn_name, emoji, desc) in CLASS_META.items():
            highlight = "**" if cid == cls.cls_id else ""
            st.markdown(f"- {highlight}{emoji} **{cn_name}**{highlight} — {desc}")

    # ─── 🧭 公司类型判断(类型编辑 + 自动分析理由 + 林奇视角提示 合并)────
    st.markdown("#### 🧭 公司类型判断")
    st.caption(
        "默认采用自动判定;若公司具有双特征(如 周期+快速增长),"
        "可调整主/次类型与权重 · 自动分析理由见下方框。"
    )
    primary, secondary, weight = _render_type_editor(ticker, cls)
    cls_id_used = primary

    # 自动分析理由 + 林奇视角提示 合并到一个 bordered container,贴紧上方编辑器
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
            f"letter-spacing:0.04em;margin-bottom:4px'>🤖 自动分析理由</div>"
            f"<div style='font-size:13px;color:#374151;line-height:1.55'>"
            f"{cls.reason}</div>",
            unsafe_allow_html=True,
        )
        if cls.notes:
            notes_html = "".join(
                f"<li style='margin:2px 0;color:#374151;font-size:13px;line-height:1.5'>{n}</li>"
                for n in cls.notes
            )
            st.markdown(
                f"<div style='border-top:1px dashed #E5E7EB;margin-top:8px;padding-top:6px'>"
                f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
                f"letter-spacing:0.04em;margin-bottom:3px'>💡 林奇视角提示</div>"
                f"<ul style='margin:0;padding-left:18px'>{notes_html}</ul></div>",
                unsafe_allow_html=True,
            )

    # ─── 🔑 核心指标分析(再接着的是关键数据)──────────────────────────
    st.divider()
    st.markdown(
        f"#### 🔑 核心指标分析 · {CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]}"
        + (f" 主导({weight}%)" if secondary else "")
    )
    st.caption("基于财报数据自动计算,按主类型阈值标注 ✅/🟡/🔴")

    indicator_rows = derive_key_indicators(m, cls_id_used)
    if indicator_rows:
        idf = pd.DataFrame(indicator_rows)

        def _style_status(v):
            if v == "✅": return "background-color:#d4edda; font-weight:600"
            if v == "🟡": return "background-color:#fff3cd; font-weight:600"
            if v == "🔴": return "background-color:#f8d7da; font-weight:600"
            return ""

        styler = idf.style.map(_style_status, subset=["状态"])
        st.dataframe(styler, width="stretch", hide_index=True)
    else:
        st.caption("(数据不足以派生核心指标)")

    # 双特征:展开看次类型关键指标
    if secondary and weight < 90:
        sec_label = f"📋 次类型视角:{CLASS_META[secondary][1]} {CLASS_META[secondary][0]} ({100-weight}%)关键指标"
        with st.expander(sec_label, expanded=False):
            st.caption(f"如果按 **{CLASS_META[secondary][0]}** 视角看,这家公司的关键指标如下:")
            sec_rows = derive_key_indicators(m, secondary)
            if sec_rows:
                sdf = pd.DataFrame(sec_rows[:5])
                sec_styler = sdf.style.map(_style_status, subset=["状态"])
                st.dataframe(sec_styler, width="stretch", hide_index=True)

    # ─── 📝 故事脚本(自动派生 + 用户编辑)─────────────────────────────
    st.divider()
    st.markdown("#### 📝 故事脚本(自动从财报派生,可编辑)")
    st.caption("林奇:'如果你不能用三句话讲清楚为什么买它,就别买。' 下面三段先由系统从财报自动总结,你再编辑。")

    industry = m.get("industry_sw_l1", "") or ""
    auto_story = derive_story(m, cls, cls_id_used, industry=industry)

    # 双特征:在 oneline 末尾标注次类型 + 在 not_happen 末尾追加次类型卖出信号
    if secondary and weight < 90:
        sec_emoji = CLASS_META[secondary][1]
        sec_name = CLASS_META[secondary][0]
        auto_story["oneline"] = (
            f"{auto_story['oneline']} · 同时具有 {sec_emoji} {sec_name}"
            f"特征({100-weight}%)"
        )
        sec_story = derive_story(m, cls, secondary, industry=industry)
        # 提取次类型 not_happen 的核心 2-3 行(第一行是标题,跳过)
        sec_lines = sec_story["not_happen"].splitlines()
        sec_signals = [l for l in sec_lines[1:] if l.strip().startswith("•")][:2]
        if sec_signals:
            auto_story["not_happen"] += (
                f"\n\n双特征额外信号({sec_name}视角):\n"
                + "\n".join(sec_signals)
            )

    # 持久化:首次进或切换公司/类型 → 重置为 auto;若用户编辑过,保留编辑
    story_key = f"lynch_story_{ticker}"
    story_meta_key = f"lynch_story_meta_{ticker}"  # 记录用了哪个 cls_id_used
    last_meta = st.session_state.get(story_meta_key)
    cur_meta = (cls_id_used, secondary, weight, _fmt_num(m.get("rev_cagr_5y"), 3))

    # 类型变了 → 重新生成
    if last_meta != cur_meta:
        st.session_state[story_key] = dict(auto_story)
        st.session_state[story_meta_key] = cur_meta

    story = st.session_state.get(story_key, dict(auto_story))

    # 顶部:并排显示"自动派生 vs 当前编辑"
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
    with btn_col1:
        if st.button("🤖 重新自动生成", key=f"{story_key}_regen",
                     help="覆盖当前编辑,用财报数据重新生成 3 段"):
            st.session_state[story_key] = dict(auto_story)
            st.rerun()
    with btn_col2:
        edited_flag = (story != auto_story)
        if edited_flag:
            st.caption("✏️ 已编辑(与自动派生不同)")
        else:
            st.caption("🤖 自动派生(未编辑)")

    s1 = st.text_input(
        "🎯 故事一句话",
        value=story.get("oneline", ""),
        key=f"{story_key}_oneline",
    )

    # 验证证据 — 逐条预览 + 行内编辑 + 增删按钮
    s2 = _editable_list(
        label="✅ 验证证据(从财报数据派生,可补充行业/管理层信号)",
        key_base=f"{story_key}_evidence",
        raw_value=story.get("evidence", ""),
        placeholder="如:营收 5y CAGR 18%(高速扩张,远超 GDP)",
        hint="每行 1 条;点 ✕ 删除,点 ➕ 添加",
    )

    # 不会发生的事 / 卖出信号 — 同上
    s3 = _editable_list(
        label="❌ 不会发生的事 / 卖出信号",
        key_base=f"{story_key}_not_happen",
        raw_value=story.get("not_happen", ""),
        placeholder="如:连续 2 季营收 YoY < 20% — 增长断档",
        hint="每行 1 条;点 ✕ 删除,点 ➕ 添加",
    )

    st.session_state[story_key] = {
        "oneline": s1, "evidence": s2, "not_happen": s3,
    }

