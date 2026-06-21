"""持仓动作面板 — 清仓 / 取消 watch / 彻底删除 的统一入口。

设计要点:
- 三段都常驻可见(段 1/2 用 disabled 状态而非整段消失),不论 active=0 还是 watch=0,
  用户都能看到对应的提示与按钮。
- 段 1 卖出归档(软删 status=exited)+ 自动写决策日志(action=清仓)。
- 段 2 取消 watch(物理移除,loader.delete_holding 自带 .bak 备份)。
- 段 3 彻底删除藏在 expander 里 + 二次确认勾选。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".tools" / "portfolio"))
sys.path.insert(0, str(ROOT / ".tools" / "dashboard"))

from holdings_view import HoldingsSnapshot  # noqa: E402
import loader as _loader  # noqa: E402


_SELL_REASONS = [
    "估值过热触发止盈",
    "基本面恶化",
    "调结构",
    "自定义…",
]
_CANCEL_REASONS = [
    "改观察方向",
    "失去兴趣",
    "录错",
    "自定义…",
]
_PLACEHOLDER = "— 请选择 —"


def _label(row) -> str:
    name = getattr(row, "name", "") or row.ticker
    return f"{name}({row.ticker})"


def _write_decision_log(ticker: str, reason: str, exit_price: float) -> str | None:
    """写卖出归档的决策日志。返回错误信息(None=成功)。"""
    try:
        sys.path.insert(0, str(ROOT / ".tools"))
        from decisions import db as _ddb
        from decisions import snapshot as _dsnap
        try:
            snap_d = _dsnap.capture(ticker)
        except Exception:
            snap_d = {}
        _ddb.insert(
            ticker=ticker, folder="",
            date=date.today(), action="清仓",
            weight_change=0.0, price=float(exit_price),
            rationale=reason, thesis_5y="", risks="", tags="auto-close",
            snapshot=snap_d,
        )
        return None
    except Exception as e:
        return f"决策日志写入失败:{e}"


def _call_close_holding(ticker: str, reason: str, exit_price: float) -> tuple[bool, str]:
    """优先用新签名,失败回退到老签名。返回 (ok, message)。"""
    fn = getattr(_loader, "close_holding", None)
    if fn is None:
        return False, "loader.close_holding 不存在 — 请先升级 loader 或手填 yaml。"
    # 试新签名
    try:
        fn(ticker, reason, exit_price=exit_price)
        return True, f"已软删 {ticker}(status=exited, exit_price={exit_price:.2f})"
    except TypeError:
        pass
    except Exception as e:
        return False, f"close_holding 调用失败:{e}"
    # 回退老签名
    try:
        fn(ticker, reason)
        return True, f"已软删 {ticker}(老签名,exit_price 请在 yaml 手填)"
    except Exception as e:
        return False, f"close_holding 老签名也失败:{e}"


def _call_delete_holding(ticker: str) -> tuple[bool, str]:
    fn = getattr(_loader, "delete_holding", None)
    if fn is None:
        return False, "loader.delete_holding 不存在。"
    try:
        fn(ticker)
        return True, f"已彻底移除 {ticker}(.bak 备份已生成)"
    except Exception as e:
        return False, f"delete_holding 调用失败:{e}"


# ─── 段 1:清仓 / 卖出归档 ─────────────────────────────────────────────
def _render_close_section(snap: HoldingsSnapshot) -> None:
    st.markdown("#### 📤 段 1:清仓 / 卖出归档(active)")
    actives = [r for r in snap.rows if r.status == "active"]
    if not actives:
        st.caption("(无 active 持仓 — 此段当前不可用)")
        st.selectbox("选 active 持仓", [_PLACEHOLDER], disabled=True, key="ha_sell_pick_disabled")
        st.button("📤 一键清仓归档", disabled=True, key="ha_sell_btn_disabled")
        return

    options = [_PLACEHOLDER] + [_label(r) for r in actives]
    pick = st.selectbox("选 active 持仓", options, key="ha_sell_pick")
    chosen = None
    if pick != _PLACEHOLDER:
        chosen = actives[options.index(pick) - 1]

    default_px = float(chosen.last_price) if chosen and chosen.last_price else 0.0
    exit_price = st.number_input(
        "卖出价",
        min_value=0.0, value=default_px, step=0.01,
        key="ha_sell_price",
        disabled=chosen is None,
    )
    reason_pick = st.selectbox("卖出原因", _SELL_REASONS, key="ha_sell_reason")
    if reason_pick == "自定义…":
        custom = st.text_input("自定义原因", key="ha_sell_reason_custom").strip()
        reason = custom
    else:
        reason = reason_pick

    ready = (chosen is not None) and (exit_price > 0) and bool(reason)
    if st.button("📤 一键清仓归档", disabled=not ready, key="ha_sell_btn"):
        ok, msg = _call_close_holding(chosen.ticker, reason, float(exit_price))
        if ok:
            err = _write_decision_log(chosen.ticker, reason, float(exit_price))
            st.success(msg)
            if err:
                st.warning(err)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)


# ─── 段 2:取消 watch 持仓 ────────────────────────────────────────────
def _render_cancel_section(snap: HoldingsSnapshot) -> None:
    st.markdown("#### ❌ 段 2:取消 watch 持仓")
    watches = [r for r in snap.rows if r.status == "watch"]
    if not watches:
        st.caption("(无 watch 持仓 — 此段当前不可用)")
        st.selectbox("选 watch 持仓", [_PLACEHOLDER], disabled=True, key="ha_cancel_pick_disabled")
        st.button("❌ 一键取消", disabled=True, key="ha_cancel_btn_disabled")
        return

    options = [_PLACEHOLDER] + [_label(r) for r in watches]
    pick = st.selectbox("选 watch 持仓", options, key="ha_cancel_pick")
    chosen = None
    if pick != _PLACEHOLDER:
        chosen = watches[options.index(pick) - 1]

    reason_pick = st.selectbox("取消原因", _CANCEL_REASONS, key="ha_cancel_reason")
    if reason_pick == "自定义…":
        custom = st.text_input("自定义原因", key="ha_cancel_reason_custom").strip()
        reason = custom
    else:
        reason = reason_pick

    ready = (chosen is not None) and bool(reason)
    if st.button("❌ 一键取消(物理移除,有 .bak 备份)", disabled=not ready, key="ha_cancel_btn"):
        ok, msg = _call_delete_holding(chosen.ticker)
        if ok:
            st.success(f"{msg} · 原因:{reason}")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)


# ─── 段 3:彻底删除(危险操作) ───────────────────────────────────────
def _render_hard_delete_section(snap: HoldingsSnapshot) -> None:
    with st.expander("🔥 段 3:彻底删除(危险 — 物理移除,任何状态)", expanded=False):
        all_rows = list(snap.rows)
        if not all_rows:
            st.caption("(无持仓)")
            return
        options = [_PLACEHOLDER] + [f"[{r.status}] {_label(r)}" for r in all_rows]
        pick = st.selectbox("选要彻底删除的持仓", options, key="ha_hard_pick")
        chosen = None
        if pick != _PLACEHOLDER:
            chosen = all_rows[options.index(pick) - 1]

        confirm = st.checkbox("我已确认,知道此操作物理移除该持仓(有 .bak 备份)",
                              key="ha_hard_confirm")
        ready = (chosen is not None) and confirm
        if st.button("🔥 彻底删除", disabled=not ready, key="ha_hard_btn"):
            ok, msg = _call_delete_holding(chosen.ticker)
            if ok:
                st.success(msg)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)


# ─── 主入口 ────────────────────────────────────────────────────────
def render(snap: HoldingsSnapshot) -> None:
    """渲染清仓 / 取消 / 删除 动作面板。"""
    st.markdown("### 🛠️ 持仓动作面板")
    st.caption("统一入口:清仓归档(软删)/ 取消 watch(物理)/ 彻底删除(危险)。"
               "active=0 或 watch=0 时对应段灰显但常驻可见。")
    _render_close_section(snap)
    st.divider()
    _render_cancel_section(snap)
    st.divider()
    _render_hard_delete_section(snap)
