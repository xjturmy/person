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

import ui.score_card as sc  # 6 维评分(方向 B)

try:
    import peers.radar as pr  # dash-03 同行雷达
    import peers.timeline as dt  # dash-03 决策时间线
except Exception:
    pr = None
    dt = None

try:
    import industry.compare_view as icv  # B2/B3 行业横评
except Exception:
    icv = None

# 强制 reload 自写 helper:streamlit 老进程会缓存 sys.modules,
# 改动 score_card / peer_radar / decision_timeline 后浏览器只 Rerun 不重启 → AttributeError
for _mod in (sc, pr, dt, icv):
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

# ─── 全局搜索:候选 ⑩ v2.4 step-B ────────────────────────────────────
from components import search_bar as company_search  # noqa: E402
from ui.dataframe_locale import inject_zh_column_menu  # noqa: E402

COMPANIES_CSV = ROOT / ".config" / "companies.csv"


@st.cache_data(ttl=300)
def _company_search_index(csv_mtime: float):
    if not COMPANIES_CSV.exists():
        return []
    return company_search.load_index(COMPANIES_CSV)

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

inject_zh_column_menu()

DB_MTIME = _db_mtime()
RPT_MTIME = report_mtime()

# v2.7 简化导航:11 → 5 顶级页面
# - 市场&行业 = 市场周期 + 行业分析 (2合1, sub-tab)
# - 公司研究  = 单公司详情 + 林奇 + 格雷厄姆 + 芒格 (4合1, sub-tab),公司只选一次
# - 选股 / 黄金 / 决策中心 保留独立
# - 删 Claude 终端(ttyd 早转方案 B,VS Code 旁挂)
PAGE_MARKET_HUB = "🌡️ 市场 & 行业"
PAGE_SCREENER   = "🔍 选股"
PAGE_COMPANY    = "🏢 公司研究"
PAGE_GOLD       = "🥇 黄金"
PAGE_DC         = "💼 决策中心"
PAGES = [PAGE_MARKET_HUB, PAGE_SCREENER, PAGE_COMPANY, PAGE_GOLD, PAGE_DC]

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
          section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
            border-left: 3px solid #1f77b4;
            padding-left: 8px;
            background: rgba(31,119,180,0.06);
            border-radius: 4px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("**🧭 导航**")
    page = st.radio("页面", PAGES, key="nav", label_visibility="collapsed")

    # 版本真源:读根目录 VERSION 文件(统一为 preson 1.0)
    try:
        _ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        _ver = "?"
    st.caption(f"preson v{_ver}")

    # M0 #4:选股 + 设置合并为一段(去掉 divider,改名"当前公司")
    st.markdown("### 🎯 当前公司")
    companies = list_companies(DB_MTIME)
    if not companies:
        st.error(f"未在 {COMPANIES_DIR} 找到公司目录")
        st.stop()

    # 候选 ⑩(v2.4 step-B):全局搜索栏 — 代码/中文名/拼音首字母/行业关键词
    csv_mtime = COMPANIES_CSV.stat().st_mtime if COMPANIES_CSV.exists() else 0.0
    search_index = _company_search_index(csv_mtime)
    query = st.text_input(
        "🔍 搜索",
        placeholder="代码 / 名称 / 拼音 / 行业,如 gzmt · 茅台 · 白酒",
        key="company_search_query",
        label_visibility="collapsed",
    )
    show_all_label = "── 📋 显示全部 ──"
    if query and search_index:
        matched_folders = company_search.search_folders(query, search_index, limit=20)
        if matched_folders:
            options = matched_folders + [show_all_label]
            st.caption(f"🎯 命中 {len(matched_folders)} 家")
        else:
            options = list(companies)
            st.caption("⚠️ 无匹配 — 显示全部")
    else:
        options = list(companies)

    # selectbox options 变化时,清掉旧 session_state 避免值不在列表内的报错
    options_signature = tuple(options)
    if st.session_state.get("_company_options_sig") != options_signature:
        st.session_state["_company_options_sig"] = options_signature
        if "company" in st.session_state and st.session_state["company"] not in options:
            del st.session_state["company"]

    selected = st.selectbox(
        "公司",
        options,
        key="company",
        label_visibility="collapsed",
    )
    if selected == show_all_label:
        # 用户点"显示全部":清搜索词,下次 rerun 走全量列表
        st.session_state["company_search_query"] = ""
        st.rerun()

    # 候选 ⑩ 修复:sidebar selected 变化时,同步覆盖各 Tab 内部的公司 selectbox。
    # streamlit selectbox 一旦 key 在 session_state,index 参数失效 — 不同步则
    # sidebar 切公司后林奇/格雷厄姆/芒格/决策中心仍显示旧公司。
    #
    # 注意:这里用 **无条件写入**(而非"仅 key 存在时写入")。
    # 因为林奇等 sub-tab 在未激活时并不渲染 selectbox,key 不会被预先注册;
    # 若仅条件写入,首次切公司时 key 不存在→不写入→sub-tab 激活后又用错误的 index。
    # 直接 setdefault 写入,sub-tab 内 selectbox 读到的就是 sidebar 当前公司。
    _SUB_COMPANY_KEYS = ("lynch_company", "graham_company", "munger_company", "dc_company")
    if st.session_state.get("_last_sidebar_company") != selected:
        st.session_state["_last_sidebar_company"] = selected
        for _k in _SUB_COMPANY_KEYS:
            st.session_state[_k] = selected

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
            if st.button("✅ 已读 / 清空", key="clear_inbox", width="stretch"):
                clear_inbox()
                read_inbox.clear()
                st.rerun()

        # 快捷入口(v2.7 简化:MCP/缺口移除 — 日常不看,需要时跑 validate 脚本即可)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔄 刷新数据", width="stretch", key="refresh_cache",
                         help="重跑分析预计算(analytics.duckdb)+ 清缓存。约 20-30s。"):
                with st.spinner("重算预计算(评分/分类/价格区间)…"):
                    try:
                        subprocess.run(
                            [sys.executable, str(TOOLS_DIR / "analytics" / "precompute.py")],
                            check=False, timeout=300, cwd=ROOT,
                        )
                    except Exception as _pc_e:
                        st.warning(f"预计算刷新失败(降级 live):{_pc_e}")
                st.cache_data.clear()
                st.rerun()
        with col_b:
            if st.button("📂 打开目录", width="stretch", key="open_root"):
                subprocess.run(["open", str(ROOT)], check=False)

