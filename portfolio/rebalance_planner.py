"""结构化再平衡建议(M4-#5).

把 holdings_view.HoldingsSnapshot 的字符串 alerts 升级为结构化 RebalanceProposal,
带 ticker / 原 target_weight / 建议 target_weight / 理由 / action,
供 UI 渲染 diff 预览 + 一键写入 portfolio.yaml + 自动追加决策日志.

设计取舍:
- 只对**有明确数学解的规则**给具体建议:单仓上限 / 估值高低位
- F-Score 跌破 / 偏离阈值 — 只标记 review_only=True,要求人工二次判断
- 不直接清仓(status: active → exited 风险太大,留给人审)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from holdings_view import HoldingRow, HoldingsSnapshot
from loader import Portfolio, load_portfolio


@dataclass
class RebalanceProposal:
    """单条再平衡建议。target_weight 是浮点小数(0.20 = 20%)."""

    ticker: str
    name: str
    rule: str                  # max_position / valuation_high / valuation_low / fscore / deviation
    action: str                # 加仓 / 减仓 / 观察(对应 decisions ACTIONS)
    old_target: float
    new_target: float
    delta_pp: float            # 百分点变化(new - old)* 100
    rationale: str             # 一句话解释
    review_only: bool = False  # True = 不主动改 target,只提示

    def diff_label(self) -> str:
        """`0.25 → 0.20  (-5.0pp)` 形式."""
        sign = "+" if self.delta_pp >= 0 else ""
        return f"{self.old_target:.0%} → {self.new_target:.0%}  ({sign}{self.delta_pp:.1f}pp)"


def plan(
    snap: HoldingsSnapshot,
    portfolio: Portfolio | None = None,
) -> list[RebalanceProposal]:
    """根据 snap 中的 active 持仓 + portfolio.rebalance 规则,生成结构化建议.

    输入:HoldingsSnapshot(已含 actual_weight / pe_pct / fscore / target_weight)
    输出:list[RebalanceProposal]
    """
    p = portfolio or load_portfolio()
    rules = p.rebalance

    proposals: list[RebalanceProposal] = []
    for r in snap.rows:
        if r.status != "active":
            continue

        # 1) 超单仓上限 → 降到 max_position_weight - 2pp(留缓冲)
        if r.actual_weight > rules.max_position_weight:
            new = max(rules.max_position_weight - 0.02, 0.05)
            proposals.append(RebalanceProposal(
                ticker=r.ticker, name=r.name,
                rule="max_position", action="减仓",
                old_target=r.target_weight, new_target=new,
                delta_pp=(new - r.target_weight) * 100,
                rationale=f"实际权重 {r.actual_weight:.0%} 超单仓上限 {rules.max_position_weight:.0%}",
            ))
            continue

        # 2) 估值高位 → 减 3pp(不少于 5%)
        if r.pe_pct is not None and r.pe_pct > rules.valuation_ceiling_pct:
            new = max(r.target_weight - 0.03, 0.05)
            proposals.append(RebalanceProposal(
                ticker=r.ticker, name=r.name,
                rule="valuation_high", action="减仓",
                old_target=r.target_weight, new_target=new,
                delta_pp=(new - r.target_weight) * 100,
                rationale=f"PE-TTM 分位 {r.pe_pct:.0%} > 上限 {rules.valuation_ceiling_pct:.0%}",
            ))
            continue

        # 3) 估值低位 → 加 2pp(不超 max_position - 1pp)
        if r.pe_pct is not None and r.pe_pct < rules.valuation_floor_pct:
            new = min(r.target_weight + 0.02, rules.max_position_weight - 0.01)
            if new > r.target_weight:
                proposals.append(RebalanceProposal(
                    ticker=r.ticker, name=r.name,
                    rule="valuation_low", action="加仓",
                    old_target=r.target_weight, new_target=new,
                    delta_pp=(new - r.target_weight) * 100,
                    rationale=f"PE-TTM 分位 {r.pe_pct:.0%} < 下限 {rules.valuation_floor_pct:.0%}",
                ))
                continue

        # 4) F-Score 跌破 → review_only(不动 target)
        if r.fscore is not None and r.fscore < rules.score_floor:
            proposals.append(RebalanceProposal(
                ticker=r.ticker, name=r.name,
                rule="fscore", action="观察",
                old_target=r.target_weight, new_target=r.target_weight,
                delta_pp=0.0,
                rationale=f"F-Score {r.fscore} < 阈值 {rules.score_floor},触发清仓评估",
                review_only=True,
            ))
            continue

        # 5) 偏离阈值 → review_only(可能是股价波动,不应改 target)
        if abs(r.deviation) > rules.max_deviation_pct:
            direction = "超配" if r.deviation > 0 else "低配"
            proposals.append(RebalanceProposal(
                ticker=r.ticker, name=r.name,
                rule="deviation", action="观察",
                old_target=r.target_weight, new_target=r.target_weight,
                delta_pp=0.0,
                rationale=f"实际权重{direction} {abs(r.deviation):.1%}(偏离 {rules.max_deviation_pct:.0%}),建议手工再平衡",
                review_only=True,
            ))

    return proposals


def apply_proposals(
    proposals: Iterable[RebalanceProposal],
    decisions_db=None,
    dry_run: bool = False,
) -> dict:
    """把 proposals 落到 portfolio.yaml + 自动追加决策日志.

    只对 review_only=False 的建议改 target_weight;review_only=True 的只写决策日志(action=观察).
    返回 {applied: int, logged: int, backup: str|None}
    """
    from loader import upsert_holdings  # 局部 import 避免循环

    payload: list[dict] = []
    for prop in proposals:
        if prop.review_only:
            continue
        payload.append({
            "ticker": prop.ticker,
            "name": prop.name,
            "target_weight": round(prop.new_target, 4),
        })

    bak: str | None = None
    applied = 0
    if payload and not dry_run:
        bak_path, stats = upsert_holdings(payload)
        applied = stats["updated"]
        bak = bak_path.name if bak_path else None

    logged = 0
    if decisions_db is not None and not dry_run:
        from datetime import date as _date
        for prop in proposals:
            try:
                decisions_db.insert(
                    ticker=prop.ticker,
                    folder="",  # 留空,由 caller 补
                    date=_date.today(),
                    action=prop.action,
                    weight_change=prop.delta_pp,
                    price=0.0,
                    rationale=f"[自动再平衡] {prop.rationale}",
                    thesis_5y="",
                    risks="",
                    tags="auto-rebalance",
                    snapshot={},
                )
                logged += 1
            except Exception:
                pass

    return {"applied": applied, "logged": logged, "backup": bak}
