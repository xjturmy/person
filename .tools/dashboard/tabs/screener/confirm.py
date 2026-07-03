"""tabs.screener.confirm · 选股确定(三路合并 → watchlist).

四段 UI:
  ① watchlist 已确认清单 + 删除
  ② 三路命中草稿合并(初筛 ∪ 林奇 ∪ 格雷厄姆),勾选 → 入观察池
  ③ 一致性检查:focus 之外的 orphan
  ④ 跳转「公司研究」

写入 watchlist 时:
  - 从 FUNNEL_SCREENER_TICKER_INDUSTRY 反查 source_industry
  - 反查不到填 "unknown"
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

# 工具函数(纯逻辑、可被测试直接调用)─────────────────────────────────


def _ticker_industry_map() -> dict[str, str]:
    """从 session 拿 ticker→industry_l2 dict(_universe 渲染时写入)。"""
    try:
        from funnel import session as _session
        return dict(_session.get_draft(_session.FUNNEL_SCREENER_TICKER_INDUSTRY, {}) or {})
    except Exception:
        return {}


def _merge_draft_hits() -> pd.DataFrame:
    """合并三路 ticker 草稿,返回 DataFrame(ticker / sources)."""
    try:
        from funnel import session as _session
        prelim = set(_session.get_draft(_session.FUNNEL_SCREENER_PRELIM, []) or [])
        lynch  = set(_session.get_draft(_session.FUNNEL_SCREENER_LYNCH, []) or [])
        graham = set(_session.get_draft(_session.FUNNEL_SCREENER_GRAHAM, []) or [])
        buffett = set(_session.get_draft(_session.FUNNEL_SCREENER_BUFFETT, []) or [])
    except Exception:
        prelim = lynch = graham = buffett = set()

    all_tickers = prelim | lynch | graham | buffett
    rows = []
    for t in sorted(all_tickers):
        tags = []
        if t in prelim: tags.append("P")
        if t in lynch:  tags.append("L")
        if t in graham: tags.append("G")
        if t in buffett: tags.append("B")
        rows.append({"ticker": t, "sources": "+".join(tags)})
    return pd.DataFrame(rows, columns=["ticker", "sources"])


def write_selected_to_watchlist(tickers: list[str], preset_label: str,
                                  name_lookup: dict[str, str] | None = None) -> int:
    """把 tickers 写入 watchlist;source_industry 从 session 反查。

    返回新增条数。
    """
    if not tickers:
        return 0
    import watchlist as _wl

    name_lookup = name_lookup or {}
    t2i = _ticker_industry_map()
    rows = []
    for t in tickers:
        t6 = str(t).zfill(6)
        rows.append({
            "ticker": t6,
            "name": name_lookup.get(t6, ""),
            "source_industry": t2i.get(t6, "unknown") or "unknown",
        })
    df = pd.DataFrame(rows)
    return _wl.add(df, preset=preset_label)


# 渲染段 ─────────────────────────────────────────────────────────────


def _section_existing_watchlist() -> None:
    st.markdown("### ① 观察池已确认清单")
    try:
        import watchlist as _wl
        entries = _wl.load() or []
    except Exception as e:
        st.error(f"watchlist 加载失败:{e}")
        return

    if not entries:
        st.info("观察池为空 — 在下方草稿区勾选加入。")
        return

    show_rows = []
    for e in entries:
        show_rows.append({
            "删除": False,
            "代码": e.ticker,
            "公司": e.name,
            "preset": e.preset,
            "评分": e.score if e.score is not None else "—",
            "评级": e.rating or "—",
            "状态": e.status,
            "source_industry": getattr(e, "source_industry", "unknown"),
            "added_at": e.added_at,
        })
    show = pd.DataFrame(show_rows)
    edited = st.data_editor(
        show, width="stretch", hide_index=True, num_rows="fixed",
        disabled=[c for c in show.columns if c != "删除"],
        column_config={"删除": st.column_config.CheckboxColumn(default=False, width="small")},
        key="confirm_existing_table",
    )
    del_codes = (
        edited.loc[edited["删除"], "代码"].astype(str).str.zfill(6).tolist()
        if "删除" in edited.columns else []
    )
    if st.button(f"🗑️ 删除选中 ({len(del_codes)})", disabled=not del_codes,
                 key="confirm_remove_btn"):
        n = 0
        for t in del_codes:
            try:
                if _wl.remove(t):
                    n += 1
            except Exception:
                pass
        st.success(f"✅ 已删除 {n} 只")
        st.rerun()


def _section_merged_drafts(universe_df: pd.DataFrame | None) -> None:
    st.markdown("### ② 四路命中合并草稿(初筛 ∪ 林奇 ∪ 格雷厄姆 ∪ 巴菲特)")
    merged = _merge_draft_hits()
    if merged.empty:
        st.info("草稿为空 — 到「初步筛选」/「林奇选股」/「格雷厄姆选股」勾选命中。")
        return

    # name 反查 — 用 universe_df(可能为空 → 退到空 dict)
    name_lookup: dict[str, str] = {}
    if universe_df is not None and not universe_df.empty:
        for _, r in universe_df.iterrows():
            t6 = str(r["ticker"]).zfill(6)
            name_lookup[t6] = str(r.get("name", "") or "")

    t2i = _ticker_industry_map()

    show = merged.copy()
    show["公司"] = show["ticker"].map(name_lookup).fillna("")
    show["行业来源"] = show["ticker"].map(t2i).fillna("unknown")
    show["加入观察池"] = True
    show = show[["加入观察池", "公司", "ticker", "sources", "行业来源"]]

    edited = st.data_editor(
        show, width="stretch", hide_index=True, num_rows="fixed",
        disabled=[c for c in show.columns if c != "加入观察池"],
        column_config={
            "加入观察池": st.column_config.CheckboxColumn(default=True, width="small"),
            "sources": st.column_config.TextColumn(help="P=初筛 L=林奇 G=格雷厄姆 B=巴菲特"),
        },
        key="confirm_merged_table",
    )

    sel_codes = (
        edited.loc[edited["加入观察池"], "ticker"].astype(str).str.zfill(6).tolist()
        if "加入观察池" in edited.columns else []
    )

    if st.button(f"✅ 加入观察池 ({len(sel_codes)})", type="primary",
                 disabled=not sel_codes, key="confirm_add_watch"):
        n = write_selected_to_watchlist(
            sel_codes, preset_label="v2.9 选股确定", name_lookup=name_lookup,
        )
        st.success(f"✅ 新增 {n} 只(已存在的去重跳过)")
        # 清三路草稿
        try:
            from funnel import session as _session
            _session.clear_draft(_session.FUNNEL_SCREENER_PRELIM)
            _session.clear_draft(_session.FUNNEL_SCREENER_LYNCH)
            _session.clear_draft(_session.FUNNEL_SCREENER_GRAHAM)
            _session.clear_draft(_session.FUNNEL_SCREENER_BUFFETT)
        except Exception:
            pass
        st.rerun()


def _section_orphan_check() -> None:
    st.markdown("### ③ 一致性检查")
    try:
        from funnel import layers as _layers
        from funnel import orphans as _orphans
        focus_names = _layers.get_focus_names() or set()
        orphan_list = _orphans.find_orphan_watchlist(focus_names) or []
    except Exception as e:
        st.error(f"orphan 检查失败:{e}")
        return

    if not orphan_list:
        st.success("✅ 无孤立观察股 — focus 行业覆盖完整")
        return

    st.warning(f"⚠️ watchlist 中有 **{len(orphan_list)}** 只孤立股(行业不在 focus):")
    st.dataframe(pd.DataFrame(orphan_list), hide_index=True, width="stretch")


def _section_nav_to_company() -> None:
    st.markdown("---")
    cols = st.columns([3, 1])
    cols[0].caption("选股确定后 → 进入公司研究做深度判定")
    with cols[1]:
        if st.button("→ 公司研究", type="primary", width="stretch",
                     key="confirm_goto_company"):
            try:
                from navigation import goto, PAGE_COMPANY
                # P2 才定义 SUB_COMPANY_*;先用字面量占位
                goto(PAGE_COMPANY, sub_tab="公司研判")
            except Exception as e:
                st.error(f"跳转失败:{e}")


def render(companies=None, db_mtime: float = 0.0) -> None:
    st.markdown("### ✅ 确定入观察池")

    # 读 universe(若 focus 空会跳转;这里允许 universe 为空也继续展示已有 watchlist)
    universe_df = None
    try:
        from funnel import layers as _layers
        universe_df = _layers.get_screener_universe()
        # 顺便刷一遍 ticker→industry 映射给写入用
        if universe_df is not None and not universe_df.empty:
            from . import _universe as _u
            _u.get_ticker_industry_map(universe_df)
    except Exception:
        universe_df = None

    _section_existing_watchlist()
    st.markdown("---")
    _section_merged_drafts(universe_df)
    st.markdown("---")
    _section_orphan_check()
    _section_nav_to_company()


__all__ = ["render", "write_selected_to_watchlist", "_merge_draft_hits",
           "_ticker_industry_map"]
