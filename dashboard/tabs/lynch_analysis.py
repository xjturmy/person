"""M6 彼得林奇分析法 · 5 步成长投资框架。

5 sub-tabs:
  ① 公司分类(六类判断)+ 故事脚本
  ② 成长核查(CAGR / 季度连续性 / 增长来源)
  ③ 财务护栏(高增长不烧钱)
  ④ PEG 估值(成长合理性)
  ⑤ 故事更新(每季 ping)

设计:
  - 复用 lynch_classifier(classify_ticker / load_metrics_from_db)
  - 类型驱动阈值:fast_grower 负债率 < 40% / stalwart < 50% / slow_grower < 60%
  - 故事脚本存 session_state,key 形如 lynch_story_{ticker}
  - 决策导出到 02_companies/{N}_{name}/05_投资决策/林奇五步分析_{date}.md

入口:
  from tabs.lynch_analysis import render
  render(companies, selected, db_mtime, folder_to_ticker_fn)
"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from datetime import timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
DB_PATH = ROOT / "data" / "preson.duckdb"
COMPANIES_DIR = ROOT / "02_companies"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from lynch_classifier import (  # noqa: E402
    CLASS_META, LYNCH_DIM_SCHEMA, ClassificationResult,
    QuarterlyContinuity,
    classify_ticker, compute_lynch_dims, load_metrics_from_db, overall_lynch,
    quarterly_continuity,
)


@st.cache_data(ttl=600, show_spinner=False)
def _quarterly_continuity_cached(ticker: str, db_mtime: float,
                                  n_quarters: int = 8) -> dict | None:
    """Streamlit 缓存层 — 内层调 lynch_classifier.quarterly_continuity 纯函数。

    返回 dict(可缓存,QuarterlyContinuity dataclass 不直接 cache 友好);
    上层 _step_2 调 _qc_from_dict 还原成 QuarterlyContinuity 用 fast_grower_pass 等方法。
    """
    if not ticker:
        return None
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        qc = quarterly_continuity(con, ticker, n_quarters=n_quarters)
    finally:
        con.close()
    return qc.to_dict() if qc and qc.n_quarters > 0 else None


def _qc_from_dict(d: dict | None) -> QuarterlyContinuity | None:
    if not d:
        return None
    return QuarterlyContinuity(
        series=[(s, float(y)) for s, y in d["series"]],
        n_quarters=d["n_quarters"],
        hits_20pct=d["hits_20pct"],
        hits_10pct=d["hits_10pct"],
        hits_0=d["hits_0"],
        latest_yoy=d["latest_yoy"],
        median_yoy=d["median_yoy"],
        source=d["source"],
    )


# ─── 类型驱动阈值表 ──────────────────────────────────────────────────────

GUARDRAIL_THRESHOLDS = {
    "fast_grower": {
        "debt_ratio_max":  0.40,    # 林奇铁律
        "current_ratio_min": 1.5,
        "cfo_to_ni_min":   1.0,
        "inv_days_max":    180,     # 库存周转天数(高速消费/扩张型不应囤货)
        "ar_days_max":     90,      # 应收账款周转(回款 ≤ 3 月)
        "label": "快速增长(林奇铁律)",
    },
    "stalwart": {
        "debt_ratio_max":  0.50,
        "current_ratio_min": 1.5,
        "cfo_to_ni_min":   0.9,
        "inv_days_max":    240,
        "ar_days_max":     90,
        "label": "稳健增长",
    },
    "slow_grower": {
        "debt_ratio_max":  0.60,
        "current_ratio_min": 1.2,
        "cfo_to_ni_min":   0.8,
        "inv_days_max":    300,
        "ar_days_max":     120,
        "label": "缓慢增长",
    },
    "cyclical": {
        "debt_ratio_max":  0.55,
        "current_ratio_min": 1.5,
        "cfo_to_ni_min":   0.7,
        "inv_days_max":    360,     # 周期股库存波动大,放宽
        "ar_days_max":     120,
        "label": "周期型",
    },
    "asset_play": {
        "debt_ratio_max":  0.50,
        "current_ratio_min": 1.5,
        "cfo_to_ni_min":   0.5,
        "inv_days_max":    None,    # 资产股关注资产质量,不卡库存
        "ar_days_max":     180,
        "label": "资产隐蔽",
    },
    "turnaround": {
        "debt_ratio_max":  0.65,
        "current_ratio_min": 1.0,
        "cfo_to_ni_min":   0.0,    # 经营现金流转正即可
        "inv_days_max":    360,    # 困境期库存常积压,放宽看趋势
        "ar_days_max":     150,
        "label": "困境反转",
    },
}

PEG_BY_TYPE = {
    "fast_grower":  {"target": 1.5, "applicable": True,  "note": "快速增长 PEG ≤ 1.5 合理"},
    "stalwart":     {"target": 1.0, "applicable": True,  "note": "稳健增长 PEG ≤ 1.0 是核心"},
    "slow_grower":  {"target": None, "applicable": False, "note": "缓慢增长不用 PEG,看股息率"},
    "cyclical":     {"target": None, "applicable": False, "note": "周期股 PE 反向解读,不用 PEG"},
    "asset_play":   {"target": None, "applicable": False, "note": "资产隐蔽看 NAV,不用 PEG"},
    "turnaround":   {"target": None, "applicable": False, "note": "困境反转 EPS 不稳,PEG 失真"},
}


# ─── 辅助函数 ────────────────────────────────────────────────────────────

def _section_banner(letter: str, emoji: str, title: str, subtitle: str = "",
                    color: str = "#0d6efd") -> None:
    """渲染步骤标题条(对照 M3 区块 banner 风格)。"""
    st.markdown(
        f'<div style="background: linear-gradient(90deg,{color} 0%, transparent 100%);'
        f'padding: 10px 14px; border-radius: 6px; margin: 12px 0 8px;'
        f'border-left: 4px solid {color};">'
        f'<span style="display:inline-block;background:white;color:{color};'
        f'padding:2px 8px;border-radius:10px;font-weight:700;font-size:13px;'
        f'margin-right:10px">{letter}</span>'
        f'<span style="font-size:17px;font-weight:700;color:white">{emoji} {title}</span>'
        + (f'<div style="font-size:12px;color:rgba(255,255,255,0.85);'
           f'margin-top:2px;margin-left:42px">{subtitle}</div>' if subtitle else '')
        + '</div>',
        unsafe_allow_html=True,
    )


def _badge_pill(label: str, color: str) -> str:
    return (f'<span style="background:{color};color:white;padding:3px 10px;'
            f'border-radius:12px;font-size:13px;font-weight:600">{label}</span>')


def _confidence_color(conf: float) -> str:
    return "#1b8a3a" if conf >= 0.80 else "#f0ad4e" if conf >= 0.60 else "#d9534f"


@st.cache_data(ttl=600, show_spinner=False)
def _classify_cached(ticker: str, db_mtime: float) -> dict | None:
    """缓存分类结果(随 DuckDB mtime 失效)。"""
    if not ticker:
        return None
    try:
        r = classify_ticker(ticker)
        return r.to_dict()
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _metrics_cached(ticker: str, db_mtime: float) -> dict | None:
    if not ticker:
        return None
    try:
        return load_metrics_from_db(ticker)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _deduct_metrics(ticker: str, db_mtime: float) -> dict:
    """从 non_recurring_items 表读取扣非数据(2026-05-06 P3 后续解锁,sina IS 派生)。

    返回最近 4 季的关键指标:
        latest_dnp_to_np_ratio  扣非/归母 占比(用于"利润质量"判别)
        latest_dnp_yoy          最近一期累计扣非 yoy(单期同比)
        np_yoy_recent           归母同期累计 yoy(从 growth 表读)
        single_q_dnp_yoy_8q     近 8 季单季扣非同比 DataFrame
    """
    if not ticker:
        return {}
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            tabs = {r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()}
            if "non_recurring_items" not in tabs:
                return {}

            ratio_row = con.execute(
                """
                SELECT date, value FROM non_recurring_items
                WHERE ticker = ? AND metric = 'dnp_to_np_ratio'
                ORDER BY date DESC LIMIT 1
                """,
                [ticker],
            ).fetchone()

            dnp_yoy_row = con.execute(
                """
                SELECT date, value FROM non_recurring_items
                WHERE ticker = ? AND metric = 'dnp_yoy'
                ORDER BY date DESC LIMIT 1
                """,
                [ticker],
            ).fetchone()

            quarterly_rows = con.execute(
                """
                SELECT date, value FROM non_recurring_items
                WHERE ticker = ? AND metric = 'single_q_dnp_yoy'
                ORDER BY date DESC LIMIT 8
                """,
                [ticker],
            ).fetchall()
        finally:
            con.close()
    except Exception:
        return {}

    out = {}
    if ratio_row:
        out["dnp_to_np_ratio"] = float(ratio_row[1])
        out["dnp_to_np_date"] = str(ratio_row[0])
    if dnp_yoy_row:
        out["dnp_yoy_recent"] = float(dnp_yoy_row[1])
    if quarterly_rows:
        df = pd.DataFrame(quarterly_rows, columns=["date", "yoy"])
        df["date"] = pd.to_datetime(df["date"])
        out["single_q_dnp_yoy_8q"] = df.sort_values("date").reset_index(drop=True)
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _company_category(ticker: str, db_mtime: float) -> str:
    """读 companies.category(non_financial / bank / insurance / hk),失败返回空串。"""
    if not ticker:
        return ""
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            r = con.execute(
                "SELECT category FROM companies WHERE ticker = ?", [ticker]
            ).fetchone()
            return (r[0] or "") if r else ""
        finally:
            con.close()
    except Exception:
        return ""


# 林奇五步在不同行业的"层 3 增长来源"适用性。
# 层 3 关注:销量 vs 提价拆解 / 海外占比 / 市占率 — 这些指标对金融业不成立。
LAYER3_INDUSTRY_NA = {
    "bank": (
        "🏦 行业不适用 — 银行业核心驱动是 NIM/规模/不良率,不存在'销量 vs 提价'拆解;"
        "海外占比对国有大行/股份行通常 <5%,无信息量;"
        "市占率以贷款余额衡量,见 [reference] 银保监披露"
    ),
    "insurance": (
        "🏥 行业不适用 — 保险业核心驱动是 NBV/EV/续期率,而非销量提价;"
        "新华/平安等大型寿险均为纯国内业务;"
        "市占率按保费收入衡量,行业 CR5≈80%"
    ),
}


@st.cache_data(ttl=600, show_spinner=False)
def _quarterly_yoy(ticker: str, db_mtime: float, n_quarters: int = 8) -> pd.DataFrame:
    """近 N 季单季营收 YoY。

    数据源策略(2026-05-06):
    1. 优先取 growth 表 '同比' 字段(若理杏仁后续补回)
    2. 否则从 '营业收入' 累计值派生:单季 = 累计本季 - 累计上季(Q1 直接用累计),
       然后 单季同比 = 单季今年 / 单季去年同期 - 1
    """
    if not ticker:
        return pd.DataFrame()
    cutoff = (_date_cls.today() - timedelta(days=365 * 5)).isoformat()  # 多取 2 年作 yoy 锚
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # ---- 路径 1: 直接取 '同比' ----
        rows = con.execute(
            """
            SELECT date, value FROM growth
            WHERE ticker = ? AND metric = '同比' AND value IS NOT NULL
                  AND date >= ?
            ORDER BY date DESC LIMIT ?
            """,
            [ticker, cutoff, n_quarters],
        ).fetchall()
        if rows:
            df = pd.DataFrame(rows, columns=["date", "yoy"])
            df["date"] = pd.to_datetime(df["date"])
            return df.sort_values("date")

        # ---- 路径 2: 从累计营收派生单季同比 ----
        rev_rows = con.execute(
            """
            SELECT date, value FROM growth
            WHERE ticker = ? AND metric = '营业收入' AND value IS NOT NULL
                  AND date >= ?
            ORDER BY date ASC
            """,
            [ticker, cutoff],
        ).fetchall()
    except Exception:
        rev_rows = []
    finally:
        con.close()

    if not rev_rows:
        return pd.DataFrame()

    rev = pd.DataFrame(rev_rows, columns=["date", "cum_revenue"])
    rev["date"] = pd.to_datetime(rev["date"])
    rev["year"] = rev["date"].dt.year
    rev["quarter"] = rev["date"].dt.month // 3  # 3->1 / 6->2 / 9->3 / 12->4

    # 单季 = 累计本季 - 累计上季(同年内);Q1 直接用累计
    rev = rev.sort_values(["year", "quarter"]).reset_index(drop=True)
    rev["prev_cum"] = rev.groupby("year")["cum_revenue"].shift(1)
    rev["single_q"] = rev["cum_revenue"] - rev["prev_cum"].fillna(0)

    # yoy:同 quarter 上一年单季对齐
    rev["prev_year_single"] = rev.groupby("quarter")["single_q"].shift(1)
    rev["yoy"] = (rev["single_q"] / rev["prev_year_single"] - 1).where(
        rev["prev_year_single"].abs() > 1e-6
    )

    out = rev.dropna(subset=["yoy"])[["date", "yoy"]].tail(n_quarters)
    return out.sort_values("date").reset_index(drop=True)


# ─── 自动故事 + 关键指标分析(基于财报数据) ─────────────────────────────

def _fmt_pct(x: float | None, decimals: int = 1) -> str:
    return "—" if x is None else f"{x*100:.{decimals}f}%"


def _fmt_num(x: float | None, decimals: int = 1) -> str:
    return "—" if x is None else f"{x:.{decimals}f}"


def derive_key_indicators(m: dict, cls_id: str) -> list[dict]:
    """根据类型生成"类型核心指标卡"(数值 + 类型基线 + 解读 + 状态)。

    每个指标返回 dict:{label, value, baseline, status, reading}
    status: ✅ / 🟡 / 🔴 / ⚪
    """
    rows: list[dict] = []

    def _row(label, value, baseline, status, reading):
        rows.append({
            "指标": label, "数值": value, "类型基线": baseline,
            "状态": status, "解读": reading,
        })

    # ─── 通用财务数据点 ────────────────────────────────────
    rev_5y = m.get("rev_cagr_5y")
    rev_3y = m.get("rev_cagr_3y")
    np_yoy = m.get("np_yoy_recent")
    rev_yoy = m.get("rev_yoy_recent")
    roe = m.get("roe")
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    debt = m.get("debt_ratio")
    div = m.get("dividend_yield")
    pe_pct = m.get("pe_pct_10y")

    if cls_id == "fast_grower":
        # 快速增长型核心指标:CAGR / 季度连续 / ROE / 负债率(铁律) / PEG
        if rev_5y is not None:
            status = "✅" if rev_5y >= 0.25 else ("🟡" if rev_5y >= 0.15 else "🔴")
            note = "高速扩张" if rev_5y >= 0.25 else "增长稳定" if rev_5y >= 0.15 else "增速不达标"
            _row("营收 5y CAGR", _fmt_pct(rev_5y), "≥ 25%(优 ≥ 35%)", status, note)
        if np_yoy is not None:
            status = "✅" if np_yoy >= 0.20 else ("🟡" if np_yoy >= 0 else "🔴")
            _row("最新净利 YoY", _fmt_pct(np_yoy), "≥ 20%", status,
                 "仍加速" if np_yoy > 0.30 else "稳" if np_yoy > 0 else "下滑")
        if roe is not None:
            status = "✅" if roe >= 0.15 else ("🟡" if roe >= 0.10 else "🔴")
            _row("ROE", _fmt_pct(roe), "≥ 15%(高质量内生)", status,
                 "强" if roe >= 0.20 else "良" if roe >= 0.12 else "弱")
        if debt is not None:
            status = "✅" if debt <= 0.40 else ("🟡" if debt <= 0.50 else "🔴")
            _row("资产负债率", _fmt_pct(debt), "< 40%(林奇铁律)", status,
                 "内生增长" if debt <= 0.40 else "边缘" if debt <= 0.50 else "加杠杆撑场")
        if pe and rev_3y and rev_3y > 0:
            peg = pe / (rev_3y * 100)
            status = "✅" if peg < 1.0 else ("🟡" if peg < 1.5 else "🔴")
            _row("PEG", _fmt_num(peg, 2), "< 1.5(快速放宽)", status,
                 "便宜" if peg < 1 else "合理" if peg < 1.5 else "贵")

    elif cls_id == "stalwart":
        # 稳健:ROE 持续 / CAGR 中速 / PEG ≤ 1 / 股息 / 现金流
        if roe is not None:
            status = "✅" if roe >= 0.15 else ("🟡" if roe >= 0.12 else "🔴")
            _row("ROE", _fmt_pct(roe), "持续 ≥ 15%", status,
                 "压舱石" if roe >= 0.20 else "稳" if roe >= 0.15 else "退化中")
        if rev_5y is not None:
            status = "✅" if 0.10 <= rev_5y <= 0.20 else ("🟡" if rev_5y >= 0.05 else "🔴")
            _row("营收 5y CAGR", _fmt_pct(rev_5y), "10-20%", status,
                 "稳健成长" if 0.10 <= rev_5y <= 0.20 else "偏快(留意降速)" if rev_5y > 0.20
                 else "偏慢")
        if pe and rev_3y and rev_3y > 0:
            peg = pe / (rev_3y * 100)
            status = "✅" if peg <= 1.0 else ("🟡" if peg <= 1.3 else "🔴")
            _row("PEG", _fmt_num(peg, 2), "≤ 1.0(稳健核心)", status,
                 "理想" if peg <= 1 else "略贵" if peg <= 1.3 else "估值透支")
        if div is not None:
            status = "✅" if div >= 0.025 else ("🟡" if div >= 0.015 else "⚪")
            _row("股息率", _fmt_pct(div, 2), "≥ 2.5%(辅助回报)", status,
                 "稳定回报" if div >= 0.03 else "偏低")
        if debt is not None:
            status = "✅" if debt <= 0.50 else ("🟡" if debt <= 0.60 else "🔴")
            _row("资产负债率", _fmt_pct(debt), "< 50%", status, "稳健")

    elif cls_id == "slow_grower":
        # 缓慢:股息率主导 / 负债率低 / ROE 稳 / 不看 PEG
        if div is not None:
            status = "✅" if div >= 0.04 else ("🟡" if div >= 0.025 else "🔴")
            _row("股息率", _fmt_pct(div, 2), "≥ 4%(核心持有理由)", status,
                 "高股息" if div >= 0.04 else "中等" if div >= 0.025 else "失去持有意义")
        if pe is not None:
            status = "✅" if pe <= 12 else ("🟡" if pe <= 18 else "🔴")
            _row("PE-TTM", _fmt_num(pe), "≤ 12", status,
                 "便宜" if pe <= 12 else "中性" if pe <= 18 else "贵")
        if roe is not None:
            status = "✅" if roe >= 0.10 else ("🟡" if roe >= 0.07 else "🔴")
            _row("ROE", _fmt_pct(roe), "稳定 ≥ 10%", status, "稳定" if roe >= 0.10 else "弱")
        if debt is not None:
            status = "✅" if debt <= 0.50 else ("🟡" if debt <= 0.60 else "🔴")
            _row("资产负债率", _fmt_pct(debt), "< 50%", status, "稳" if debt <= 0.50 else "高")
        if rev_5y is not None:
            status = "✅" if rev_5y >= 0 else "🔴"
            _row("营收 5y CAGR", _fmt_pct(rev_5y), "0-10%(避免负增长)", status,
                 "稳" if 0 <= rev_5y <= 0.10 else "偏快" if rev_5y > 0.10 else "衰退")

    elif cls_id == "cyclical":
        # 周期:PE 反向 / PB 位置 / 营收 YoY 方向 / 负债率
        if pb is not None:
            status = "✅" if pb < 1.5 else ("🟡" if pb < 2.5 else "🔴")
            _row("PB", _fmt_num(pb, 2), "< 1.5(底部)", status,
                 "周期底部" if pb < 1 else "下行段" if pb < 1.5 else "中性" if pb < 2.5 else "顶部信号")
        if pe is not None:
            _row("PE-TTM(反向解读)", _fmt_num(pe), "高 PE = 低谷,低 PE = 顶部", "🟡",
                 "周期顶部信号" if pe < 8 else "正常段" if pe < 25 else "可能是底部")
        if rev_yoy is not None:
            status = "✅" if rev_yoy > 0 else "🔴"
            _row("最新营收 YoY", _fmt_pct(rev_yoy), "正 = 周期上行", status,
                 "上行确认" if rev_yoy > 0.10 else "拐点" if rev_yoy > 0 else "下行")
        if debt is not None:
            status = "✅" if debt <= 0.55 else "🟡"
            _row("资产负债率", _fmt_pct(debt), "< 55%(扛周期能力)", status,
                 "可扛" if debt <= 0.55 else "脆弱")

    elif cls_id == "turnaround":
        if np_yoy is not None:
            _row("净利 YoY", _fmt_pct(np_yoy), "—", "🔴" if np_yoy < -0.30 else "🟡",
                 "重度下滑" if np_yoy < -0.30 else "下滑")
        if rev_yoy is not None:
            status = "✅" if rev_yoy > 0 else "🔴"
            _row("营收 YoY", _fmt_pct(rev_yoy), "正 = 反转启动", status,
                 "已企稳" if rev_yoy > 0 else "仍恶化")
        if roe is not None:
            status = "✅" if roe > 0.05 else "🔴"
            _row("ROE", _fmt_pct(roe), "> 0(没出局)", status,
                 "已恢复" if roe > 0.10 else "刚触底" if roe > 0 else "未触底")
        if debt is not None:
            status = "✅" if debt <= 0.65 else "🔴"
            _row("资产负债率", _fmt_pct(debt), "< 65%(防破产)", status,
                 "可控" if debt <= 0.65 else "高危")

    elif cls_id == "asset_play":
        cash_mc = m.get("cash_to_market_cap")
        if cash_mc is not None:
            status = "✅" if cash_mc >= 0.30 else "🟡"
            _row("现金/市值", _fmt_pct(cash_mc), "≥ 30%", status,
                 "深度低估" if cash_mc >= 0.40 else "低估")
        else:
            _row("现金/市值", "—", "≥ 30%", "⚪", "数据未装配,需手补")
        if pb is not None:
            status = "✅" if pb < 1 else "🟡"
            _row("PB", _fmt_num(pb, 2), "< 1(NAV 折价)", status,
                 "折价" if pb < 1 else "无折价")
        if div is not None:
            _row("股息率", _fmt_pct(div, 2), "—", "—",
                 "等催化" + (",有股息缓冲" if div > 0.03 else ""))

    # 估值分位(通用,所有类型都加上)
    if pe_pct is not None:
        status = "✅" if pe_pct < 0.30 else ("🟡" if pe_pct < 0.70 else "🔴")
        _row("PE 10y 分位", _fmt_pct(pe_pct), "—", status,
             "历史低位" if pe_pct < 0.30 else "中性" if pe_pct < 0.70 else "历史高位")

    return rows


def derive_story(m: dict, cls: ClassificationResult, cls_id: str,
                 industry: str = "") -> dict:
    """基于财报数据自动生成故事三段:oneline / evidence / not_happen。

    用户可在此基础上编辑(预填到 text_area)。
    """
    rev_5y = m.get("rev_cagr_5y")
    rev_3y = m.get("rev_cagr_3y")
    np_yoy = m.get("np_yoy_recent")
    rev_yoy = m.get("rev_yoy_recent")
    roe = m.get("roe")
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    debt = m.get("debt_ratio")
    div = m.get("dividend_yield")
    pe_pct = m.get("pe_pct_10y")
    name = m.get("name", "")
    industry = industry or m.get("industry_sw_l1", "") or "目标"

    oneline = ""
    evidences: list[str] = []
    not_happen = ""

    if cls_id == "fast_grower":
        # 一句话:行业 + 增速 + ROE
        cagr_str = _fmt_pct(rev_5y) if rev_5y else "—"
        roe_str = _fmt_pct(roe) if roe else "—"
        oneline = f"{industry}行业扩张期,{name} 以 5y 营收 CAGR {cagr_str} + ROE {roe_str} 抢占份额,渗透率仍在上升"

        if rev_5y and rev_5y >= 0.25:
            evidences.append(f"• 营收 5y CAGR {_fmt_pct(rev_5y)}(高速扩张,远超 GDP 增速)")
        if np_yoy and np_yoy > 0.20:
            evidences.append(f"• 最新净利润 YoY +{np_yoy*100:.1f}%(利润增长仍在加速)")
        if roe and roe >= 0.15:
            evidences.append(f"• ROE {_fmt_pct(roe)}(资本效率高,内生增长非靠加杠杆)")
        if debt is not None and debt <= 0.40:
            evidences.append(f"• 资产负债率 {_fmt_pct(debt)}(< 40% 林奇铁律,扩张未透支)")

        not_happen = (
            f"林奇式买入逻辑失效信号:\n"
            f"• 资产负债率突破 50% — 说明扩张靠加杠杆,故事破裂\n"
            f"• 连续 2 季单季营收 YoY < 20% — 增速断档,十倍股逻辑终结\n"
            f"• PEG > 2 — 估值透支未来 3 年,需减仓"
        )

    elif cls_id == "stalwart":
        cagr_str = _fmt_pct(rev_5y) if rev_5y else "—"
        roe_str = _fmt_pct(roe) if roe else "—"
        oneline = f"{industry}龙头,{name} 以稳定 ROE {roe_str} + 营收 CAGR {cagr_str} 形成压舱石型护城河"

        if roe and roe >= 0.15:
            evidences.append(f"• ROE {_fmt_pct(roe)}(持续 ≥ 15%,定价权 + 资本效率双高)")
        if rev_5y and 0.10 <= rev_5y <= 0.25:
            evidences.append(f"• 营收 5y CAGR {_fmt_pct(rev_5y)}(稳健 10-20% 区间,可持续)")
        if div and div >= 0.025:
            evidences.append(f"• 股息率 {_fmt_pct(div, 2)}(稳定分红 + 资本回报组合)")
        if debt is not None and debt <= 0.50:
            evidences.append(f"• 资产负债率 {_fmt_pct(debt)}(财务结构稳)")

        not_happen = (
            f"压舱石资格丢失信号:\n"
            f"• ROE 跌破 15% — 护城河被侵蚀,降级为 slow_grower\n"
            f"• 营收 CAGR 跌破 8% — 退化为缓慢增长\n"
            f"• PEG > 1.3 — 失去稳健成长股的估值优势"
        )

    elif cls_id == "slow_grower":
        div_str = _fmt_pct(div, 2) if div else "—"
        pe_str = _fmt_num(pe) if pe else "—"
        oneline = f"成熟期 {industry} 公司,{name} 主要靠 {div_str} 股息率 + 稳定 PE {pe_str} 提供长期回报"

        if div and div >= 0.04:
            evidences.append(f"• 股息率 {_fmt_pct(div, 2)}(≥ 4%,核心持有理由)")
        if pe and pe <= 12:
            evidences.append(f"• PE-TTM {pe:.1f}(低于 12 倍,估值便宜)")
        if roe and roe >= 0.10:
            evidences.append(f"• ROE {_fmt_pct(roe)}(稳定盈利能力)")
        if debt and debt <= 0.50:
            evidences.append(f"• 资产负债率 {_fmt_pct(debt)}(经营稳健,不靠杠杆)")

        not_happen = (
            f"持有理由消失信号:\n"
            f"• 股息率跌破 3% — 失去主要回报来源\n"
            f"• 营收 5y CAGR 转负 — 进入衰退,不再是缓慢成长\n"
            f"• 资产负债率突破 60% — 现金流恶化"
        )

    elif cls_id == "cyclical":
        pe_str = _fmt_num(pe) if pe else "—"
        pb_str = _fmt_num(pb, 2) if pb else "—"
        rev_dir = "上行" if rev_yoy and rev_yoy > 0 else "下行" if rev_yoy and rev_yoy < 0 else "拐点"
        oneline = f"{industry} 周期股,当前 PE {pe_str} / PB {pb_str},营收 {rev_dir}阶段(周期股 PE 反向解读)"

        if pb is not None:
            note = "周期底部" if pb < 1 else "下行段尾部" if pb < 1.5 else "中性"
            evidences.append(f"• PB {pb:.2f}({note})")
        if rev_yoy is not None:
            evidences.append(f"• 最新营收 YoY {_fmt_pct(rev_yoy)}({'上行确认' if rev_yoy > 0.10 else '下行'})")
        if pe is not None:
            evidences.append(f"• PE {pe:.1f}({'高 PE 是低谷信号' if pe > 25 else '低 PE 警惕周期顶部' if pe < 8 else '正常周期段'})")
        if debt is not None:
            evidences.append(f"• 资产负债率 {_fmt_pct(debt)}({'扛得住周期' if debt <= 0.55 else '脆弱'})")

        not_happen = (
            f"周期反转/卖出信号:\n"
            f"• PE 进入历史低位(< 8)— 经典周期顶部信号\n"
            f"• 营收 YoY 持续转负 — 周期下行确认\n"
            f"• 库存/产能利用率恶化 — 主动减仓"
        )

    elif cls_id == "turnaround":
        oneline = f"{name} 处于困境反转候选,净利 YoY {_fmt_pct(np_yoy)},关键看现金流和催化"
        if np_yoy is not None and np_yoy < -0.30:
            evidences.append(f"• 净利 YoY {_fmt_pct(np_yoy)}(大幅下滑,反转空间大)")
        if rev_yoy is not None:
            evidences.append(f"• 营收 YoY {_fmt_pct(rev_yoy)}({'已企稳' if rev_yoy > 0 else '仍恶化'})")
        if roe is not None:
            evidences.append(f"• ROE {_fmt_pct(roe)}({'已恢复' if roe > 0.10 else '刚触底' if roe > 0 else '未触底'})")
        not_happen = (
            f"反转失败信号:\n"
            f"• 经营性现金流持续转负 — 倒闭风险\n"
            f"• 营收持续下滑超过 1 年 — 反转故事破裂\n"
            f"• 管理层无清晰转型动作 — 只是衰退,非反转"
        )

    elif cls_id == "asset_play":
        cash_mc = m.get("cash_to_market_cap")
        oneline = f"{name} 资产隐蔽型,{('现金/市值 ' + _fmt_pct(cash_mc)) if cash_mc else '资产被低估'},等待催化重估"
        if cash_mc is not None and cash_mc >= 0.30:
            evidences.append(f"• 现金/市值 {_fmt_pct(cash_mc)}(净现金占比极高)")
        if pb is not None and pb < 1:
            evidences.append(f"• PB {pb:.2f}(< 1,NAV 折价)")
        if div is not None and div > 0.03:
            evidences.append(f"• 股息率 {_fmt_pct(div, 2)}(等催化期间有现金回报)")
        not_happen = (
            f"价值陷阱信号:\n"
            f"• 等不到催化(回购/分红/分拆)— 沦为价值陷阱\n"
            f"• 管理层挥霍现金 — 资产价值流失\n"
            f"• 主营业务持续恶化 — 资产无人接盘"
        )

    return {
        "oneline": oneline,
        "evidence": "\n".join(evidences) if evidences else "(数据不足以自动生成证据)",
        "not_happen": not_happen,
    }


# ─── 步骤渲染 ────────────────────────────────────────────────────────────

def _render_type_editor(ticker: str, cls: ClassificationResult) -> tuple[str, str, int]:
    """🏷️ 类型编辑器 — 主类型 + 次类型 + 主类型权重。

    返回 (primary_id, secondary_id 或 '', primary_weight 50-100)。
    某些公司具有双特征(如 周期+快速增长),用权重表达倾向性。
    若 cls.extra 含 suggest_split_secondary,会作为次类型默认值(用户首次进入时)。
    """
    # 顶部:auto badge
    conf_color = _confidence_color(cls.confidence)
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:14px;margin-bottom:8px'>"
        f"<span style='font-size:30px;line-height:1'>{cls.cls_emoji}</span>"
        f"<span style='font-size:17px;font-weight:600'>"
        f"自动判定:{cls.cls_name}</span>"
        f"{_badge_pill(f'置信度 {cls.confidence*100:.0f}%', conf_color)}"
        f"</div>",
        unsafe_allow_html=True,
    )

    extra = getattr(cls, "extra", {}) or {}

    # ─── 林奇 6 类不完美匹配 警告 banner ─────────────────────────────
    if extra.get("lynch_six_class_misfit"):
        ind_l2 = extra.get("industry_l2") or ""
        proper_method = (
            "内含价值法(EV)+ 新业务价值(NBV)+ 投资收益率分解" if ind_l2 == "保险"
            else "拨备覆盖率 + 净息差 + 不良率周期" if ind_l2 == "银行"
            else "自营 / 经纪 / 投行 分部估值 + 净资本充足率" if ind_l2 == "证券"
            else "行业专属估值法"
        )
        st.warning(
            f"⚠️ **林奇 6 类不完美适用** — 该公司行业「{ind_l2}」核心估值口径是 "
            f"**{proper_method}**,而非 PEG / PB。\n\n"
            f"林奇分类作为辅助框架仍有意义,但请配合行业专属指标使用。"
            + (
                f"\n\n📊 **检测到金融周期信号**:5y 净利率 CV "
                f"{extra.get('net_margin_cv', 0)*100:.0f}% > 30%,"
                "盈利随利率/资本市场剧烈波动。"
                if extra.get("net_margin_cv") and extra["net_margin_cv"] > 0.30
                else ""
            ),
            icon="📐",
        )

    # ─── 主次拆分推荐 ──────────────────────────────────────────────────
    suggest_secondary = extra.get("suggest_split_secondary", "")
    suggest_weight = extra.get("suggest_split_weight", 70)
    if suggest_secondary and suggest_secondary in CLASS_META:
        sec_emoji = CLASS_META[suggest_secondary][1]
        sec_name = CLASS_META[suggest_secondary][0]
        st.info(
            f"💡 **建议主次拆分**:此公司具有双特征 — "
            f"主 {cls.cls_emoji} {cls.cls_name} ({suggest_weight}%) + "
            f"次 {sec_emoji} {sec_name} ({100-suggest_weight}%) · "
            f"在下方「次类型」处可选,或保持单一类型(将仅用主类型评分)。",
            icon="🎯",
        )

    type_options = list(CLASS_META.keys())
    sec_widget_key = f"lynch_sec_{ticker}"
    weight_widget_key = f"lynch_weight_{ticker}"
    init_key = f"lynch_type_editor_init_{ticker}"

    # 首次访问该 ticker 编辑器:把推荐次类型直接预设进 widget state
    # (streamlit 的 selectbox 一旦绑定 key,index 参数对后续 reload 无效)
    if init_key not in st.session_state:
        if suggest_secondary and suggest_secondary in type_options:
            st.session_state[sec_widget_key] = suggest_secondary
            st.session_state[weight_widget_key] = suggest_weight
        st.session_state[init_key] = True

    col_p, col_w, col_s = st.columns([2, 2, 2])

    with col_p:
        idx = type_options.index(cls.cls_id) if cls.cls_id in type_options else 0
        primary = st.selectbox(
            "🥇 主类型(可编辑)",
            options=type_options,
            index=idx,
            format_func=lambda x: f"{CLASS_META[x][1]} {CLASS_META[x][0]}",
            key=f"lynch_primary_{ticker}",
        )

    with col_s:
        sec_options = ["(无 · 单一类型)"] + [t for t in type_options if t != primary]
        # 不传 index — selectbox 自动从 session_state[sec_widget_key] 取
        # 但 session_state 里的值如果不在 options 里(如选了主类型 = 之前的次类型),会出错
        # 所以做一次校验
        cur_sec_state = st.session_state.get(sec_widget_key)
        if cur_sec_state and cur_sec_state not in sec_options:
            st.session_state[sec_widget_key] = sec_options[0]  # 重置为 "无"

        # 首次渲染需要 index;之后 selectbox 会忽略 index 用 session_state
        if sec_widget_key not in st.session_state:
            sec_default_idx = (
                sec_options.index(suggest_secondary)
                if (suggest_secondary and suggest_secondary in sec_options)
                else 0
            )
            secondary_pick = st.selectbox(
                "🥈 次类型(双特征公司)",
                options=sec_options,
                index=sec_default_idx,
                format_func=lambda x: x if x.startswith("(") else f"{CLASS_META[x][1]} {CLASS_META[x][0]}",
                key=sec_widget_key,
                help="例:比亚迪 = 周期型 + 快速增长 双特征。无此场景选'单一类型'",
            )
        else:
            secondary_pick = st.selectbox(
                "🥈 次类型(双特征公司)",
                options=sec_options,
                format_func=lambda x: x if x.startswith("(") else f"{CLASS_META[x][1]} {CLASS_META[x][0]}",
                key=sec_widget_key,
                help="例:比亚迪 = 周期型 + 快速增长 双特征。无此场景选'单一类型'",
            )
        secondary = "" if (not secondary_pick or secondary_pick.startswith("(")) else secondary_pick

    with col_w:
        if secondary:
            if weight_widget_key not in st.session_state:
                default_weight = suggest_weight if (suggest_secondary == secondary) else 70
                weight = st.slider(
                    "🥇 主类型权重 %",
                    min_value=50, max_value=95, value=default_weight, step=5,
                    key=weight_widget_key,
                    help="50% = 双特征对半;80% = 主导明显;95% = 接近单一",
                )
            else:
                weight = st.slider(
                    "🥇 主类型权重 %",
                    min_value=50, max_value=95, step=5,
                    key=weight_widget_key,
                    help="50% = 双特征对半;80% = 主导明显;95% = 接近单一",
                )
        else:
            weight = 100
            st.caption("权重 100%(单一类型)")

    st.session_state[f"lynch_secondary_{ticker}"] = secondary
    st.session_state[f"lynch_type_{ticker}"] = primary

    # 综合定位描述(banner)
    if secondary:
        st.success(
            f"📌 **综合定位**:{CLASS_META[primary][1]} {CLASS_META[primary][0]}({weight}%)"
            f" + {CLASS_META[secondary][1]} {CLASS_META[secondary][0]}({100-weight}%)"
            f" — 双特征叠加",
            icon="🎯",
        )
    elif primary != cls.cls_id:
        st.warning(
            f"⚠️ 已手动覆盖:{CLASS_META[cls.cls_id][1]} {CLASS_META[cls.cls_id][0]}"
            f" → {CLASS_META[primary][1]} {CLASS_META[primary][0]}",
            icon="✏️",
        )

    return primary, secondary, weight


def _step_1_classification(ticker: str, cls: ClassificationResult, m: dict,
                           folder: str) -> None:
    """① 公司分类 + 故事脚本(新版三段式:类型编辑器 → 自动理由 → 核心指标 → 故事)。"""
    _section_banner("①", "🔍", "公司分类(决定后续四步用什么口径)",
                    "林奇核心:先定性,后定量 — 误判 = 灾难", color="#0d6efd")

    # 📖 林奇六类速读
    with st.expander("📖 林奇六类公司速读(展开看)", expanded=False):
        for cid, (cn_name, emoji, desc) in CLASS_META.items():
            highlight = "**" if cid == cls.cls_id else ""
            st.markdown(f"- {highlight}{emoji} **{cn_name}**{highlight} — {desc}")

    # ─── 🧭 公司类型判断(类型编辑 + 自动分析理由 + 林奇视角提示 合并)────
    st.markdown("#### 🧭 公司类型判断")
    st.caption(
        "默认采用自动判定;若公司具有双特征(如 周期+快速增长),"
        "可调整主/次类型与权重 · 自动分析理由见下方框。"
    )
    primary, secondary, weight = _render_type_editor(ticker, cls)
    cls_id_used = primary

    # 自动分析理由 + 林奇视角提示 合并到一个 bordered container,贴紧上方编辑器
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
            f"letter-spacing:0.04em;margin-bottom:4px'>🤖 自动分析理由</div>"
            f"<div style='font-size:13px;color:#374151;line-height:1.55'>"
            f"{cls.reason}</div>",
            unsafe_allow_html=True,
        )
        if cls.notes:
            notes_html = "".join(
                f"<li style='margin:2px 0;color:#374151;font-size:13px;line-height:1.5'>{n}</li>"
                for n in cls.notes
            )
            st.markdown(
                f"<div style='border-top:1px dashed #E5E7EB;margin-top:8px;padding-top:6px'>"
                f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
                f"letter-spacing:0.04em;margin-bottom:3px'>💡 林奇视角提示</div>"
                f"<ul style='margin:0;padding-left:18px'>{notes_html}</ul></div>",
                unsafe_allow_html=True,
            )

    # ─── 🔑 核心指标分析(再接着的是关键数据)──────────────────────────
    st.divider()
    st.markdown(
        f"#### 🔑 核心指标分析 · {CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]}"
        + (f" 主导({weight}%)" if secondary else "")
    )
    st.caption("基于财报数据自动计算,按主类型阈值标注 ✅/🟡/🔴")

    indicator_rows = derive_key_indicators(m, cls_id_used)
    if indicator_rows:
        idf = pd.DataFrame(indicator_rows)

        def _style_status(v):
            if v == "✅": return "background-color:#d4edda; font-weight:600"
            if v == "🟡": return "background-color:#fff3cd; font-weight:600"
            if v == "🔴": return "background-color:#f8d7da; font-weight:600"
            return ""

        styler = idf.style.map(_style_status, subset=["状态"])
        st.dataframe(styler, use_container_width=True, hide_index=True)
    else:
        st.caption("(数据不足以派生核心指标)")

    # 双特征:展开看次类型关键指标
    if secondary and weight < 90:
        sec_label = f"📋 次类型视角:{CLASS_META[secondary][1]} {CLASS_META[secondary][0]} ({100-weight}%)关键指标"
        with st.expander(sec_label, expanded=False):
            st.caption(f"如果按 **{CLASS_META[secondary][0]}** 视角看,这家公司的关键指标如下:")
            sec_rows = derive_key_indicators(m, secondary)
            if sec_rows:
                sdf = pd.DataFrame(sec_rows[:5])
                sec_styler = sdf.style.map(_style_status, subset=["状态"])
                st.dataframe(sec_styler, use_container_width=True, hide_index=True)

    # ─── 📝 故事脚本(自动派生 + 用户编辑)─────────────────────────────
    st.divider()
    st.markdown("#### 📝 故事脚本(自动从财报派生,可编辑)")
    st.caption("林奇:'如果你不能用三句话讲清楚为什么买它,就别买。' 下面三段先由系统从财报自动总结,你再编辑。")

    industry = m.get("industry_sw_l1", "") or ""
    auto_story = derive_story(m, cls, cls_id_used, industry=industry)

    # 双特征:在 oneline 末尾标注次类型 + 在 not_happen 末尾追加次类型卖出信号
    if secondary and weight < 90:
        sec_emoji = CLASS_META[secondary][1]
        sec_name = CLASS_META[secondary][0]
        auto_story["oneline"] = (
            f"{auto_story['oneline']} · 同时具有 {sec_emoji} {sec_name}"
            f"特征({100-weight}%)"
        )
        sec_story = derive_story(m, cls, secondary, industry=industry)
        # 提取次类型 not_happen 的核心 2-3 行(第一行是标题,跳过)
        sec_lines = sec_story["not_happen"].splitlines()
        sec_signals = [l for l in sec_lines[1:] if l.strip().startswith("•")][:2]
        if sec_signals:
            auto_story["not_happen"] += (
                f"\n\n双特征额外信号({sec_name}视角):\n"
                + "\n".join(sec_signals)
            )

    # 持久化:首次进或切换公司/类型 → 重置为 auto;若用户编辑过,保留编辑
    story_key = f"lynch_story_{ticker}"
    story_meta_key = f"lynch_story_meta_{ticker}"  # 记录用了哪个 cls_id_used
    last_meta = st.session_state.get(story_meta_key)
    cur_meta = (cls_id_used, secondary, weight, _fmt_num(m.get("rev_cagr_5y"), 3))

    # 类型变了 → 重新生成
    if last_meta != cur_meta:
        st.session_state[story_key] = dict(auto_story)
        st.session_state[story_meta_key] = cur_meta

    story = st.session_state.get(story_key, dict(auto_story))

    # 顶部:并排显示"自动派生 vs 当前编辑"
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
    with btn_col1:
        if st.button("🤖 重新自动生成", key=f"{story_key}_regen",
                     help="覆盖当前编辑,用财报数据重新生成 3 段"):
            st.session_state[story_key] = dict(auto_story)
            st.rerun()
    with btn_col2:
        edited_flag = (story != auto_story)
        if edited_flag:
            st.caption("✏️ 已编辑(与自动派生不同)")
        else:
            st.caption("🤖 自动派生(未编辑)")

    s1 = st.text_input(
        "🎯 故事一句话",
        value=story.get("oneline", ""),
        key=f"{story_key}_oneline",
    )

    # 验证证据 — 逐条预览 + 行内编辑 + 增删按钮
    s2 = _editable_list(
        label="✅ 验证证据(从财报数据派生,可补充行业/管理层信号)",
        key_base=f"{story_key}_evidence",
        raw_value=story.get("evidence", ""),
        placeholder="如:营收 5y CAGR 18%(高速扩张,远超 GDP)",
        hint="每行 1 条;点 ✕ 删除,点 ➕ 添加",
    )

    # 不会发生的事 / 卖出信号 — 同上
    s3 = _editable_list(
        label="❌ 不会发生的事 / 卖出信号",
        key_base=f"{story_key}_not_happen",
        raw_value=story.get("not_happen", ""),
        placeholder="如:连续 2 季营收 YoY < 20% — 增长断档",
        hint="每行 1 条;点 ✕ 删除,点 ➕ 添加",
    )

    st.session_state[story_key] = {
        "oneline": s1, "evidence": s2, "not_happen": s3,
    }


def _editable_list(*, label: str, key_base: str, raw_value: str,
                    placeholder: str = "", hint: str = "",
                    min_n: int = 1) -> str:
    """渲染多行可编辑列表 — 每条独立 text_input + 删除按钮 + 末尾添加按钮。

    返回 \\n-join 的字符串,与原 text_area 兼容。
    raw_value 变化时(如"重新自动生成")自动重置 line keys。
    """
    parsed = [l.rstrip() for l in (raw_value or "").splitlines() if l.strip()]
    count_key = f"{key_base}_count"
    sync_key = f"{key_base}_synced_hash"
    cur_hash = hash(raw_value or "")

    # raw_value 变化(如点重新生成)→ 重置行数 + 行内容
    if st.session_state.get(sync_key) != cur_hash:
        st.session_state[count_key] = max(min_n, len(parsed))
        for i, v in enumerate(parsed):
            st.session_state[f"{key_base}_line_{i}"] = v
        # 清掉超出新行数的旧 key
        i = len(parsed)
        while f"{key_base}_line_{i}" in st.session_state:
            del st.session_state[f"{key_base}_line_{i}"]
            i += 1
        st.session_state[sync_key] = cur_hash

    n = st.session_state.get(count_key, max(min_n, len(parsed)))

    st.markdown(f"**{label}**")
    if hint:
        st.caption(hint)

    new_lines: list[str] = []
    for i in range(n):
        c1, c2 = st.columns([20, 1], gap="small")
        with c1:
            line_key = f"{key_base}_line_{i}"
            v = st.text_input(
                f"第 {i+1} 条",
                value=st.session_state.get(line_key,
                                            parsed[i] if i < len(parsed) else ""),
                key=line_key,
                label_visibility="collapsed",
                placeholder=placeholder,
            )
        with c2:
            disable_del = (n <= min_n)
            if st.button("✕", key=f"{key_base}_del_{i}",
                          help="删除此条" if not disable_del
                          else f"至少保留 {min_n} 条",
                          disabled=disable_del):
                # 把后面的值前移
                for j in range(i, n - 1):
                    next_v = st.session_state.get(f"{key_base}_line_{j+1}", "")
                    st.session_state[f"{key_base}_line_{j}"] = next_v
                last_key = f"{key_base}_line_{n-1}"
                if last_key in st.session_state:
                    del st.session_state[last_key]
                st.session_state[count_key] = n - 1
                st.session_state[sync_key] = hash(
                    "\n".join(st.session_state.get(f"{key_base}_line_{k}", "")
                              for k in range(n - 1))
                )
                st.rerun()
        new_lines.append(v)

    if st.button("➕ 添加一条", key=f"{key_base}_add"):
        st.session_state[count_key] = n + 1
        st.session_state[f"{key_base}_line_{n}"] = ""
        st.session_state[sync_key] = hash(
            "\n".join(st.session_state.get(f"{key_base}_line_{k}", "")
                      for k in range(n + 1))
        )
        st.rerun()

    return "\n".join(l for l in new_lines if l.strip())


def _step_2_growth_check(ticker: str, m: dict, cls_id_used: str) -> None:
    """② 成长核查 — 三层证据。"""
    _section_banner("②", "📈", "成长核查(增长真假 + 持续性 + 来源)",
                    "三层证据:CAGR 速率 / 季度连续 / 销量驱动", color="#1b8a3a")

    if cls_id_used in ("slow_grower", "cyclical", "asset_play", "turnaround"):
        st.info(f"💡 当前类型 {CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]} "
                f"非典型成长股,本步骤侧重数据展示而非判定")

    # 层 1:CAGR 速率
    st.markdown("**层 1:CAGR 速率**")
    rev_5y = m.get("rev_cagr_5y")
    np_yoy = m.get("np_yoy_recent")

    threshold_cagr = 0.25 if cls_id_used == "fast_grower" else 0.10 if cls_id_used == "stalwart" else 0.05
    threshold_label = "快速 ≥25%" if cls_id_used == "fast_grower" else "稳健 ≥10%" if cls_id_used == "stalwart" else "缓慢 ≥5%"

    db_mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0
    deduct = _deduct_metrics(ticker, db_mtime)
    dnp_yoy = deduct.get("dnp_yoy_recent")
    dnp_ratio = deduct.get("dnp_to_np_ratio")

    c1, c2, c3, c4 = st.columns(4)
    if rev_5y is not None:
        delta_color = "normal" if rev_5y >= threshold_cagr else "inverse"
        c1.metric("营收 5y CAGR", f"{rev_5y*100:.1f}%",
                  delta=f"{threshold_label} 阈值",
                  delta_color=delta_color)
    else:
        c1.metric("营收 5y CAGR", "—", delta="数据缺失")

    if m.get("rev_cagr_3y") is not None:
        c2.metric("营收 3y CAGR", f"{m['rev_cagr_3y']*100:.1f}%")
    else:
        c2.metric("营收 3y CAGR", "—")

    if np_yoy is not None:
        c3.metric("归母净利 YoY", f"{np_yoy*100:.1f}%",
                  delta="加速" if np_yoy > 0.20 else "稳" if np_yoy > 0 else "下滑",
                  delta_color="normal" if np_yoy > 0 else "inverse")
    else:
        c3.metric("归母净利 YoY", "—")

    # ⭐ 第 4 列:扣非净利 YoY(2026-05-06 新增 — 衡量"非一次性"利润的真实增速)
    if dnp_yoy is not None:
        # 极端值(|yoy| > 200%)通常源于扣非基数过小或翻负→翻正,显示提醒而非误导数字
        if abs(dnp_yoy) > 2.0:
            c4.metric("扣非净利 YoY ⭐", "极端值",
                      delta="基数小/翻正翻负",
                      delta_color="off",
                      help=f"派生 yoy = {dnp_yoy*100:.0f}%,"
                           f"通常因上年同期扣非基数过小或翻负→翻正所致;"
                           f"建议看下方近 8 季单季趋势图")
        else:
            c4.metric("扣非净利 YoY ⭐", f"{dnp_yoy*100:.1f}%",
                      delta="加速" if dnp_yoy > 0.20 else "稳" if dnp_yoy > 0 else "下滑",
                      delta_color="normal" if dnp_yoy > 0 else "inverse",
                      help="sina IS 派生(非理杏仁权威值,与官方差 5-10%):"
                           "净利 - 投资收益 - 公允价值变动 - 政府补助 - 资产处置 - 营业外收入 + 营业外支出,"
                           "再用 25% 简化税率调整")
    else:
        c4.metric("扣非净利 YoY ⭐", "—",
                  help="non_recurring_items 表无此公司数据,跑 fetch_non_recurring.py 补")

    # 差异警报:扣非 vs 归母差距大 → 一次性损益占比高(剔除极端值场景)
    if dnp_yoy is not None and np_yoy is not None and abs(dnp_yoy) <= 2.0:
        diff = abs(dnp_yoy - np_yoy)
        if diff > 0.30:
            direction = "高估" if np_yoy > dnp_yoy else "低估"
            st.warning(
                f"⚠️ 归母 yoy 与扣非 yoy 相差 {diff*100:.1f}pp(归母 {direction}真实增速)— "
                f"利润对一次性损益依赖度大,看扣非更可信",
                icon="⚠️",
            )

    # 扣非占比卡(显示在 metric 下面)
    if dnp_ratio is not None:
        if dnp_ratio >= 0.90:
            ratio_msg = f"🟢 扣非占比 {dnp_ratio*100:.1f}% — 主业纯净,几乎无一次性损益"
            st.caption(ratio_msg)
        elif dnp_ratio >= 0.70:
            ratio_msg = f"🟡 扣非占比 {dnp_ratio*100:.1f}% — 中等依赖一次性损益(政府补助/投资收益)"
            st.caption(ratio_msg)
        else:
            st.error(
                f"🔴 扣非占比仅 {dnp_ratio*100:.1f}% — **重度依赖一次性损益**!"
                f"若一次性损益消失,真实利润会大幅缩水",
                icon="🚨",
            )

    # 层 2:季度连续性(db_mtime 在层 1 已计算)— 8 季单季 YoY 滑窗
    qc = _qc_from_dict(_quarterly_continuity_cached(ticker, db_mtime, n_quarters=8))
    threshold_yoy = 0.20 if cls_id_used == "fast_grower" else 0.10
    threshold_label = ">20%" if cls_id_used == "fast_grower" else ">10%"
    st.markdown(f"**层 2:连续性(近 8 季营收 YoY,{threshold_label} 绿区)**")

    if qc is None:
        st.caption("(growth 表无营收数据,跳过季度连续性)")
    else:
        dates = [s for s, _ in qc.series]
        yoys = [y for _, y in qc.series]
        ymax = max(yoys) if yoys else 0
        ymin = min(yoys) if yoys else 0

        fig = go.Figure()
        fig.add_hrect(y0=threshold_yoy, y1=ymax + 0.10 if ymax > threshold_yoy else 0.5,
                      fillcolor="#1b8a3a", opacity=0.08, line_width=0,
                      annotation_text=f"林奇阈值 {threshold_label}",
                      annotation_position="top right", annotation_font_size=10)
        fig.add_hrect(y0=ymin - 0.05 if ymin < 0 else -0.1, y1=0,
                      fillcolor="#d9534f", opacity=0.06, line_width=0)
        fig.add_trace(go.Scatter(
            x=dates, y=yoys, mode="lines+markers",
            line=dict(color="#0d6efd", width=2),
            marker=dict(size=8),
            name="单季营收 YoY",
            hovertemplate="<b>%{x}</b><br>YoY %{y:.1%}<extra></extra>",
        ))
        fig.update_layout(
            height=240, margin=dict(t=20, b=20, l=10, r=10),
            yaxis_tickformat=".0%", showlegend=False,
            yaxis_title="单季营收 YoY",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # 命中数 + 类型铁律达标判断 + 退化提示
        n, h20, h10 = qc.n_quarters, qc.hits_20pct, qc.hits_10pct
        c_a, c_b, c_c, c_d = st.columns(4)
        c_a.metric("8 季中 >20% 命中", f"{h20}/{n}")
        c_b.metric("8 季中 >10% 命中", f"{h10}/{n}")
        if qc.median_yoy is not None:
            c_c.metric("中位 YoY", f"{qc.median_yoy*100:+.1f}%")
        if qc.latest_yoy is not None:
            delta_color = "normal" if qc.latest_yoy > 0 else "inverse"
            c_d.metric("最新季 YoY", f"{qc.latest_yoy*100:+.1f}%",
                       delta_color=delta_color)

        if cls_id_used == "fast_grower":
            if qc.fast_grower_pass():
                st.success(f"✅ 快速增长铁律达标 — 近 {n} 季 {h20}/{n} >20%(≥6/8)", icon="✅")
            elif h10 >= 6:
                st.warning(
                    f"⚠️ 已退化为稳健 — 快速铁律未达(仅 {h20}/{n} >20%)但 {h10}/{n} >10% "
                    f"满足稳健铁律;建议把分类改为 stalwart 重评",
                    icon="⚠️",
                )
            elif h20 >= 4:
                st.warning(f"⚠️ 快速增长边缘 — 近 {n} 季 {h20}/{n} >20%(铁律要求 ≥6/8)",
                           icon="⚠️")
            else:
                st.error(
                    f"🔴 快速增长属性丧失 — 近 {n} 季仅 {h20}/{n} >20% / {h10}/{n} >10%;"
                    f"建议重新分类为 缓慢增长型 / 周期型 / 困境反转型",
                    icon="🚨",
                )
        elif cls_id_used == "stalwart":
            if qc.stalwart_pass():
                st.success(f"✅ 稳健增长铁律达标 — 近 {n} 季 {h10}/{n} >10%(≥6/8)", icon="✅")
            elif h10 >= 4:
                st.warning(f"⚠️ 稳健增长边缘 — 近 {n} 季 {h10}/{n} >10%(铁律要求 ≥6/8)",
                           icon="⚠️")
            elif qc.hits_0 >= 6:
                st.info(f"ℹ️ 增长缓慢但未断档 — 近 {n} 季 {qc.hits_0}/{n} 季正增长",
                        icon="ℹ️")
            else:
                st.error(
                    f"🔴 稳健属性丧失 — 近 {n} 季仅 {h10}/{n} >10%;建议重新分类",
                    icon="🚨",
                )
        else:
            st.caption(f"近 {n} 季中:{h20} 季 >20% / {h10} 季 >10% / {qc.hits_0} 季 ≥0%")

        if qc.source == "derived":
            st.caption("📐 数据派生口径:营业收入累计 → 单季还原(Q1=累计;Q2/Q3/Q4=当期-上期);"
                       "YoY = 单季今年 / 单季去年同期 - 1")

    # 层 3:增长来源(简化版,行业适配)
    st.markdown("**层 3:增长来源(质量)**")
    cat = _company_category(ticker, db_mtime)
    na_msg = LAYER3_INDUSTRY_NA.get(cat)
    if na_msg:
        st.info(na_msg)
    else:
        st.caption("⚠️ 销量 vs 提价拆解 / 海外占比 / 市占率 — 当前数据层未装配,需手工补"
                   "(可在 02_companies/{N}_{name}/01_基本面数据/摘要.md 末尾手动补,"
                   "或后续用 Claude vision 解析年报 PDF)")

    # 自动结论
    st.divider()
    if rev_5y is not None and rev_5y >= threshold_cagr:
        st.success(f"✅ 成长核查 — 营收 5y CAGR {rev_5y*100:.1f}% 达标 ({threshold_label})", icon="✅")
    elif rev_5y is not None:
        st.warning(f"⚠️ 营收 5y CAGR {rev_5y*100:.1f}% 未达 {threshold_label}", icon="⚠️")
    else:
        st.info("ℹ️ 数据不足,建议人工确认")


def _step_3_financial_guardrails(ticker: str, m: dict, cls_id_used: str) -> None:
    """③ 财务护栏 — 类型驱动阈值。"""
    _section_banner("③", "🛡️", "财务护栏(高增长不烧钱)",
                    f"林奇原话:'快速增长公司的资产负债率超过 40%,我会立刻卖出'",
                    color="#f0ad4e")

    # 金融业(银行/保险/证券)短路:林奇财务护栏不适用 — 高负债率是行业特性
    industry = (m.get("industry_sw_l1") or "").strip()
    FINANCIAL_INDUSTRIES = {"银行", "非银金融", "保险", "证券"}
    if industry in FINANCIAL_INDUSTRIES:
        st.info(
            f"📌 金融业「{industry}」**不适用林奇财务护栏** — "
            f"负债率 {(m.get('debt_ratio') or 0)*100:.1f}% 是行业特性(银行靠存款、保险靠保费),"
            f"不能套用快速/稳健增长股的负债率阈值。\n\n"
            f"建议改看:**净息差/不良率/ROE/拨备覆盖率**(银行) · **内含价值/赔付率**(保险)"
        )
        return

    th = GUARDRAIL_THRESHOLDS.get(cls_id_used, GUARDRAIL_THRESHOLDS["stalwart"])
    st.caption(f"📌 当前阈值口径:**{th['label']}**")

    rows: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    edge_count = 0
    na_count = 0

    def _verdict(passed: bool | None, edge: bool = False) -> str:
        nonlocal pass_count, fail_count, edge_count, na_count
        if passed is None:
            na_count += 1
            return "⚪"
        if passed:
            pass_count += 1
            return "✅"
        if edge:
            edge_count += 1
            return "⚠️"
        fail_count += 1
        return "🔴"

    # 1. 资产负债率(越低越好)
    debt = m.get("debt_ratio")
    if debt is not None:
        max_th = th["debt_ratio_max"]
        passed = debt <= max_th
        edge = (not passed) and (debt <= max_th + 0.05)
        rows.append({
            "指标": "资产负债率",
            "当前值": f"{debt*100:.1f}%",
            "林奇阈值": f"≤ {max_th*100:.0f}%",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "资产负债率", "当前值": "—",
                     "林奇阈值": f"≤ {th['debt_ratio_max']*100:.0f}%",
                     "状态": _verdict(None)})

    # 2. 流动比率(越高越好)
    cr = m.get("current_ratio")
    if cr is not None:
        min_th = th["current_ratio_min"]
        passed = cr >= min_th
        edge = (not passed) and (cr >= min_th * 0.85)
        rows.append({
            "指标": "流动比率",
            "当前值": f"{cr:.2f}",
            "林奇阈值": f"≥ {min_th:.1f}",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "流动比率", "当前值": "—",
                     "林奇阈值": f"≥ {th['current_ratio_min']:.1f}",
                     "状态": _verdict(None)})

    # 3. 经营现金流/净利润(越高越好;> 1 表示利润有现金支撑)
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is not None:
        min_th = th["cfo_to_ni_min"]
        passed = cfo_ni >= min_th
        edge = (not passed) and (cfo_ni >= min_th - 0.15)
        rows.append({
            "指标": "经营现金流/净利润",
            "当前值": f"{cfo_ni:.2f}",
            "林奇阈值": f"≥ {min_th:.2f}",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "经营现金流/净利润", "当前值": "—",
                     "林奇阈值": f"≥ {th['cfo_to_ni_min']:.2f}",
                     "状态": _verdict(None)})

    # 4. 库存周转天数(越低越好)
    inv_d = m.get("inventory_turnover_days")
    inv_max = th.get("inv_days_max")
    if inv_d is not None:
        if inv_max is None:
            rows.append({"指标": "库存周转天数",
                         "当前值": f"{inv_d:.0f} 天",
                         "林奇阈值": "—(此类型不卡)",
                         "状态": "—"})  # 不计入
        else:
            passed = inv_d <= inv_max
            edge = (not passed) and (inv_d <= inv_max * 1.15)
            rows.append({
                "指标": "库存周转天数",
                "当前值": f"{inv_d:.0f} 天",
                "林奇阈值": f"≤ {inv_max} 天",
                "状态": _verdict(passed, edge),
            })
    else:
        rows.append({"指标": "库存周转天数", "当前值": "—",
                     "林奇阈值": f"≤ {inv_max} 天" if inv_max else "—",
                     "状态": _verdict(None)})

    # 5. 应收账款周转天数(越低越好)
    ar_d = m.get("receivables_turnover_days")
    ar_max = th.get("ar_days_max")
    if ar_d is not None and ar_max is not None:
        passed = ar_d <= ar_max
        edge = (not passed) and (ar_d <= ar_max * 1.2)
        rows.append({
            "指标": "应收账款周转天数",
            "当前值": f"{ar_d:.0f} 天",
            "林奇阈值": f"≤ {ar_max} 天",
            "状态": _verdict(passed, edge),
        })
    else:
        rows.append({"指标": "应收账款周转天数", "当前值": "—",
                     "林奇阈值": f"≤ {ar_max} 天" if ar_max else "—",
                     "状态": _verdict(None)})

    df = pd.DataFrame(rows)

    def _style_status(v):
        if v == "✅": return "background-color:#d4edda; font-weight:600"
        if v == "⚠️": return "background-color:#fff3cd; font-weight:600"
        if v == "🔴": return "background-color:#f8d7da; font-weight:600"
        return ""

    styler = df.style.map(_style_status, subset=["状态"])
    st.dataframe(styler, use_container_width=True, hide_index=True)

    # 整体结论
    total_evaluated = pass_count + fail_count + edge_count
    if total_evaluated == 0:
        st.info("ℹ️ 5 项护栏数据全缺失,无法判断", icon="ℹ️")
    elif fail_count == 0 and edge_count == 0:
        st.success(
            f"✅ 财务护栏 {pass_count}/{total_evaluated} 项全部通过 — 健康"
            + (f" · {na_count} 项数据缺" if na_count else ""),
            icon="✅",
        )
    elif fail_count == 0:
        st.warning(
            f"⚠️ {pass_count}/{total_evaluated} 通过 + {edge_count} 边缘 — 需关注",
            icon="⚠️",
        )
    else:
        st.error(
            f"🔴 {pass_count} 通过 / {edge_count} 边缘 / {fail_count} 不合格 — 护栏失守,警示信号",
            icon="🚨",
        )

    # 数据来源说明
    st.caption(
        "📊 数据来源:`资产负债率/流动比率`(safety) · `CFO/NI`(cashflow) · "
        "`存货周转/应收周转天数`(独立 turnover.duckdb,sina 财报派生)"
    )


def _step_4_peg_valuation(ticker: str, m: dict, cls_id_used: str) -> None:
    """④ PEG 估值 — 类型决定是否适用。

    口径校准(2026-05-06,与理杏仁页面对齐):
      PEG = PE-TTM ÷ (净利润 3y CAGR × 100)
      其中 3y CAGR 使用**倒数第二份年报作 end**(滞后一年保稳定),
      避免最新年报刚披露带来的 PEG 跳变。
      美的实测对齐:14.0 / 10.50% = **1.33** ✅(与理杏仁页面一致)
    """
    _section_banner("④", "📐", "PEG 估值(成长合理性核心)",
                    "PEG = PE-TTM ÷ (净利润 3y CAGR × 100) · 理杏仁同口径",
                    color="#6f42c1")

    peg_cfg = PEG_BY_TYPE.get(cls_id_used, PEG_BY_TYPE["stalwart"])

    if not peg_cfg["applicable"]:
        st.info(f"💡 **{CLASS_META[cls_id_used][0]}** {peg_cfg['note']}", icon="ℹ️")
        # 替代方案
        if cls_id_used == "slow_grower":
            dy = m.get("dividend_yield")
            pe = m.get("pe_ttm")
            st.markdown("**替代估值口径**")
            c1, c2 = st.columns(2)
            if dy is not None:
                rating = "🟢 高股息" if dy >= 0.04 else "🟡 中性" if dy >= 0.025 else "🔴 偏低"
                c1.metric("股息率", f"{dy*100:.2f}%", delta=rating)
            if pe is not None:
                rating = "🟢" if pe < 12 else "🟡" if pe < 18 else "🔴"
                c2.metric("PE-TTM", f"{pe:.1f}",
                          delta=f"{rating} 缓慢增长 PE 上限 12")
        elif cls_id_used == "cyclical":
            pb = m.get("pb")
            st.markdown("**替代估值口径(周期股看 PB)**")
            if pb is not None:
                rating = "🟢 周期底部" if pb < 1 else "🟡 中性" if pb < 2 else "🔴 周期顶部"
                st.metric("PB", f"{pb:.2f}", delta=rating)
        elif cls_id_used == "asset_play":
            cash_mc = m.get("cash_to_market_cap")
            st.markdown("**替代估值口径(看 NAV/现金)**")
            if cash_mc is not None:
                st.metric("现金/市值", f"{cash_mc*100:.1f}%")
            else:
                st.caption("(现金/市值数据未装配)")
        return

    pe = m.get("pe_ttm")
    np_yoy = m.get("np_ttm_yoy")           # 百分数 33.0 = 33%
    peg_lx = m.get("peg_lixinger")          # 直接复用 peg_curve 算好的 PEG

    if pe is None or np_yoy is None or np_yoy <= 0:
        # 兜底退化:净利 3y CAGR 不可用时退到营收 CAGR(明确告知)
        cagr_3y = m.get("rev_cagr_3y")
        cagr_5y = m.get("rev_cagr_5y")
        cagr = cagr_3y or cagr_5y
        if pe is None or cagr is None or cagr <= 0:
            st.warning(
                "⚠️ PE-TTM 或增长率数据缺失,无法算 PEG。"
                "(理杏仁口径需净利润 3y CAGR > 0)",
                icon="⚠️",
            )
            return
        peg = pe / (cagr * 100)
        st.warning(
            f"⚠️ 净利润 3y CAGR 不可用({np_yoy or 0:.1f}%) — "
            f"退化用营收 5y CAGR={cagr*100:.1f}% 兜底,"
            f"**与理杏仁页面会有差异**。",
            icon="⚠️",
        )
        growth_label = f"营收 CAGR({'3y' if cagr_3y else '5y'},兜底)"
        growth_value_str = f"{cagr*100:.1f}%"
    else:
        peg = peg_lx if peg_lx is not None else pe / (np_yoy / 100 * 100)
        growth_label = "净利润 3y CAGR"
        growth_value_str = f"{np_yoy:+.1f}%"

    target = peg_cfg["target"]

    # 顶部大数字
    c1, c2, c3 = st.columns(3)
    c1.metric("PE-TTM", f"{pe:.1f}")
    c2.metric(growth_label, growth_value_str,
              help="理杏仁标准:净利润 3 年 CAGR(年报数据,end=倒数第二份年报)")
    peg_rating = (
        "🟢🟢 极度低估" if peg < 0.5 else
        "🟢 合理偏低" if peg < 1.0 else
        "🟡 略贵" if peg < 1.5 else
        "🔴 高估" if peg < 2.0 else
        "🔴🔴 严重高估"
    )
    c3.metric("PEG", f"{peg:.2f}", delta=peg_rating,
              delta_color="normal" if peg < target else "inverse",
              help="PEG = PE-TTM ÷ (净利润 3y CAGR × 100) · 理杏仁同口径")

    # 评级表
    st.markdown("**📊 PEG 评级表**")
    rating_data = [
        {"PEG 区间": "< 0.5", "评级": "🟢🟢 极度低估", "建议": "重仓买入"},
        {"PEG 区间": "0.5 - 1.0", "评级": "🟢 合理偏低", "建议": "买入"},
        {"PEG 区间": "1.0 - 1.5", "评级": "🟡 略贵", "建议": "观望"},
        {"PEG 区间": "1.5 - 2.0", "评级": "🔴 高估", "建议": "减仓"},
        {"PEG 区间": "> 2.0", "评级": "🔴🔴 严重高估", "建议": "清仓"},
    ]
    rating_df = pd.DataFrame(rating_data)

    # 高亮当前所在档
    def _highlight_current(row):
        rng = row["PEG 区间"]
        is_current = (
            (rng == "< 0.5" and peg < 0.5) or
            (rng == "0.5 - 1.0" and 0.5 <= peg < 1.0) or
            (rng == "1.0 - 1.5" and 1.0 <= peg < 1.5) or
            (rng == "1.5 - 2.0" and 1.5 <= peg < 2.0) or
            (rng == "> 2.0" and peg >= 2.0)
        )
        return ["background-color:#d4edda; font-weight:700" if is_current else ""] * len(row)

    styled = rating_df.style.apply(_highlight_current, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # 结论
    if peg < target:
        st.success(f"✅ PEG {peg:.2f} ≤ 目标 {target} — 估值合理", icon="✅")
    elif peg < target * 1.3:
        st.warning(f"⚠️ PEG {peg:.2f} 略高于 {target} 目标 — 需观望", icon="⚠️")
    else:
        st.error(f"🔴 PEG {peg:.2f} 远超 {target} 目标 — 估值过高", icon="🚨")


def _step_5_story_update(ticker: str, m: dict | None = None,
                          cls_id_used: str = "") -> None:
    """⑤ 故事更新 — 每季 ping 兑现度。

    m / cls_id_used 用于自动计算卖出触发条件状态(PEG / YoY / 负债率)。
    """
    _section_banner("⑤", "🎬", "故事更新(决策续集 · 每季 ping 一次)",
                    "故事在轨吗?需不需要卖?",
                    color="#d63384")

    story = st.session_state.get(f"lynch_story_{ticker}", {})
    if not story.get("oneline"):
        st.warning("⚠️ 第 1 步未填故事脚本 — 请先回到「① 公司分类」填写")
        return

    m = m or {}

    # ─── 📖 故事 + 验证证据(默认全部展开)───────────────────────────────
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
            f"letter-spacing:0.04em;margin-bottom:4px'>📖 你的故事</div>"
            f"<div style='font-size:14px;color:#111827;line-height:1.55;"
            f"font-style:italic'>{story['oneline']}</div>",
            unsafe_allow_html=True,
        )
        if story.get("evidence"):
            evidence_lines = [
                l.strip() for l in story["evidence"].splitlines() if l.strip()
            ]
            evi_html = "".join(
                f"<div style='margin:3px 0;font-size:13px;color:#374151;"
                f"line-height:1.55'>{l}</div>"
                for l in evidence_lines
            )
            st.markdown(
                f"<div style='border-top:1px dashed #E5E7EB;margin-top:8px;"
                f"padding-top:6px'>"
                f"<div style='font-size:12px;color:#0369A1;font-weight:600;"
                f"letter-spacing:0.04em;margin-bottom:3px'>"
                f"✅ 验证证据(故事写入时的支撑数据)</div>"
                f"{evi_html}</div>",
                unsafe_allow_html=True,
            )

    # ─── 📊 故事打分卡(每条证据带"建议分数"参考)──────────────────────
    st.markdown("**📊 故事打分卡(本季更新)**")
    st.caption("逐条对照原始证据打分(0-100)· 系统已根据当前财报给出建议值")

    score_key = f"lynch_score_{ticker}"
    scores_state = st.session_state.get(score_key, {})

    evidence_lines = [
        l.strip() for l in (story.get("evidence") or "").splitlines()
        if l.strip() and l.strip() not in ("•", "-")
    ]
    n_evidence = max(1, len(evidence_lines))

    # 给每条证据一个"建议分数" — 基于关键指标当前 vs 原始判断
    suggested = _suggested_evidence_scores(m, cls_id_used, n_evidence)

    cols = st.columns(min(3, n_evidence))
    new_scores = []
    for i in range(n_evidence):
        with cols[i % len(cols)]:
            sug = suggested[i] if i < len(suggested) else 80
            evi_short = (evidence_lines[i][:42] + "…") if i < len(evidence_lines) and len(evidence_lines[i]) > 42 else (evidence_lines[i] if i < len(evidence_lines) else f"证据 #{i+1}")
            st.caption(f"#{i+1}: {evi_short}")
            v = st.slider(
                f"兑现度",
                min_value=0, max_value=100,
                value=int(scores_state.get(f"e{i}", sug)),
                step=5,
                key=f"{score_key}_e{i}",
                label_visibility="collapsed",
            )
            sug_badge = "🟢" if sug >= 80 else "🟡" if sug >= 60 else "🔴"
            st.caption(f"💡 建议 **{sug}** {sug_badge}(基于当前财报)")
            new_scores.append(v)
            scores_state[f"e{i}"] = v

    st.session_state[score_key] = scores_state

    avg = sum(new_scores) / len(new_scores)
    if avg >= 80:
        verdict, color = "🟢 故事在轨", "#1b8a3a"
    elif avg >= 60:
        verdict, color = "🟡 部分兑现", "#f0ad4e"
    else:
        verdict, color = "🔴 故事破裂", "#d9534f"

    st.markdown(
        f'<div style="padding:12px;border-radius:6px;background:{color}20;'
        f'border-left:4px solid {color};margin-top:8px">'
        f'<span style="font-size:20px;font-weight:700;color:{color}">'
        f'兑现度 {avg:.0f}% — {verdict}</span></div>',
        unsafe_allow_html=True,
    )

    # ─── 🚨 卖出触发条件(自动判断每条是否触发)─────────────────────────
    st.markdown("---")
    st.markdown("**🚨 卖出触发条件(任一触发 = 严肃评估)**")
    st.caption("每条阈值均由系统对照当前财报自动判断 · 无需手动勾选")

    triggers = _evaluate_sell_triggers(m, cls_id_used, avg)
    n_fired = sum(1 for t in triggers if t["fired"])

    # 顶部摘要徽章
    if n_fired == 0:
        summary_color = "#1b8a3a"
        summary_text = f"✅ 全部未触发({len(triggers)}/{len(triggers)} 安全)"
    elif n_fired == 1:
        summary_color = "#f0ad4e"
        summary_text = f"🟡 已触发 1 条 — 需密切关注"
    else:
        summary_color = "#d9534f"
        summary_text = f"🚨 已触发 {n_fired} 条 — 严肃评估卖出"

    st.markdown(
        f'<div style="padding:8px 12px;border-radius:6px;background:{summary_color}15;'
        f'border-left:4px solid {summary_color};margin:6px 0 10px;'
        f'font-weight:600;color:{summary_color}">{summary_text}</div>',
        unsafe_allow_html=True,
    )

    # 4 条触发条件(2x2 grid,每条带状态徽章 + 当前值 + 阈值)
    trig_cols = st.columns(2)
    for i, t in enumerate(triggers):
        with trig_cols[i % 2]:
            badge = "🚨" if t["fired"] else ("⚪" if t["current"] is None else "✅")
            badge_color = ("#d9534f" if t["fired"]
                           else "#9CA3AF" if t["current"] is None
                           else "#1b8a3a")
            border_color = badge_color
            cur_str = t["current_str"]
            with st.container(border=True):
                st.markdown(
                    f"<div style='border-left:3px solid {border_color};"
                    f"padding-left:8px;margin:-2px 0'>"
                    f"<div style='font-size:13px;font-weight:600;color:#111827'>"
                    f"{badge} {t['cond']} <span style='color:#9CA3AF;font-weight:400;"
                    f"font-size:11px'>· {t['label']}</span></div>"
                    f"<div style='font-size:12px;color:#374151;margin-top:3px'>"
                    f"当前 <b style='color:{badge_color}'>{cur_str}</b> · "
                    f"阈值 <span style='color:#6B7280'>{t['threshold']}</span>"
                    f"</div>"
                    f"<div style='font-size:11px;color:#6B7280;margin-top:2px;"
                    f"line-height:1.4'>{t['detail']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def _suggested_evidence_scores(m: dict, cls_id_used: str, n: int) -> list[int]:
    """对 n 条证据给出建议兑现度(0-100)。简化策略:用核心指标的'当前 vs 原阈值'综合打分。"""
    rev_yoy = m.get("rev_yoy_recent")
    np_yoy = m.get("np_yoy_recent")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    debt = m.get("debt_ratio")
    pe = m.get("pe_ttm")

    # 类型化阈值
    cagr_th = 0.15 if cls_id_used == "fast_grower" else 0.05 if cls_id_used == "stalwart" else 0.0
    yoy_th = 0.20 if cls_id_used == "fast_grower" else 0.10 if cls_id_used == "stalwart" else 0.0
    debt_th = 0.50 if cls_id_used == "fast_grower" else 0.65

    parts: list[int] = []
    # CAGR 维持度
    if cagr is not None and cagr_th > 0:
        ratio = max(0.0, min(1.5, cagr / cagr_th))
        parts.append(int(min(100, max(20, ratio * 70))))
    # 单季 YoY 维持度
    if rev_yoy is not None:
        if yoy_th > 0:
            ratio = max(0.0, min(1.5, rev_yoy / yoy_th))
            parts.append(int(min(100, max(20, ratio * 70))))
        else:
            parts.append(80 if rev_yoy > 0 else 40)
    # 净利 YoY
    if np_yoy is not None:
        parts.append(int(min(100, max(20, 80 + np_yoy * 100))))
    # 负债率(反向:越低分越高)
    if debt is not None:
        if debt <= debt_th * 0.7:
            parts.append(90)
        elif debt <= debt_th:
            parts.append(75)
        else:
            parts.append(45)
    # PEG
    if pe is not None and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        parts.append(90 if peg < 1 else 70 if peg < 1.5 else 50 if peg < 2 else 30)

    if not parts:
        return [70] * n
    avg_part = int(round(sum(parts) / len(parts)))
    return [avg_part] * n


def _evaluate_sell_triggers(m: dict, cls_id_used: str, story_avg: float) -> list[dict]:
    """对 4 条卖出触发条件做自动评估。返回每条的状态字典。"""
    rev_yoy = m.get("rev_yoy_recent")
    np_yoy = m.get("np_yoy_recent")
    debt = m.get("debt_ratio")
    pe = m.get("pe_ttm")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")

    # ① PEG > 2.0
    if pe is not None and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        peg_fired = peg > 2.0
        peg_cur = f"{peg:.2f}"
        peg_detail = f"PE {pe:.1f} ÷ CAGR {cagr*100:.1f}% = {peg:.2f}"
    else:
        peg = None
        peg_fired = False
        peg_cur = "—"
        peg_detail = "缺 PE 或 CAGR 数据"

    # ② 连续 2 季单季 YoY < 20%(快速类阈值,其它类放宽到 10% / 0)
    yoy_th = 20 if cls_id_used == "fast_grower" else 10 if cls_id_used == "stalwart" else 0
    yoy_used = rev_yoy if rev_yoy is not None else np_yoy
    if yoy_used is not None:
        yoy_pct = yoy_used * 100
        # 简化:用 1 个季度 YoY 是否低于阈值代表"是否进入断档区"
        # (真严格判断需 _quarterly_yoy 取连续 2 季,这里给保守估计)
        yoy_fired = yoy_pct < yoy_th
        yoy_cur = f"{yoy_pct:+.1f}%"
        yoy_detail = (f"最新单季营收 YoY {yoy_pct:+.1f}%(阈值 ≥{yoy_th}%);"
                      "连续 2 季低于阈值则触发")
    else:
        yoy_fired = False
        yoy_cur = "—"
        yoy_detail = "无最新单季 YoY 数据"

    # ③ 资产负债率 > 50%(快速类)/ > 65%(其它)
    debt_th_pct = 50 if cls_id_used == "fast_grower" else 65
    if debt is not None:
        debt_pct = debt * 100
        debt_fired = debt_pct > debt_th_pct
        debt_cur = f"{debt_pct:.1f}%"
        debt_detail = f"当前 {debt_pct:.1f}%(阈值 ≤{debt_th_pct}%)"
    else:
        debt_fired = False
        debt_cur = "—"
        debt_detail = "无负债率数据"

    # ④ 故事兑现度 < 60%
    story_fired = story_avg < 60
    story_cur = f"{story_avg:.0f}%"
    story_detail = "上方打分卡综合得分(系统建议 + 你的调整)"

    return [
        {
            "cond": "PEG > 2.0",
            "label": "估值反转",
            "current": peg,
            "current_str": peg_cur,
            "threshold": "≤ 2.0",
            "fired": peg_fired,
            "detail": peg_detail,
        },
        {
            "cond": f"单季 YoY < {yoy_th}%(连续 2 季)",
            "label": "增长断档",
            "current": yoy_used,
            "current_str": yoy_cur,
            "threshold": f"≥ {yoy_th}%",
            "fired": yoy_fired,
            "detail": yoy_detail,
        },
        {
            "cond": f"资产负债率 > {debt_th_pct}%",
            "label": "护栏失守",
            "current": debt,
            "current_str": debt_cur,
            "threshold": f"≤ {debt_th_pct}%",
            "fired": debt_fired,
            "detail": debt_detail,
        },
        {
            "cond": "故事兑现度 < 60%",
            "label": "故事破裂",
            "current": story_avg,
            "current_str": story_cur,
            "threshold": "≥ 60%",
            "fired": story_fired,
            "detail": story_detail,
        },
    ]


# ─── ⑥ ABCD/12345 综合评级 ──────────────────────────────────────────────


def _step_6_abcd_evaluation(ticker: str, m: dict, cls_id_used: str) -> None:
    """⑥ ABCD/12345 综合评级 — 文档同源:02_彼得林奇投资法/。

    三类适用(stalwart / fast_grower / cyclical),其它类型显示提示。
    评分流程:
      1. 自动分(财报数据驱动)+ 主观分(slider)+ 调整因子(checkbox)
      2. 公司质量 → A/B/C/D / 价格吸引力 → 1/2/3/4/5
      3. 4×5 矩阵决策(全力出击 / 减仓 / 卖出 / ...)
      4. 若有次类型(双特征),按主/次权重加权综合分,矩阵决策用综合分
    """
    _section_banner("⑥", "🎯", "ABCD/12345 综合评级",
                    "公司质量 × 价格吸引力 → 4×5 矩阵决策",
                    color="#0EA5E9")

    try:
        from lynch_abcd_scorer import score_abcd, applicable, MATRIX
    except Exception as e:
        st.error(f"ABCD 评分引擎加载失败:{e}")
        return

    # ─── 读取主次拆分(① 类型编辑器写到 session_state)──────────────────
    secondary = st.session_state.get(f"lynch_secondary_{ticker}", "")
    weight = st.session_state.get(f"lynch_weight_{ticker}", 100) if secondary else 100

    if not applicable(cls_id_used):
        cls_label = CLASS_META.get(cls_id_used, ("?",))[0]
        # 若主类型不适用但次类型适用 → 退化用次类型
        if secondary and applicable(secondary):
            st.info(
                f"💡 主类型 **{cls_label}** 暂未实现 ABCD,改用次类型 "
                f"**{CLASS_META[secondary][0]}** 评分(权重 100%)"
            )
            cls_id_used = secondary
            secondary = ""
            weight = 100
        else:
            st.info(
                f"💡 当前类型 **{cls_label}** 暂未实现 ABCD/12345 双维评估。\n\n"
                "已支持:🛡️ 稳健增长 / 🚀 快速增长 / 🔄 周期型 三类\n\n"
                "请回到 ① 公司分类调整为以上三类之一,或参考 "
                "[02_彼得林奇投资法/01_六类公司分类法.md](../../../01_knowledge/03_投资策略与选股/02_彼得林奇投资法/01_六类公司分类法.md) "
                "手动评估。"
            )
            return

    # ─── session 持久化 manual 输入(主类型自己一份,次类型一份)──────
    manual_key = f"lynch_abcd_manual_{ticker}_{cls_id_used}"
    manual = st.session_state.get(manual_key, {})

    # 预跑主类型
    result = score_abcd(ticker, m, cls_id_used, manual=manual)
    if result is None:
        st.error("评分计算失败")
        return

    # 主次拆分提示
    if secondary and applicable(secondary):
        sec_meta = CLASS_META[secondary]
        st.success(
            f"🎯 **双特征综合评分**:主 {result.cls_emoji} {result.cls_name} "
            f"({weight}%) + 次 {sec_meta[1]} {sec_meta[0]} ({100-weight}%) — "
            f"下方两套打分独立,综合分 = 主×{weight}% + 次×{100-weight}%",
            icon="🎯",
        )
    elif secondary:
        st.caption(f"次类型 {CLASS_META[secondary][0]} 暂未实现 ABCD,综合评分仅用主类型")
        secondary = ""
        weight = 100

    st.markdown(
        f"📚 **方法论**:[02_{result.cls_name}_ABCD评估.md]"
        f"(../../../01_knowledge/03_投资策略与选股/02_彼得林奇投资法/) · "
        f"📐 评分细则同源,改文档不改代码"
    )
    st.divider()

    # ═══ 主类型评分 ═══
    if secondary:
        st.markdown(f"## 🥇 主类型评分 · {result.cls_emoji} {result.cls_name} ({weight}%)")

    st.markdown("### 🏛️ 公司质量评分(好公司)")
    new_manual_company = _render_score_panel(
        result.company_items, result.company_adjusts,
        prefix=f"{manual_key}_company", manual=manual,
    )

    st.markdown("### 💰 价格吸引力评分(好价格)")
    new_manual_price = _render_score_panel(
        result.price_items, result.price_adjusts,
        prefix=f"{manual_key}_price", manual=manual,
    )

    merged = {**manual, **new_manual_company, **new_manual_price}
    if merged != manual:
        st.session_state[manual_key] = merged
        result = score_abcd(ticker, m, cls_id_used, manual=merged)

    # ═══ 次类型评分(若双特征)═══
    sec_result = None
    if secondary:
        st.divider()
        sec_meta = CLASS_META[secondary]
        st.markdown(f"## 🥈 次类型评分 · {sec_meta[1]} {sec_meta[0]} ({100-weight}%)")
        sec_manual_key = f"lynch_abcd_manual_{ticker}_{secondary}"
        sec_manual = st.session_state.get(sec_manual_key, {})
        sec_result = score_abcd(ticker, m, secondary, manual=sec_manual)
        if sec_result is None:
            st.error("次类型评分失败")
        else:
            st.markdown("### 🏛️ 公司质量评分(次类型口径)")
            sec_new_company = _render_score_panel(
                sec_result.company_items, sec_result.company_adjusts,
                prefix=f"{sec_manual_key}_company", manual=sec_manual,
            )
            st.markdown("### 💰 价格吸引力评分(次类型口径)")
            sec_new_price = _render_score_panel(
                sec_result.price_items, sec_result.price_adjusts,
                prefix=f"{sec_manual_key}_price", manual=sec_manual,
            )
            sec_merged = {**sec_manual, **sec_new_company, **sec_new_price}
            if sec_merged != sec_manual:
                st.session_state[sec_manual_key] = sec_merged
                sec_result = score_abcd(ticker, m, secondary, manual=sec_merged)

    st.divider()

    # ═══ 矩阵决策(综合分 / 单一分)═══
    final_result = _combine_results(result, sec_result, weight) if sec_result else result
    if sec_result:
        st.markdown(f"### 🎯 综合定位({result.cls_name} {weight}% + {sec_result.cls_name} {100-weight}%)")
    _render_matrix_decision(final_result)


def _combine_results(primary, secondary, weight: int):
    """主+次类型加权合成最终 AbcdResult。weight = 主类型权重(50-95)。"""
    from lynch_abcd_scorer import AbcdResult, MATRIX

    w1, w2 = weight / 100.0, (100 - weight) / 100.0
    # 加权综合分(分数项 + 调整因子合成的最终分)
    company_combined = primary.company_final_score * w1 + secondary.company_final_score * w2
    price_combined = primary.price_final_score * w1 + secondary.price_final_score * w2

    # 重新算等级 + 决策
    from lynch_abcd_scorer import _grade_company, _grade_price
    c_grade = _grade_company(company_combined)
    p_grade = _grade_price(price_combined)
    decision, color = MATRIX[c_grade][p_grade]

    return AbcdResult(
        cls_id=f"{primary.cls_id}+{secondary.cls_id}",
        cls_name=f"{primary.cls_name}{weight}% + {secondary.cls_name}{100-weight}%",
        company_items=primary.company_items + secondary.company_items,
        company_adjusts=primary.company_adjusts + secondary.company_adjusts,
        company_base_score=company_combined,
        company_adjust_total=0,
        company_final_score=company_combined,
        company_grade=c_grade,
        company_max=110,
        price_items=primary.price_items + secondary.price_items,
        price_adjusts=primary.price_adjusts + secondary.price_adjusts,
        price_base_score=price_combined,
        price_adjust_total=0,
        price_final_score=price_combined,
        price_grade=p_grade,
        price_max=110,
        matrix_decision=decision,
        matrix_color=color,
    )


def _render_score_panel(items, adjusts, *, prefix: str, manual: dict) -> dict:
    """渲染评分项 + 调整因子。返回新 manual 输入 dict。"""
    new_manual: dict = {}

    # 评分项
    for it in items:
        c1, c2, c3 = st.columns([3, 1.2, 4], gap="small")
        with c1:
            tag = ("🤖 自动" if it.source == "auto"
                   else "✍️ 主观" if it.source == "manual"
                   else "❓ 待填" if it.source == "missing"
                   else "")
            st.markdown(
                f"**{it.label}** "
                f"<span style='color:#9CA3AF;font-size:11px'>{tag}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            color = ("#16A34A" if it.score >= it.max_score * 0.8
                     else "#EAB308" if it.score >= it.max_score * 0.5
                     else "#DC2626" if it.source != "missing"
                     else "#9CA3AF")
            st.markdown(
                f"<div style='text-align:center;font-size:18px;font-weight:700;"
                f"color:{color}'>{it.score:.0f}<span style='color:#9CA3AF;"
                f"font-weight:400;font-size:12px'>/{it.max_score:.0f}</span></div>",
                unsafe_allow_html=True,
            )
        with c3:
            if it.source in ("manual", "missing"):
                # slider 让用户输入
                cur_v = manual.get(it.key)
                v = st.slider(
                    f"_slider_{it.key}",
                    min_value=0, max_value=int(it.max_score),
                    value=int(cur_v) if cur_v is not None else 0,
                    step=1,
                    key=f"{prefix}_{it.key}",
                    label_visibility="collapsed",
                )
                new_manual[it.key] = v
                st.caption(it.detail.replace("⚠️ 需手动评分:", "").replace("用户评分", "已确认"))
            else:
                st.caption(it.detail)

    # 调整因子
    if adjusts:
        st.markdown("**📌 调整因子**(勾选触发的)")
        cols = st.columns(2)
        for i, adj in enumerate(adjusts):
            with cols[i % 2]:
                # auto 触发的(如 ROE ≥20% 自动判定)直接显示
                key_id = f"adj_{adj.key}"
                if any(p in adj.detail for p in ["当前 ROE", "PEG"]) and adj.triggered:
                    # 自动判断触发的
                    badge = "🟢" if adj.polarity == "bonus" else "🔴"
                    st.markdown(
                        f"{badge} **{adj.label}** {adj.delta:+d} 分 "
                        f"<span style='color:#9CA3AF;font-size:11px'>(自动触发)</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(adj.detail)
                else:
                    # 用户 checkbox
                    cur = bool(manual.get(key_id, False))
                    new_v = st.checkbox(
                        f"{adj.label} ({adj.delta:+d})",
                        value=cur,
                        key=f"{prefix}_{key_id}",
                        help=adj.detail,
                    )
                    new_manual[key_id] = new_v

    # 小计
    total_items = sum(it.score for it in items)
    total_adj = sum(a.delta for a in adjusts)
    final = total_items + total_adj
    adj_color = "#16A34A" if total_adj >= 0 else "#DC2626"
    st.markdown(
        f"<div style='background:#F3F4F6;padding:6px 12px;border-radius:6px;"
        f"margin:8px 0;font-size:13px'>"
        f"基础分 <b>{total_items:.0f}</b> / "
        f"{sum(it.max_score for it in items):.0f} · "
        f"调整 <b style='color:{adj_color}'>{total_adj:+d}</b> · "
        f"<b style='font-size:16px'>最终 {final:.0f}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    return new_manual


def _render_matrix_decision(result) -> None:
    """渲染 ABCD/12345 + 4×5 矩阵决策 banner。"""
    from lynch_abcd_scorer import MATRIX

    # 大数字徽章 — 三列:公司质量 / 价格吸引力 / 矩阵决策
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        grade_color = {"A": "#16A34A", "B": "#65A30D",
                        "C": "#EAB308", "D": "#DC2626"}[result.company_grade]
        st.markdown(
            f"<div style='text-align:center;background:white;border:2px solid {grade_color};"
            f"border-radius:14px;padding:12px;'>"
            f"<div style='font-size:11px;color:#6B7280;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>公司质量</div>"
            f"<div style='font-size:48px;font-weight:800;color:{grade_color};"
            f"line-height:1.1'>{result.company_grade}</div>"
            f"<div style='font-size:13px;color:#374151'>"
            f"{result.company_final_score:.0f}<span style='color:#9CA3AF'>/110</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        grade_color = {1: "#16A34A", 2: "#65A30D",
                        3: "#EAB308", 4: "#F97316", 5: "#DC2626"}[result.price_grade]
        st.markdown(
            f"<div style='text-align:center;background:white;border:2px solid {grade_color};"
            f"border-radius:14px;padding:12px;'>"
            f"<div style='font-size:11px;color:#6B7280;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>价格吸引力</div>"
            f"<div style='font-size:48px;font-weight:800;color:{grade_color};"
            f"line-height:1.1'>{result.price_grade}</div>"
            f"<div style='font-size:13px;color:#374151'>"
            f"{result.price_final_score:.0f}<span style='color:#9CA3AF'>/110</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div style='background:linear-gradient(90deg,{result.matrix_color}22 0%,white 100%);"
            f"border-left:5px solid {result.matrix_color};"
            f"padding:12px 16px;border-radius:8px;height:100%;display:flex;"
            f"flex-direction:column;justify-content:center'>"
            f"<div style='font-size:11px;color:#6B7280;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>矩阵决策</div>"
            f"<div style='font-size:18px;font-weight:700;color:{result.matrix_color};"
            f"margin-top:4px;line-height:1.3'>{result.matrix_decision}</div>"
            f"<div style='font-size:11px;color:#6B7280;margin-top:4px'>"
            f"{result.cls_name}{' · 文档定义'} · 公司 {result.company_grade} 级 × 价格 {result.price_grade} 级"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    # 4×5 矩阵热力图(本格高亮)
    with st.expander("📊 完整 4×5 决策矩阵(当前位置高亮)", expanded=False):
        cur_g, cur_p = result.company_grade, result.price_grade
        rows_html = ""
        for grade in ["A", "B", "C", "D"]:
            cells = "".join(
                _matrix_cell_html(grade, p, cur_g == grade and cur_p == p)
                for p in [1, 2, 3, 4, 5]
            )
            rows_html += (
                f"<tr><td style='font-weight:700;padding:8px;background:#F9FAFB;"
                f"border:1px solid #E5E7EB;width:80px'>{grade} 级</td>{cells}</tr>"
            )
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:12px'>"
            f"<tr><th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'></th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>1 级<br>低估</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>2 级</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>3 级<br>合理</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>4 级</th>"
            f"<th style='padding:6px;border:1px solid #E5E7EB;background:#F3F4F6'>5 级<br>高估</th>"
            f"</tr>{rows_html}</table>",
            unsafe_allow_html=True,
        )


def _matrix_cell_html(grade: str, price: int, highlight: bool) -> str:
    from lynch_abcd_scorer import MATRIX
    decision, color = MATRIX[grade][price]
    if highlight:
        return (
            f"<td style='padding:8px;border:3px solid {color};background:{color}33;"
            f"font-weight:700;color:{color};text-align:center;font-size:11px'>"
            f"📍 当前<br>{decision}</td>"
        )
    return (
        f"<td style='padding:8px;border:1px solid #E5E7EB;"
        f"text-align:center;font-size:11px;color:{color}'>{decision}</td>"
    )


def _step_6_summary(ticker: str, folder: str, cls: ClassificationResult,
                    cls_id_used: str, m: dict,
                    decisions_db=None) -> None:
    """🎯 五步综合结论 + 决策日志写入 + md 导出。"""
    _section_banner("🎯", "🎯", "五步综合结论",
                    "汇总 5 步判定 → 生成决策建议",
                    color="#198754")

    # 汇总 5 步状态(简化:从已渲染数据推导)
    rows = []

    # 步 1
    type_changed = (cls_id_used != cls.cls_id)
    rows.append({
        "步骤": "① 公司分类",
        "结果": f"{CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]}"
                + (" (用户覆盖)" if type_changed else ""),
        "状态": "✅",
    })

    # 步 2
    rev_5y = m.get("rev_cagr_5y")
    threshold_cagr = 0.25 if cls_id_used == "fast_grower" else 0.10 if cls_id_used == "stalwart" else 0.05
    if rev_5y is not None:
        rows.append({
            "步骤": "② 成长核查",
            "结果": f"5y CAGR {rev_5y*100:.1f}%",
            "状态": "✅" if rev_5y >= threshold_cagr else "⚠️",
        })
    else:
        rows.append({"步骤": "② 成长核查", "结果": "数据缺失", "状态": "⚪"})

    # 步 3
    debt = m.get("debt_ratio")
    th_max = GUARDRAIL_THRESHOLDS.get(cls_id_used, GUARDRAIL_THRESHOLDS["stalwart"])["debt_ratio_max"]
    if debt is not None:
        rows.append({
            "步骤": "③ 财务护栏",
            "结果": f"负债率 {debt*100:.1f}%(≤ {th_max*100:.0f}% 阈值)",
            "状态": "✅" if debt <= th_max else "⚠️" if debt <= th_max + 0.05 else "🔴",
        })
    else:
        rows.append({"步骤": "③ 财务护栏", "结果": "数据缺失", "状态": "⚪"})

    # 步 4
    pe = m.get("pe_ttm")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    peg_cfg = PEG_BY_TYPE.get(cls_id_used, PEG_BY_TYPE["stalwart"])
    if peg_cfg["applicable"] and pe and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        rows.append({
            "步骤": "④ PEG 估值",
            "结果": f"PEG {peg:.2f}",
            "状态": "✅" if peg < peg_cfg["target"] else "⚠️" if peg < peg_cfg["target"] * 1.3 else "🔴",
        })
    else:
        rows.append({
            "步骤": "④ PEG 估值",
            "结果": peg_cfg["note"],
            "状态": "—",
        })

    # 步 5
    score_state = st.session_state.get(f"lynch_score_{ticker}", {})
    if score_state:
        avg_story = sum(score_state.values()) / max(len(score_state), 1)
        rows.append({
            "步骤": "⑤ 故事更新",
            "结果": f"兑现度 {avg_story:.0f}%",
            "状态": "✅" if avg_story >= 80 else "⚠️" if avg_story >= 60 else "🔴",
        })
    else:
        rows.append({"步骤": "⑤ 故事更新", "结果": "未填写", "状态": "⚪"})

    # 渲染汇总表
    sdf = pd.DataFrame(rows)

    def _style_state(v):
        if v == "✅": return "background-color:#d4edda; font-weight:600"
        if v == "⚠️": return "background-color:#fff3cd; font-weight:600"
        if v == "🔴": return "background-color:#f8d7da; font-weight:600"
        return ""

    styler = sdf.style.map(_style_state, subset=["状态"])
    st.dataframe(styler, use_container_width=True, hide_index=True)

    # 综合判断
    n_pass = sum(1 for r in rows if r["状态"] == "✅")
    n_warn = sum(1 for r in rows if r["状态"] == "⚠️")
    n_fail = sum(1 for r in rows if r["状态"] == "🔴")

    if n_pass >= 4:
        verdict = "🟢 综合通过 — 适合中等以上仓位"
        color = "#1b8a3a"
    elif n_pass >= 3:
        verdict = "🟡 综合可通过 — 试仓 / 关注"
        color = "#f0ad4e"
    else:
        verdict = "🔴 综合不通过 — 不建议建仓"
        color = "#d9534f"

    # ⭐ 同步显示"筛选页加权综合分"— 让两边数字可直接对照
    try:
        dims = compute_lynch_dims(m, cls_id_used)
        weighted_score, weighted_badge = overall_lynch(dims)
        if weighted_score >= 75:
            weighted_rating = "🟢 优秀"
            weighted_color = "#1b8a3a"
        elif weighted_score >= 60:
            weighted_rating = "🟡 合格"
            weighted_color = "#f0ad4e"
        elif weighted_score >= 45:
            weighted_rating = "🟠 警戒"
            weighted_color = "#fd7e14"
        else:
            weighted_rating = "🔴 不及格"
            weighted_color = "#d9534f"
    except Exception:
        weighted_score, weighted_rating, weighted_color = None, None, "#888"

    # 双视角并排展示
    col_v1, col_v2 = st.columns(2)

    with col_v1:
        st.markdown(
            f'<div style="padding:14px;border-radius:8px;background:{color}20;'
            f'border-left:4px solid {color};">'
            f'<div style="font-size:13px;color:#666">五步判定(离散 · gate 式)</div>'
            f'<div style="font-size:20px;font-weight:700;color:{color};margin-top:4px">{verdict}</div>'
            f'<div style="margin-top:4px;font-size:13px">通过 {n_pass} · 警示 {n_warn} · 不及格 {n_fail}</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with col_v2:
        if weighted_score is not None:
            st.markdown(
                f'<div style="padding:14px;border-radius:8px;background:{weighted_color}20;'
                f'border-left:4px solid {weighted_color};">'
                f'<div style="font-size:13px;color:#666">加权综合分(连续 · 同筛选页)</div>'
                f'<div style="font-size:20px;font-weight:700;color:{weighted_color};margin-top:4px">'
                f'{weighted_rating} · {weighted_score:.1f}/100</div>'
                f'<div style="margin-top:4px;font-size:13px">阈值 🟢 ≥75 / 🟡 ≥60 / 🟠 ≥45 / 🔴 &lt;45</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("(加权综合分计算失败)")

    # 视角差异提示(关键!避免用户困惑两套结论不一致)
    if weighted_score is not None:
        same_signal = (
            (n_pass >= 4 and weighted_score >= 75) or
            (n_pass >= 3 and 60 <= weighted_score < 75) or
            (n_pass < 3 and weighted_score < 60)
        )
        if same_signal:
            st.caption(
                f"💡 **两个视角一致**:五步通过 {n_pass}/5 ≈ 加权 {weighted_score:.0f}/100。"
                f"五步是 _{cls_id_used} 类型的 gate 式判定_,加权分是 _类型驱动 5 维评分_,"
                f"两者算法不同但结论同向。"
            )
        else:
            st.warning(
                f"⚠️ **两个视角分歧**:五步通过 {n_pass}/5 vs 加权 {weighted_score:.0f}/100。"
                f"原因:某一项硬伤(如 PEG 或负债率)在五步里独立扣 1 票,"
                f"但在加权分里只占 15-25% 权重,会被其它高分维度对冲。"
                f"**建议**:把五步当_决策 gate_(任一硬伤需复盘),加权分当_整体画像_(高分仍可优秀)。",
                icon="⚠️",
            )

    # 操作按钮
    st.markdown("---")
    col_a, col_b, col_c = st.columns([1, 1, 1])

    with col_a:
        if st.button("💾 写入决策日志", key=f"lynch_save_{ticker}",
                     use_container_width=True,
                     disabled=(decisions_db is None)):
            try:
                action = "观察" if n_pass < 3 else "买入" if n_pass >= 4 else "观察"
                rationale = (
                    f"林奇五步: ① {CLASS_META[cls_id_used][0]}"
                    + f" · ② CAGR { (rev_5y or 0)*100 :.1f}%"
                    + f" · ③ 负债 {(debt or 0)*100:.0f}%"
                    + f" · 综合通过 {n_pass}/5"
                )
                decisions_db.insert(
                    ticker=ticker, folder=folder,
                    date=_date_cls.today(), action=action,
                    weight_change=0.0, price=0.0,
                    rationale=rationale,
                    thesis_5y=st.session_state.get(f"lynch_story_{ticker}", {}).get("oneline", ""),
                    risks="",
                    tags="林奇五步分析", snapshot={},
                )
                st.success("✅ 已写入 decisions.duckdb", icon="✅")
            except Exception as e:
                st.error(f"❌ 写入失败:{e}")

    with col_b:
        if st.button("📤 导出五步分析 md", key=f"lynch_export_{ticker}",
                     use_container_width=True):
            md_path = _export_md(ticker, folder, cls, cls_id_used, m, rows, verdict)
            if md_path:
                st.success(f"✅ 已导出 → `{md_path.relative_to(ROOT)}`", icon="📤")
            else:
                st.error("❌ 导出失败,公司目录未找到")

    with col_c:
        st.caption(f"决策日志:.tools/decisions/decisions.duckdb")
        st.caption(f"md 路径:02_companies/{folder}/05_投资决策/")


def _export_md(ticker: str, folder: str, cls: ClassificationResult,
               cls_id_used: str, m: dict, rows: list[dict], verdict: str) -> Path | None:
    """导出五步分析 md 到 02_companies/{N}_{name}/05_投资决策/。"""
    company_dir = COMPANIES_DIR / folder
    if not company_dir.exists():
        return None
    target_dir = company_dir / "05_投资决策"
    target_dir.mkdir(exist_ok=True)
    today = _date_cls.today().strftime("%Y%m%d")
    md_path = target_dir / f"林奇五步分析_{today}.md"

    story = st.session_state.get(f"lynch_story_{ticker}", {})
    score_state = st.session_state.get(f"lynch_score_{ticker}", {})

    lines = [
        f"# {folder} · 林奇五步分析",
        "",
        f"**分析日期**:{_date_cls.today().strftime('%Y-%m-%d')}",
        f"**Ticker**:{ticker}",
        f"**分析框架**:彼得林奇 GARP + 六类公司分类(`.tools/rules/lynch.yaml`)",
        f"**自动判定类型**:{cls.cls_emoji} {cls.cls_name}(置信度 {cls.confidence*100:.0f}%)",
        f"**采用类型**:{CLASS_META[cls_id_used][1]} {CLASS_META[cls_id_used][0]}",
        "",
        "---",
        "",
        "## 第一步:公司分类",
        "",
        f"**自动判定理由**:{cls.reason}",
        "",
        "**关键数据**:",
        "",
    ]
    for k, v in cls.key_metrics.items():
        lines.append(f"- {k}:{v}")
    lines.extend([
        "",
        "**故事脚本**:",
        "",
        f"- 🎯 一句话:{story.get('oneline', '(未填)')}",
        f"- ✅ 验证证据:",
    ])
    for ev_line in (story.get("evidence") or "(未填)").splitlines():
        if ev_line.strip():
            lines.append(f"  - {ev_line.strip()}")
    lines.extend([
        f"- ❌ 不会发生的事:{story.get('not_happen', '(未填)')}",
        "",
        "---",
        "",
        "## 第二步:成长核查",
        "",
        f"- 营收 5y CAGR:{(m.get('rev_cagr_5y') or 0)*100:.1f}%",
        f"- 营收 3y CAGR:{(m.get('rev_cagr_3y') or 0)*100:.1f}%",
        f"- 最新净利 YoY:{(m.get('np_yoy_recent') or 0)*100:.1f}%",
        "",
        "---",
        "",
        "## 第三步:财务护栏",
        "",
        f"- 资产负债率:{(m.get('debt_ratio') or 0)*100:.1f}%(类型阈值 {GUARDRAIL_THRESHOLDS[cls_id_used]['debt_ratio_max']*100:.0f}%)",
        "",
        "---",
        "",
        "## 第四步:PEG 估值",
        "",
    ])
    pe = m.get("pe_ttm")
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    peg_cfg = PEG_BY_TYPE.get(cls_id_used, PEG_BY_TYPE["stalwart"])
    if peg_cfg["applicable"] and pe and cagr and cagr > 0:
        peg = pe / (cagr * 100)
        lines.append(f"- PE-TTM:{pe:.1f}")
        lines.append(f"- CAGR:{cagr*100:.1f}%")
        lines.append(f"- **PEG = {peg:.2f}**(目标 ≤ {peg_cfg['target']})")
    else:
        lines.append(f"- {peg_cfg['note']}")
    lines.extend([
        "",
        "---",
        "",
        "## 第五步:故事更新",
        "",
    ])
    if score_state:
        avg = sum(score_state.values()) / max(len(score_state), 1)
        lines.append(f"- 兑现度:{avg:.0f}%")
        for k, v in score_state.items():
            lines.append(f"  - {k}:{v}")
    else:
        lines.append("- 未打分")
    lines.extend([
        "",
        "---",
        "",
        "## 综合结论",
        "",
        f"**{verdict}**",
        "",
        "| 步骤 | 结果 | 状态 |",
        "| --- | --- | --- |",
    ])
    for r in rows:
        lines.append(f"| {r['步骤']} | {r['结果']} | {r['状态']} |")
    lines.extend([
        "",
        "---",
        "",
        f"**生成工具**:`.tools/dashboard/tabs/lynch_analysis.py`",
        f"**对照模板**:`02_companies/01_新华保险/05_投资决策/02_格雷厄姆投资法_新华保险五步分析.md`",
    ])

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


# ─── 主入口 ─────────────────────────────────────────────────────────────

def render(companies: list[str], selected: str, db_mtime: float,
           decisions_db=None, folder_to_ticker_fn=None) -> None:
    st.subheader("🌱 彼得林奇分析法 · 成长投资五步框架")

    # 顶部公司选择 + 年份
    col_c, col_y, col_r = st.columns([3, 1, 1])
    with col_c:
        # 默认与 sidebar selected 同步
        idx = companies.index(selected) if selected in companies else 0
        company = st.selectbox("公司", companies, index=idx,
                               key="lynch_company", label_visibility="collapsed")
    with col_y:
        year = st.selectbox("年份",
                            list(range(_date_cls.today().year, _date_cls.today().year - 5, -1)),
                            index=1, key="lynch_year", label_visibility="collapsed")
    with col_r:
        if st.button("🔄 重新评估", key="lynch_refresh", use_container_width=True):
            _classify_cached.clear()
            _metrics_cached.clear()
            _quarterly_yoy.clear()
            st.rerun()

    # ticker 解析
    if folder_to_ticker_fn:
        f2t = folder_to_ticker_fn if isinstance(folder_to_ticker_fn, dict) else folder_to_ticker_fn
        ticker = f2t.get(company, "")
    else:
        # fallback:从 helpers 加载
        from dashboard_helpers import _folder_to_ticker
        ticker = _folder_to_ticker(db_mtime).get(company, "")

    if not ticker:
        st.error(f"⚠️ 未找到 {company} 的 ticker 映射")
        return

    # 加载分类 + metrics
    cls_dict = _classify_cached(ticker, db_mtime)
    m = _metrics_cached(ticker, db_mtime)

    if cls_dict is None or m is None:
        st.error(f"⚠️ {company} ({ticker}) 数据加载失败")
        return

    # 重建 ClassificationResult(从 dict)
    cls = ClassificationResult(
        cls_id=cls_dict["cls_id"],
        cls_name=cls_dict["cls_name"],
        cls_emoji=cls_dict["cls_emoji"],
        confidence=cls_dict["confidence"],
        reason=cls_dict["reason"],
        key_metrics=cls_dict["key_metrics"],
        notes=cls_dict["notes"],
    )

    # 顶部 banner:类型徽章 + 一句话定位
    st.markdown(
        f'<div style="padding:12px 16px;border-radius:8px;'
        f'background:linear-gradient(90deg,#0d6efd 0%, #198754 100%);'
        f'color:white;margin:8px 0">'
        f'<span style="font-size:24px">{cls.cls_emoji}</span> '
        f'<span style="font-size:20px;font-weight:700;margin-left:8px">'
        f'当前阶段:{cls.cls_name}</span>'
        f'<span style="margin-left:16px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'置信度 {cls.confidence*100:.0f}%</span>'
        f'<div style="font-size:13px;opacity:0.9;margin-top:6px">'
        f'📍 林奇视角:{CLASS_META[cls.cls_id][2]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 6 sub-tabs(增 ⑥ ABCD/12345 评级)
    tab1, tab2, tab3, tab4, tab5, tab6, tab_sum = st.tabs([
        "① 公司分类", "② 成长核查", "③ 财务护栏",
        "④ PEG 估值", "⑤ 故事更新", "⑥ ABCD 评级", "🎯 综合结论",
    ])

    with tab1:
        _step_1_classification(ticker, cls, m, company)

    # 用户覆盖后的类型
    cls_id_used = st.session_state.get(f"lynch_type_{ticker}", cls.cls_id)

    with tab2:
        _step_2_growth_check(ticker, m, cls_id_used)

    with tab3:
        _step_3_financial_guardrails(ticker, m, cls_id_used)

    with tab4:
        _step_4_peg_valuation(ticker, m, cls_id_used)

    with tab5:
        _step_5_story_update(ticker, m, cls_id_used)

    with tab6:
        _step_6_abcd_evaluation(ticker, m, cls_id_used)

    with tab_sum:
        _step_6_summary(ticker, company, cls, cls_id_used, m, decisions_db)


__all__ = ["render"]
