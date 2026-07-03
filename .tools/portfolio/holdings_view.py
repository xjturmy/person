"""持仓总览数据装配 — 给 dash-04 决策中心 L0 上半段用。

核心输出:HoldingsSnapshot dataclass
- 单仓行(权重/市值/浮盈/F-Score/估值分位)
- 行业聚合(集中度)
- 加权 F-Score(按目标权重)
- 决策审计提示(买入超 N 个月未复盘)

外部依赖:
- portfolio.loader.load_portfolio
- DuckDB:data/preson.duckdb(prices / valuation / Piotroski)
- DuckDB:data/decisions.duckdb(决策日志)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "portfolio"))
sys.path.insert(0, str(ROOT / ".tools" / "score"))

from loader import Holding, Portfolio, load_portfolio  # noqa: E402

ENGINE = SourceFileLoader("engine", str(ROOT / ".tools" / "score" / "engine.py")).load_module()
DB_PATH = ROOT / "data" / "preson.duckdb"
DECISIONS_DB = ROOT / "data" / "decisions.duckdb"
RULES_DIR = ROOT / ".tools" / "rules"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _rules_signature() -> tuple[tuple[str, float], ...]:
    if not RULES_DIR.exists():
        return ()
    return tuple(sorted((p.name, _mtime(p)) for p in RULES_DIR.glob("*.yaml")))


@lru_cache(maxsize=8)
def _load_portfolio_cached(path_str: str, mtime: float) -> Portfolio:
    return load_portfolio(Path(path_str))


@dataclass
class HoldingRow:
    ticker: str
    name: str
    status: str
    shares: float | None
    cost_basis: float | None
    target_weight: float
    actual_weight: float          # 0-1, 仅 active 持仓内
    deviation: float              # actual - target
    last_price: float | None
    market_value: float | None
    cost_total: float | None
    pnl: float | None             # 浮盈浮亏
    pnl_pct: float | None         # 浮盈%
    fscore: int | None
    pe_pct: float | None          # 0-1
    tags: list[str] = field(default_factory=list)
    thesis: str = ""
    school: str = ""


@dataclass
class IndustryAgg:
    tag: str                       # 主标签(取 tags[0])
    n_holdings: int
    weight: float                  # 该行业总权重
    avg_fscore: float | None


@dataclass
class DecisionAuditAlert:
    ticker: str
    name: str
    last_decision_date: date
    last_action: str
    months_since: int
    msg: str


@dataclass
class HoldingsSnapshot:
    portfolio_status: str
    total_capital: float
    target_equity_ratio: float
    rows: list[HoldingRow]
    industry_agg: list[IndustryAgg]
    weighted_fscore: float | None  # 按 active 权重加权 F-Score
    cash_value: float              # 估算现金值(target_equity_ratio 反推)
    cash_ratio: float              # 现金/总资本
    audit_alerts: list[DecisionAuditAlert]
    rebalance_alerts: list[str]    # 再平衡引擎给的提示
    ticker_to_school: dict[str, str] = field(default_factory=dict)


def _last_price(con, ticker: str) -> float | None:
    """从 prices 表取最近收盘价。"""
    try:
        row = con.execute(
            "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            [ticker],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


@lru_cache(maxsize=32)
def _latest_prices_cached(tickers: tuple[str, ...], db_mtime: float) -> dict[str, float]:
    if not tickers or db_mtime <= 0:
        return {}
    import duckdb

    placeholders = ",".join("?" for _ in tickers)
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            rows = con.execute(
                f"""
                SELECT ticker, close
                FROM (
                    SELECT ticker, close,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                    FROM prices
                    WHERE ticker IN ({placeholders})
                )
                WHERE rn = 1
                """,
                list(tickers),
            ).fetchall()
            return {str(t): float(px) for t, px in rows if px is not None}
        finally:
            con.close()
    except Exception:
        return {}


def _pe_and_pct(con, ticker: str) -> tuple[float | None, float | None]:
    """最新 PE-TTM + 10 年窗口分位(全局统一口径,与 score_card/screener/lynch 一致)。"""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=365 * 10)).isoformat()
    try:
        row = con.execute(
            """
            WITH series AS (
                SELECT value FROM valuation
                WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
                  AND date >= ?
            ),
            latest AS (
                SELECT value FROM valuation
                WHERE ticker = ? AND metric = 'PE-TTM'
                ORDER BY date DESC LIMIT 1
            )
            SELECT
                (SELECT value FROM latest),
                (SELECT COUNT(*) FROM series WHERE value <= (SELECT value FROM latest))
                    * 1.0 / NULLIF((SELECT COUNT(*) FROM series), 0)
            """,
            [ticker, cutoff, ticker],
        ).fetchone()
        return ((float(row[0]) if row[0] is not None else None),
                (float(row[1]) if row[1] is not None else None))
    except Exception:
        return None, None


@lru_cache(maxsize=32)
def _pe_and_pct_cached(
    tickers: tuple[str, ...],
    cutoff: str,
    db_mtime: float,
) -> dict[str, tuple[float | None, float | None]]:
    if not tickers or db_mtime <= 0:
        return {}
    import duckdb

    placeholders = ",".join("?" for _ in tickers)
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            rows = con.execute(
                f"""
                WITH latest AS (
                    SELECT ticker, value
                    FROM (
                        SELECT ticker, value,
                               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                        FROM valuation
                        WHERE ticker IN ({placeholders})
                          AND metric = 'PE-TTM'
                    )
                    WHERE rn = 1
                ),
                series AS (
                    SELECT ticker, value
                    FROM valuation
                    WHERE ticker IN ({placeholders})
                      AND metric = 'PE-TTM'
                      AND value IS NOT NULL
                      AND date >= ?
                )
                SELECT
                    l.ticker,
                    l.value,
                    SUM(CASE WHEN s.value <= l.value THEN 1 ELSE 0 END)
                        * 1.0 / NULLIF(COUNT(s.value), 0) AS pct
                FROM latest l
                LEFT JOIN series s ON s.ticker = l.ticker
                GROUP BY l.ticker, l.value
                """,
                [*tickers, *tickers, cutoff],
            ).fetchall()
            return {
                str(t): (
                    float(pe) if pe is not None else None,
                    float(pct) if pct is not None else None,
                )
                for t, pe, pct in rows
            }
        finally:
            con.close()
    except Exception:
        return {}


def _fscore(ticker: str, year: int) -> int | None:
    rules = RULES_DIR / "piotroski.yaml"
    if not rules.exists():
        return None
    try:
        data = ENGINE.load_duckdb_data(ticker, db_path=DB_PATH)
        result = ENGINE.run_score(rules, data, year)
        return int(round(result.total_score)) if result else None
    except Exception:
        return None


@lru_cache(maxsize=16)
def _rules_doc_cached(path_str: str, mtime: float) -> dict:
    import yaml

    return yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}


def _run_score_cached_rules(rules_path: Path, data: Any, year: int):
    rules_doc = _rules_doc_cached(str(rules_path), _mtime(rules_path))

    if data.industry in rules_doc.get("exclude_industries", []):
        return None

    industry_files = rules_doc.get("industry_specific_files") or {}
    specific_filename = industry_files.get(data.industry)
    if specific_filename:
        specific_path = rules_path.parent / specific_filename
        if specific_path.exists() and specific_path != rules_path:
            return _run_score_cached_rules(specific_path, data, year)

    evaluator = ENGINE.FormulaEvaluator(data, year)
    details = []
    for rule in rules_doc.get("rules", []):
        score, passed, formula = ENGINE.eval_rule(rule, evaluator)
        details.append(ENGINE.RuleResult(
            rule_id=rule["id"],
            name=rule.get("name", rule["id"]),
            passed=passed,
            score=float(score),
            formula=formula,
        ))

    total = sum(d.score for d in details)
    return ENGINE.ScoreResult(
        master=rules_doc["master"],
        master_cn=rules_doc["master_cn"],
        method=rules_doc.get("method", ""),
        ticker=data.ticker,
        year=year,
        total_score=total,
        max_score=rules_doc.get("max_score"),
        rating=ENGINE.classify(total, rules_doc.get("threshold", {})),
        details=details,
    )


@lru_cache(maxsize=16)
def _fscores_cached(
    tickers: tuple[str, ...],
    year: int,
    db_mtime: float,
    rules_signature: tuple[tuple[str, float], ...],
) -> dict[str, int]:
    rules = RULES_DIR / "piotroski.yaml"
    if not tickers or db_mtime <= 0 or not rules.exists():
        return {}
    import duckdb

    placeholders = ",".join("?" for _ in tickers)
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            info_rows = con.execute(
                f"SELECT ticker, name, category FROM companies WHERE ticker IN ({placeholders})",
                list(tickers),
            ).fetchall()
            data_by_ticker = {
                str(t): ENGINE.CompanyData(
                    ticker=str(t),
                    name=name or str(t),
                    industry=ENGINE.CATEGORY_TO_INDUSTRY.get(category or "", "未知"),
                    metrics={},
                )
                for t, name, category in info_rows
            }
            if not data_by_ticker:
                return {}

            existing_tables = {
                r[0] for r in con.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()
            }
            active_tickers = tuple(data_by_ticker.keys())
            active_placeholders = ",".join("?" for _ in active_tickers)
            for table, mappings in ENGINE.DUCKDB_METRIC_MAP.items():
                if table not in existing_tables:
                    continue
                metric_names = [cn for cn, _ in mappings]
                metric_placeholders = ",".join("?" for _ in metric_names)
                key_by_metric = dict(mappings)
                rows = con.execute(
                    f"""
                    SELECT ticker, EXTRACT(YEAR FROM date) AS y, metric, value
                    FROM {table}
                    WHERE ticker IN ({active_placeholders})
                      AND metric IN ({metric_placeholders})
                      AND MONTH(date) = 12
                      AND DAY(date) = 31
                    """,
                    [*active_tickers, *metric_names],
                ).fetchall()
                for ticker, y, metric, value in rows:
                    if value is None:
                        continue
                    data = data_by_ticker.get(str(ticker))
                    key = key_by_metric.get(metric)
                    if data is None or key is None:
                        continue
                    data.metrics.setdefault(key, {})[int(y)] = float(value)
        finally:
            con.close()

        result: dict[str, int] = {}
        for ticker, data in data_by_ticker.items():
            try:
                ENGINE._add_derived_metrics(data.metrics)
                score = _run_score_cached_rules(rules, data, year)
                if score:
                    result[ticker] = int(round(score.total_score))
            except Exception:
                continue
        return result
    except Exception:
        return {}


def _last_decision(ticker: str) -> tuple[date | None, str | None]:
    if not DECISIONS_DB.exists():
        return None, None
    try:
        import duckdb
        con = duckdb.connect(str(DECISIONS_DB), read_only=True)
        try:
            row = con.execute(
                "SELECT date, action FROM decisions "
                "WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                [ticker],
            ).fetchone()
            if row and row[0]:
                d = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
                return d, str(row[1])
        finally:
            con.close()
    except Exception:
        pass
    return None, None


@lru_cache(maxsize=32)
def _last_decisions_cached(
    tickers: tuple[str, ...],
    decisions_mtime: float,
) -> dict[str, tuple[date, str]]:
    if not tickers or decisions_mtime <= 0:
        return {}
    import duckdb

    placeholders = ",".join("?" for _ in tickers)
    try:
        con = duckdb.connect(str(DECISIONS_DB), read_only=True)
        try:
            rows = con.execute(
                f"""
                SELECT ticker, date, action
                FROM (
                    SELECT ticker, date, action,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                    FROM decisions
                    WHERE ticker IN ({placeholders})
                )
                WHERE rn = 1
                """,
                list(tickers),
            ).fetchall()
            out: dict[str, tuple[date, str]] = {}
            for ticker, d, action in rows:
                if not d:
                    continue
                parsed = d if isinstance(d, date) else date.fromisoformat(str(d))
                out[str(ticker)] = (parsed, str(action))
            return out
        finally:
            con.close()
    except Exception:
        return {}


def build_snapshot(
    portfolio: Portfolio | None = None,
    fscore_year: int | None = None,
    audit_threshold_months: int = 3,
) -> HoldingsSnapshot:
    portfolio_path = ROOT / ".config" / "portfolio.yaml"
    p = portfolio or _load_portfolio_cached(str(portfolio_path), _mtime(portfolio_path))
    year = fscore_year or (date.today().year - 1)

    rows: list[HoldingRow] = []
    actives = p.active()
    visible_holdings = actives + p.watch()
    tickers = tuple(dict.fromkeys(h.ticker for h in visible_holdings))
    db_mtime = _mtime(DB_PATH)
    prices = _latest_prices_cached(tickers, db_mtime)
    cutoff = (date.today() - timedelta(days=365 * 10)).isoformat()
    pe_pcts = _pe_and_pct_cached(tickers, cutoff, db_mtime)
    fscores = _fscores_cached(tickers, year, db_mtime, _rules_signature())

    # 先一次性算 active 总市值用于权重
    market_values: dict[str, float] = {}
    for h in actives:
        if h.shares is None:
            continue
        px = prices.get(h.ticker)
        px = px if px is not None else (h.cost_basis or 0)
        market_values[h.ticker] = h.shares * px

    total_active_mv = sum(market_values.values()) or 0.0

    for h in visible_holdings:
        last_px = prices.get(h.ticker)
        mv = (h.shares * last_px) if (h.shares is not None and last_px is not None) else None
        cost_t = h.cost_total
        pnl = (mv - cost_t) if (mv is not None and cost_t is not None) else None
        pnl_pct = (pnl / cost_t) if (pnl is not None and cost_t and cost_t > 0) else None
        actual_w = (market_values.get(h.ticker, 0.0) / total_active_mv) if (h.status == "active" and total_active_mv) else 0.0
        deviation = actual_w - (h.target_weight or 0.0) if h.status == "active" else 0.0
        _pe, pct = pe_pcts.get(h.ticker, (None, None))
        fs = fscores.get(h.ticker)

        rows.append(HoldingRow(
            ticker=h.ticker, name=h.name, status=h.status,
            shares=h.shares, cost_basis=h.cost_basis,
            target_weight=h.target_weight or 0.0,
            actual_weight=actual_w, deviation=deviation,
            last_price=last_px, market_value=mv,
            cost_total=cost_t, pnl=pnl, pnl_pct=pnl_pct,
            fscore=fs, pe_pct=pct,
            tags=list(h.tags or []), thesis=h.thesis or "",
            school=h.school or "",
        ))

    # 行业聚合(按 tags[0] 主标签)
    agg_map: dict[str, dict] = {}
    for r in rows:
        if r.status != "active":
            continue
        tag = r.tags[0] if r.tags else "未分类"
        a = agg_map.setdefault(tag, {"n": 0, "w": 0.0, "fs_sum": 0, "fs_n": 0})
        a["n"] += 1
        a["w"] += r.actual_weight
        if r.fscore is not None:
            a["fs_sum"] += r.fscore
            a["fs_n"] += 1
    industry_agg = [
        IndustryAgg(tag=k, n_holdings=v["n"], weight=v["w"],
                    avg_fscore=(v["fs_sum"] / v["fs_n"]) if v["fs_n"] else None)
        for k, v in sorted(agg_map.items(), key=lambda x: x[1]["w"], reverse=True)
    ]

    # 加权 F-Score(active)
    wf_num, wf_den = 0.0, 0.0
    for r in rows:
        if r.status == "active" and r.fscore is not None and r.target_weight > 0:
            wf_num += r.fscore * r.target_weight
            wf_den += r.target_weight
    weighted_fscore = wf_num / wf_den if wf_den > 0 else None

    # 现金估算(总资本 × (1 - 目标权益比) 视为目标现金)
    cash_value = p.account.total_capital * (1 - p.account.target_equity_ratio)
    cash_ratio = (1 - p.account.target_equity_ratio)

    # 决策审计:active 持仓上次决策超过 N 个月
    audit_alerts: list[DecisionAuditAlert] = []
    today = date.today()
    threshold = timedelta(days=audit_threshold_months * 30)
    last_decisions = _last_decisions_cached(
        tuple(r.ticker for r in rows if r.status == "active"),
        _mtime(DECISIONS_DB),
    )
    for r in rows:
        if r.status != "active":
            continue
        last_date, last_action = last_decisions.get(r.ticker, (None, None))
        if last_date is None:
            audit_alerts.append(DecisionAuditAlert(
                ticker=r.ticker, name=r.name,
                last_decision_date=date(1970, 1, 1), last_action="(无)",
                months_since=999,
                msg=f"📋 {r.name} 在 active 但**从未在 decisions.duckdb 留过决策**,需补录",
            ))
            continue
        delta = today - last_date
        if delta > threshold:
            months = int(delta.days / 30)
            audit_alerts.append(DecisionAuditAlert(
                ticker=r.ticker, name=r.name,
                last_decision_date=last_date, last_action=last_action or "?",
                months_since=months,
                msg=f"⏰ {r.name} 上次决策({last_action} @ {last_date})已 {months} 个月未复盘",
            ))

    # 复用 portfolio 的再平衡 alerts
    fscores = {r.ticker: r.fscore for r in rows if r.fscore is not None}
    pcts = {r.ticker: r.pe_pct for r in rows if r.pe_pct is not None}
    rebalance_alerts = p.rebalance_alerts(scores=fscores, valuation_pct=pcts)

    return HoldingsSnapshot(
        portfolio_status=p.status,
        total_capital=p.account.total_capital,
        target_equity_ratio=p.account.target_equity_ratio,
        rows=rows,
        industry_agg=industry_agg,
        weighted_fscore=weighted_fscore,
        cash_value=cash_value,
        cash_ratio=cash_ratio,
        audit_alerts=audit_alerts,
        rebalance_alerts=rebalance_alerts,
        ticker_to_school={h.ticker: (h.school or "") for h in p.holdings},
    )


# ─── CLI 自检 ───────────────────────────────────────────────────────
def _main() -> int:
    snap = build_snapshot()
    print(f"组合状态:{snap.portfolio_status}  ·  active={sum(1 for r in snap.rows if r.status=='active')}  ·  watch={sum(1 for r in snap.rows if r.status=='watch')}")
    print(f"加权 F-Score:{snap.weighted_fscore}")
    print(f"行业聚合:{[(a.tag, a.n_holdings, f'{a.weight:.1%}') for a in snap.industry_agg]}")
    print(f"决策审计:{len(snap.audit_alerts)} 项 alert")
    print(f"再平衡:{len(snap.rebalance_alerts)} 项 alert")
    for a in snap.rebalance_alerts[:3]:
        print(f"  - {a}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
