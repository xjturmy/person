"""决策写入时,从 preson.duckdb 抓取当时的指标快照。

输入:ticker(如 "600519")、date(可选,默认抓最新)
输出:dict — pe / pb / pe_pct_10y / fscore / roe / extra...

只读连接 preson.duckdb,不与 MCP / Streamlit 写锁冲突。
失败时返回空 dict;调用方仍能写入决策(snapshot_json 为 null)。
"""
from __future__ import annotations

from datetime import date as _date
from pathlib import Path
from typing import Any, Optional

import duckdb

ROOT = Path(__file__).resolve().parents[2]
PRESON_DB = ROOT / "data" / "preson.duckdb"


def _conn() -> Optional[duckdb.DuckDBPyConnection]:
    if not PRESON_DB.exists():
        return None
    try:
        return duckdb.connect(str(PRESON_DB), read_only=True)
    except Exception:
        return None


def _latest_metric(con, table: str, ticker: str, metric: str,
                   on_or_before: Optional[_date]) -> Optional[float]:
    sql = f"""
        SELECT value FROM {table}
        WHERE ticker = ? AND metric = ?
              {"AND date <= ?" if on_or_before else ""}
        ORDER BY date DESC LIMIT 1
    """
    args: list[Any] = [ticker, metric]
    if on_or_before:
        args.append(on_or_before)
    row = con.execute(sql, args).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _percentile_10y(con, ticker: str, metric: str,
                    on_or_before: Optional[_date]) -> Optional[float]:
    """近似 valuation_percentile:在 10 年窗口内算当前值的分位 (0-1)。"""
    end_clause = "AND date <= ?" if on_or_before else ""
    args: list[Any] = [ticker, metric]
    if on_or_before:
        args.append(on_or_before)
    sql = f"""
        WITH win AS (
            SELECT date, value FROM valuation
            WHERE ticker = ? AND metric = ? {end_clause}
              AND date >= (
                  SELECT MAX(date) - INTERVAL 10 YEAR FROM valuation
                  WHERE ticker = ? AND metric = ? {end_clause}
              )
        ),
        cur AS (SELECT value FROM win ORDER BY date DESC LIMIT 1)
        SELECT
            (SELECT COUNT(*) FROM win WHERE value <= (SELECT value FROM cur))::DOUBLE
          / NULLIF((SELECT COUNT(*) FROM win), 0)
    """
    args2 = args + args
    try:
        row = con.execute(sql, args2).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def capture(ticker: str, on_or_before: Optional[_date] = None) -> dict[str, Any]:
    """抓取该 ticker 在 on_or_before(默认最新)的快照。"""
    con = _conn()
    if con is None:
        return {}
    try:
        snap: dict[str, Any] = {"ticker": ticker}
        if on_or_before:
            snap["as_of"] = on_or_before.isoformat()

        snap["pe"] = _latest_metric(con, "valuation", ticker, "PE-TTM", on_or_before)
        snap["pb"] = _latest_metric(con, "valuation", ticker, "PB", on_or_before)
        snap["dy"] = _latest_metric(con, "valuation", ticker, "股息率", on_or_before)

        snap["pe_pct_10y"] = _percentile_10y(con, ticker, "PE-TTM", on_or_before)
        snap["pb_pct_10y"] = _percentile_10y(con, ticker, "PB", on_or_before)

        snap["roe"] = _latest_metric(con, "profitability", ticker,
                                     "净资产收益率(ROE)", on_or_before)
        snap["gm"] = _latest_metric(con, "profitability", ticker,
                                    "毛利率(GM)", on_or_before)

        snap["rev_yoy"] = _latest_metric(con, "growth", ticker,
                                         "营业收入_同比", on_or_before)
        snap["np_yoy"] = _latest_metric(con, "growth", ticker,
                                        "归母净利润_同比", on_or_before)

        snap["debt_ratio"] = _latest_metric(con, "safety", ticker,
                                            "资产负债率", on_or_before)

        # F-Score 暂不在主库,留空,后续 2.2 审计接入大师评分时填充
        snap["fscore"] = None

        # 清洗 None
        out = {k: v for k, v in snap.items() if v is not None}
    finally:
        con.close()

    # Phase C C4 · 同行对比建议快照(peers.duckdb 独立库)
    try:
        import sys as _sys
        _dash = ROOT / ".tools" / "dashboard"
        if str(_dash) not in _sys.path:
            _sys.path.insert(0, str(_dash))
        import peer_advisor as _pa  # noqa: WPS433
        _adv = _pa.advise(ticker)
        if _adv is not None and _adv.n_peers > 0:
            out["peer_advice"] = {
                "overall_label": _adv.overall_label,
                "quality_label": _adv.quality_label,
                "weighted_sum": round(_adv.weighted_sum, 1),
                "industry": _adv.industry,
                "n_peers": _adv.n_peers,
                "top_evidence": [
                    {"metric": v.metric,
                     "percentile": round(v.percentile, 0) if v.percentile is not None else None,
                     "label": v.label,
                     "signal": v.signal}
                    for v in sorted(_adv.verdicts,
                                     key=lambda x: abs(x.signal) * x.weight,
                                     reverse=True)
                    if v.signal != 0 and v.percentile is not None
                ][:3],
            }
    except Exception:
        # 同行库未刷新或缺数据时静默跳过,不阻塞主 snapshot
        pass

    return out


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "600519"
    import json as _json
    print(_json.dumps(capture(t), ensure_ascii=False, indent=2, default=str))
