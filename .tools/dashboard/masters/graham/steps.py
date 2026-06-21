"""格雷厄姆深度价值五步法 — 纯逻辑层(对照 lynch_classifier.py 模式)。

提供:
  - GrahamClassResult dataclass(四类:deep_value / defensive / enterprising / special)
  - DefensiveSeven dataclass(防御 7 准则评估)
  - GrahamNumberCheck dataclass(格氏数 + 安全边际)
  - NCAVCheck dataclass(净流动资产法)
  - ThreeLinesDefense dataclass(三层防御工事)
  - classify_graham_type(m) → GrahamClassResult
  - load_graham_metrics(ticker) → 派生 BS 三件套 + EPS + BVPS

复用:
  - lynch_classifier.load_metrics_from_db 拿主要 metric
  - 自行从 DuckDB safety 表派生 NCAV / BVPS / EPS

入口:
  from masters.graham.steps import classify_graham_type, load_graham_metrics

Author: Claude (D3 Phase B, 2026-05-07)
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))


# ─── 类型元数据 ──────────────────────────────────────────────────────────

CLASS_META = {
    "deep_value":   ("深度低估型", "🪙", "市值低于净流动资产 - 用 0.5 美元买 1 美元"),
    "defensive":    ("防御型",     "🛡️", "10 年盈利 + 10 年股息 + 格氏数达标"),
    "enterprising": ("进取型",     "⚔️", "二线优质 + 适度成长 + PEG ≤ 1.0"),
    "special":      ("特殊情境",   "🎭", "困境反转 / 重组套利 / NAV 折价"),
    "skip":         ("不适用",     "❓", "数据不全或不符合任一类型"),
}


# 类型驱动财务护栏(对照 00_方法论总览 第五节)
GUARDRAIL_THRESHOLDS = {
    "deep_value": {
        "debt_ratio_max":  0.50,
        "current_ratio_min": 2.0,         # 铁律
        "cfo_to_ni_min":   0.5,
        "interest_cov_min": 3,
        "label": "深度低估型(NCAV)",
    },
    "defensive": {
        "debt_ratio_max":  0.50,
        "current_ratio_min": 2.0,         # 铁律
        "cfo_to_ni_min":   0.9,
        "interest_cov_min": 5,
        "label": "防御型(《Intelligent Investor》第 14 章)",
    },
    "enterprising": {
        "debt_ratio_max":  0.60,
        "current_ratio_min": 1.5,
        "cfo_to_ni_min":   0.8,
        "interest_cov_min": 3,
        "label": "进取型(第 15 章)",
    },
    "special": {
        "debt_ratio_max":  0.70,         # 困境放宽
        "current_ratio_min": 1.0,
        "cfo_to_ni_min":   0.0,           # 转正即可
        "interest_cov_min": 1.5,
        "label": "特殊情境(困境反转/套利/NAV)",
    },
}

# 格氏数核心阈值
GRAHAM_NUMBER_RATIO = 22.5            # 经典 22.5 = PE 15 × PB 1.5
GRAHAM_NUMBER_SOFT_1 = 30             # 软达标 1 档
GRAHAM_NUMBER_SOFT_2 = 50             # 软达标 2 档


# ─── DataClass ──────────────────────────────────────────────────────────

@dataclass
class GrahamClassResult:
    cls_id: str
    cls_name: str
    cls_emoji: str
    confidence: float                    # 0-1
    reason: str
    key_metrics: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cls_id": self.cls_id, "cls_name": self.cls_name,
            "cls_emoji": self.cls_emoji, "confidence": self.confidence,
            "reason": self.reason,
            "key_metrics": dict(self.key_metrics),
            "notes": list(self.notes),
        }


@dataclass
class DefensiveCheck:
    """防御 7 准则单项结果。"""
    rule_id: str
    name: str
    passed: bool | None                  # None = 数据缺失
    actual: str
    threshold: str
    detail: str = ""

    @property
    def emoji(self) -> str:
        if self.passed is None: return "⚪"
        return "✅" if self.passed else "❌"


@dataclass
class DefensiveSeven:
    """防御 7 准则汇总。"""
    items: list[DefensiveCheck]
    pass_count: int
    total_count: int

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total_count if self.total_count else 0.0


@dataclass
class GrahamNumberCheck:
    pe: float | None
    pb: float | None
    pe_x_pb: float | None
    grade: str                           # 严达标 / 软 1 档 / 软 2 档 / 不达标
    grade_emoji: str
    safety_margin_pct: float | None     # 隐含安全边际(如 PE×PB=10 → 1 - 10/22.5 = 55.6%)


@dataclass
class NCAVCheck:
    market_cap: float | None
    current_assets: float | None
    total_liabilities: float | None
    ncav: float | None                   # = 流动资产 - 总负债
    mc_to_ncav: float | None             # 市值 / NCAV(< 0.67 是经典阈值)
    grade: str                           # 经典深度 / 适度低估 / 持有 / 不适用
    grade_emoji: str


@dataclass
class ThreeLinesDefense:
    """三层防御工事评估(对照 08_实战_财务健康)。"""
    line1_cash_buffer_months: float | None
    line2_cfo_to_ni: float | None
    line3_debt_capacity: str             # "充足" / "中等" / "紧张"
    line1_status: str                    # "🟢 极充裕" / "🟡 中等" / "🔴 紧张"
    line2_status: str
    line3_status: str
    overall_status: str                  # 综合


# ─── 派生函数 ──────────────────────────────────────────────────────────

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _normalize_ticker(raw: str, market: str | None = None) -> str:
    """ticker 规范化 — 委托给 dashboard/tickers.py 单一可信源。

    A 股 6 位 zero-padded,港股 5 位 zero-padded。
    """
    try:
        from tickers import normalize_ticker as _norm
    except ImportError:  # pragma: no cover
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        from tickers import normalize_ticker as _norm
    return _norm(raw, market=market)


def _latest_value(con, table: str, ticker: str, metric: str) -> float | None:
    try:
        row = con.execute(
            f"SELECT value FROM {table} WHERE ticker=? AND metric=? "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
            [ticker, metric],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def _annual_eps_5y(con, ticker: str) -> list[tuple[int, float]]:
    """从 growth 表派生年度 EPS — 用基本每股收益(若有)否则净利润÷股数。

    返回 [(year, eps), ...] 按年降序。
    """
    try:
        rows = con.execute(
            "SELECT date, value FROM growth WHERE ticker=? AND metric='基本每股收益' "
            "AND value IS NOT NULL AND CAST(strftime(date, '%m-%d') AS VARCHAR) = '12-31' "
            "ORDER BY date DESC LIMIT 12",
            [ticker],
        ).fetchall()
    except Exception:
        rows = []
    if not rows:
        return []
    out = []
    for d, v in rows:
        try:
            year = int(str(d)[:4])
            out.append((year, float(v)))
        except Exception:
            continue
    return out


def _years_continuous_dividend(con, ticker: str) -> int | None:
    """计算从最近一年起的连续派息年数(股息率 > 0)。"""
    try:
        rows = con.execute(
            "SELECT EXTRACT(year FROM date)::INTEGER AS yr, MAX(value) AS dy "
            "FROM valuation WHERE ticker=? AND metric='股息率' AND value IS NOT NULL "
            "GROUP BY yr ORDER BY yr DESC",
            [ticker],
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    cnt = 0
    for _yr, dy in rows:
        if dy and float(dy) > 0:
            cnt += 1
        else:
            break
    return cnt


def load_graham_metrics(ticker: str, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """组装格雷厄姆判断所需的 metric — 复用 lynch_classifier 的 load_metrics_from_db,叠加 BS 派生。"""
    # 规范化 ticker(DuckDB 去前导零;'000333' → '333' / '02097' → '2097')
    ticker = _normalize_ticker(ticker)

    # 复用 lynch 的主体加载
    try:
        from masters.lynch.classifier import load_metrics_from_db  # noqa
    except ImportError:
        from .lynch_classifier import load_metrics_from_db  # type: ignore

    m = load_metrics_from_db(ticker, db_path=db_path)

    con = _conn(db_path)
    try:
        # BS 三件套(safety 表)
        m["total_assets"] = _latest_value(con, "safety", ticker, "资产合计")
        m["total_liabilities"] = _latest_value(con, "safety", ticker, "负债合计")
        m["current_assets"] = _latest_value(con, "safety", ticker, "流动资产合计")
        m["current_liabilities"] = _latest_value(con, "safety", ticker, "流动负债合计")
        m["long_term_debt"] = _latest_value(con, "safety", ticker, "长期负债合计")
        m["book_equity"] = None  # 净资产(可派生:总资产 - 总负债)
        if m["total_assets"] and m["total_liabilities"]:
            m["book_equity"] = m["total_assets"] - m["total_liabilities"]

        # 市值
        m["market_cap"] = _latest_value(con, "valuation", ticker, "市值(元)")

        # NCAV(派生)
        if m["current_assets"] is not None and m["total_liabilities"] is not None:
            m["ncav"] = m["current_assets"] - m["total_liabilities"]
        else:
            m["ncav"] = None

        # PE × PB(格氏数核心)
        if m.get("pe_ttm") and m.get("pb"):
            m["pe_x_pb"] = m["pe_ttm"] * m["pb"]
        else:
            m["pe_x_pb"] = None

        # EPS 时序(用于 5/10 年盈利持续性 + 增长率)
        eps_series = _annual_eps_5y(con, ticker)
        m["eps_series"] = eps_series

        # 5 年盈利持续(全部为正)
        if eps_series:
            recent_5 = eps_series[:5]
            m["eps_5y_all_positive"] = len(recent_5) >= 5 and all(v > 0 for _, v in recent_5)
            recent_10 = eps_series[:10]
            m["eps_10y_all_positive"] = len(recent_10) >= 10 and all(v > 0 for _, v in recent_10)
        else:
            m["eps_5y_all_positive"] = None
            m["eps_10y_all_positive"] = None

        # EPS 10y CAGR
        m["eps_10y_cagr"] = None
        if len(eps_series) >= 10:
            end = eps_series[0][1]
            start = eps_series[9][1]
            if start > 0 and end > 0:
                m["eps_10y_cagr"] = (end / start) ** (1 / 10) - 1

        # 连续派息年数(覆盖 lynch 已有 dividend_years_continuous)
        if m.get("dividend_years_continuous") is None:
            m["dividend_years_continuous"] = _years_continuous_dividend(con, ticker)

        # 利息覆盖倍数 — 简化派生(没有 EBIT 直接字段,先 None)
        m["interest_coverage"] = None

        # 经营现金流(年报)
        m["cfo_latest"] = _latest_value(con, "cashflow", ticker, "经营活动产生的现金流量净额")
    finally:
        con.close()
    return m


# ─── 第 1 步:四类判定 ─────────────────────────────────────────────────

def classify_graham_type(m: dict[str, Any]) -> GrahamClassResult:
    """格雷厄姆四类判定 — 决策树见 01_四类价值分类.md。"""
    notes: list[str] = []
    key: dict[str, str] = {}

    pe = m.get("pe_ttm")
    pb = m.get("pb")
    pe_x_pb = m.get("pe_x_pb")
    market_cap = m.get("market_cap")
    ncav = m.get("ncav")
    eps_5y_pos = m.get("eps_5y_all_positive")
    eps_10y_pos = m.get("eps_10y_all_positive")
    div_years = m.get("dividend_years_continuous")
    dy = m.get("dividend_yield") or 0
    np_yoy = m.get("np_yoy_recent") or 0
    cfo_to_ni = m.get("cfo_to_ni") or 0
    debt_ratio = m.get("debt_ratio") or 0
    industry = m.get("industry_sw_l1") or ""
    category = m.get("category") or ""

    # 银行/保险特殊处理
    is_financial = "银行" in industry or "保险" in industry or category in ("bank", "insurance")
    if is_financial:
        # 金融业用 PB + DY + ROE 综合判断 → 默认走防御型
        notes.append("金融业(银行/保险)— PE 不可比,走 PB + DY + ROE 评估")
        if (pb or 99) < 1.5 and dy > 0.03 and (m.get("roe") or 0) > 0.10:
            return GrahamClassResult(
                cls_id="defensive", cls_name="防御型", cls_emoji="🛡️",
                confidence=0.85,
                reason=f"金融业:PB={pb:.2f} / DY={dy*100:.1f}% / ROE={(m.get('roe') or 0)*100:.1f}%",
                key_metrics={
                    "PB": f"{pb:.2f}" if pb else "—",
                    "股息率": f"{dy*100:.2f}%",
                    "ROE": f"{(m.get('roe') or 0)*100:.1f}%",
                    "行业": industry,
                },
                notes=notes,
            )
        # 否则归类为进取(若 ROE 较低)或特殊
        return GrahamClassResult(
            cls_id="enterprising", cls_name="进取型", cls_emoji="⚔️",
            confidence=0.70,
            reason="金融业但未达防御型阈值",
            key_metrics={"PB": f"{pb:.2f}" if pb else "—", "股息率": f"{dy*100:.2f}%", "行业": industry},
            notes=notes,
        )

    # 1) 困境反转判定:亏损 / 微利 + 净利大跌
    if eps_5y_pos is False or (np_yoy and np_yoy < -30):
        # 检查是否资产扎实(NCAV)
        if ncav and market_cap and market_cap < ncav * 1.0:
            return GrahamClassResult(
                cls_id="deep_value", cls_name="深度低估型", cls_emoji="🪙",
                confidence=0.75,
                reason=f"市值 {market_cap/1e8:.0f}亿 < NCAV {ncav/1e8:.0f}亿,净流动资产打底",
                key_metrics={
                    "市值": f"{market_cap/1e8:.0f}亿",
                    "NCAV": f"{ncav/1e8:.0f}亿",
                    "市值/NCAV": f"{market_cap/ncav:.2f}",
                    "PB": f"{pb:.2f}" if pb else "—",
                },
                notes=notes,
            )
        return GrahamClassResult(
            cls_id="special", cls_name="特殊情境", cls_emoji="🎭",
            confidence=0.65,
            reason=f"近期亏损或大幅下滑(YoY {np_yoy:+.0f}%)— 困境反转候选",
            key_metrics={
                "PE": f"{pe:.1f}" if pe else "—",
                "PB": f"{pb:.2f}" if pb else "—",
                "净利 YoY": f"{np_yoy:+.0f}%",
            },
            notes=notes + ["反转可见性待评估,见第 5 步深度审视"],
        )

    # 2) 深度低估(NCAV 严)
    if ncav and market_cap and market_cap < ncav * 0.67:
        return GrahamClassResult(
            cls_id="deep_value", cls_name="深度低估型", cls_emoji="🪙",
            confidence=0.95,
            reason=f"格雷厄姆经典:市值 < NCAV × 2/3({market_cap/ncav:.2f})",
            key_metrics={
                "市值": f"{market_cap/1e8:.0f}亿",
                "NCAV": f"{ncav/1e8:.0f}亿",
                "市值/NCAV": f"{market_cap/ncav:.2f}",
            },
            notes=notes + ["A 股极少出现,需深度审视资产真实性"],
        )

    # 3) 防御型判定:大盘 + 10 年盈利 + 10 年分红 + 格氏数软达标
    is_large = (market_cap or 0) >= 5e10  # 500 亿
    has_long_dividend = (div_years or 0) >= 10
    has_long_earnings = bool(eps_10y_pos)
    is_graham_number = (pe_x_pb or 99) <= 50  # 软达标 2 档

    if is_large and has_long_dividend and has_long_earnings and is_graham_number:
        return GrahamClassResult(
            cls_id="defensive", cls_name="防御型", cls_emoji="🛡️",
            confidence=0.90,
            reason=f"大盘({market_cap/1e10:.0f}百亿)+ 10 年盈利 + {div_years} 年股息 + PE×PB={pe_x_pb:.1f}",
            key_metrics={
                "市值": f"{market_cap/1e10:.0f}百亿",
                "PE×PB": f"{pe_x_pb:.1f}",
                "股息率": f"{dy*100:.2f}%",
                "连续派息": f"{div_years} 年",
            },
            notes=notes,
        )

    # 4) 进取型(default fallback for healthy companies)
    is_healthy = bool(eps_5y_pos) and (debt_ratio < 0.6) and (cfo_to_ni > 0.5)
    if is_healthy:
        confidence = 0.75
        if not is_large:
            notes.append("中小盘:符合进取型(规模 < 500 亿)")
        if pe_x_pb and pe_x_pb > 50:
            notes.append(f"PE×PB={pe_x_pb:.0f} 超 50 — 估值偏贵,需 PEG 验证")
        return GrahamClassResult(
            cls_id="enterprising", cls_name="进取型", cls_emoji="⚔️",
            confidence=confidence,
            reason=f"持续盈利 + 财务健康 + 适度成长(PEG={m.get('peg_lixinger') or '—'})",
            key_metrics={
                "PE": f"{pe:.1f}" if pe else "—",
                "PEG": f"{m.get('peg_lixinger'):.2f}" if m.get('peg_lixinger') else "—",
                "ROE": f"{(m.get('roe') or 0)*100:.1f}%",
                "资产负债率": f"{debt_ratio*100:.0f}%" if debt_ratio else "—",
            },
            notes=notes,
        )

    # 5) Skip
    return GrahamClassResult(
        cls_id="skip", cls_name="不适用", cls_emoji="❓",
        confidence=0.50,
        reason="数据不全或不符合任一类型",
        key_metrics={
            "PE": f"{pe:.1f}" if pe else "—",
            "PB": f"{pb:.2f}" if pb else "—",
            "市值": f"{market_cap/1e8:.0f}亿" if market_cap else "—",
        },
        notes=notes + ["建议手动指定类型,或回避"],
    )


# ─── 第 2 步:盈利能力诊断(辅助函数) ──────────────────────────────────

def evaluate_earnings_quality(m: dict) -> dict[str, Any]:
    """杜邦三因子 + 现金流验证 + 增长质量。"""
    roe = m.get("roe")
    cfo_to_ni = m.get("cfo_to_ni")
    rev_5y = m.get("rev_cagr_5y")
    np_yoy = m.get("np_yoy_recent")

    duboston = {}
    if roe:
        net_margin = m.get("net_margin_5y_mean") or 0
        # 简化 — 周转率 = 1 / 总资产周转日数 不易直接算,用代理
        # 杠杆 = 1 / (1 - debt_ratio)
        debt_ratio = m.get("debt_ratio") or 0
        leverage = 1 / (1 - debt_ratio) if debt_ratio < 0.95 else None
        duboston = {
            "ROE": roe,
            "net_margin": net_margin,
            "leverage": leverage,
            "interpretation": (
                "高杠杆驱动" if leverage and leverage > 2.5 else
                "高净利率驱动" if net_margin > 0.20 else
                "均衡"
            ),
        }

    # 现金流验证
    cfo_ok = cfo_to_ni is not None and cfo_to_ni >= 0.9
    cfo_warning = cfo_to_ni is not None and cfo_to_ni < 0.7

    return {
        "dupont": duboston,
        "cfo_to_ni": cfo_to_ni,
        "cfo_quality": "🟢 优秀" if cfo_ok else ("🔴 预警" if cfo_warning else "🟡 一般"),
        "rev_cagr_5y": rev_5y,
        "np_yoy_recent": np_yoy,
        "growth_quality": (
            "🟢 健康" if (rev_5y or 0) > 0.05 and (np_yoy or 0) > 0 else
            "🟡 缓慢" if (rev_5y or 0) > 0 else "🔴 衰退"
        ),
    }


# ─── 第 3 步:三层防御工事 ─────────────────────────────────────────────

def evaluate_three_lines_defense(m: dict) -> ThreeLinesDefense:
    """三层防御工事评估(08_实战_财务健康)。"""
    cfo = m.get("cfo_latest")
    market_cap = m.get("market_cap") or 1
    debt_ratio = m.get("debt_ratio") or 0
    cfo_to_ni = m.get("cfo_to_ni")
    current_ratio = m.get("current_ratio")

    # 第一道:现金缓冲(用流动比率代理 — 没有直接现金数据)
    line1_months = None
    if current_ratio:
        # 简化:流动比率 ≥ 2 = 极充裕(24+ 月)/ 1.5-2 = 中等(12-24)/ < 1.5 紧张
        if current_ratio >= 2.0:
            line1_months = 24
            line1_status = "🟢 极充裕"
        elif current_ratio >= 1.5:
            line1_months = 18
            line1_status = "🟡 中等"
        else:
            line1_months = 6
            line1_status = "🔴 紧张"
    else:
        line1_status = "⚪ 数据缺失"

    # 第二道:经营现金流造血
    if cfo_to_ni is not None:
        if cfo_to_ni >= 1.0:
            line2_status = "🟢 强劲(每元利润生 1+ 元现金)"
        elif cfo_to_ni >= 0.7:
            line2_status = "🟡 健康"
        elif cfo_to_ni >= 0.0:
            line2_status = "🟠 偏弱"
        else:
            line2_status = "🔴 失血(经营现金流为负)"
    else:
        line2_status = "⚪ 数据缺失"

    # 第三道:外部融资空间(用资产负债率代理)
    if debt_ratio < 0.40:
        line3_status = "🟢 充足(负债低,授信空间大)"
        line3_capacity = "充足"
    elif debt_ratio < 0.60:
        line3_status = "🟡 中等"
        line3_capacity = "中等"
    else:
        line3_status = "🔴 紧张(高负债,新融资难)"
        line3_capacity = "紧张"

    # 综合
    statuses = [line1_status, line2_status, line3_status]
    red_count = sum(1 for s in statuses if "🔴" in s)
    if red_count >= 2:
        overall = "🔴 三道防线穿透 — 财务健康预警"
    elif red_count == 1:
        overall = "🟡 一道防线偏弱"
    else:
        overall = "🟢 三道防线坚固"

    return ThreeLinesDefense(
        line1_cash_buffer_months=line1_months,
        line2_cfo_to_ni=cfo_to_ni,
        line3_debt_capacity=line3_capacity,
        line1_status=line1_status,
        line2_status=line2_status,
        line3_status=line3_status,
        overall_status=overall,
    )


# ─── 第 4 步:估值与安全边际 ───────────────────────────────────────────

def check_graham_number(m: dict) -> GrahamNumberCheck:
    """格氏数检验 — PE × PB ≤ 22.5(原版)/ ≤ 30(软 1)/ ≤ 50(软 2)。"""
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    pe_x_pb = m.get("pe_x_pb")

    if pe_x_pb is None:
        return GrahamNumberCheck(
            pe=pe, pb=pb, pe_x_pb=None,
            grade="数据缺失", grade_emoji="⚪",
            safety_margin_pct=None,
        )

    if pe_x_pb <= GRAHAM_NUMBER_RATIO:
        grade = "严达标(原版)"
        emoji = "🟢"
    elif pe_x_pb <= GRAHAM_NUMBER_SOFT_1:
        grade = "软达标 1 档"
        emoji = "🟡"
    elif pe_x_pb <= GRAHAM_NUMBER_SOFT_2:
        grade = "软达标 2 档"
        emoji = "🟠"
    else:
        grade = "不达标(估值偏贵)"
        emoji = "🔴"

    # 安全边际:格氏数 / 当前 = sqrt(22.5 / PE×PB)
    if pe_x_pb > 0:
        ratio = math.sqrt(GRAHAM_NUMBER_RATIO / pe_x_pb)
        safety = (1 - 1 / ratio) * 100 if ratio > 1 else (ratio - 1) * 100
    else:
        safety = None

    return GrahamNumberCheck(
        pe=pe, pb=pb, pe_x_pb=pe_x_pb,
        grade=grade, grade_emoji=emoji,
        safety_margin_pct=safety,
    )


def check_ncav(m: dict) -> NCAVCheck:
    """净流动资产法(NCAV)— 适用于深度低估型。"""
    market_cap = m.get("market_cap")
    ncav = m.get("ncav")
    current_assets = m.get("current_assets")
    total_liabilities = m.get("total_liabilities")

    if market_cap is None or ncav is None:
        return NCAVCheck(
            market_cap=market_cap,
            current_assets=current_assets,
            total_liabilities=total_liabilities,
            ncav=ncav, mc_to_ncav=None,
            grade="数据缺失", grade_emoji="⚪",
        )

    if ncav <= 0:
        return NCAVCheck(
            market_cap=market_cap,
            current_assets=current_assets,
            total_liabilities=total_liabilities,
            ncav=ncav, mc_to_ncav=None,
            grade="不适用(负债 > 流动资产)", grade_emoji="❌",
        )

    ratio = market_cap / ncav

    if ratio < 0.67:
        grade, emoji = "格雷厄姆经典深度(< 2/3)", "🟢🟢"
    elif ratio < 1.0:
        grade, emoji = "适度低估(< NCAV)", "🟢"
    elif ratio < 1.5:
        grade, emoji = "持有但不新增", "🟡"
    elif ratio < 2.0:
        grade, emoji = "价值已实现 — 减仓", "🟠"
    else:
        grade, emoji = "深度低估逻辑失效", "🔴"

    return NCAVCheck(
        market_cap=market_cap,
        current_assets=current_assets,
        total_liabilities=total_liabilities,
        ncav=ncav, mc_to_ncav=ratio,
        grade=grade, grade_emoji=emoji,
    )


def evaluate_defensive_seven(m: dict) -> DefensiveSeven:
    """《Intelligent Investor》第 14 章防御 7 准则(A 股调整版)。"""
    items: list[DefensiveCheck] = []

    # 1. 规模充足 — A 股调整为 ≥ 200 亿
    mc = m.get("market_cap")
    p = mc is not None and mc >= 2e10
    items.append(DefensiveCheck(
        rule_id="g1", name="规模充足(市值 ≥ 200 亿)",
        passed=p if mc is not None else None,
        actual=f"{mc/1e8:.0f}亿" if mc else "—",
        threshold="≥ 200 亿(原版 ≥ $2B)",
    ))

    # 2. 财务稳健 — 流动比率 ≥ 2
    cr = m.get("current_ratio")
    p = cr is not None and cr >= 2.0
    items.append(DefensiveCheck(
        rule_id="g2", name="财务稳健(流动比率 ≥ 2)",
        passed=p if cr is not None else None,
        actual=f"{cr:.2f}" if cr else "—",
        threshold="≥ 2.0(铁律)",
        detail="格雷厄姆 1929 年大萧条幸存的核心经验",
    ))

    # 3. 盈利稳定 — 10 年至少 8 年盈利
    eps_10y = m.get("eps_10y_all_positive")
    eps_series = m.get("eps_series") or []
    pos_years = sum(1 for _, v in eps_series[:10] if v > 0)
    n_years = min(len(eps_series), 10)
    p = (pos_years >= 8) if n_years >= 10 else None
    items.append(DefensiveCheck(
        rule_id="g3", name="盈利稳定(10 年至少 8 年盈利)",
        passed=p,
        actual=f"{pos_years}/{n_years} 年盈利" if n_years > 0 else "—",
        threshold="≥ 8/10 年(A 股放宽)",
    ))

    # 4. 股息历史 — 连续 10 年(A 股放宽)
    dy = m.get("dividend_years_continuous")
    p = dy is not None and dy >= 10
    items.append(DefensiveCheck(
        rule_id="g4", name="股息历史(≥ 10 年连续派息)",
        passed=p if dy is not None else None,
        actual=f"{dy} 年" if dy else "—",
        threshold="≥ 10 年(原版 ≥ 20 年)",
    ))

    # 5. 盈利增长 — 10 年 EPS CAGR ≥ 3%
    cagr = m.get("eps_10y_cagr")
    p = cagr is not None and cagr >= 0.03
    items.append(DefensiveCheck(
        rule_id="g5", name="盈利增长(10 年 EPS CAGR ≥ 3%)",
        passed=p if cagr is not None else None,
        actual=f"{cagr*100:+.1f}%" if cagr is not None else "—",
        threshold="≥ 3% (原版 ≥ 33% 累计)",
    ))

    # 6. PE 合理 — < 25 + 历史 < 70% 分位
    pe = m.get("pe_ttm")
    pe_pct = m.get("pe_pct_10y")
    pe_pass = pe is not None and pe <= 25
    pe_pct_pass = pe_pct is not None and pe_pct < 0.7
    p = pe_pass and pe_pct_pass if (pe is not None and pe_pct is not None) else None
    items.append(DefensiveCheck(
        rule_id="g6", name="PE 合理(< 25 + 历史分位 < 70%)",
        passed=p,
        actual=f"PE={pe:.1f}, 分位={pe_pct*100:.0f}%" if pe and pe_pct else "—",
        threshold="< 25 + 历史 < 70% 分位",
    ))

    # 7. PB 合理 — < 2.5 或格氏数 ≤ 30(软达标)
    pb = m.get("pb")
    pe_x_pb = m.get("pe_x_pb")
    pb_pass = pb is not None and (pb < 2.5 or (pe_x_pb is not None and pe_x_pb <= 30))
    items.append(DefensiveCheck(
        rule_id="g7", name="PB 合理(< 2.5 或 PE×PB ≤ 30 软达标)",
        passed=pb_pass if pb is not None else None,
        actual=f"PB={pb:.2f}, PE×PB={pe_x_pb:.1f}" if pb and pe_x_pb else "—",
        threshold="< 2.5 或 PE×PB ≤ 30",
    ))

    pass_count = sum(1 for it in items if it.passed is True)
    total_count = sum(1 for it in items if it.passed is not None)
    return DefensiveSeven(items=items, pass_count=pass_count, total_count=total_count)


# ─── 第 5 步:深度审视(诊断信号) ──────────────────────────────────────

def deep_inspection_signals(m: dict) -> list[dict[str, str]]:
    """深度审视 — 触发警告信号清单(对照 10_实战_深度审视)。"""
    signals: list[dict[str, str]] = []

    # 1. 应收 vs 营收增速
    # (lynch_classifier.load_metrics_from_db 没直接给应收增速,先 placeholder)

    # 2. CFO/NI 持续偏低
    cfo_to_ni = m.get("cfo_to_ni")
    if cfo_to_ni is not None and cfo_to_ni < 0.7:
        signals.append({
            "type": "🔴 利润含金量预警",
            "detail": f"CFO/NI = {cfo_to_ni:.2f} < 0.7,可能存在纸面富贵 / 应收沉淀",
        })

    # 3. 高负债率
    dr = m.get("debt_ratio")
    if dr is not None and dr > 0.65:
        signals.append({
            "type": "🟠 高杠杆预警",
            "detail": f"资产负债率 {dr*100:.0f}%,需关注是否依赖杠杆推动 ROE",
        })

    # 4. PE 接近历史高位
    pe_pct = m.get("pe_pct_10y")
    if pe_pct is not None and pe_pct > 0.8:
        signals.append({
            "type": "🔴 估值高位预警",
            "detail": f"当前 PE 在自身 10y 分位 {pe_pct*100:.0f}%,价格已透支预期",
        })

    # 5. 增长停滞
    rev_5y = m.get("rev_cagr_5y")
    if rev_5y is not None and rev_5y < 0.01:
        signals.append({
            "type": "🟡 增长停滞预警",
            "detail": f"5 年营收 CAGR {rev_5y*100:+.1f}%,可能向「缓慢增长」滑落",
        })

    # 6. 净利下滑
    np_yoy = m.get("np_yoy_recent")
    if np_yoy is not None and np_yoy < -10:
        signals.append({
            "type": "🔴 利润下滑预警",
            "detail": f"最近净利 YoY {np_yoy:+.1f}%,触发卖出条件 ②",
        })

    # 7. 流动比率低于铁律
    cr = m.get("current_ratio")
    if cr is not None and cr < 1.5:
        signals.append({
            "type": "🟠 流动性预警",
            "detail": f"流动比率 {cr:.2f} < 1.5,违反格雷厄姆财务铁律(≥ 2.0)",
        })

    if not signals:
        signals.append({
            "type": "🟢 无重大预警",
            "detail": "前 6 步常见预警全部通过",
        })

    return signals


# ─── 卖出触发 ──────────────────────────────────────────────────────────

def evaluate_sell_triggers(m: dict, cls_id: str,
                           graham_num: GrahamNumberCheck,
                           three_lines: ThreeLinesDefense,
                           defensive: DefensiveSeven | None = None) -> list[dict]:
    """4 条通用卖出触发(对照 00_方法论总览 第七节)。"""
    triggers: list[dict] = []

    # ① 价格 > 内在价值 × 1.33(用格氏数 PE×PB > 50 代理)
    if graham_num.pe_x_pb and graham_num.pe_x_pb > 50:
        triggers.append({
            "id": "①", "name": "估值反转",
            "fired": True,
            "detail": f"PE×PB = {graham_num.pe_x_pb:.1f} > 50(深度高估)",
        })
    else:
        triggers.append({
            "id": "①", "name": "估值反转",
            "fired": False,
            "detail": f"PE×PB = {graham_num.pe_x_pb:.1f}" if graham_num.pe_x_pb else "数据缺失",
        })

    # ② 三道防线被穿透
    if "🔴" in three_lines.overall_status:
        triggers.append({
            "id": "②", "name": "财务健康破裂",
            "fired": True,
            "detail": three_lines.overall_status,
        })
    else:
        triggers.append({
            "id": "②", "name": "财务健康破裂",
            "fired": False,
            "detail": three_lines.overall_status,
        })

    # ③ 报表造假预警(用 CFO/NI 代理)
    cfo_to_ni = m.get("cfo_to_ni")
    if cfo_to_ni is not None and cfo_to_ni < 0.5:
        triggers.append({
            "id": "③", "name": "报表造假预警",
            "fired": True,
            "detail": f"CFO/NI = {cfo_to_ni:.2f} < 0.5(应收/存货沉淀严重)",
        })
    else:
        triggers.append({
            "id": "③", "name": "报表造假预警",
            "fired": False,
            "detail": f"CFO/NI = {cfo_to_ni:.2f}" if cfo_to_ni else "数据缺失",
        })

    # ④ 价值陷阱信号
    rev_5y = m.get("rev_cagr_5y")
    np_yoy = m.get("np_yoy_recent")
    is_trap = (rev_5y is not None and rev_5y < 0) or (np_yoy is not None and np_yoy < -30)
    if is_trap:
        triggers.append({
            "id": "④", "name": "价值陷阱预警",
            "fired": True,
            "detail": f"营收 CAGR={rev_5y*100:+.1f}% / 净利 YoY={np_yoy:+.0f}%" if rev_5y and np_yoy else "增长断档",
        })
    else:
        triggers.append({
            "id": "④", "name": "价值陷阱预警",
            "fired": False,
            "detail": "营收稳定,无衰退信号",
        })

    return triggers


__all__ = [
    "CLASS_META", "GUARDRAIL_THRESHOLDS",
    "GrahamClassResult", "DefensiveCheck", "DefensiveSeven",
    "GrahamNumberCheck", "NCAVCheck", "ThreeLinesDefense",
    "load_graham_metrics", "classify_graham_type",
    "evaluate_earnings_quality", "evaluate_three_lines_defense",
    "check_graham_number", "check_ncav", "evaluate_defensive_seven",
    "deep_inspection_signals", "evaluate_sell_triggers",
]
