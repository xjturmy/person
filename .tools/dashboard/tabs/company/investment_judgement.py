"""Company overview investment judgement cockpit preview."""
from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st


_CSS = """
<style>
.ij-wrap {
    background: #FFFFFF;
    border: 1px solid #D8DEE8;
    border-left: 4px solid var(--ij-accent, #2563EB);
    border-radius: 8px;
    margin: 8px 0 12px;
    padding: 9px 11px 10px;
    font-family: -apple-system, "Inter", "PingFang SC", sans-serif;
}
.ij-head {
    align-items: center;
    display: flex;
    gap: 10px;
    justify-content: space-between;
}
.ij-title {
    color: #111827;
    font-size: 15px;
    font-weight: 760;
    line-height: 1.25;
}
.ij-subtitle {
    color: #6B7280;
    font-size: 12px;
    line-height: 1.35;
    margin-top: 2px;
}
.ij-action {
    background: var(--ij-bg, #EFF6FF);
    border: 1px solid var(--ij-border, #BFDBFE);
    border-radius: 7px;
    color: var(--ij-fg, #1D4ED8);
    flex: 0 0 auto;
    font-size: 17px;
    font-weight: 780;
    line-height: 1;
    min-width: 78px;
    padding: 7px 10px;
    text-align: center;
}
.ij-strip {
    align-items: stretch;
    display: grid;
    gap: 0;
    grid-template-columns: 0.9fr 1.15fr 1.05fr 1.25fr;
    margin-top: 8px;
}
.ij-cell {
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-left: 0;
    min-height: 0;
    padding: 7px 9px;
}
.ij-cell:first-child {
    border-left: 1px solid #E5E7EB;
    border-radius: 7px 0 0 7px;
}
.ij-cell:last-child {
    border-radius: 0 7px 7px 0;
}
.ij-label {
    color: #6B7280;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0;
    line-height: 1.2;
    margin-bottom: 6px;
}
.ij-main {
    color: #111827;
    font-size: 14px;
    font-weight: 750;
    line-height: 1.25;
}
.ij-note {
    color: #4B5563;
    font-size: 12px;
    line-height: 1.3;
    margin-top: 3px;
}
.ij-evidence {
    display: grid;
    gap: 7px;
    grid-template-columns: 1.15fr 0.85fr;
    margin-top: 7px;
}
.ij-block {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 7px;
    padding: 8px 9px;
}
.ij-list {
    color: #374151;
    font-size: 12px;
    line-height: 1.35;
    margin: 0;
    padding-left: 16px;
}
.ij-list li {
    margin: 0 0 2px;
}
.ij-invalid {
    color: #7C2D12;
}
.ij-invalid .ij-list {
    color: #7C2D12;
}
@media (max-width: 900px) {
    .ij-head {
        display: block;
    }
    .ij-action {
        margin-top: 8px;
    }
    .ij-strip,
    .ij-evidence {
        grid-template-columns: 1fr;
    }
    .ij-cell,
    .ij-cell:first-child,
    .ij-cell:last-child {
        border: 1px solid #E5E7EB;
        border-radius: 7px;
        margin-top: 6px;
    }
}
</style>
"""

_ACTION_STYLE = {
    "买入": ("#16A34A", "#DCFCE7", "#BBF7D0", "#166534"),
    "持有": ("#2563EB", "#EFF6FF", "#BFDBFE", "#1D4ED8"),
    "观察": ("#D97706", "#FFFBEB", "#FDE68A", "#92400E"),
    "减仓": ("#EA580C", "#FFF7ED", "#FDBA74", "#9A3412"),
    "卖出": ("#DC2626", "#FEF2F2", "#FECACA", "#991B1B"),
    "暂不判断": ("#6B7280", "#F3F4F6", "#E5E7EB", "#374151"),
}


def _dim(score_dict: dict[str, Any], key: str) -> dict[str, Any]:
    try:
        return score_dict.get("dims", {}).get(key, {}) or {}
    except Exception:
        return {}


def _score_status(score: float | None) -> str:
    if score is None:
        return "数据不足"
    if score >= 75:
        return "强"
    if score >= 60:
        return "合格"
    if score >= 45:
        return "警戒"
    return "弱"


def _price_zone(raw: float | None) -> tuple[str, str]:
    if raw is None:
        return "不适合判断", "缺估值分位，先不下价格结论"
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return "不适合判断", "估值数据不可用"
    if pct < 0.30:
        return "便宜", "进入方法内买入线核查"
    if pct <= 0.55:
        return "合理", "可继续做方法内判断"
    if pct <= 0.75:
        return "偏贵", "不追价，已有仓位以持有观察为主"
    return "偏贵", "等待价格回落或基本面抬升"


def _reason_list(
    method: str,
    price_zone: str,
    price_note: str,
    period: str,
    overall: float,
    safety_score: float | None,
) -> list[str]:
    reasons = [
        f"先按「{method}」判断，避免多方法互相抵消",
        f"价格「{price_zone}」：{price_note}",
        f"{period} 综合 {_score_status(float(overall))}，安全项 {_score_status(safety_score)}",
    ]
    return reasons[:3]


