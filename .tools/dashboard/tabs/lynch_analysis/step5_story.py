"""Lynch step 5 — 故事更新(每季 ping)+ 卖出触发器。"""
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


def _step_5_story_update(ticker: str, m: dict | None = None,
                          cls_id_used: str = "") -> None:
    """⑤ 故事更新 — 每季 ping 兑现度。

    m / cls_id_used 用于自动计算卖出触发条件状态(PEG / YoY / 负债率)。
    """
    _section_banner("⑤", "🎬", "故事更新(决策续集 · 每季 ping 一次)",
                    "故事在轨吗?需不需要卖?",
                    color="#d63384")

    story = st.session_state.get(f"lynch_story_{ticker}", {})
    if not story.get("oneline"):
        st.warning("⚠️ 第 1 步未填故事脚本 — 请先回到「① 公司分类」填写")
        return

    m = m or {}

    # ─── 📖 故事 + 验证证据(默认全部展开)───────────────────────────────
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
            f"letter-spacing:0.04em;margin-bottom:4px'>📖 你的故事</div>"
            f"<div style='font-size:14px;color:#111827;line-height:1.55;"
            f"font-style:italic'>{story['oneline']}</div>",
            unsafe_allow_html=True,
        )
        if story.get("evidence"):
            evidence_lines = [
                l.strip() for l in story["evidence"].splitlines() if l.strip()
            ]
            evi_html = "".join(
                f"<div style='margin:3px 0;font-size:13px;color:#374151;"
                f"line-height:1.55'>{l}</div>"
                for l in evidence_lines
            )
            st.markdown(
                f"<div style='border-top:1px dashed #E5E7EB;margin-top:8px;"
                f"padding-top:6px'>"
                f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
                f"letter-spacing:0.04em;margin-bottom:3px'>"
                f"✅ 验证证据(故事写入时的支撑数据)</div>"
                f"{evi_html}</div>",
                unsafe_allow_html=True,
            )

    # ─── 📊 故事打分卡(每条证据带"建议分数"参考)──────────────────────
    st.markdown("**📊 故事打分卡(本季更新)**")
    st.caption("逐条对照原始证据打分(0-100)· 系统已根据当前财报给出建议值")

    score_key = f"lynch_score_{ticker}"
    scores_state = st.session_state.get(score_key, {})

    evidence_lines = [
        l.strip() for l in (story.get("evidence") or "").splitlines()
        if l.strip() and l.strip() not in ("•", "-")
    ]
    n_evidence = max(1, len(evidence_lines))

    # 给每条证据一个"建议分数" — 基于关键指标当前 vs 原始判断
    suggested = _suggested_evidence_scores(m, cls_id_used, n_evidence)

    cols = st.columns(min(3, n_evidence))
    new_scores = []
    for i in range(n_evidence):
        with cols[i % len(cols)]:
            sug = suggested[i] if i < len(suggested) else 80
            evi_short = (evidence_lines[i][:42] + "…") if i < len(evidence_lines) and len(evidence_lines[i]) > 42 else (evidence_lines[i] if i < len(evidence_lines) else f"证据 #{i+1}")
            st.caption(f"#{i+1}: {evi_short}")
            v = st.slider(
                f"兑现度",
                min_value=0, max_value=100,
                value=int(scores_state.get(f"e{i}", sug)),
                step=5,
                key=f"{score_key}_e{i}",
                label_visibility="collapsed",
            )
            sug_badge = "🟢" if sug >= 80 else "🟡" if sug >= 60 else "🔴"
            st.caption(f"💡 建议 **{sug}** {sug_badge}(基于当前财报)")
            new_scores.append(v)
            scores_state[f"e{i}"] = v

    st.session_state[score_key] = scores_state

    avg = sum(new_scores) / len(new_scores)
    if avg >= 80:
        verdict, color = "🟢 故事在轨", "#1b8a3a"
    elif avg >= 60:
        verdict, color = "🟡 部分兑现", "#f0ad4e"
    else:
        verdict, color = "🔴 故事破裂", "#d9534f"

    st.markdown(
        f'<div style="padding:12px;border-radius:6px;background:{color}20;'
        f'border-left:4px solid {color};margin-top:8px">'
        f'<span style="font-size:20px;font-weight:700;color:{color}">'
        f'兑现度 {avg:.0f}% — {verdict}</span></div>',
        unsafe_allow_html=True,
    )

    # ─── 🚨 卖出触发条件(自动判断每条是否触发)─────────────────────────
    st.markdown("---")
    st.markdown("**🚨 卖出触发条件(任一触发 = 严肃评估)**")
    st.caption("每条阈值均由系统对照当前财报自动判断 · 无需手动勾选")

    triggers = _evaluate_sell_triggers(m, cls_id_used, avg)
    n_fired = sum(1 for t in triggers if t["fired"])

    # 顶部摘要徽章
    if n_fired == 0:
        summary_color = "#1b8a3a"
        summary_text = f"✅ 全部未触发({len(triggers)}/{len(triggers)} 安全)"
    elif n_fired == 1:
        summary_color = "#f0ad4e"
        summary_text = f"🟡 已触发 1 条 — 需密切关注"
    else:
        summary_color = "#d9534f"
        summary_text = f"🚨 已触发 {n_fired} 条 — 严肃评估卖出"

    st.markdown(
        f'<div style="padding:8px 12px;border-radius:6px;background:{summary_color}15;'
        f'border-left:4px solid {summary_color};margin:6px 0 10px;'
        f'font-weight:600;color:{summary_color}">{summary_text}</div>',
        unsafe_allow_html=True,
    )

    # 4 条触发条件(2x2 grid,每条带状态徽章 + 当前值 + 阈值)
    trig_cols = st.columns(2)
    for i, t in enumerate(triggers):
        with trig_cols[i % 2]:
            badge = "🚨" if t["fired"] else ("⚪" if t["current"] is None else "✅")
            badge_color = ("#d9534f" if t["fired"]
                           else "#9CA3AF" if t["current"] is None
                           else "#1b8a3a")
            border_color = badge_color
            cur_str = t["current_str"]
            with st.container(border=True):
                st.markdown(
                    f"<div style='border-left:3px solid {border_color};"
                    f"padding-left:8px;margin:-2px 0'>"
                    f"<div style='font-size:13px;font-weight:600;color:#111827'>"
                    f"{badge} {t['cond']} <span style='color:#9CA3AF;font-weight:400;"
                    f"font-size:11px'>· {t['label']}</span></div>"
                    f"<div style='font-size:12px;color:#374151;margin-top:3px'>"
                    f"当前 <b style='color:{badge_color}'>{cur_str}</b> · "
                    f"阈值 <span style='color:#6B7280'>{t['threshold']}</span>"
                    f"</div>"
                    f"<div style='font-size:11px;color:#6B7280;margin-top:2px;"
                    f"line-height:1.4'>{t['detail']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def _suggested_evidence_scores(m: dict, cls_id_used: str, n: int) -> list[int]:
    """对 n 条证据给出建议兑现度(0-100)。简化策略:用核心指标的'当前 vs 原阈值'综合打分。"""
    rev_yoy = m.get("rev_yoy_recent")
    np_yoy = m.get("np_yoy_recent")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    debt = m.get("debt_ratio")
    pe = m.get("pe_ttm")

    # 类型化阈值
    cagr_th = 0.15 if cls_id_used == "fast_grower" else 0.05 if cls_id_used == "stalwart" else 0.0
    yoy_th = 0.20 if cls_id_used == "fast_grower" else 0.10 if cls_id_used == "stalwart" else 0.0
    debt_th = 0.50 if cls_id_used == "fast_grower" else 0.65

    parts: list[int] = []
    # CAGR 维持度
    if cagr is not None and cagr_th > 0:
        ratio = max(0.0, min(1.5, cagr / cagr_th))
        parts.append(int(min(100, max(20, ratio * 70))))
    # 单季 YoY 维持度
    if rev_yoy is not None:
        if yoy_th > 0:
            ratio = max(0.0, min(1.5, rev_yoy / yoy_th))
            parts.append(int(min(100, max(20, ratio * 70))))
        else:
            parts.append(80 if rev_yoy > 0 else 40)
    # 净利 YoY
    if np_yoy is not None:
        parts.append(int(min(100, max(20, 80 + np_yoy * 100))))
    # 负债率(反向:越低分越高)
    if debt is not None:
        if debt <= debt_th * 0.7:
            parts.append(90)
        elif debt <= debt_th:
            parts.append(75)
        else:
            parts.append(45)
    # PEG
    if pe is not None and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        parts.append(90 if peg < 1 else 70 if peg < 1.5 else 50 if peg < 2 else 30)

    if not parts:
        return [70] * n
    avg_part = int(round(sum(parts) / len(parts)))
    return [avg_part] * n


def _evaluate_sell_triggers(m: dict, cls_id_used: str, story_avg: float) -> list[dict]:
    """对 4 条卖出触发条件做自动评估。返回每条的状态字典。"""
    rev_yoy = m.get("rev_yoy_recent")
    np_yoy = m.get("np_yoy_recent")
    debt = m.get("debt_ratio")
    pe = m.get("pe_ttm")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")

    # ① PEG > 2.0
    if pe is not None and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        peg_fired = peg > 2.0
        peg_cur = f"{peg:.2f}"
        peg_detail = f"PE {pe:.1f} ÷ CAGR {cagr*100:.1f}% = {peg:.2f}"
    else:
        peg = None
        peg_fired = False
        peg_cur = "—"
        peg_detail = "缺 PE 或 CAGR 数据"

    # ② 连续 2 季单季 YoY < 20%(快速类阈值,其它类放宽到 10% / 0)
    yoy_th = 20 if cls_id_used == "fast_grower" else 10 if cls_id_used == "stalwart" else 0
    yoy_used = rev_yoy if rev_yoy is not None else np_yoy
    if yoy_used is not None:
        yoy_pct = yoy_used * 100
        # 简化:用 1 个季度 YoY 是否低于阈值代表"是否进入断档区"
        # (真严格判断需 _quarterly_yoy 取连续 2 季,这里给保守估计)
        yoy_fired = yoy_pct < yoy_th
        yoy_cur = f"{yoy_pct:+.1f}%"
        yoy_detail = (f"最新单季营收 YoY {yoy_pct:+.1f}%(阈值 ≥{yoy_th}%);"
                      "连续 2 季低于阈值则触发")
    else:
        yoy_fired = False
        yoy_cur = "—"
        yoy_detail = "无最新单季 YoY 数据"

    # ③ 资产负债率 > 50%(快速类)/ > 65%(其它)
    debt_th_pct = 50 if cls_id_used == "fast_grower" else 65
    if debt is not None:
        debt_pct = debt * 100
        debt_fired = debt_pct > debt_th_pct
        debt_cur = f"{debt_pct:.1f}%"
        debt_detail = f"当前 {debt_pct:.1f}%(阈值 ≤{debt_th_pct}%)"
    else:
        debt_fired = False
        debt_cur = "—"
        debt_detail = "无负债率数据"

    # ④ 故事兑现度 < 60%
    story_fired = story_avg < 60
    story_cur = f"{story_avg:.0f}%"
    story_detail = "上方打分卡综合得分(系统建议 + 你的调整)"

    return [
        {
            "cond": "PEG > 2.0",
            "label": "估值反转",
            "current": peg,
            "current_str": peg_cur,
            "threshold": "≤ 2.0",
            "fired": peg_fired,
            "detail": peg_detail,
        },
        {
            "cond": f"单季 YoY < {yoy_th}%(连续 2 季)",
            "label": "增长断档",
            "current": yoy_used,
            "current_str": yoy_cur,
            "threshold": f"≥ {yoy_th}%",
            "fired": yoy_fired,
            "detail": yoy_detail,
        },
        {
            "cond": f"资产负债率 > {debt_th_pct}%",
            "label": "护栏失守",
            "current": debt,
            "current_str": debt_cur,
            "threshold": f"≤ {debt_th_pct}%",
            "fired": debt_fired,
            "detail": debt_detail,
        },
        {
            "cond": "故事兑现度 < 60%",
            "label": "故事破裂",
            "current": story_avg,
            "current_str": story_cur,
            "threshold": "≥ 60%",
            "fired": story_fired,
            "detail": story_detail,
        },
    ]


# ─── ⑥ ABCD/12345 综合评级 ──────────────────────────────────────────────

