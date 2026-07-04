"""Lynch analysis 共享 helper / 常量 / 缓存层。"""
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

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
DB_PATH = ROOT / "data" / "preson.duckdb"
COMPANIES_DIR = ROOT / "02_companies"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from masters.lynch.classifier import (  # noqa: E402
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
        "current_ratio_min": 1.2,
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

HOME_APPLIANCE_KEYWORDS = ("家电", "白色家电", "家用电器")

INDUSTRY_GUARDRAIL_OVERRIDES = {
    "home_appliance": {
        "keywords": HOME_APPLIANCE_KEYWORDS,
        "types": {
            "stalwart": {
                "debt_ratio_max": 0.65,
                "current_ratio_min": 1.1,
                "cfo_to_ni_min": 0.9,
                "label": "稳健增长 · 家电校正",
            },
        },
    },
}


def guardrail_thresholds_for(cls_id: str, industry: str | None = None) -> dict:
    """按林奇类型取财务护栏,再叠加 A 股行业校正。"""
    base = dict(GUARDRAIL_THRESHOLDS.get(cls_id, GUARDRAIL_THRESHOLDS["stalwart"]))
    industry_text = str(industry or "")
    for cfg in INDUSTRY_GUARDRAIL_OVERRIDES.values():
        if not any(k in industry_text for k in cfg["keywords"]):
            continue
        override = cfg["types"].get(cls_id)
        if override:
            base.update(override)
            base["industry_override"] = True
        break
    return base

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
