"""持仓快照 + F-Score + 再平衡提示报告。

用法:
    python3 .tools/portfolio/report.py
    python3 .tools/portfolio/report.py --year 2025
"""
from __future__ import annotations

import argparse
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "portfolio"))

from loader import load_portfolio

ENGINE = SourceFileLoader("engine", str(ROOT / ".tools" / "score" / "engine.py")).load_module()
RULES_DIR = ROOT / ".tools" / "rules"
DB_PATH = ROOT / "data" / "preson.duckdb"


def fetch_latest_pe_percentile(ticker: str) -> float | None:
    """从 valuation 表算 PE-TTM 全周期分位(0-1)。失败返回 None。"""
    try:
        import duckdb
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            row = con.execute(
                """
                WITH series AS (
                    SELECT value FROM valuation
                    WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
                )
                SELECT
                    (SELECT value FROM valuation
                     WHERE ticker = ? AND metric = 'PE-TTM'
                     ORDER BY date DESC LIMIT 1) AS latest,
                    (SELECT COUNT(*) FROM series WHERE value <= (
                        SELECT value FROM valuation
                        WHERE ticker = ? AND metric = 'PE-TTM'
                        ORDER BY date DESC LIMIT 1
                    )) * 1.0 / NULLIF((SELECT COUNT(*) FROM series), 0) AS pct
                """,
                [ticker, ticker, ticker],
            ).fetchone()
            return float(row[1]) if row and row[1] is not None else None
        finally:
            con.close()
    except Exception:
        return None


def fetch_fscore(ticker: str, year: int) -> int | None:
    rules_path = RULES_DIR / "piotroski.yaml"
    try:
        data = ENGINE.load_duckdb_data(ticker)
        result = ENGINE.run_score(rules_path, data, year)
        return int(result.total_score) if result else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024, help="F-Score 评估年份(默认 2024,因 2025 年报多数未披露)")
    args = ap.parse_args()

    p = load_portfolio()

    print(f"\n{'='*72}")
    print(f"  preson 投资组合快照  ·  status={p.status}  ·  更新于 {p.last_updated}")
    print(f"{'='*72}\n")

    print(f"💰 账户配置:总资本 ¥{p.account.total_capital:,.0f}  "
          f"|  目标权益占比 {p.account.target_equity_ratio:.0%}  "
          f"|  现金缓冲 [{p.account.cash_min_ratio:.0%}, {p.account.cash_max_ratio:.0%}]\n")

    actives = p.active()
    watches = p.watch()
    print(f"📊 持仓状态:active {len(actives)} 家  |  watch {len(watches)} 家  |  exited {len(p.exited)} 家\n")

    # 持仓评分表(active + watch 都打分,active 计权重)
    print(f"📋 评分快照(F-Score 年份={args.year},估值分位 = 全周期):\n")
    print(f"{'ticker':<8}{'name':<10}{'状态':<8}{'目标权重':>10}{'F-Score':>10}{'PE 分位':>10}  thesis")
    print("─" * 110)

    fscores: dict[str, int] = {}
    pcts: dict[str, float] = {}

    for h in (actives + watches):
        score = fetch_fscore(h.ticker, args.year)
        pct = fetch_latest_pe_percentile(h.ticker)
        if score is not None:
            fscores[h.ticker] = score
        if pct is not None:
            pcts[h.ticker] = pct

        score_str = f"{score}/9" if score is not None else "—"
        pct_str = f"{pct:.1%}" if pct is not None else "—"
        weight_str = f"{h.target_weight:.0%}" if h.target_weight else "—"
        print(f"{h.ticker:<8}{h.name:<8}{h.status:<8}{weight_str:>10}{score_str:>10}{pct_str:>10}  {h.thesis[:50]}")

    # 再平衡提示(只对 active 生效)
    print(f"\n🚨 再平衡提示:\n")
    alerts = p.rebalance_alerts(scores=fscores, valuation_pct=pcts)
    if not alerts:
        print(f"  ✅ 当前无 active 持仓或无触发(规则:单仓<{p.rebalance.max_position_weight:.0%} / 偏离<{p.rebalance.max_deviation_pct:.0%} / F-Score≥{p.rebalance.score_floor} / 估值分位 [{p.rebalance.valuation_floor_pct:.0%}, {p.rebalance.valuation_ceiling_pct:.0%}])")
    else:
        for a in alerts:
            print(f"  {a}")

    # watch 池中评分高 + 估值低的"加仓候选"
    print(f"\n🌟 watch 池加仓候选(F-Score ≥ 7 且 PE 分位 < 30%):\n")
    candidates = [
        (h, fscores.get(h.ticker), pcts.get(h.ticker))
        for h in watches
        if fscores.get(h.ticker) is not None and fscores[h.ticker] >= 7
        and pcts.get(h.ticker) is not None and pcts[h.ticker] < 0.30
    ]
    if not candidates:
        print(f"  (空)")
    else:
        for h, s, pct in candidates:
            print(f"  💎 {h.ticker} {h.name}  F-Score {s}/9  PE 分位 {pct:.1%}  → {h.thesis}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
