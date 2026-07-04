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
    padding: 10px 12px;
    font-family: -apple-system, "Inter", "PingFang SC", sans-serif;
}
.ij-head {
    align-items: center;
    display: flex;
    gap: 12px;
    justify-content: space-between;
}
.ij-title {
    color: #111827;
    font-size: 16px;
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
    border-radius: 8px;
    color: var(--ij-fg, #1D4ED8);
    flex: 0 0 auto;
    font-size: 18px;
    font-weight: 780;
    line-height: 1;
    min-width: 88px;
    padding: 8px 12px;
    text-align: center;
}
.ij-grid {
    display: grid;
    gap: 7px;
    grid-template-columns: 0.9fr 1fr 1.45fr;
    margin-top: 8px;
}
.ij-panel {
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 7px;
    min-height: 0;
    padding: 8px 9px;
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
    font-size: 15px;
    font-weight: 750;
    line-height: 1.25;
}
.ij-note {
    color: #4B5563;
    font-size: 12px;
    line-height: 1.3;
    margin-top: 3px;
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
.ij-bottom {
    align-items: stretch;
    display: grid;
    gap: 7px;
    grid-template-columns: 1.35fr 1fr;
    margin-top: 7px;
}
.ij-next {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    color: #1F2937;
    font-size: 12px;
    line-height: 1.35;
    padding: 8px 9px;
}
.ij-invalid {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    border-radius: 8px;
    color: #7C2D12;
    font-size: 12px;
    line-height: 1.35;
    padding: 8px 9px;
}
@media (max-width: 900px) {
    .ij-head,
    .ij-bottom {
        display: block;
    }
    .ij-action {
        margin-top: 8px;
    }
    .ij-grid {
        grid-template-columns: 1fr;
    }
    .ij-invalid {
        margin-top: 8px;
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
        return "数据不足", "缺估值分位，暂不做价格结论"
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return "数据不足", "估值数据不可用"
    if pct < 0.30:
        return "买入观察区", "估值处低分位，值得进入方法内价格核查"
    if pct <= 0.55:
        return "合理偏低", "价格未明显透支，适合结合方法继续判断"
    if pct <= 0.75:
        return "合理偏贵", "不适合追价，已有仓位以持有观察为主"
    return "偏贵/减仓区", "估值分位偏高，需要等待价格或基本面改善"


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

    if "偏贵" in price_zone and overall < 70:
        action = "观察"
    elif "买入" in price_zone and overall >= 65 and (safety_score or 0) >= 50:
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
    elif "买入" in price_zone:
        method = "格雷厄姆"
    elif (profit_score or 0) >= 70:
        method = "芒格质量判断"

    period = (latest_period or {}).get("label") or "最新财报期"
    reasons = [
        f"主方法先按「{method}」校准，避免多方法混用",
        f"价格处于「{price_zone}」：{price_note}",
        f"{period} 下综合评分 {_score_status(float(overall))}，安全项 {_score_status(safety_score)}",
    ]
    invalidations = [
        "主方法判定不适配该公司",
        "价格越过方法内卖出/减仓线",
        "最新财报触发增长、现金流或负债硬伤",
    ]

    if action == "买入":
        next_step = "进入方法内价格区间页，确认买入线与仓位上限后再分批执行。"
    elif action == "持有":
        next_step = "维持观察，下一次复查放在新财报或价格触发区间变化时。"
    elif action == "观察":
        next_step = "暂不追价，等待价格回到买入区或基本面继续验证。"
    else:
        next_step = "先补齐方法适配和关键数据，再做买卖判断。"

    return {
        "action": action,
        "method": method,
        "price_zone": price_zone,
        "price_note": price_note,
        "reasons": reasons,
        "next_step": next_step,
        "invalidations": invalidations,
        "ticker": ticker,
        "name": score_dict.get("name") or ticker,
    }


def render_preview(judgement: dict[str, Any]) -> None:
    action = judgement.get("action") or "暂不判断"
    accent, bg, border, fg = _ACTION_STYLE.get(action, _ACTION_STYLE["暂不判断"])
    reasons = judgement.get("reasons") or []
    invalidations = judgement.get("invalidations") or []
    reason_html = "".join(f"<li>{escape(str(item))}</li>" for item in reasons[:2])
    invalid_html = "；".join(escape(str(item)) for item in invalidations[:3])
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
        f'  <div class="ij-grid">'
        f'    <div class="ij-panel">'
        f'      <div class="ij-label">主判断方法</div>'
        f'      <div class="ij-main">{escape(str(judgement.get("method") or "—"))}</div>'
        f'      <div class="ij-note">先看方法是否适配</div>'
        f'    </div>'
        f'    <div class="ij-panel">'
        f'      <div class="ij-label">价格位置</div>'
        f'      <div class="ij-main">{escape(str(judgement.get("price_zone") or "—"))}</div>'
        f'      <div class="ij-note">{escape(str(judgement.get("price_note") or ""))}</div>'
        f'    </div>'
        f'    <div class="ij-panel">'
        f'      <div class="ij-label">核心理由</div>'
        f'      <ul class="ij-list">{reason_html}</ul>'
        f'    </div>'
        f'  </div>'
        f'  <div class="ij-bottom">'
        f'    <div class="ij-next"><strong>下一步：</strong>{escape(str(judgement.get("next_step") or ""))}</div>'
        f'    <div class="ij-invalid"><strong>失效条件：</strong>{invalid_html}</div>'
        f'  </div>'
        f'</section>',
        unsafe_allow_html=True,
    )
