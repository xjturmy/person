"""行业深度下钻 — PE 速览 / ETF Top3 / 龙头 Top5 / 知识(共享组件)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[4]
INDUSTRY_MASTER_YAML = ROOT / ".config" / "industry_master.yaml"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
PEERS_CSV = ROOT / ".config" / "peers.csv"


def _short_text(text: object, max_len: int = 22) -> str:
    """单行摘要,去掉换行并截断."""
    t = str(text or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t or "—"
    return t[: max_len - 1] + "…"


def _short_reason(reason: object, max_len: int = 24) -> str:
    """理由取首段(第一个 / 前),避免两行."""
    raw = str(reason or "").replace("\n", " ").strip()
    head = raw.split(" / ")[0].strip() if raw else ""
    return _short_text(head or raw, max_len)


def _inject_compact_row_css() -> None:
    st.markdown(
        """
<style>
[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button {
    padding: 0.12rem 0.4rem;
    font-size: 0.75rem;
    min-height: 1.55rem;
    line-height: 1.2;
}
[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton > button:disabled {
    opacity: 1;
    border: 1px solid #d1d5db;
    background: #f3f4f6;
    color: #6b7280;
    cursor: default;
}
.drill-status-cell {
    min-height: 1.55rem;
    display: flex;
    align-items: center;
    font-size: 0.75rem;
    line-height: 1.2;
    color: #374151;
}
.drill-text-cell {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 0.82rem;
    line-height: 1.55rem;
    min-height: 1.55rem;
    margin: 0;
    padding: 0;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _compact_line(text: str) -> None:
    """单行 HTML,与操作按钮同高对齐."""
    safe = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    st.markdown(
        f'<div class="drill-text-cell">{safe or "&nbsp;"}</div>',
        unsafe_allow_html=True,
    )


def _status_cell(text: str) -> None:
    """状态列 — 固定行高,与右侧按钮对齐."""
    safe = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    st.markdown(
        f'<div class="drill-status-cell">{safe or "&nbsp;"}</div>',
        unsafe_allow_html=True,
    )


def _pool_action_button(
    *,
    in_pool: bool,
    key: str,
    add_label: str = "＋自选",
    done_label: str = "✓ 已选",
    on_add=None,
) -> None:
    """操作列 — 未入池可点,已入池为同尺寸禁用按钮."""
    if in_pool:
        st.button(done_label, key=f"{key}_done", disabled=True, width="stretch")
    elif st.button(add_label, key=key, width="stretch"):
        if on_add:
            on_add()


def load_name_to_meta() -> dict[str, dict]:
    """name → meta(yaml + companies.csv 合并)."""
    from tabs.industry._master_loader import load_master_merged
    return load_master_merged()


def _ticker_name_lookup() -> dict[str, str]:
    """代码 → 名称(companies.csv + peers.csv)."""
    out: dict[str, str] = {}
    if COMPANIES_CSV.exists():
        try:
            import csv
            with COMPANIES_CSV.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = str(row.get("stock") or "").strip().zfill(6)
                    n = str(row.get("name") or "").strip()
                    if t and n:
                        out[t] = n
        except Exception:
            pass
    if PEERS_CSV.exists():
        try:
            import csv
            with PEERS_CSV.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = str(row.get("ticker") or "").strip().zfill(6)
                    n = str(row.get("name") or "").strip()
                    if t and n:
                        out.setdefault(t, n)
                    pt = str(row.get("peer_ticker") or "").strip().zfill(6)
                    pn = str(row.get("peer_name") or "").strip()
                    if pt and pn:
                        out.setdefault(pt, pn)
        except Exception:
            pass
    return out


def build_industry_leaders_intro(
    industry: str,
    meta: dict,
    *,
    top_n: int = 5,
) -> pd.DataFrame:
    """代表公司清单 — 仅基本情况,无林奇评分(预选/介绍用)."""
    names = _ticker_name_lookup()
    leader_order = [str(t).strip().zfill(6) for t in (meta.get("leaders") or []) if t]
    seen: set[str] = set()
    rows: list[dict[str, str]] = []

    def _append(ticker: str, name: str, note: str) -> None:
        t = str(ticker).strip().zfill(6)
        if not t or t in seen:
            return
        seen.add(t)
        rows.append({
            "代码": t,
            "名称": name or names.get(t, "—"),
            "备注": note,
        })

    for t in leader_order:
        _append(t, names.get(t, "—"), "配置龙头")
        if len(rows) >= top_n:
            break

    if len(rows) < top_n:
        try:
            from industry.screener import list_industry_candidates
            for c in list_industry_candidates(industry):
                t = str(c.get("ticker", "")).zfill(6)
                src = c.get("data_source") or ""
                note = "自选候选池" if src == "self_only" else "同行业代表"
                _append(t, str(c.get("name") or ""), note)
                if len(rows) >= top_n:
                    break
        except Exception:
            pass

    if not rows:
        return pd.DataFrame(columns=["序号", "代码", "名称", "备注"])

    df = pd.DataFrame(rows[:top_n])
    df.insert(0, "序号", range(1, len(df) + 1))
    return df


def _render_leaders_intro_block(industry: str, meta: dict) -> None:
    """预选阶段:行业代表公司介绍(无评分/自选/跳转)."""
    st.markdown("##### 🏢 代表公司")
    summary = str(meta.get("summary") or "").strip()
    if summary:
        st.info(summary)

    df = build_industry_leaders_intro(industry, meta, top_n=5)
    if df.empty:
        st.caption("暂无代表公司 — 可在 industry_master.yaml 配置 leaders")
        return

    if len(df) < 5:
        st.caption(
            f"共 **{len(df)}** 家（该 L2 数据源当前可覆盖;"
            "完整 Top 排序与评分 → 「🔍 选股」）"
        )
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption(
        "💡 林奇评分 / 评级 / 加入自选 → 「🔍 选股 · 初步筛选 / 选股确定」中完成"
    )


@st.cache_data(ttl=900, show_spinner=False)
def _cached_rank_rows() -> list[dict]:
    """全 L2 percentile 计算 + 行字典;ttl=900s 避免 sub-tab 切换抖动."""
    name_to_meta = load_name_to_meta()
    if not name_to_meta:
        return []
    try:
        from industry.percentile_engine import compute as _pe_compute
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for ind_name, meta in name_to_meta.items():
        try:
            r = _pe_compute(ind_name)
            rows.append({
                "行业": ind_name,
                "申万一级": meta.get("sw_l1", "—"),
                "PE 中位": r.pe_median,
                "PE 分位(10y)": r.pe_percentile_10y,
                "PB 分位(10y)": r.pb_percentile_10y,
                "成份股": r.member_count,
            })
        except Exception:
            continue
    return rows


def build_industry_rank_df(name_to_meta: dict[str, dict] | None = None) -> pd.DataFrame:
    """全 L2 分位排行 — 走 cached helper(入参兼容保留,但实际忽略;统一读 load_name_to_meta())."""
    rows = _cached_rank_rows()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        "PE 分位(10y)", na_position="last",
    ).reset_index(drop=True)


def _watchlist_ticker_set() -> set[str]:
    try:
        import watchlist as _wl
        return {e.ticker for e in _wl.load()}
    except Exception:
        return set()


def add_leader_to_watchlist(
    industry: str,
    row: dict[str, Any] | pd.Series,
    *,
    preset_prefix: str = "行业预选",
) -> int:
    """将 Top 公司行写入 watchlist.yaml;已存在则返回 0."""
    import watchlist as _wl

    raw_ticker = str(row.get("ticker", "")).strip()
    if not raw_ticker:
        return 0
    ticker = raw_ticker.zfill(6)
    if ticker in _watchlist_ticker_set():
        return 0
    score = row.get("score")
    rating = row.get("rating")
    df = pd.DataFrame([{
        "ticker": ticker,
        "name": str(row.get("name") or ""),
        "score": score if score is not None and pd.notna(score) else None,
        "rating": rating if rating is not None and pd.notna(rating) else None,
        "source_industry": industry,
    }])
    return _wl.add(df, preset=f"{preset_prefix}·{industry}")


def add_etf_to_watchlist(
    industry: str,
    etf: Any,
    *,
    preset_prefix: str = "行业预选",
) -> int:
    """将推荐 ETF 写入 watchlist.yaml;已存在则返回 0."""
    import watchlist as _wl

    code = str(getattr(etf, "code", None) or etf.get("code", "")).strip()
    if not code:
        return 0
    ticker = code.zfill(6)
    if ticker in _watchlist_ticker_set():
        return 0
    name = str(getattr(etf, "name", None) or etf.get("name") or "")
    df = pd.DataFrame([{
        "ticker": ticker,
        "name": name,
        "source_industry": industry,
    }])
    return _wl.add(df, preset=f"{preset_prefix}·{industry}·ETF")


def _render_metrics_row(sel_row: pd.Series) -> None:
    c1, c2, c3, c4 = st.columns(4)
    pe_med = sel_row["PE 中位"]
    c1.metric(
        "PE 中位",
        f"{pe_med:.1f}" if pd.notna(pe_med) else "—",
        f"第 {sel_row['PE 分位(10y)']:.0f}%"
        if pd.notna(sel_row["PE 分位(10y)"]) else "—",
    )
    c2.metric(
        "PB 分位(10y)",
        f"{sel_row['PB 分位(10y)']:.0f}%"
        if pd.notna(sel_row["PB 分位(10y)"]) else "—",
    )
    c3.metric("成份股", f"N={int(sel_row['成份股'])}")
    c4.metric("申万一级", sel_row["申万一级"])


def _render_etf_block(
    industry: str,
    *,
    interactive_watchlist: bool = False,
    key_prefix: str = "drill",
) -> None:
    try:
        from screening.etf_recommender import recommend as _etf_recommend
        etfs = _etf_recommend(industry, top_n=3)
    except Exception as e:
        etfs = []
        st.markdown("##### 📦 推荐 ETF")
        st.caption(f"ETF 推荐失败:{e}")
        return
    if not etfs:
        st.markdown("##### 📦 推荐 ETF")
        st.caption("此行业暂无对应 ETF 配置")
        return

    st.markdown(f"##### 📦 推荐 ETF · {len(etfs)} 只")

    if not interactive_watchlist:
        etf_df = pd.DataFrame([{
            "代码": c.code, "名称": c.name, "主题": c.theme,
            "1y 涨跌": f"{c.return_1y:+.1%}" if c.return_1y is not None else "—",
            "流动性分位": f"{c.liquidity_score:.0f}" if c.liquidity_score is not None else "—",
            "理由": c.rationale,
        } for c in etfs])
        st.dataframe(etf_df, hide_index=True, width="stretch")
        return

    wl_tickers = _watchlist_ticker_set()
    _inject_compact_row_css()
    # 代码 | 名称 | 主题 | 1y | 流 | 理由 | 状态 | 操作
    weights = [0.65, 1.0, 0.55, 0.45, 0.45, 2.0, 0.55, 0.85]
    hcols = st.columns(weights)
    for hc, label in zip(
        hcols,
        ["代码", "名称", "主题", "1y", "流", "理由", "状态", "操作"],
    ):
        hc.caption(label)

    for c in etfs:
        ticker = str(c.code).zfill(6)
        in_wl = ticker in wl_tickers
        ret_s = f"{c.return_1y:+.0%}" if c.return_1y is not None else "—"
        liq_s = f"{c.liquidity_score:.0f}" if c.liquidity_score is not None else "—"
        status = "✅池" if in_wl else ""

        cols = st.columns(weights)
        with cols[0]:
            _compact_line(ticker)
        with cols[1]:
            _compact_line(_short_text(c.name, 10))
        with cols[2]:
            _compact_line(_short_text(c.theme or "—", 6))
        with cols[3]:
            _compact_line(ret_s)
        with cols[4]:
            _compact_line(liq_s)
        with cols[5]:
            _compact_line(_short_reason(c.rationale, 28))
        with cols[6]:
            _status_cell(status)

        with cols[7]:
            def _add_etf() -> None:
                n = add_etf_to_watchlist(industry, c)
                if n:
                    st.toast(f"已加入观察池 {c.name}", icon="✅")
                    st.rerun()
                else:
                    st.toast(f"已在观察池 {c.name}", icon="ℹ️")

            _pool_action_button(
                in_pool=in_wl,
                key=f"{key_prefix}_etf_{industry}_{ticker}",
                on_add=_add_etf,
            )


def _render_top5_block(
    industry: str,
    type_: str,
    *,
    interactive_watchlist: bool,
    key_prefix: str,
) -> None:
    try:
        from industry.screener import screen_industry as _screen
        top_df = _screen(industry, type_, top_n=5)
    except Exception as e:
        st.markdown("##### 🏢 行业龙头")
        st.caption(f"评分失败:{e}")
        return

    if top_df.empty:
        st.markdown("##### 🏢 行业龙头")
        st.caption("评分候选为空")
        return

    # 过滤掉「数据不足 / 未分类」的低信息公司(本地库未覆盖),
    # 但保留自选/持仓股;避免把没法评分的公司当成「龙头」乱放
    def _has_real_data(r: pd.Series) -> bool:
        if bool(r.get("is_owned")):
            return True
        reason = str(r.get("reason") or "")
        if "数据不足" in reason or "未分类" in reason:
            return False
        return r.get("score") is not None and pd.notna(r.get("score"))

    scored_df = top_df[top_df.apply(_has_real_data, axis=1)].copy()
    if not scored_df.empty:
        top_df = scored_df.reset_index(drop=True)

    st.markdown(f"##### 🏢 行业龙头 · {len(top_df)} 家")

    wl_tickers = _watchlist_ticker_set()

    if not interactive_watchlist:
        show = top_df[["rank", "ticker", "name", "score", "rating", "reason", "is_owned"]].copy()
        show["score"] = show["score"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
        show["is_owned"] = show["is_owned"].map({True: "🌟 已持", False: ""})
        show.columns = ["排名", "代码", "名称", "分数", "评级", "理由", "自选"]
        st.dataframe(show, hide_index=True, width="stretch")
        return

    wl_tickers = _watchlist_ticker_set()
    _inject_compact_row_css()
    # 排名 | 代码 | 名称 | 理由 | 分 | 评级 | 状态 | 操作(自选+跳转)
    weights = [0.35, 0.65, 0.85, 2.1, 0.35, 0.55, 0.45, 1.0]
    hcols = st.columns(weights)
    for hc, label in zip(
        hcols,
        ["#", "代码", "名称", "理由", "分", "评级", "状态", "操作"],
    ):
        hc.caption(label)

    for _, row in top_df.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        cname = str(row.get("name", ""))
        score = row.get("score")
        score_s = f"{score:.0f}" if score is not None and pd.notna(score) else "—"
        in_wl = ticker in wl_tickers
        owned = bool(row.get("is_owned"))
        if owned:
            status = "🌟持"
        elif in_wl:
            status = "✅池"
        else:
            status = ""
        rating_s = _short_text(row.get("rating", ""), 8)

        cols = st.columns(weights)
        with cols[0]:
            _compact_line(str(row.get("rank", "")))
        with cols[1]:
            _compact_line(ticker)
        with cols[2]:
            _compact_line(_short_text(cname, 8))
        with cols[3]:
            _compact_line(_short_reason(row.get("reason"), 30))
        with cols[4]:
            _compact_line(score_s)
        with cols[5]:
            _compact_line(rating_s)
        with cols[6]:
            _status_cell(status)

        with cols[7]:
            b1, b2 = st.columns(2)
            with b1:
                if owned or in_wl:
                    st.button(
                        "✓", key=f"{key_prefix}_done_{industry}_{ticker}",
                        disabled=True, width="stretch",
                        help="已持仓" if owned else "已在观察池",
                    )
                elif st.button("＋", key=f"{key_prefix}_wl_{industry}_{ticker}", width="stretch", help="加入自选"):
                    n = add_leader_to_watchlist(industry, row)
                    if n:
                        st.toast(f"已加入观察池 {cname}", icon="✅")
                        st.rerun()
                    else:
                        st.toast(f"已在观察池 {cname}", icon="ℹ️")
            with b2:
                if st.button("→", key=f"{key_prefix}_co_{industry}_{ticker}", width="stretch", help="跳公司"):
                    try:
                        from tabs.market import DB_PATH as _DB_PATH
                        from dashboard_helpers import _folder_to_ticker
                        from navigation import goto, PAGE_COMPANY

                        db_mtime = _DB_PATH.stat().st_mtime if _DB_PATH.exists() else 0.0
                        t2f = {v: k for k, v in _folder_to_ticker(db_mtime).items()}
                        folder = t2f.get(ticker, "")
                        if folder:
                            goto(PAGE_COMPANY, company=folder, sub_tab="公司研判")
                        else:
                            st.toast(f"未找到 {cname}", icon="⚠️")
                    except Exception as ex:
                        st.toast(f"跳转失败:{ex}", icon="⚠️")


def _render_knowledge_block(meta: dict) -> None:
    st.markdown("##### 📚 行业知识速读")
    md_rel = meta.get("knowledge_md", "")
    md_path = ROOT / md_rel if md_rel else None
    if md_path and md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        preview = text[:800] + ("…" if len(text) > 800 else "")
        st.markdown(preview)
        with st.expander("📖 查看完整知识 md", expanded=False):
            st.markdown(text)
    else:
        st.caption(f"知识库文件未找到:{md_rel or '—'}")


def render_industry_drilldown(
    industry: str,
    *,
    type_: str | None = None,
    rank_df: pd.DataFrame | None = None,
    interactive_watchlist: bool = False,
    leaders_mode: str = "score",
    key_prefix: str = "drill",
    show_footer_hint: bool = False,
) -> None:
    """渲染单行业 A/B/C/D 四块 UI.

    leaders_mode:
      - ``intro`` — 代表公司基本情况(预选介绍,无评分/自选)
      - ``score`` — 林奇 Top5 评分表(选股/确认用)
    """
    name_to_meta = load_name_to_meta()
    meta = name_to_meta.get(industry)
    if meta is None:
        meta = {}
        st.caption(
            f"ℹ️ 行业 **{industry}** 未在 `industry_master.yaml` 配置 — 显示降级视图"
            "(PE 速览 / 代表公司 / 行业知识可能缺失;ETF 推荐独立可用)"
        )

    type_ = type_ or meta.get("type", "stalwart")
    if rank_df is None:
        rank_df = build_industry_rank_df(name_to_meta)
    sel_rows = rank_df[rank_df["行业"] == industry] if not rank_df.empty else rank_df
    if sel_rows.empty:
        st.caption("📊 PE 速览暂缺(此行业未在 master 配置的排行中)")
    else:
        _render_metrics_row(sel_rows.iloc[0])

    _render_etf_block(
        industry,
        interactive_watchlist=interactive_watchlist,
        key_prefix=key_prefix,
    )
    if leaders_mode == "intro":
        _render_leaders_intro_block(industry, meta)
    else:
        _render_top5_block(
            industry, type_,
            interactive_watchlist=interactive_watchlist,
            key_prefix=key_prefix,
        )
    _render_knowledge_block(meta)

    if show_footer_hint:
        st.info("💡 完整 4 区卡(ETF 叠加图 / 周期诊断)→ 切到 ✅ 行业确定 · 已确认行业档案")


def render_rank_table(rank_df: pd.DataFrame) -> None:
    """展示估值排行表(只读)."""
    if rank_df.empty:
        return
    st.markdown("#### 🔍 聚焦行业估值排行(申万二级 · 按 PE 10y 分位从低到高)")
    show_df = rank_df.copy()
    show_df["PE 中位"] = show_df["PE 中位"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
    show_df["PE 分位(10y)"] = show_df["PE 分位(10y)"].apply(
        lambda v: f"{v:.0f}%" if pd.notna(v) else "—"
    )
    show_df["PB 分位(10y)"] = show_df["PB 分位(10y)"].apply(
        lambda v: f"{v:.0f}%" if pd.notna(v) else "—"
    )
    st.dataframe(show_df, hide_index=True, width="stretch")


__all__ = [
    "load_name_to_meta",
    "build_industry_rank_df",
    "build_industry_leaders_intro",
    "add_leader_to_watchlist",
    "add_etf_to_watchlist",
    "render_industry_drilldown",
    "render_rank_table",
]
