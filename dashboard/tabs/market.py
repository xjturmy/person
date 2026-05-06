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
        # ─── 顶部 4 列:核心指标卡 ───
        c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.0, 1.8])
        with c1:
            st.metric("A 股全指 PE-TTM", f"{pe:.2f}",
                      help=f"最新 {hs['date']} · 中证全指 000985 市值加权 · 理杏仁 API")
            st.metric("盈利收益率 1/PE", f"{ey_pct:.2f}%")
        with c2:
            st.metric("10Y 国债收益率", f"{bond_pct:.2f}%",
                      help=f"最新 {yld['date']}")
            st.metric("股债差(格雷厄姆)", f"{graham_diff:+.2f}%",
                      help="盈利收益率 − 国债收益率 · 与理杏仁制图同口径")
        with c3:
            st.markdown(f"### {badge}")
            st.markdown(f"**{label}**")
            st.caption(f"建议权益 {eq_lo}-{eq_hi}%")
        with c4:
            st.markdown(
                "**📐 阈值红绿灯**(差值法,单位 %)\n\n"
                "🟢🟢 ≥6% 极度吸引\n\n"
                "🟢 4-6% 高度吸引\n\n"
                "🟡 2-4% 吸引\n\n"
                "🟠 0-2% 中性\n\n"
                "🔴 <0% 不吸引",
            )

        st.markdown(
            "<div style='border-top:1px dashed #ccc;margin:10px 0 8px'></div>"
            "<div style='font-size:13px;color:#444'><b>📈 历史走势 + 当前位置</b> "
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

        # ─── 主图:差值时序 + 阈值色带 + 当前点 + 当前水平线 ───
        # 自适应 y 轴:贴紧实际数据 + 包住 0/2 阈值线,留 0.4pp buffer
        BAND_EDGES = [-15, 0, 2, 4, 6, 15]   # 阈值法五档边界
        BAND_FILLS = ["#d9534f", "#fd7e14", "#f0ad4e", "#5cb85c", "#1b8a3a"]
        data_min = min(win_min, graham_diff)
        data_max = max(win_max, graham_diff)
        # 至少包住 0 和 2(中性 / 吸引边界),让用户看到当前在哪一档
        y_lo = min(data_min, 0) - 0.4
        y_hi = max(data_max, 2) + 0.4

        fig = go.Figure()
        # 阈值红绿灯色带 — 仅画落在 [y_lo, y_hi] 内的部分
        for lo, hi, fill in zip(BAND_EDGES[:-1], BAND_EDGES[1:], BAND_FILLS):
            seg_lo = max(lo, y_lo)
            seg_hi = min(hi, y_hi)
            if seg_hi > seg_lo:
                fig.add_hrect(y0=seg_lo, y1=seg_hi, fillcolor=fill,
                              opacity=0.12, line_width=0, layer="below")

        # 阈值边界线 — 仅画落在 y 轴范围内的
        for y, txt, color in [
            (6.0, "极度吸引",  "#1b8a3a"),
            (4.0, "高度吸引",  "#5cb85c"),
            (2.0, "吸引",      "#f0ad4e"),
            (0.0, "0% 中性",   "#888"),
        ]:
            if y_lo <= y <= y_hi:
                fig.add_hline(y=y, line_dash="dot", line_color=color, opacity=0.6,
                              annotation_text=f"{y:+.0f}% {txt}",
                              annotation_position="right",
                              annotation_font=dict(size=10, color=color))

        # 折线
        fig.add_trace(go.Scatter(
            x=df_win["date"], y=df_win["diff"],
            mode="lines", name="股债差",
            line=dict(color="#0d6efd", width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>股债差: %{y:.2f}%<extra></extra>",
        ))

        # 窗口中位数水平线
        fig.add_hline(y=win_med, line_dash="longdash", line_color="#666", opacity=0.5,
                      annotation_text=f"中位 {win_med:+.2f}%",
                      annotation_position="left",
                      annotation_font=dict(size=10, color="#666"))

        # 当前值水平线 + 大点
        fig.add_hline(y=graham_diff, line_dash="solid", line_color="#0d6efd",
                      opacity=0.85, line_width=1.5,
                      annotation_text=f"当前 {graham_diff:+.2f}%",
                      annotation_position="top left",
                      annotation_font=dict(size=12, color="#0d6efd"))
        fig.add_trace(go.Scatter(
            x=[df_win["date"].iloc[-1]], y=[graham_diff],
            mode="markers+text",
            text=[f"{graham_diff:+.2f}%"],
            textposition="middle right",
            marker=dict(size=14, color="#0d6efd",
                        line=dict(color="white", width=2)),
            showlegend=False,
            hoverinfo="skip",
        ))

        fig.update_layout(
            height=380, margin=dict(t=20, b=30, l=40, r=120),
            yaxis_title="股债差 (%)", xaxis_title="",
            yaxis=dict(range=[y_lo, y_hi], fixedrange=False),
            hovermode="x unified", showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            f"💡 当前 **{graham_diff:+.2f}%** 在 **{sel_label}内** 处于 "
            f"**{rank_pct*100:.1f}% 分位** · 评级 **{badge} {label}** · "
            "色带=阈值红绿灯 / 蓝实线=当前值 / 灰长虚线=窗口中位"
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
            st.markdown(f"**{ind['label']}**")
            st.markdown(
                f"<div style='font-size:24px;font-weight:700;line-height:1.1;color:#0d6efd'>"
                f"{ind['fmt'].format(cur)}</div>"
                f"<div style='font-size:11px;color:#888'>{cur_date}</div>"
                f"<div style='margin-top:4px;font-size:13px'>"
                f"<b>{cur_emoji} {cur_label}</b></div>",
                unsafe_allow_html=True,
            )
            meaning = ind.get("meaning", "")
            if meaning:
                st.caption(f"💡 {meaning}")
            if bands:
                st.markdown("<div style='font-size:12px;color:#666;margin-top:6px'>"
                            "<b>阈值红绿灯</b></div>", unsafe_allow_html=True)
                for b in bands:
                    is_cur = (b is cur_band)
                    style = ("font-weight:700;color:#000;background:#fff3cd;padding:1px 4px;"
                             "border-radius:3px") if is_cur else "color:#777"
                    st.markdown(
                        f"<div style='font-size:11px;{style};margin:1px 0'>"
                        f"{b['emoji']} {b['label']}{' ← 当前' if is_cur else ''}</div>",
                        unsafe_allow_html=True,
                    )

        with chart_col:
            fig = go.Figure()
            # 先画底层红绿灯阈值带(填充区域)
            y_min = float(df["value"].min())
            y_max = float(df["value"].max())
            for b in bands:
                lo = b.get("lo"); hi = b.get("hi")
                y0 = lo if lo is not None else (y_min - abs(y_min) * 0.2 - 1)
                y1 = hi if hi is not None else (y_max + abs(y_max) * 0.2 + 1)
                fig.add_hrect(
                    y0=y0, y1=y1,
                    fillcolor=b["fill"], opacity=0.10,
                    line_width=0, layer="below",
                )
                # 阈值边界横线(虚线)
                if lo is not None:
                    fig.add_hline(
                        y=lo, line_dash="dot", line_color=b["fill"],
                        opacity=0.55, line_width=1,
                    )
            # 折线
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["value"],
                mode="lines", name=ind["label"],
                line=dict(width=2.2, color="#0d6efd"),
                hovertemplate="%{x|%Y-%m-%d}<br>" + ind["label"] + ": %{y:.2f}<extra></extra>",
            ))
            # 当前点突出
            fig.add_trace(go.Scatter(
                x=[df.iloc[-1]["date"]], y=[cur],
                mode="markers",
                marker=dict(size=10, color="#0d6efd",
                            line=dict(color="white", width=2)),
                showlegend=False, hoverinfo="skip",
            ))
            fig.update_layout(
                height=210, margin=dict(t=10, b=20, l=30, r=10),
                showlegend=False,
                yaxis_title="", xaxis_title="",
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("<div style='border-bottom:1px dashed #e0e0e0;margin:8px 0 12px'></div>",
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

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["value"], name="A 股全指 PE",
        line=dict(color="#0d6efd", width=2),
    ))
    fig.add_hline(y=p80, line_dash="dot", line_color="#d9534f",
                  annotation_text=f"80% = {p80:.1f}")
    fig.add_hline(y=p50, line_dash="dash", line_color="#888",
                  annotation_text=f"50% = {p50:.1f}")
    fig.add_hline(y=p20, line_dash="dot", line_color="#1b8a3a",
                  annotation_text=f"20% = {p20:.1f}")
    fig.add_annotation(
        x=cur_date, y=cur, text=f"当前 {cur:.1f}<br>{pct*100:.0f}% 分位",
        showarrow=True, arrowhead=2, ax=-50, ay=-40,
        bgcolor="rgba(255,255,255,0.85)",
    )
    fig.update_layout(height=380, hovermode="x unified",
                      title=f"A 股全指 PE-TTM(市值加权)全周期分位带 · {verdict}")
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
    if len(args) == 1 and isinstance(args[0], (int, float)):
        db_mtime = float(args[0])
    elif len(args) >= 3 and isinstance(args[2], (int, float)):
        db_mtime = float(args[2])
    elif "db_mtime" in kwargs:
        db_mtime = float(kwargs["db_mtime"])
    elif DB_PATH.exists():
        db_mtime = DB_PATH.stat().st_mtime

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
