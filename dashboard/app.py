"""preson 投研驾驶舱 - Streamlit Dashboard

数据源:DuckDB 优先(`data/preson.duckdb`),失败回退 CSV。
缓存:mtime-aware,DuckDB 文件改了自动失效(配合周日 cron 增量)。

Run: cd /Users/gongyong/Desktop/Keyi/preson && .venv/bin/streamlit run .tools/dashboard/app.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from io import BytesIO
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
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))
COMPANIES_DIR = ROOT / "02_companies"
DUCKDB_PATH = ROOT / "data" / "preson.duckdb"
CONTEXT_FILE = ROOT / ".temp" / "current_context.md"
INBOX_FILE = ROOT / ".temp" / "dashboard_inbox.md"
VALIDATE_REPORT = ROOT / ".temp" / "validate_report.md"
SETTINGS_FILE = ROOT / ".claude" / "settings.json"
TTYD_LAUNCHER = ROOT / ".tools" / "dashboard" / "launch_terminal.sh"
TTYD_PID = ROOT / ".temp" / "ttyd.pid"

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


# ─── S4: ttyd 生命周期 ─────────────────────────────────────────────────
def ttyd_status() -> tuple[bool, int | None]:
    if not TTYD_PID.exists():
        return False, None
    try:
        pid = int(TTYD_PID.read_text().strip())
        import os, signal
        os.kill(pid, 0)
        return True, pid
    except Exception:
        return False, None


def ttyd_start_daemon() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["bash", str(TTYD_LAUNCHER), "--daemon"],
            capture_output=True, text=True, timeout=10, cwd=ROOT,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def ttyd_stop() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["bash", str(TTYD_LAUNCHER), "--stop"],
            capture_output=True, text=True, timeout=10, cwd=ROOT,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="preson 投研驾驶舱", page_icon="📊", layout="wide")
st.title("📊 preson 投研驾驶舱")
st.caption("MVP · DuckDB 直连(mtime 缓存)+ MCP 状态 + 双向通道")

DB_MTIME = _db_mtime()
RPT_MTIME = report_mtime()

with st.sidebar:
    st.header("🎯 选股")
    companies = list_companies(DB_MTIME)
    if not companies:
        st.error(f"未在 {COMPANIES_DIR} 找到公司目录")
        st.stop()
    selected = st.selectbox("公司", companies, key="company")
    st.caption("上下文 → `.temp/current_context.md`")
    st.divider()

    ds = datasource_status(DB_MTIME)
    if ds["source"] == "duckdb":
        st.success(f"💾 DuckDB · {ds['rows']:,} 行 · {ds['size_mb']} MB · 更新于 {ds['updated']}")
    else:
        st.warning(f"📁 CSV 兜底模式 — {ds.get('reason', '')}")

    st.markdown("**🔌 MCP 工具**")
    servers = mcp_status()
    if not servers:
        st.caption("(settings.json 未配置 mcpServers)")
    else:
        for s in servers:
            icon = "✅" if s["script_exists"] else "⚠️"
            st.caption(f"{icon} `{s['name']}`" + ("" if s["script_exists"] else " · 脚本缺失"))
        st.caption("注册情况(实际调通需 Claude 会话挂载)")
    st.divider()

    # S8: validate 缺口
    report = parse_validate_report(RPT_MTIME)
    crit = report.get(selected, [])
    if crit:
        st.markdown("**🩺 数据缺口**")
        for line in crit:
            st.warning(line, icon="⚠️")
    elif RPT_MTIME > 0:
        st.markdown("**🩺 数据健康**")
        st.success("当前公司无 critical 缺口", icon="✅")
    st.divider()

    # M4: 收件箱
    inbox = read_inbox()
    if inbox:
        st.markdown("### 📨 Claude 来信")
        with st.container(border=True):
            st.markdown(inbox)
        if st.button("✅ 已读 / 清空", key="clear_inbox", use_container_width=True):
            clear_inbox()
            read_inbox.clear()
            st.rerun()
    else:
        st.caption("📭 收件箱空 · Claude 写 `.temp/dashboard_inbox.md` 即可推送")
        if st.button("🔄 检查收件箱", key="poll_inbox", use_container_width=True):
            read_inbox.clear()
            st.rerun()

tab_overview, tab_company, tab_compare, tab_claude = st.tabs(
    ["🏠 首页全景", "🏢 公司详情", "⚖️ 横向对比", "🤖 Claude 终端"]
)

# ─── Tab 1 首页全景 ────────────────────────────────────────────────────
with tab_overview:
    st.subheader("15 家公司一屏概览(分位 <20% 绿、>80% 红)")
    pct_window = st.radio(
        "分位窗口", ["10y", "5y", "3y", "1y", "all"], index=0, horizontal=True, key="pct_window",
        help="经 MCP `valuation_percentile` 自算(DuckDB 全量数据,与理杏仁内置 10y 分位差 ~0.04pp);MCP 失败时回退 CSV 内置字段",
    )
    folder_to_ticker = _folder_to_ticker(DB_MTIME)
    mcp_alive = _mcp_data_source() is not None
    fallback_ct = 0
    rows = []
    for c in companies:
        v = load_metric(c, "估值", DB_MTIME)
        p = load_metric(c, "盈利", DB_MTIME)
        latest_v = v.iloc[-1] if not v.empty else None
        latest_p = p.iloc[-1] if not p.empty else None
        ticker = folder_to_ticker.get(c, "")

        pe_pct = mcp_percentile(ticker, "PE-TTM", pct_window, DB_MTIME) if mcp_alive else None
        pb_pct = mcp_percentile(ticker, "PB", pct_window, DB_MTIME) if mcp_alive else None
        pe_src = "M"
        pb_src = "M"
        if pe_pct is None and latest_v is not None and "PE-TTM_分位点" in latest_v:
            pe_pct = float(latest_v["PE-TTM_分位点"])
            pe_src = "C"; fallback_ct += 1
        if pb_pct is None and latest_v is not None and "PB_分位点" in latest_v:
            pb_pct = float(latest_v["PB_分位点"])
            pb_src = "C"; fallback_ct += 1

        rows.append({
            "公司": c,
            "PE-TTM": float(latest_v["PE-TTM"]) if latest_v is not None and "PE-TTM" in latest_v else None,
            "PE 分位": pe_pct,
            "PE 源": pe_src if pe_pct is not None else "—",
            "PB": float(latest_v["PB"]) if latest_v is not None and "PB" in latest_v else None,
            "PB 分位": pb_pct,
            "PB 源": pb_src if pb_pct is not None else "—",
            "股息率": float(latest_v["股息率"]) if latest_v is not None and "股息率" in latest_v else None,
            "ROE": float(latest_p["净资产收益率(ROE)"]) if latest_p is not None and "净资产收益率(ROE)" in latest_p else None,
            "毛利率": float(latest_p["毛利率(GM)"]) if latest_p is not None and "毛利率(GM)" in latest_p else None,
        })
    df_panel = pd.DataFrame(rows)
    if mcp_alive:
        st.caption(f"🔌 分位口径:MCP `valuation_percentile` (window={pct_window}) · 回退 CSV 次数:{fallback_ct}")
    else:
        st.caption("⚠️ MCP data_source 加载失败,全部用 CSV 内置 10y 分位")

    styler = (
        df_panel.style
        .map(percentile_color, subset=["PE 分位", "PB 分位"])
        .format({
            "PE-TTM": "{:.1f}", "PE 分位": "{:.1%}",
            "PB": "{:.2f}", "PB 分位": "{:.1%}",
            "股息率": "{:.2%}", "ROE": "{:.2%}", "毛利率": "{:.2%}",
        }, na_rep="—")
        .set_properties(subset=["PE 源", "PB 源"], **{"text-align": "center", "font-size": "11px"})
    )
    st.dataframe(styler, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ 下载全景表 CSV", df_panel.to_csv(index=False).encode("utf-8-sig"),
        file_name="preson_overview.csv", mime="text/csv", key="dl_overview",
    )

    cheap = df_panel.dropna(subset=["PE 分位"]).nsmallest(3, "PE 分位")
    expensive = df_panel.dropna(subset=["PE 分位"]).nlargest(3, "PE 分位")
    high_roe = df_panel.dropna(subset=["ROE"]).nlargest(3, "ROE")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**🟢 PE 分位最低 Top3(便宜)**")
    c1.dataframe(cheap[["公司", "PE-TTM", "PE 分位"]].assign(**{"PE 分位": cheap["PE 分位"].map("{:.1%}".format)}), hide_index=True, use_container_width=True)
    c2.markdown("**🔴 PE 分位最高 Top3(贵)**")
    c2.dataframe(expensive[["公司", "PE-TTM", "PE 分位"]].assign(**{"PE 分位": expensive["PE 分位"].map("{:.1%}".format)}), hide_index=True, use_container_width=True)
    c3.markdown("**⭐ ROE 最高 Top3**")
    c3.dataframe(high_roe[["公司", "ROE"]].assign(ROE=high_roe["ROE"].map("{:.2%}".format)), hide_index=True, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PE 分位排行**")
        st.bar_chart(df_panel.set_index("公司")["PE 分位"].dropna().sort_values())
    with col2:
        st.markdown("**ROE 排行**")
        st.bar_chart(df_panel.set_index("公司")["ROE"].dropna().sort_values(ascending=False))

# ─── Tab 2 公司详情 ────────────────────────────────────────────────────
with tab_company:
    st.subheader(f"🏢 {selected}")
    main_col, side_col = st.columns([3, 1])

    with main_col:
        module = st.radio("模块", list(MODULES.keys()), horizontal=True, key="mod")
        df = load_metric(selected, module, DB_MTIME)
        if df.empty:
            st.warning(f"{selected} / {module} 数据缺失")
            picked, window_label = [], None
            df_view = pd.DataFrame()
        else:
            cols = numeric_cols(df)
            window_label = st.select_slider(
                "时间窗", options=["近 1 年", "近 3 年", "近 5 年", "全部"], value="近 5 年", key="win"
            )
            window_days = {"近 1 年": 365, "近 3 年": 365 * 3, "近 5 年": 365 * 5, "全部": None}[window_label]
            df_view = df if window_days is None else df[df["date"] >= df["date"].max() - pd.Timedelta(days=window_days)]

            if module == "估值":
                pct_options = [m for m in PERCENTILE_TRIPLES if m in cols]
                pct_metric = st.selectbox("分位带指标", pct_options, key="pct_metric") if pct_options else None
                if pct_metric:
                    fig = percentile_band_chart(df_view, pct_metric, f"{selected} · {pct_metric} 分位带")
                    if fig is not None:
                        st.plotly_chart(fig, use_container_width=True)
                picked = [pct_metric] if pct_metric else []
            else:
                default = [c for c in ("净资产收益率(ROE)", "毛利率(GM)", "营业收入", "自由现金流量", "资产负债率") if c in cols][:2] or cols[:2]
                picked = st.multiselect("指标", cols, default=default)
                if picked:
                    fig = px.line(df_view, x="date", y=picked, title=f"{selected} · {module}")
                    fig.update_layout(height=420, hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)

            if not df_view.empty:
                st.download_button(
                    f"⬇️ 下载 {selected}/{module} CSV",
                    df_view.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{selected}_{module}.csv", mime="text/csv", key="dl_company_metric",
                )
            with st.expander("原始数据(末 50 行)"):
                st.dataframe(df_view.tail(50), use_container_width=True, hide_index=True)

        # ─── S7: 股价 + 行业 PE ─────────────────────────────────────
        st.markdown("---")
        st.markdown("##### 📈 股价(prices)")
        ticker = _folder_to_ticker(DB_MTIME).get(selected)
        if not ticker:
            st.caption("(未找到 ticker 映射)")
        else:
            prices = load_prices(ticker, DB_MTIME)
            if prices.empty:
                st.caption("(prices 表无此 ticker · 可能是港股或未抓取)")
            else:
                price_window = st.select_slider(
                    "股价时间窗", options=["近 1 月", "近 3 月", "近 1 年", "近 3 年", "全部"],
                    value="近 1 年", key="price_win",
                )
                wd = {"近 1 月": 30, "近 3 月": 90, "近 1 年": 365, "近 3 年": 1095, "全部": None}[price_window]
                pv = prices if wd is None else prices[prices["date"] >= prices["date"].max() - pd.Timedelta(days=wd)]
                kfig = go.Figure(data=[go.Candlestick(
                    x=pv["date"], open=pv["open"], high=pv["high"], low=pv["low"], close=pv["close"], name=ticker,
                )])
                kfig.update_layout(
                    height=380, hovermode="x unified", xaxis_rangeslider_visible=False,
                    title=f"{selected} ({ticker}) · {price_window} K 线",
                )
                st.plotly_chart(kfig, use_container_width=True)

        st.markdown("##### 🏭 行业 PE 中位数(industry_pe)")
        industries = list_industries(DB_MTIME)
        if industries:
            options = [f"{c} · {n}" for c, n in industries]
            opt_idx = st.selectbox("行业", range(len(options)), format_func=lambda i: options[i], key="ind_idx")
            ind_code, ind_name = industries[opt_idx]
            ind_df = load_industry_pe(ind_code, DB_MTIME)
            if ind_df.empty:
                st.caption("(无数据)")
            else:
                ifig = px.line(ind_df, x="date", y=["pe_median", "pe_weighted", "pe_arith"],
                               title=f"{ind_name} · PE 中位/加权/算术")
                ifig.update_layout(height=320, hovermode="x unified")
                st.plotly_chart(ifig, use_container_width=True)

    with side_col:
        st.markdown("### 📝 投资决策")
        decisions = list_decision_docs(selected)
        if not decisions:
            st.caption("(暂无决策文档)")
        else:
            for p in decisions:
                rel = p.relative_to(COMPANIES_DIR / selected)
                with st.expander(str(rel), expanded=False):
                    try:
                        body = p.read_text(encoding="utf-8")
                        st.markdown(body[:4000] + ("\n\n... (截断,完整见源文件)" if len(body) > 4000 else ""))
                    except Exception as e:
                        st.error(f"读取失败:{e}")

        st.markdown("### 🏦 券商分析")
        broker = list_broker_docs(selected)
        if not broker:
            st.caption("(暂无)")
        else:
            for p in broker[:8]:
                st.caption(f"`{p.relative_to(COMPANIES_DIR / selected)}`")

        st.markdown("### 📄 财报")
        reports = list_reports(selected)
        if not reports:
            st.caption("(暂无 PDF)")
        else:
            st.caption(f"共 {len(reports)} 份 · 最新:")
            for p in reports[:5]:
                st.caption(f"• {p.name}")

    write_context(
        selected,
        module=module if not df.empty else None,
        metric=", ".join([p for p in picked if p]) if picked else None,
        window=window_label,
    )

# ─── Tab 3 横向对比(S5 基准化 + S6 导出)──────────────────────────────
with tab_compare:
    st.subheader("⚖️ 横向对比")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        cmp_module = st.selectbox("模块", list(MODULES.keys()), key="cmp_mod")
        sample_df = next(
            (load_metric(c, cmp_module, DB_MTIME) for c in companies if not load_metric(c, cmp_module, DB_MTIME).empty),
            pd.DataFrame(),
        )
        cmp_metrics = numeric_cols(sample_df)
        if not cmp_metrics:
            st.warning("无可对比指标")
            st.stop()
        cmp_metric = st.selectbox("指标", cmp_metrics, key="cmp_metric")
        targets = st.multiselect("公司", companies, default=companies[: min(5, len(companies))])
        normalize = st.toggle("基准化(=100 起点)", value=False, help="把每家公司的首个有效值归一到 100,便于跨量级对比")
    with col_b:
        if targets:
            frames = []
            for c in targets:
                d = load_metric(c, cmp_module, DB_MTIME)
                if not d.empty and cmp_metric in d.columns:
                    frames.append(d[["date", cmp_metric]].assign(公司=c))
            if frames:
                merged = pd.concat(frames, ignore_index=True)
                if normalize:
                    parts = []
                    for c, g in merged.groupby("公司"):
                        g = g.sort_values("date").dropna(subset=[cmp_metric])
                        if g.empty:
                            continue
                        first = g[cmp_metric].iloc[0]
                        if first and first != 0:
                            g = g.assign(**{cmp_metric: g[cmp_metric] / first * 100})
                        parts.append(g)
                    merged = pd.concat(parts, ignore_index=True) if parts else merged
                    y_label = f"{cmp_metric}(基准 100)"
                else:
                    y_label = cmp_metric
                fig = px.line(merged, x="date", y=cmp_metric, color="公司",
                              title=f"{cmp_module} · {y_label}")
                fig.update_layout(height=480, hovermode="x unified")
                if normalize:
                    fig.add_hline(y=100, line_dash="dot", line_color="#999", annotation_text="基准 100")
                st.plotly_chart(fig, use_container_width=True)

                latest = (
                    merged.sort_values("date").groupby("公司", as_index=False)
                    .tail(1)[["公司", "date", cmp_metric]].sort_values(cmp_metric, ascending=False)
                )
                st.dataframe(latest, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇️ 下载对比数据 CSV",
                    merged.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"compare_{cmp_module}_{cmp_metric}.csv",
                    mime="text/csv", key="dl_compare",
                )

    write_context(selected, compare_targets=targets, compare_metric=f"{cmp_module}/{cmp_metric}")

# ─── Tab 4 Claude 终端(M3 + S4)──────────────────────────────────────
with tab_claude:
    st.subheader("🤖 嵌入式 Claude Code 终端")
    running, pid = ttyd_status()
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if running:
            st.success(f"🟢 ttyd 运行中 (PID {pid}) · http://127.0.0.1:7681")
        else:
            st.warning("🔴 ttyd 未运行 · 点右侧按钮启动")
    with c2:
        if st.button("▶️ 启动 daemon", disabled=running, use_container_width=True):
            ok, out = ttyd_start_daemon()
            (st.success if ok else st.error)(out or ("已启动" if ok else "启动失败"))
            st.rerun()
    with c3:
        if st.button("⏹ 停止", disabled=not running, use_container_width=True):
            ok, out = ttyd_stop()
            (st.success if ok else st.error)(out or ("已停止" if ok else "停止失败"))
            st.rerun()

    ttyd_port = st.number_input("ttyd 端口", min_value=1024, max_value=65535, value=7681, step=1)
    ttyd_url = f"http://127.0.0.1:{ttyd_port}"
    st.link_button("🔗 在新窗口打开", ttyd_url)
    st.components.v1.iframe(ttyd_url, height=560, scrolling=True)
    st.markdown("---")
    st.markdown("##### 🔁 双向通道协议")
    st.markdown(
        f"- **Dashboard → Claude**:`.temp/current_context.md`(当前 → **{selected}**,Claude 启动自动加载)\n"
        f"- **Claude → Dashboard**:写入 `.temp/dashboard_inbox.md` → Dashboard 侧栏「📨 Claude 来信」展示"
    )
    with st.expander("Claude 端发送示例"):
        st.code(
            'echo "**茅台 PE 已到 5 年低位 10.7%**,可考虑分批建仓。" > .temp/dashboard_inbox.md',
            language="bash",
        )
