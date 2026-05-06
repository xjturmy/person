"""rebalance_planner 单测 — mock HoldingsSnapshot 不依赖 DuckDB."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from holdings_view import HoldingRow, HoldingsSnapshot  # noqa: E402
from loader import RebalanceRules, Account, Portfolio, Holding  # noqa: E402
from rebalance_planner import apply_proposals, plan  # noqa: E402

errs: list[str] = []


def expect(c: bool, msg: str) -> None:
    print(f"  {'✅' if c else '❌'} {msg}")
    if not c:
        errs.append(msg)


def make_row(**kw):
    base = dict(
        ticker="600519", name="贵州茅台", status="active",
        shares=100.0, cost_basis=1500.0,
        target_weight=0.10, actual_weight=0.10, deviation=0.0,
        last_price=1500.0, market_value=150000.0, cost_total=150000.0,
        pnl=0.0, pnl_pct=0.0,
        fscore=7, pe_pct=0.50,
        tags=["白酒"], thesis="",
    )
    base.update(kw)
    return HoldingRow(**base)


def make_snap(rows):
    return HoldingsSnapshot(
        portfolio_status="live", total_capital=1000000.0,
        target_equity_ratio=0.7,
        cash_value=300000.0, cash_ratio=0.30,
        rows=rows, industry_agg=[], weighted_fscore=7.0,
        audit_alerts=[], rebalance_alerts=[],
    )


def make_portfolio():
    return Portfolio(
        status="live", last_updated="2026-05-05",
        account=Account(total_capital=1000000),
        rebalance=RebalanceRules(
            max_position_weight=0.20, max_deviation_pct=0.05,
            score_floor=4, valuation_ceiling_pct=0.85, valuation_floor_pct=0.15,
        ),
        holdings=[], exited=[],
    )


print("─── 规则 1:超单仓上限 → 减仓 ───")
rows = [make_row(ticker="600519", actual_weight=0.25, target_weight=0.20)]
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 1, "1 条 proposal")
expect(props[0].rule == "max_position", "rule=max_position")
expect(props[0].action == "减仓", "action=减仓")
expect(abs(props[0].new_target - 0.18) < 1e-6, f"new_target≈0.18 (得到 {props[0].new_target})")
expect(props[0].delta_pp < 0, "delta_pp < 0")

print("─── 规则 2:估值高位 → 减仓 ───")
rows = [make_row(ticker="600036", name="招商银行",
                 actual_weight=0.10, target_weight=0.10, pe_pct=0.92)]
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 1, "1 条")
expect(props[0].rule == "valuation_high", "rule=valuation_high")
expect(abs(props[0].new_target - 0.07) < 1e-6, f"new=0.07(得到 {props[0].new_target})")

print("─── 规则 3:估值低位 → 加仓 ───")
rows = [make_row(ticker="000333", name="美的集团",
                 actual_weight=0.08, target_weight=0.08, pe_pct=0.10)]
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 1, "1 条")
expect(props[0].rule == "valuation_low", "rule=valuation_low")
expect(props[0].action == "加仓", "action=加仓")
expect(abs(props[0].new_target - 0.10) < 1e-6, f"new=0.10(得到 {props[0].new_target})")

print("─── 规则 4:F-Score 跌破 → 观察(review_only)───")
rows = [make_row(ticker="000858", actual_weight=0.05, target_weight=0.05,
                 fscore=2, pe_pct=0.50)]
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 1, "1 条")
expect(props[0].review_only, "review_only=True")
expect(props[0].new_target == props[0].old_target, "target 不变")

print("─── 规则 5:偏离阈值 → 观察 ───")
rows = [make_row(ticker="600276", target_weight=0.10, actual_weight=0.18,
                 deviation=0.08, pe_pct=0.50, fscore=7)]
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 1, f"1 条(得到 {len(props)})")
expect(props[0].rule == "deviation", "rule=deviation")
expect(props[0].review_only, "review_only=True")

print("─── 多规则同时触发 → 优先级 max_position ───")
rows = [make_row(ticker="600519", actual_weight=0.30, target_weight=0.25,
                 pe_pct=0.92, fscore=2)]  # 三规则同时
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 1, "1 条(最高优先级)")
expect(props[0].rule == "max_position", "选 max_position")

print("─── 空 snapshot ───")
props = plan(make_snap([]), make_portfolio())
expect(len(props) == 0, "0 条")

print("─── 非 active 持仓被忽略 ───")
rows = [make_row(status="watch", actual_weight=0.30)]
props = plan(make_snap(rows), make_portfolio())
expect(len(props) == 0, "watch 持仓不出 proposal")

print("─── apply_proposals(dry_run)───")
with tempfile.TemporaryDirectory() as td:
    test_yaml = Path(td) / "portfolio.yaml"
    test_yaml.write_text(yaml.safe_dump({
        "_meta": {"version": "1.0", "status": "live"},
        "account": {}, "rebalance": {},
        "holdings": [
            {"ticker": "600519", "name": "贵州茅台", "status": "active",
             "shares": 100, "cost_basis": 1500.0, "target_weight": 0.25},
        ],
        "exited": [],
    }, allow_unicode=True), encoding="utf-8")

    rows = [make_row(ticker="600519", actual_weight=0.30, target_weight=0.25, pe_pct=0.50)]
    proposals = plan(make_snap(rows), make_portfolio())
    expect(len(proposals) == 1, "1 条 proposal")

    # 重定向 DEFAULT_YAML
    import loader as _loader
    orig_path = _loader.DEFAULT_YAML
    _loader.DEFAULT_YAML = test_yaml
    try:
        result = apply_proposals(proposals, decisions_db=None, dry_run=False)
        expect(result["applied"] == 1, f"applied=1(得到 {result['applied']})")
        expect(result["backup"] is not None, "产生备份")

        after = yaml.safe_load(test_yaml.read_text(encoding="utf-8"))
        h = after["holdings"][0]
        expect(abs(h["target_weight"] - 0.18) < 1e-6, f"target_weight 已改为 0.18(得到 {h['target_weight']})")
    finally:
        _loader.DEFAULT_YAML = orig_path

print()
if errs:
    print(f"❌ 失败 {len(errs)} 项")
    for e in errs:
        print(f"  - {e}")
    sys.exit(1)
print("✅ rebalance_planner 全部用例通过")
