"""Lynch step 1 — 公司分类(六类判断)+ 故事脚本。"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from datetime import timedelta
from html import escape
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

    # ─── 📝 故事要点(只读 Top3)──────────────────────────────────────
    st.divider()
    st.markdown("#### 📝 故事要点")
    st.caption("只保留最重要的 3 条:为什么看、现在靠什么支撑、什么情况说明看错。")

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

    # 持久化给后续“故事更新/综合结论”使用;页面这里只做只读摘要。
    story_key = f"lynch_story_{ticker}"
    story_meta_key = f"lynch_story_meta_{ticker}"  # 记录用了哪个 cls_id_used
    last_meta = st.session_state.get(story_meta_key)
    cur_meta = (cls_id_used, secondary, weight, _fmt_num(m.get("rev_cagr_5y"), 3))

    if last_meta != cur_meta:
        st.session_state[story_key] = dict(auto_story)
        st.session_state[story_meta_key] = cur_meta

    story = dict(auto_story)
    st.session_state[story_key] = story

    def _useful_lines(raw: str, *, fallback: str, limit: int = 3) -> list[str]:
        out: list[str] = []
        for line in str(raw or "").splitlines():
            text = line.strip().lstrip("•- ").strip()
            if not text or text.endswith(":") or text.endswith("："):
                continue
            out.append(text)
            if len(out) >= limit:
                break
        return out or [fallback]

    supports = _useful_lines(
        story.get("evidence", ""),
        fallback="当前财报证据不足,先看下一期收入、利润和现金流是否继续验证。",
    )
    risks = _useful_lines(
        story.get("not_happen", ""),
        fallback="若核心增长或现金流连续转弱,说明原始故事需要重审。",
    )
    support_html = "".join(
        f"<li style='margin:4px 0;line-height:1.45;'>{escape(x)}</li>"
        for x in supports[:3]
    )
    risk_html = "".join(
        f"<li style='margin:4px 0;line-height:1.45;'>{escape(x)}</li>"
        for x in risks[:3]
    )

    st.markdown(
        f"""
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:8px;">
          <div style="border:1px solid #E5E7EB;border-radius:8px;padding:12px;background:#FFFFFF;">
            <div style="font-size:12px;color:#6B7280;font-weight:760;">① 为什么看</div>
            <div style="font-size:15px;color:#111827;font-weight:760;line-height:1.55;margin-top:5px;">{escape(str(story.get("oneline", "—")))}</div>
          </div>
          <div style="border:1px solid #DCFCE7;border-radius:8px;padding:12px;background:#F0FDF4;">
            <div style="font-size:12px;color:#15803D;font-weight:760;">② 最关键支撑 Top3</div>
            <ol style="font-size:14px;color:#111827;font-weight:720;padding-left:18px;margin:6px 0 0 0;">{support_html}</ol>
          </div>
          <div style="border:1px solid #FEE2E2;border-radius:8px;padding:12px;background:#FEF2F2;">
            <div style="font-size:12px;color:#B91C1C;font-weight:760;">③ 看错/卖出信号 Top3</div>
            <ol style="font-size:14px;color:#111827;font-weight:720;padding-left:18px;margin:6px 0 0 0;">{risk_html}</ol>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
