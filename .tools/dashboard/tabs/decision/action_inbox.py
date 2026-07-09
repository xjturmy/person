"""🚨 待办动作区块 — 决策中心首屏 active=0 时的零空白填充。

5 类信号:
- 🟢 已跌破低估线   (距 graham_number × 0.85 ≤ 0,仅 verified=True)
- 🔥 估值过热       (pe_pct ≥ 0.85)
- 🔴 F-Score 跌破   (fscore < 4)
- ⚖️ 偏离过大       (|deviation| > 0.05,active 持仓)
- 💰 现金偏离       (|cash_ratio - (1-target_equity_ratio)| > 0.05)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

import streamlit as st

# ─── sys.path 注入 ───────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
for _p in (ROOT / ".tools" / "portfolio", ROOT / ".tools" / "dashboard"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from holdings_view import HoldingsSnapshot, HoldingRow  # noqa: E402


# ─── fair_price 懒加载(SourceFileLoader,避免硬依赖)─────────────────
def _load_fair_price():
    fp_path = ROOT / ".tools" / "dashboard" / "valuation" / "fair_price.py"
    try:
        return SourceFileLoader("fair_price_inbox", str(fp_path)).load_module()
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _cached_fair_range(ticker: str, name: str) -> dict | None:
    """缓存的 compute_fair_range 包装 — 返回纯 dict 避免 dataclass 序列化坑。"""
    fp = _load_fair_price()
    if fp is None:
        return None
    try:
        rng = fp.compute_fair_range(ticker, name)
    except Exception:
        return None
    return {
        "verified": bool(getattr(rng, "verified", False)),
        "graham_number": getattr(rng, "graham_number", None),
        "current_price": getattr(rng, "current_price", None),
    }


# ─── 信号 dataclass ─────────────────────────────────────────────────
@dataclass
class _Signal:
    sev: int      # 排序权重 越大越急
    emoji: str
    title: str
    detail: str   # "公司名 (ticker) · 数值"


def _detect(snap: HoldingsSnapshot) -> list[_Signal]:
    sigs: list[_Signal] = []
    for r in snap.rows:
        pos_band = getattr(r, "position_band", None) or {}
        if r.status == "active" and isinstance(pos_band, dict):
            max_w = pos_band.get("max_weight")
            target_w = pos_band.get("target_weight")
            role = pos_band.get("role") or "仓位"
            if max_w is not None and r.actual_weight > float(max_w):
                sigs.append(_Signal(
                    sev=6, emoji="⚖️", title="超过类型上限",
                    detail=f"{r.name} ({r.ticker}) · {role} 当前 {r.actual_weight * 100:.1f}% > 上限 {float(max_w) * 100:.0f}%",
                ))
            elif target_w is not None and r.actual_weight > float(target_w) + 0.02:
                sigs.append(_Signal(
                    sev=3, emoji="⚖️", title="高于目标仓位",
                    detail=f"{r.name} ({r.ticker}) · {role} 当前 {r.actual_weight * 100:.1f}% > 目标 {float(target_w) * 100:.0f}%",
                ))

        band = getattr(r, "price_band", None) or {}
        manual_hit = False
        if isinstance(band, dict) and r.last_price is not None:
            px = float(r.last_price)
            stop_loss = band.get("stop_loss_below")
            add_below = band.get("add_below")
            buy_below = band.get("buy_below")
            trim_above = band.get("trim_above")
            exit_above = band.get("exit_above")
            if stop_loss is not None and px <= float(stop_loss):
                manual_hit = True
                sigs.append(_Signal(
                    sev=6, emoji="🔴", title="跌破人工失效线",
                    detail=f"{r.name} ({r.ticker}) · 现价 {px:g} ≤ {float(stop_loss):g}",
                ))
            elif add_below is not None and px <= float(add_below):
                manual_hit = True
                sigs.append(_Signal(
                    sev=4, emoji="🟢", title="人工加仓区",
                    detail=f"{r.name} ({r.ticker}) · 现价 {px:g} ≤ {float(add_below):g}",
                ))
            elif buy_below is not None and px <= float(buy_below):
                manual_hit = True
                sigs.append(_Signal(
                    sev=3, emoji="🟢", title="人工买入区",
                    detail=f"{r.name} ({r.ticker}) · 现价 {px:g} ≤ {float(buy_below):g}",
                ))
            elif exit_above is not None and px >= float(exit_above):
                manual_hit = True
                sigs.append(_Signal(
                    sev=6, emoji="🔥", title="人工清仓评估",
                    detail=f"{r.name} ({r.ticker}) · 现价 {px:g} ≥ {float(exit_above):g}",
                ))
            elif trim_above is not None and px >= float(trim_above):
                manual_hit = True
                sigs.append(_Signal(
                    sev=4, emoji="🟡", title="人工减仓区",
                    detail=f"{r.name} ({r.ticker}) · 现价 {px:g} ≥ {float(trim_above):g}",
                ))

        # 🔴 F-Score 跌破
        if r.fscore is not None and r.fscore < 4:
            sigs.append(_Signal(
                sev=5, emoji="🔴", title="触发清仓评估",
                detail=f"{r.name} ({r.ticker}) · F={r.fscore}",
            ))
        # 🔥 估值过热
        if r.pe_pct is not None and r.pe_pct >= 0.85:
            sigs.append(_Signal(
                sev=4, emoji="🔥", title="评估减仓",
                detail=f"{r.name} ({r.ticker}) · PE 分位 {r.pe_pct * 100:.1f}%",
            ))
        # ⚖️ 偏离过大(仅 active)
        if r.status == "active" and r.deviation is not None and abs(r.deviation) > 0.05:
            sigs.append(_Signal(
                sev=3, emoji="⚖️", title="再平衡",
                detail=f"{r.name} ({r.ticker}) · 偏离 {r.deviation * 100:+.1f}%",
            ))
        # 🟢 已跌破低估线
        rng = _cached_fair_range(r.ticker, r.name)
        if not manual_hit and rng and rng["verified"] and rng["graham_number"] and r.last_price:
            low_line = rng["graham_number"] * 0.85
            if r.last_price <= low_line:
                gap_pct = (r.last_price / low_line - 1) * 100
                sigs.append(_Signal(
                    sev=2, emoji="🟢", title="加仓区间",
                    detail=f"{r.name} ({r.ticker}) · 距低估线 {gap_pct:+.1f}%",
                ))

    # 💰 现金偏离
    target_cash = 1.0 - (snap.target_equity_ratio or 0.0)
    cash_dev = (snap.cash_ratio or 0.0) - target_cash
    if abs(cash_dev) > 0.05:
        verb = "补仓" if cash_dev > 0 else "减仓"
        sigs.append(_Signal(
            sev=1, emoji="💰", title=f"现金偏离 · {verb}",
            detail=f"现金 {snap.cash_ratio * 100:.1f}% vs 目标 {target_cash * 100:.1f}%"
                   f" · 偏离 {cash_dev * 100:+.1f}%",
        ))

    sigs.sort(key=lambda s: -s.sev)
    return sigs


def render(snap: HoldingsSnapshot) -> None:
    """渲染🚨待办动作区块到 streamlit。"""
    sigs = _detect(snap)
    n = len(sigs)
    st.markdown(f"### 🚨 待办动作 · {n} 项")

    if n == 0:
        st.success("✅ 当前无急办事项,持仓状态良好")
        return

    # 横排 5 张迷你卡(超过 5 条则只展示 sev 最高的 5 条)
    top = sigs[:5]
    cols = st.columns(5)
    for col, s in zip(cols, top):
        with col:
            st.markdown(
                f"<div style='padding:10px 12px;border:1px solid #e0e0e0;"
                f"border-radius:8px;background:#fafafa;height:100%;'>"
                f"<div style='font-size:22px;line-height:1'>{s.emoji}</div>"
                f"<div style='font-weight:600;margin:6px 0 4px;font-size:13px'>"
                f"{s.title}</div>"
                f"<div style='font-size:12px;color:#555'>{s.detail}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if n > 5:
        with st.expander(f"其余 {n - 5} 项待办"):
            for s in sigs[5:]:
                st.markdown(f"- {s.emoji} **{s.title}** · {s.detail}")
