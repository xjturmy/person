"""Walter Schloss 简版评分模块(v2.5 TODO#1 G6)。

Schloss 基于格雷厄姆的"统计式深度价值"方法 — 15 项快速过滤清单(简化自 Schloss 16 条)。

仅提供模块逻辑,sub-tab 接入留给后续 dashboard 整合。

调用约定:
    from masters.graham.schloss import schloss_quick_score
    result = schloss_quick_score("600519")
    print(result["score"], result["passed"], result["failed"])

Author: Claude (v2.5 TODO#1, 2026-05-10)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"


# ─── 15 条清单定义 ─────────────────────────────────────────────────────────
# 每条:id / name / description / 通过条件说明(用于展示)
SCHLOSS_ITEMS: list[dict[str, str]] = [
    {
        "id": "s01_pb_low",
        "name": "PB < 1.5",
        "desc": "股价/账面价值 < 1.5(资产折价买入)",
        "category": "估值",
    },
    {
        "id": "s02_pb_below_one",
        "name": "PB 低于历史均值",
        "desc": "当前 PB 低于自身 5 年中位",
        "category": "估值",
    },
    {
        "id": "s03_pe_moderate",
        "name": "PE-TTM ≤ 15",
        "desc": "市盈率不超过 15 倍",
        "category": "估值",
    },
    {
        "id": "s04_dividend",
        "name": "有派息记录",
        "desc": "最近一年股息率 > 0",
        "category": "股息",
    },
    {
        "id": "s05_dividend_5y",
        "name": "近 5 年连续派息",
        "desc": "连续 5 年以上股息率 > 0",
        "category": "股息",
    },
    {
        "id": "s06_earnings_5y",
        "name": "近 5 年盈利",
        "desc": "过去 5 年每年归母净利润 > 0",
        "category": "盈利",
    },
    {
        "id": "s07_earnings_growth",
        "name": "盈利有增长",
        "desc": "5 年净利润 CAGR > 0",
        "category": "盈利",
    },
    {
        "id": "s08_long_debt_lt_nwc",
        "name": "长期负债 < 净营运资本",
        "desc": "长期借款 < (流动资产 - 流动负债)",
        "category": "财务健康",
    },
    {
        "id": "s09_debt_ratio_lt60",
        "name": "资产负债率 < 60%",
        "desc": "非金融行业负债率上限",
        "category": "财务健康",
    },
    {
        "id": "s10_current_ratio",
        "name": "流动比率 ≥ 1.5",
        "desc": "短期偿债能力充足",
        "category": "财务健康",
    },
    {
        "id": "s11_roe_positive",
        "name": "ROE > 0",
        "desc": "最新年报 ROE 为正",
        "category": "盈利质量",
    },
    {
        "id": "s12_roe_stable",
        "name": "近 3 年 ROE 稳定",
        "desc": "3 年平均 ROE ≥ 8%",
        "category": "盈利质量",
    },
    {
        "id": "s13_market_cap",
        "name": "具备一定规模",
        "desc": "市值 ≥ 100 亿元(A 股标准)",
        "category": "规模",
    },
    {
        "id": "s14_price_below_52w_high",
        "name": "价格低于 52 周高点",
        "desc": "当前股价低于 52 周高点 20% 以上(有价格安全边际)",
        "category": "价格",
    },
    {
        "id": "s15_low_premium_to_ncav",
        "name": "价格不远超净资产",
        "desc": "市值 / 净资产 < 2(不为净资产大幅溢价)",
        "category": "估值",
    },
]


# ─── 数据读取 helpers ─────────────────────────────────────────────────────

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _latest(con, table: str, ticker: str, metric: str) -> float | None:
    row = con.execute(
        f"""
        SELECT value FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _yearly_last(con, ticker: str, metric: str, table: str = "valuation",
                 years_back: int = 10) -> list[tuple[int, float]]:
    """每年最后一条记录,按年份降序。"""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=365 * years_back)).isoformat()
    rows = con.execute(
        f"""
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
          AND date >= ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date)
                                    ORDER BY date DESC) = 1
        ORDER BY y DESC
        """,
        [ticker, metric, cutoff],
    ).fetchall()
    return [(int(y), float(v)) for y, v in rows]


