"""tabs.screener.lynch_pick · 林奇六类分类器选股.

输入:universe(可选继承初步筛选草稿)→ score_lynch_classifier_all
命中(score ≥ 用户阈值)写入 FUNNEL_SCREENER_LYNCH 草稿。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from screening import screener as _scr

from . import _universe
from ._ui_helpers import count_excellent, preset_for_master, render_methodology_card, render_scatter

_SORT_OPTIONS = {
    "评分 ↓": ("score", False),
    "评分 ↑": ("score", True),
    "公司 A→Z": ("name", True),
    "林奇类型": ("lynch_type_cn", True),
}


@st.cache_data(ttl=300)
def _load_screener_data(db_mtime: float, year: int) -> pd.DataFrame:
    return _scr.load_all(fscore_year=year)


@st.cache_data(ttl=3600, show_spinner=False)
def _lynch_scored(db_mtime: float, year: int, tickers_key: str) -> pd.DataFrame:
    df = _load_screener_data(db_mtime, year)
    df = df[df["ticker"].astype(str).str.zfill(6).isin(set(tickers_key.split(",")))]
    if df.empty:
        return df
    return _scr.score_lynch_classifier_all(df)


def _lynch_type_labels(scored: pd.DataFrame) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """返回 (type_id 列表, id→展示标签, 展示标签→id)。"""
    type_rows = (
        scored[["lynch_type", "lynch_type_cn", "lynch_type_emoji"]]
        .drop_duplicates(subset=["lynch_type"])
        .sort_values("lynch_type_cn", na_position="last")
    )
    id_to_label: dict[str, str] = {}
    for _, row in type_rows.iterrows():
        tid = row["lynch_type"] or ""
        id_to_label[tid] = f"{row['lynch_type_emoji']} {row['lynch_type_cn']}"
    type_ids = list(id_to_label.keys())
    label_to_id = {v: k for k, v in id_to_label.items()}
    return type_ids, id_to_label, label_to_id


def render(companies=None, db_mtime: float = 0.0) -> None:
    st.markdown("## 🌱 林奇选股 · 六类分类器")
    st.caption(
        "对 universe(可继承初筛草稿)运行林奇六类自动分类 + 类型专属 5 维评分。"
        "命中(评分 ≥ 阈值)写入草稿,在「✅ 选股确定」汇总入观察池。"
    )

    df_universe = _universe.get_or_block()
    if df_universe is None:
        return

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
        key="lynch_pick_src",
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

    lynch_preset = preset_for_master("lynch") or {
        "name": "林奇六类分析",
        "tagline": "六类公司自动分类 + 类型驱动评估",
        "use_classifier": True,
        "book_origin": "《彼得林奇的成功投资》",
        "knowledge_link": "01_knowledge/03_投资策略与选股/02_彼得林奇投资法/",
    }
    render_methodology_card(lynch_preset)

    tickers_key = ",".join(sorted(df_in["ticker"].astype(str).str.zfill(6).tolist()))
    year = pd.Timestamp.now().year - 1
    with st.spinner("运行林奇六类分类器..."):
        try:
            scored = _lynch_scored(db_mtime, year, tickers_key)
        except Exception as e:
            st.error(f"林奇评分失败:{e}")
            return

    if scored is None or scored.empty:
        st.warning("评分结果为空(可能本地数据不覆盖这些 ticker)。")
        return

    type_counts = scored.groupby(
        ["lynch_type_emoji", "lynch_type_cn"]
    ).size().reset_index(name="count").sort_values("count", ascending=False)
    if not type_counts.empty:
        badges = " · ".join(
            f"{r['lynch_type_emoji']} {r['lynch_type_cn']} **{r['count']}**"
            for _, r in type_counts.iterrows()
        )
        st.caption(f"📊 六类分布:{badges}")

    threshold = st.slider(
        "命中阈值(评分 ≥)", min_value=0, max_value=100, value=60, step=5,
        key="lynch_pick_threshold",
    )

    scored = scored.sort_values("score", ascending=False, na_position="last")
    hit_mask = scored["score"].fillna(-1) >= threshold
    scored["命中"] = hit_mask

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("评分公司", f"{int(scored['score'].notna().sum())}")
    m2.metric("命中数", f"{int(hit_mask.sum())}")
    m3.metric("阈值", f"≥ {threshold}")
    pass_excellent = count_excellent(scored, lynch_preset)
    m4.metric("🟢 优秀级", f"{pass_excellent}" if pass_excellent is not None else "—")

    render_scatter(scored, lynch_preset, has_score=True, chart_key="lynch_scatter")

    st.markdown("##### 📋 候选清单")

    type_ids, id_to_label, label_to_id = _lynch_type_labels(scored)
    pill_labels = [id_to_label[tid] for tid in type_ids]

    fc1, fc2 = st.columns([3, 1])
    with fc1:
        selected_labels = st.pills(
            "林奇类型筛选(可多选,点选切换)",
            options=pill_labels,
            default=pill_labels,
            selection_mode="multi",
            key="lynch_pick_type_pills",
            help="筛选表格中显示的类型;默认全选",
        )
    with fc2:
        sort_label = st.selectbox(
            "排序",
            list(_SORT_OPTIONS.keys()),
            index=0,
            key="lynch_pick_sort",
        )

    if not selected_labels:
        st.warning("请至少选择一种林奇类型。")
        return

    selected_types = {label_to_id[lb] for lb in selected_labels if lb in label_to_id}
    table_df = scored[scored["lynch_type"].fillna("").isin(selected_types)].copy()
    if len(selected_labels) < len(pill_labels):
        st.caption(f"🔎 类型筛选:**{len(table_df)}** / {len(scored)} 只")

    sort_col, sort_asc = _SORT_OPTIONS[sort_label]
    if sort_col in table_df.columns:
        table_df = table_df.sort_values(
            sort_col, ascending=sort_asc, na_position="last",
        )

    if table_df.empty:
        st.warning("当前类型筛选无公司 — 请调整类型或阈值。")
        return

    show = table_df.copy()
    show["林奇类型"] = show.apply(
        lambda r: f"{r.get('lynch_type_emoji', '⚪')} {r.get('lynch_type_cn', '—')}", axis=1,
    )
    show["评分"] = show["score"].round(0)
    show["评级"] = show["rating"].fillna("—")
    show["优势"] = show["dim_top"].fillna("—")
    show["短板"] = show["dim_bot"].fillna("—")
    cols = ["命中", "公司", "代码", "林奇类型", "评分", "评级", "优势", "短板"]
    show = show.rename(columns={"name": "公司", "ticker": "代码"})
    show = show[[c for c in cols if c in show.columns]]

    edited = st.data_editor(
        show,
        use_container_width=True, hide_index=True, num_rows="fixed",
        disabled=[c for c in show.columns if c != "命中"],
        column_config={
            "命中": st.column_config.CheckboxColumn("命中", default=False, width="small"),
            "评分": st.column_config.NumberColumn("评分", format="%d"),
            "林奇类型": st.column_config.TextColumn(
                "林奇类型",
                help="用上方「林奇类型筛选」pills 过滤;列菜单可升序/降序排序",
            ),
            "评级": st.column_config.TextColumn("评级"),
            "优势": st.column_config.TextColumn("优势"),
            "短板": st.column_config.TextColumn("短板"),
        },
        key="lynch_pick_table",
    )

    hit_codes = (
        edited.loc[edited["命中"], "代码"].astype(str).str.zfill(6).tolist()
        if "命中" in edited.columns else []
    )
    try:
        from funnel import session as _session
        _session.set_draft(_session.FUNNEL_SCREENER_LYNCH, list(hit_codes))
    except Exception:
        pass

    st.caption(f"✏️ 林奇命中草稿已同步:{len(hit_codes)} 只 → 到「选股确定」汇总")


__all__ = ["render"]
