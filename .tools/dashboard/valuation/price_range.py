"""下季度合理价格区间 — 多模型加权聚合。

三个模型(各自基于 valuation/ 下已落地的逻辑):
  1. Graham:fair_price.compute_fair_range() → graham_number
  2. PEG=1(林奇):fair_PE = 净利 3y CAGR(%);fair_price = current × fair_PE / pe_ttm
  3. Gordon DDM(股息折现):D_next / (r - g),r=8%,g=股息率 5y 平均增速(capped at 5%)

聚合:
  - floor   = min(各模型公允价)
  - ceiling = max(各模型公允价)
  - mid     = weighted_mean(各模型 × 权重)
  - 权重按 lynch_type 调整;缺数据的模型从加权中剔除并写入 note

verdict:
  - 当前价 < floor    → 🟢 区间下沿之下,显著低估
  - 当前价 ≤ mid      → 🟢 区间内偏低,可分批
  - 当前价 ≤ ceiling  → 🟡 区间内偏高,谨慎
  - 当前价 > ceiling  → 🔴 区间上沿之上,高估
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb

try:
    import streamlit as st
    if st.runtime.exists():
        _cache_data = st.cache_data
    else:
        raise RuntimeError("no streamlit runtime")
except Exception:
    def _cache_data(*a, **kw):
        def deco(fn):
            return fn
        return deco

from .fair_price import (
    DB_PATH, FairPriceRange, compute_fair_range, _normalize_ticker,
)

try:
    from dashboard_helpers import get_conn
except Exception:
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    try:
        from dashboard_helpers import get_conn
    except Exception:
        _sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
        from dashboard_helpers import get_conn

# 林奇分类 → 模型权重 (graham, peg, ddm, pe_hist, pb_hist, rim)
# - PE_hist:自身 5y PE 中位回归,适合估值带稳态公司
# - PB_hist:自身 5y PB 中位回归,适合 PE 失真但 PB 有锚的银行/保险/周期
# - RIM:剩余收益模型,适合高 ROE 特许经营公司,巴菲特口径
_WEIGHTS_BY_TYPE: dict[str, tuple[float, float, float, float, float, float]] = {
    "stalwart":    (0.05, 0.20, 0.10, 0.40, 0.05, 0.20),  # 茅台:PE_hist + RIM 双主导
    "fast_grower": (0.05, 0.30, 0.05, 0.50, 0.05, 0.05),  # 立讯:PE_hist + PEG
    "slow_grower": (0.10, 0.05, 0.25, 0.20, 0.20, 0.20),  # 招行:DDM + PB_hist + RIM 并重
    "cyclical":    (0.10, 0.15, 0.10, 0.20, 0.40, 0.05),  # 周期:PB_hist 主导
    "turnaround":  (0.40, 0.30, 0.05, 0.15, 0.10, 0.00),  # 问题股:Graham/PEG 严
    "asset_play":  (0.30, 0.10, 0.10, 0.15, 0.30, 0.05),  # 资产股:Graham + PB_hist
}
_DEFAULT_WEIGHTS = (0.10, 0.20, 0.15, 0.25, 0.15, 0.15)

# DDM 参数
_DDM_R = 0.08         # 必要回报率
_DDM_G_CAP = 0.05     # 股息增长率上限(避免 g >= r 发散)


@dataclass
class ModelEstimate:
    name: str               # "Graham" / "PEG=1" / "Gordon DDM"
    fair_price: float | None
    weight: float
    verified: bool
    note: str


@dataclass
class PriceRange:
    ticker: str
    name: str
    current_price: float | None
    floor: float | None
    mid: float | None
    ceiling: float | None
    verdict_code: str        # "below_floor" / "in_lower" / "in_upper" / "above_ceiling" / "na"
    verdict_label: str
    models: list[ModelEstimate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    as_of: date | None = None


# ─── 模型 2:PEG=1 公允价 ─────────────────────────────────────────────
def _peg_fair_price(con, ticker: str, current_price: float, pe_ttm: float) -> ModelEstimate:
    """林奇 PEG=1:fair_PE = 净利 3y CAGR(%);fair = current × fair_PE / pe_ttm。"""
    # 取年度归母净利润序列,算 3y CAGR(end 用倒数第二份年报)
    rows = con.execute(
        """
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM growth
        WHERE ticker = ? AND metric = '归属于母公司普通股股东的净利润'
          AND value IS NOT NULL AND EXTRACT(MONTH FROM date) = 12
        ORDER BY date DESC LIMIT 6
        """,
        [ticker],
    ).fetchall()
    if len(rows) < 5:
        return ModelEstimate("PEG=1", None, 0.0, False, f"年报数据不足 5 年 (实 {len(rows)})")
    # rows DESC:[最新, 上一年, ...];end 取 rows[1](倒数第二份),start = rows[4]
    end_v = rows[1][1]
    start_v = rows[4][1]
    if end_v is None or start_v is None or end_v <= 0 or start_v <= 0:
        return ModelEstimate("PEG=1", None, 0.0, False, "净利非正,3y CAGR 无意义")
    cagr = (end_v / start_v) ** (1 / 3) - 1
    if cagr <= 0:
        return ModelEstimate("PEG=1", None, 0.0, False, f"3y CAGR={cagr*100:.1f}% ≤ 0,PEG 不适用")
    fair_pe = cagr * 100  # PEG=1 → fair_PE = growth_rate(%)
    fair = current_price * (fair_pe / pe_ttm)
    return ModelEstimate(
        "PEG=1", fair, 0.0, True,
        f"3y CAGR={cagr*100:.1f}%(用 {rows[4][0]}-{rows[1][0]} 年报);fair PE={fair_pe:.1f}",
    )


# ─── 模型 3:Gordon DDM ────────────────────────────────────────────────
def _gordon_fair_price(con, ticker: str, current_price: float) -> ModelEstimate:
    """Gordon 股息折现:D_next / (r - g)。

    D    = 最新股息率 × current_price
    g    = 净利 5y CAGR(作为分红能力代理),capped at _DDM_G_CAP
    r    = _DDM_R
    """
    # 12m 滚动平均股息率,避免瞬时尖刺(美的 5.35% 案例)
    yld_row = con.execute(
        "SELECT AVG(value), COUNT(*) FROM valuation "
        "WHERE ticker=? AND metric='股息率' AND value > 0 "
        "AND date >= (CURRENT_DATE - INTERVAL 12 MONTH)",
        [ticker],
    ).fetchone()
    if yld_row is None or yld_row[0] is None or yld_row[1] is None or yld_row[1] < 60:
        return ModelEstimate(
            "Gordon DDM", None, 0.0, False,
            f"近 12m 股息率样本不足({yld_row[1] if yld_row else 0} 个,需 ≥60),模型不适用",
        )
    yld = float(yld_row[0])
    # 理杏仁股息率单位:百分数(3.78 = 3.78%)
    if yld > 1:
        yld = yld / 100.0
    d_now = yld * current_price

    # g:净利 5y CAGR
    rows = con.execute(
        """
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM growth
        WHERE ticker = ? AND metric = '归属于母公司普通股股东的净利润'
          AND value IS NOT NULL AND EXTRACT(MONTH FROM date) = 12
        ORDER BY date DESC LIMIT 6
        """,
        [ticker],
    ).fetchall()
    g = 0.0
    g_note = ""
    if len(rows) >= 6:
        end_v, start_v = rows[0][1], rows[5][1]
        if end_v and start_v and end_v > 0 and start_v > 0:
            g_raw = (end_v / start_v) ** (1 / 5) - 1
            g = max(0.0, min(g_raw, _DDM_G_CAP))
            g_note = f"净利 5y CAGR={g_raw*100:.1f}% (capped {g*100:.1f}%)"
        else:
            g_note = "净利非正,g=0"
    else:
        g_note = "净利年报不足 6 年,g=0"

    if g >= _DDM_R:
        return ModelEstimate("Gordon DDM", None, 0.0, False, f"g≥r,模型发散 ({g_note})")
    d_next = d_now * (1 + g)
    fair = d_next / (_DDM_R - g)
    return ModelEstimate(
        "Gordon DDM", fair, 0.0, True,
        f"D=¥{d_now:.2f}(12m 均股息率 {yld*100:.2f}%);{g_note};r={_DDM_R*100:.0f}%",
    )


# ─── 模型 5:历史 PB 中位回归(银行/周期/重资产)──────────────────
def _pb_hist_fair_price(con, ticker: str, current_price: float, pb_now: float | None) -> ModelEstimate:
    """5y PB-TTM 中位 → fair = current × (pb_med5y / pb_now)。

    银行/保险/化工/钢铁等 PE 失真但 PB 有锚的行业,用自身 PB 估值带回归。
    """
    if pb_now is None or pb_now <= 0:
        return ModelEstimate("PB_hist", None, 0.0, False, "当前 PB ≤ 0 或缺失")
    row = con.execute(
        "SELECT MEDIAN(value), COUNT(*) FROM valuation "
        "WHERE ticker=? AND metric='PB' AND value > 0 "
        "AND date >= (CURRENT_DATE - INTERVAL 5 YEAR)",
        [ticker],
    ).fetchone()
    if row is None or row[0] is None or row[1] is None or row[1] < 300:
        return ModelEstimate(
            "PB_hist", None, 0.0, False,
            f"近 5y PB 样本不足({row[1] if row else 0} 个交易日,需 ≥300)",
        )
    pb_med = float(row[0])
    fair = current_price * (pb_med / pb_now)
    return ModelEstimate(
        "PB_hist", fair, 0.0, True,
        f"5y PB 中位={pb_med:.2f};current PB={pb_now:.2f};"
        f"fair = current × {pb_med:.2f}/{pb_now:.2f}",
    )


# ─── 模型 6:简化剩余收益模型 RIM(高 ROE 特许经营)─────────────────
def _rim_fair_price(con, ticker: str, bps_now: float | None) -> ModelEstimate:
    """剩余收益模型:fair = BPS + Σ_t [(ROE_t - r) × BPS_t / (1+r)^t] + 永续。

    简化假设:
      - ROE 取 growth 表净资产收益率 3y 平均(若不可得降级)
      - BPS 增长率 b = ROE × 留存比例;留存比例 1 - 派息率 → 用 1 - 股息率/ROE 估算
      - 显式期 5 年,r=8%
      - 永续期 ROE 收敛到 12%(去除超额回报),终值用 Gordon
    """
    if bps_now is None or bps_now <= 0:
        return ModelEstimate("RIM", None, 0.0, False, "BPS 缺失或非正")
    # ROE 3y 平均(年报口径,避开当年 partial)
    rows = con.execute(
        "SELECT value FROM profitability WHERE ticker=? AND metric='净资产收益率(ROE)' "
        "AND value IS NOT NULL AND EXTRACT(MONTH FROM date)=12 "
        "ORDER BY date DESC LIMIT 4",
        [ticker],
    ).fetchall()
    if len(rows) < 3:
        return ModelEstimate("RIM", None, 0.0, False, f"ROE 年报不足 3 年(实 {len(rows)} 年)")
    roe_vals = [float(r[0]) for r in rows[1:4]]  # 跳过最新一年(可能未结)
    roe = sum(roe_vals) / len(roe_vals)
    if roe > 1:  # 容错:百分数 18.33 而非小数 0.18
        roe = roe / 100.0
    r = 0.08
    if roe <= r:
        return ModelEstimate(
            "RIM", None, 0.0, False,
            f"ROE({roe*100:.1f}%) ≤ r({r*100:.0f}%),无超额回报,模型不适用",
        )
    # 派息率粗估:取近 5 年股息率 / ROE 比,假设利润中分掉 d 部分
    yld_row = con.execute(
        "SELECT AVG(value) FROM valuation WHERE ticker=? AND metric='股息率' "
        "AND value > 0 AND date >= (CURRENT_DATE - INTERVAL 5 YEAR)",
        [ticker],
    ).fetchone()
    payout = 0.3  # 默认 30% 派息率
    if yld_row and yld_row[0]:
        y = float(yld_row[0]) / 100.0
        # 简化:payout ≈ y × PB_med / ROE — 实际此处用经验值即可
        payout = max(0.0, min(0.7, y * 5 / roe))  # 粗估,cap [0, 70%]
    retention = 1 - payout
    g = roe * retention  # BPS 增长率
    # 5 期显式 + 永续(永续 ROE 降到 12%,留存不变)
    bps_t = bps_now
    pv_resid = 0.0
    for t in range(1, 6):
        resid = (roe - r) * bps_t  # 第 t 期剩余收益
        pv_resid += resid / (1 + r) ** t
        bps_t = bps_t * (1 + g)
    # 永续:ROE → 0.12(去 alpha),g 重算
    roe_term = 0.12
    g_term = roe_term * retention
    if g_term >= r:
        terminal = 0.0  # 谨慎处理
    else:
        resid_term = (roe_term - r) * bps_t
        terminal = (resid_term / (r - g_term)) / (1 + r) ** 5
    fair = bps_now + pv_resid + terminal
    return ModelEstimate(
        "RIM", fair, 0.0, True,
        f"BPS={bps_now:.2f};ROE 3y avg={roe*100:.1f}%;payout={payout*100:.0f}%;"
        f"g={g*100:.1f}%;5期剩余收益+永续(ROE→12%);r=8%",
    )


# ─── 模型 4:历史 PE 中位回归 ─────────────────────────────────────────
def _pe_hist_fair_price(con, ticker: str, current_price: float, pe_ttm: float) -> ModelEstimate:
    """公司自身近 5 年 PE-TTM 中位 → fair = current × (pe_med5y / pe_ttm)。

    用于护城河/特许经营公司:Graham/PEG/DDM 都吃不下品牌定价权,
    用自身估值带做"回归到自己长期水位"是更现实的合理价基线。
    """
    row = con.execute(
        "SELECT MEDIAN(value), COUNT(*) FROM valuation "
        "WHERE ticker=? AND metric='PE-TTM' AND value > 0 "
        "AND date >= (CURRENT_DATE - INTERVAL 5 YEAR)",
        [ticker],
    ).fetchone()
    if row is None or row[0] is None or row[1] is None or row[1] < 300:
        return ModelEstimate(
            "PE_hist", None, 0.0, False,
            f"近 5y PE-TTM 样本不足({row[1] if row else 0} 个交易日,需 ≥300)",
        )
    pe_med = float(row[0])
    if pe_ttm <= 0:
        return ModelEstimate("PE_hist", None, 0.0, False, "当前 PE-TTM ≤ 0")
    fair = current_price * (pe_med / pe_ttm)
    return ModelEstimate(
        "PE_hist", fair, 0.0, True,
        f"5y PE-TTM 中位={pe_med:.1f};current PE={pe_ttm:.1f};"
        f"fair = current × {pe_med:.1f}/{pe_ttm:.1f}",
    )


# ─── 主入口 ────────────────────────────────────────────────────────────
# 不在此层缓存:内部 sub-functions 各自被 mock,函数级缓存会绕过测试 patch。
# 调用方(hero/block_a)如需 P0 提速,在 wrapper 层加 cache。
def compute_next_quarter_range(
    ticker: str,
    name: str = "",
    lynch_type: str | None = None,
    db_path: Path | str = DB_PATH,
    _mtime: float = 0.0,
) -> PriceRange:
    """下季度合理价格区间。lynch_type 缺时用 default 权重。"""
    ticker = _normalize_ticker(ticker)

    # 模型 1:Graham(同时供 current_price / pe_ttm)
    fp: FairPriceRange = compute_fair_range(ticker, name=name, db_path=db_path)
    current = fp.current_price
    pe_ttm = fp.pe_ttm
    as_of = fp.as_of

    graham_est = ModelEstimate(
        "Graham", fp.graham_number, 0.0,
        bool(fp.verified and fp.graham_number is not None),
        f"√(22.5×EPS×BPS);EPS={fp.eps_ttm:.2f},BPS={fp.bps:.2f}"
        if fp.verified else (fp.skip_reason or "Graham 不可得"),
    )

    # 模型 2-6 需要 current_price / pe_ttm
    if current is None or pe_ttm is None or pe_ttm <= 0:
        peg_est = ModelEstimate("PEG=1", None, 0.0, False, "current_price / pe_ttm 缺失")
        ddm_est = ModelEstimate("Gordon DDM", None, 0.0, False, "current_price 缺失")
        pe_hist_est = ModelEstimate("PE_hist", None, 0.0, False, "current_price / pe_ttm 缺失")
        pb_hist_est = ModelEstimate("PB_hist", None, 0.0, False, "current_price 缺失")
        rim_est = ModelEstimate("RIM", None, 0.0, False, "current_price 缺失")
    else:
        con = get_conn(str(db_path))
        try:
            peg_est = _peg_fair_price(con, ticker, current, pe_ttm)
            ddm_est = _gordon_fair_price(con, ticker, current)
            pe_hist_est = _pe_hist_fair_price(con, ticker, current, pe_ttm)
            pb_hist_est = _pb_hist_fair_price(con, ticker, current, fp.pb)
            rim_est = _rim_fair_price(con, ticker, fp.bps)
        finally:
            pass  # get_conn 单例,不关
    # 按 lynch_type 取权重
    base_w = _WEIGHTS_BY_TYPE.get((lynch_type or "").lower(), _DEFAULT_WEIGHTS)
    raw = [
        (graham_est, base_w[0]),
        (peg_est, base_w[1]),
        (ddm_est, base_w[2]),
        (pe_hist_est, base_w[3]),
        (pb_hist_est, base_w[4]),
        (rim_est, base_w[5]),
    ]
    available = [(m, w) for m, w in raw if m.fair_price is not None and m.fair_price > 0]
    notes: list[str] = []
    for m, _w in raw:
        if m.fair_price is None or m.fair_price <= 0:
            notes.append(f"{m.name} 降级:{m.note}")

    if not available:
        return PriceRange(
            ticker=ticker, name=name, current_price=current,
            floor=None, mid=None, ceiling=None,
            verdict_code="na", verdict_label="⚪ 不适用",
            models=[graham_est, peg_est, ddm_est, pe_hist_est, pb_hist_est, rim_est],
            notes=notes or ["六模型均不可得"], as_of=as_of,
        )

    # 归一化权重
    w_sum = sum(w for _, w in available)
    for m, w in available:
        m.weight = w / w_sum if w_sum > 0 else 1 / len(available)

    # floor/mid/ceiling 都只纳入归一化权重 ≥ 0.10 的模型:
    # - 避免失效模型(低股息股的 DDM)用极值拉到不合理的区间下/上沿(立讯 ¥10 floor)
    # - 保证 floor ≤ mid ≤ ceiling 几何一致(否则 verdict 区间逻辑会断裂)
    qualified_models = [m for m, _ in available if m.weight >= 0.10]
    if qualified_models:
        prices = [m.fair_price for m in qualified_models]
        floor = min(prices)
        ceiling = max(prices)
        # mid 在 qualified 内重新归一化加权
        w_sub = sum(m.weight for m in qualified_models)
        mid = sum(m.fair_price * m.weight / w_sub for m in qualified_models)
    else:
        prices = [m.fair_price for m, _ in available]
        floor = min(prices)
        ceiling = max(prices)
        mid = sum(m.fair_price * m.weight for m, _ in available)

    # verdict
    if current is None:
        code, label = "na", "⚪ 当前价未知"
    elif current < floor:
        code, label = "below_floor", "🟢🟢 区间下沿之下,显著低估"
    elif current <= mid:
        code, label = "in_lower", "🟢 区间内偏低,可分批"
    elif current <= ceiling:
        code, label = "in_upper", "🟡 区间内偏高,谨慎"
    else:
        code, label = "above_ceiling", "🔴 区间上沿之上,高估"

    return PriceRange(
        ticker=ticker, name=name, current_price=current,
        floor=floor, mid=mid, ceiling=ceiling,
        verdict_code=code, verdict_label=label,
        models=[graham_est, peg_est, ddm_est, pe_hist_est, pb_hist_est, rim_est],
        notes=notes, as_of=as_of,
    )


# ─── 按流派单一方法估值(决策中心持仓表使用)──────────────────────────
# 设计原则:每个流派只跑该流派最经典的一个公式,带合理 cap;
# 避免 compute_next_quarter_range 多模型加权对极端增长/股息股的失真。

@dataclass
class SchoolFair:
    ticker: str
    name: str
    school: str               # 价值 / 成长 / 周期 / 防御
    method: str               # 用到的公式名(展示)
    fair: float | None        # 单点公允价
    low: float | None         # fair × 0.85(15% 安全边际下沿)
    high: float | None        # fair × 1.15
    current: float | None
    verdict_code: str         # "below_low" / "in_band" / "above_high" / "na"
    verdict_label: str
    note: str                 # 一句话公式细节


def _verdict(current: float | None, fair: float | None) -> tuple[str, str]:
    if current is None or fair is None or fair <= 0:
        return "na", "⚪ 不适用"
    ratio = current / fair
    if ratio < 0.85:
        return "below_low", "🟢🟢 显著低估"
    if ratio <= 1.0:
        return "in_band", "🟢 区间内偏低"
    if ratio <= 1.15:
        return "in_band", "🟡 区间内偏高"
    return "above_high", "🔴 显著高估"


def _latest(con, table: str, ticker: str, metric: str) -> float | None:
    row = con.execute(
        f"SELECT value FROM {table} WHERE ticker=? AND metric=? "
        f"AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _net_profit_cagr(con, ticker: str, years: int) -> float | None:
    """年报口径净利 N 年 CAGR;end 取倒数第二份年报(避开当年 partial)."""
    rows = con.execute(
        "SELECT EXTRACT(YEAR FROM date)::INTEGER, value FROM growth "
        "WHERE ticker=? AND metric='归属于母公司普通股股东的净利润' "
        "  AND value IS NOT NULL AND EXTRACT(MONTH FROM date)=12 "
        "ORDER BY date DESC LIMIT ?",
        [ticker, years + 2],
    ).fetchall()
    if len(rows) < years + 1:
        return None
    end_v, start_v = rows[1][1], rows[years][1]
    if not end_v or not start_v or end_v <= 0 or start_v <= 0:
        return None
    return (end_v / start_v) ** (1 / years) - 1


def _pb_median_10y(con, ticker: str) -> float | None:
    row = con.execute(
        "SELECT MEDIAN(value) FROM valuation WHERE ticker=? AND metric='PB' "
        "AND value > 0 AND date >= (CURRENT_DATE - INTERVAL 10 YEAR)",
        [ticker],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def compute_by_school(ticker: str, school: str, name: str = "",
                       db_path: Path | str = DB_PATH) -> SchoolFair:
    """按流派选公式,返回单点公允价 + ±15% 区间。

    - 价值 → Graham 增长版 V = EPS × min(15, 8.5 + g_pct);g 上限 12%(防御型 PE 红线 15)
    - 成长 → PEG=1 上限版 fair_PE = clamp(g_3y%, 10, 35);fair = EPS × fair_PE
    - 周期 → PB 10y 中位回归 fair = BPS × PB_10y_median
    - 防御 → 股息率回归 fair = current × (current_yield / 4%);target_yield=4%
    """
    school = (school or "").strip()
    ticker = (ticker or "").strip().zfill(6) if (ticker or "").isdigit() else ticker
    con = get_conn(str(db_path))
    if con is None:
        return SchoolFair(ticker, name, school, "—", None, None, None, None,
                          "na", "⚪ 不适用", "DuckDB 不可用")

    # P0-3:valuation 表无 EPS-TTM/BPS/收盘价 — 复用 fair_price.compute_fair_range
    # 它已基于"市值÷总股本""真实价÷PE/PB"反推 current/eps/bps,口径一致
    fp = compute_fair_range(ticker, name=name, db_path=db_path)
    current = fp.current_price
    eps = fp.eps_ttm
    bps = fp.bps

    if school == "价值":
        # Graham 增长版:V = EPS × (8.5 + 2g);PE 硬上限 15(Graham 防御型红线)
        if eps is None or eps <= 0:
            note = "EPS-TTM 缺失或非正,Graham 不适用"
            fair = None
        else:
            g = _net_profit_cagr(con, ticker, 3) or 0.0
            g_capped = max(0.0, min(g, 0.12))  # cap 12%
            fair_pe = min(15.0, 8.5 + 2 * g_capped * 100)
            fair = eps * fair_pe
            note = (f"Graham 增长版:EPS={eps:.2f} × min(15, 8.5+2g)={fair_pe:.1f}"
                    f"(3y CAGR={g*100:.1f}% capped {g_capped*100:.1f}%)")
        method = "Graham 增长版"

    elif school == "成长":
        # PEG=1 上限版:fair_PE = clamp(g_pct, 10, 35)
        if eps is None or eps <= 0:
            note = "EPS-TTM 缺失或非正,PEG 不适用"
            fair = None
        else:
            g = _net_profit_cagr(con, ticker, 3)
            if g is None or g <= 0:
                note = f"净利 3y CAGR={'N/A' if g is None else f'{g*100:.1f}%'} ≤ 0,PEG 不适用"
                fair = None
            else:
                fair_pe = max(10.0, min(g * 100, 35.0))
                fair = eps * fair_pe
                note = (f"PEG=1 上限版:EPS={eps:.2f} × clamp(3y CAGR {g*100:.1f}%, 10, 35)"
                        f"={fair_pe:.1f}")
        method = "PEG=1 上限版"

    elif school == "周期":
        # PB 10y 中位回归:fair = BPS × PB_10y_median
        pb_med = _pb_median_10y(con, ticker)
        if bps is None or bps <= 0 or pb_med is None:
            note = f"BPS={bps} / PB 10y 中位={pb_med},数据缺失"
            fair = None
        else:
            fair = bps * pb_med
            note = f"PB 中位回归:BPS={bps:.2f} × PB 10y 中位 {pb_med:.2f} = {fair:.2f}"
        method = "PB 10y 中位回归"

    elif school == "防御":
        # 股息率回归:fair = current × (current_yield / 4%)
        yld = _latest(con, "valuation", ticker, "股息率")
        if yld is None or yld <= 0 or current is None:
            note = f"股息率={yld} 缺失或非正,模型不适用"
            fair = None
        else:
            if yld > 1: yld = yld / 100.0  # 理杏仁 3.78 = 3.78%
            target = 0.04
            fair = current * (yld / target)
            note = f"股息率回归:当前 {yld*100:.2f}% → target {target*100:.0f}%;fair = current × yld/target"
        method = "股息率回归 (target 4%)"

    else:
        return SchoolFair(ticker, name, school, "—", None, None, current,
                          "na", "⚪ 不适用", f"未知流派「{school}」")

    if fair is None or fair <= 0:
        return SchoolFair(ticker, name, school, method, None, None, None, current,
                          "na", "⚪ 不适用", note)
    low, high = fair * 0.85, fair * 1.15
    code, label = _verdict(current, fair)
    return SchoolFair(ticker, name, school, method, fair, low, high, current,
                      code, label, note)


__all__ = [
    "ModelEstimate", "PriceRange", "compute_next_quarter_range",
    "SchoolFair", "compute_by_school",
]
