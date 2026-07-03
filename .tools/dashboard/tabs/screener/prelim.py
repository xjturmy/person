"""tabs.screener.prelim · 初步筛选(多维硬过滤).

universe 来自 funnel.layers.get_screener_universe(),受 focus 行业约束。
对 universe 子集运行 apply_filters(粗筛预设 / 自定义滑块),
通过名单写入 FUNNEL_SCREENER_PRELIM 草稿,供林奇/格雷厄姆 Tab 继承。

大师评分、方法论卡、散点图 → 见「林奇选股」「格雷厄姆选股」Tab。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from screening import screener as _scr
from dashboard_helpers import latest_annual_year, latest_financial_period

from . import _universe


@st.cache_data(ttl=300)
def _load_screener_data(db_mtime: float, year: int) -> pd.DataFrame:
    # 优先读预计算 screener_wide(load_all 的超集,<30ms);未覆盖降级 live。
    try:
        import analytics_store as _store
        pre = _store.wide_table_for(year)
        if pre is not None:
            return pre
    except Exception:
        pass
    return _scr.load_all(fscore_year=year)


@st.cache_data(ttl=600)
def _load_prelim_presets_cached(_dummy: float) -> list[dict]:
    return _scr.load_prelim_presets()


def _render_custom_sliders(metrics_cfg: dict) -> list[dict]:
    """自定义模式:从 metrics 段生成用户可调过滤条件。"""
    filters: list[dict] = []
    if not metrics_cfg:
        return filters

    st.caption("拖动滑块设定阈值(左=下限,右=上限;未勾选则不生效)")
    cols = st.columns(2)
    items = list(metrics_cfg.items())
    for i, (key, meta) in enumerate(items):
        col = cols[i % 2]
        with col:
            label = meta.get("label", key)
            lo, hi = meta.get("range", [0.0, 1.0])
            step = meta.get("step", 0.01)
            enabled = st.checkbox(f"启用 {label}", value=False, key=f"prelim_custom_en_{key}")
            if not enabled:
                continue
            use_min = st.checkbox(f"{label} ≥", value=True, key=f"prelim_custom_min_{key}")
            val = st.slider(
                label, min_value=float(lo), max_value=float(hi),
                value=float(lo if use_min else hi), step=float(step),
                key=f"prelim_custom_val_{key}",
            )
            filters.append({
                "metric": key,
                "op": ">=" if use_min else "<=",
                "value": val,
            })
    return filters


def render(companies=None, db_mtime: float = 0.0) -> None:
    st.markdown("### 🧮 初步筛选")
    st.caption(
        "universe 来自「行业确定」聚焦行业展开。"
        "此处仅做**多维硬指标粗筛**;林奇/格雷厄姆大师评分请切到对应 Tab。"
    )

    df_universe = _universe.get_or_block()
    if df_universe is None:
        return

    try:
        from funnel import layers as _layers
        n_focus = len(_layers.get_focus_names() or set())
    except Exception:
        n_focus = 0
    st.info(f"universe: **{len(df_universe)}** 只(来自 **{n_focus}** 个 focus 行业)")

    latest_period = latest_financial_period(db_mtime).get("label", "—")
    fscore_year = latest_annual_year(db_mtime) or (pd.Timestamp.now().year - 1)
    st.caption(f"财务指标最新到 {latest_period}; F-Score 使用 {fscore_year} 完整年报口径。")
    with st.spinner("加载指标 + F-Score..."):
        try:
            df_all = _load_screener_data(db_mtime, fscore_year).copy()
        except Exception as e:
            st.error(f"指标加载失败:{e}")
            return

    universe_tickers = set(df_universe["ticker"].astype(str).str.zfill(6))
    df_all["ticker"] = df_all["ticker"].astype(str).str.zfill(6)
    df = df_all[df_all["ticker"].isin(universe_tickers)].copy()
    if df.empty:
        st.warning(
            f"⚠️ universe({len(universe_tickers)} 只)与本地指标库无交集,"
            "可能本地 DuckDB 还未覆盖这些 ticker。"
        )
        return

    presets = _load_prelim_presets_cached(db_mtime)
    full_cfg = _scr.load_presets()
    metrics_cfg = full_cfg.get("metrics") or {}

    label_for = {
        p["id"]: f"{p.get('icon', '')} {p.get('name', p['id'])}"
        for p in presets if p.get("id")
    }
    if not label_for:
        st.warning("未配置 prelim_presets(presets.yaml)")
        return

    preset_id = st.radio(
        "粗筛预设(一键应用)", list(label_for.keys()),
        format_func=lambda x: label_for[x],
        horizontal=True, key="prelim_preset",
    )
    preset_meta = next((p for p in presets if p.get("id") == preset_id), None)
    if preset_meta and preset_meta.get("description"):
        st.caption(preset_meta["description"])

    if preset_id == "custom":
        filters = _render_custom_sliders(metrics_cfg)
    else:
        filters = (preset_meta or {}).get("filters") or []

    filtered = _scr.apply_filters(df, filters)
    filtered = filtered.sort_values(
        ["fscore", "pe_pct_10y"],
        ascending=[False, True],
        na_position="last",
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("universe 内公司", f"{len(df)}")
    m2.metric("通过条数", f"{len(filtered)}")
    hit_pct = len(filtered) / len(df) if len(df) else 0
    m3.metric("通过率", f"{hit_pct:.0%}")

    if filtered.empty:
        st.warning("当前预设无任何公司命中,试试切换预设或放宽自定义阈值。")
        try:
            from funnel import session as _session
            _session.set_draft(_session.FUNNEL_SCREENER_PRELIM, [])
        except Exception:
            pass
        return

    st.markdown("##### 📋 候选清单 · 按 F-Score ↓ / PE 分位 ↑")
    disp = filtered.copy()
    disp["加入草稿"] = False

    cols_order = [
        "加入草稿", "name", "ticker", "pe", "pe_pct_10y",
        "pb", "dividend_yield", "roe", "rev_yoy", "cfo_to_ni",
        "debt_ratio", "fscore",
    ]
    rename = {
        "name": "公司", "ticker": "代码", "pe": "PE-TTM",
        "pe_pct_10y": "PE 10y 分位", "pb": "PB",
        "dividend_yield": "股息率", "roe": "ROE",
        "rev_yoy": "营收 YoY", "cfo_to_ni": "CFO/NI",
        "debt_ratio": "负债率", "fscore": "F-Score",
    }
    show = disp[[c for c in cols_order if c in disp.columns]].rename(columns=rename)

    edited = st.data_editor(
        show,
        width="stretch", hide_index=True,
        num_rows="fixed",
        disabled=[c for c in show.columns if c != "加入草稿"],
        column_config={
            "加入草稿": st.column_config.CheckboxColumn(default=False, width="small"),
            "PE 10y 分位": st.column_config.NumberColumn(format="%.1f%%"),
            "股息率":     st.column_config.NumberColumn(format="%.2f%%"),
            "ROE":        st.column_config.NumberColumn(format="%.1f%%"),
            "营收 YoY":   st.column_config.NumberColumn(format="%.1f%%"),
            "负债率":     st.column_config.NumberColumn(format="%.0f%%"),
            "CFO/NI":     st.column_config.NumberColumn(format="%.2f"),
            "PE-TTM":     st.column_config.NumberColumn(format="%.1f"),
            "PB":         st.column_config.NumberColumn(format="%.2f"),
            "F-Score":    st.column_config.NumberColumn(format="%d"),
        },
        key="prelim_table",
    )

    selected_codes = (
        edited.loc[edited["加入草稿"], "代码"].astype(str).str.zfill(6).tolist()
        if "加入草稿" in edited.columns else []
    )
    try:
        from funnel import session as _session
        _session.set_draft(_session.FUNNEL_SCREENER_PRELIM, list(selected_codes))
    except Exception:
        pass

    st.caption(
        f"✏️ 草稿已同步:{len(selected_codes)} 只 → "
        f"可切到「林奇选股 / 格雷厄姆选股」继续,或在「选股确定」汇总"
    )


__all__ = ["render"]
