"""Lynch 综合结论 + Markdown 导出。"""
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
from .step6_abcd import _render_lynch_price_zones


def _step_6_summary(ticker: str, folder: str, cls: ClassificationResult,
                    cls_id_used: str, m: dict,
                    decisions_db=None) -> None:
    """🎯 五步综合结论 + 决策日志写入 + md 导出。"""
    _section_banner("🎯", "🎯", "五步综合结论",
                    "汇总 5 步判定 → 生成决策建议",
                    color="#198754")

    # 汇总 5 步状态(简化:从已渲染数据推导)
    rows = []

    # 步 1
    type_changed = (cls_id_used != cls.cls_id)
    rows.append({
        "步骤": "① 公司分类",
        "结果": f"{CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]}"
                + (" (用户覆盖)" if type_changed else ""),
        "状态": "✅",
    })

    # 步 2
    rev_5y = m.get("rev_cagr_5y")
    threshold_cagr = 0.25 if cls_id_used == "fast_grower" else 0.10 if cls_id_used == "stalwart" else 0.05
    if rev_5y is not None:
        rows.append({
            "步骤": "② 成长核查",
            "结果": f"5y CAGR {rev_5y*100:.1f}%",
            "状态": "✅" if rev_5y >= threshold_cagr else "⚠️",
        })
    else:
        rows.append({"步骤": "② 成长核查", "结果": "数据缺失", "状态": "⚪"})

    # 步 3
    debt = m.get("debt_ratio")
    th = guardrail_thresholds_for(cls_id_used, m.get("industry_sw_l1") or "")
    th_max = th["debt_ratio_max"]
    if debt is not None:
        rows.append({
            "步骤": "③ 财务护栏",
            "结果": f"负债率 {debt*100:.1f}%(≤ {th_max*100:.0f}% 阈值)",
            "状态": "✅" if debt <= th_max else "⚠️" if debt <= th_max + 0.05 else "🔴",
        })
    else:
        rows.append({"步骤": "③ 财务护栏", "结果": "数据缺失", "状态": "⚪"})

    # 步 4
    pe = m.get("pe_ttm")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    peg_cfg = PEG_BY_TYPE.get(cls_id_used, PEG_BY_TYPE["stalwart"])
    if peg_cfg["applicable"] and pe and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        rows.append({
            "步骤": "④ PEG 估值",
            "结果": f"PEG {peg:.2f}",
            "状态": "✅" if peg < peg_cfg["target"] else "⚠️" if peg < peg_cfg["target"] * 1.3 else "🔴",
        })
    else:
        rows.append({
            "步骤": "④ PEG 估值",
            "结果": peg_cfg["note"],
            "状态": "—",
        })

    # 步 5
    score_state = st.session_state.get(f"lynch_score_{ticker}", {})
    if score_state:
        avg_story = sum(score_state.values()) / max(len(score_state), 1)
        rows.append({
            "步骤": "⑤ 故事更新",
            "结果": f"兑现度 {avg_story:.0f}%",
            "状态": "✅" if avg_story >= 80 else "⚠️" if avg_story >= 60 else "🔴",
        })
    else:
        rows.append({"步骤": "⑤ 故事更新", "结果": "未填写", "状态": "⚪"})

    # 渲染汇总表
    sdf = pd.DataFrame(rows)

    def _style_state(v):
        if v == "✅": return "background-color:#d4edda; font-weight:600"
        if v == "⚠️": return "background-color:#fff3cd; font-weight:600"
        if v == "🔴": return "background-color:#f8d7da; font-weight:600"
        return ""

    styler = sdf.style.map(_style_state, subset=["状态"])
    st.dataframe(styler, width="stretch", hide_index=True)

    # 综合判断
    n_pass = sum(1 for r in rows if r["状态"] == "✅")
    n_warn = sum(1 for r in rows if r["状态"] == "⚠️")
    n_fail = sum(1 for r in rows if r["状态"] == "🔴")

    if n_pass >= 4:
        verdict = "🟢 综合通过 — 适合中等以上仓位"
        color = "#1b8a3a"
    elif n_pass >= 3:
        verdict = "🟡 综合可通过 — 试仓 / 关注"
        color = "#f0ad4e"
    else:
        verdict = "🔴 综合不通过 — 不建议建仓"
        color = "#d9534f"

    # ⭐ 同步显示"筛选页加权综合分"— 让两边数字可直接对照
    try:
        dims = compute_lynch_dims(m, cls_id_used)
        weighted_score, weighted_badge = overall_lynch(dims)
        if weighted_score >= 75:
            weighted_rating = "🟢 优秀"
            weighted_color = "#1b8a3a"
        elif weighted_score >= 60:
            weighted_rating = "🟡 合格"
            weighted_color = "#f0ad4e"
        elif weighted_score >= 45:
            weighted_rating = "🟠 警戒"
            weighted_color = "#fd7e14"
        else:
            weighted_rating = "🔴 不及格"
            weighted_color = "#d9534f"
    except Exception:
        weighted_score, weighted_rating, weighted_color = None, None, "#888"

    # 双视角并排展示
    col_v1, col_v2 = st.columns(2)

    with col_v1:
        st.markdown(
            f'<div style="padding:14px;border-radius:8px;background:{color}20;'
            f'border-left:4px solid {color};">'
            f'<div style="font-size:13px;color:#666">五步判定(离散 · gate 式)</div>'
            f'<div style="font-size:20px;font-weight:700;color:{color};margin-top:4px">{verdict}</div>'
            f'<div style="margin-top:4px;font-size:13px">通过 {n_pass} · 警示 {n_warn} · 不及格 {n_fail}</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with col_v2:
        if weighted_score is not None:
            st.markdown(
                f'<div style="padding:14px;border-radius:8px;background:{weighted_color}20;'
                f'border-left:4px solid {weighted_color};">'
                f'<div style="font-size:13px;color:#666">加权综合分(连续 · 同筛选页)</div>'
                f'<div style="font-size:20px;font-weight:700;color:{weighted_color};margin-top:4px">'
                f'{weighted_rating} · {weighted_score:.1f}/100</div>'
                f'<div style="margin-top:4px;font-size:13px">阈值 🟢 ≥75 / 🟡 ≥60 / 🟠 ≥45 / 🔴 &lt;45</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("(加权综合分计算失败)")

    # 视角差异提示(关键!避免用户困惑两套结论不一致)
    if weighted_score is not None:
        same_signal = (
            (n_pass >= 4 and weighted_score >= 75) or
            (n_pass >= 3 and 60 <= weighted_score < 75) or
            (n_pass < 3 and weighted_score < 60)
        )
        if same_signal:
            st.caption(
                f"💡 **两个视角一致**:五步通过 {n_pass}/5 ≈ 加权 {weighted_score:.0f}/100。"
                f"五步是 _{cls_id_used} 类型的 gate 式判定_,加权分是 _类型驱动 5 维评分_,"
                f"两者算法不同但结论同向。"
            )
        else:
            st.warning(
                f"⚠️ **两个视角分歧**:五步通过 {n_pass}/5 vs 加权 {weighted_score:.0f}/100。"
                f"原因:某一项硬伤(如 PEG 或负债率)在五步里独立扣 1 票,"
                f"但在加权分里只占 15-25% 权重,会被其它高分维度对冲。"
                f"**建议**:把五步当_决策 gate_(任一硬伤需复盘),加权分当_整体画像_(高分仍可优秀)。",
                icon="⚠️",
            )

    _render_lynch_price_zones(ticker, cls_id_used, m)

    # 操作按钮
    st.markdown("---")
    col_a, col_b, col_c = st.columns([1, 1, 1])

    with col_a:
        if st.button("💾 写入决策日志", key=f"lynch_save_{ticker}",
                     width="stretch",
                     disabled=(decisions_db is None)):
            try:
                action = "观察" if n_pass < 3 else "买入" if n_pass >= 4 else "观察"
                rationale = (
                    f"林奇五步: ① {CLASS_META[cls_id_used][0]}"
                    + f" · ② CAGR { (rev_5y or 0)*100 :.1f}%"
                    + f" · ③ 负债 {(debt or 0)*100:.0f}%"
                    + f" · 综合通过 {n_pass}/5"
                )
                decisions_db.insert(
                    ticker=ticker, folder=folder,
                    date=_date_cls.today(), action=action,
                    weight_change=0.0, price=0.0,
                    rationale=rationale,
                    thesis_5y=st.session_state.get(f"lynch_story_{ticker}", {}).get("oneline", ""),
                    risks="",
                    tags="林奇五步分析", snapshot={},
                )
                st.success("✅ 已写入 decisions.duckdb", icon="✅")
            except Exception as e:
                st.error(f"❌ 写入失败:{e}")

    with col_b:
        if st.button("📤 导出五步分析 md", key=f"lynch_export_{ticker}",
                     width="stretch"):
            md_path = _export_md(ticker, folder, cls, cls_id_used, m, rows, verdict)
            if md_path:
                st.success(f"✅ 已导出 → `{md_path.relative_to(ROOT)}`", icon="📤")
            else:
                st.error("❌ 导出失败,公司目录未找到")

    with col_c:
        st.caption(f"决策日志:.tools/decisions/decisions.duckdb")
        st.caption(f"md 路径:02_companies/{folder}/05_投资决策/")


def _export_md(ticker: str, folder: str, cls: ClassificationResult,
               cls_id_used: str, m: dict, rows: list[dict], verdict: str) -> Path | None:
    """导出五步分析 md 到 02_companies/{N}_{name}/05_投资决策/。"""
    company_dir = COMPANIES_DIR / folder
    if not company_dir.exists():
        return None
    target_dir = company_dir / "05_投资决策"
    target_dir.mkdir(exist_ok=True)
    today = _date_cls.today().strftime("%Y%m%d")
    md_path = target_dir / f"林奇五步分析_{today}.md"

    story = st.session_state.get(f"lynch_story_{ticker}", {})
    score_state = st.session_state.get(f"lynch_score_{ticker}", {})

    lines = [
        f"# {folder} · 林奇五步分析",
        "",
        f"**分析日期**:{_date_cls.today().strftime('%Y-%m-%d')}",
        f"**Ticker**:{ticker}",
        f"**分析框架**:彼得林奇 GARP + 六类公司分类(`.tools/rules/lynch.yaml`)",
        f"**自动判定类型**:{cls.cls_emoji} {cls.cls_name}(置信度 {cls.confidence*100:.0f}%)",
        f"**采用类型**:{CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]}",
        "",
        "---",
        "",
        "## 第一步:公司分类",
        "",
        f"**自动判定理由**:{cls.reason}",
        "",
        "**关键数据**:",
        "",
    ]
    for k, v in cls.key_metrics.items():
        lines.append(f"- {k}:{v}")
    lines.extend([
        "",
        "**故事脚本**:",
        "",
        f"- 🎯 一句话:{story.get('oneline', '(未填)')}",
        f"- ✅ 验证证据:",
    ])
    for ev_line in (story.get("evidence") or "(未填)").splitlines():
        if ev_line.strip():
            lines.append(f"  - {ev_line.strip()}")
    lines.extend([
        f"- ❌ 不会发生的事:{story.get('not_happen', '(未填)')}",
        "",
        "---",
        "",
        "## 第二步:成长核查",
        "",
        f"- 营收 5y CAGR:{(m.get('rev_cagr_5y') or 0)*100:.1f}%",
        f"- 营收 3y CAGR:{(m.get('rev_cagr_3y') or 0)*100:.1f}%",
        f"- 最新净利 YoY:{(m.get('np_yoy_recent') or 0)*100:.1f}%",
        "",
        "---",
        "",
        "## 第三步:财务护栏",
        "",
        f"- 资产负债率:{(m.get('debt_ratio') or 0)*100:.1f}%(类型阈值 {guardrail_thresholds_for(cls_id_used, m.get('industry_sw_l1') or '')['debt_ratio_max']*100:.0f}%)",
        "",
        "---",
        "",
        "## 第四步:PEG 估值",
        "",
    ])
    pe = m.get("pe_ttm")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    peg_cfg = PEG_BY_TYPE.get(cls_id_used, PEG_BY_TYPE["stalwart"])
    if peg_cfg["applicable"] and pe and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        lines.append(f"- PE-TTM:{pe:.1f}")
        lines.append(f"- CAGR:{cagr*100:.1f}%")
        lines.append(f"- **PEG = {peg:.2f}**(目标 ≤ {peg_cfg['target']})")
    else:
        lines.append(f"- {peg_cfg['note']}")
    lines.extend([
        "",
        "---",
        "",
        "## 第五步:故事更新",
        "",
    ])
    if score_state:
        avg = sum(score_state.values()) / max(len(score_state), 1)
        lines.append(f"- 兑现度:{avg:.0f}%")
        for k, v in score_state.items():
            lines.append(f"  - {k}:{v}")
    else:
        lines.append("- 未打分")
    lines.extend([
        "",
        "---",
        "",
        "## 综合结论",
        "",
        f"**{verdict}**",
        "",
        "| 步骤 | 结果 | 状态 |",
        "| --- | --- | --- |",
    ])
    for r in rows:
        lines.append(f"| {r['步骤']} | {r['结果']} | {r['状态']} |")
    lines.extend([
        "",
        "---",
        "",
        f"**生成工具**:`.tools/dashboard/tabs/lynch_analysis.py`",
        f"**对照模板**:`02_companies/01_新华保险/05_投资决策/02_格雷厄姆投资法_新华保险五步分析.md`",
    ])

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


# ─── 主入口 ─────────────────────────────────────────────────────────────
