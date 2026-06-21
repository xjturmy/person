"""市场 Tab 共享 helpers:路径常量 / 理杏仁风格样式 / DuckDB 加载器 / 评级工具。"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"           # 主库:industry_pe / 价格 / 财务
MACRO_DB = ROOT / "data" / "macro.duckdb"           # dash-01:5 项宏观独立库
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
PORTFOLIO_DIR = ROOT / ".tools" / "portfolio"
KONDRATIEFF_YAML = DASHBOARD_DIR / "data" / "kondratieff.yaml"
for _p in (DASHBOARD_DIR, PORTFOLIO_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ─── 理杏仁风格通用样式(全 Tab 共享) ───
# 详见 memory/reference_lixinger_chart_style.md
LIXINGER_FONT = ('"PingFang SC","Helvetica Neue","Microsoft YaHei",'
                 '"Hiragino Sans GB","Noto Sans CJK SC",sans-serif')
LIXINGER_LINE_COLOR = "#1f4e9c"     # 深沉金融蓝主线
# 饱和色 → 浅色实心(opacity=1)映射,header_thermometer.bands 用得到
# 比第一版更浅一档(更接近白底,数据折线和文字对比度更好)
LIGHT_BAND_FILL = {
    "#d9534f": "#fef5f4",   # 红 → 极浅红
    "#fd7e14": "#fff7f0",   # 橙 → 极浅橙
    "#f0ad4e": "#fffdf2",   # 黄 → 极浅黄
    "#5cb85c": "#f2fcf6",   # 浅绿 → 极浅绿
    "#1b8a3a": "#e6faee",   # 深绿 → 浅绿
}
# 对应深色文字(色带右侧标签用)
LIGHT_BAND_TEXT = {
    "#d9534f": "#c0392b", "#fd7e14": "#d35400", "#f0ad4e": "#b58a00",
    "#5cb85c": "#27ae60", "#1b8a3a": "#1e8449",
}


def _apply_lixinger_layout(fig: go.Figure, *, height: int = 340,
                           margin_t: int = 8, margin_b: int = 30,
                           margin_l: int = 55, margin_r: int = 20,
                           y_title: str = "", y_range=None,
                           hovermode: str = "x unified") -> go.Figure:
    """套用理杏仁风格 layout:白底 / 关 vertical grid / 中文字体栈 / 隐藏 spine."""
    yaxis_cfg = dict(
        showgrid=True, gridcolor="#f0f0f0", gridwidth=1,
        zeroline=False, showline=False, ticks="",
        tickfont=dict(size=12, color="#333", family=LIXINGER_FONT),
    )
    if y_title:
        yaxis_cfg["title"] = dict(
            text=y_title,
            font=dict(size=13, color="#333", family=LIXINGER_FONT),
            standoff=6,
        )
    if y_range is not None:
        yaxis_cfg["range"] = y_range
    fig.update_layout(
        height=height,
        margin=dict(t=margin_t, b=margin_b, l=margin_l, r=margin_r),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=yaxis_cfg,
        xaxis=dict(
            title="", showgrid=False, zeroline=False, showline=False,
            ticks="outside", tickcolor="#ddd", ticklen=4,
            tickfont=dict(size=12, color="#333", family=LIXINGER_FONT),
        ),
        hovermode=hovermode, showlegend=False,
        font=dict(family=LIXINGER_FONT, color="#333"),
    )
    return fig


# ─── 格雷厄姆指数评级表(差值法,理杏仁口径,单位 %) ───
# 来源:01_knowledge/02_权益类动态调整/04_格雷厄姆指数.md 第 41-47 行
# 差值 = (1 / A股全指PE) − 10Y国债收益率
GRAHAM_DIFF_TABLE = [
    # (diff_min_pct, label, badge, equity_low, equity_high)
    (6.0,   "极度吸引", "🟢🟢", 75, 85),
    (4.0,   "高度吸引", "🟢",   65, 75),
    (2.0,   "吸引",     "🟡",   55, 65),
    (0.0,   "中性",     "🟡",   40, 55),
    (-99,   "不吸引",   "🔴",   20, 40),
]

# 历史参照点(沪深 300 PE,作为差值法历史对照,note 含原始走势)
GRAHAM_HISTORY = [
    {"date": "2008-10", "pe": 12,   "yield": 3.3, "diff": (1/12   *100 - 3.3), "note": "🟢 大底,后续大涨"},
    {"date": "2014-06", "pe": 8,    "yield": 4.1, "diff": (1/8    *100 - 4.1), "note": "🟢 绝佳买点"},
    {"date": "2015-06", "pe": 18,   "yield": 3.6, "diff": (1/18   *100 - 3.6), "note": "🔴 顶部区"},
    {"date": "2018-12", "pe": 10,   "yield": 3.3, "diff": (1/10   *100 - 3.3), "note": "🟢 绝佳买点"},
    {"date": "2021-02", "pe": 18,   "yield": 3.2, "diff": (1/18   *100 - 3.2), "note": "🔴 顶部区"},
    {"date": "2024-01", "pe": 10.5, "yield": 2.5, "diff": (1/10.5 *100 - 2.5), "note": "🟢 底部区"},
]

# 时间窗口选项(供格雷厄姆 section + 后续复用)
GRAHAM_WINDOWS = [
    ("1 年",  365),
    ("3 年",  365 * 3),
    ("5 年",  365 * 5),
    ("10 年", 365 * 10),
    ("全部",  None),
]


def _graham_rating(diff_pct: float) -> tuple[str, str, int, int]:
    """差值法评级:返回 (label, badge, equity_low, equity_high)。diff_pct 单位为 %."""
    for g_min, label, badge, lo, hi in GRAHAM_DIFF_TABLE:
        if diff_pct >= g_min:
            return label, badge, lo, hi
    return "不吸引", "🔴", 20, 40


@st.cache_data(ttl=600, show_spinner=False)
def _load_macro_series(db_path: str, indicator: str, mtime: float,
                       years: int = 5) -> pd.DataFrame:
    p = Path(db_path)
    if not p.exists():
        return pd.DataFrame()
    cutoff = date.today() - timedelta(days=365 * years)
    con = duckdb.connect(str(p), read_only=True)
    try:
        df = con.execute(
            "SELECT date, value FROM macro "
            "WHERE indicator = ? AND value IS NOT NULL AND date >= ? "
            "ORDER BY date",
            [indicator, cutoff],
        ).fetchdf()
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@st.cache_data(ttl=600, show_spinner=False)
def _load_macro_latest(db_path: str, indicator: str, mtime: float) -> dict | None:
    """读最新一期 + 5y 分位。返回 {value, date, pct_5y} 或 None。"""
    p = Path(db_path)
    if not p.exists():
        return None
    con = duckdb.connect(str(p), read_only=True)
    try:
        row = con.execute(
            "SELECT value, date FROM macro WHERE indicator = ? AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT 1",
            [indicator],
        ).fetchone()
        if not row:
            return None
        cur = float(row[0])
        cur_date = str(row[1])
        cutoff = date.today() - timedelta(days=365 * 5)
        series = con.execute(
            "SELECT value FROM macro WHERE indicator = ? AND value IS NOT NULL AND date >= ?",
            [indicator, cutoff],
        ).fetchdf()
        pct = float((series["value"] <= cur).sum()) / len(series) if len(series) > 5 else None
        return {"value": cur, "date": cur_date, "pct_5y": pct, "n_5y": len(series)}
    except Exception:
        return None
    finally:
        con.close()


@st.cache_data(ttl=600, show_spinner=False)
def _load_industry_pe_latest(db_path: str, mtime: float) -> pd.DataFrame:
    p = Path(db_path)
    if not p.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(p), read_only=True)
    try:
        df = con.execute(
            """
            WITH ranked AS (
                SELECT industry_code, industry_name, level,
                       pe_median, pe_weighted, pe_arith, n_companies, date,
                       ROW_NUMBER() OVER (PARTITION BY industry_code ORDER BY date DESC) AS rn
                FROM industry_pe
                WHERE pe_median IS NOT NULL
            )
            SELECT industry_code, industry_name, level, pe_median, pe_weighted,
                   pe_arith, n_companies, date
            FROM ranked WHERE rn = 1
            ORDER BY pe_median
            """,
        ).fetchdf()
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    return df


@st.cache_data(ttl=600, show_spinner=False)
def _load_graham_diff_series(db_path: str, mtime: float) -> pd.DataFrame:
    """计算历史股债差时间序列:(1/A_FULL_PE) − 10Y_YIELD,按日期 inner-join。"""
    p = Path(db_path)
    if not p.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(p), read_only=True)
    try:
        df = con.execute(
            """
            WITH pe AS (
                SELECT date, value AS pe FROM macro
                WHERE indicator = 'A_FULL_PE' AND value IS NOT NULL AND value > 0
            ),
            yld AS (
                SELECT date, value AS yld FROM macro
                WHERE indicator = '10Y_YIELD' AND value IS NOT NULL
            )
            SELECT pe.date AS date,
                   (1.0 / pe.pe) * 100.0 - yld.yld AS diff
            FROM pe JOIN yld ON pe.date = yld.date
            ORDER BY pe.date
            """,
        ).fetchdf()
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _load_kondratieff() -> dict:
    if not KONDRATIEFF_YAML.exists():
        return {}
    try:
        return yaml.safe_load(KONDRATIEFF_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _current_band(value: float, bands: list[dict]) -> dict | None:
    """根据当前值找到所处的 band(用于左侧高亮当前档位)。"""
    for b in bands:
        lo = b.get("lo"); hi = b.get("hi")
        ok_lo = (lo is None) or (value >= lo)
        ok_hi = (hi is None) or (value < hi)
        if ok_lo and ok_hi:
            return b
    return None