# dash-01:顶部全局市场温度计(仅「市场 & 行业」页展示)
if page == PAGE_MARKET_HUB:
    st.markdown(
        """
        <style>
          section.main div[data-testid="stRadio"] > div > label {
            padding: 6px 14px;
            margin-right: 4px;
            border-radius: 6px;
            border: 1px solid #e6e6e6;
            background: #fafafa;
            cursor: pointer;
            transition: all 0.15s ease;
          }
          section.main div[data-testid="stRadio"] label:has(input:checked) {
            background: #1f77b4 !important;
            border-color: #1f77b4 !important;
          }
          section.main div[data-testid="stRadio"] label:has(input:checked) p {
            color: white !important;
            font-weight: 600 !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    try:
        import ui.thermometer as _hth
        _macro_db = ROOT / "data" / "macro.duckdb"
        _macro_mtime = _macro_db.stat().st_mtime if _macro_db.exists() else 0.0
        _hth.render(_macro_db, _macro_mtime)
    except Exception as _hth_exc:
        st.caption(f"🌡️ 市场温度计加载失败:{_hth_exc}")

# v2.1:左侧 radio 导航代替 st.tabs() — 各 with tab_xxx: 已替换为 if page == ...:
# tab_xxx 变量保留为 st.container() 兼容引用(空容器,不会渲染内容到外面)
tab_market = tab_screener = tab_company = tab_dc = tab_decisions = tab_claude = st.container()
tab_home = tab_overview = tab_compare = st.container()

# ─── 🌡️ 市场 & 行业(v2.9 P0b:4 合 1 — 市场研判 / 行业分析 / 行业预选 / 行业确定)──
if page == PAGE_MARKET_HUB:
    from navigation import (
        MARKET_HUB_SUB_TAB_KEY as _MARKET_SUB_TAB_KEY,
        SUB_MARKET_JUDGE as _SUB_MARKET_JUDGE,
        SUB_INDUSTRY_ANALYSIS as _SUB_INDUSTRY_ANALYSIS,
        SUB_INDUSTRY_PRESELECT as _SUB_INDUSTRY_PRESELECT,
        SUB_INDUSTRY_CONFIRM as _SUB_INDUSTRY_CONFIRM,
    )

    _MARKET_SUB_IDS = (
        _SUB_MARKET_JUDGE,
        _SUB_INDUSTRY_ANALYSIS,
        _SUB_INDUSTRY_PRESELECT,
        _SUB_INDUSTRY_CONFIRM,
    )
    _MARKET_SUB_LABELS = {
        _SUB_MARKET_JUDGE: f"📊 {_SUB_MARKET_JUDGE}",
        _SUB_INDUSTRY_ANALYSIS: f"🏭 {_SUB_INDUSTRY_ANALYSIS}",
        _SUB_INDUSTRY_PRESELECT: f"🎯 {_SUB_INDUSTRY_PRESELECT}",
        _SUB_INDUSTRY_CONFIRM: f"✅ {_SUB_INDUSTRY_CONFIRM}",
    }

    try:
        from navigation import consume_intent as _consume_intent
        _intent = _consume_intent()
        _intent_sub = (_intent or {}).get("sub_tab")
        if _intent_sub in _MARKET_SUB_IDS:
            st.session_state[_MARKET_SUB_TAB_KEY] = _intent_sub
    except Exception:
        pass

    if _MARKET_SUB_TAB_KEY not in st.session_state:
        st.session_state[_MARKET_SUB_TAB_KEY] = _SUB_MARKET_JUDGE

    # st.tabs 在 widget rerun 后会回到第一格;radio + session key 可保持当前子页
    st.markdown("<div style='height:1px;background:#eee;margin:8px 0 12px;'></div>", unsafe_allow_html=True)
    active_sub = st.radio(
        "市场子页",
        options=_MARKET_SUB_IDS,
        format_func=lambda s: _MARKET_SUB_LABELS[s],
        horizontal=True,
        key=_MARKET_SUB_TAB_KEY,
        label_visibility="collapsed",
    )

    if active_sub == _SUB_MARKET_JUDGE:
        try:
            from tabs.market import render as _render_market
            _render_market(companies, selected, DB_MTIME)
        except Exception as _exc:
            st.error(f"⚠️ 市场研判加载失败:{_exc}")
            import traceback as _tb
            st.code(_tb.format_exc(), language="python")
    elif active_sub == _SUB_INDUSTRY_ANALYSIS:
        try:
            from tabs.industry import analysis as _industry_analysis
            _industry_analysis.render()
        except Exception as _exc:
            st.error(f"⚠️ 行业分析加载失败:{_exc}")
            import traceback as _tb
            st.code(_tb.format_exc(), language="python")
    elif active_sub == _SUB_INDUSTRY_PRESELECT:
        try:
            from tabs.industry import preselect as _industry_preselect
            _industry_preselect.render()
        except Exception as _exc:
            st.error(f"⚠️ 行业预选加载失败:{_exc}")
            import traceback as _tb
            st.code(_tb.format_exc(), language="python")
    elif active_sub == _SUB_INDUSTRY_CONFIRM:
        try:
            from tabs.industry import confirm as _industry_confirm
            _industry_confirm.render()
        except Exception as _exc:
            st.error(f"⚠️ 行业确定加载失败:{_exc}")
            import traceback as _tb
            st.code(_tb.format_exc(), language="python")


# ─── 🔍 选股(v2.9:4 个子 Tab — 初步筛选 / 林奇选股 / 格雷厄姆选股 / 选股确定)─
if page == PAGE_SCREENER:
    try:
        from tabs.screener import render as _render_screener
        _render_screener(companies, DB_MTIME)
    except Exception as _exc:
        st.error(f"⚠️ 选股 Tab 加载失败:{_exc}")
        import traceback as _tb
        st.code(_tb.format_exc(), language="python")


# ─── Tab 0 公司主页(方向 B:雷达 + 5 卡片)──────────────────────────────
@st.cache_data(ttl=300)
def _company_score(ticker: str, window: str, mtime: float) -> dict | None:
    if not ticker:
        return None
    # 默认 10y 窗口走预计算 bundle(<5ms);其它窗口或未覆盖降级 live。
    if window == "10y":
        try:
            import analytics_store as _store
            pre = _store.company_score(ticker)
            if pre is not None:
                return pre.to_dict()
        except Exception:
            pass
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
from ui.sws_styles import (  # noqa: E402
    SWS_DIM_KEYS, SWS_COLORS, SWS_ICONS,
    SWS_PRIMARY, SWS_PRIMARY_2, SWS_TEXT, SWS_MUTED, SWS_BORDER, SWS_BG_SOFT,
    _sws_score_pill, _radar_chart, _sws_dim_card_html, _SWS_CSS,
)



# ─── 🏢 公司研究(v2.7:4 合 1 — 概览 / 林奇 / 格雷厄姆 / 芒格,公司只选一次)─
if page == PAGE_COMPANY:
    sub_overview, sub_lynch, sub_graham, sub_munger = st.tabs(
        ["📋 概览", "🌱 林奇", "💎 格雷厄姆", "🧠 芒格"]
    )
    _f2t = _folder_to_ticker(DB_MTIME)
    with sub_overview:
        try:
            from tabs import company as _company_mod
            _company_mod.render(globals())
        except Exception as _e:
            st.error(f"概览加载失败:{_e}")
            import traceback as _tb
            st.caption(_tb.format_exc())
    with sub_lynch:
        try:
            from tabs import lynch_analysis as _lynch_mod
            _lynch_mod.render(
                companies=companies, selected=selected, db_mtime=DB_MTIME,
                decisions_db=decisions_db, folder_to_ticker_fn=_f2t,
            )
        except Exception as _e:
            st.error(f"林奇加载失败:{_e}")
            import traceback as _tb
            st.caption(_tb.format_exc())
    with sub_graham:
        try:
            from tabs import graham_analysis as _graham_mod
            _graham_mod.render(
                companies=companies, selected=selected, db_mtime=DB_MTIME,
                decisions_db=decisions_db, folder_to_ticker_fn=_f2t,
            )
        except Exception as _e:
            st.error(f"格雷厄姆加载失败:{_e}")
            import traceback as _tb
            st.caption(_tb.format_exc())
    with sub_munger:
        try:
            from tabs import munger_analysis as _munger_mod
            _munger_mod.render(
                companies=companies, selected=selected, db_mtime=DB_MTIME,
                decisions_db=decisions_db, folder_to_ticker_fn=_f2t,
            )
        except Exception as _e:
            st.error(f"芒格加载失败:{_e}")
            import traceback as _tb
            st.caption(_tb.format_exc())


# ─── 💼 决策中心(4 个子 Tab)──────────────────────────────────────
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


# ─── 🥇 黄金分析法(三身份决策框架)──────────────────────────────────
if page == PAGE_GOLD:
    try:
        from tabs import gold_analysis as _gold_mod
        _gold_mod.render(
            companies=companies,
            selected=selected,
            db_mtime=DB_MTIME,
            decisions_db=decisions_db,
            folder_to_ticker_fn=_folder_to_ticker(DB_MTIME),
        )
    except Exception as _e:
        st.error(f"黄金分析法加载失败:{_e}")
        import traceback as _tb
        st.caption(_tb.format_exc())

# v2.7: Claude 终端 Tab + 右下浮窗已移除(终端转 VS Code 旁挂;浮窗低频)
