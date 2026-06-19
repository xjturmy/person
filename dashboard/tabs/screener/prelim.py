"""tabs.screener.prelim · 初步筛选(多维过滤预设).

universe 来自 funnel.layers.get_screener_universe(),受 focus 行业约束。
对 universe ∩ screener.load_all() 子集运行 apply_filters(预设 yaml),
通过名单写入 FUNNEL_SCREENER_PRELIM 草稿,供「选股确定」汇总。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from screening import screener as _scr

from . import _universe


@st.cache_data(ttl=300)
def _load_screener_data(db_mtime: float, year: int) -> pd.DataFrame:
    return _scr.load_all(fscore_year=year)


@st.cache_data(ttl=600)
def _load_presets_cached(_dummy: float) -> dict:
    return _scr.load_presets()


def render(companies=None, db_mtime: float = 0.0) -> None:
    st.markdown("### 🧮 初步筛选")
    st.caption(
        "universe 来自「行业确定」聚焦行业展开。多维过滤预设(PE 分位 / "
        "ROE / F-Score 等)给候选打粗筛标签,通过名单在下方「确定」区汇总。"
    )

    df_universe = _universe.get_or_block()
    if df_universe is None:
        return

    # universe summary
    try:
        from funnel import layers as _layers
        n_focus = len(_layers.get_focus_names() or set())
    except Exception:
        n_focus = 0
    st.info(f"universe: **{len(df_universe)}** 只(来自 **{n_focus}** 个 focus 行业)")

    # 拉全量指标,再按 universe ticker 过滤
    fscore_year = pd.Timestamp.now().year - 1
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

    # 预设选择
    presets_cfg = _load_presets_cached(db_mtime)
    preset_options = [(p["id"], p) for p in presets_cfg.get("presets", [])]
    label_for = {
        pid: f"{p.get('icon','')} {p.get('name', pid)}"
        for pid, p in preset_options if p
    }
    if not label_for:
        st.warning("未配置任何筛选预设(presets.yaml 为空)")
        return

    preset_id = st.radio(
        "筛选预设(一键应用)", list(label_for.keys()),
        format_func=lambda x: label_for[x],
        horizontal=True, key="prelim_preset",
    )
    preset_meta = next((p for p in presets_cfg["presets"] if p["id"] == preset_id), None)
    filters = (preset_meta or {}).get("filters") or []

    # 跑过滤
    filtered = _scr.apply_filters(df, filters)

    m1, m2, m3 = st.columns(3)
    m1.metric("universe 内公司", f"{len(df)}")
    m2.metric("通过条数", f"{len(filtered)}")
    hit_pct = len(filtered) / len(df) if len(df) else 0
    m3.metric("通过率", f"{hit_pct:.0%}")

    if filtered.empty:
        st.warning("当前预设无任何公司命中,试试切换预设。")
        # 也清掉草稿,避免上一次残留误导
        try:
            from funnel import session as _session
            _session.set_draft(_session.FUNNEL_SCREENER_PRELIM, [])
        except Exception:
            pass
        return

    # 候选清单 + checkbox(默认全勾,用户可取消)
    disp = filtered.copy()
    disp["加入草稿"] = True
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
        use_container_width=True, hide_index=True,
        num_rows="fixed",
        disabled=[c for c in show.columns if c != "加入草稿"],
        column_config={
            "加入草稿": st.column_config.CheckboxColumn(default=True, width="small"),
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

    # 写草稿:勾选的 ticker
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
        f"在下方确定区勾选写入观察池"
    )


__all__ = ["render"]
