"""黄金分析法 Tab 子包入口 — dispatch 9 sub-tabs。

对外 API 与原 tabs/gold_analysis.py 完全一致:`render(...)` 同签名同行为。
"""
from __future__ import annotations

import streamlit as st

from ._helpers import (
    Snapshot,
    _snapshot_cached, _vote_cached, _overheat_cached,
    _freshness_cached, _refresh_gold_data,
    _ratios_cached, _indicator_cached, _percentiles_cached,
    _etf_master_cached, _etf_prices_cached,
    _overheat_history_cached,
    _stock_etf_master_cached, _stock_etf_prices_cached, _stock_betas_cached,
    _render_banner, _render_overheat_banner,
)
from .paradigm import _render_paradigm
from .metrics_panel import _render_metrics_panel
from .etf import _render_etf
from .overheat import _render_overheat
from .stock_leverage import _render_stock_etf_leverage
from .backtest import _render_backtest
from .position import _render_position_advisor


def render(companies: list[str] | None = None,
           selected: str | None = None,
           db_mtime: float = 0.0,
           decisions_db=None,
           folder_to_ticker_fn=None) -> None:
    """黄金分析法 Tab 入口。signature 与 lynch/graham 对齐,但黄金是资产类不针对单家公司。"""
    st.subheader("🥇 黄金分析法 · 三身份决策框架")

    # 上一次刷新日志(session_state 跨 rerun 残留 → 渲染后清空)
    if st.session_state.get("gold_refresh_log"):
        log = st.session_state.pop("gold_refresh_log")
        ok = st.session_state.pop("gold_refresh_ok", False)
        if ok:
            st.success("✅ 行情已刷新,数据已重算")
        else:
            st.warning("⚠️ 刷新部分失败 — 详见日志")
        with st.expander("📋 刷新日志(自动隐藏)", expanded=not ok):
            st.code(log, language="text")

    # 顶部:数据来源 / 时效 / 刷新按钮
    fresh = _freshness_cached(db_mtime)
    col_left, col_ts, col_refresh = st.columns([3, 2, 1])
    with col_left:
        st.caption(
            "📊 数据来源:沪金 SGE / 美国 10Y / CPI / WTI 油 / 4 只 ETF · "
            "理论:鲁政委《保卫财富》三大范式 + 周金涛康波"
        )
    with col_ts:
        db_ts = fresh.get("db_mtime") or "—"
        etf_d = fresh.get("etf_date") or "—"
        oh_d = fresh.get("overheat_date") or "—"
        st.caption(
            f"💾 库更新:**{db_ts}**  ·  📈 ETF 最新:**{etf_d}**  ·  "
            f"⏱ 过热快照:**{oh_d}**"
        )
    with col_refresh:
        if st.button("🔄 拉新数据", key="gold_refresh",
                     use_container_width=True,
                     help="跑 fetch_gold_etf + fetch_gold_etf_share + "
                          "fetch_gold_prices + overheat_engine --write"
                          "(预计 30-90s)"):
            with st.spinner("正在拉取最新行情(预计 30-90s,请勿关闭)..."):
                ok, log = _refresh_gold_data()
            st.session_state["gold_refresh_log"] = log
            st.session_state["gold_refresh_ok"] = ok
            for cache_fn in (_snapshot_cached, _ratios_cached, _indicator_cached,
                             _percentiles_cached, _etf_master_cached, _etf_prices_cached,
                             _overheat_cached, _overheat_history_cached,
                             _freshness_cached,
                             _stock_etf_master_cached, _stock_etf_prices_cached,
                             _stock_betas_cached):
                cache_fn.clear()
            st.rerun()

    # 加载 snapshot + 投票
    snap_dict = _snapshot_cached(db_mtime)
    if snap_dict is None or "_error" in (snap_dict or {}):
        err = snap_dict.get("_error") if snap_dict else "数据加载失败"
        st.error(f"⚠️ gold.duckdb 未就绪:{err}")
        st.info("请先跑 4 个 fetch 脚本:`fetch_gold_prices` / `fetch_real_rate` / `fetch_gold_etf` / `fetch_gold_ratios`")
        return

    snap = Snapshot(**snap_dict)

    # 投票:引擎优先,失败回落 static
    vote_dict = _vote_cached(db_mtime)
    # SimpleNamespace 适配:UI 用属性访问(.dominant_label / .suggested_pct 等)
    from types import SimpleNamespace
    # tuple 化 suggested_pct(yaml 出 list)
    if isinstance(vote_dict.get("suggested_pct"), list):
        vote_dict["suggested_pct"] = tuple(vote_dict["suggested_pct"])
    vote = SimpleNamespace(**vote_dict)

    # Banner(主)
    _render_banner(snap, vote)

    # v2.4 step-D · 短期过热 banner(挂主 banner 下方)
    overheat = _overheat_cached(db_mtime)
    paradigm_actives = sum([vote.p1_active, vote.p2_active, vote.p3_active])
    _render_overheat_banner(overheat, paradigm_actives)

    # 7 sub-tabs(v2.7 简化:实际利率/周期/关键比率合并为「关键指标面板」)
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "① 三大范式投票",
        "② 关键指标面板",
        "③ ETF 选择",
        "④ 短期过热扫描",
        "⑤ 金股 ETF 杠杆视图",
        "⑥ 策略回溯",
        "⑦ 持仓建议",
    ])
    with tab1:
        _render_paradigm(snap, vote)
    with tab2:
        _render_metrics_panel(snap, db_mtime)
    with tab3:
        _render_etf(db_mtime)
    with tab4:
        _render_overheat(overheat, paradigm_actives, db_mtime)
    with tab5:
        _render_stock_etf_leverage(overheat, db_mtime)
    with tab6:
        _render_backtest(db_mtime)
    with tab7:
        _render_position_advisor(overheat, db_mtime)
