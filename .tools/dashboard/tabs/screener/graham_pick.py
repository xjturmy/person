"""tabs.screener.graham_pick · 格雷厄姆价值选股.

对 universe(可继承初筛草稿)运行 ``score_with_master``:
  - 格雷厄姆:四类判定 + 多规则评分

命中(score ≥ 阈值)写入 FUNNEL_SCREENER_GRAHAM 草稿。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from screening import screener as _scr
from dashboard_helpers import latest_annual_year, latest_financial_period

from . import _universe
from ._ui_helpers import count_excellent, preset_for_master, render_methodology_card, render_scatter

_MASTER_LABELS = {
    "graham": "格雷厄姆",
}


@st.cache_data(ttl=300)
def _load_screener_data(db_mtime: float, year: int) -> pd.DataFrame:
    try:
        import analytics_store as _store
        pre = _store.wide_table_for(year)
        if pre is not None:
            return pre
    except Exception:
        pass
    return _scr.load_all(fscore_year=year)


@st.cache_data(ttl=3600, show_spinner=False)
def _value_scored(db_mtime: float, year: int, tickers_key: str,
                  master_id: str) -> pd.DataFrame:
    want = set(tickers_key.split(","))
    # 优先读预计算 value_scored_{master}(全市场,含 graham 四类),过滤即可。
    try:
        import analytics_store as _store
        pre = _store.value_scored_for(master_id, year)
        if pre is not None:
            return pre[pre["ticker"].astype(str).str.zfill(6).isin(want)].copy()
    except Exception:
        pass
    df = _load_screener_data(db_mtime, year)
    df = df[df["ticker"].astype(str).str.zfill(6).isin(want)]
    if df.empty:
        return df
    return _scr.score_with_master(df, master_id, year)


def _classify_one(ticker: str) -> tuple[str, str, str]:
    """返回 (cls_id, cls_cn, cls_emoji);失败时 ("skip","不适用","❓")."""
    try:
        from masters.graham.steps import classify_graham_type, load_graham_metrics
        m = load_graham_metrics(ticker)
        r = classify_graham_type(m)
        return (r.cls_id, r.cls_name, r.cls_emoji)
    except Exception:
        return ("skip", "不适用", "❓")


def render(companies=None, db_mtime: float = 0.0) -> None:
    st.markdown("## 📐 格雷厄姆选股")
    st.caption(
        "用格雷厄姆四类价值框架评分。命中项写入草稿,"
        "在「✅ 选股确定」汇总入观察池。"
    )

    df_universe = _universe.get_or_block()
    if df_universe is None:
        return

    master_id = "graham"

    try:
        from funnel import session as _session
        prelim_codes = list(_session.get_draft(_session.FUNNEL_SCREENER_PRELIM, []) or [])
    except Exception:
        prelim_codes = []

    src_choices = ["全 universe", "继承初步筛选草稿"]
    default_idx = 1 if prelim_codes else 0
    src = st.radio(
        f"数据源(初筛草稿:{len(prelim_codes)} 只)",
        src_choices, index=default_idx, horizontal=True,
        key="graham_pick_src",
    )
    if src == "继承初步筛选草稿" and prelim_codes:
        df_in = df_universe[
            df_universe["ticker"].astype(str).str.zfill(6).isin(set(prelim_codes))
        ].copy()
    else:
        df_in = df_universe.copy()

    if df_in.empty:
        st.warning("输入为空 — 检查初筛草稿或换数据源。")
        return

    label = _MASTER_LABELS[master_id]
    value_preset = preset_for_master(master_id) or {
        "name": label,
        "tagline": "深度价值评分",
        "rules_yaml": master_id,
    }
    render_methodology_card(value_preset)

    tickers_key = ",".join(sorted(df_in["ticker"].astype(str).str.zfill(6).tolist()))
    latest_period = latest_financial_period(db_mtime).get("label", "—")
    year = latest_annual_year(db_mtime) or (pd.Timestamp.now().year - 1)
    st.caption(f"财务指标最新到 {latest_period}; 格雷厄姆规则使用 {year} 完整年报口径。")
    with st.spinner(f"运行{label}评分..."):
        try:
            scored = _value_scored(db_mtime, year, tickers_key, master_id)
        except Exception as e:
            st.error(f"{label}评分失败:{e}")
            return

    if scored is None or scored.empty:
        st.warning("评分结果为空(可能本地数据不覆盖这些 ticker)。")
        return

    # 预计算表已带 graham_class / 价值类型 → 跳过逐家 live 判定(实测 3.8s/41 家)。
    if "graham_class" not in scored.columns or "价值类型" not in scored.columns:
        with st.spinner("格雷厄姆四类判定..."):
            cls_rows = [_classify_one(t) for t in scored["ticker"].astype(str)]
        scored["graham_class"] = [c[0] for c in cls_rows]
        scored["价值类型"] = [f"{c[2]} {c[1]}" for c in cls_rows]
    type_counts = scored["价值类型"].value_counts()
    if not type_counts.empty:
        badges = " · ".join(f"{k} **{v}**" for k, v in type_counts.items())
        st.caption(f"📊 四类分布:{badges}")

    threshold = st.slider(
        "命中阈值(评分 ≥)", min_value=0, max_value=20, value=5, step=1,
        key=f"value_pick_threshold_{master_id}",
    )
    scored = scored.sort_values("score", ascending=False, na_position="last")
    hit_mask = scored["score"].fillna(-1) >= threshold
    scored["命中"] = hit_mask

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("评分公司", f"{int(scored['score'].notna().sum())}")
    m2.metric("命中数", f"{int(hit_mask.sum())}")
    m3.metric("阈值", f"≥ {threshold}")
    pass_excellent = count_excellent(scored, value_preset)
    m4.metric("🟢 优秀级", f"{pass_excellent}" if pass_excellent is not None else "—")

    render_scatter(scored, value_preset, has_score=True, chart_key=f"value_scatter_{master_id}")

    show = scored.copy()
    show["评分"] = show.apply(
        lambda r: (
            f"{r['score']:.0f}/{int(r['max_score'])}"
            if pd.notna(r.get("score")) and pd.notna(r.get("max_score"))
            else (f"{r['score']:.0f}" if pd.notna(r.get("score")) else "—")
        ),
        axis=1,
    )
    cols = ["命中", "name", "ticker", "评分", "rating", "pe", "pe_pct_10y", "roe"]
    cols.insert(4, "价值类型")
    rename = {
        "name": "公司", "ticker": "代码", "rating": "评级",
        "pe": "PE-TTM", "pe_pct_10y": "PE 10y 分位", "roe": "ROE",
    }
    show = show[[c for c in cols if c in show.columns]].rename(columns=rename)

    edited = st.data_editor(
        show,
        width="stretch", hide_index=True, num_rows="fixed",
        disabled=[c for c in show.columns if c != "命中"],
        column_config={
            "命中": st.column_config.CheckboxColumn(default=False, width="small"),
            "PE 10y 分位": st.column_config.NumberColumn(format="%.1f%%"),
            "ROE":         st.column_config.NumberColumn(format="%.1f%%"),
            "PE-TTM":      st.column_config.NumberColumn(format="%.1f"),
        },
        key=f"value_pick_table_{master_id}",
    )

    hit_codes = (
        edited.loc[edited["命中"], "代码"].astype(str).str.zfill(6).tolist()
        if "命中" in edited.columns else []
    )
    try:
        from funnel import session as _session
        _session.set_draft(_session.FUNNEL_SCREENER_GRAHAM, list(hit_codes))
    except Exception:
        pass

    st.caption(f"✏️ {label}命中草稿已同步:{len(hit_codes)} 只")


__all__ = ["render"]
