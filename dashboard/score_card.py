"""6 维 0-100 评分函数 + 雷达/卡片所需数据装配。

设计:
- valuation:   PE-TTM 全周期分位反向 → 分位越低分越高
- profitability: 最新 ROE 区间映射 (0% → 0, 25%+ → 100)
- growth:      营业收入 YoY 区间映射 (-10% → 0, +25% → 100)
- cashflow:    经营现金流/净利润比率 (0 → 30, 1.0 → 90, ≥1.2 → 100)
- safety:      资产负债率反向 (<=30% → 100, >=70% → 0;银行/保险跳过)
- strategies:  7 大师评分(piotroski/buffett/lynch/graham/altman/greenblatt/damodaran)
               按规则归一化求均值,0-100;调用 .tools/score/multi_master.run_one

综合分 = 0.20·估值 + 0.20·盈利 + 0.12·成长 + 0.13·现金流 + 0.15·安全 + 0.20·策略
       (任一维度缺失则按 50 中性占位,不污染其他维度)

不依赖 streamlit,可单跑离线验证:
    python3 .tools/dashboard/score_card.py 600519
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = ROOT / ".tools" / "mcp"
SCORE_DIR = ROOT / ".tools" / "score"
RULES_DIR = ROOT / ".tools" / "rules"
for _p in (MCP_DIR, SCORE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import duckdb  # noqa: E402

DB_PATH = ROOT / "data" / "preson.duckdb"

DIM_WEIGHTS = {
    "valuation": 0.20,
    "profitability": 0.20,
    "growth": 0.12,
    "cashflow": 0.13,
    "safety": 0.15,
    "strategies": 0.20,
}

DIM_LABEL = {
    "valuation": "估值",
    "profitability": "盈利",
    "growth": "成长",
    "cashflow": "现金流",
    "safety": "安全",
    "strategies": "策略",
}

FINANCIAL_CATEGORIES = {"bank", "insurance"}


@dataclass
class DimResult:
    score: float | None
    raw: float | None
    label: str
    note: str
    badge: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "raw": self.raw,
            "label": self.label,
            "note": self.note,
            "badge": self.badge,
        }


@dataclass
class CompanyScore:
    ticker: str
    name: str
    category: str
    dims: dict[str, DimResult] = field(default_factory=dict)
    overall: float | None = None
    overall_badge: str = ""

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "category": self.category,
            "overall": self.overall,
            "overall_badge": self.overall_badge,
            "dims": {k: v.to_dict() for k, v in self.dims.items()},
        }


# ───── 区间映射 ─────────────────────────────────────────────────────────

def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _linear(value: float, lo: float, hi: float) -> float:
    """value 在 [lo, hi] 线性映射到 [0, 100],外溢截断。"""
    if hi == lo:
        return 50.0
    return _clip((value - lo) / (hi - lo) * 100.0)


def score_valuation(pe_pct: float | None) -> DimResult:
    """pe_pct 0-1 全周期分位,越低越好。"""
    if pe_pct is None:
        return DimResult(None, None, "估值", "PE 分位无数据", "⚪")
    s = _clip(100.0 * (1.0 - pe_pct))
    if pe_pct < 0.20:
        badge, note = "🟢", f"低位 {pe_pct:.0%}"
    elif pe_pct < 0.50:
        badge, note = "🟢", f"偏低 {pe_pct:.0%}"
    elif pe_pct <= 0.80:
        badge, note = "🟡", f"中性 {pe_pct:.0%}"
    else:
        badge, note = "🔴", f"高位 {pe_pct:.0%}"
    return DimResult(s, pe_pct, "估值", f"PE 分位 · {note}", badge)


def score_profitability(roe: float | None) -> DimResult:
    if roe is None:
        return DimResult(None, None, "盈利", "ROE 无数据", "⚪")
    s = _linear(roe, 0.0, 0.25)
    if roe >= 0.20:
        badge, note = "🟢", f"ROE {roe:.1%} 强"
    elif roe >= 0.12:
        badge, note = "🟢", f"ROE {roe:.1%} 良"
    elif roe >= 0.06:
        badge, note = "🟡", f"ROE {roe:.1%} 平"
    else:
        badge, note = "🔴", f"ROE {roe:.1%} 弱"
    return DimResult(s, roe, "盈利", note, badge)


def score_growth(yoy: float | None) -> DimResult:
    """营业收入累积同比(%, 已是百分比形式如 12.3 表示 12.3%)。"""
    if yoy is None:
        return DimResult(None, None, "成长", "营收 YoY 无数据", "⚪")
    yoy_frac = yoy / 100.0 if abs(yoy) > 1.5 else yoy  # 兼容 0.12 与 12.0 两种表示
    s = _linear(yoy_frac, -0.10, 0.25)
    if yoy_frac >= 0.15:
        badge, note = "🟢", f"营收 YoY {yoy_frac:.1%} 高速"
    elif yoy_frac >= 0.05:
        badge, note = "🟢", f"营收 YoY {yoy_frac:.1%} 稳健"
    elif yoy_frac >= -0.02:
        badge, note = "🟡", f"营收 YoY {yoy_frac:.1%} 平淡"
    else:
        badge, note = "🔴", f"营收 YoY {yoy_frac:.1%} 下滑"
    return DimResult(s, yoy_frac, "成长", note, badge)


def score_cashflow(cfo_to_ni: float | None) -> DimResult:
    if cfo_to_ni is None:
        return DimResult(None, None, "现金流", "CFO/NI 无数据", "⚪")
    if cfo_to_ni >= 1.2:
        s = 100.0
    elif cfo_to_ni >= 1.0:
        s = 90.0 + (cfo_to_ni - 1.0) / 0.2 * 10.0
    elif cfo_to_ni >= 0.0:
        s = 30.0 + cfo_to_ni / 1.0 * 60.0
    else:
        s = _clip(30.0 + cfo_to_ni * 60.0)  # 负数线性掉到 0
    if cfo_to_ni >= 1.0:
        badge, note = "🟢", f"CFO/NI {cfo_to_ni:.2f} 健康"
    elif cfo_to_ni >= 0.6:
        badge, note = "🟡", f"CFO/NI {cfo_to_ni:.2f} 偏弱"
    else:
        badge, note = "🔴", f"CFO/NI {cfo_to_ni:.2f} 警示"
    return DimResult(s, cfo_to_ni, "现金流", note, badge)


def score_safety(debt_ratio: float | None, category: str) -> DimResult:
    """资产负债率(0-1 或 0-100)。银行/保险跳过。"""
    if category in FINANCIAL_CATEGORIES:
        return DimResult(None, None, "安全", f"{category} 行业不适用通用规则", "⚪")
    if debt_ratio is None:
        return DimResult(None, None, "安全", "负债率无数据", "⚪")
    dr = debt_ratio / 100.0 if debt_ratio > 1.5 else debt_ratio
    s = _clip(100.0 * (0.70 - dr) / 0.40)
    if dr <= 0.30:
        badge, note = "🟢", f"负债率 {dr:.1%} 极低"
    elif dr <= 0.50:
        badge, note = "🟢", f"负债率 {dr:.1%} 低"
    elif dr <= 0.65:
        badge, note = "🟡", f"负债率 {dr:.1%} 中"
    else:
        badge, note = "🔴", f"负债率 {dr:.1%} 高"
    return DimResult(s, dr, "安全", note, badge)


def score_strategies(ticker: str, year: int) -> tuple[DimResult, dict]:
    """
    跑 7 大师评分 → 0-100 均分。
    返回 (DimResult, {master: {score, valid, total, normalized_pct, badge}})。
    """
    try:
        import multi_master as mm
    except Exception as e:
        return DimResult(None, None, "策略", f"multi_master 不可用: {e}", "⚪"), {}

    yamls = mm.list_executable_yamls()
    per_master: dict[str, dict] = {}
    pcts: list[float] = []
    for yp in yamls:
        master = yp.stem
        res = mm.run_one(yp, ticker, year)
        if res is None:
            per_master[master] = {"score": None, "valid": 0, "total": 0, "pct": None, "badge": "⚪"}
            continue
        score, valid, total = res
        if total <= 0:
            per_master[master] = {"score": score, "valid": valid, "total": total, "pct": None, "badge": "⚪"}
            continue
        pct = score / total * 100.0  # 0-100
        if valid >= max(2, int(total * 0.5)):
            pcts.append(pct)
        if pct >= 75: badge = "🟢"
        elif pct >= 50: badge = "🟡"
        elif pct >= 30: badge = "🟠"
        else: badge = "🔴"
        per_master[master] = {
            "score": int(round(score)), "valid": valid, "total": total,
            "pct": round(pct, 1), "badge": badge,
        }

    if not pcts:
        return DimResult(None, None, "策略", f"7 大师全部数据不足({year}年)", "⚪"), per_master
    avg = sum(pcts) / len(pcts)
    if avg >= 75: badge, tag = "🟢", "强势"
    elif avg >= 60: badge, tag = "🟢", "良好"
    elif avg >= 45: badge, tag = "🟡", "中性"
    elif avg >= 30: badge, tag = "🟠", "偏弱"
    else: badge, tag = "🔴", "警示"
    note = f"{len(pcts)}/{len(yamls)} 大师可比 · 均 {avg:.0f}/100 · {tag}"
    return DimResult(round(avg, 1), avg / 100.0, "策略", note, badge), per_master


def master_matrix(tickers: list[str], year: int | None = None) -> list[dict]:
    """
    dash-03 · 跨公司 × 多大师评分矩阵(纯数据,无 UI)。

    返回:
      [
        {"ticker": "600519", "name": "贵州茅台",
         "masters": {"piotroski": {"score": 8, "total": 9, "valid": 9, "pct": 88.9, "badge": "🟢"},
                     "graham": {...}, "lynch": {...}, "buffett": {...}, ...}},
        ...
      ]
    """
    from datetime import date as _date
    y = year or (_date.today().year - 1)
    out: list[dict] = []
    con = _conn()
    try:
        for t in tickers:
            row = con.execute(
                "SELECT name FROM companies WHERE ticker = ?", [t]
            ).fetchone()
            name = row[0] if row else t
            _, masters = score_strategies(t, y)
            out.append({"ticker": t, "name": name, "masters": masters})
    finally:
        con.close()
    return out


def overall_score(dims: dict[str, DimResult]) -> tuple[float, str]:
    """加权平均;缺失维度用 50 占位(不夸大优势也不放大劣势)。"""
    total = 0.0
    for k, w in DIM_WEIGHTS.items():
        v = dims.get(k)
        s = v.score if (v and v.score is not None) else 50.0
        total += w * s
    if total >= 75:
        badge = "🟢"
    elif total >= 60:
        badge = "🟡"
    elif total >= 45:
        badge = "🟠"
    else:
        badge = "🔴"
    return round(total, 1), badge


# ───── 数据访问 ────────────────────────────────────────────────────────

def _conn(db_path: Path = DB_PATH):
    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB 不存在: {db_path}")
    return duckdb.connect(str(db_path), read_only=True)


def _latest_value(con, table: str, ticker: str, metric: str) -> float | None:
    row = con.execute(
        f"SELECT value FROM {table} "
        f"WHERE ticker = ? AND metric = ? AND value IS NOT NULL "
        f"ORDER BY date DESC LIMIT 1",
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _pe_percentile(con, ticker: str, window_years: int = 10) -> float | None:
    """全周期 PE-TTM 分位 (0-1)。"""
    from datetime import date, timedelta

    cutoff = date.today() - timedelta(days=365 * window_years)
    row = con.execute(
        """
        WITH series AS (
            SELECT value FROM valuation
            WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
              AND date >= ?
        ),
        latest AS (
            SELECT value FROM valuation
            WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
        )
        SELECT
            (SELECT COUNT(*) FROM series WHERE value <= (SELECT value FROM latest)) * 1.0
            / NULLIF((SELECT COUNT(*) FROM series), 0)
        """,
        [ticker, cutoff, ticker],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def compute_dimensions(
    ticker: str,
    *,
    db_path: Path = DB_PATH,
    pct_window: str = "10y",
    strategies_year: int | None = None,
) -> CompanyScore:
    """主入口:对一家公司返回 6 维评分 + 综合分 + 各大师明细。"""
    from datetime import date as _date
    win_years = {"10y": 10, "5y": 5, "3y": 3, "1y": 1, "all": 50}.get(pct_window, 10)
    year = strategies_year or (_date.today().year - 1)
    con = _conn(db_path)
    try:
        info = con.execute(
            "SELECT name, category FROM companies WHERE ticker = ?", [ticker]
        ).fetchone()
        if info is None:
            raise ValueError(f"ticker {ticker} 不在 companies 表")
        name, category = info[0], (info[1] or "")

        pe_pct = _pe_percentile(con, ticker, win_years)
        roe = _latest_value(con, "profitability", ticker, "净资产收益率(ROE)")
        rev_yoy = _latest_value(con, "growth", ticker, "累积同比")
        cfo_to_ni = _latest_value(
            con, "cashflow", ticker,
            "经营活动产生的现金流量净额对净利润的比率",
        )
        debt = _latest_value(con, "safety", ticker, "资产负债率")
    finally:
        con.close()

    strat_dim, masters_detail = score_strategies(ticker, year)
    dims = {
        "valuation": score_valuation(pe_pct),
        "profitability": score_profitability(roe),
        "growth": score_growth(rev_yoy),
        "cashflow": score_cashflow(cfo_to_ni),
        "safety": score_safety(debt, category),
        "strategies": strat_dim,
    }
    overall, badge = overall_score(dims)
    score = CompanyScore(
        ticker=ticker, name=name, category=category,
        dims=dims, overall=overall, overall_badge=badge,
    )
    score.masters = masters_detail  # type: ignore[attr-defined]
    score.strategies_year = year     # type: ignore[attr-defined]
    return score


# ───── CLI 离线验证 ────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════
# 综合健康度 + 简化大师 + 中国本土警示(2026-05-04 v2.0 知识体系迭代)
# 公式来源:Altman Z'' / Greenblatt MF / 巴菲特经典指标 / Sloan Ratio / A 股暴雷归因
# 设计:不依赖 BS 三件套(W2 数据广度补齐前的可行 MVP);BS 数据齐后可升级
# ═══════════════════════════════════════════════════════════════════════


def _series_recent(con, table: str, ticker: str, metric: str, n: int = 5) -> list[float]:
    rows = con.execute(
        f"SELECT value FROM {table} "
        f"WHERE ticker=? AND metric=? AND value IS NOT NULL "
        f"ORDER BY date DESC LIMIT ?",
        [ticker, metric, n],
    ).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None]


def simple_altman_rating(con, ticker: str) -> dict:
    """简化 Altman 风险评级(用现有衍生指标代理 BS,等 W2 拉到 BS 后升级真版 Z'')。

    4 项代理:
      A: 资产负债率 — 反向(< 50% safe / 50-70% gray / >70% danger)
      B: 流动比率   — 正向(> 2 safe / 1-2 gray / <1 danger)
      C: ROA 持续   — 最近 3 年都 > 5% safe / 都 > 0 gray / 任一 < 0 danger
      D: 经营现金流/净利润比 — 持续 > 0.7 safe / 0.5-0.7 gray / < 0.5 danger

    每项 0/1/2 分,总分 0-8;> 6 = safe / 4-6 = gray / < 4 = danger
    """
    debt_ratio = _latest_value(con, "safety", ticker, "资产负债率")
    current_ratio = _latest_value(con, "safety", ticker, "流动比率")
    roa_3y = _series_recent(con, "profitability", ticker, "总资产收益率(ROA)", 3)
    cfo_ni_3y = _series_recent(con, "cashflow", ticker,
                                "经营活动产生的现金流量净额对净利润的比率", 3)

    def _bin(score_value: float | None, safe_lo: float, gray_lo: float,
             reverse: bool = False) -> int:
        if score_value is None:
            return 0
        if reverse:
            if score_value <= safe_lo:
                return 2
            if score_value <= gray_lo:
                return 1
            return 0
        if score_value >= safe_lo:
            return 2
        if score_value >= gray_lo:
            return 1
        return 0

    sA = _bin(debt_ratio, 0.5, 0.7, reverse=True)
    sB = _bin(current_ratio, 2.0, 1.0)
    if not roa_3y:
        sC = 0
    elif all(v > 0.05 for v in roa_3y):
        sC = 2
    elif all(v > 0 for v in roa_3y):
        sC = 1
    else:
        sC = 0
    if not cfo_ni_3y:
        sD = 0
    elif all(v > 0.7 for v in cfo_ni_3y):
        sD = 2
    elif all(v > 0.5 for v in cfo_ni_3y):
        sD = 1
    else:
        sD = 0

    total = sA + sB + sC + sD
    if total >= 6:
        rating, badge = "safe", "🟢"
    elif total >= 4:
        rating, badge = "gray", "🟡"
    else:
        rating, badge = "danger", "🔴"

    return {
        "score": total,
        "max": 8,
        "rating": rating,
        "badge": badge,
        "details": {
            "杠杆 (资产负债率)": (debt_ratio, sA),
            "流动性 (流动比率)": (current_ratio, sB),
            "ROA 持续性 (3年)": (roa_3y, sC),
            "现金流真实度 (3年)": (cfo_ni_3y, sD),
        },
    }


def simple_greenblatt_score(con, ticker: str) -> dict:
    """简化 Greenblatt 综合分:好生意(ROE)+ 便宜(PE 分位反向)。

    完整版需 ROIC + EY,缺 BS 时用 ROE 代理 ROIC,1/PE 代理 EY。
    评分 0-100。
    """
    roe = _latest_value(con, "profitability", ticker, "净资产收益率(ROE)")
    # 估值口径(.config/数据更新规则.md):扣非主,GAAP 备
    pe = (_latest_value(con, "valuation", ticker, "PE-TTM(扣非)")
          or _latest_value(con, "valuation", ticker, "PE-TTM"))
    pe_pct = _pe_percentile(con, ticker, window_years=10)

    if roe is None or roe <= 0:
        roe_score = 0.0
    else:
        roe_score = _clip(_linear(roe * 100, 5, 30), 0, 100)
    if pe_pct is None:
        pe_score = 50.0
    else:
        pe_score = _clip(_linear(1 - pe_pct, 0.0, 0.8), 0, 100)
    combined = (roe_score + pe_score) / 2.0
    if combined >= 70:
        badge = "🟢"
    elif combined >= 50:
        badge = "🟡"
    else:
        badge = "🔴"
    return {
        "score": round(combined, 1),
        "badge": badge,
        "roe": roe,
        "roe_score": round(roe_score, 1),
        "pe": pe,
        "pe_pct_10y": pe_pct,
        "pe_score": round(pe_score, 1),
    }


def china_warnings(con, ticker: str) -> dict:
    """A 股本土暴雷预警 — 数据可得的 3 条(商誉/应收/存货 等 BS 拉齐后再加 5 条)。

    红牌(任一触发)→ 综合健康度 -2 分:
      1. 现金流真实度差:CFO/净利润比 < 0.7 持续 3 年(类康美/乐视)
      2. 高杠杆:资产负债率 > 70%
      3. ROE 连续下滑 3 年(经营恶化)
    """
    warnings: list[dict] = []

    cfo_ni = _series_recent(con, "cashflow", ticker,
                            "经营活动产生的现金流量净额对净利润的比率", 3)
    if cfo_ni and len(cfo_ni) >= 3 and all(v < 0.7 for v in cfo_ni):
        warnings.append({
            "code": "CFO_QUALITY_LOW",
            "level": "🔴",
            "title": "现金流质量持续偏低",
            "detail": f"CFO/净利润比 3 年值 {[round(v, 2) for v in cfo_ni]} 全 < 0.7",
            "reference": "类康美药业 / 乐视网 财务粉饰征兆",
        })

    debt_ratio = _latest_value(con, "safety", ticker, "资产负债率")
    if debt_ratio is not None and debt_ratio > 0.70:
        warnings.append({
            "code": "HIGH_LEVERAGE",
            "level": "🟠",
            "title": "高杠杆",
            "detail": f"资产负债率 {debt_ratio:.1%} > 70%(银行/保险/房地产除外)",
            "reference": "Altman Z'' D 项关键警示",
        })

    roe_5y = _series_recent(con, "profitability", ticker, "净资产收益率(ROE)", 5)
    if len(roe_5y) >= 3:
        # roe_5y 从最新到旧 → 反转为时间正序看趋势
        seq = list(reversed(roe_5y[:3]))
        if all(seq[i] > seq[i + 1] for i in range(len(seq) - 1)):
            warnings.append({
                "code": "ROE_DECLINING",
                "level": "🟡",
                "title": "ROE 连续下滑",
                "detail": f"近 3 年 ROE {[f'{v:.1%}' for v in seq]} 单调下降",
                "reference": "经营恶化早期信号",
            })

    return {
        "count": len(warnings),
        "items": warnings,
        "any_red": any(w["level"] == "🔴" for w in warnings),
    }


def health_score(ticker: str) -> dict:
    """综合健康度 0-10 分 + 三档结论。

    输入(已有):
      - 6 维评分(估值/盈利/成长/现金流/安全/策略)
      - 大师矩阵(已有 multi_master 4-7 套)
      - 简化 Altman 评级
      - 简化 Greenblatt 分
      - 中国警示

    权重(总分 10):
      价值层(40%):  estimate * 4 / 100
                     综合估值=(估值维度 + Greenblatt PE 部分) / 2
      质量层(25%):  (盈利 + 现金流) / 2 * 2.5 / 100
      安全层(20%):  Altman 评级映射 0/1/2 分
                     (safe→2 / gray→1 / danger→0)
      策略层(15%):  策略维度 * 1.5 / 100
      警示扣分:每红牌 -2,每黄牌 -1,封底 0
    """
    from datetime import date as _date

    s = compute_dimensions(ticker)

    con = _conn()
    try:
        altman = simple_altman_rating(con, ticker)
        greenblatt = simple_greenblatt_score(con, ticker)
        warns = china_warnings(con, ticker)
    finally:
        con.close()

    # 各层分数
    v_score = (s.dims["valuation"].score or 50) / 100  # 0-1
    q_score = ((s.dims["profitability"].score or 50)
               + (s.dims["cashflow"].score or 50)) / 200  # 0-1
    a_score = altman["score"] / altman["max"]  # 0-1
    p_score = (s.dims["strategies"].score or 50) / 100  # 0-1

    base = (v_score * 4.0) + (q_score * 2.5) + (a_score * 2.0) + (p_score * 1.5)
    # 警示扣分
    deduct = 0.0
    for w in warns["items"]:
        if w["level"] == "🔴":
            deduct += 2.0
        elif w["level"] == "🟠":
            deduct += 1.0
        elif w["level"] == "🟡":
            deduct += 0.5
    final = max(0.0, base - deduct)

    if final >= 7.5:
        verdict, badge = "强烈推荐(核心持仓候选)", "🟢"
    elif final >= 5.5:
        verdict, badge = "可配置(中等仓位)", "🟡"
    elif final >= 4.0:
        verdict, badge = "观察(等更好价格 / 数据)", "🟠"
    else:
        verdict, badge = "回避(警示叠加 / 健康度低)", "🔴"

    return {
        "ticker": ticker,
        "name": s.name,
        "score": round(final, 2),
        "max": 10.0,
        "badge": badge,
        "verdict": verdict,
        "year": _date.today().year - 1,
        "components": {
            "value (40%)": round(v_score * 4.0, 2),
            "quality (25%)": round(q_score * 2.5, 2),
            "safety (20%)": round(a_score * 2.0, 2),
            "strategy (15%)": round(p_score * 1.5, 2),
            "deduct": -round(deduct, 2),
        },
        "altman": altman,
        "greenblatt": greenblatt,
        "warnings": warns,
        "dims": {k: (v.score, v.badge) for k, v in s.dims.items()},
        "overall_legacy": (s.overall, s.overall_badge),
    }


PEERS_DB_PATH = ROOT / "data" / "peers.duckdb"


def industry_peers(ticker: str) -> list[dict]:
    """读独立 peers.duckdb 的 peers 表,返回 ticker 的 2 个对标公司基本信息。

    返回:[{"rank": 1, "peer_ticker", "peer_name", "peer_market_cap",
            "peer_pe", "peer_pb", "is_above_self", "industry_em"}, ...]
    表不存在或无数据时返回 []。
    """
    if not PEERS_DB_PATH.exists():
        return []
    try:
        con = duckdb.connect(str(PEERS_DB_PATH), read_only=True)
    except Exception:
        return []
    try:
        try:
            rows = con.execute(
                "SELECT rank, peer_ticker, peer_name, peer_market_cap, "
                "peer_pe, peer_pb, peer_roe, is_above_self, industry_em, "
                "self_market_cap "
                "FROM peers WHERE ticker = ? ORDER BY rank",
                [ticker],
            ).fetchall()
        except Exception:
            return []
        if not rows:
            return []
        return [
            {
                "rank": r[0],
                "peer_ticker": r[1],
                "peer_name": r[2],
                "peer_market_cap": r[3],
                "peer_pe": r[4],
                "peer_pb": r[5],
                "peer_roe": r[6],
                "is_above_self": r[7],
                "industry_em": r[8],
                "self_market_cap": r[9],
            }
            for r in rows
        ]
    finally:
        con.close()


def _print_one(s: CompanyScore) -> None:
    print(f"\n{'='*64}")
    print(f"  {s.name} ({s.ticker})  ·  category={s.category or '—'}")
    print(f"  ★ 综合 {s.overall_badge} {s.overall}/100")
    print(f"{'='*64}")
    for k in ["valuation", "profitability", "growth", "cashflow", "safety", "strategies"]:
        d = s.dims[k]
        score_str = f"{d.score:5.1f}" if d.score is not None else "  N/A"
        print(f"  {d.badge} {DIM_LABEL[k]:<5}  {score_str}  ·  {d.note}")
    masters = getattr(s, "masters", {})
    if masters:
        print(f"  ── 大师明细 (year={getattr(s, 'strategies_year', '?')}) ──")
        for m, info in masters.items():
            pct = f"{info['pct']:5.1f}%" if info.get("pct") is not None else "  N/A "
            sc_str = str(info["score"]) if info.get("score") is not None else "—"
            tot_str = str(info["total"]) if info.get("total") is not None else "—"
            print(f"    {info['badge']} {m:<11} {sc_str:>3}/{tot_str:<2}  ({pct}, valid={info.get('valid', 0)})")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="*", default=[],
                    help="ticker 代码;留空则跑全部 15 家")
    ap.add_argument("--window", default="10y")
    args = ap.parse_args()

    if args.ticker:
        targets = args.ticker
    else:
        with _conn() as con:
            targets = [r[0] for r in con.execute(
                "SELECT ticker FROM companies ORDER BY folder"
            ).fetchall()]

    for t in targets:
        try:
            _print_one(compute_dimensions(t, pct_window=args.window))
        except Exception as e:
            print(f"\n❌ {t}: {e}")
