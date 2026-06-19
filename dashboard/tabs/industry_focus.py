# v2.9 P0b 已迁移到 tabs/industry/(analysis / preselect / confirm 三件套)。
# 本文件保留兼容:tabs.industry.analysis 直接复用此处的渲染函数/helper;
# 主入口 render() 已被 PAGE_MARKET_HUB 4 sub-tab 替代,P5 清理。
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
ETF_MAPPING_YAML = ROOT / ".tools" / "rules" / "industry_etf_mapping.yaml"
BROAD_ETF_YAML = ROOT / ".config" / "broad_index_etf.yaml"
PORTFOLIO_YAML = ROOT / ".config" / "portfolio.yaml"
KONDRATIEFF_YAML = DASHBOARD_DIR / "data" / "kondratieff.yaml"
ETF_DB = ROOT / "data" / "etf.duckdb"
MACRO_DB = ROOT / "data" / "macro.duckdb"

GREEN_BG = "#dcfce7"
GREEN_FG = "#14532d"
GREEN_GRAD = "linear-gradient(135deg,#16a34a 0%,#22c55e 100%)"
BLUE_BG = "#dbeafe"
BLUE_FG = "#1e3a8a"

PHASE_EMOJI = {
    "rising": "📈", "topping": "🔻", "falling": "📉",
    "bottoming": "🟢", "sideways": "🔄",
}
LAYER_CN = {"defensive": "防御层", "offensive": "进攻层", "auxiliary": "过渡"}
LAYER_STYLE = {
    "defensive": (GREEN_BG, GREEN_FG),
    "offensive": (BLUE_BG, BLUE_FG),
    "auxiliary": ("#f3f4f6", "#374151"),
}

OFFENSIVE_DIRECTION = {
    "通信设备": "AI",
    "电池": "能源",
    "化学制药": "生物",
}
CYCLE_TYPE_LAYER = {"防御": "defensive", "成长": "offensive"}

TYPE_METHODOLOGY = {
    "stalwart": ("彼得林奇 · 稳健增长", "01_knowledge/03_投资策略与选股/02_彼得林奇投资法/"),
    "fast_grower": ("彼得林奇 · 快速增长", "01_knowledge/03_投资策略与选股/02_彼得林奇投资法/"),
    "cyclical": ("彼得林奇 · 周期型", "01_knowledge/03_投资策略与选股/02_彼得林奇投资法/"),
    "slow_grower": ("彼得林奇 · 缓慢增长", "01_knowledge/03_投资策略与选股/02_彼得林奇投资法/"),
    "bank": ("格雷厄姆 · 银行专版", "01_knowledge/03_投资策略与选股/01_格雷厄姆投资法/"),
    "insurance": ("格雷厄姆 · 保险专版", "01_knowledge/03_投资策略与选股/01_格雷厄姆投资法/"),
}


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


@st.cache_data(ttl=3600)
def _load_etf_mapping() -> dict:
    """industry → {layer, target_pct, direction}."""
    d = _load_yaml(str(ETF_MAPPING_YAML))
    out: dict = {}
    for row in d.get("mapping") or []:
        ind = row.get("industry")
        if not ind:
            continue
        out[ind] = {
            "layer": row.get("layer"),
            "target_pct": row.get("target_pct"),
            "direction": row.get("direction"),
        }
    return out


@st.cache_data(ttl=3600)
def _load_broad_etfs() -> list[dict]:
    d = _load_yaml(str(BROAD_ETF_YAML))
    return [e for e in (d.get("broad_etfs") or []) if e.get("visible", True)]


