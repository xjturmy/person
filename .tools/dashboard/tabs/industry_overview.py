"""行业概况 — 全 SW L1 估值横向对比 + 下钻到 L2/成员公司.

数据来源:
  - `.config/companies.csv` 提供 SW L1 + L2 + ticker 映射(100 家候选池)
  - `data/preson.duckdb.valuation` 提供 PE-TTM / PB 时序(2016- ),按 L1 聚合中位

设计:
  1. 概况表:21 行 SW L1,公司数 / PE·PB 10y 分位 / 截至
  2. 顶部 3 张速览卡:最低估 PE / 最低估 PB / 最高估 PE
  3. 下钻:选中一个 L1 → 时序图 + 成员表 + ETF 对比 + 行业知识
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
ETF_MAPPING_YAML = ROOT / ".tools" / "rules" / "industry_etf_mapping.yaml"

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


def _l2_groups_for_l1(industry_l1: str) -> tuple[list[dict], bool]:
    """返回 (L2 条目列表, 是否来自 companies.csv 合成)。"""
    groups = list(_l2_knowledge_by_l1().get(industry_l1, []) or [])
    if groups:
        return groups, False

    comp = _load_companies(_csv_mtime())
    if comp.empty or "industry" not in comp.columns:
        return [], False

    sub = comp[comp["industry"].astype(str) == industry_l1]
    if sub.empty:
        return [], False

    synthetic: list[dict] = []
    for l2, g in sub.groupby("industry_l2", sort=True):
        l2_name = str(l2).strip()
        if not l2_name or l2_name == "nan":
            continue
        names = g["name"].astype(str).tolist()
        tickers = g["stock"].astype(str).str.zfill(6).tolist()
        synthetic.append({
            "name": l2_name,
            "sw_l1": industry_l1,
            "type": "cyclical",
            "summary": (
                f"自选池 {len(g)} 家 · "
                f"成员:{'、'.join(names[:4])}"
                + ("…" if len(names) > 4 else "")
            ),
            "knowledge_md": "",
            "cycle_attrs": {"type": "待标注", "key_indicators": []},
            "leaders": tickers[:4],
            "_synthetic": True,
            "_members": list(zip(names, tickers)),
        })
    return synthetic, bool(synthetic)


def _render_knowledge(industry_l1: str, *, show_preselect_actions: bool = False) -> None:
    """L1 下钻 · 行业知识速读 — 聚合该 L1 下所有 L2 的 knowledge_md。"""
    st.markdown("##### 📚 行业知识速读")
    groups, from_csv = _l2_groups_for_l1(industry_l1)
    if not groups:
        st.caption(
            f"`industry_master.yaml` 与自选池均无 **{industry_l1}** 的 L2 数据"
        )
        return

    if from_csv:
        st.caption(
            f"ℹ️ **{industry_l1}** 尚未写入 `industry_master.yaml` — "
            f"下方 {len(groups)} 个 L2 卡片由自选池成员自动生成;"
            "深度知识 md 可按需补入 `.config/industry_master.yaml` + `03_macro/02_行业对标数据/`"
        )

    rendered = 0
    for meta in groups:
        l2 = meta.get("name", "—")
        md_rel = meta.get("knowledge_md") or ""
        md_path = ROOT / md_rel if md_rel else None
        cycle_attrs = meta.get("cycle_attrs") or {}
        indicators = cycle_attrs.get("key_indicators") or []
        cycle_type = cycle_attrs.get("type") or meta.get("cycle_type") or "—"
        default_type = meta.get("type") or "stalwart"
        is_synthetic = bool(meta.get("_synthetic"))

        with st.expander(f"📖 {l2} · 周期:{cycle_type}", expanded=(rendered == 0)):
            summary = (meta.get("summary") or "").strip()
            if summary:
                st.markdown(summary)

            if md_path and md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                preview = text[:1200] + ("…" if len(text) > 1200 else "")
                st.markdown(preview)
                if len(text) > 1200:
                    with st.expander("查看完整知识 md", expanded=False):
                        st.markdown(text)
            elif not is_synthetic:
                st.caption(f"知识库文件未配置或缺失:{md_rel or '—'}")

            logic = _l2_framework_logic(l2)
            if logic:
                st.markdown(f"**📐 配置逻辑**:{logic}")

            members = meta.get("_members") or []
            if members:
                mem_str = " · ".join(f"{n}({t})" for n, t in members)
                st.markdown(f"**👥 自选池成员**:{mem_str}")

            if indicators:
                st.markdown("**🔍 关键观察指标**:" + " · ".join(indicators))
            elif is_synthetic:
                st.caption("关键观察指标待写入 industry_master.yaml → cycle_attrs.key_indicators")

            if show_preselect_actions and l2 and l2 != "—":
                if st.button("→ 加入预选", key=f"ov_preselect_{l2}", width="stretch"):
                    try:
                        from tabs.industry._draft_helpers import add_industry_to_draft
                        from navigation import goto, PAGE_MARKET_HUB, SUB_INDUSTRY_PRESELECT

                        if add_industry_to_draft(l2, type_=default_type):
                            st.success(f"✅ 已加入预选:{l2}")
                            goto(PAGE_MARKET_HUB, sub_tab=SUB_INDUSTRY_PRESELECT)
                        else:
                            st.info(f"{l2} 已在 focus 或草稿中")
                    except Exception as ex:
                        st.warning(f"加入预选失败:{ex}")
        rendered += 1

    if show_preselect_actions:
        st.caption("💡 加入预选后 → 「🎯 行业预选」查看 Top 公司 / ETF 并勾选落盘")
    else:
        st.caption("💡 想看 ETF / 龙头 Top / 周期诊断 → 切到 🏭 行业分析 sub-tab")


def _l2_framework_logic(l2: str) -> str:
    """读 industry_etf_mapping.yaml 中 L2 的 framework_logic."""
    if not ETF_MAPPING_YAML.exists():
        return ""
    try:
        import yaml as _yaml
        data = _yaml.safe_load(ETF_MAPPING_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    for m in data.get("mapping") or []:
        if m.get("industry") == l2:
            return str(m.get("framework_logic") or "").strip()
    return ""


def _render_l1_etf_compare(l1: str) -> None:
    """L1 下钻 · 聚合下属 L2 的推荐 ETF,并说明差异."""
    l2_groups, _ = _l2_groups_for_l1(l1)
    l2_names = [str(g.get("name")) for g in l2_groups if g.get("name")]
    if not l2_names:
        return

    try:
        from screening.etf_recommender import recommend as _etf_recommend
    except Exception as ex:
        st.markdown("##### 📦 行业 ETF 对比")
        st.caption(f"ETF 模块加载失败:{ex}")
        return

    by_code: dict[str, dict] = {}
    for l2 in l2_names:
        for etf in _etf_recommend(l2, top_n=5):
            code = str(etf.code).zfill(6)
            rationale = (etf.rationale or "").strip()
            if code not in by_code:
                by_code[code] = {
                    "代码": code,
                    "名称": etf.name,
                    "主题": etf.theme or "—",
                    "1y 涨跌": (
                        f"{etf.return_1y:+.1%}" if etf.return_1y is not None else "—"
                    ),
                    "流动性分位": (
                        f"{etf.liquidity_score:.0f}"
                        if etf.liquidity_score is not None else "—"
                    ),
                    "覆盖 L2": [l2],
                    "差异说明": [rationale] if rationale else [],
                }
            else:
                if l2 not in by_code[code]["覆盖 L2"]:
                    by_code[code]["覆盖 L2"].append(l2)
                if rationale and rationale not in by_code[code]["差异说明"]:
                    by_code[code]["差异说明"].append(rationale)

    st.markdown("##### 📦 行业 ETF 对比")
    st.caption(
        f"聚合 **{l1}** 下 {len(l2_names)} 个 L2（{' · '.join(l2_names)}）的推荐 ETF；"
        "同代码只保留一行，差异见下方说明"
    )

    if not by_code:
        st.info("此一级行业暂无 ETF 配置（请在 industry_etf_mapping.yaml 补充 L2 映射）")
        return

    table_rows = []
    for rec in by_code.values():
        table_rows.append({
            "代码": rec["代码"],
            "名称": rec["名称"],
            "主题": rec["主题"],
            "覆盖 L2": " / ".join(rec["覆盖 L2"]),
            "1y 涨跌": rec["1y 涨跌"],
            "流动性分位": rec["流动性分位"],
        })
    st.dataframe(
        pd.DataFrame(table_rows).sort_values("代码"),
        hide_index=True,
        width="stretch",
    )

    for l2 in l2_names:
        logic = _l2_framework_logic(l2)
        if logic:
            st.caption(f"**{l2}** 配置逻辑:{logic}")

    st.markdown("**ETF 之间的区别**")
    for code in sorted(by_code.keys()):
        rec = by_code[code]
        l2s = "、".join(rec["覆盖 L2"])
        diffs = "；".join(rec["差异说明"]) if rec["差异说明"] else "—"
        st.markdown(
            f"- **{code} {rec['名称']}**（{rec['主题']}）— 覆盖 {l2s}。"
            f"{diffs}"
        )

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


def _inject_preselect_table_css() -> None:
    """L1 待分析表: 绿色勾选 + 行内垂直居中."""
    st.markdown(
        """
        <style>
        section[data-testid="stMain"] div[data-testid="stCheckbox"] input[type="checkbox"] {
            accent-color: #16a34a !important;
            width: 1.15rem;
            height: 1.15rem;
            cursor: pointer;
        }
        section[data-testid="stMain"] div[data-testid="stCheckbox"] input[type="checkbox"]:checked {
            accent-color: #16a34a !important;
        }
        section[data-testid="stMain"] div[data-testid="stCheckbox"] {
            margin: 0;
            padding: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _pct_bar_html(pct: float | None) -> str:
    """统一行高的 PE/PB 进度条 HTML."""
    if pct is None or (isinstance(pct, float) and pd.isna(pct)):
        return "<span style='color:#6b7280;font-size:0.875rem'>—</span>"
    v = max(0.0, min(float(pct), 100.0))
    return (
        f"<div style='display:flex;align-items:center;gap:0.45rem'>"
        f"<span style='min-width:2.2rem;font-size:0.875rem'>{v:.0f}%</span>"
        f"<div style='flex:1;max-width:7rem;background:#e5e7eb;height:0.45rem;"
        f"border-radius:999px;overflow:hidden'>"
        f"<div style='width:{v:.0f}%;background:#6366f1;height:100%'></div>"
        f"</div></div>"
    )


def _l1_checkbox_key(l1: str) -> str:
    import hashlib
    digest = hashlib.md5(l1.encode("utf-8")).hexdigest()[:10]
    return f"l1_pre_{digest}"


def _l1_preselect_is_selected(
    l1: str,
    l1_to_l2: dict[str, list[str]],
    draft_inds: set[str],
) -> bool:
    """合并 shadow set + 草稿 + 当前 run 的 checkbox session state.

    fallback 链:_persist_l1_picks(跨 sub-tab 切换不丢) → widget key → draft。
    """
    from tabs.industry._draft_helpers import l1_marked_in_draft

    shadow = st.session_state.get("_persist_l1_picks")
    if isinstance(shadow, set) and l1 in shadow:
        return True

    key = _l1_checkbox_key(l1)
    if key in st.session_state:
        return bool(st.session_state[key])
    return l1_marked_in_draft(l1, l1_to_l2, draft_inds)


def _sort_l1_preselect_view(
    view: pd.DataFrame,
    l1_to_l2: dict[str, list[str]],
    draft_inds: set[str],
    *,
    selected_first: bool,
) -> pd.DataFrame:
    """已选 L1 置顶,组内按 PE 10y 分位升序."""
    out = view.copy()
    out["_marked"] = out["SW L1 行业"].astype(str).apply(
        lambda l1: _l1_preselect_is_selected(l1, l1_to_l2, draft_inds)
    )
    sort_cols: list[str] = []
    ascending: list[bool] = []
    if selected_first:
        sort_cols.append("_marked")
        ascending.append(False)
    sort_cols.append("PE 10y 分位")
    ascending.append(True)
    out = out.sort_values(sort_cols, ascending=ascending, na_position="last")
    return out.drop(columns="_marked").reset_index(drop=True)


def _render_l1_preselect_rows(
    view: pd.DataFrame,
    l1_ctx: dict,
    draft_inds: set[str],
) -> None:
    """L1 待分析 — 原生 checkbox + 对齐行 + 已选置顶."""
    from tabs.industry._draft_helpers import sync_l1_table_selection

    l1_to_l2 = l1_ctx["l1_to_l2"]
    weights = [0.32, 1.35, 0.55, 1.15, 1.15, 0.75]

    sort_selected_top = st.checkbox(
        "已选置顶",
        value=True,
        key="l1_preselect_sort_selected_top",
        help="勾选后已选申万一级排在最前,其余仍按 PE 10y 分位升序",
    )
    sorted_view = _sort_l1_preselect_view(
        view,
        l1_to_l2,
        draft_inds,
        selected_first=sort_selected_top,
    )

    hcols = st.columns(weights, vertical_alignment="center")
    for hc, label in zip(
        hcols,
        ["待分析", "SW L1 行业", "公司数", "PE 10y 分位", "PB 10y 分位", "截至"],
    ):
        hc.caption(f"**{label}**")

    selected_l1s: set[str] = set()
    for _, row in sorted_view.iterrows():
        l1 = str(row["SW L1 行业"])
        marked = _l1_preselect_is_selected(l1, l1_to_l2, draft_inds)
        cols = st.columns(weights, vertical_alignment="center")
        with cols[0]:
            checked = st.checkbox(
                "待分析",
                value=marked,
                key=_l1_checkbox_key(l1),
                label_visibility="collapsed",
                help="勾选 → 该 L1 下全部 L2 进入行业预选",
            )
        if checked:
            selected_l1s.add(l1)
        with cols[1]:
            if checked:
                st.markdown(
                    f"<span style='color:#15803d;font-weight:600;font-size:0.875rem'>{l1}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<span style='font-size:0.875rem'>{l1}</span>",
                    unsafe_allow_html=True,
                )
        with cols[2]:
            st.markdown(
                f"<span style='font-size:0.875rem'>{int(row['公司数'])}</span>",
                unsafe_allow_html=True,
            )
        with cols[3]:
            st.markdown(_pct_bar_html(row["PE 10y 分位"]), unsafe_allow_html=True)
        with cols[4]:
            st.markdown(_pct_bar_html(row["PB 10y 分位"]), unsafe_allow_html=True)
        with cols[5]:
            st.markdown(
                f"<span style='font-size:0.875rem;color:#6b7280'>{row['截至']}</span>",
                unsafe_allow_html=True,
            )

    # 把当前帧勾选写回 shadow set,跨 sub-tab 切换时 _l1_preselect_is_selected 优先读它
    table_l1_set = set(view["SW L1 行业"].astype(str))
    prev_shadow = st.session_state.get("_persist_l1_picks")
    if not isinstance(prev_shadow, set):
        prev_shadow = set()
    # 仅覆盖本表管辖的 L1,表外 L1 保留(若有其他视图也写过 shadow)
    new_shadow = (prev_shadow - table_l1_set) | set(selected_l1s)
    st.session_state["_persist_l1_picks"] = new_shadow

    sync_l1_table_selection(
        selected_l1s,
        l1_to_l2,
        l1_ctx["master"],
        table_l1_names=set(view["SW L1 行业"].astype(str)),
        focus_names=l1_ctx["focus_names"],
    )


def _render_overview_table(df: pd.DataFrame, *, show_preselect_actions: bool = False) -> None:
    show = df.copy()
    show = show.sort_values("pe_pct", na_position="last")
    show["PE 10y 分位"] = show["pe_pct"]
    show["PB 10y 分位"] = show["pb_pct"]
    show["公司数"] = show["n"].fillna(0).astype(int)
    show["截至"] = pd.to_datetime(show["as_of"], errors="coerce").dt.strftime("%Y-%m-%d")
    view = show[["industry", "公司数", "PE 10y 分位", "PB 10y 分位", "截至"]].rename(
        columns={"industry": "SW L1 行业"}
    )

    col_config = {
        "PE 10y 分位": st.column_config.ProgressColumn(
            "PE 10y 分位", format="%.0f%%", min_value=0, max_value=100,
            help="当前 PE 中位在过去 10 年行业 PE 中位序列中的百分位"),
        "PB 10y 分位": st.column_config.ProgressColumn(
            "PB 10y 分位", format="%.0f%%", min_value=0, max_value=100,
            help="当前 PB 中位在过去 10 年行业 PB 中位序列中的百分位"),
    }
    disabled_cols = list(view.columns)
    l1_ctx: dict | None = None

    if show_preselect_actions:
        try:
            import state as _state
            from funnel import layers as _layers
            from tabs.industry._draft_helpers import (
                build_l1_to_l2_map,
                get_industry_draft,
                l1_marked_in_draft,
            )

            master = _state.industry_master() or {}
            l1_to_l2 = build_l1_to_l2_map(master)
            draft_inds = {d["industry"] for d in get_industry_draft()}
            l1_ctx = {
                "master": master,
                "l1_to_l2": l1_to_l2,
                "focus_names": _layers.get_focus_names() or set(),
            }
            st.caption("勾选「待分析」→ 对应申万一级下全部 L2 进入「🎯 行业预选 · 初步筛选行业」")
            _inject_preselect_table_css()
            _render_l1_preselect_rows(view, l1_ctx, draft_inds)
            return
        except Exception as ex:
            st.caption(f"⚠️ 待分析列不可用:{ex}")

    edited = st.data_editor(
        view,
        hide_index=True,
        width="stretch",
        column_config=col_config,
        disabled=disabled_cols,
        key="industry_overview_l1_table",
    )

    if l1_ctx and "待分析" in edited.columns:
        try:
            from tabs.industry._draft_helpers import sync_l1_table_selection

            selected_l1s = set(
                edited.loc[edited["待分析"].astype(bool), "SW L1 行业"].astype(str)
            )
            sync_l1_table_selection(
                selected_l1s,
                l1_ctx["l1_to_l2"],
                l1_ctx["master"],
                table_l1_names=set(view["SW L1 行业"].astype(str)),
                focus_names=l1_ctx["focus_names"],
            )
        except Exception:
            pass


def render_l1_selection_table(*, show_preselect_actions: bool = True) -> pd.DataFrame:
    """仅 L1 估值表(含待分析勾选),供独立复用(主流程在「行业分析」页)."""
    df = _industry_l1_pe_pb(_db_mtime(), _csv_mtime())
    if df.empty:
        st.warning("无行业聚合数据 — 请确认 data/preson.duckdb 存在且 valuation 表非空")
        return df
    _render_overview_table(df, show_preselect_actions=show_preselect_actions)
    return df


def _render_drill(industry: str, *, show_preselect_actions: bool = False) -> None:
    # 时序图 — 标题用 caption,避免与 expander 标题 + plotly title 三层堆叠
    st.caption(f"📈 **{industry}** · 成员逐日 PE/PB 中位（2016–）")
    ts = _industry_l1_timeseries(industry, _db_mtime(), _csv_mtime())
    if ts.empty:
        st.info("无时序数据")
    else:
        fig = go.Figure()
        if PE_METRIC in ts.columns:
            fig.add_trace(go.Scatter(
                x=ts.index, y=ts[PE_METRIC], mode="lines",
                name="PE 中位", line=dict(color="#6366F1", width=2.2),
            ))
        if PB_METRIC in ts.columns:
            fig.add_trace(go.Scatter(
                x=ts.index, y=ts[PB_METRIC], mode="lines",
                name="PB 中位", yaxis="y2",
                line=dict(color="#10b981", width=2.2),
            ))
        fig.update_layout(
            height=300,
            margin=dict(l=48, r=48, t=8, b=32),
            yaxis=dict(title="PE", side="left", gridcolor="#f3f4f6"),
            yaxis2=dict(title="PB", overlaying="y", side="right", showgrid=False),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="left", x=0,
            ),
            hovermode="x unified",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
        )
        st.plotly_chart(fig, width="stretch")

    # 成员表
    st.markdown("##### 📋 成员公司 PE / PB")
    members = _members_snapshot(industry, _db_mtime(), _csv_mtime())
    if members.empty:
        st.info("无成员数据")
        return
    show = members.copy()
    show["PE"] = show["PE"].apply(_format_num) if "PE" in show.columns else "—"
    show["PB"] = show["PB"].apply(_format_num) if "PB" in show.columns else "—"
    st.dataframe(show, hide_index=True, width="stretch")

    # L2 分布提示
    if "L2 行业" in members.columns:
        l2_counts = members["L2 行业"].value_counts()
        st.caption(
            "L2 分布:" + " · ".join(f"{k}({v})" for k, v in l2_counts.items())
        )

    _render_l1_etf_compare(industry)

    # 行业知识速读(聚合该 L1 下所有 L2)
    _render_knowledge(industry, show_preselect_actions=show_preselect_actions)