def build_preview_judgement(
    ticker: str,
    score_dict: dict[str, Any],
    latest_period: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lightweight preview rules for the company overview cockpit."""
    valuation = _dim(score_dict, "valuation")
    safety = _dim(score_dict, "safety")
    growth = _dim(score_dict, "growth")
    profitability = _dim(score_dict, "profitability")

    overall = score_dict.get("overall") or 0.0
    price_zone, price_note = _price_zone(valuation.get("raw"))
    safety_score = safety.get("score")
    growth_score = growth.get("score")
    profit_score = profitability.get("score")

    if price_zone == "偏贵" and overall < 70:
        action = "观察"
    elif price_zone == "便宜" and overall >= 65 and (safety_score or 0) >= 50:
        action = "买入"
    elif overall >= 60:
        action = "持有"
    elif overall >= 45:
        action = "观察"
    else:
        action = "暂不判断"

    method = "林奇/格雷厄姆待校准"
    category = str(score_dict.get("category") or "")
    if "保险" in category or "insurance" in category.lower():
        method = "保险专属"
    elif (growth_score or 0) >= 65:
        method = "林奇"
    elif price_zone == "便宜":
        method = "格雷厄姆"
    elif (profit_score or 0) >= 70:
        method = "芒格质量判断"

    period = (latest_period or {}).get("label") or "最新财报期"
    reasons = _reason_list(method, price_zone, price_note, period, overall, safety_score)
    invalidations = [
        "主方法被证伪，暂停沿用原判断",
        "价格越过方法内卖出/减仓线",
        "新财报出现增长、现金流或负债硬伤",
    ]

    if action == "买入":
        next_step = "确认买入线和仓位上限后，只分批执行。"
    elif action == "持有":
        next_step = "未触发卖出条件，新财报或价格越线再复查。"
    elif action == "观察":
        next_step = "暂不追价，等价格回到区间或基本面继续验证。"
    else:
        next_step = "先补齐方法适配和关键数据，再谈买卖。"

    review_trigger = "季报/年报或价格越线"
    if action == "买入":
        review_trigger = "买入线、仓位上限"
    elif action == "暂不判断":
        review_trigger = "方法适配、关键数据"

    return {
        "action": action,
        "method": method,
        "price_zone": price_zone,
        "price_note": price_note,
        "reasons": reasons,
        "next_step": next_step,
        "invalidations": invalidations,
        "review_trigger": review_trigger,
        "ticker": ticker,
        "name": score_dict.get("name") or ticker,
    }


def render_preview(judgement: dict[str, Any]) -> None:
    action = judgement.get("action") or "暂不判断"
    accent, bg, border, fg = _ACTION_STYLE.get(action, _ACTION_STYLE["暂不判断"])
    reasons = judgement.get("reasons") or []
    invalidations = judgement.get("invalidations") or []
    reason_html = "".join(f"<li>{escape(str(item))}</li>" for item in reasons[:3])
    invalid_html = "".join(f"<li>{escape(str(item))}</li>" for item in invalidations[:3])
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<section class="ij-wrap" style="--ij-accent:{accent};--ij-bg:{bg};'
        f'--ij-border:{border};--ij-fg:{fg};">'
        f'  <div class="ij-head">'
        f'    <div>'
        f'      <div class="ij-title">当前投资判断</div>'
        f'      <div class="ij-subtitle">先回答该不该动、依据什么、错了怎么办</div>'
        f'    </div>'
        f'    <div class="ij-action">{escape(action)}</div>'
        f'  </div>'
        f'  <div class="ij-strip">'
        f'    <div class="ij-cell">'
        f'      <div class="ij-label">价格状态</div>'
        f'      <div class="ij-main">{escape(str(judgement.get("price_zone") or "—"))}</div>'
        f'      <div class="ij-note">{escape(str(judgement.get("price_note") or ""))}</div>'
        f'    </div>'
        f'    <div class="ij-cell">'
        f'      <div class="ij-label">主方法</div>'
        f'      <div class="ij-main">{escape(str(judgement.get("method") or "—"))}</div>'
        f'      <div class="ij-note">不混用口径</div>'
        f'    </div>'
        f'    <div class="ij-cell">'
        f'      <div class="ij-label">复查触发</div>'
        f'      <div class="ij-main">{escape(str(judgement.get("review_trigger") or "季报/年报或价格越线"))}</div>'
        f'      <div class="ij-note">触发再改判断</div>'
        f'    </div>'
        f'    <div class="ij-cell">'
        f'      <div class="ij-label">下一步纪律</div>'
        f'      <div class="ij-main">{escape(str(judgement.get("next_step") or "—"))}</div>'
        f'    </div>'
        f'  </div>'
        f'  <div class="ij-evidence">'
        f'    <div class="ij-block">'
        f'      <div class="ij-label">核心理由</div>'
        f'      <ul class="ij-list">{reason_html}</ul>'
        f'    </div>'
        f'    <div class="ij-block ij-invalid">'
        f'      <div class="ij-label">失效条件</div>'
        f'      <ul class="ij-list">{invalid_html}</ul>'
        f'    </div>'
        f'  </div>'
        f'</section>',
        unsafe_allow_html=True,
    )
