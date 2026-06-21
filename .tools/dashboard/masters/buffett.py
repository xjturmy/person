"""巴菲特评分体系扩展模块 (v2.5)

五大功能:
  B2 — industry_alt_score / industry_alt_oe_score  排除行业替代评分
  B3 — compute_owner_earnings / simple_owner_earnings  OE 计算
  B4 — retained_earnings_breakdown  留存收益可视化接口
  B5 — load_qualitative_score / save_qualitative_score  护城河主观打分

口径约定:
  - 与 derived_metrics.py 共用 _conn / _yearly_series / _latest_value 约定
  - verified=True  →  直接用理杏仁原始字段,已对齐
  - verified=False →  本地估算或 P3 阻塞,等数据源补齐后升 True

数据库:data/preson.duckdb
配置文件:.config/buffett_qualitative.yaml
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple, Optional

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "preson.duckdb"
QUALITATIVE_PATH = ROOT / ".config" / "buffett_qualitative.yaml"

# 行业归属映射 (ticker → industry_type)
INDUSTRY_MAP: dict[str, str] = {
    "601336": "insurance",    # 新华保险
    "600036": "bank",         # 招商银行
    "300308": "high_rd_tech", # 中际旭创
    "600276": "high_rd_tech", # 恒瑞医药
    "002594": "high_rd_tech", # 比亚迪(高研发)
}


class DerivedResult(NamedTuple):
    """巴菲特扩展计算结果。"""
    value: float | None
    verified: bool
    note: str

    def __repr__(self) -> str:
        v = "None" if self.value is None else f"{self.value:.4f}"
        flag = "✅" if self.verified else "⚠️"
        return f"{flag} {v} ({self.note})"


# ═══════════════════════════════════════════════════════════════════════
# 内部 helpers
# ═══════════════════════════════════════════════════════════════════════

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _yearly_series(con, table: str, ticker: str, metric: str,
                   years_back: int = 10) -> list[tuple[int, float]]:
    """取年末(12-31)序列,按年份升序。返回 [(year, value), ...]。"""
    cutoff = (date.today() - timedelta(days=365 * (years_back + 1))).isoformat()
    rows = con.execute(
        f"""
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
          AND MONTH(date) = 12 AND DAY(date) = 31
          AND date >= ?
        ORDER BY date
        """,
        [ticker, metric, cutoff],
    ).fetchall()
    return [(int(y), float(v)) for y, v in rows]


def _latest_value(con, table: str, ticker: str, metric: str) -> float | None:
    row = con.execute(
        f"""
        SELECT value FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _cagr(series: list[tuple[int, float]], years: int) -> float | None:
    """给定年末序列,计算指定年数的 CAGR。首尾匹配。"""
    if len(series) < years + 1:
        return None
    end_year, end_val = series[-1]
    start_year_target = end_year - years
    start_match = [v for y, v in series if y == start_year_target]
    if not start_match:
        return None
    start_val = start_match[0]
    if start_val <= 0 or end_val <= 0:
        return None
    return (end_val / start_val) ** (1.0 / years) - 1.0


# ═══════════════════════════════════════════════════════════════════════
# B2 — 行业替代评分(industry_alternatives)
# ═══════════════════════════════════════════════════════════════════════

def industry_alt_oe_score(ticker: str, industry_type: str,
                           db_path: Path | str = DB_PATH) -> DerivedResult:
    """B2 主入口:按行业类型返回替代评分分档。

    bank        → PB-ROE 法:ROE / PB 比值分档 (verified=True)
    insurance   → EV/NBV 法:P3 阻塞,返回 None (verified=False)
    high_rd_tech→ R&D 还原 OE:占位,返回 None (verified=False)

    返回 DerivedResult(score_0_to_2, verified, note)
    """
    return industry_alt_score(ticker, industry_type, db_path)


def industry_alt_score(ticker: str, industry_type: str,
                        db_path: Path | str = DB_PATH) -> DerivedResult:
    """按行业类型路由到对应替代评分函数。"""
    if industry_type == "bank":
        return _bank_pb_roe_score(ticker, db_path)
    elif industry_type == "insurance":
        return DerivedResult(
            None, False,
            "P3 阻塞:理杏仁未提供保险 EV/NBV 字段,需从年报手工录入"
        )
    elif industry_type == "high_rd_tech":
        return _high_rd_tech_score(ticker, db_path)
    else:
        return DerivedResult(None, False, f"未知行业类型: {industry_type}")