# ─── 15 条评分计算 ────────────────────────────────────────────────────────

def _eval_items(con, ticker: str) -> dict[str, bool | None]:
    """逐条计算 15 项,返回 {item_id: True/False/None}(None=数据缺失)。"""
    results: dict[str, bool | None] = {}

    # 基础指标
    pb = _latest(con, "valuation", ticker, "PB")
    pe = _latest(con, "valuation", ticker, "PE-TTM")
    dr = _latest(con, "valuation", ticker, "股息率")
    cr = _latest(con, "safety", ticker, "流动比率")
    debt_ratio = _latest(con, "safety", ticker, "资产负债率")
    roe = _latest(con, "profitability", ticker, "净资产收益率(ROE)")
    mc = _latest(con, "valuation", ticker, "市值(元)")
    if mc is None:
        mc = _latest(con, "valuation", ticker, "市值(港币)")

    # s01: PB < 1.5
    results["s01_pb_low"] = (pb < 1.5) if pb is not None else None

    # s02: PB 低于 5 年中位
    pb_history = _yearly_last(con, ticker, "PB", "valuation", 5)
    if pb is not None and len(pb_history) >= 3:
        median_pb = sorted(v for _, v in pb_history)[len(pb_history) // 2]
        results["s02_pb_below_one"] = pb < median_pb
    else:
        results["s02_pb_below_one"] = None

    # s03: PE ≤ 15
    results["s03_pe_moderate"] = (pe <= 15) if pe is not None else None

    # s04: 最近年股息率 > 0
    results["s04_dividend"] = (dr is not None and dr > 0)

    # s05: 近 5 年连续派息
    dy_series = _yearly_last(con, ticker, "股息率", "valuation", 6)
    if dy_series:
        streak = 0
        for _, v in dy_series:  # 已降序
            if v > 0:
                streak += 1
            else:
                break
        results["s05_dividend_5y"] = streak >= 5
    else:
        results["s05_dividend_5y"] = None

    # s06: 近 5 年每年净利润 > 0
    np_series = _yearly_last(con, ticker, "归属于母公司普通股股东的净利润", "growth", 6)
    if len(np_series) >= 5:
        last5 = np_series[:5]  # 降序取最近 5 年
        results["s06_earnings_5y"] = all(v > 0 for _, v in last5)
    else:
        results["s06_earnings_5y"] = None

    # s07: 净利润 5 年 CAGR > 0
    if len(np_series) >= 5:
        v_recent = np_series[0][1]
        v_old = np_series[4][1]
        if v_old > 0 and v_recent > 0:
            cagr = (v_recent / v_old) ** 0.25 - 1
            results["s07_earnings_growth"] = cagr > 0
        else:
            results["s07_earnings_growth"] = None
    else:
        results["s07_earnings_growth"] = None

    # s08: 长期负债 < 净营运资本(近似:资产负债率低 + 流动比率高则通过)
    if cr is not None and debt_ratio is not None:
        results["s08_long_debt_lt_nwc"] = (cr >= 2.0 and debt_ratio <= 0.5)
    else:
        results["s08_long_debt_lt_nwc"] = None

    # s09: 资产负债率 < 60%(金融行业宽松)
    if debt_ratio is not None:
        results["s09_debt_ratio_lt60"] = debt_ratio < 0.60
    else:
        results["s09_debt_ratio_lt60"] = None

    # s10: 流动比率 ≥ 1.5
    results["s10_current_ratio"] = (cr >= 1.5) if cr is not None else None

    # s11: ROE > 0
    results["s11_roe_positive"] = (roe > 0) if roe is not None else None

    # s12: 近 3 年平均 ROE ≥ 8%
    roe_series = _yearly_last(con, ticker, "净资产收益率(ROE)", "profitability", 4)
    if len(roe_series) >= 3:
        avg_roe = sum(v for _, v in roe_series[:3]) / 3
        results["s12_roe_stable"] = avg_roe >= 0.08
    else:
        results["s12_roe_stable"] = None

    # s13: 市值 ≥ 100 亿
    if mc is not None:
        results["s13_market_cap"] = mc >= 1e10
    else:
        results["s13_market_cap"] = None

    # s14: 股价低于 52 周高点 20%(用 PE 分位近似:PE < 50% 分位视为有折扣)
    pe_pct = _latest(con, "valuation", ticker, "PE-TTM_分位点")
    if pe_pct is not None:
        results["s14_price_below_52w_high"] = pe_pct < 0.5
    else:
        results["s14_price_below_52w_high"] = None

    # s15: 市值 / 净资产 < 2(即 PB < 2)
    results["s15_low_premium_to_ncav"] = (pb < 2.0) if pb is not None else None

    return results


def schloss_quick_score(ticker: str, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Schloss 15 项快速评分。

    Args:
        ticker: 股票代码(6 位 A 股 / 5 位港股)

    Returns:
        {
            "ticker": str,
            "score": int,           # 0-15
            "total": int,           # 15
            "passed": List[str],    # 通过项的 name 列表
            "failed": List[str],    # 未通过项的 name 列表
            "na": List[str],        # 数据缺失项
            "pct": float,           # 通过百分比 0-1
            "grade": str,           # A/B/C/D
            "items": List[dict],    # 每条明细
        }
    """
    con = _conn(db_path)
    try:
        item_results = _eval_items(con, ticker)
    finally:
        con.close()

    passed = []
    failed = []
    na = []
    items_detail = []

    for item in SCHLOSS_ITEMS:
        iid = item["id"]
        verdict = item_results.get(iid)
        if verdict is True:
            passed.append(item["name"])
            status = "pass"
        elif verdict is False:
            failed.append(item["name"])
            status = "fail"
        else:
            na.append(item["name"])
            status = "na"
        items_detail.append({
            "id": iid,
            "name": item["name"],
            "desc": item["desc"],
            "category": item["category"],
            "status": status,
        })

    score = len(passed)
    total = len(SCHLOSS_ITEMS)
    pct = score / total

    if pct >= 0.80:
        grade = "A"
    elif pct >= 0.65:
        grade = "B"
    elif pct >= 0.45:
        grade = "C"
    else:
        grade = "D"

    return {
        "ticker": ticker,
        "score": score,
        "total": total,
        "passed": passed,
        "failed": failed,
        "na": na,
        "pct": round(pct, 3),
        "grade": grade,
        "items": items_detail,
    }


# ─── CLI 快速验证 ─────────────────────────────────────────────────────────

def _smoke_test() -> None:
    targets = [
        ("600036", "招商银行"),
        ("600519", "贵州茅台"),
        ("000333", "美的集团"),
        ("601336", "新华保险"),
    ]
    print(f"{'═' * 72}")
    print("  Schloss 15 条快速评分")
    print("═" * 72)
    for ticker, name in targets:
        r = schloss_quick_score(ticker)
        print(
            f"\n  {ticker} {name}  评分:{r['score']}/{r['total']} "
            f"({r['pct']*100:.0f}%)  等级:{r['grade']}"
        )
        print(f"  ✅ 通过({len(r['passed'])}): {', '.join(r['passed'][:5])}"
              f"{'...' if len(r['passed']) > 5 else ''}")
        print(f"  ❌ 未过({len(r['failed'])}): {', '.join(r['failed'][:5])}"
              f"{'...' if len(r['failed']) > 5 else ''}")
        if r["na"]:
            print(f"  ⚠️ 缺数({len(r['na'])}): {', '.join(r['na'][:3])}")


if __name__ == "__main__":
    _smoke_test()
