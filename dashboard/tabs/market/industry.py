"""市场 Tab · ⑤ 行业 PE 热力图 + 聚焦行业下钻(目前在 render() 中已迁至独立 sub-tab,保留以备复用)。"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ._helpers import ROOT, _load_industry_pe_latest


def _section_industry_heatmap(db_path: str, mtime: float) -> None:
    """段 ⑤:申万一级 28 行业 PE 中位数,从低到高条形图。"""
    df = _load_industry_pe_latest(db_path, mtime)
    if df.empty:
        st.caption("(industry_pe 表无数据)")
        return
    if "level" in df.columns and df["level"].notna().any():
        df1 = df[df["level"] == 1].copy()
        if df1.empty:
            df1 = df.copy()
    else:
        df1 = df.copy()
    df1 = df1.sort_values("pe_median")
    fig = px.bar(
        df1, x="industry_name", y="pe_median",
        color="pe_median", color_continuous_scale="RdYlGn_r",
        hover_data=["pe_weighted", "pe_arith", "n_companies", "date"],
    )
    fig.update_layout(
        height=460, xaxis_tickangle=-40,
        title=f"{len(df1)} 个行业 · PE 中位数(从低到高 · 绿=低估 / 红=高估)",
        xaxis_title="", yaxis_title="PE 中位数",
        margin=dict(t=50, b=140),
        coloraxis_colorbar=dict(title="PE"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "⚠️ 上图为国民经济行业分类(GB/T 4754,19 粗类)。"
        "下方「下钻」区按申万二级聚焦行业,可对应 ETF / 龙头 / 知识库。"
    )

    _section_industry_drilldown()


def _section_industry_drilldown() -> None:
    """⑤ 下钻区:从聚焦行业里选一个 → ETF + Top 公司 + 知识 + 估值分位。"""
    import yaml as _yaml
    from pathlib import Path as _Path

    master_path = ROOT / ".config" / "industry_master.yaml"
    if not master_path.exists():
        st.info("未配置 industry_master.yaml,跳过下钻区")
        return
    master_yaml = _yaml.safe_load(master_path.read_text(encoding="utf-8")) or {}
    industries = master_yaml.get("industries") or []
    if not industries:
        st.info("industry_master.yaml 无行业条目")
        return

    name_to_meta = {i["name"]: i for i in industries}

    # 计算每个聚焦行业的 PE 分位,按低到高排序作为"被低估"候选
    try:
        from industry.percentile_engine import compute as _pe_compute
    except Exception as e:
        st.warning(f"分位引擎不可用:{e}")
        return

    rows = []
    for ind_name in name_to_meta.keys():
        try:
            r = _pe_compute(ind_name)
            rows.append({
                "行业": ind_name,
                "申万一级": name_to_meta[ind_name].get("sw_l1", "—"),
                "PE 中位": r.pe_median,
                "PE 分位(10y)": r.pe_percentile_10y,
                "PB 分位(10y)": r.pb_percentile_10y,
                "成份股": r.member_count,
            })
        except Exception:
            continue
    if not rows:
        st.info("分位计算无可用行业")
        return
    rank_df = pd.DataFrame(rows).sort_values("PE 分位(10y)", na_position="last").reset_index(drop=True)

    st.markdown("#### 🔍 聚焦行业估值排行(申万二级 · 按 PE 10y 分位从低到高)")
    show_df = rank_df.copy()
    show_df["PE 中位"] = show_df["PE 中位"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
    show_df["PE 分位(10y)"] = show_df["PE 分位(10y)"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
    show_df["PB 分位(10y)"] = show_df["PB 分位(10y)"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
    st.dataframe(show_df, hide_index=True, use_container_width=True)

    # 默认推荐:分位最低的那个
    options = rank_df["行业"].tolist()
    default_idx = 0
    pick = st.selectbox(
        "🎯 选择行业深入了解(默认为分位最低)",
        options,
        index=default_idx,
        key="market_industry_drilldown_pick",
    )
    if not pick:
        return

    meta = name_to_meta[pick]
    type_ = meta.get("type", "stalwart")

    # A · 速览
    sel_row = rank_df[rank_df["行业"] == pick].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    pe_med = sel_row["PE 中位"]
    c1.metric("PE 中位", f"{pe_med:.1f}" if pd.notna(pe_med) else "—",
              f"第 {sel_row['PE 分位(10y)']:.0f}%" if pd.notna(sel_row['PE 分位(10y)']) else "—")
    c2.metric("PB 分位(10y)",
              f"{sel_row['PB 分位(10y)']:.0f}%" if pd.notna(sel_row['PB 分位(10y)']) else "—")
    c3.metric("成份股", f"N={int(sel_row['成份股'])}")
    c4.metric("申万一级", sel_row["申万一级"])

    # B · 推荐 ETF
    st.markdown("##### 📦 推荐 ETF Top 3")
    try:
        from screening.etf_recommender import recommend as _etf_recommend
        etfs = _etf_recommend(pick, top_n=3)
    except Exception as e:
        etfs = []
        st.caption(f"ETF 推荐失败:{e}")
    if etfs:
        etf_df = pd.DataFrame([{
            "代码": c.code, "名称": c.name, "主题": c.theme,
            "1y 涨跌": f"{c.return_1y:+.1%}" if c.return_1y is not None else "—",
            "流动性分位": f"{c.liquidity_score:.0f}" if c.liquidity_score is not None else "—",
            "理由": c.rationale,
        } for c in etfs])
        st.dataframe(etf_df, hide_index=True, use_container_width=True)
    else:
        st.caption("此行业暂无 ETF 配置")

    # C · 推荐公司 Top 5
    st.markdown("##### 🏢 行业龙头 Top 5")
    try:
        from industry.screener import screen_industry as _screen
        top_df = _screen(pick, type_, top_n=5)
        if not top_df.empty:
            show = top_df[["rank", "ticker", "name", "score", "rating", "reason", "is_owned"]].copy()
            show["score"] = show["score"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
            show["is_owned"] = show["is_owned"].map({True: "🌟 已持", False: ""})
            show.columns = ["排名", "代码", "名称", "分数", "评级", "理由", "自选"]
            st.dataframe(show, hide_index=True, use_container_width=True)
        else:
            st.caption("评分候选为空")
    except Exception as e:
        st.caption(f"评分失败:{e}")

    # D · 行业知识(摘要)
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

    st.info("💡 想看完整 4 区行业卡(含 ETF 1y 叠加图 / 周期诊断 / 康波位置)→ 切到 🏭 行业分析 sub-tab")