def _bank_pb_roe_score(ticker: str, db_path: Path | str = DB_PATH) -> DerivedResult:
    """银行替代评分:ROE / PB 分档。

    比值 = ROE(最新年末) / PB(最新)
    grades: ≥0.15→2.0 / ≥0.12→1.5 / ≥0.10→1.0 / ≥0.07→0.5 / else→0
    """
    con = _conn(db_path)
    try:
        roe = _latest_value(con, "profitability", ticker, "净资产收益率(ROE)")
        pb = _latest_value(con, "valuation", ticker, "PB")
        if roe is None or pb is None or pb <= 0:
            return DerivedResult(
                None, False,
                f"数据缺失 ROE={roe}, PB={pb}"
            )
        ratio = roe / pb
        if ratio >= 0.15:
            score, grade = 2.0, "excellent"
        elif ratio >= 0.12:
            score, grade = 1.5, "good"
        elif ratio >= 0.10:
            score, grade = 1.0, "fair"
        elif ratio >= 0.07:
            score, grade = 0.5, "weak"
        else:
            score, grade = 0.0, "fail"
        return DerivedResult(
            score, True,
            f"银行 PB-ROE: ROE={roe:.3f} / PB={pb:.2f} = {ratio:.3f} → {grade}({score})"
        )
    finally:
        con.close()


def _high_rd_tech_score(ticker: str, db_path: Path | str = DB_PATH) -> DerivedResult:
    """高研发科技替代评分:R&D 资本化还原后的 OE(占位)。

    当前理杏仁 cashflow 表无独立 R&D 费用字段,返回 None + verified=False。
    数据齐后由 compute_owner_earnings_rd_adj 升级。
    """
    return DerivedResult(
        None, False,
        "占位:理杏仁 cashflow 无研发费用独立字段,OE_adj=NI+D&A+R&D-maint_capex 待补数据"
    )


# ═══════════════════════════════════════════════════════════════════════
# B3 — Owner Earnings 计算
# ═══════════════════════════════════════════════════════════════════════

def simple_owner_earnings(ticker: str,
                           years: int = 10,
                           db_path: Path | str = DB_PATH) -> DerivedResult:
    """简化版 OE = 自由现金流量(理杏仁直接字段)。

    等价于 CFO - CapEx,已在理杏仁 cashflow 表以「自由现金流量」名提供。
    verified=True

    返回 DerivedResult(oe_cagr_float, True, note)
    """
    con = _conn(db_path)
    try:
        series = _yearly_series(con, "cashflow", ticker, "自由现金流量", years_back=years + 2)
        oe_cagr = _cagr(series, years)
        if oe_cagr is not None:
            # 确定分档
            if oe_cagr >= 0.15:
                score = 2.0
            elif oe_cagr >= 0.10:
                score = 1.5
            elif oe_cagr >= 0.05:
                score = 1.0
            elif oe_cagr >= 0.0:
                score = 0.5
            else:
                score = 0.0
            return DerivedResult(
                oe_cagr, True,
                f"简化 OE CAGR({years}y)={oe_cagr*100:.1f}% → score={score} "
                f"(数据点={len(series)})"
            )

        # fallback: 尝试 5y CAGR
        if years > 5:
            oe_cagr_5 = _cagr(series, 5)
            if oe_cagr_5 is not None:
                if oe_cagr_5 >= 0.15:
                    score = 2.0
                elif oe_cagr_5 >= 0.10:
                    score = 1.5
                elif oe_cagr_5 >= 0.05:
                    score = 1.0
                elif oe_cagr_5 >= 0.0:
                    score = 0.5
                else:
                    score = 0.0
                return DerivedResult(
                    oe_cagr_5, True,
                    f"简化 OE 5y fallback CAGR={oe_cagr_5*100:.1f}% → score={score} "
                    f"(数据点={len(series)})"
                )

        return DerivedResult(
            None, False,
            f"自由现金流量数据不足(实有 {len(series)} 个年末点)"
        )
    finally:
        con.close()


def compute_owner_earnings(ticker: str,
                            db_path: Path | str = DB_PATH) -> DerivedResult:
    """完整版 OE = NI + D&A - maint_capex - ΔWWC(占位)。

    当前理杏仁 cashflow 表仅有 4 个 metric(无独立 D&A / maint_capex),
    完整公式无法直接计算。返回 None + verified=False。

    数据补齐路径:
      1. 理杏仁财报科目补「折旧摊销」「资本支出」「营运资金变化」
      2. 或从年报手工录入
    """
    con = _conn(db_path)
    try:
        # 尝试读取现有 cashflow 字段,评估覆盖状况
        cfo = _latest_value(con, "cashflow", ticker, "经营活动产生的现金流量净额")
        fcf = _latest_value(con, "cashflow", ticker, "自由现金流量")
        ni = _latest_value(con, "growth", ticker, "归属于母公司普通股股东的净利润")

        if fcf is not None and ni is not None:
            # 估算:使用 FCF 作为 OE 下界(缺 D&A 还原)
            return DerivedResult(
                fcf, False,
                f"P3 占位:用 FCF={fcf/1e8:.1f}亿 估代 OE(缺 D&A={None} maint_capex={None})"
                f" NI={ni/1e8:.1f}亿 — 升 True 需补充折旧/资本支出字段"
            )
        return DerivedResult(
            None, False,
            "P3 阻塞:cashflow 表无 D&A/maint_capex,完整 OE 无法计算"
        )
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════════════════
# B4 — 留存收益再投资可视化接口
# ═══════════════════════════════════════════════════════════════════════