@st.cache_data(ttl=3600)
def _load_kondratieff_banner() -> dict:
    if not KONDRATIEFF_YAML.exists():
        return {}
    try:
        return yaml.safe_load(KONDRATIEFF_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


@st.cache_data(ttl=600)
def _portfolio_etf_held() -> tuple[set[str], set[str]]:
    """返回 (holdings tickers, benchmark/index names)."""
    d = _load_yaml(str(PORTFOLIO_YAML))
    tickers: set[str] = set()
    names: set[str] = set()
    for h in d.get("holdings") or []:
        t = str(h.get("ticker", "")).strip()
        if t:
            tickers.add(t.zfill(6))
        n = str(h.get("name", "")).strip()
        if n:
            names.add(n)
    for b in d.get("benchmarks") or []:
        n = str(b.get("name", "")).strip()
        if n:
            names.add(n)
    return tickers, names


def _resolve_layer(industry: str, mapping: dict, master: dict) -> str:
    meta = mapping.get(industry) or {}
    layer = meta.get("layer")
    if layer:
        return str(layer)
    cycle_type = (master.get("cycle_attrs") or {}).get("type", "")
    return CYCLE_TYPE_LAYER.get(cycle_type, "auxiliary")


def _short_text(text: str, max_len: int = 14) -> str:
    if not text or text == "—":
        return "—"
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


@st.cache_data(ttl=1800)
def _etf_1y_return(code: str) -> float | None:
    if not ETF_DB.exists() or not code:
        return None
    try:
        con = duckdb.connect(str(ETF_DB), read_only=True)
        df = con.execute(
            "SELECT close FROM etf_prices "
            "WHERE etf_code = ? AND date >= (CURRENT_DATE - INTERVAL 365 DAY) "
            "ORDER BY date",
            [code],
        ).fetchdf()
        con.close()
    except Exception:
        return None
    if df.empty or len(df) < 2:
        return None
    base = df["close"].iloc[0]
    last = df["close"].iloc[-1]
    if not base or base <= 0:
        return None
    return float(last / base - 1.0)


def _macro_pe_display(pe_key: str | None) -> str:
    if not pe_key:
        return "—"
    if not MACRO_DB.exists():
        return "—"
    try:
        from tabs.market._helpers import _load_macro_latest
        mtime = MACRO_DB.stat().st_mtime
        row = _load_macro_latest(str(MACRO_DB), pe_key, mtime)
        if row and row.get("value") is not None:
            pct = row.get("pct_5y")
            pct_s = f" · 5y {_format_pct(pct * 100)}" if pct is not None else ""
            return f"{row['value']:.1f}{pct_s}"
    except Exception:
        pass
    return "—"


def _render_industry_mini_card(focus_item: dict, mapping: dict) -> None:
    ind = focus_item["industry"]
    type_ = focus_item.get("type", "stalwart")
    master = _industry_master_dict().get(ind, {})
    layer = _resolve_layer(ind, mapping, master)
    bg, fg = LAYER_STYLE.get(layer, LAYER_STYLE["auxiliary"])
    badge = LAYER_CN.get(layer, layer)

    pct = _cached_percentile(ind)
    cyc = _cached_cycle(ind)
    meta = mapping.get(ind) or {}
    target = meta.get("target_pct")
    target_s = f"{target[0]}-{target[1]}%" if target else "—"

    direction = OFFENSIVE_DIRECTION.get(ind) or meta.get("direction")
    dir_tag = f" · 🎯{direction}" if direction and layer == "offensive" else ""

    top1_name, top1_etf = "—", "—"
    try:
        top_df = _cached_top7(ind, type_, top_n=1)
        if not top_df.empty:
            top1_name = str(top_df.iloc[0].get("name", "—"))
    except Exception:
        pass
    try:
        etfs = _cached_etf(ind, top_n=1)
        if etfs:
            top1_etf = etfs[0].get("code", "—")
    except Exception:
        pass

    phase_s = f"{PHASE_EMOJI.get(cyc['phase'], '❓')} {cyc['phase_cn']}"
    kp = _short_text(cyc.get("kondratieff_position") or "—", 16)

    st.markdown(
        f"<div style='background:{bg};padding:0.55rem 0.65rem;"
        f"border-radius:6px;border-left:3px solid {fg};font-size:0.82rem;'>"
        f"<b>{ind}</b> <span style='color:{fg};font-size:0.75rem;'>[{badge}]{dir_tag}</span><br>"
        f"{phase_s} · PE 第{_format_pct(pct['pe_percentile_10y'])} · 配 {target_s}<br>"
        f"康波:{kp}<br>"
        f"Top1 {top1_name} · ETF {top1_etf}</div>",
        unsafe_allow_html=True,
    )


def _render_broad_etf_mini_card(broad_item: dict) -> None:
    layer = broad_item.get("layer", "defensive")
    bg, fg = LAYER_STYLE.get(layer, LAYER_STYLE["auxiliary"])
    badge = LAYER_CN.get(layer, layer)
    code = broad_item.get("etf_code", "—")
    name = broad_item.get("name", "—")
    role = _short_text(broad_item.get("role", ""), 22)
    target = broad_item.get("target_pct")
    target_s = f"{target[0]}-{target[1]}%" if target else "—"

    ret = _etf_1y_return(code)
    ret_s = f"{ret:+.1%}" if ret is not None else "—"
    pe_s = _macro_pe_display(broad_item.get("macro_pe_key"))

    held_tickers, held_names = _portfolio_etf_held()
    held = code in held_tickers or name in held_names
    held_s = "🌟 已配" if held else ""

    st.markdown(
        f"<div style='background:{bg};padding:0.55rem 0.65rem;"
        f"border-radius:6px;border-left:3px solid {fg};font-size:0.82rem;'>"
        f"<b>{name}</b> <span style='color:{fg};font-size:0.75rem;'>[{badge}]</span> {held_s}<br>"
        f"{code} · 1y {ret_s} · 配 {target_s}<br>"
        f"PE {pe_s}<br>"
        f"<span style='opacity:0.85;'>{role}</span></div>",
        unsafe_allow_html=True,
    )


def _render_coverage_check(focus_list: list[dict], broad_etfs: list[dict]) -> None:
    focus_inds = {f["industry"] for f in focus_list}
    themes = {"AI": "通信设备", "能源": "电池", "生物": "化学制药"}
    lines = []
    for theme, ind in themes.items():
        hit = "✅" if ind in focus_inds else "⚠️ 未覆盖"
        lines.append(f"- **{theme}**({ind}): {hit}")

    visible_broad = [e["name"] for e in broad_etfs if e.get("visible", True)]
    if visible_broad:
        lines.append(f"- **宽基 ETF**: {' · '.join(visible_broad)}")

    missing_def = []
    for note_ind in ("红利低波", "黄金"):
        if note_ind not in focus_inds:
            missing_def.append(note_ind)
    if missing_def:
        lines.append(
            f"- **防御缺口**: {' / '.join(missing_def)} 未在聚焦行业 — "
            f"请通过宽基 / 专项 ETF 配置(见 industry_etf_mapping)"
        )

    st.markdown("\n".join(lines))


def _render_top_banner(focus_list: list[dict]) -> None:
    """康波驱动 banner:行业 mini-card + 宽基 ETF + 覆盖度检查."""
    mapping = _load_etf_mapping()
    kdf = _load_kondratieff_banner()
    broad_etfs = _load_broad_etfs()

    cycle = kdf.get("cycle", "—")
    phase = kdf.get("phase", "—")
    phase_emoji = kdf.get("phase_emoji", "🔴")
    strategy = kdf.get("strategy_summary", "")
    alloc = _load_yaml(str(ETF_MAPPING_YAML)).get("target_allocation") or {}
    def_rng = alloc.get("defensive", [65, 75])
    off_rng = alloc.get("offensive", [25, 35])

    st.markdown(
        f"<div style='background:{GREEN_GRAD};padding:1rem 1.2rem;border-radius:8px;"
        f"color:white;margin-bottom:0.8rem;'>"
        f"<h3 style='margin:0;'>🏭 行业分析 · {len(focus_list)} 聚焦行业</h3>"
        f"<p style='margin:0.35rem 0 0;opacity:0.92;font-size:0.9rem;'>"
        f"{phase_emoji} {cycle} · <b>{phase}</b>"
        f"{' · ' + strategy if strategy else ''}"
        f"<br>配置框架:防御 {def_rng[0]}-{def_rng[1]}% / 进攻 {off_rng[0]}-{off_rng[1]}%</p></div>",
        unsafe_allow_html=True,
    )

    defensive, offensive, other = [], [], []
    for f in focus_list:
        ind = f["industry"]
        master = _industry_master_dict().get(ind, {})
        layer = _resolve_layer(ind, mapping, master)
        if layer == "defensive":
            defensive.append(f)
        elif layer == "offensive":
            offensive.append(f)
        else:
            other.append(f)

    for title, group in [
        ("🛡️ 防御层行业", defensive),
        ("⚔️ 进攻层行业", offensive),
    ]:
        if not group:
            continue
        st.markdown(f"**{title}**")
        per_row = 4
        for i in range(0, len(group), per_row):
            cols = st.columns(per_row)
            for j, f in enumerate(group[i:i + per_row]):
                with cols[j]:
                    _render_industry_mini_card(f, mapping)
        st.write("")

    if other:
        st.markdown("**🔄 过渡层行业**")
        cols = st.columns(min(4, len(other)))
        for j, f in enumerate(other):
            with cols[j]:
                _render_industry_mini_card(f, mapping)
        st.write("")

    if broad_etfs:
        st.markdown("**📊 宽基 ETF · 卫星底仓**")
        def_broad = [e for e in broad_etfs if e.get("layer") == "defensive"]
        off_broad = [e for e in broad_etfs if e.get("layer") == "offensive"]
        for title, group in [("防御宽基", def_broad), ("进攻宽基", off_broad)]:
            if not group:
                continue
            st.caption(title)
            cols = st.columns(len(group))
            for j, item in enumerate(group):
                with cols[j]:
                    _render_broad_etf_mini_card(item)
        st.write("")

    with st.expander("🔍 康波覆盖度检查", expanded=True):
        _render_coverage_check(focus_list, broad_etfs)


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

                # Top 3 快捷操作:加自选 / 跳公司
                top3 = top_df.head(3)
                btn_cols = st.columns(len(top3))
                for bi, (_, row) in enumerate(top3.iterrows()):
                    ticker = str(row.get("ticker", "")).zfill(6)
                    cname = str(row.get("name", ""))
                    with btn_cols[bi]:
                        st.caption(f"{row.get('rank', bi + 1)}. {cname} ({ticker})")
                        if st.button("🌟 加自选", key=f"wl_{ind}_{ticker}", use_container_width=True):
                            try:
                                import watchlist as _wl
                                n = _wl.add(
                                    pd.DataFrame([{
                                        "ticker": ticker,
                                        "name": cname,
                                        "source_industry": ind,
                                    }]),
                                    preset=f"行业分析·{ind}",
                                )
                                if n:
                                    st.success(f"✅ 已加入观察池:{cname}")
                                else:
                                    st.info(f"已在观察池:{cname}")
                            except Exception as ex:
                                st.info(f"观察池写入不可用 — 请切到「选股确定」手动添加 ({ex})")
                        if st.button("📊 跳公司", key=f"co_{ind}_{ticker}", use_container_width=True):
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
                                    st.warning(f"未找到 {cname}({ticker}) 的公司目录")
                            except Exception as ex:
                                st.warning(f"跳转失败:{ex}")
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

            label, kpath = TYPE_METHODOLOGY.get(type_, ("评分方法论", "01_knowledge/03_投资策略与选股/"))
            st.markdown(
                f"**📚 方法论**: [{label}]({kpath})"
            )


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
    """行业估值矩阵(从 L1 市场周期迁来):粗粒度热力图 + 细粒度下钻。"""
    st.markdown("### 行业估值矩阵 · 哪些行业被低估?")
    try:
        from tabs.market import DB_PATH as _DB_PATH, _section_industry_heatmap

        db_mtime = _DB_PATH.stat().st_mtime if _DB_PATH.exists() else 0.0
        _section_industry_heatmap(str(_DB_PATH), db_mtime)
    except Exception as e:
        st.warning(f"行业估值矩阵加载失败:{e}")


def render() -> None:
    """主入口."""
    cfg = _load_yaml(str(FOCUS_YAML))
    focus_list = cfg.get("focus") or []

    _render_sidebar_editor()

    # 行业估值矩阵 — 自顶向下入口(粗类热力图 + 细类下钻)
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