# ─── 公共入口 ───────────────────────────────────────────────────────────


def render(*, show_preselect_actions: bool = False) -> None:
    """主入口 — 在 PAGE_MARKET_HUB → 🏭 行业分析 sub-tab 渲染.

    注意:show_preselect_actions 的默认值为 False(独立 sub-tab 使用),
    但 industry/analysis.py 内嵌调用时显式传 True 以暴露"加入预选"按钮。
    调用方需显式指定,不要依赖默认值。
    """
    if not show_preselect_actions:
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
    _render_overview_table(df, show_preselect_actions=show_preselect_actions)

    # 下钻选择 — 行业概况表只读,这里用 selectbox 触发下钻 + 写 session_state
    inds = sorted(df["industry"].dropna().tolist())
    if not inds:
        st.info("行业列表为空 — 无可下钻条目")
        return

    # options 变化时用 shadow 重水化 widget key,避免 Streamlit 静默重置为首项
    _options_sig = tuple(inds)
    _shadow = st.session_state.get("_persist_industry_overview_drill")
    if st.session_state.get("_sig_industry_overview_drill") != _options_sig:
        st.session_state["_sig_industry_overview_drill"] = _options_sig
        if _shadow in inds:
            st.session_state["industry_overview_drill"] = _shadow
        elif st.session_state.get("industry_overview_drill") not in inds:
            st.session_state.pop("industry_overview_drill", None)

    default_idx = 0
    cur = st.session_state.get("focus_industry_l1")
    if cur in inds:
        default_idx = inds.index(cur)

    sel = st.selectbox(
        "选一个行业下钻看细节", inds, index=default_idx,
        key="industry_overview_drill",
    )
    st.session_state["_persist_industry_overview_drill"] = sel
    if sel != st.session_state.get("focus_industry_l1"):
        st.session_state["focus_industry_l1"] = sel

    with st.expander(f"📍 {sel} · 时序 + 成员", expanded=True):
        _render_drill(sel, show_preselect_actions=show_preselect_actions)


if __name__ == "__main__":
    # 离线烟测
    df = _industry_l1_pe_pb(_db_mtime(), _csv_mtime())
    print(f"L1 行业数:{len(df)}")
    if not df.empty:
        print(df.sort_values("pe_pct").head(10).to_string(index=False))