def retained_earnings_breakdown(ticker: str,
                                  years: int = 10,
                                  db_path: Path | str = DB_PATH) -> list[dict]:
    """留存收益逐年分解表。

    返回结构:
      [{
        year: int,
        eps: float,                 # 基本每股收益
        dividend_per_share: float,  # 每股派息(eps × 股息率 / 100,估算)
        retained_eps: float,        # 留存 EPS = eps - dividend_per_share
        eps_growth_yoy: float|None, # EPS 同比增幅
      }, ...]

    股息率来自 valuation.股息率(年末值),单位 %。
    dividend_per_share = eps × (股息率 / 100)  — 估算,非精确
    verified: 股息率是理杏仁真实字段; D/EPS 转换是本地估算
    """
    con = _conn(db_path)
    try:
        eps_series = _yearly_series(con, "growth", ticker, "基本每股收益",
                                    years_back=years + 2)
        div_rate_series = dict(
            _yearly_series(con, "valuation", ticker, "股息率",
                           years_back=years + 2)
        )  # 股息率单位:%

        if not eps_series:
            return []

        result = []
        for i, (year, eps) in enumerate(eps_series[-(years):]):
            div_rate = div_rate_series.get(year, None)
            # dividend_per_share 估算:股息率 = 年度派息总额 / 股价,换算成 EPS 口径存在偏差
            # 更准确应用 DPS = 股息率 × 年末股价,此处用 eps × 股息率比例近似
            dividend_per_share = (eps * div_rate / 100.0) if (div_rate is not None and eps > 0) else 0.0
            retained_eps = eps - dividend_per_share

            # YoY EPS growth
            if i > 0:
                prev_eps = eps_series[-(years) + i - 1][1] if (-(years) + i - 1) >= -(len(eps_series)) else None
                if prev_eps is not None and prev_eps != 0:
                    eps_growth_yoy = (eps - prev_eps) / abs(prev_eps)
                else:
                    eps_growth_yoy = None
            else:
                eps_growth_yoy = None

            result.append({
                "year": year,
                "eps": round(eps, 4),
                "dividend_per_share": round(dividend_per_share, 4),
                "retained_eps": round(retained_eps, 4),
                "eps_growth_yoy": round(eps_growth_yoy, 4) if eps_growth_yoy is not None else None,
                "div_rate_pct": round(div_rate, 2) if div_rate is not None else None,
                "verified": False,  # dividend_per_share 是估算口径
                "note": "dividend_per_share = eps × 股息率(估算),非精确每股 DPS",
            })

        return result
    finally:
        con.close()


def retained_earnings_return_rate(ticker: str,
                                   years: int = 10,
                                   db_path: Path | str = DB_PATH) -> DerivedResult:
    """留存收益再投资回报率:巴菲特经典公式。

    公式:(EPS_t - EPS_{t-n}) / sum(retained_eps[t-n+1 .. t-1])
    threshold: ≥18%→2.0 / ≥15%→1.5 / ≥12%→1.0 / ≥8%→0.5 / else→0

    Returns DerivedResult(rate, verified, note)
    """
    breakdown = retained_earnings_breakdown(ticker, years, db_path)
    if len(breakdown) < years:
        return DerivedResult(
            None, False,
            f"留存收益数据不足 {years} 年 (实有 {len(breakdown)})"
        )

    eps_start = breakdown[0]["eps"]
    eps_end = breakdown[-1]["eps"]
    # 分母: t-n+1 到 t-1 的留存 EPS 之和(不含最后一年)
    retained_sum = sum(r["retained_eps"] for r in breakdown[:-1])

    if retained_sum <= 0:
        return DerivedResult(
            None, False,
            f"留存 EPS 之和非正({retained_sum:.4f}),无法计算再投资回报"
        )

    rate = (eps_end - eps_start) / retained_sum
    if rate >= 0.18:
        score = 2.0
    elif rate >= 0.15:
        score = 1.5
    elif rate >= 0.12:
        score = 1.0
    elif rate >= 0.08:
        score = 0.5
    else:
        score = 0.0

    return DerivedResult(
        rate, False,
        f"留存再投资率={rate*100:.1f}% (EPS {eps_start:.2f}→{eps_end:.2f}, "
        f"retained_sum={retained_sum:.2f}) → score={score} [verified=False: DPS 估算]"
    )


