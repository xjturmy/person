"""行业概况 — 全 SW L1 估值横向对比 + 下钻到 L2/成员公司.

数据来源:
  - `.config/companies.csv` 提供 SW L1 + L2 + ticker 映射(100 家候选池)
  - `data/preson.duckdb.valuation` 提供 PE-TTM / PB 时序(2016- ),按 L1 聚合中位

设计:
  1. 概况表:21 行 SW L1,公司数 / PE 中位 / PE 10y 分位 / PB 中位 / PB 10y 分位
  2. 顶部 3 张速览卡:最低估 PE / 最低估 PB / 最高估 PE
  3. 下钻:选中一个 L1 → 展开 L2 表 + 成员公司表 + PE/PB 时序图
  4. 与 `industry_focus.py`(8 聚焦行业 L2 详情卡)共存,不重复造数据

入口: from tabs.industry_overview import render; render()
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
try:
    from dashboard_helpers import get_conn
except Exception:
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    try:
        from dashboard_helpers import get_conn
    except Exception:
        _sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
        from dashboard_helpers import get_conn

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

COMPANIES_CSV = ROOT / ".config" / "companies.csv"
DUCKDB_PATH = ROOT / "data" / "preson.duckdb"
INDUSTRY_MASTER_YAML = ROOT / ".config" / "industry_master.yaml"

PE_METRIC = "PE-TTM"
PB_METRIC = "PB"


# ─── 数据层 ─────────────────────────────────────────────────────────────


def _csv_mtime() -> float:
    return COMPANIES_CSV.stat().st_mtime if COMPANIES_CSV.exists() else 0.0


def _db_mtime() -> float:
    return DUCKDB_PATH.stat().st_mtime if DUCKDB_PATH.exists() else 0.0


@st.cache_data(ttl=900)
def _load_companies(_mtime: float) -> pd.DataFrame:
    if not COMPANIES_CSV.exists():
        return pd.DataFrame()
    rows = list(csv.DictReader(COMPANIES_CSV.open(encoding="utf-8")))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["stock"] = df["stock"].astype(str).str.zfill(6)
    return df[["folder", "stock", "name", "industry", "industry_l2", "category"]]


@st.cache_data(ttl=900)
def _industry_l1_pe_pb(_db_mtime: float, _csv_mtime: float) -> pd.DataFrame:
    """对每个 SW L1,聚合其成员的逐日 PE/PB 中位序列,并算当前值 + 10y 分位.

    返回列:industry / n / pe_now / pe_pct / pb_now / pb_pct / as_of
    pe_pct/pb_pct 为 0-100 整数,代表当前中位在 10 年中位序列中的分位.
    """
    try:
        import duckdb
    except ImportError:
        return pd.DataFrame()
    if not DUCKDB_PATH.exists():
        return pd.DataFrame()

    companies = _load_companies(_csv_mtime)
    if companies.empty or "industry" not in companies.columns:
        return pd.DataFrame()

    con = get_conn(str(DUCKDB_PATH))
    try:
        # 一次性拉 100 家公司的 PE/PB 全量(~10y · 日级,2 metric · 100 家 ≈ 50万行,可控)
        df = con.execute(
            "SELECT ticker, date, metric, value FROM valuation "
            "WHERE metric IN (?, ?) AND value > 0",
            [PE_METRIC, PB_METRIC],
        ).fetchdf()
    except Exception:
        return pd.DataFrame()
    finally:
        pass  # get_conn 单例,不关
    if df.empty:
        return pd.DataFrame()

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df = df.merge(
        companies[["stock", "industry"]].rename(columns={"stock": "ticker"}),
        on="ticker", how="inner",
    )
    if df.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for (ind, metric), sub in df.groupby(["industry", "metric"]):
        # 行业逐日中位:对当日所有成员取 median(已先过滤 value>0)
        daily = sub.groupby("date")["value"].median()
        if daily.empty:
            continue
        cur = float(daily.iloc[-1])
        s = pd.to_numeric(daily, errors="coerce").dropna()
        pct = (s <= cur).sum() / len(s) * 100.0 if not s.empty else None
        rows.append({
            "industry": ind, "metric": metric,
            "value": cur, "percentile": pct,
            "as_of": daily.index.max(),
        })

    wide = pd.DataFrame(rows)
    if wide.empty:
        return pd.DataFrame()
    pe = wide[wide["metric"] == PE_METRIC].set_index("industry")
    pb = wide[wide["metric"] == PB_METRIC].set_index("industry")
    n_by_ind = companies.groupby("industry")["stock"].nunique()

    out = pd.DataFrame({
        "n": n_by_ind,
        "pe_now": pe["value"], "pe_pct": pe["percentile"],
        "pb_now": pb["value"], "pb_pct": pb["percentile"],
        "as_of": pe["as_of"],
    }).dropna(subset=["pe_now", "pb_now"], how="all")
    out.index.name = "industry"
    return out.reset_index()


@st.cache_data(ttl=900)
def _industry_l1_timeseries(industry_l1: str, _db_mtime: float, _csv_mtime: float) -> pd.DataFrame:
    """单一 L1 的 PE/PB 逐日中位时序(用于下钻区折线图)."""
    try:
        import duckdb
    except ImportError:
        return pd.DataFrame()
    companies = _load_companies(_csv_mtime)
    tickers = companies.loc[companies["industry"] == industry_l1, "stock"].tolist()
    if not tickers or not DUCKDB_PATH.exists():
        return pd.DataFrame()
    con = get_conn(str(DUCKDB_PATH))
    try:
        ph = ",".join(["?"] * len(tickers))
        df = con.execute(
            f"SELECT date, metric, value FROM valuation "
            f"WHERE metric IN (?, ?) AND value > 0 AND ticker IN ({ph})",
            [PE_METRIC, PB_METRIC, *tickers],
        ).fetchdf()
    except Exception:
        return pd.DataFrame()
    finally:
        pass  # get_conn 单例,不关
    if df.empty:
        return df
    g = df.groupby(["date", "metric"])["value"].median().unstack("metric")
    g.index = pd.to_datetime(g.index, errors="coerce")
    return g.sort_index()


@st.cache_data(ttl=900)
def _members_snapshot(industry_l1: str, _db_mtime: float, _csv_mtime: float) -> pd.DataFrame:
    """L1 内每家公司的当前 PE/PB(取该 ticker valuation 最新非空值)."""
    try:
        import duckdb
    except ImportError:
        return pd.DataFrame()
    companies = _load_companies(_csv_mtime)
    sub = companies[companies["industry"] == industry_l1].copy()
    if sub.empty or not DUCKDB_PATH.exists():
        return sub
    tickers = sub["stock"].tolist()
    con = get_conn(str(DUCKDB_PATH))
    try:
        ph = ",".join(["?"] * len(tickers))
        df = con.execute(
            f"SELECT ticker, metric, value FROM (\n"
            f"  SELECT ticker, metric, value, date,\n"
            f"    ROW_NUMBER() OVER (PARTITION BY ticker, metric ORDER BY date DESC) rn\n"
            f"  FROM valuation\n"
            f"  WHERE ticker IN ({ph}) AND metric IN (?, ?) AND value > 0\n"
            f") WHERE rn = 1",
            [*tickers, PE_METRIC, PB_METRIC],
        ).fetchdf()
    except Exception:
        return sub
    finally:
        pass  # get_conn 单例,不关
    if df.empty:
        return sub
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    wide = df.pivot(index="ticker", columns="metric", values="value").reset_index()
    out = sub.merge(wide, left_on="stock", right_on="ticker", how="left")
    return out[["folder", "stock", "name", "industry_l2", "PE-TTM", "PB"]].rename(
        columns={"stock": "代码", "name": "名称", "industry_l2": "L2 行业",
                 "PE-TTM": "PE", "PB": "PB", "folder": "目录"}
    )


@st.cache_data(ttl=3600)
def _l2_knowledge_by_l1() -> dict[str, list[dict]]:
    """读 industry_master.yaml,按 sw_l1 归集 L2 条目(含 name / knowledge_md / cycle_attrs)。"""
    if not INDUSTRY_MASTER_YAML.exists():
        return {}
    try:
        import yaml as _yaml
        data = _yaml.safe_load(INDUSTRY_MASTER_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    out: dict[str, list[dict]] = {}
    for item in (data.get("industries") or []):
        l1 = item.get("sw_l1") or "—"
        out.setdefault(l1, []).append(item)
    return out


def _render_knowledge(industry_l1: str) -> None:
    """L1 下钻 · 行业知识速读 — 聚合该 L1 下所有 L2 的 knowledge_md。"""
    st.markdown("##### 📚 行业知识速读")
    groups = _l2_knowledge_by_l1().get(industry_l1, [])
    if not groups:
        st.caption(f"`industry_master.yaml` 中无 sw_l1={industry_l1} 的 L2 条目")
        return

    rendered = 0
    for meta in groups:
        l2 = meta.get("name", "—")
        md_rel = meta.get("knowledge_md") or ""
        md_path = ROOT / md_rel if md_rel else None
        indicators = (meta.get("cycle_attrs") or {}).get("key_indicators") or []
        cycle_type = (meta.get("cycle_attrs") or {}).get("cycle_type") or meta.get("cycle_type") or "—"

        with st.expander(f"📖 {l2} · 周期:{cycle_type}", expanded=(rendered == 0)):
            if md_path and md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                preview = text[:1200] + ("…" if len(text) > 1200 else "")
                st.markdown(preview)
                if len(text) > 1200:
                    with st.expander("查看完整知识 md", expanded=False):
                        st.markdown(text)
            else:
                st.caption(f"知识库文件未配置或缺失:{md_rel or '—'}")
            if indicators:
                st.markdown("**🔍 关键观察指标**:" + " · ".join(indicators))
        rendered += 1

    st.caption("💡 想看 ETF / 龙头 Top / 周期诊断 → 切到 🏭 行业分析 sub-tab")

# ─── 渲染层 ─────────────────────────────────────────────────────────────


def _pct_color(p: float | None) -> str:
    if p is None or pd.isna(p):
        return "#9ca3af"
    if p < 30:
        return "#16a34a"  # 绿:低估
    if p < 70:
        return "#ca8a04"  # 黄:中性
    return "#dc2626"      # 红:高估


def _format_pct(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.0f}%"


def _format_num(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.2f}"


def _render_quick_cards(df: pd.DataFrame) -> None:
    valid_pe = df.dropna(subset=["pe_pct"])
    valid_pb = df.dropna(subset=["pb_pct"])
    cards = []
    if not valid_pe.empty:
        lo = valid_pe.loc[valid_pe["pe_pct"].idxmin()]
        cards.append(("🟢 PE 最低估", lo["industry"],
                      f"分位 {lo['pe_pct']:.0f}% · PE {lo['pe_now']:.1f}"))
    if not valid_pb.empty:
        lo = valid_pb.loc[valid_pb["pb_pct"].idxmin()]
        cards.append(("🟢 PB 最低估", lo["industry"],
                      f"分位 {lo['pb_pct']:.0f}% · PB {lo['pb_now']:.2f}"))
    if not valid_pe.empty:
        hi = valid_pe.loc[valid_pe["pe_pct"].idxmax()]
        cards.append(("🔴 PE 最高估", hi["industry"],
                      f"分位 {hi['pe_pct']:.0f}% · PE {hi['pe_now']:.1f}"))
    cards.append(("🎯 当前聚焦",
                  st.session_state.get("focus_industry_l1") or "— 未选 —",
                  "点表格选择 / 下方下钻"))

    cols = st.columns(len(cards))
    for col, (title, val, sub) in zip(cols, cards):
        with col:
            st.markdown(
                f"<div style='background:#f9fafb;padding:0.7rem;border-radius:6px;"
                f"border-left:3px solid #6366F1;'>"
                f"<div style='font-size:0.8rem;color:#6b7280;'>{title}</div>"
                f"<div style='font-size:1.05rem;font-weight:600;margin:0.2rem 0;'>{val}</div>"
                f"<div style='font-size:0.78rem;color:#6b7280;'>{sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _render_overview_table(df: pd.DataFrame) -> None:
    show = df.copy()
    show = show.sort_values("pe_pct", na_position="last")
    show["PE 中位"] = show["pe_now"].apply(_format_num)
    show["PE 10y 分位"] = show["pe_pct"]  # 用 ProgressColumn 渲染条
    show["PB 中位"] = show["pb_now"].apply(_format_num)
    show["PB 10y 分位"] = show["pb_pct"]
    show["公司数"] = show["n"].fillna(0).astype(int)
    show["截至"] = pd.to_datetime(show["as_of"], errors="coerce").dt.strftime("%Y-%m-%d")
    view = show[["industry", "公司数", "PE 中位", "PE 10y 分位",
                 "PB 中位", "PB 10y 分位", "截至"]].rename(
        columns={"industry": "SW L1 行业"}
    )

    st.dataframe(
        view, hide_index=True, use_container_width=True,
        column_config={
            "PE 10y 分位": st.column_config.ProgressColumn(
                "PE 10y 分位", format="%.0f%%", min_value=0, max_value=100,
                help="当前 PE 中位在过去 10 年行业 PE 中位序列中的百分位"),
            "PB 10y 分位": st.column_config.ProgressColumn(
                "PB 10y 分位", format="%.0f%%", min_value=0, max_value=100,
                help="当前 PB 中位在过去 10 年行业 PB 中位序列中的百分位"),
        },
    )


def _render_drill(industry: str) -> None:
    st.markdown(f"### 🔍 下钻 · {industry}")

    # 时序图
    ts = _industry_l1_timeseries(industry, _db_mtime(), _csv_mtime())
    if ts.empty:
        st.info("无时序数据")
    else:
        fig = go.Figure()
        if PE_METRIC in ts.columns:
            fig.add_trace(go.Scatter(
                x=ts.index, y=ts[PE_METRIC], mode="lines",
                name="PE 中位", line=dict(color="#6366F1", width=2.4),
            ))
        if PB_METRIC in ts.columns:
            fig.add_trace(go.Scatter(
                x=ts.index, y=ts[PB_METRIC], mode="lines",
                name="PB 中位", yaxis="y2",
                line=dict(color="#10b981", width=2.4),
            ))
        fig.update_layout(
            height=320, margin=dict(l=20, r=20, t=30, b=20),
            yaxis=dict(title="PE", side="left"),
            yaxis2=dict(title="PB", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=1.1),
            title=f"{industry} · 成员逐日中位(2016- )",
        )
        st.plotly_chart(fig, use_container_width=True)

    # 成员表
    st.markdown("##### 📋 行业内公司当前 PE / PB")
    members = _members_snapshot(industry, _db_mtime(), _csv_mtime())
    if members.empty:
        st.info("无成员数据")
        return
    show = members.copy()
    show["PE"] = show["PE"].apply(_format_num) if "PE" in show.columns else "—"
    show["PB"] = show["PB"].apply(_format_num) if "PB" in show.columns else "—"
    st.dataframe(show, hide_index=True, use_container_width=True)

    # L2 分布提示
    if "L2 行业" in members.columns:
        l2_counts = members["L2 行业"].value_counts()
        st.caption(
            "L2 分布:" + " · ".join(f"{k}({v})" for k, v in l2_counts.items())
        )

    # 行业知识速读(聚合该 L1 下所有 L2)
    _render_knowledge(industry)


# ─── 公共入口 ───────────────────────────────────────────────────────────


def render() -> None:
    """主入口 — 在 PAGE_MARKET_HUB → 🏭 行业分析 sub-tab 顶部渲染."""
    st.markdown("### 🌐 行业概况 · 自选池 SW L1 估值全景")
    st.caption(
        "21 个一级行业 · 100 家成员逐日中位 PE/PB 与 10y 分位 — "
        "从「便宜行业」入手,再下钻到具体公司"
    )

    df = _industry_l1_pe_pb(_db_mtime(), _csv_mtime())
    if df.empty:
        st.warning("无行业聚合数据 — 请确认 data/preson.duckdb 存在且 valuation 表非空")
        return

    _render_quick_cards(df)
    st.write("")
    _render_overview_table(df)

    # 下钻选择 — 行业概况表只读,这里用 selectbox 触发下钻 + 写 session_state
    inds = sorted(df["industry"].dropna().tolist())
    default_idx = 0
    cur = st.session_state.get("focus_industry_l1")
    if cur in inds:
        default_idx = inds.index(cur)

    sel = st.selectbox(
        "选一个行业下钻看细节", inds, index=default_idx,
        key="industry_overview_drill",
    )
    if sel != st.session_state.get("focus_industry_l1"):
        st.session_state["focus_industry_l1"] = sel

    with st.expander(f"📍 {sel} · 时序 + 成员", expanded=True):
        _render_drill(sel)


if __name__ == "__main__":
    # 离线烟测
    df = _industry_l1_pe_pb(_db_mtime(), _csv_mtime())
    print(f"L1 行业数:{len(df)}")
    if not df.empty:
        print(df.sort_values("pe_pct").head(10).to_string(index=False))
