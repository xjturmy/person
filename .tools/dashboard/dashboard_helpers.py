"""V4/V5/多大师/V8 数据 + 渲染 helper(从 app.py 抽出)。

- V4 MCP valuation_percentile / mcp_freshness
- V5 Piotroski F-Score
- 多大师评分(list_executable_masters / master_score)
- V8 SWS 6 维评分(company_score / render_radar / render_score_cards / render_strategies_detail)
- overlay_price(跨 tab 时序图右轴叠加股价)

注:仍然 import streamlit 因为多个 helper 用 @st.cache_data 装饰 + render_* 写 st.* widget。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import duckdb
except ImportError:
    duckdb = None

ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = ROOT / ".tools" / "mcp"
SCORE_DIR = ROOT / ".tools" / "score"
RULES_DIR = ROOT / ".tools" / "rules"
for _p in (MCP_DIR, SCORE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ui.score_card as sc
from data_context import (
    latest_annual_year as _context_latest_annual_year,
    latest_financial_period as _context_latest_financial_period,
)

try:
    import peers.radar as pr
except Exception:
    pr = None

DUCKDB_PATH = ROOT / "data" / "preson.duckdb"
ETF_DB_PATH = ROOT / "data" / "etf.duckdb"
PEERS_ETF_CSV = ROOT / ".config" / "peers_etf.csv"
COMPANIES_DIR = ROOT / "02_companies"
VALIDATE_REPORT = ROOT / ".temp" / "validate_report.md"
SETTINGS_FILE = ROOT / ".claude" / "settings.json"
INBOX_FILE = ROOT / ".temp" / "dashboard_inbox.md"
CONTEXT_FILE = ROOT / ".temp" / "current_context.md"

MODULES = {
    "估值": ("valuation", "估值.csv"),
    "盈利": ("profitability", "盈利.csv"),
    "成长": ("growth", "成长.csv"),
    "现金流": ("cashflow", "现金流.csv"),
    "安全性": ("safety", "安全性.csv"),
}

PERCENTILE_TRIPLES = {
    "PE-TTM": ("PE-TTM_分位点", "PE-TTM_80%分位点值", "PE-TTM_50%分位点值", "PE-TTM_20%分位点值"),
    "PB": ("PB_分位点", "PB_80%分位点值", "PB_50%分位点值", "PB_20%分位点值"),
    "PS-TTM": ("PS-TTM_分位点", "PS-TTM_80%分位点值", "PS-TTM_50%分位点值", "PS-TTM_20%分位点值"),
}


# ─── 数据访问 + mtime 缓存(S2)─────────────────────────────────────────
def _db_mtime() -> float:
    """每次 rerun 重新读 mtime,变更即触发下游 cache 失效。"""
    return DUCKDB_PATH.stat().st_mtime if DUCKDB_PATH.exists() else 0.0


@st.cache_resource
def _duckdb_conn(mtime: float):
    if duckdb is None or mtime == 0.0:
        return None
    try:
        return duckdb.connect(str(DUCKDB_PATH), read_only=True)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def latest_financial_period(mtime: float, ticker: str = "") -> dict:
    """Return latest financial statement period from core statement tables."""
    return _context_latest_financial_period(DUCKDB_PATH, ticker=ticker)


@st.cache_data(ttl=600, show_spinner=False)
def latest_annual_year(mtime: float, ticker: str = "") -> int | None:
    """Return latest complete annual report year available in statement tables."""
    return _context_latest_annual_year(DUCKDB_PATH, ticker=ticker)


@st.cache_resource
def get_conn(db_path: str):
    """按路径返回 DuckDB 只读连接(单例,调用方勿 close)。"""
    if duckdb is None:
        raise ImportError("duckdb 未安装")
    try:
        return duckdb.connect(db_path, read_only=True)
    except Exception:
        return duckdb.connect(db_path)


@st.cache_data(ttl=300)
def _folder_to_ticker(mtime: float) -> dict[str, str]:
    con = _duckdb_conn(mtime)
    if con is None:
        return {}
    try:
        rows = con.execute("SELECT folder, ticker FROM companies").fetchall()
        return {f: t for f, t in rows}
    except Exception:
        return {}


@st.cache_data(ttl=300)
def list_companies(mtime: float) -> list[str]:
    con = _duckdb_conn(mtime)
    if con is not None:
        try:
            rows = con.execute("SELECT folder FROM companies ORDER BY folder").fetchall()
            return [r[0] for r in rows if r[0]]
        except Exception:
            pass
    pattern = re.compile(r"^\d{2}_.+")
    return sorted(p.name for p in COMPANIES_DIR.iterdir() if p.is_dir() and pattern.match(p.name))


def _load_metric_csv(company: str, module: str) -> pd.DataFrame:
    fname = MODULES[module][1]
    path = COMPANIES_DIR / company / "01_基本面数据" / "历史数据" / fname
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
    return df


@st.cache_data(ttl=300)
def load_metric(company: str, module: str, mtime: float) -> pd.DataFrame:
    """从 DuckDB 长表 pivot 回宽表;数据库缺时回退 CSV。"""
    if module not in MODULES:
        return pd.DataFrame()
    con = _duckdb_conn(mtime)
    table = MODULES[module][0]
    ticker = _folder_to_ticker(mtime).get(company)
    if con is not None and ticker:
        try:
            long_df = con.execute(
                f"SELECT date, metric, value FROM {table} WHERE ticker = ? ORDER BY date",
                [ticker],
            ).fetchdf()
            if not long_df.empty:
                wide = long_df.pivot_table(
                    index="date", columns="metric", values="value", aggfunc="last"
                ).reset_index()
                wide.columns.name = None
                wide["date"] = pd.to_datetime(wide["date"], errors="coerce")
                return wide.dropna(subset=["date"]).sort_values("date")
        except Exception:
            pass
    return _load_metric_csv(company, module)


@st.cache_data(ttl=300)
def load_prices(ticker: str, mtime: float) -> pd.DataFrame:
    con = _duckdb_conn(mtime)
    if con is None:
        return pd.DataFrame()
    try:
        df = con.execute(
            "SELECT date, open, close, high, low, volume, pct_change "
            "FROM prices WHERE ticker = ? ORDER BY date",
            [ticker],
        ).fetchdf()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def list_industries(mtime: float) -> list[tuple[str, str]]:
    con = _duckdb_conn(mtime)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT industry_code, industry_name FROM industry_pe "
            "GROUP BY industry_code, industry_name ORDER BY industry_code"
        ).fetchall()
        return [(c, n) for c, n in rows if c]
    except Exception:
        return []


@st.cache_data(ttl=300)
def load_industry_pe(code: str, mtime: float) -> pd.DataFrame:
    con = _duckdb_conn(mtime)
    if con is None:
        return pd.DataFrame()
    try:
        df = con.execute(
            "SELECT date, pe_median, pe_weighted, pe_arith, n_companies "
            "FROM industry_pe WHERE industry_code = ? ORDER BY date",
            [code],
        ).fetchdf()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()




# ─── V4: MCP valuation_percentile 直连(自算 10y 分位)──────────────────
def _mcp_data_source():
    try:
        import data_source as ds
        return ds
    except Exception:
        return None


@st.cache_data(ttl=300)
def mcp_percentile(ticker: str, metric: str, window: str, mtime: float) -> float | None:
    """返回 0-1 浮点(与 CSV 字段口径一致)。失败返回 None。"""
    ds = _mcp_data_source()
    if ds is None or not ticker:
        return None
    try:
        r = ds.percentile(ticker, metric, window=window)
        return float(r["percentile"]) / 100.0
    except Exception:
        return None


@st.cache_data(ttl=300)
def mcp_freshness(ticker: str, metric: str, mtime: float) -> dict | None:
    """从 MCP `query_metric` 拿单指标 freshness meta。失败 None。"""
    ds = _mcp_data_source()
    if ds is None or not ticker:
        return None
    try:
        r = ds.query_metric(ticker, metric, period="1y")
        return r["meta"]  # {ticker, name, metric, col, period, count, latest_date, lag_days, freshness}
    except Exception:
        return None


# ─── V5: Piotroski F-Score 接首页 ──────────────────────────────────────
def _score_engine():
    try:
        import engine
        return engine
    except Exception:
        return None


@st.cache_data(ttl=600)
def piotroski_score(ticker: str, year: int, mtime: float) -> tuple[int | None, int | None]:
    """返回 (total, max)。引擎/规则/数据缺失返回 (None, None)。"""
    r = piotroski_detail(ticker, year, mtime)
    if r is None:
        return None, None
    return r["total"], r["max"]


@st.cache_data(ttl=600)
def piotroski_detail(ticker: str, year: int, mtime: float) -> dict | None:
    """返回 {total, max, items: [(rule_id, name, passed)]}。失败 None。"""
    eng = _score_engine()
    if eng is None or not ticker:
        return None
    rules_path = RULES_DIR / "piotroski.yaml"
    if not rules_path.exists():
        return None
    try:
        data = eng.load_duckdb_data(ticker, db_path=DUCKDB_PATH)
        result = eng.run_score(rules_path, data, year)
        if result is None:
            return None
        return {
            "total": int(round(result.total_score)),
            "max": len(result.details),
            "items": [(d.rule_id, d.name, d.passed) for d in result.details],
        }
    except Exception:
        return None


def _freshness_icon(tag: str | None) -> str:
    return {"fresh": "🟢", "stale": "🟡", "very_stale": "🟠", "outdated": "🔴", "unknown": "⚫"}.get(tag or "unknown", "⚫")


# ─── 多大师评分 helper(全景红绿灯支持选大师)───────────────────────────
RULES_DIR_FOR_MASTERS = ROOT / ".tools" / "rules"


@st.cache_data(ttl=600)
def list_executable_masters() -> list[str]:
    """返回 rules/ 下有可执行 rules 顶层的大师名(不含金融业适配版)。"""
    import yaml as _yaml
    out: list[str] = []
    for p in sorted(RULES_DIR_FOR_MASTERS.glob("*.yaml")):
        if p.name.startswith("_") or p.stem in ("piotroski_bank", "piotroski_insurance"):
            continue
        try:
            doc = _yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and ("rules" in doc or "garp_rules" in doc):
            out.append(p.stem)
    return out


@st.cache_data(ttl=600)
def master_score(ticker: str, master: str, year: int, mtime: float) -> tuple[int | None, int | None, int | None]:
    """跑指定大师的评分,返回 (得分, 总规则数, 有效项数);失败返回 (None, None, None)。

    兼容 lynch 用 garp_rules 顶层。
    """
    eng = _score_engine()
    if eng is None or not ticker or not master:
        return None, None, None

    rules_path = RULES_DIR_FOR_MASTERS / f"{master}.yaml"
    if not rules_path.exists():
        return None, None, None

    import yaml as _yaml
    try:
        doc = _yaml.safe_load(rules_path.read_text(encoding="utf-8"))
        if "rules" not in doc:
            for alt in ("garp_rules", "core_rules"):
                if alt in doc:
                    doc["rules"] = doc[alt]
                    break

        data = eng.load_duckdb_data(ticker, db_path=DUCKDB_PATH)

        # 行业自动切换(piotroski_bank/insurance)
        industry_files = doc.get("industry_specific_files") or {}
        specific = industry_files.get(data.industry)
        if specific:
            return master_score(ticker, Path(specific).stem, year, mtime)

        if data.industry in (doc.get("exclude_industries") or []):
            return None, None, None

        rules = doc.get("rules", [])
        if not rules:
            return None, None, None

        evaluator = eng.FormulaEvaluator(data, year)
        score = 0.0
        valid = 0
        for rule in rules:
            f = rule.get("formula", "") or rule.get("formula_primary", "") or ""
            # 跳过多行 / 复合表达式
            if "\n" in f or "==" in f or "Z'" in f or "DCF" in f:
                continue
            rule_score, passed, _ = eng.eval_rule(rule, evaluator)
            if passed is None:
                continue
            valid += 1
            score += rule_score
        return int(round(score)), len(rules), valid
    except Exception:
        return None, None, None


# ─── V8: SWS 风格 6 维评分 + 雪花图 + 评分卡 ───────────────────────────
@st.cache_data(ttl=600)
def company_score(ticker: str, mtime: float, pct_window: str = "10y", year: int | None = None):
    """返回 score_card.CompanyScore;失败返回 None。

    优先读 analytics.duckdb 预计算(<5ms);仅默认参数(10y / 去年)走预计算,
    非默认参数或库缺失/未覆盖时降级 live 计算(sc.compute_dimensions ~0.5s)。
    """
    if not ticker:
        return None
    if pct_window == "10y" and year is None:
        try:
            import analytics_store as _store
            pre = _store.company_score(ticker)
            if pre is not None:
                return pre
        except Exception:
            pass
    try:
        return sc.compute_dimensions(ticker, db_path=DUCKDB_PATH, pct_window=pct_window, strategies_year=year)
    except Exception as e:
        st.session_state["_score_err"] = f"{type(e).__name__}: {e}"
        return None


SCORE_DIM_ORDER = ["valuation", "profitability", "growth", "cashflow", "safety", "strategies"]


def render_radar(score) -> go.Figure:
    """6 维 0-100 雷达图(plotly Scatterpolar)。缺失维度按 50 中性占位。"""
    labels = [sc.DIM_LABEL.get(k, k) for k in SCORE_DIM_ORDER]
    values = []
    for k in SCORE_DIM_ORDER:
        d = score.dims.get(k)
        values.append(d.score if (d and d.score is not None) else 50)
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed, theta=labels_closed,
        fill="toself", line=dict(color="#0d6efd", width=2),
        fillcolor="rgba(13,110,253,0.18)", name="得分",
    ))
    fig.add_trace(go.Scatterpolar(
        r=[75] * (len(labels) + 1), theta=labels_closed,
        line=dict(color="#1b8a3a", dash="dash", width=1), name="优秀线 75",
    ))
    fig.add_trace(go.Scatterpolar(
        r=[45] * (len(labels) + 1), theta=labels_closed,
        line=dict(color="#d9534f", dash="dot", width=1), name="警戒线 45",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickvals=[20, 40, 60, 80, 100])),
        showlegend=False, height=360, margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


def render_score_cards(score) -> None:
    """6 张评分卡:估值 / 盈利 / 成长 / 现金流 / 安全 / 策略。"""
    cols = st.columns(3)
    for i, key in enumerate(SCORE_DIM_ORDER):
        d = score.dims.get(key)
        col = cols[i % 3]
        with col.container(border=True):
            label = sc.DIM_LABEL.get(key, key)
            score_val = d.score if d else None
            badge = (d.badge if d else "⚪") or "⚪"
            score_str = f"**{score_val:.0f}** / 100" if score_val is not None else "**N/A**"
            st.markdown(f"##### {badge} {label} · {score_str}")
            if d and d.note:
                st.caption(d.note)


def overlay_price(fig: go.Figure, ticker: str, date_min, date_max) -> go.Figure:
    """若 session_state['overlay_price'] 为真,在 fig 右轴叠加 prices 收盘价。"""
    if not st.session_state.get("overlay_price"):
        return fig
    if not ticker:
        return fig
    prices = load_prices(ticker, DB_MTIME)
    if prices.empty:
        return fig
    try:
        pv = prices[(prices["date"] >= pd.Timestamp(date_min)) & (prices["date"] <= pd.Timestamp(date_max))]
    except Exception:
        return fig
    if pv.empty:
        return fig
    fig.add_trace(go.Scatter(
        x=pv["date"], y=pv["close"], name="📈 收盘价", yaxis="y2", mode="lines",
        line=dict(color="#888", width=1.4, dash="dot"), opacity=0.85,
    ))
    fig.update_layout(yaxis2=dict(
        title="股价 ¥", overlaying="y", side="right", showgrid=False, zeroline=False,
    ))
    return fig


def render_strategies_detail(score) -> None:
    """7 大师明细行(若 strategies 维度有 masters)。"""
    masters = getattr(score, "masters", {}) or {}
    if not masters:
        return
    year = getattr(score, "strategies_year", "?")
    st.markdown(f"##### 🧪 多大师评分明细 · year = {year}")
    rows = []
    for m, info in masters.items():
        sc_str = info["score"] if info.get("score") is not None else "—"
        tot = info.get("total") or "—"
        valid = info.get("valid", 0)
        pct = info.get("pct")
        pct_str = f"{pct:.0f}%" if pct is not None else "—"
        rows.append({
            "大师": m,
            "得分": f"{sc_str}/{tot}",
            "可跑": valid,
            "归一": pct_str,
            "评级": info.get("badge", "⚪"),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")



# ─── 第二波抽:dash-03 同行 + 状态 + S8 + 文件枚举 + 分位带图 ─────

# ─── dash-03: 同行评分缓存 + 大师矩阵渲染 ─────────────────────────────
@st.cache_data(ttl=600)
def peer_scores(self_ticker: str, mtime: float, max_n: int = 4) -> list:
    """返回 [self_score, *peer_scores]。失败 []。"""
    if pr is None or not self_ticker:
        return []
    try:
        peers = pr.peer_pool(self_ticker, db_path=DUCKDB_PATH, max_n=max_n)
        all_t = [self_ticker] + [t for t, _ in peers]
        # 优先读预计算 CompanyScore(每家 <5ms);未覆盖的降级 live。
        try:
            import analytics_store as _store
        except Exception:
            _store = None
        out = []
        for t in all_t:
            s = _store.company_score(t) if _store is not None else None
            if s is None:
                try:
                    s = sc.compute_dimensions(t, db_path=DUCKDB_PATH)
                except Exception:
                    s = None
            if s is not None:
                out.append(s)
        return out
    except Exception:
        return []


def render_master_matrix(self_ticker: str, peer_tickers: list[str], year: int | None = None) -> None:
    """4 大师 × N 公司矩阵。本公司高亮。"""
    if not self_ticker:
        st.info("缺 ticker,跳过大师矩阵")
        return
    tickers = [self_ticker] + [t for t in peer_tickers if t != self_ticker]
    matrix = None
    if year is None:
        try:
            import analytics_store as _store
            matrix = _store.master_matrix_from_store(tickers)
        except Exception:
            matrix = None
    if matrix is None:
        matrix = sc.master_matrix(tickers, year=year)
    if not matrix:
        st.info("multi_master 无可用数据")
        return
    masters = list(matrix[0]["masters"].keys())
    rows = []
    for row in matrix:
        line = {"公司": ("⭐ " if row["ticker"] == self_ticker else "  ") + row["name"]}
        for m in masters:
            info = row["masters"].get(m, {})
            sc_str = info.get("score") if info.get("score") is not None else "—"
            tot = info.get("total") or "—"
            valid = info.get("valid", 0)
            badge = info.get("badge", "⚪")
            line[m] = f"{badge} {sc_str}/{tot}({valid})"
        rows.append(line)
    df_m = pd.DataFrame(rows)

    def _color(label: str) -> str:
        if not isinstance(label, str):
            return ""
        for icon, color in [("🟢", "#1b8a3a"), ("🟡", "#f0ad4e"), ("🟠", "#e07b00"), ("🔴", "#d9534f")]:
            if label.startswith(icon):
                return f"background-color: {color}; color: white"
        return ""

    styler = df_m.style.map(_color, subset=masters).set_properties(
        subset=masters, **{"text-align": "center", "font-size": "11px"}
    )
    st.dataframe(styler, width="stretch", hide_index=True)
    _latest_period = latest_financial_period(_db_mtime()).get("label", "—")
    _annual_year = year or latest_annual_year(_db_mtime()) or (pd.Timestamp.now().year - 1)
    st.caption(
        f"格式:`评级 得分/总规则(可跑项)` · 完整年报评分 year = {_annual_year} · "
        f"最新财报 = {_latest_period} · ⭐ = 本公司"
    )


@st.cache_data(ttl=60)
def datasource_status(mtime: float) -> dict:
    if duckdb is None:
        return {"source": "csv", "reason": "duckdb 未安装", "rows": None}
    if mtime == 0.0:
        return {"source": "csv", "reason": "data/preson.duckdb 不存在", "rows": None}
    con = _duckdb_conn(mtime)
    if con is None:
        return {"source": "csv", "reason": "DuckDB 连接失败", "rows": None}
    try:
        rows = con.execute("SELECT COUNT(*) FROM valuation").fetchone()[0]
        size_mb = DUCKDB_PATH.stat().st_size / 1024 / 1024
        from datetime import datetime
        updated = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
        return {"source": "duckdb", "rows": rows, "size_mb": round(size_mb, 1), "updated": updated}
    except Exception as e:
        return {"source": "csv", "reason": f"DuckDB 查询失败: {e}", "rows": None}


@st.cache_data(ttl=30)
def mcp_status() -> list[dict]:
    if not SETTINGS_FILE.exists():
        return []
    try:
        cfg = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for name, spec in cfg.get("mcpServers", {}).items():
        args = spec.get("args", [])
        script = next((Path(a) for a in args if a.endswith(".py")), None)
        out.append({
            "name": name,
            "script_exists": script.exists() if script else False,
            "script": str(script) if script else "",
        })
    return out


@st.cache_data(ttl=2)
def read_inbox() -> str | None:
    if not INBOX_FILE.exists():
        return None
    try:
        text = INBOX_FILE.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None


def clear_inbox() -> None:
    if INBOX_FILE.exists():
        INBOX_FILE.unlink()


# ─── S8: validate 报告解析 ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def parse_validate_report(report_mtime: float) -> dict[str, list[str]]:
    """返回 {folder: [critical 行, ...]}。"""
    if not VALIDATE_REPORT.exists():
        return {}
    text = VALIDATE_REPORT.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("- **"):
            continue
        m = re.match(r"^- \*\*(\d{2}_[^/]+) / (\w+)\*\* \(score=(\d+)\): (.+)$", line)
        if m:
            folder, table, score, detail = m.groups()
            out.setdefault(folder, []).append(f"`{table}` · score={score} · {detail}")
    return out


def report_mtime() -> float:
    return VALIDATE_REPORT.stat().st_mtime if VALIDATE_REPORT.exists() else 0.0


# ─── 文件枚举 ──────────────────────────────────────────────────────────
def numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c != "date" and pd.api.types.is_numeric_dtype(df[c])]


@st.cache_data(ttl=300)
def list_decision_docs(company: str) -> list[Path]:
    base = COMPANIES_DIR / company / "05_投资决策"
    if not base.exists():
        return []
    return sorted(base.rglob("*.md"))


@st.cache_data(ttl=300)
def list_broker_docs(company: str) -> list[Path]:
    base = COMPANIES_DIR / company / "04_券商分析"
    if not base.exists():
        return []
    return sorted([p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".csv", ".pdf"}])


@st.cache_data(ttl=300)
def list_reports(company: str) -> list[Path]:
    base = COMPANIES_DIR / company / "02_公司财报"
    if not base.exists():
        return []
    return sorted(base.glob("*.pdf"), reverse=True)


def write_context(
    company: str,
    *,
    module: str | None = None,
    metric: str | None = None,
    window: str | None = None,
    compare_targets: list[str] | None = None,
    compare_metric: str | None = None,
) -> None:
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    m = re.match(r"^(\d{2})_(.+)$", company)
    code, name = (m.group(1), m.group(2)) if m else ("", company)
    lines = [
        "# Dashboard 当前上下文", "",
        f"- **公司**: {name}",
        f"- **目录编号**: {code}",
        f"- **完整目录**: `02_companies/{company}/`",
    ]
    if module: lines.append(f"- **当前模块**: {module}")
    if metric: lines.append(f"- **当前指标**: {metric}")
    if window: lines.append(f"- **时间窗**: {window}")
    if compare_targets: lines.append(f"- **对比组**: {', '.join(compare_targets)}")
    if compare_metric: lines.append(f"- **对比指标**: {compare_metric}")
    lines.append(f"- **更新时间**: {pd.Timestamp.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("> 由 .tools/dashboard/app.py 自动写入。Claude Code 启动时通过 CLAUDE.md hook 加载此文件。")
    lines.append("> 用户问 \"现在贵不贵 / 这家怎么样 / 这几家谁便宜\" 等省略主语的问句时,以本文件为锚点。")
    CONTEXT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def percentile_color(p: float | None) -> str:
    if p is None or pd.isna(p):
        return ""
    if p < 0.2: return "background-color: #1b8a3a; color: white"
    if p < 0.5: return "background-color: #5cb85c; color: white"
    if p <= 0.8: return "background-color: #f0ad4e; color: black"
    return "background-color: #d9534f; color: white"


def percentile_band_chart(df: pd.DataFrame, metric: str, title: str) -> go.Figure | None:
    triple = PERCENTILE_TRIPLES.get(metric)
    if not triple:
        return None
    quant_col, p80, p50, p20 = triple
    if not all(c in df.columns for c in (metric, p80, p50, p20)):
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df[p80], name="80% 分位", line=dict(color="#d9534f", dash="dot"), opacity=0.7))
    fig.add_trace(go.Scatter(x=df["date"], y=df[p50], name="50% 分位", line=dict(color="#999", dash="dash"), opacity=0.7))
    fig.add_trace(go.Scatter(x=df["date"], y=df[p20], name="20% 分位", line=dict(color="#1b8a3a", dash="dot"), opacity=0.7))
    fig.add_trace(go.Scatter(x=df["date"], y=df[metric], name=metric, line=dict(color="#0d6efd", width=2.2)))
    latest = df.dropna(subset=[metric]).iloc[-1] if not df.empty else None
    if latest is not None:
        latest_q = latest.get(quant_col)
        annot = f"{metric} = {latest[metric]:.2f}"
        if pd.notna(latest_q):
            annot += f"  ·  分位 {latest_q*100:.1f}%"
        fig.add_annotation(x=latest["date"], y=latest[metric], text=annot, showarrow=True, arrowhead=2,
                           ax=-40, ay=-30, bgcolor="rgba(255,255,255,0.85)")
    fig.update_layout(title=title, height=480, hovermode="x unified", legend=dict(orientation="h", y=-0.15))
    return fig


# ─── ETF 行业对标(独立 etf.duckdb)──────────────────────────────────

def _etf_db_mtime() -> float:
    return ETF_DB_PATH.stat().st_mtime if ETF_DB_PATH.exists() else 0.0


@st.cache_data(ttl=600)
def load_etf_peers(folder: str) -> list[dict]:
    """读 .config/peers_etf.csv,返回 folder 对应的 ETF 列表(按 rank 排序)。
    每项:{etf_code, etf_name, etf_type, rank}
    """
    if not PEERS_ETF_CSV.exists():
        return []
    try:
        df = pd.read_csv(PEERS_ETF_CSV, dtype={"etf_code": str, "company_ticker": str})
    except Exception:
        return []
    sub = df[df["folder"] == folder].sort_values("rank")
    return [
        {"etf_code": r["etf_code"], "etf_name": r["etf_name"],
         "etf_type": r["etf_type"], "rank": int(r["rank"])}
        for _, r in sub.iterrows()
    ]


@st.cache_data(ttl=300)
def load_etf_prices(etf_codes_csv: str, mtime: float) -> pd.DataFrame:
    """从 etf.duckdb 读多只 ETF 的日 K(date, etf_code, close)。
    etf_codes_csv: '512800,512820,515020' (cache_data 不接 list)
    """
    if not ETF_DB_PATH.exists() or not etf_codes_csv:
        return pd.DataFrame()
    import duckdb
    try:
        con = duckdb.connect(str(ETF_DB_PATH), read_only=True)
    except Exception:
        return pd.DataFrame()
    try:
        codes = [c.strip() for c in etf_codes_csv.split(",") if c.strip()]
        placeholders = ",".join(["?"] * len(codes))
        df = con.execute(
            f"SELECT etf_code, date, close, pct_change "
            f"FROM etf_prices WHERE etf_code IN ({placeholders}) ORDER BY date",
            codes,
        ).fetchdf()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


def render_etf_overlay(folder: str, ticker: str, price_window_days: int | None) -> None:
    """渲染"个股 vs 3 只行业 ETF"基准化叠加图。

    起点基准化为 100,看相对走势 — 跑赢 / 跑平 / 跑输。
    """
    peers = load_etf_peers(folder)
    if not peers:
        st.caption(f"📊 {folder} 暂无 ETF 对标配置(.config/peers_etf.csv)")
        return

    codes_csv = ",".join(p["etf_code"] for p in peers)
    name_map = {p["etf_code"]: f"{p['etf_name']} ({p['etf_code']})" for p in peers}
    etf_df = load_etf_prices(codes_csv, _etf_db_mtime())
    if etf_df.empty:
        st.warning(
            f"📊 ETF 库 {ETF_DB_PATH.name} 无数据;"
            f"运行 `.venv/bin/python .tools/db/fetch_etf.py` 抓取"
        )
        return

    stock = load_prices(ticker, DB_MTIME)
    if stock.empty:
        st.caption(f"📊 (个股 prices 表无 {ticker},仅显示 ETF 走势)")

    # 时间窗过滤
    if price_window_days is not None:
        cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=price_window_days)
        etf_df = etf_df[etf_df["date"] >= cutoff]
        if not stock.empty:
            stock = stock[stock["date"] >= cutoff]

    if etf_df.empty:
        st.caption("📊 (时间窗内无 ETF 数据)")
        return

    # 基准化(起点 = 100)
    parts = []
    if not stock.empty:
        s = stock.sort_values("date")[["date", "close"]].dropna()
        if not s.empty:
            base = s["close"].iloc[0]
            if base and base != 0:
                parts.append(s.assign(
                    series=f"📈 {ticker} (本公司)",
                    norm=s["close"] / base * 100.0,
                )[["date", "series", "norm"]])

    for code, g in etf_df.groupby("etf_code"):
        g = g.sort_values("date").dropna(subset=["close"])
        if g.empty:
            continue
        base = g["close"].iloc[0]
        if not base or base == 0:
            continue
        parts.append(g.assign(
            series=name_map.get(code, code),
            norm=g["close"] / base * 100.0,
        )[["date", "series", "norm"]])

    if not parts:
        st.caption("📊 (基准化后无可绘数据)")
        return

    merged = pd.concat(parts, ignore_index=True)
    fig = px.line(merged, x="date", y="norm", color="series",
                  title=f"📊 {folder} vs 行业 ETF · 起点基准化为 100")
    # 个股线加粗
    for tr in fig.data:
        if "本公司" in tr.name:
            tr.update(line=dict(width=3.0, color="#0d6efd"))
        else:
            tr.update(line=dict(width=1.6, dash="dot"))
    fig.update_layout(height=380, hovermode="x unified",
                      legend=dict(orientation="h", y=-0.18),
                      yaxis_title="基准 = 100")
    fig.add_hline(y=100, line_dash="dot", line_color="#999",
                  annotation_text="起点基准 100")
    st.plotly_chart(fig, width="stretch")

    # 相对收益小表
    latest = merged.sort_values("date").groupby("series").tail(1)[["series", "norm"]]
    latest = latest.rename(columns={"norm": "累计收益(基准 100)"})
    latest["相对涨幅"] = latest["累计收益(基准 100)"] - 100
    latest = latest.sort_values("相对涨幅", ascending=False)
    st.dataframe(
        latest.style.format({"累计收益(基准 100)": "{:.1f}", "相对涨幅": "{:+.1f}%"}),
        hide_index=True, width="stretch",
    )