# ═══════════════════════════════════════════════════════════════════════
# B5 — 护城河质性打分存储接口
# ═══════════════════════════════════════════════════════════════════════

_MOAT_DIMENSIONS = ["brand", "switching_cost", "network_effect",
                     "economies_of_scale", "intangible_assets"]
_MOAT_MAX = 2  # 每维度最高分


def load_qualitative_score(ticker: str,
                             path: Path | str = QUALITATIVE_PATH) -> dict:
    """读取某公司的护城河主观评分。

    返回:
      {
        "brand": 0-2,
        "switching_cost": 0-2,
        "network_effect": 0-2,
        "economies_of_scale": 0-2,
        "intangible_assets": 0-2,
        "total": 0-10,
        "updated_at": "YYYY-MM-DD" | None,
        "notes": str | None,
      }
    未录入时全部返回 None(非 0)。
    """
    path = Path(path)
    if not path.exists():
        return _empty_qualitative(ticker)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    companies = data.get("companies", {})
    entry = companies.get(ticker, None)
    if entry is None:
        return _empty_qualitative(ticker)

    scores = {dim: entry.get("scores", {}).get(dim, None) for dim in _MOAT_DIMENSIONS}
    valid_scores = [s for s in scores.values() if s is not None]
    total = sum(valid_scores) if valid_scores else None

    return {
        **scores,
        "total": total,
        "updated_at": entry.get("updated_at", None),
        "notes": entry.get("notes", None),
    }


def save_qualitative_score(ticker: str,
                             scores: dict,
                             notes: str = "",
                             path: Path | str = QUALITATIVE_PATH) -> bool:
    """写入某公司的护城河主观评分。

    scores: {dim: 0-2} — 缺省维度保留原值
    返回 True 表示成功写入。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {"companies": {}}

    if "companies" not in data:
        data["companies"] = {}

    # 合并原有数据
    existing = data["companies"].get(ticker, {})
    existing_scores = existing.get("scores", {})
    existing_scores.update({
        dim: scores[dim] for dim in _MOAT_DIMENSIONS if dim in scores
    })

    data["companies"][ticker] = {
        "scores": existing_scores,
        "updated_at": date.today().isoformat(),
        "notes": notes or existing.get("notes", ""),
    }

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return True


def _empty_qualitative(ticker: str) -> dict:
    return {
        "brand": None,
        "switching_cost": None,
        "network_effect": None,
        "economies_of_scale": None,
        "intangible_assets": None,
        "total": None,
        "updated_at": None,
        "notes": None,
    }


def qualitative_total_score(ticker: str,
                              path: Path | str = QUALITATIVE_PATH) -> DerivedResult:
    """加载主观护城河总分(0-10),未录入时返回 None。"""
    q = load_qualitative_score(ticker, path)
    total = q.get("total", None)
    if total is None:
        return DerivedResult(None, False, f"{ticker} 护城河评分未录入")
    updated = q.get("updated_at", "unknown")
    return DerivedResult(
        float(total), True,
        f"护城河主观总分={total}/10 (更新:{updated})"
    )


# ═══════════════════════════════════════════════════════════════════════
# 5 档梯度打分器(通用辅助)
# ═══════════════════════════════════════════════════════════════════════

def apply_grades(value: float, grades: dict, direction: str = "normal") -> float:
    """按 grades 段定义返回分档 score。

    grades: {"excellent": {"threshold": x, "score": y}, ...}
    direction: "normal" → 越大越好; "reverse" → 越小越好(threshold 是上限)
    """
    if direction == "reverse":
        # 反向:阈值是上限,从小到大排序找最优档
        ordered = sorted(
            [(k, v) for k, v in grades.items()],
            key=lambda x: x[1]["threshold"]
        )
        for grade_name, cfg in ordered:
            if value <= cfg["threshold"]:
                return cfg["score"]
        return 0.0
    else:
        # 正向:从最高档往下匹配
        ordered = sorted(
            [(k, v) for k, v in grades.items()],
            key=lambda x: x[1]["threshold"],
            reverse=True
        )
        for grade_name, cfg in ordered:
            thr = cfg["threshold"]
            if thr == float("-inf") or value >= thr:
                return cfg["score"]
        return 0.0
