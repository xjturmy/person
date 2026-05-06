"""投资智能体 - Streamlit Dashboard

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
SCORE_DIR = ROOT / ".tools" / "score"
RULES_DIR = ROOT / ".tools" / "rules"
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
TOOLS_DIR = ROOT / ".tools"
for _p in (MCP_DIR, SCORE_DIR, DASHBOARD_DIR, TOOLS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import importlib

import score_card as sc  # 6 维评分(方向 B)

try:
    import peer_radar as pr  # dash-03 同行雷达
    import decision_timeline as dt  # dash-03 决策时间线
except Exception:
    pr = None
    dt = None

# 强制 reload 自写 helper:streamlit 老进程会缓存 sys.modules,
# 改动 score_card / peer_radar / decision_timeline 后浏览器只 Rerun 不重启 → AttributeError
for _mod in (sc, pr, dt):
    if _mod is not None:
        try:
            importlib.reload(_mod)
        except Exception:
            pass

try:
    from decisions import db as decisions_db
    from decisions import snapshot as decisions_snapshot
except Exception:
    decisions_db = None
    decisions_snapshot = None
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


# ─── 数据访问层已抽到 .tools/dashboard/dashboard_helpers.py ──────────
from dashboard_helpers import (  # noqa: E402
    _db_mtime, _duckdb_conn, _folder_to_ticker, list_companies,
    load_metric, load_prices, list_industries, load_industry_pe,
)

# ─── V4/V5/多大师/V8 helper 已抽到 .tools/dashboard/dashboard_helpers.py ──
from dashboard_helpers import (  # noqa: E402
    # 数据
    _mcp_data_source, mcp_percentile, mcp_freshness,
    _score_engine, piotroski_score, piotroski_detail,
    _freshness_icon,
    list_executable_masters, master_score,
    company_score, SCORE_DIM_ORDER,
    # 渲染
    render_radar, render_score_cards, overlay_price, render_strategies_detail,
)


# ─── 第二波抽:dash-03 + status + S8 + 文件枚举 → dashboard_helpers.py ─
from dashboard_helpers import (  # noqa: E402
    peer_scores, render_master_matrix,
    datasource_status, mcp_status, read_inbox, clear_inbox,
    parse_validate_report, report_mtime,
    numeric_cols, list_decision_docs, list_broker_docs, list_reports,
    write_context, percentile_color, percentile_band_chart,
)

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
st.set_page_config(page_title="投资智能体", page_icon="📊", layout="wide")
st.title("📊 投资智能体")

DB_MTIME = _db_mtime()
RPT_MTIME = report_mtime()

# dash-01:顶部全局市场温度计(所有 Tab 都可见)
try:
    import header_thermometer as _hth
    _macro_db = ROOT / "data" / "macro.duckdb"
    _macro_mtime = _macro_db.stat().st_mtime if _macro_db.exists() else 0.0
    _hth.render(_macro_db, _macro_mtime)
except Exception as _hth_exc:
    st.caption(f"🌡️ 市场温度计加载失败:{_hth_exc}")

# v2.1 布局:左侧 radio 导航 + 公司选择 · 状态/MCP/健康收入 ⚙️ 设置 expander
PAGE_MARKET   = "📊 市场周期"
PAGE_SCREENER = "🔍 公司筛选"
PAGE_COMPANY  = "🏢 单公司详情"
PAGE_LYNCH    = "🌱 林奇分析法"
PAGE_DC       = "💼 决策中心"
PAGE_CLAUDE   = "🤖 Claude 终端"
PAGES = [PAGE_MARKET, PAGE_SCREENER, PAGE_COMPANY, PAGE_LYNCH, PAGE_DC, PAGE_CLAUDE]

with st.sidebar:
    # M0 #1:字体 + 行距 CSS(sidebar 视觉减负)
    st.markdown(
        """
        <style>
          section[data-testid="stSidebar"] [data-testid="stRadio"] label p {
            font-size: 16px !important;
            line-height: 2.0 !important;
            font-weight: 500;
          }
          section[data-testid="stSidebar"] h3 {
            font-size: 18px !important;
            margin-top: 8px !important;
            margin-bottom: 8px !important;
          }
          section[data-testid="stSidebar"] [data-baseweb="select"] {
            font-size: 15px !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🧭 导航")
    page = st.radio("页面", PAGES, key="nav", label_visibility="collapsed")

    # M0 #4:选股 + 设置合并为一段(去掉 divider,改名"当前公司")
    st.markdown("### 🎯 当前公司")
    companies = list_companies(DB_MTIME)
    if not companies:
        st.error(f"未在 {COMPANIES_DIR} 找到公司目录")
        st.stop()
    selected = st.selectbox("公司", companies, key="company", label_visibility="collapsed")

    # M0 #6:收件箱并入设置(顶部独立段删除,有信时设置内徽章提示)
    inbox = read_inbox()

    with st.expander(
        f"⚙️ 设置" + (f" · 📨 {len([l for l in inbox.splitlines() if l.strip()])} 条新信" if inbox else ""),
        expanded=bool(inbox),
    ):
        # 1. 数据源状态(M0 #5:精简到 1 行)
        ds = datasource_status(DB_MTIME)
        if ds["source"] == "duckdb":
            st.caption(f"💾 DuckDB · {ds['rows']:,} 行 · {ds['updated']}")
        else:
            st.caption(f"📁 CSV 兜底 — {ds.get('reason', '')}")

        # 2. 收件箱(有信才展开,M0 #6)
        if inbox:
            with st.container(border=True):
                st.markdown(inbox)
            if st.button("✅ 已读 / 清空", key="clear_inbox", use_container_width=True):
                clear_inbox()
                read_inbox.clear()
                st.rerun()

        # 3. MCP / 缺口 二级折叠(日常不看,M0 #5)
        report = parse_validate_report(RPT_MTIME)
        crit = report.get(selected, [])
        gap_badge = f" ({len(crit)})" if crit else ""
        with st.expander(f"🔌 MCP / 🩺 缺口{gap_badge}", expanded=False):
            st.markdown("**🔌 MCP 工具**")
            servers = mcp_status()
            if not servers:
                st.caption("(settings.json 未配置 mcpServers)")
            else:
                for s in servers:
                    icon = "✅" if s["script_exists"] else "⚠️"
                    st.caption(f"{icon} `{s['name']}`" + ("" if s["script_exists"] else " · 脚本缺失"))
                st.caption("注册情况(实际调通需 Claude 会话挂载)")

            st.markdown(f"**🩺 数据缺口 — {selected}**")
            if crit:
                for line in crit:
                    st.warning(line, icon="⚠️")
            elif RPT_MTIME > 0:
                st.success("无 critical 缺口", icon="✅")
            else:
                st.caption("(尚未运行 validate)")

        # 4. 快捷入口(M0 #5)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔄 刷新数据", use_container_width=True, key="refresh_cache"):
                st.cache_data.clear()
                st.rerun()
        with col_b:
            if st.button("📂 打开目录", use_container_width=True, key="open_root"):
                subprocess.run(["open", str(ROOT)], check=False)

# v2.1:左侧 radio 导航代替 st.tabs() — 各 with tab_xxx: 已替换为 if page == ...:
# tab_xxx 变量保留为 st.container() 兼容引用(空容器,不会渲染内容到外面)
tab_market = tab_screener = tab_company = tab_dc = tab_decisions = tab_claude = st.container()
tab_home = tab_overview = tab_compare = st.container()

# ─── Tab 0 市场周期(dash-01 · L1 — "现在是好时机吗?")— 占位 ─────────
if page == PAGE_MARKET:
    try:
        from tabs.market import render as _render_market
        _render_market(companies, selected, DB_MTIME)
    except Exception as _exc:
        st.error(f"⚠️ 市场周期 Tab 加载失败:{_exc}")
        import traceback as _tb
        st.code(_tb.format_exc(), language="python")


# ─── Tab 2 公司筛选(dash-02 · L2 — "15 家里哪些值得看?")────────────────
if page == PAGE_SCREENER:
    try:
        from tabs.screener import render as _render_screener
        _render_screener(companies, DB_MTIME)
    except Exception as _exc:
        st.error(f"⚠️ 公司筛选 Tab 加载失败:{_exc}")
        import traceback as _tb
        st.code(_tb.format_exc(), language="python")


# ─── Tab 0 公司主页(方向 B:雷达 + 5 卡片)──────────────────────────────
@st.cache_data(ttl=300)
def _company_score(ticker: str, window: str, mtime: float) -> dict | None:
    if not ticker:
        return None
    try:
        return sc.compute_dimensions(ticker, pct_window=window).to_dict()
    except Exception:
        return None


@st.cache_data(ttl=600)
def _fscore_for(ticker: str, year: int, mtime: float) -> tuple[int | None, list[dict]]:
    """返回 (得分, [{id,name,passed,score}, ...])。"""
    if not ticker:
        return None, []
    try:
        from importlib.machinery import SourceFileLoader
        engine = SourceFileLoader("engine", str(SCORE_DIR / "engine.py")).load_module()
        rules_path = RULES_DIR / "piotroski.yaml"
        data = engine.load_duckdb_data(ticker)
        result = engine.run_score(rules_path, data, year)
        if result is None:
            return None, []
        details = [
            {"id": d.rule_id, "name": d.name,
             "passed": d.passed, "score": d.score}
            for d in result.details
        ]
        return int(result.total_score), details
    except Exception:
        return None, []


# ─── SWS 视觉语言已抽到 .tools/dashboard/sws_styles.py ──────────────────
from sws_styles import (  # noqa: E402
    SWS_DIM_KEYS, SWS_COLORS, SWS_ICONS,
    SWS_PRIMARY, SWS_PRIMARY_2, SWS_TEXT, SWS_MUTED, SWS_BORDER, SWS_BG_SOFT,
    _sws_score_pill, _radar_chart, _sws_dim_card_html, _SWS_CSS,
)



if page == PAGE_COMPANY:
    try:
        from tabs import company as _company_mod
        _company_mod.render(globals())
    except Exception as _e:
        st.error(f"公司详情加载失败:{_e}")
        import traceback as _tb
        st.caption(_tb.format_exc())

# ─── dash-04 决策中心(L0 三段式 Tab)──────────────────────────────────
if page == PAGE_DC:
    try:
        from tabs import decision_center as _dc_mod
        _dc_mod.render(
            companies=companies,
            selected=selected,
            db_mtime=DB_MTIME,
            decisions_db=decisions_db,
            decisions_snapshot=decisions_snapshot,
            folder_to_ticker_fn=_folder_to_ticker(DB_MTIME),
        )
    except Exception as _e:
        st.error(f"决策中心加载失败:{_e}")
        import traceback as _tb
        st.caption(_tb.format_exc())

# ─── M6 林奇分析法(成长投资五步框架)──────────────────────────────────
if page == PAGE_LYNCH:
    try:
        from tabs import lynch_analysis as _lynch_mod
        _lynch_mod.render(
            companies=companies,
            selected=selected,
            db_mtime=DB_MTIME,
            decisions_db=decisions_db,
            folder_to_ticker_fn=_folder_to_ticker(DB_MTIME),
        )
    except Exception as _e:
        st.error(f"林奇分析法加载失败:{_e}")
        import traceback as _tb
        st.caption(_tb.format_exc())

# ─── Tab 5 Claude 终端(M3 + S4)──────────────────────────────────────
if page == PAGE_CLAUDE:
    try:
        from tabs import claude as _claude_mod
        _claude_mod.render(globals())
    except Exception as _e:
        st.error(f"Claude 终端加载失败:{_e}")
        import traceback as _tb
        st.caption(_tb.format_exc())

# ─── dash-04 横切组件:右下浮窗(显示在所有 tab)──────────────────────
try:
    import floating_widget as _fab
    _fab.render()
except Exception as _e:
    st.sidebar.caption(f"(右下浮窗加载失败:{_e})")
