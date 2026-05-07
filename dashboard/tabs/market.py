"""dash-01 L1 市场周期 Tab — 回答"现在是好时机吗?"。

v2.1 (2026-05-05) 切理杏仁口径:差值法 + A 股全指(000985 中证全指)PE-TTM.mcw
布局:
  ⓪ 综合结论 banner — 三信号(康波/格雷厄姆差值/A股全指 PE 分位)合成
  ① 康波周期定位卡 — 静态 yaml,知识库驱动
  ② 格雷厄姆指数 — (1/A股全指 PE) − 10Y 国债 = 差值法 %(理杏仁口径)
  ③ 5 项宏观时序(M2/CPI/10Y/USDCNY/A_FULL_PE)+ 阈值红绿灯
  ④ A 股全指 PE 全周期分位带
  ⑤ 行业 PE 热力图
  侧栏:📍 我的持仓水位

数据源:
  - 5 项宏观:DuckDB `macro` 表(.tools/db/fetch_macro.py)
    A_FULL_PE 由理杏仁 API 拉(open.lixinger.com/api/cn/index/fundamental,000985 pe_ttm.mcw)
  - 行业 PE: DuckDB `industry_pe` 表
  - 持仓水位:portfolio.yaml + .tools/portfolio/loader.py
  - 康波周期:.tools/dashboard/data/kondratieff.yaml
  - 格雷厄姆评级:01_knowledge/02_权益类动态调整/04_格雷厄姆指数.md
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[3]
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


# ─────────────────────────────────────────────────────────────────────
# ⓪ 综合结论 banner — 三信号合成
# ─────────────────────────────────────────────────────────────────────

def _section_verdict_banner(macro_path: str, macro_mtime: float) -> None:
    """三信号合成:康波(静态权重) + 格雷厄姆差值(动态) + A 股全指 PE 全周期分位(动态)。

    评分规则(每信号 -1 / 0 / +1):
      康波(萧条期防御) → -1   (静态)
      格雷厄姆差值 ≥4% → +1 / [2,4)% → 0 / <2% → -1
      A 股全指 PE 5y 分位 ≤30% → +1 / 30-70% → 0 / >70% → -1
    合成总分 → 总评级 + 推荐权益区间
    """
    kdf = _load_kondratieff()
    hs = _load_macro_latest(macro_path, "A_FULL_PE", macro_mtime)
    yld = _load_macro_latest(macro_path, "10Y_YIELD", macro_mtime)

    # 信号 1:康波(静态从 yaml)
    kondratieff_phase = kdf.get("phase", "萧条期中后段") if kdf else "萧条期中后段"
    kondratieff_emoji = kdf.get("phase_emoji", "🔴") if kdf else "🔴"
    kondratieff_score = -1  # 萧条期默认偏防御

    # 信号 2:格雷厄姆指数(差值法,理杏仁口径)
    if hs and yld and hs["value"] > 0 and yld["value"] > 0:
        ey_pct = (1.0 / hs["value"]) * 100.0       # 盈利收益率 %
        bond_pct = yld["value"]                    # 10Y 国债已是 %
        graham_diff = ey_pct - bond_pct
        g_label, g_badge, eq_lo, eq_hi = _graham_rating(graham_diff)
        graham_score = 1 if graham_diff >= 4.0 else (0 if graham_diff >= 2.0 else -1)
        graham_text = f"{g_badge} {graham_diff:+.2f}% {g_label}"
    else:
        graham_diff = None
        graham_score = 0
        graham_text = "⚪ 数据缺"
        eq_lo, eq_hi = 40, 55

    # 信号 3:A 股全指 PE 5y 分位
    if hs and hs.get("pct_5y") is not None:
        pct = hs["pct_5y"]
        if pct <= 0.30:
            hs_score, hs_badge = 1, "🟢"
        elif pct <= 0.70:
            hs_score, hs_badge = 0, "🟡"
        else:
            hs_score, hs_badge = -1, "🔴"
        hs_text = f"{hs_badge} {hs['value']:.1f}({pct*100:.0f}% 分位)"
    else:
        hs_score = 0
        hs_text = "⚪ 数据缺"

    total = kondratieff_score + graham_score + hs_score

    # 综合判定 — 取格雷厄姆建议区间为主,康波做防御封顶
    if total >= 2:
        verdict_emoji, verdict_text = "🟢🟢", "股市极度吸引 · 加仓窗口"
        eq_target = eq_hi
    elif total == 1:
        verdict_emoji, verdict_text = "🟢", "股市偏吸引 · 逐步加仓"
        eq_target = (eq_lo + eq_hi) // 2
    elif total == 0:
        verdict_emoji, verdict_text = "🟡", "股债平衡 · 持有观察"
        eq_target = (eq_lo + eq_hi) // 2
    elif total == -1:
        verdict_emoji, verdict_text = "🟡", "防御为主 · 谨慎加仓"
        eq_target = eq_lo
    else:
        verdict_emoji, verdict_text = "🔴", "全面防御 · 减仓避险"
        eq_target = max(20, eq_lo - 10)

    # 康波封顶:萧条期权益建议不超过 75%
    eq_max_by_kw = (kdf or {}).get("equity_target_pct_max", 75)
    eq_target = min(eq_target, eq_max_by_kw)

    # 信号通过数(+1 算通过)
    pass_n = sum(1 for s in (kondratieff_score, graham_score, hs_score) if s >= 0)

    # 渲染:浅色背景 banner
    color = {"🟢🟢": "#1b8a3a", "🟢": "#1b8a3a", "🟡": "#f0ad4e", "🔴": "#d9534f"}.get(verdict_emoji, "#888")
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, {color}22 0%, transparent 100%);
                    border-left: 5px solid {color};
                    padding: 14px 18px; border-radius: 8px; margin: 8px 0 16px;">
          <div style="font-size: 18px; font-weight: 700;">
            {verdict_emoji} 当前综合判断:{verdict_text}
            <span style="font-size: 13px; color: #555; margin-left: 12px; font-weight: 500;">
              建议权益占比 ≈ <b>{eq_target}%</b> · 三信号通过 {pass_n}/3
            </span>
          </div>
          <div style="font-size: 13px; color: #444; margin-top: 8px;">
            <b>康波</b>:{kondratieff_emoji} {kondratieff_phase}(防御主)　|
            <b>股债收益差</b>:{graham_text}　|
            <b>A 股全指 PE 5y 分位</b>:{hs_text}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────
# ① 康波周期定位卡
# ─────────────────────────────────────────────────────────────────────

def _section_kondratieff_card() -> None:
    kdf = _load_kondratieff()
    if not kdf:
        st.caption("⚠️ 康波周期 yaml 缺失:.tools/dashboard/data/kondratieff.yaml")
        return

    cycle = kdf.get("cycle", "—")
    phase = kdf.get("phase", "—")
    phase_range = kdf.get("phase_range", "—")
    phase_emoji = kdf.get("phase_emoji", "🟡")
    conflicts = kdf.get("core_conflicts", [])
    strategy = kdf.get("strategy_summary", "")
    key_node = kdf.get("key_node", {}) or {}
    last_updated = kdf.get("last_updated", "—")

    with st.container(border=True):
        st.markdown(
            f"#### {phase_emoji} {cycle} · **{phase}** ({phase_range})"
        )
        if conflicts:
            for line in conflicts:
                st.markdown(f"- {line}")
        if strategy:
            st.markdown(f"**📌 策略**:{strategy}")
        if key_node.get("date"):
            st.markdown(
                f"**⏰ 关键节点**:{key_node['date']} — {key_node.get('description', '')}"
            )

        with st.expander("📚 完整四阶段时间表 + 数据源", expanded=False):
            phases = kdf.get("phases_table", [])
            if phases:
                pdf = pd.DataFrame(phases)
                if "current" in pdf.columns:
                    pdf["current"] = pdf["current"].fillna(False).map(
                        lambda v: "✅ 当前" if v else ""
                    )
                st.dataframe(pdf, hide_index=True, use_container_width=True)
            st.caption(
                f"📅 数据更新:{last_updated} · "
                f"📖 来源:{kdf.get('source_md', '—')}"
            )


# ─────────────────────────────────────────────────────────────────────
# ② 格雷厄姆指数 — 动态算 + 历史参照
# ─────────────────────────────────────────────────────────────────────

# 时间窗口选项(供格雷厄姆 section + 后续复用)
GRAHAM_WINDOWS = [
    ("1 年",  365),
    ("3 年",  365 * 3),
    ("5 年",  365 * 5),
    ("10 年", 365 * 10),
    ("全部",  None),
]


def _section_graham_index(macro_path: str, macro_mtime: float) -> None:
    """格雷厄姆指数(差值法,理杏仁口径):

       graham_diff = (1 / A股全指 PE-TTM 市值加权) − 10Y 国债收益率
                   = 盈利收益率 − 无风险利率(单位 %)
    """
    hs = _load_macro_latest(macro_path, "A_FULL_PE", macro_mtime)
    yld = _load_macro_latest(macro_path, "10Y_YIELD", macro_mtime)

    if not (hs and yld) or hs["value"] <= 0 or yld["value"] <= 0:
        st.caption("(A_FULL_PE 或 10Y_YIELD 缺数据。先跑 "
                   "`.venv/bin/python .tools/db/fetch_macro.py --only A_FULL_PE,10Y_YIELD`)")
        return

    pe = hs["value"]
    bond_pct = yld["value"]                    # 已是 %
    ey_pct = (1.0 / pe) * 100.0
    graham_diff = ey_pct - bond_pct
    label, badge, eq_lo, eq_hi = _graham_rating(graham_diff)

    diff_series_full = _load_graham_diff_series(macro_path, macro_mtime)

    with st.container(border=True):
        # ─── 顶部 3 列:核心指标卡(紧凑 2×2)+ 阈值红绿灯(含当前位置) ───
        c1, c2, c3 = st.columns([1.1, 1.1, 2.2])

        # 两列 metric 容器与 c3 红绿灯做等高对齐:c3 = 1 标题 + 4 档位 ≈ 175px
        STAT_COL_HEIGHT = 175

        def _stat(label: str, value: str, tip: str = "") -> str:
            tip_attr = f' title="{tip}"' if tip else ""
            return (
                f"<div style='flex:1;display:flex;flex-direction:column;"
                f"justify-content:center'>"
                f"<div style='font-size:13px;color:#888;font-weight:400'{tip_attr}>"
                f"{label}</div>"
                f"<div style='font-size:28px;font-weight:600;"
                f"line-height:1.15;margin-top:4px'>{value}</div>"
                f"</div>"
            )

        def _stat_col(*cards: str) -> str:
            return (
                f"<div style='min-height:{STAT_COL_HEIGHT}px;display:flex;"
                f"flex-direction:column;justify-content:space-between;gap:6px'>"
                f"{''.join(cards)}</div>"
            )

        with c1:
            st.markdown(
                _stat_col(
                    _stat("A 股全指 PE-TTM", f"{pe:.2f}",
                          f"最新 {hs['date']} · 中证全指 000985 市值加权 · 理杏仁 API"),
                    _stat("盈利收益率 1/PE", f"{ey_pct:.2f}%"),
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _stat_col(
                    _stat("10Y 国债收益率", f"{bond_pct:.2f}%", f"最新 {yld['date']}"),
                    _stat("股债差(格雷厄姆)", f"{graham_diff:+.2f}%",
                          "盈利收益率 − 国债收益率 · 与理杏仁制图同口径"),
                ),
                unsafe_allow_html=True,
            )
        with c3:
            # 4 档显示(≥6 极度吸引合并入 ≥4 高度吸引)— UI 简化,判定仍走原 5 档
            BANDS_UI = [
                ("🟢", "≥4%   高度吸引",  4.0),
                ("🟡", "2-4%  吸引",       2.0),
                ("🟠", "0-2%  中性",       0.0),
                ("🔴", "&lt;0%   不吸引", -99.0),
            ]
            cur_idx = next(
                (i for i, (_b, _t, lo) in enumerate(BANDS_UI) if graham_diff >= lo),
                len(BANDS_UI) - 1,
            )
            rows_html = [
                "<div style='font-weight:600;font-size:14px'>"
                "📐 阈值红绿灯(差值法,单位 %)</div>"
            ]
            for i, (b, t, _lo) in enumerate(BANDS_UI):
                if i == cur_idx:
                    rows_html.append(
                        f"<div style='font-weight:600;color:#111'>"
                        f"{b} {t}  ← 当前 <b>{graham_diff:+.2f}%</b> "
                        f"· 建议权益 <b>{eq_lo}-{eq_hi}%</b></div>"
                    )
                else:
                    rows_html.append(
                        f"<div style='color:#555'>{b} {t}</div>"
                    )
            st.markdown(
                f"<div style='min-height:{STAT_COL_HEIGHT}px;display:flex;"
                f"flex-direction:column;justify-content:space-between;gap:4px'>"
                f"{''.join(rows_html)}</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            # 注入局部 CSS:压缩本容器内 element-container 默认间距
            "<style>"
            "div[data-testid='stVerticalBlock'] > div[data-testid='element-container']"
            ":has(.js-plotly-plot){margin-top:-4px !important;margin-bottom:-8px !important}"
            "</style>"
            "<div style='border-top:1px dashed #ccc;margin:6px 0 2px'></div>"
            "<div style='font-size:13px;color:#444;margin-bottom:0'>"
            "<b>📈 历史走势 + 当前位置</b> "
            "<span style='color:#888;font-size:11px;margin-left:8px'>"
            "选时间窗口 → 看当前差值在该区间的相对位置(色带=阈值红绿灯)</span></div>",
            unsafe_allow_html=True,
        )

        # ─── 时间窗口选择 ───
        win_labels = [w[0] for w in GRAHAM_WINDOWS]
        sel_label = st.radio(
            "时间窗口", win_labels, index=2, horizontal=True,
            label_visibility="collapsed", key="graham_window",
        )
        win_days = dict(GRAHAM_WINDOWS)[sel_label]

        # ─── 截取窗口内的差值时序 + 算分位 ───
        if diff_series_full.empty:
            st.caption("(股债差时序数据缺失)")
            return
        if win_days is None:
            df_win = diff_series_full
        else:
            cutoff = pd.Timestamp(date.today() - timedelta(days=win_days))
            df_win = diff_series_full[diff_series_full["date"] >= cutoff].copy()
        if df_win.empty or len(df_win) < 5:
            st.caption(f"(窗口 {sel_label} 数据不足,样本 {len(df_win)} 条)")
            return

        rank_pct = float((df_win["diff"] <= graham_diff).sum()) / len(df_win)
        win_min = float(df_win["diff"].min())
        win_max = float(df_win["diff"].max())
        win_med = float(df_win["diff"].median())

        # ─── 窗口统计小条 ───
        s1, s2, s3, s4 = st.columns(4)
        s1.metric(f"{sel_label}内当前分位", f"{rank_pct*100:.1f}%",
                  help=f"在 {len(df_win)} 个样本中,有 {rank_pct*100:.1f}% 的样本 ≤ 当前 {graham_diff:+.2f}%")
        s2.metric(f"{sel_label}内中位数", f"{win_med:+.2f}%")
        s3.metric(f"{sel_label}内最低", f"{win_min:+.2f}%")
        s4.metric(f"{sel_label}内最高", f"{win_max:+.2f}%")

        # ─── 主图:理杏仁风格(浅色实心色带 + 单一折线 + 当前点) ───
        BAND_EDGES = [-15, 0, 2, 4, 6, 15]   # 阈值法五档边界
        # 浅色实心色带(opacity=1)— 不与折线/散点产生颜色叠加
        BAND_FILLS = ["#fef5f4", "#fff7f0", "#fffdf2", "#f2fcf6", "#e6faee"]
        BAND_LABEL_COLORS = ["#c0392b", "#d35400", "#b58a00", "#27ae60", "#1e8449"]
        BAND_LABELS = ["不吸引", "中性", "吸引", "高度吸引", "极度吸引"]
        FONT_FAMILY = ('"PingFang SC","Helvetica Neue","Microsoft YaHei",'
                       '"Hiragino Sans GB","Noto Sans CJK SC",sans-serif')

        # 是否叠加历史散点(默认关闭,保持图面清爽)
        show_hist = st.checkbox("叠加 HS300 历史关键时点(◇)", value=False,
                                key="graham_show_hist")
        hist_pts: list[dict] = []
        if show_hist:
            x_min = df_win["date"].min()
            x_max = df_win["date"].max()
            for h in GRAHAM_HISTORY:
                d = pd.to_datetime(h["date"] + "-15", errors="coerce")
                if pd.notna(d) and x_min <= d <= x_max:
                    hist_pts.append({"date": d, "diff": h["diff"], "note": h["note"]})

        data_min = min(win_min, graham_diff)
        data_max = max(win_max, graham_diff)
        if hist_pts:
            data_min = min(data_min, min(p["diff"] for p in hist_pts))
            data_max = max(data_max, max(p["diff"] for p in hist_pts))
        data_range = max(data_max - data_min, 0.5)
        pad = max(data_range * 0.08, 0.25)
        y_lo = data_min - pad
        y_hi = data_max + pad

        fig = go.Figure()
        # 浅色实心色带 — opacity 拉满,纯背景作用
        for (lo, hi, fill, lab, lab_color) in zip(
            BAND_EDGES[:-1], BAND_EDGES[1:], BAND_FILLS, BAND_LABELS, BAND_LABEL_COLORS,
        ):
            seg_lo = max(lo, y_lo)
            seg_hi = min(hi, y_hi)
            if seg_hi <= seg_lo:
                continue
            fig.add_hrect(y0=seg_lo, y1=seg_hi, fillcolor=fill,
                          opacity=1.0, line_width=0, layer="below")
            mid_y = (seg_lo + seg_hi) / 2
            fig.add_annotation(
                xref="paper", yref="y", x=0.995, y=mid_y,
                text=f"<b>{lab}</b>",
                showarrow=False, xanchor="right", yanchor="middle",
                font=dict(size=11, color=lab_color, family=FONT_FAMILY),
            )

        # 折线 — 加粗到 2.8px,样条平滑
        fig.add_trace(go.Scatter(
            x=df_win["date"], y=df_win["diff"],
            mode="lines", name="股债差",
            line=dict(color="#1f4e9c", width=2.8, shape="spline", smoothing=0.6),
            hovertemplate="%{x|%Y-%m-%d}<br>股债差: %{y:.2f}%<extra></extra>",
        ))

        # 历史散点(可选,默认关闭)
        if hist_pts:
            fig.add_trace(go.Scatter(
                x=[p["date"] for p in hist_pts],
                y=[p["diff"] for p in hist_pts],
                mode="markers+text",
                text=[p["note"][:2] for p in hist_pts],
                textposition="top center",
                textfont=dict(size=14, family=FONT_FAMILY),
                marker=dict(size=11, color="#fff",
                            line=dict(color="#555", width=1.5),
                            symbol="diamond"),
                name="历史时点",
                hovertemplate=("%{x|%Y-%m}<br>股债差: %{y:.2f}%<br>"
                               "<extra>HS300 历史对照</extra>"),
                showlegend=False,
            ))

        # 当前值 — 单一蓝圆 + 数字气泡(无水平线、无中位线)
        cur_x = df_win["date"].iloc[-1]
        fig.add_trace(go.Scatter(
            x=[cur_x], y=[graham_diff],
            mode="markers",
            marker=dict(size=14, color="#1f4e9c",
                        line=dict(color="white", width=2.5),
                        symbol="circle"),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_annotation(
            x=cur_x, y=graham_diff,
            text=f"<b>{graham_diff:+.2f}%</b>",
            showarrow=True, arrowhead=0, arrowwidth=1.2, arrowcolor="#1f4e9c",
            ax=-36, ay=-26,
            font=dict(size=13, color="#1f4e9c", family=FONT_FAMILY),
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#1f4e9c", borderwidth=1, borderpad=3,
        )

        fig.update_layout(
            height=340, margin=dict(t=8, b=30, l=55, r=20),
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(
                range=[y_lo, y_hi], fixedrange=False,
                title=dict(text="股债差 (%)",
                           font=dict(size=13, color="#333", family=FONT_FAMILY),
                           standoff=6),
                tickfont=dict(size=12, color="#333", family=FONT_FAMILY),
                showgrid=True, gridcolor="#f0f0f0", gridwidth=1,
                zeroline=False, showline=False,
                ticks="",
            ),
            xaxis=dict(
                title="",
                tickfont=dict(size=12, color="#333", family=FONT_FAMILY),
                showgrid=False,            # 关闭 vertical grid
                zeroline=False, showline=False,
                ticks="outside", tickcolor="#ddd", ticklen=4,
            ),
            hovermode="x unified", showlegend=False,
            font=dict(family=FONT_FAMILY, color="#333"),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            f"<div style='margin-top:-4px;font-size:12px;color:#666;"
            f"line-height:1.5;font-family:{FONT_FAMILY}'>"
            f"💡 当前 <b>{graham_diff:+.2f}%</b> 在 <b>{sel_label}内</b> 处于 "
            f"<b>{rank_pct*100:.1f}% 分位</b> · 评级 <b>{badge} {label}</b> · "
            "色带=阈值档位 / 蓝点=当前</div>",
            unsafe_allow_html=True,
        )

        # ─── 沪深 300 历史标记点(知识库归档) ───
        with st.expander("📜 沪深 300 历史参照点(知识库手工归档,辅助对照)", expanded=False):
            hist_df = pd.DataFrame(GRAHAM_HISTORY)
            hist_df["diff"] = hist_df["diff"].round(2)
            hist_df.columns = ["日期", "HS300 PE", "10Y 国债 %", "股债差 %", "实际走势"]
            st.dataframe(hist_df, hide_index=True, use_container_width=True)
            st.caption("数据源:01_knowledge/02_权益类动态调整/04_格雷厄姆指数.md")


# ─────────────────────────────────────────────────────────────────────
# ③ 5 项宏观时序(原段 1)+ caption(M1 #4)
# ─────────────────────────────────────────────────────────────────────

def _current_band(value: float, bands: list[dict]) -> dict | None:
    """根据当前值找到所处的 band(用于左侧高亮当前档位)。"""
    for b in bands:
        lo = b.get("lo"); hi = b.get("hi")
        ok_lo = (lo is None) or (value >= lo)
        ok_hi = (hi is None) or (value < hi)
        if ok_lo and ok_hi:
            return b
    return None


def _section_company_graham_number(selected: str, db_mtime: float) -> None:
    """单公司格氏数 PE×PB 实时位置卡片(D3 阶段 C 项 1)。

    与 ② 格雷厄姆指数(全市场)对应:聚焦单只股票当前的格雷厄姆数判定。
    数据源:graham_steps.load_graham_metrics + check_graham_number。
    """
    if not selected:
        return
    try:
        from graham_steps import (
            load_graham_metrics, check_graham_number, classify_graham_type,
        )
    except Exception as e:
        st.caption(f"⚠️  graham_steps 模块加载失败:{e}")
        return

    # selected 是 folder 名(如 "贵州茅台"),通过 companies 表反查 ticker
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            row = con.execute(
                "SELECT ticker FROM companies WHERE folder = ? OR name = ? LIMIT 1",
                [selected, selected],
            ).fetchone()
            ticker = row[0] if row else ""
        finally:
            con.close()
    except Exception as e:
        st.caption(f"⚠️  ticker 反查失败:{e}")
        return
    if not ticker:
        st.caption(f"(未找到 {selected} 的 ticker 映射)")
        return

    try:
        m = load_graham_metrics(ticker)
        gn = check_graham_number(m)
        cls = classify_graham_type(m)
    except Exception as e:
        st.caption(f"⚠️  格氏数计算失败:{e}")
        return

    # 评级 → 颜色映射
    grade_color = {
        "严达标(原版)": "#10B981",     # 绿
        "严达标": "#10B981",
        "软达标 1 档": "#34D399",       # 浅绿
        "软达标 2 档": "#F59E0B",       # 黄
        "软达标": "#F59E0B",
        "不达标(估值偏贵)": "#EF4444",  # 红
        "不达标": "#EF4444",
    }
    color = grade_color.get(gn.grade, "#6B7280")

    pe_str = f"{m.get('pe'):.2f}" if m.get("pe") is not None else "—"
    pb_str = f"{m.get('pb'):.2f}" if m.get("pb") is not None else "—"
    pe_x_pb_str = f"{gn.pe_x_pb:.2f}" if gn.pe_x_pb is not None else "—"

    # 卡片渲染:单行 + 紧凑
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.2, 2.0])
        c1.metric(f"📍 {selected}", ticker, help="当前选中公司,sidebar 切换")
        c2.metric("PE", pe_str)
        c2.metric("PB", pb_str)
        c3.metric("PE × PB", pe_x_pb_str,
                   delta=gn.grade,
                   delta_color="off",
                   help="格雷厄姆数:防御股 ≤ 22.5 严达标 / ≤ 30 软达标 1 / ≤ 50 软达标 2")
        with c4:
            st.markdown(
                f'<div style="margin-top:8px;">'
                f'<span style="font-size:13px;color:#6B7280;">价值类型</span>'
                f'<div style="font-size:18px;font-weight:600;color:{color};margin-top:4px;">'
                f'{cls.cls_emoji} {cls.cls_name}'
                f'</div>'
                f'<div style="font-size:12px;color:#6B7280;margin-top:6px;">'
                f'置信度 {cls.confidence:.0%}'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.caption(
            f"💡 完整五步分析(商业模式/盈利/财务/估值/审视)→ 切到 **💎 格雷厄姆分析法** Tab"
        )


def _section_thermometer_trends(db_path: str, mtime: float) -> None:
    """5 项宏观时序 — 左标右图布局 + 图上画红绿灯阈值带。

    左列(1/4 宽):指标名 / 当前值 / 含义 / 阈值列表(当前档位高亮)
    右列(3/4 宽):时序折线 + 横向 hrect 红绿灯带
    """
    try:
        from header_thermometer import INDICATORS
    except Exception:
        st.warning("⚠️ 无法加载 header_thermometer.INDICATORS,跳过宏观时序")
        return

    have_any = False
    for ind in INDICATORS:
        df = _load_macro_series(db_path, ind["key"], mtime, years=5)
        if df.empty:
            st.caption(f"({ind['label']} 无数据)")
            continue
        have_any = True

        cur = float(df.iloc[-1]["value"])
        cur_date = df.iloc[-1]["date"].strftime("%Y-%m-%d")
        bands = ind.get("bands", []) or []
        cur_band = _current_band(cur, bands)
        cur_emoji = (cur_band or {}).get("emoji", "⚪")
        cur_label = (cur_band or {}).get("label", "—")

        meta_col, chart_col = st.columns([1, 4])

        with meta_col:
            st.markdown(
                f"<div style='font-size:20px;font-weight:800;margin-bottom:10px;"
                f"color:#1a1a1a'>{ind['label']}</div>",
                unsafe_allow_html=True,
            )
            if bands:
                for b in bands:
                    is_cur = (b is cur_band)
                    style = ("font-weight:700;color:#000;background:#fff3cd;"
                             "padding:3px 8px;border-radius:4px;"
                             "border:1px solid #ffd96a") if is_cur else (
                             "color:#666;padding:3px 8px;background:#fafafa;"
                             "border-radius:4px;border:1px solid #eee")
                    st.markdown(
                        f"<div style='font-size:13px;{style};margin:5px 0;"
                        f"line-height:1.55'>"
                        f"{b['emoji']} {b['label']}{' ← 当前' if is_cur else ''}</div>",
                        unsafe_allow_html=True,
                    )

        with chart_col:
            fig = go.Figure()
            # 数据范围 + 8% padding(贴紧数据,色带 clip 到可见区域)
            y_min = float(df["value"].min())
            y_max = float(df["value"].max())
            data_range = max(y_max - y_min, 0.5)
            pad = max(data_range * 0.08, 0.25)
            y_lo = y_min - pad
            y_hi = y_max + pad

            # 浅色实心色带(opacity=1.0)+ 右侧深色档位标签
            for b in bands:
                lo = b.get("lo"); hi = b.get("hi")
                y0 = lo if lo is not None else y_lo
                y1 = hi if hi is not None else y_hi
                seg_lo = max(y0, y_lo)
                seg_hi = min(y1, y_hi)
                if seg_hi <= seg_lo:
                    continue
                light_fill = LIGHT_BAND_FILL.get(b["fill"], "#f5f5f5")
                fig.add_hrect(y0=seg_lo, y1=seg_hi, fillcolor=light_fill,
                              opacity=1.0, line_width=0, layer="below")

            # 折线 — 2.8px spline,深沉金融蓝
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["value"],
                mode="lines", name=ind["label"],
                line=dict(width=2.6, color=LIXINGER_LINE_COLOR,
                          shape="spline", smoothing=0.6),
                hovertemplate="%{x|%Y-%m-%d}<br>" + ind["label"] + ": %{y:.2f}<extra></extra>",
            ))
            # 当前点突出
            fig.add_trace(go.Scatter(
                x=[df.iloc[-1]["date"]], y=[cur],
                mode="markers",
                marker=dict(size=11, color=LIXINGER_LINE_COLOR,
                            line=dict(color="white", width=2.5)),
                showlegend=False, hoverinfo="skip",
            ))
            _apply_lixinger_layout(
                fig, height=210,
                margin_t=8, margin_b=22, margin_l=42, margin_r=14,
                y_range=[y_lo, y_hi],
            )
            st.plotly_chart(fig, use_container_width=True)

        # 全宽底部卡片(脱离左右两列,从最左侧贯穿到最右)
        # 一行展开:数值 + 日期 + 档位 + 含义 + intro 介绍
        meaning = ind.get("meaning", "")
        intro = ind.get("intro", "")
        meaning_html = (
            "<span style='color:#555;margin-left:14px;padding-left:14px;"
            "border-left:1px solid #d6dde5'>"
            f"💡 <b>含义:</b>{meaning}</span>"
        ) if meaning else ""
        intro_html = (
            "<div style='margin-top:6px;padding-top:6px;border-top:1px dashed #e2e6ea;"
            "font-size:13px;color:#555;line-height:1.55'>"
            f"📘 <b>是什么:</b>{intro}</div>"
        ) if intro else ""
        st.markdown(
            "<div style='margin-top:-6px;padding:10px 14px;background:#f8f9fa;"
            "border-left:3px solid #0d6efd;border-radius:3px'>"
            # 第一行:数值 / 日期 / 档位 / 含义 一字排开
            "<div style='display:flex;align-items:center;gap:14px;flex-wrap:wrap'>"
            f"<span style='font-size:22px;font-weight:700;color:#0d6efd;line-height:1'>"
            f"{ind['fmt'].format(cur)}</span>"
            f"<span style='font-size:12px;color:#888'>{cur_date}</span>"
            f"<span style='font-size:14px;font-weight:700;padding-left:14px;"
            f"border-left:1px solid #d6dde5'>{cur_emoji} {cur_label}</span>"
            f"{meaning_html}"
            "</div>"
            # 第二行:📘 是什么(M2 长介绍)
            f"{intro_html}"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div style='border-bottom:1px dashed #e0e0e0;margin:14px 0 18px'></div>",
                    unsafe_allow_html=True)

    if not have_any:
        st.info("📭 macro 表暂无数据。先跑:`.venv/bin/python .tools/db/fetch_macro.py`")


def _section_a_full_band(db_path: str, mtime: float) -> None:
    """段 ④:A 股全指 PE-TTM 分位带 — 当前值 + 全周期 20/50/80 分位横线。"""
    df = _load_macro_series(db_path, "A_FULL_PE", mtime, years=10)
    if df.empty or len(df) < 30:
        st.caption("(A_FULL_PE 数据不足。先跑 "
                   "`.venv/bin/python .tools/db/fetch_macro.py --only A_FULL_PE`)")
        return
    cur = df.iloc[-1]["value"]
    cur_date = df.iloc[-1]["date"]
    series = df["value"].dropna()
    p20, p50, p80 = (
        float(series.quantile(0.2)),
        float(series.quantile(0.5)),
        float(series.quantile(0.8)),
    )
    pct = float((series <= cur).sum()) / len(series)
    if pct <= 0.20:
        verdict, color = "🟢 低位(便宜)", "#1b8a3a"
    elif pct <= 0.50:
        verdict, color = "🟢 偏低", "#1b8a3a"
    elif pct <= 0.80:
        verdict, color = "🟡 中性", "#f0ad4e"
    else:
        verdict, color = "🔴 高位(贵)", "#d9534f"

    # 数据范围 + 8% padding
    y_min = float(series.min()); y_max = float(series.max())
    data_range = max(y_max - y_min, 0.5)
    pad = max(data_range * 0.05, 0.4)
    y_lo, y_hi = y_min - pad, y_max + pad

    # 4 段分位带(浅色实心) + 右侧深色档位标签
    BAND_DEFS = [
        (y_lo, p20,  "#e6faee", "#1e8449", "低估 (≤20%)"),
        (p20,  p50,  "#f2fcf6", "#27ae60", "偏低 (20-50%)"),
        (p50,  p80,  "#fffdf2", "#b58a00", "中性 (50-80%)"),
        (p80,  y_hi, "#fef5f4", "#c0392b", "高位 (>80%)"),
    ]

    fig = go.Figure()
    for lo, hi, fill, label_color, label_text in BAND_DEFS:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=fill, opacity=1.0,
                      line_width=0, layer="below")
        fig.add_annotation(
            xref="paper", yref="y", x=0.995, y=(lo + hi) / 2,
            text=f"<b>{label_text}</b>",
            showarrow=False, xanchor="right", yanchor="middle",
            font=dict(size=11, color=label_color, family=LIXINGER_FONT),
        )

    # 主线 — 2.8px spline
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["value"], name="A 股全指 PE",
        line=dict(color=LIXINGER_LINE_COLOR, width=2.8,
                  shape="spline", smoothing=0.6),
        hovertemplate="%{x|%Y-%m-%d}<br>PE: %{y:.2f}x<extra></extra>",
    ))

    # 当前点 + 数字气泡(单一强调)
    fig.add_trace(go.Scatter(
        x=[cur_date], y=[cur], mode="markers",
        marker=dict(size=14, color=LIXINGER_LINE_COLOR,
                    line=dict(color="white", width=2.5)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(
        x=cur_date, y=cur,
        text=f"<b>{cur:.1f}x · {pct*100:.0f}% 分位</b>",
        showarrow=True, arrowhead=0, arrowwidth=1.2,
        arrowcolor=LIXINGER_LINE_COLOR,
        ax=-50, ay=-32,
        font=dict(size=12, color=LIXINGER_LINE_COLOR, family=LIXINGER_FONT),
        bgcolor="rgba(255,255,255,0.95)",
        bordercolor=LIXINGER_LINE_COLOR, borderwidth=1, borderpad=3,
    )

    _apply_lixinger_layout(fig, height=340, y_title="PE-TTM (x)",
                           y_range=[y_lo, y_hi])

    st.markdown(
        f"<div style='font-size:13px;color:#444;margin:2px 0 6px'>"
        f"全周期分位 <b>{pct*100:.0f}%</b> · 评级 <b>{verdict}</b> · "
        f"P20={p20:.1f}x / P50={p50:.1f}x / P80={p80:.1f}x</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, use_container_width=True)


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


def _section_holdings_water_level() -> None:
    """侧栏:持仓水位(权益占比 vs 目标 + 家数 + 简要)。"""
    try:
        from loader import load_portfolio
        p = load_portfolio()
    except Exception as e:
        st.caption(f"(持仓 loader 加载失败:{e})")
        return

    actives = p.active()
    target_eq = p.account.target_equity_ratio or 0.0
    cash_min = p.account.cash_min_ratio or 0.0
    cash_max = p.account.cash_max_ratio or 1.0
    total_w = sum((h.target_weight or 0.0) for h in actives)
    cash_w = max(0.0, 1.0 - total_w)

    st.metric("权益占比", f"{total_w:.1%}", f"目标 {target_eq:.0%}")
    st.metric("现金占比", f"{cash_w:.1%}", f"区间 [{cash_min:.0%}, {cash_max:.0%}]")
    st.metric("active 家数", f"{len(actives)}")
    if target_eq > 0:
        ratio = min(total_w / target_eq, 1.5)
        st.progress(min(ratio / 1.5, 1.0),
                    text=f"权益水位 vs 目标:{(total_w / target_eq) * 100:.0f}%")
    if actives:
        st.markdown("**top 5 权重**")
        top5 = sorted(actives, key=lambda h: h.target_weight or 0, reverse=True)[:5]
        for h in top5:
            w = h.target_weight or 0
            st.caption(f"• {h.name} ({h.ticker}) · {w:.1%}")


def render(*args, **kwargs) -> None:
    """L1 市场周期 Tab 入口。

    兼容多种调用签名:
      render()
      render(db_mtime)
      render(companies, selected, db_mtime)
    """
    db_mtime = 0.0
    selected = ""
    if len(args) == 1 and isinstance(args[0], (int, float)):
        db_mtime = float(args[0])
    elif len(args) >= 3 and isinstance(args[2], (int, float)):
        db_mtime = float(args[2])
        selected = args[1] if isinstance(args[1], str) else ""
    elif "db_mtime" in kwargs:
        db_mtime = float(kwargs["db_mtime"])
    elif DB_PATH.exists():
        db_mtime = DB_PATH.stat().st_mtime
    if not selected:
        selected = kwargs.get("selected", "") or st.session_state.get("company", "")

    st.subheader("📊 L1 市场周期 · 现在是好时机吗?")

    macro_path = str(MACRO_DB)
    macro_mtime = MACRO_DB.stat().st_mtime if MACRO_DB.exists() else 0.0
    main_path = str(DB_PATH)

    main_col, side_col = st.columns([4, 1])
    with main_col:
        # ⓪ 综合结论 banner
        _section_verdict_banner(macro_path, macro_mtime)

        # ① 康波周期定位卡
        st.markdown("### ① 康波周期定位 · 我们处在哪个大周期?")
        _section_kondratieff_card()

        # ② 格雷厄姆指数
        st.markdown("### ② 格雷厄姆指数 · 股票比债券更值得买吗?")
        _section_graham_index(macro_path, macro_mtime)

        # ②.5 单公司格氏数 PE×PB(D3 阶段 C 项 1)
        if selected:
            st.markdown(f"#### ②.5 {selected} 格氏数 · 当前公司 PE×PB 实时位置")
            _section_company_graham_number(selected, db_mtime)

        # ③ 5 项宏观时序(原段 1 改提问式)
        st.markdown("---")
        st.markdown("### ③ 五大宏观信号 · 流动性、通胀、利率怎么样?")
        _section_thermometer_trends(macro_path, macro_mtime)

        # ④ A 股全指 PE 分位带
        st.markdown("---")
        st.markdown("### ④ 大盘估值水位 · A 股全指 PE 处于历史什么位置?")
        _section_a_full_band(macro_path, macro_mtime)

        # ⑤ 行业 PE 热力图(原段 3 改提问式)
        st.markdown("---")
        st.markdown("### ⑤ 行业估值矩阵 · 哪些行业被低估?")
        _section_industry_heatmap(main_path, db_mtime)

    with side_col:
        st.markdown("### 📍 我的持仓水位")
        _section_holdings_water_level()


__all__ = ["render"]
