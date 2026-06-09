"""ETF 推荐引擎 (E3) — v2.5 行业分析与聚焦 / 任务包 05.

主入口:
    recommend(industry, top_n=3) -> list[ETFCandidate]
    list_all_recommendations() -> dict[str, list[ETFCandidate]]

数据来源:
- .config/industry_master.yaml          (industries[].etf_codes / leaders, fallback)
- .tools/rules/industry_etf_mapping.yaml (mapping[].recommended_etfs, 主源,带 theme/rationale)
- data/etf.duckdb                        (etf_meta + etf_prices 35 ETF / 16940 行)

排序:liquidity_score(60d 均 turnover 在全 35 ETF 池内的百分位)降序 → Top N
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDUSTRY_MASTER = PROJECT_ROOT / ".config" / "industry_master.yaml"
ETF_MAPPING = PROJECT_ROOT / ".tools" / "rules" / "industry_etf_mapping.yaml"
ETF_DB = PROJECT_ROOT / "data" / "etf.duckdb"


# ──────────────────────────────────────────────────────────────────
# Dataclass
# ──────────────────────────────────────────────────────────────────


@dataclass
class ETFCandidate:
    code: str
    name: str
    theme: str  # 主题 / 龙头 / 红利
    fund_type: str | None = None  # etf_meta.etf_type
    last_close: float | None = None
    return_1y: float | None = None  # 0.18 = +18%
    avg_turnover_60d: float | None = None  # 60 日均成交额
    liquidity_score: float = 0.0  # 0-100
    rationale: str = ""
    layer: str | None = None  # defensive / offensive / auxiliary
    target_pct: tuple | None = None  # (min%, max%)


# ──────────────────────────────────────────────────────────────────
# YAML 读取
# ──────────────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def _load_master_yaml() -> dict:
    d = _load_yaml(INDUSTRY_MASTER) or {}
    return d


def _load_mapping_yaml() -> dict:
    d = _load_yaml(ETF_MAPPING) or {}
    return d


def _find_master_industry(name: str) -> dict | None:
    d = _load_master_yaml()
    for ind in d.get("industries") or []:
        if ind.get("name") == name:
            return ind
    return None


def _find_mapping_industry(name: str) -> dict | None:
    d = _load_mapping_yaml()
    for m in d.get("mapping") or []:
        if m.get("industry") == name:
            return m
    return None


# ──────────────────────────────────────────────────────────────────
# DuckDB 数据
# ──────────────────────────────────────────────────────────────────


def _open_db():
    """返回 duckdb connection 或 None(打不开)。"""
    if not ETF_DB.exists():
        return None
    try:
        import duckdb

        return duckdb.connect(str(ETF_DB), read_only=True)
    except Exception:
        return None


def _fetch_etf_meta(con, code: str) -> tuple[str | None, str | None]:
    """返回 (etf_name, etf_type),都可能 None。"""
    try:
        row = con.execute(
            "SELECT etf_name, etf_type FROM etf_meta WHERE etf_code = ?",
            [code],
        ).fetchone()
        if row:
            return row[0], row[1]
    except Exception:
        pass
    return None, None


def _fetch_last_close(con, code: str) -> tuple[float | None, date | None]:
    """最新一日 close + 该日期。"""
    try:
        row = con.execute(
            "SELECT close, date FROM etf_prices "
            "WHERE etf_code = ? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 1",
            [code],
        ).fetchone()
        if row:
            return float(row[0]) if row[0] is not None else None, row[1]
    except Exception:
        pass
    return None, None


def _fetch_close_around(con, code: str, target: date) -> float | None:
    """取 target 日及之前最近一日 close(用于算 1y 涨跌)。"""
    try:
        row = con.execute(
            "SELECT close FROM etf_prices "
            "WHERE etf_code = ? AND date <= ? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 1",
            [code, target],
        ).fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return None


def _fetch_avg_turnover_60d(con, code: str, latest: date | None) -> float | None:
    """latest 日往前 60 日的 avg(turnover)。latest 为 None 则用 CURRENT_DATE。"""
    try:
        if latest is None:
            row = con.execute(
                "SELECT avg(turnover) FROM etf_prices "
                "WHERE etf_code = ? AND date >= (CURRENT_DATE - INTERVAL 60 DAY)",
                [code],
            ).fetchone()
        else:
            cutoff = latest - timedelta(days=60)
            row = con.execute(
                "SELECT avg(turnover) FROM etf_prices "
                "WHERE etf_code = ? AND date >= ? AND date <= ?",
                [code, cutoff, latest],
            ).fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return None


def _build_pool_turnover_map(con) -> dict[str, float]:
    """全 35 ETF 的 60 日(从全池最新日往前)平均 turnover 字典。"""
    pool: dict[str, float] = {}
    try:
        # 用全池最新日往前 60 d 作为统一窗口,避免不同 ETF 用不同 cutoff 互不可比
        latest_row = con.execute(
            "SELECT max(date) FROM etf_prices"
        ).fetchone()
        if not latest_row or latest_row[0] is None:
            return pool
        latest = latest_row[0]
        cutoff = latest - timedelta(days=60)
        rows = con.execute(
            "SELECT etf_code, avg(turnover) FROM etf_prices "
            "WHERE date >= ? AND date <= ? "
            "GROUP BY etf_code",
            [cutoff, latest],
        ).fetchall()
        for code, t in rows:
            if t is not None:
                pool[code] = float(t)
    except Exception:
        pass
    return pool


def _percentile_rank(value: float, pool: list[float]) -> float:
    """value 在 pool 内的百分位(0-100)。pool 空或 value None 返回 0。"""
    if not pool or value is None:
        return 0.0
    n = len(pool)
    below = sum(1 for x in pool if x < value)
    equal = sum(1 for x in pool if x == value)
    # 中位百分位:严格小于 + 一半相等
    pct = (below + 0.5 * equal) / n * 100.0
    return round(pct, 1)


# ──────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────


def _collect_yaml_etfs(industry: str) -> tuple[list[dict], str | None, tuple | None]:
    """按优先级合并 mapping + master 的 ETF 列表。

    返回 (entries, layer, target_pct):
        entries = [{"code": str, "name": str?, "theme": str?, "rationale": str?}, ...]
        layer / target_pct 来自 mapping yaml(无则 None)
    """
    seen: set[str] = set()
    entries: list[dict] = []
    layer: str | None = None
    target_pct: tuple | None = None

    m = _find_mapping_industry(industry)
    if m:
        layer = m.get("layer")
        tp = m.get("target_pct")
        if isinstance(tp, (list, tuple)) and len(tp) == 2:
            target_pct = (tp[0], tp[1])
        for e in m.get("recommended_etfs") or []:
            code = str(e.get("code") or "").strip()
            if not code or code in seen:
                continue
            entries.append({
                "code": code,
                "name": e.get("name"),
                "theme": e.get("theme"),
                "rationale": e.get("rationale"),
            })
            seen.add(code)

    master = _find_master_industry(industry)
    if master:
        for code in master.get("etf_codes") or []:
            code = str(code).strip()
            if not code or code in seen:
                continue
            entries.append({
                "code": code,
                "name": None,
                "theme": None,
                "rationale": None,
            })
            seen.add(code)

    return entries, layer, target_pct


def _format_rationale(theme: str, return_1y: float | None, liq_score: float) -> str:
    parts = [f"{theme}型"]
    if return_1y is not None:
        parts.append(f"1y {return_1y:+.1%}")
    else:
        parts.append("1y ?")
    parts.append(f"流动性分位 {liq_score:.0f}")
    return " / ".join(parts)


def recommend(industry: str, top_n: int = 3) -> list[ETFCandidate]:
    """给定行业 → 返回 Top N ETF 候选。

    无该行业 → 空 list。
    etf.duckdb 不可用 → 返回 yaml 静态信息,数据字段 None,liquidity_score=0。
    """
    entries, layer, target_pct = _collect_yaml_etfs(industry)
    if not entries:
        return []

    con = _open_db()
    pool_turnover: dict[str, float] = {}
    pool_values: list[float] = []
    db_ok = con is not None
    if db_ok:
        pool_turnover = _build_pool_turnover_map(con)
        pool_values = list(pool_turnover.values())

    candidates: list[ETFCandidate] = []
    try:
        for e in entries:
            code = e["code"]
            yaml_name = e.get("name")
            yaml_theme = e.get("theme") or "主题"
            yaml_rationale = e.get("rationale")

            fund_type: str | None = None
            db_name: str | None = None
            last_close: float | None = None
            return_1y: float | None = None
            avg_turnover_60d: float | None = None
            liquidity_score = 0.0
            in_db = False

            if db_ok and con is not None:
                db_name, fund_type = _fetch_etf_meta(con, code)
                last_close, latest_date = _fetch_last_close(con, code)
                in_db = last_close is not None or db_name is not None
                if last_close is not None and latest_date is not None:
                    earlier = _fetch_close_around(
                        con, code, latest_date - timedelta(days=365)
                    )
                    if earlier and earlier > 0:
                        return_1y = last_close / earlier - 1.0
                avg_turnover_60d = _fetch_avg_turnover_60d(con, code, latest_date)
                if avg_turnover_60d is not None and pool_values:
                    liquidity_score = _percentile_rank(
                        avg_turnover_60d, pool_values
                    )

            display_name = yaml_name or db_name or code

            if yaml_rationale:
                rationale = yaml_rationale
            elif not in_db:
                rationale = f"{yaml_theme}型 / 数据未入库"
            else:
                rationale = _format_rationale(
                    yaml_theme, return_1y, liquidity_score
                )

            candidates.append(
                ETFCandidate(
                    code=code,
                    name=display_name,
                    theme=yaml_theme,
                    fund_type=fund_type,
                    last_close=last_close,
                    return_1y=return_1y,
                    avg_turnover_60d=avg_turnover_60d,
                    liquidity_score=liquidity_score,
                    rationale=rationale,
                    layer=layer,
                    target_pct=target_pct,
                )
            )
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass

    # 排序:有数据(在库)优先,然后 liquidity_score 降序
    candidates.sort(
        key=lambda c: (
            0 if c.last_close is not None else 1,  # 在库的排前面
            -c.liquidity_score,
        )
    )
    return candidates[:top_n]


def list_all_recommendations() -> dict[str, list[ETFCandidate]]:
    """所有 industry_etf_mapping.yaml 里的行业,各推 Top 3。

    key = industry name(SW L2 中文)
    """
    out: dict[str, list[ETFCandidate]] = {}
    d = _load_mapping_yaml()
    for m in d.get("mapping") or []:
        ind = m.get("industry")
        if not ind:
            continue
        out[ind] = recommend(ind, top_n=3)
    # 也补 master 中独有的行业(防御性,通常 mapping 已涵盖)
    md = _load_master_yaml()
    for ind in md.get("industries") or []:
        name = ind.get("name")
        if name and name not in out:
            out[name] = recommend(name, top_n=3)
    return out


__all__ = ["ETFCandidate", "recommend", "list_all_recommendations"]
