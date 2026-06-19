"""持仓季度合理价格区间 — v2.7 基础版(只用 Graham Number)。

公式:
    Graham Number = √(22.5 × EPS × BPS)

简化推导(避免依赖 EPS-TTM 直接字段):
    真实股价 = 市值 / 总股本
    总股本   = 净利润 / 基本每股收益       (从 growth 表)
    EPS-TTM = 真实股价 / PE-TTM           (从 valuation 表反推)
    BPS     = 真实股价 / PB
    ∴ Graham Number = 真实股价 × √(22.5 / (PE × PB))

数据源:
    - valuation 表:PE-TTM / PB / 市值(元)
    - growth 表:基本每股收益 / 归属于母公司普通股股东的净利润
    - 不用 prices 表(后复权累计价不是真实股价,会显示成 7-8 倍放大)

5 档 verdict 阈值(基于格雷厄姆经典 33% 安全边际):
    🟢🟢 极度低估   <  Graham × 0.67
    🟢  低估       <  Graham × 0.85
    🟡  合理       ≤  Graham × 1.15
    🔴  高估       ≤  Graham × 1.33
    🔴🔴 极度高估   >  Graham × 1.33
    ⚪  不适用     PE/PB/市值 缺失,或 EPS ≤ 0,或净资产 ≤ 0
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import yaml

# 公共 ticker 规范化(单一可信源)
try:
    from tickers import normalize_ticker as _shared_normalize_ticker
except ImportError:  # pragma: no cover — 直接以脚本方式运行时回退
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from tickers import normalize_ticker as _shared_normalize_ticker

# ─── 路径常量 ───────────────────────────────────────────────────────
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parents[3]
DB_PATH = PROJECT_ROOT / "data" / "preson.duckdb"
PORTFOLIO_PATH = PROJECT_ROOT / ".config" / "portfolio.yaml"

# ─── Graham Number 常量 ─────────────────────────────────────────────
GRAHAM_RATIO = 22.5          # 15 (PE 上限) × 1.5 (PB 上限)
VERDICT_LOW = 0.67           # 极度低估 < Graham × 0.67
VERDICT_LOW_SOFT = 0.85      # 低估     < Graham × 0.85
VERDICT_HIGH_SOFT = 1.15     # 合理上沿
VERDICT_HIGH = 1.33          # 高估 < Graham × 1.33;> 即极度高估


# ─── 数据结构 ───────────────────────────────────────────────────────
@dataclass
class FairPriceRange:
    """合理价格区间 + verdict + 计算明细(供 UI 展示)。"""

    ticker: str
    name: str
    verified: bool                  # Graham 算出才 True
    as_of: date | None              # 数据快照日

    # 区间核心
    graham_number: float | None     # √(22.5 × EPS × BPS)
    low: float | None               # graham_number × 0.85
    high: float | None              # graham_number × 1.15
    current_price: float | None     # 真实股价 = 市值 / 总股本

    # verdict
    verdict_code: str               # "extreme_low" / "low" / "fair" / "high" / "extreme_high" / "na"
    verdict_label: str              # "🟢🟢 极度低估" / ...
    deviation_pct: float | None     # (current - graham) / graham × 100

    # 计算明细(展示给用户)
    eps_ttm: float | None           # 真实股价 / PE-TTM
    bps: float | None               # 真实股价 / PB
    pe_ttm: float | None
    pb: float | None
    market_cap: float | None        # 市值(元)
    shares_outstanding: float | None  # 真实总股本 = 净利润 / EPS

    # 降级原因
    skip_reason: str | None = None


@dataclass
class PortfolioEntry:
    """portfolio.yaml 单条持仓。"""

    ticker: str
    name: str
    school: str
    rationale: str
    criteria_met: list[str] = field(default_factory=list)
    review_triggers: list[str] = field(default_factory=list)


# ─── portfolio.yaml 加载 ─────────────────────────────────────────────
def load_portfolio(path: Path | str = PORTFOLIO_PATH) -> dict[str, PortfolioEntry]:
    """加载持仓档案,返回 {ticker: PortfolioEntry}。"""
    path = Path(path)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # v2.8+ positions[] 已 merge 进 holdings[],直接读 holdings 字段。
    holdings = data.get("holdings", []) or []
    return {
        h["ticker"]: PortfolioEntry(
            ticker=h["ticker"],
            name=h.get("name", ""),
            school=h.get("school", ""),
            rationale=h.get("rationale", ""),
            criteria_met=h.get("criteria_met", []) or [],
            review_triggers=h.get("review_triggers", []) or [],
        )
        for h in holdings
    }


def is_in_portfolio(ticker: str, path: Path | str = PORTFOLIO_PATH) -> bool:
    """判断 ticker 是否在持仓档案里。"""
    return ticker in load_portfolio(path)


def _backup_portfolio(path: Path) -> Path | None:
    """改写 portfolio.yaml 前备份到 .bak(单层覆盖)。"""
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + ".bak")
    bak.write_bytes(path.read_bytes())
    return bak


def add_to_portfolio(ticker: str, name: str, school: str = "未分类",
                     rationale: str = "(待填写)",
                     path: Path | str = PORTFOLIO_PATH) -> bool:
    """把 ticker 加入持仓档案 holdings[](status=watch 默认)。已存在则跳过。

    v2.8+:positions[] 已合并到 holdings[],此函数直写 holdings 字段。
    新条目带 school/rationale,详细 criteria_met / review_triggers 由用户后续在 yaml 补全。

    返回 True 表示新增成功,False 表示已存在 / ticker 为空。
    """
    if not ticker:
        return False
    path = Path(path)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    else:
        doc = {}

    holdings = doc.setdefault("holdings", []) or []
    if any(str(h.get("ticker", "")).strip() == ticker for h in holdings):
        return False

    _backup_portfolio(path)
    holdings.append({
        "ticker": ticker,
        "name": name or ticker,
        "status": "watch",
        "school": school,
        "rationale": rationale,
        "criteria_met": [],
        "review_triggers": [],
    })
    doc["holdings"] = holdings
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return True


def remove_from_portfolio(ticker: str,
                          path: Path | str = PORTFOLIO_PATH) -> bool:
    """从持仓档案 holdings[] 物理移除 ticker(硬删,保兼容)。

    v2.8+:对 holdings[] 操作;若要软删归档(status=exited),改用 loader.close_holding。
    """
    if not ticker:
        return False
    path = Path(path)
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    holdings = doc.get("holdings") or []
    new_holdings = [h for h in holdings if str(h.get("ticker", "")).strip() != ticker]
    if len(new_holdings) == len(holdings):
        return False
    _backup_portfolio(path)
    doc["holdings"] = new_holdings
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return True


# ─── 数据加载(从 preson.duckdb)──────────────────────────────────────
def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _normalize_ticker(raw: str, market: str | None = None) -> str:
    """ticker 规范化 — 委托给 dashboard/tickers.py 单一可信源。

    口径:A 股 6 位 zero-padded(如 '000001' / '600519'),
         港股 5 位 zero-padded(如 '02097')。

    保留函数名 `_normalize_ticker` 以兼容现有 import / test。
    """
    return _shared_normalize_ticker(raw, market=market)


def _latest(con, table: str, ticker: str, metric: str) -> tuple[float | None, date | None]:
    """取 ticker 在 table 表 metric 最新非空值 + 数据日期。"""
    sql = (
        f"SELECT value, date FROM {table} "
        f"WHERE ticker=? AND metric=? AND value IS NOT NULL "
        f"ORDER BY date DESC LIMIT 1"
    )
    row = con.execute(sql, [ticker, metric]).fetchone()
    if row is None:
        return None, None
    return float(row[0]), row[1]


def load_price_metrics(ticker: str, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """加载 Graham Number 计算所需的全部字段。

    返回 dict:
        pe_ttm / pb / market_cap / eps_basic / net_income / 各自数据日期
    """
    ticker = _normalize_ticker(ticker)
    con = _conn(db_path)
    try:
        pe, pe_date = _latest(con, "valuation", ticker, "PE-TTM")
        pb, pb_date = _latest(con, "valuation", ticker, "PB")
        mcap, mcap_date = _latest(con, "valuation", ticker, "市值(元)")
        eps, eps_date = _latest(con, "growth", ticker, "基本每股收益")
        ni, ni_date = _latest(con, "growth", ticker, "归属于母公司普通股股东的净利润")
        return {
            "pe_ttm": pe,
            "pb": pb,
            "market_cap": mcap,
            "eps_basic": eps,
            "net_income": ni,
            "pe_date": pe_date,
            "pb_date": pb_date,
            "mcap_date": mcap_date,
            "eps_date": eps_date,
            "ni_date": ni_date,
        }
    finally:
        con.close()


# ─── verdict 阈值 ───────────────────────────────────────────────────
def _classify_verdict(current: float, graham: float) -> tuple[str, str]:
    """5 档 verdict 分类。返回 (code, label)。"""
    if current < graham * VERDICT_LOW:
        return "extreme_low", "🟢🟢 极度低估"
    if current < graham * VERDICT_LOW_SOFT:
        return "low", "🟢 低估"
    if current <= graham * VERDICT_HIGH_SOFT:
        return "fair", "🟡 合理"
    if current <= graham * VERDICT_HIGH:
        return "high", "🔴 高估"
    return "extreme_high", "🔴🔴 极度高估"


def _build_na(ticker: str, name: str, as_of: date | None, pe: float | None,
              pb: float | None, mcap: float | None, reason: str) -> FairPriceRange:
    """构造不适用降级返回。"""
    return FairPriceRange(
        ticker=ticker, name=name, verified=False, as_of=as_of,
        graham_number=None, low=None, high=None, current_price=None,
        verdict_code="na", verdict_label="⚪ 不适用",
        deviation_pct=None, eps_ttm=None, bps=None,
        pe_ttm=pe, pb=pb, market_cap=mcap, shares_outstanding=None,
        skip_reason=reason,
    )


# ─── 主入口:compute_fair_range ──────────────────────────────────────
def compute_fair_range(ticker: str, name: str = "",
                       db_path: Path | str = DB_PATH) -> FairPriceRange:
    """计算单只持仓的合理价格区间。

    返回 FairPriceRange,verified=False 时填 skip_reason。
    """
    pm = load_price_metrics(ticker, db_path)
    pe = pm["pe_ttm"]
    pb = pm["pb"]
    mcap = pm["market_cap"]
    eps = pm["eps_basic"]
    ni = pm["net_income"]
    as_of = pm["pe_date"] or pm["pb_date"] or pm["mcap_date"]

    # ── 不适用判定 ──
    if pe is None or pb is None or mcap is None:
        return _build_na(ticker, name, as_of, pe, pb, mcap,
                          "PE / PB / 市值 至少一项缺失(港股 / 数据未到位)")

    if pe <= 0:
        return _build_na(ticker, name, as_of, pe, pb, mcap,
                          "PE-TTM ≤ 0(公司亏损或扭亏中)")

    if pb <= 0:
        return _build_na(ticker, name, as_of, pe, pb, mcap,
                          "PB ≤ 0(净资产为负)")

    if eps is None or ni is None or eps <= 0 or ni <= 0:
        return _build_na(ticker, name, as_of, pe, pb, mcap,
                          "EPS 或净利润缺失/非正(无法反推总股本)")

    # ── 真实股价 = 市值 / 总股本(总股本 = 净利润 / EPS)──
    shares = ni / eps                       # 总股本
    current_price = mcap / shares           # 真实股价

    # ── Graham Number = 真实股价 × √(22.5 / (PE × PB))──
    pe_x_pb = pe * pb
    graham = current_price * math.sqrt(GRAHAM_RATIO / pe_x_pb)

    # ── EPS-TTM / BPS 反推(供 UI 明细展示)──
    eps_ttm = current_price / pe
    bps = current_price / pb

    low = graham * VERDICT_LOW_SOFT
    high = graham * VERDICT_HIGH_SOFT
    deviation = (current_price - graham) / graham * 100

    code, label = _classify_verdict(current_price, graham)

    return FairPriceRange(
        ticker=ticker, name=name, verified=True, as_of=as_of,
        graham_number=graham, low=low, high=high, current_price=current_price,
        verdict_code=code, verdict_label=label,
        deviation_pct=deviation,
        eps_ttm=eps_ttm, bps=bps, pe_ttm=pe, pb=pb,
        market_cap=mcap, shares_outstanding=shares,
        skip_reason=None,
    )


# ─── 格式化辅助(供 UI 使用)──────────────────────────────────────────
def format_price(value: float | None, decimals: int = 2) -> str:
    """数字格式化:1234.56 → '¥1,234.56';None → '—'。"""
    if value is None:
        return "—"
    return f"¥{value:,.{decimals}f}"


def verdict_color(verdict_code: str) -> tuple[str, str]:
    """返回 (background, text) HTML 颜色。"""
    palette = {
        "extreme_low": ("#a7f3d0", "#064e3b"),    # 深绿
        "low": ("#d1fae5", "#065f46"),             # 浅绿
        "fair": ("#fef3c7", "#92400e"),            # 琥珀
        "high": ("#fee2e2", "#991b1b"),            # 浅红
        "extreme_high": ("#fca5a5", "#7f1d1d"),    # 深红
        "na": ("#f3f4f6", "#4b5563"),              # 灰
    }
    return palette.get(verdict_code, palette["na"])


__all__ = [
    "FairPriceRange",
    "PortfolioEntry",
    "load_portfolio",
    "is_in_portfolio",
    "load_price_metrics",
    "compute_fair_range",
    "format_price",
    "verdict_color",
    "GRAHAM_RATIO",
    "VERDICT_LOW",
    "VERDICT_LOW_SOFT",
    "VERDICT_HIGH_SOFT",
    "VERDICT_HIGH",
]
