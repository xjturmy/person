"""v2.5 行业分析 Tab — 8 聚焦行业 4 区行业卡 + 顶部 banner + sidebar 编辑入口.

4 区结构(每行业):
  A · 行业速览        — 周期阶段 / PE 中位+分位 / PB 中位+分位 / 成份股数(metric 4 列)
  B · 推荐公司 Top 7  — industry_screener.screen_industry,固定列 DataFrame
  C · 推荐 ETF Top 3  — etf_recommender.recommend + 1y 归一化叠加图
  D · 行业知识        — 渲染 industry_master.yaml.knowledge_md + 关键观察指标

依赖(全部已就绪):
  - industry_percentile_engine.compute
  - industry_cycle_engine.diagnose
  - etf_recommender.recommend
  - industry_screener.screen_industry / screen_all_focus
  - .config/industry_master.yaml + focus_industries.yaml

入口:
  from tabs.industry_focus import render
  render()  # 不依赖 selected/companies(行业级 Tab)
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

INDUSTRY_MASTER_YAML = ROOT / ".config" / "industry_master.yaml"
FOCUS_YAML = ROOT / ".config" / "focus_industries.yaml"
ETF_DB = ROOT / "data" / "etf.duckdb"

GREEN_BG = "#dcfce7"
GREEN_FG = "#14532d"
GREEN_GRAD = "linear-gradient(135deg,#16a34a 0%,#22c55e 100%)"

PHASE_EMOJI = {
    "rising": "📈", "topping": "🔻", "falling": "📉",
    "bottoming": "🟢", "sideways": "🔄",
}
LAYER_CN = {"defensive": "防御层", "offensive": "进攻层", "auxiliary": "过渡"}


@st.cache_data(ttl=1800)
def _load_yaml(path_str: str) -> dict:
    p = Path(path_str)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


@st.cache_data(ttl=3600)
def _industry_master_dict() -> dict:
    d = _load_yaml(str(INDUSTRY_MASTER_YAML))
    return {i["name"]: i for i in (d.get("industries") or [])}


@st.cache_data(ttl=3600)
def _cached_percentile(industry: str) -> dict:
    from industry.percentile_engine import compute
    r = compute(industry)
    return {
        "pe_median": r.pe_median,
        "pe_percentile_10y": r.pe_percentile_10y,
        "pb_median": r.pb_median,
        "pb_percentile_10y": r.pb_percentile_10y,
        "member_count": r.member_count,
        "data_source": r.data_source,
    }


@st.cache_data(ttl=3600)
def _cached_cycle(industry: str) -> dict:
    from industry.cycle import diagnose
    r = diagnose(industry)
    return {
        "phase": r.phase, "phase_cn": r.phase_cn,
        "cycle_type": r.cycle_type,
        "kondratieff_position": r.kondratieff_position,
        "confidence": float(r.confidence),
        "rationale": r.rationale,
    }


@st.cache_data(ttl=3600)
def _cached_etf(industry: str, top_n: int = 3) -> list[dict]:
    from screening.etf_recommender import recommend
    out = recommend(industry, top_n=top_n)
    return [
        {
            "code": c.code, "name": c.name, "theme": c.theme,
            "fund_type": c.fund_type, "last_close": c.last_close,
            "return_1y": c.return_1y, "avg_turnover_60d": c.avg_turnover_60d,
            "liquidity_score": c.liquidity_score, "rationale": c.rationale,
            "layer": c.layer,
            "target_pct": list(c.target_pct) if c.target_pct else None,
        }
        for c in out
    ]


@st.cache_data(ttl=3600)
def _cached_top7(industry: str, type_: str, top_n: int = 7) -> pd.DataFrame:
    from industry.screener import screen_industry
    return screen_industry(industry, type_, top_n=top_n)


def _save_focus_yaml(focus_list: list[str], top_n: int, market_cap_min: int) -> None:
    master = _industry_master_dict()
    out_focus = [
        {"industry": ind, "type": master.get(ind, {}).get("type", "stalwart"), "weight": 1.0}
        for ind in focus_list
    ]
    text = yaml.safe_dump(
        {"focus": out_focus, "top_n": top_n, "market_cap_min": market_cap_min},
        allow_unicode=True, sort_keys=False,
    )
    FOCUS_YAML.write_text(text, encoding="utf-8")


def _format_pct(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.0f}%"


def _format_num(v, fmt: str = "{:.2f}") -> str:
    if v is None or pd.isna(v):
        return "—"
    return fmt.format(v)


def _render_top_banner(focus_list: list[dict]) -> None:
    """G1: 顶部 8 行业速览(2 行 4 列)."""
    st.markdown(
        f"<div style='background:{GREEN_GRAD};padding:1.2rem;border-radius:8px;"
        f"color:white;margin-bottom:1rem;'>"
        f"<h3 style='margin:0;'>🏭 行业分析 · {len(focus_list)} 聚焦行业</h3>"
        f"<p style='margin:0.3rem 0 0;opacity:0.9;'>"
        f"自顶向下视角:周期 × 估值分位 × 推荐公司 × ETF 选择</p></div>",
        unsafe_allow_html=True,
    )

    per_row = 4
    for i in range(0, len(focus_list), per_row):
        cols = st.columns(per_row)
        for j, f in enumerate(focus_list[i:i + per_row]):
            with cols[j]:
                ind = f["industry"]
                pct = _cached_percentile(ind)
                cyc = _cached_cycle(ind)
                phase_s = f"{PHASE_EMOJI.get(cyc['phase'], '❓')} {cyc['phase_cn']}"
                st.markdown(
                    f"<div style='background:{GREEN_BG};padding:0.6rem;"
                    f"border-radius:6px;border-left:3px solid {GREEN_FG};"
                    f"font-size:0.85rem;'>"
                    f"<b>{ind}</b><br>"
                    f"{phase_s} · PE 第{_format_pct(pct['pe_percentile_10y'])}<br>"
                    f"N={pct['member_count']} · {cyc['cycle_type']}</div>",
                    unsafe_allow_html=True,
                )
        st.write("")


def _render_etf_overlay(codes: list[str], names: list[str]) -> None:
    """C 区底部:N 只 ETF 1y 价格归一化叠加图."""
    if not ETF_DB.exists() or not codes:
        return
    try:
        con = duckdb.connect(str(ETF_DB), read_only=True)
        ph = ",".join(["?"] * len(codes))
        df = con.execute(
            f"SELECT etf_code, date, close FROM etf_prices "
            f"WHERE etf_code IN ({ph}) "
            f"AND date >= (CURRENT_DATE - INTERVAL 365 DAY) "
            f"ORDER BY date",
            codes,
        ).fetchdf()
        con.close()
    except Exception:
        return
    if df.empty:
        return

    fig = go.Figure()
    name_map = dict(zip(codes, names))
    for code in codes:
        sub = df[df["etf_code"] == code]
        if sub.empty:
            continue
        base = sub["close"].iloc[0]
        if not base or base <= 0:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"],
            y=sub["close"] / base * 100,
            mode="lines",
            name=f"{code} {name_map.get(code, '')}",
        ))
    fig.update_layout(
        title="ETF 1y 归一化叠加(起点=100)",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_industry_card(focus_item: dict) -> None:
    """单行业 4 区卡:A 速览 / B Top 7 / C ETF / D 知识."""
    ind = focus_item["industry"]
    type_ = focus_item.get("type", "stalwart")
    master = _industry_master_dict().get(ind, {})

    pct = _cached_percentile(ind)
    cyc = _cached_cycle(ind)

    title = f"🏭 {ind}({master.get('sw_l1', '—')}) · 类型 {type_} · {cyc['cycle_type']}"
    with st.expander(title, expanded=True):
        # ── A 区 · 行业速览 ──
        st.markdown("##### 📍 A · 行业速览")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "当前周期阶段",
            f"{PHASE_EMOJI.get(cyc['phase'], '❓')} {cyc['phase_cn']}",
            f"信心 {cyc['confidence']:.1f}",
        )
        c2.metric("PE 中位", _format_num(pct["pe_median"]),
                  f"第 {_format_pct(pct['pe_percentile_10y'])}")
        c3.metric("PB 中位", _format_num(pct["pb_median"]),
                  f"第 {_format_pct(pct['pb_percentile_10y'])}")
        c4.metric("成份股", f"N={pct['member_count']}",
                  pct["data_source"])
        st.caption(f"📝 {cyc['rationale']}")

        # ── B 区 · 推荐公司 Top 7 ──
        st.divider()
        st.markdown("##### 📍 B · 推荐公司 Top 7")
        try:
            top_df = _cached_top7(ind, type_, top_n=7)
            if top_df.empty:
                st.info("暂无评分候选(数据池可能为空)")
            else:
                show = top_df[["rank", "ticker", "name", "score", "rating",
                               "reason", "is_owned"]].copy()
                show["score"] = show["score"].apply(
                    lambda x: f"{x:.0f}" if pd.notna(x) else "—"
                )
                show["is_owned"] = show["is_owned"].map({True: "🌟 已持", False: ""})
                show.columns = ["排名", "代码", "名称", "分数", "评级", "理由", "自选"]
                st.dataframe(show, hide_index=True, use_container_width=True)
                pm = top_df.iloc[0].get("primary_master", "—")
                ds = top_df.iloc[0].get("data_source", "—")
                st.caption(f"评分链路:{type_} → primary={pm};数据池:{ds}")
        except Exception as e:
            st.warning(f"评分失败:{e}")

        # ── C 区 · 推荐 ETF Top 3 ──
        st.divider()
        st.markdown("##### 📍 C · 推荐 ETF + 选择建议")
        etfs = _cached_etf(ind, top_n=3)
        if not etfs:
            st.info("此行业暂无 ETF 配置")
        else:
            etf_df = pd.DataFrame([{
                "代码": c["code"],
                "名称": c["name"],
                "主题": c["theme"],
                "1y 涨跌": f"{c['return_1y']:+.1%}" if c["return_1y"] is not None else "—",
                "流动性分位": f"{c['liquidity_score']:.0f}" if c["liquidity_score"] is not None else "—",
                "层级": LAYER_CN.get(c.get("layer"), "—"),
                "推荐理由": c["rationale"],
            } for c in etfs])
            st.dataframe(etf_df, hide_index=True, use_container_width=True)

            layer = etfs[0].get("layer")
            target = etfs[0].get("target_pct")
            if target:
                st.caption(
                    f"📐 此行业属{LAYER_CN.get(layer, '—')},建议配置 {target[0]}-{target[1]}%"
                )

            try:
                _render_etf_overlay(
                    [c["code"] for c in etfs],
                    [c["name"] for c in etfs],
                )
            except Exception:
                pass

        # ── D 区 · 行业知识 ──
        st.divider()
        st.markdown("##### 📍 D · 行业知识 + 周期特性")
        kc1, kc2 = st.columns([2, 1])
        with kc1:
            md_rel = master.get("knowledge_md", "")
            md_path = ROOT / md_rel if md_rel else None
            if md_path and md_path.exists():
                md_text = md_path.read_text(encoding="utf-8")
                if len(md_text) > 1500:
                    st.markdown(md_text[:1500])
                    with st.expander("📖 查看完整知识 md", expanded=False):
                        st.markdown(md_text)
                else:
                    st.markdown(md_text)
            else:
                st.info(f"知识库文件未找到:{md_rel or '—'}")
        with kc2:
            st.markdown("**🔍 关键观察指标**")
            indicators = master.get("cycle_attrs", {}).get("key_indicators", []) or []
            for kw in indicators:
                st.markdown(f"- {kw}")
            st.markdown(f"**周期类型**:{cyc['cycle_type']}")
            kp = cyc.get("kondratieff_position") or "—"
            st.markdown(f"**康波位置**:{kp}")


def _render_sidebar_editor() -> None:
    """G2: sidebar「⚙️ 编辑聚焦行业」expander."""
    cfg = _load_yaml(str(FOCUS_YAML))
    cur_focus = [f["industry"] for f in (cfg.get("focus") or [])]
    cur_top_n = int(cfg.get("top_n", 7))
    cur_min_yi = int(int(cfg.get("market_cap_min", 5_000_000_000)) // 1e8)

    with st.sidebar.expander("⚙️ 编辑聚焦行业", expanded=False):
        st.caption("从 industry_master.yaml 全部 SW L2 中选择")
        all_inds = list(_industry_master_dict().keys())
        with st.form("focus_editor", clear_on_submit=False):
            sel = st.multiselect("聚焦行业", all_inds, default=cur_focus)
            top_n = st.number_input(
                "Top N(每行业推荐)", min_value=3, max_value=15, value=cur_top_n, step=1
            )
            min_cap_yi = st.number_input(
                "市值门槛(亿元)", min_value=1, max_value=10000,
                value=cur_min_yi, step=10,
            )
            submitted = st.form_submit_button("💾 保存")
            if submitted:
                if not sel:
                    st.error("至少选 1 个行业")
                else:
                    _save_focus_yaml(sel, int(top_n), int(min_cap_yi * 1e8))
                    st.cache_data.clear()
                    st.success("✅ 已更新 focus_industries.yaml,刷新生效")


def _render_valuation_matrix() -> None:
    """⑤ 行业估值矩阵(从 L1 市场周期迁来):粗粒度热力图 + 细粒度下钻。"""
    st.markdown("### ⑤ 行业估值矩阵 · 哪些行业被低估?")
    try:
        from tabs.market import (
            _section_industry_heatmap,
            _section_industry_drilldown,
            DB_PATH as _DB_PATH,
        )
        db_mtime = _DB_PATH.stat().st_mtime if _DB_PATH.exists() else 0.0
        _section_industry_heatmap(str(_DB_PATH), db_mtime)
    except Exception as e:
        st.warning(f"行业估值矩阵加载失败:{e}")


def render() -> None:
    """主入口."""
    cfg = _load_yaml(str(FOCUS_YAML))
    focus_list = cfg.get("focus") or []

    _render_sidebar_editor()

    # ⑤ 行业估值矩阵 — 自顶向下入口(粗类热力图 + 细类下钻)
    _render_valuation_matrix()
    st.markdown("---")

    if not focus_list:
        st.warning(
            "focus_industries.yaml 未配置聚焦行业,请在 sidebar「⚙️ 编辑聚焦行业」中添加"
        )
        return

    _render_top_banner(focus_list)

    for f in focus_list:
        _render_industry_card(f)


if __name__ == "__main__":
    # 离线检查 — 不依赖 streamlit 渲染
    cfg = _load_yaml(str(FOCUS_YAML))
    print(f"focus 行业数:{len(cfg.get('focus') or [])}")
    print(f"industry_master 行业数:{len(_industry_master_dict())}")
