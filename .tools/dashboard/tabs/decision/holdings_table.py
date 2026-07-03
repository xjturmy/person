"""统一持仓 / 观察池明细表(v2.8+:active + watch 同列展示)。

active 行显示完整列(股数 / 成本 / 浮盈 / 实际权重 / 偏离),
watch 行对 active-only 列显示 "—"。

模块独立 — 不依赖 decision_center.py 内部状态,可在任意 tab 调用。
"""
from __future__ import annotations

import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

import pandas as pd

# ─── 路径准备 ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
_PORTFOLIO_DIR = ROOT / ".tools" / "portfolio"
_DASH_DIR = ROOT / ".tools" / "dashboard"
for _p in (_PORTFOLIO_DIR, _DASH_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from holdings_view import HoldingsSnapshot  # noqa: E402

# ─── streamlit 软依赖(离线 smoke 不需要)──────────────────
try:
    import streamlit as st  # type: ignore
    _HAS_ST = True
except Exception:  # pragma: no cover
    st = None  # type: ignore
    _HAS_ST = False


# ─── fair_price 懒加载(避免与并行 agent 抢 import 顺序)──
_FAIR_MOD: Any = None


def _load_fair_price_module() -> Any:
    global _FAIR_MOD
    if _FAIR_MOD is not None:
        return _FAIR_MOD
    fp_path = _DASH_DIR / "valuation" / "fair_price.py"
    _FAIR_MOD = SourceFileLoader("fair_price_ht", str(fp_path)).load_module()
    return _FAIR_MOD


def _fair_range_for(ticker: str, name: str):
    """带 5min 缓存的 compute_fair_range(streamlit 上下文外退化为普通调用)。"""
    mod = _load_fair_price_module()
    if _HAS_ST:
        @st.cache_data(ttl=300, show_spinner=False)
        def _cached(_t: str, _n: str):
            return mod.compute_fair_range(_t, _n)
        # cache_data 不能装饰局部闭包多次 — 用 session_state 单例
        key = "_holdings_table_fair_cache"
        if key not in st.session_state:
            st.session_state[key] = {}
        cache = st.session_state[key]
        ck = (ticker, name)
        if ck not in cache:
            try:
                cache[ck] = mod.compute_fair_range(ticker, name)
            except Exception:
                cache[ck] = None
        return cache[ck]
    try:
        return mod.compute_fair_range(ticker, name)
    except Exception:
        return None


def _load_school_map() -> dict[str, str]:
    """从 portfolio.yaml 读 ticker → school 映射。"""
    try:
        mod = _load_fair_price_module()
        entries = mod.load_portfolio()
        return {t: (e.school or "—") for t, e in entries.items()}
    except Exception:
        return {}


# ─── 渲染 ──────────────────────────────────────────────────
_STATUS_EMOJI = {"active": "🟢 active", "watch": "👀 watch", "exited": "⚪ exited"}


def render(snap: HoldingsSnapshot, include_watch: bool = True) -> None:
    """渲染统一持仓 / 观察池明细表。

    Args:
        snap: HoldingsSnapshot — 含 rows(active + watch + exited)
        include_watch: 是否把 watch 行一起渲染(False 时仅显示 active)
    """
    if not _HAS_ST:
        return  # 非 streamlit 上下文静默(供 smoke 调用不报错)

    statuses = {"active"} | ({"watch"} if include_watch else set())
    rows = [r for r in snap.rows if r.status in statuses]
    if not rows:
        st.info("📋 暂无 active / watch 行 — 请在 .tools/portfolio/portfolio.yaml 增加 holdings。")
        return

    school_map = _load_school_map()

    records: list[dict[str, Any]] = []
    for r in rows:
        fair = _fair_range_for(r.ticker, r.name)
        graham = getattr(fair, "graham_number", None) if fair else None
        verified = bool(getattr(fair, "verified", False)) if fair else False
        verdict = getattr(fair, "verdict_label", None) if fair else None
        low_line = (graham * 0.85) if (verified and graham) else None
        gap_pct = None
        if r.last_price is not None and low_line:
            gap_pct = (r.last_price - low_line) / low_line

        is_active = r.status == "active"
        records.append({
            "状态": _STATUS_EMOJI.get(r.status, r.status),
            "公司": r.name,
            "代码": r.ticker,
            "流派": school_map.get(r.ticker, "—"),
            "现价": r.last_price,
            "合理价(Graham)": graham if verified else None,
            "距低估%": gap_pct,
            "档位": verdict or "—",
            "F-Score": r.fscore,
            "PE 分位(10y)": r.pe_pct,
            "目标权重": r.target_weight,
            # active-only(watch 显示 —)
            "股数": r.shares if is_active else None,
            "成本价": r.cost_basis if is_active else None,
            "市值": r.market_value if is_active else None,
            "浮盈": r.pnl if is_active else None,
            "浮盈%": r.pnl_pct if is_active else None,
            "实际权重": r.actual_weight if is_active else None,
            "偏离": r.deviation if is_active else None,
        })

    df = pd.DataFrame(records)

    def _pnl_color(v):
        if not isinstance(v, (int, float)) or pd.isna(v):
            return ""
        if v > 0:
            return "color: #1b8a3a; font-weight:600"
        if v < 0:
            return "color: #d9534f; font-weight:600"
        return ""

    def _gap_color(v):
        if not isinstance(v, (int, float)) or pd.isna(v):
            return ""
        if v <= 0:
            return "color: #1b8a3a; font-weight:600"
        if v > 0.15:
            return "color: #d9534f; font-weight:600"
        return "color: #c08a00; font-weight:600"

    styler = (
        df.style
        .map(_pnl_color, subset=["浮盈", "浮盈%", "偏离"])
        .map(_gap_color, subset=["距低估%"])
        .format({
            "现价": "{:.2f}",
            "合理价(Graham)": "{:.2f}",
            "距低估%": "{:+.1%}",
            "成本价": "{:.2f}",
            "股数": "{:,.0f}",
            "市值": "¥{:,.0f}",
            "浮盈": "¥{:+,.0f}",
            "浮盈%": "{:+.2%}",
            "实际权重": "{:.1%}",
            "目标权重": "{:.0%}",
            "偏离": "{:+.1%}",
            "PE 分位(10y)": "{:.1%}",
        }, na_rep="—")
    )

    n_active = sum(1 for r in rows if r.status == "active")
    n_watch = sum(1 for r in rows if r.status == "watch")
    st.markdown(f"**📋 统一持仓 / 观察池明细**  ·  active {n_active} · watch {n_watch}")
    st.dataframe(styler, width="stretch", hide_index=True)
