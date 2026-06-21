"""持仓跟踪指引 — 段 2「持仓跟踪与决策」核心计算。

输入:
    row  : HoldingRow(来自 portfolio.holdings_view)
    snap : HoldingsSnapshot
    fair : FairPriceRange(来自 dashboard.valuation.fair_price.compute_fair_range)

输出:HoldingGuide — 4 卡片(长期买入/金字塔/卖出/短期)所需全部字段 + 行动摘要 md。

按流派差异化:
    价值 → graham      (Graham Number 五档安全边际)
    成长 → lynch       (PEG/增速口径,数据缺失时退回 Graham + verified=False)
    周期 → buffett     (护城河 + PE 分位减仓)
    防御 → buffett     (同 buffett 规则)
    ""   → graham      (兜底默认)

本模块纯计算,**不 import streamlit**,便于离线测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ─── 流派映射 ──────────────────────────────────────────────────────
SCHOOL_TO_RULE: dict[str, str] = {
    "价值": "graham",
    "成长": "lynch",
    "周期": "buffett",
    "防御": "buffett",
    "": "graham",
}

SCHOOL_LABEL: dict[str, str] = {
    "graham": "Graham 价值投资",
    "lynch": "彼得林奇成长",
    "buffett": "巴菲特护城河",
}


# ─── 数据结构 ──────────────────────────────────────────────────────
@dataclass
class HoldingGuide:
    ticker: str
    name: str
    rule: str                       # "graham" / "lynch" / "buffett"
    school_label: str
    # 长期买入指标
    fair_price: float | None
    buy_line: float | None
    current_price: float | None
    gap_to_low_pct: float | None    # (current-buy_line)/buy_line × 100
    verdict_label: str
    # 买入金字塔:[(档位名, 价位, 仓位占比, 是否触发)]
    pyramid: list[tuple[str, float, float, bool]] = field(default_factory=list)
    # 卖出
    take_profit: float | None = None
    stop_loss_rule: str = ""
    rebalance_rule: str = ""
    # 短期
    pe_pct: float | None = None
    overheat_threshold: float = 0.85
    short_term_action: str = "持有观望"
    # 行动摘要 markdown
    summary_md: str = ""
    # 降级标记
    verified: bool = True
    notes: list[str] = field(default_factory=list)


# ─── 短期建议 ──────────────────────────────────────────────────────
def _short_term_action(pe_pct: float | None,
                       overheat: float = 0.85,
                       cheap: float = 0.30) -> str:
    if pe_pct is None:
        return "持有观望"
    if pe_pct >= overheat:
        return "评估减仓"
    if pe_pct <= cheap:
        return "考虑加仓"
    return "持有观望"


# ─── 行动摘要 ──────────────────────────────────────────────────────
def _summary_md(row, guide: "HoldingGuide") -> str:
    lines: list[str] = []
    # 当前档位
    lines.append(f"- **当前档位**:{guide.verdict_label}")
    # 距低估
    if guide.gap_to_low_pct is not None:
        sign = "+" if guide.gap_to_low_pct >= 0 else ""
        lines.append(f"- **距买入线**:{sign}{guide.gap_to_low_pct:.1f}%(当前价相对低估线)")
    # PE 分位
    if guide.pe_pct is not None:
        lines.append(f"- **PE 分位**:{guide.pe_pct*100:.1f}%(过热阈值 {guide.overheat_threshold*100:.0f}%)")
    # F-Score
    if row.fscore is not None:
        lines.append(f"- **F-Score**:{row.fscore} / 9")
    # 建议
    lines.append(f"- **短期建议**:{guide.short_term_action}")
    if guide.notes:
        lines.append(f"- _数据降级_:{' / '.join(guide.notes)}")
    return "\n".join(lines)


# ─── graham 规则 ────────────────────────────────────────────────────
def _apply_graham(guide: HoldingGuide, fair) -> None:
    gn = fair.graham_number
    guide.fair_price = gn
    guide.buy_line = gn * 0.85
    guide.current_price = fair.current_price
    if guide.buy_line and guide.current_price is not None:
        guide.gap_to_low_pct = (guide.current_price - guide.buy_line) / guide.buy_line * 100
    guide.verdict_label = fair.verdict_label
    cp = guide.current_price if guide.current_price is not None else float("inf")
    p1 = guide.buy_line
    p2 = gn * 0.85 * 0.9      # buy_line × 0.9
    p3 = gn * 0.85 * 0.8      # buy_line × 0.8
    guide.pyramid = [
        ("一档", p1, 0.30, cp <= p1),
        ("二档", p2, 0.40, cp <= p2),
        ("三档", p3, 0.30, cp <= p3),
    ]
    guide.take_profit = gn * 1.5
    guide.stop_loss_rule = "F-Score < 4"
    guide.rebalance_rule = "偏离目标权重 > 5% 触发再平衡"


# ─── lynch 规则 ─────────────────────────────────────────────────────
def _apply_lynch(guide: HoldingGuide, fair) -> None:
    # 林奇严格口径需要 EPS 增长率 / PEG;数据未到位时回退 Graham 占位。
    gn = fair.graham_number
    guide.fair_price = gn
    guide.buy_line = gn * 0.9
    guide.current_price = fair.current_price
    if guide.buy_line and guide.current_price is not None:
        guide.gap_to_low_pct = (guide.current_price - guide.buy_line) / guide.buy_line * 100
    guide.verdict_label = fair.verdict_label
    cp = guide.current_price if guide.current_price is not None else float("inf")
    p1 = guide.buy_line
    p2 = gn * 0.9 * 0.92
    p3 = gn * 0.9 * 0.85
    guide.pyramid = [
        ("一档", p1, 0.30, cp <= p1),
        ("二档", p2, 0.40, cp <= p2),
        ("三档", p3, 0.30, cp <= p3),
    ]
    guide.take_profit = gn * 1.6
    guide.stop_loss_rule = "PEG > 2 或营收增速降至 10% 以下"
    guide.rebalance_rule = "成长股偏离 > 5% 触发再平衡"
    # 数据降级标记
    guide.verified = False
    guide.notes.append("林奇口径增长率数据待补,暂用 Graham 替代")


# ─── buffett 规则 ───────────────────────────────────────────────────
def _apply_buffett(guide: HoldingGuide, fair) -> None:
    gn = fair.graham_number
    guide.fair_price = gn * 1.1     # 巴菲特愿为护城河付溢价
    guide.buy_line = guide.fair_price * 0.9
    guide.current_price = fair.current_price
    if guide.buy_line and guide.current_price is not None:
        guide.gap_to_low_pct = (guide.current_price - guide.buy_line) / guide.buy_line * 100
    guide.verdict_label = fair.verdict_label
    cp = guide.current_price if guide.current_price is not None else float("inf")
    p1 = guide.buy_line
    p2 = guide.buy_line * 0.9
    guide.pyramid = [
        ("一档", p1, 0.50, cp <= p1),
        ("二档", p2, 0.50, cp <= p2),
    ]
    guide.take_profit = guide.fair_price * 1.4
    guide.stop_loss_rule = "PE 分位 > 85% 触发减仓 / 护城河受损则清仓"
    guide.rebalance_rule = "偏离目标权重 > 5% 触发再平衡"


# ─── 数据缺失降级 ───────────────────────────────────────────────────
def _apply_no_fair(guide: HoldingGuide) -> None:
    guide.fair_price = None
    guide.buy_line = None
    guide.current_price = None
    guide.gap_to_low_pct = None
    guide.verdict_label = "⚪ 不适用"
    guide.pyramid = []
    guide.take_profit = None
    if not guide.stop_loss_rule:
        guide.stop_loss_rule = "(合理价缺失,暂以人工判断为准)"
    if not guide.rebalance_rule:
        guide.rebalance_rule = "偏离目标权重 > 5% 触发再平衡"
    guide.verified = False
    guide.notes.append("合理价数据缺失")


# ─── 主入口 ─────────────────────────────────────────────────────────
def compute_holding_guide(row: Any, snap: Any, fair: Any) -> HoldingGuide:
    """根据持仓行 / 快照 / 合理价区间,产出 HoldingGuide。

    rule 选择:row.school(中文)→ SCHOOL_TO_RULE
    """
    rule = SCHOOL_TO_RULE.get(row.school or "", "graham")
    school_label = SCHOOL_LABEL[rule]

    guide = HoldingGuide(
        ticker=row.ticker,
        name=row.name,
        rule=rule,
        school_label=school_label,
        fair_price=None,
        buy_line=None,
        current_price=None,
        gap_to_low_pct=None,
        verdict_label="⚪ 不适用",
        pe_pct=row.pe_pct,
    )

    # 优先用真实股价数据;fair 缺失则降级
    fair_ok = fair is not None and getattr(fair, "verified", False) and getattr(fair, "graham_number", None)

    if fair_ok:
        if rule == "graham":
            _apply_graham(guide, fair)
        elif rule == "lynch":
            _apply_lynch(guide, fair)
        elif rule == "buffett":
            _apply_buffett(guide, fair)
        else:
            _apply_graham(guide, fair)
    else:
        _apply_no_fair(guide)

    # 短期建议
    guide.short_term_action = _short_term_action(row.pe_pct, guide.overheat_threshold)

    # 行动摘要
    guide.summary_md = _summary_md(row, guide)

    return guide


__all__ = [
    "HoldingGuide",
    "SCHOOL_TO_RULE",
    "SCHOOL_LABEL",
    "compute_holding_guide",
]
