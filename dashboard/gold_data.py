"""黄金分析 Tab · 纯数据访问模块(对照 graham_steps.py)。

读 `data/gold.duckdb`,提供 6 个查询函数 + 1 个静态范式判定:
- load_gold_metrics()      — 长表读取 8 个 indicator 各自时序
- load_gold_ratios()       — 派生比率宽表
- load_gold_percentiles()  — 当前分位快照
- load_gold_etf_master()   — 4 只 ETF 静态信息
- load_gold_etf_prices()   — 4 只 ETF 日 K
- latest_snapshot()        — 单点快照(最新值 + 各分位)

Phase 2.4 落地后 paradigm 投票引擎将走独立模块。当前 Tab 用 `static_paradigm_vote()`
基于已知 2026-05 状况给出静态判定(显式标 verified=False)。

UI 渲染层 → tabs/gold_analysis.py
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GOLD_DB = ROOT / "data" / "gold.duckdb"


# ───── 数据查询(纯读) ──────────────────────────────────────────────────


def _read(sql: str, params: list | None = None) -> pd.DataFrame:
    """统一读 gold.duckdb,read_only 不阻塞写。"""
    if not GOLD_DB.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        if params:
            return con.execute(sql, params).fetchdf()
        return con.execute(sql).fetchdf()
    finally:
        con.close()


def load_indicator(indicator: str, days: int | None = None) -> pd.DataFrame:
    """长表读单个 indicator;按需加近 N 天裁切。"""
    if days:
        sql = (
            "SELECT date, value FROM gold_metrics "
            "WHERE indicator = ? AND date >= CURRENT_DATE - INTERVAL '{}' DAY "
            "ORDER BY date"
        ).format(int(days))
        return _read(sql, [indicator])
    return _read(
        "SELECT date, value FROM gold_metrics WHERE indicator = ? ORDER BY date",
        [indicator],
    )


def load_ratios(days: int | None = None) -> pd.DataFrame:
    """gold_ratios 宽表(date / gold_oil / gold_silver / nominal_10y / cpi_yoy / real_rate)。"""
    if days:
        return _read(
            "SELECT * FROM gold_ratios "
            "WHERE date >= CURRENT_DATE - INTERVAL '{}' DAY "
            "ORDER BY date".format(int(days))
        )
    return _read("SELECT * FROM gold_ratios ORDER BY date")


def load_percentiles(as_of: _date | None = None) -> pd.DataFrame:
    """最新分位快照(每 metric × window 一行)。"""
    if as_of:
        return _read(
            "SELECT * FROM gold_percentiles WHERE as_of = ? ORDER BY metric, window_label",
            [as_of],
        )
    # 默认拉每个 (metric, window) 的最新一条
    return _read(
        """
        WITH latest AS (
            SELECT metric, window_label, MAX(as_of) AS as_of
            FROM gold_percentiles
            GROUP BY metric, window_label
        )
        SELECT p.* FROM gold_percentiles p
        INNER JOIN latest l USING (metric, window_label, as_of)
        ORDER BY metric, window_label
        """
    )


def load_etf_master() -> pd.DataFrame:
    return _read("SELECT * FROM gold_etf_master ORDER BY etf_code")


def load_etf_prices(days: int | None = None) -> pd.DataFrame:
    sql = (
        "SELECT etf_code, date, close FROM gold_etf_prices "
        + (f"WHERE date >= CURRENT_DATE - INTERVAL '{int(days)}' DAY " if days else "")
        + "ORDER BY etf_code, date"
    )
    return _read(sql)


# ───── 摘要快照 ─────────────────────────────────────────────────────────


@dataclass
class Snapshot:
    """单点快照,Banner 与首屏决策卡都用这个。"""
    as_of: Optional[_date]
    real_rate: Optional[float]            # %
    real_rate_pct_5y: Optional[float]     # 0-1
    real_rate_pct_10y: Optional[float]
    nominal_10y: Optional[float]
    cpi_yoy: Optional[float]
    gold_oil: Optional[float]
    gold_oil_pct_5y: Optional[float]
    gold_oil_pct_10y: Optional[float]
    gold_silver: Optional[float]
    gold_silver_pct_5y: Optional[float]
    gold_silver_pct_10y: Optional[float]
    spdr_holdings: Optional[float]        # 吨;若 SPDR 缺数据则 None
    gold_usd: Optional[float]             # USD/oz 派生

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def latest_snapshot() -> Snapshot:
    """聚合最新快照。SPDR 缺时返回 None,UI 应做"未启用"提示。"""
    # 1. 利率三件套(取 ratios 最新一行有 real_rate 的)
    rates = _read(
        "SELECT date, real_rate, nominal_10y, cpi_yoy FROM gold_ratios "
        "WHERE real_rate IS NOT NULL ORDER BY date DESC LIMIT 1"
    )
    # cpi_yoy 在 gold_ratios 是月→日 NULL,直接从 gold_metrics 拉最新月度
    cpi_latest = _read(
        "SELECT date, value FROM gold_metrics WHERE indicator='US_CPI_YOY' "
        "ORDER BY date DESC LIMIT 1"
    )

    # 2. 比率两件套(取 ratios 最新一行有 gold_oil 的)
    oil_silver = _read(
        "SELECT date, gold_oil, gold_silver FROM gold_ratios "
        "WHERE gold_oil IS NOT NULL OR gold_silver IS NOT NULL "
        "ORDER BY date DESC LIMIT 1"
    )

    # 3. SPDR(可能完全没有)
    spdr_df = _read(
        "SELECT date, value FROM gold_metrics WHERE indicator='SPDR_HOLDINGS' "
        "ORDER BY date DESC LIMIT 1"
    )

    # 4. USD 金价
    usd_df = _read(
        "SELECT date, value FROM gold_metrics WHERE indicator='GOLD_USD_DERIVED' "
        "ORDER BY date DESC LIMIT 1"
    )

    # 5. 分位快照(metric × window)
    pct = load_percentiles()
    pct_lookup: dict[tuple[str, str], float] = {}
    for _, row in pct.iterrows():
        pct_lookup[(row["metric"], row["window_label"])] = float(row["percentile"])

    # 解 as_of
    as_of_candidates = []
    for df in (rates, oil_silver):
        if not df.empty:
            as_of_candidates.append(pd.to_datetime(df["date"].iloc[0]).date())
    as_of = max(as_of_candidates) if as_of_candidates else None

    return Snapshot(
        as_of=as_of,
        real_rate=float(rates["real_rate"].iloc[0]) if not rates.empty else None,
        real_rate_pct_5y=pct_lookup.get(("real_rate", "5y")),
        real_rate_pct_10y=pct_lookup.get(("real_rate", "10y")),
        nominal_10y=float(rates["nominal_10y"].iloc[0]) if not rates.empty and pd.notna(rates["nominal_10y"].iloc[0]) else None,
        cpi_yoy=float(cpi_latest["value"].iloc[0]) if not cpi_latest.empty else None,
        gold_oil=float(oil_silver["gold_oil"].iloc[0]) if not oil_silver.empty and pd.notna(oil_silver["gold_oil"].iloc[0]) else None,
        gold_oil_pct_5y=pct_lookup.get(("gold_oil", "5y")),
        gold_oil_pct_10y=pct_lookup.get(("gold_oil", "10y")),
        gold_silver=float(oil_silver["gold_silver"].iloc[0]) if not oil_silver.empty and pd.notna(oil_silver["gold_silver"].iloc[0]) else None,
        gold_silver_pct_5y=pct_lookup.get(("gold_silver", "5y")),
        gold_silver_pct_10y=pct_lookup.get(("gold_silver", "10y")),
        spdr_holdings=float(spdr_df["value"].iloc[0]) if not spdr_df.empty else None,
        gold_usd=float(usd_df["value"].iloc[0]) if not usd_df.empty else None,
    )


# ───── 静态范式投票(Phase 2.4 替换为 yaml 引擎)──────────────────────


@dataclass
class ParadigmVote:
    """三大范式投票结果。verified=False 标静态判定。"""
    p1_active: bool       # 经济金融
    p2_active: bool       # 技术革命
    p3_active: bool       # 大国博弈
    p1_count: int         # 5 信号中 ≥3 即激活
    p2_count: int
    p3_count: int
    dominant_id: str      # safe_haven / inflation / cycle / mixed_X / weak
    dominant_label: str   # 中文标签
    suggested_pct: tuple[float, float]  # (low, high) 配置区间
    verified: bool        # False = 静态判定 / True = 引擎判定
    source: str           # 'static_2026_05' / 'paradigm_engine_v1'

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["suggested_pct"] = list(d["suggested_pct"])
        return d


def static_paradigm_vote(snapshot: Snapshot) -> ParadigmVote:
    """基于已知 2026-05 + 实时实际利率 给出静态判定。

    Phase 2.4 落地范式引擎前用此函数兜底。判定逻辑:
    - 范式一(经济金融):康波萧条期 + 实际利率 / VIX / SPDR / 地缘风险 — 简化为 实际利率<0 或 SPDR>0
    - 范式二(技术革命):AI 革命期 + 美股科技 vs 金价相关性 — 静态写"激活"
    - 范式三(大国博弈):央行连续购金 + 去美元化 — 静态写"激活"

    返回时 verified=False,UI 应显式提示"待 Phase 2.4 范式引擎接入"。
    """
    # 范式一 — 5 信号简化:康波萧条期(算 1)+ 实际利率<0(算 1)+ SPDR 有数据(算 1)+ AI 革命(算 1)+ 地缘(算 1)
    p1_count = 1  # 康波萧条期(2026 = 第五次康波萧条期中后段)
    if snapshot.real_rate is not None and snapshot.real_rate < 0:
        p1_count += 1
    if snapshot.spdr_holdings is not None:
        p1_count += 1
    p1_count += 1  # 地缘风险持续(2026 俄乌+中东)— 静态
    p1_active = p1_count >= 3

    # 范式二 — 静态:AI 革命期 + 黄金/科技股同涨 → 激活
    p2_count = 3
    p2_active = True

    # 范式三 — 静态:央行净购金连续 3 年 + 美元储备占比 < 60% + 去美元化倡议 → 全部激活
    p3_count = 5
    p3_active = True

    # 主导身份判定
    actives = sum([p1_active, p2_active, p3_active])
    if actives == 3:
        dominant_id = "all_three"
        dominant_label = "🛡️ 避险 + 🔥 抗通胀 + 🔄 周期(三身份共振)"
        suggested_pct = (20.0, 25.0)
    elif p2_active and p3_active and not p1_active:
        dominant_id = "inflation_cycle"
        dominant_label = "🔥 抗通胀 + 🔄 周期"
        suggested_pct = (15.0, 20.0)
    elif p1_active and p3_active:
        dominant_id = "safe_cycle"
        dominant_label = "🛡️ 避险 + 🔄 周期"
        suggested_pct = (15.0, 20.0)
    elif p1_active and p2_active:
        dominant_id = "safe_inflation"
        dominant_label = "🛡️ 避险 + 🔥 抗通胀"
        suggested_pct = (15.0, 20.0)
    elif p1_active:
        dominant_id = "safe_haven"
        dominant_label = "🛡️ 避险(短期)"
        suggested_pct = (5.0, 10.0)
    elif p2_active:
        dominant_id = "inflation"
        dominant_label = "🔥 抗通胀(中期)"
        suggested_pct = (10.0, 15.0)
    elif p3_active:
        dominant_id = "cycle"
        dominant_label = "🔄 周期(长期)"
        suggested_pct = (10.0, 15.0)
    else:
        dominant_id = "weak"
        dominant_label = "黄金弱势期"
        suggested_pct = (0.0, 5.0)

    return ParadigmVote(
        p1_active=p1_active, p2_active=p2_active, p3_active=p3_active,
        p1_count=p1_count, p2_count=p2_count, p3_count=p3_count,
        dominant_id=dominant_id, dominant_label=dominant_label,
        suggested_pct=suggested_pct,
        verified=False, source="static_2026_05",
    )


# ───── 15 信号定义(UI 渲染矩阵用)─────────────────────────────────────

PARADIGM_SIGNALS: list[dict] = [
    # 范式一 · 经济金融(5)
    {"id": "p1_kondratiev", "p": "经济金融", "name": "康波周期位置",
     "current": "第五次萧条期中后段", "threshold": "萧条期 = 激活", "active": True,
     "source": "周金涛 / 手填"},
    {"id": "p1_real_rate",  "p": "经济金融", "name": "实际利率(US 10Y - CPI YoY)",
     "current": "DYNAMIC", "threshold": "< 0% = 激活",
     "active": "DYNAMIC", "source": "gold_metrics"},
    {"id": "p1_vix",        "p": "经济金融", "name": "VIX 恐慌指数",
     "current": "未接入", "threshold": "> 25 = 激活", "active": False,
     "source": "P3 待接入"},
    {"id": "p1_spdr",       "p": "经济金融", "name": "SPDR 黄金 ETF 持仓",
     "current": "DYNAMIC", "threshold": "近 6 月 +5% = 激活",
     "active": "DYNAMIC", "source": "manual_csv 备选"},
    {"id": "p1_geopolitical", "p": "经济金融", "name": "地缘风险事件",
     "current": "俄乌 + 中东持续", "threshold": "≥1 重大事件 = 激活", "active": True,
     "source": "手填"},

    # 范式二 · 技术革命(5)
    {"id": "p2_ai_commercial", "p": "技术革命", "name": "AI 商用化进度",
     "current": "中期(GPT-5+)", "threshold": "早/中期 = 激活", "active": True,
     "source": "手填"},
    {"id": "p2_tech_corr", "p": "技术革命", "name": "美股科技 vs 金价相关性",
     "current": "+0.42(同向)", "threshold": "> 0 = 激活", "active": True,
     "source": "P3 待接入"},
    {"id": "p2_productivity", "p": "技术革命", "name": "美国非农生产力 YoY",
     "current": "1.8%", "threshold": "< 2% = 激活", "active": True,
     "source": "P3 待接入"},
    {"id": "p2_ai_layoff", "p": "技术革命", "name": "AI 替代率新闻指数",
     "current": "高位", "threshold": "高位 = 激活", "active": True,
     "source": "手填"},
    {"id": "p2_energy_rev", "p": "技术革命", "name": "能源革命 vs 黄金需求竞争",
     "current": "中性", "threshold": "中性 = 不激活", "active": False,
     "source": "手填"},

    # 范式三 · 大国博弈(5)
    {"id": "p3_cb_purchase", "p": "大国博弈", "name": "全球央行连续净购金",
     "current": "连续 3 年", "threshold": "连续 ≥2 年 = 激活", "active": True,
     "source": "WGC / 手填"},
    {"id": "p3_usd_share", "p": "大国博弈", "name": "美元储备占比",
     "current": "58%", "threshold": "< 60% = 激活", "active": True,
     "source": "IMF COFER / 手填"},
    {"id": "p3_dedollar", "p": "大国博弈", "name": "去美元化倡议",
     "current": "BRICS+ 扩容", "threshold": "推进中 = 激活", "active": True,
     "source": "手填"},
    {"id": "p3_sanction", "p": "大国博弈", "name": "制裁工具化频率",
     "current": "历史高位", "threshold": "高位 = 激活", "active": True,
     "source": "OFAC / 手填"},
    {"id": "p3_em_reserves", "p": "大国博弈", "name": "新兴经济体黄金储备占比",
     "current": "多国 > 10%", "threshold": "≥10% = 激活", "active": True,
     "source": "WGC / 手填"},
]


def fill_dynamic_signals(snapshot: Snapshot) -> list[dict]:
    """把 PARADIGM_SIGNALS 中的 DYNAMIC 字段用 snapshot 实际值填充。"""
    filled = []
    for sig in PARADIGM_SIGNALS:
        s = sig.copy()
        if s["id"] == "p1_real_rate":
            if snapshot.real_rate is not None:
                s["current"] = f"{snapshot.real_rate:+.2f}%"
                s["active"] = snapshot.real_rate < 0
            else:
                s["current"] = "数据缺失"
                s["active"] = False
        elif s["id"] == "p1_spdr":
            if snapshot.spdr_holdings is not None:
                s["current"] = f"{snapshot.spdr_holdings:.0f} 吨"
                s["active"] = True  # 有持仓数据即视为激活(简化)
            else:
                s["current"] = "未启用(SPDR 数据未接入)"
                s["active"] = False
        filled.append(s)
    return filled


__all__ = [
    "GOLD_DB", "Snapshot", "ParadigmVote",
    "load_indicator", "load_ratios", "load_percentiles",
    "load_etf_master", "load_etf_prices",
    "latest_snapshot", "static_paradigm_vote",
    "PARADIGM_SIGNALS", "fill_dynamic_signals",
]
