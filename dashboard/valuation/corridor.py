"""仓位走廊:短期热度 × 战略目标 × 当前持仓 → 合理仓位区间 + 操作建议。

读 `.tools/rules/gold_overheat.yaml` 的 `position_corridor` 段,
对每档 verdict 给出 X 的折扣率,加 ±tolerance 形成走廊。

纯函数 — 不依赖 streamlit,可离线测试。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[3]
YAML_PATH = ROOT / ".tools" / "rules" / "gold_overheat.yaml"


@dataclass(frozen=True)
class Corridor:
    """单次评估结果。"""
    verdict_id: str          # add / add_caution / hold / pause_partial / pause
    strategic_pct: float     # X% (战略目标)
    current_pct: float       # Y% (当前持仓)
    discount: float          # 折扣率(0.6 ~ 1.0)
    target_pct: float        # X × discount(走廊中线)
    lower_pct: float         # 中线 - tolerance
    upper_pct: float         # 中线 + tolerance
    tolerance: float         # 容忍带 ±%
    tier_label: str          # "可建满战略目标" 等
    period_weeks: int        # 匀速建仓/减仓周数
    decision: str            # "add" / "hold" / "reduce"
    decision_label: str      # "加仓" / "持有" / "减仓"
    weekly_step_pct: float   # 本周建议变动(正=加,负=减,0=持有)
    gap_pct: float           # current - target(用于诊断)


def load_corridor_config(yaml_path: Path = YAML_PATH) -> dict:
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("position_corridor", {})


def _tier_lookup(verdict_id: str, cfg: dict) -> tuple[float, str]:
    """返回 (discount, label)。未匹配走 add(全绿,1.0)。"""
    for tier in cfg.get("tiers", []):
        if tier.get("verdict_id") == verdict_id:
            return float(tier.get("discount", 1.0)), str(tier.get("label", ""))
    return 1.0, "(未匹配档位,默认全绿)"


def compute_corridor(verdict_id: str,
                     strategic_pct: float,
                     current_pct: float,
                     period_weeks: Optional[int] = None,
                     yaml_path: Path = YAML_PATH) -> Corridor:
    """主入口:给定 verdict + 战略目标 X% + 当前持仓 Y%,返回走廊评估。"""
    cfg = load_corridor_config(yaml_path)
    tolerance = float(cfg.get("tolerance_pct", 2.0))
    pw = int(period_weeks if period_weeks is not None
             else cfg.get("default_period_weeks", 26))
    discount, label = _tier_lookup(verdict_id, cfg)

    target = strategic_pct * discount
    lower = max(0.0, target - tolerance)
    upper = target + tolerance
    gap = current_pct - target

    if current_pct < lower:
        decision = "add"
        decision_label = "加仓"
        # 距离上界(更稳一点),匀速 N 周
        delta = upper - current_pct
        step = delta / max(pw, 1)
    elif current_pct > upper:
        decision = "reduce"
        decision_label = "减仓"
        delta = current_pct - lower  # 减到下界(同样稳一点)
        step = -delta / max(pw, 1)
    else:
        decision = "hold"
        decision_label = "持有"
        step = 0.0

    return Corridor(
        verdict_id=verdict_id,
        strategic_pct=strategic_pct,
        current_pct=current_pct,
        discount=discount,
        target_pct=target,
        lower_pct=lower,
        upper_pct=upper,
        tolerance=tolerance,
        tier_label=label,
        period_weeks=pw,
        decision=decision,
        decision_label=decision_label,
        weekly_step_pct=step,
        gap_pct=gap,
    )


def render_summary(c: Corridor) -> str:
    """单行 markdown 摘要(给 caption 用)。"""
    arrow = "▲" if c.decision == "add" else ("▼" if c.decision == "reduce" else "→")
    return (
        f"{arrow} **{c.decision_label}** · 走廊 {c.lower_pct:.1f}% ~ {c.upper_pct:.1f}% · "
        f"当前 {c.current_pct:.1f}% · 本周建议 {c.weekly_step_pct:+.2f}%"
    )


__all__ = ["Corridor", "compute_corridor", "load_corridor_config", "render_summary"]
