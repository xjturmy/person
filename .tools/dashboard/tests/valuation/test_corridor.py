"""离线测试 position_corridor:5 档折扣 × 三种决策分支。"""
from __future__ import annotations

import pytest

from valuation.corridor import compute_corridor, load_corridor_config, render_summary


# ─── 折扣表 ─────────────────────────────────────────────────────────


def test_yaml_loads_5_tiers():
    cfg = load_corridor_config()
    ids = {t["verdict_id"] for t in cfg["tiers"]}
    assert ids == {"add", "add_caution", "hold", "pause_partial", "pause"}


@pytest.mark.parametrize("verdict_id, expected_discount", [
    ("add", 1.00),
    ("add_caution", 0.95),
    ("hold", 0.85),
    ("pause_partial", 0.70),
    ("pause", 0.60),
])
def test_discount_per_tier(verdict_id, expected_discount):
    c = compute_corridor(verdict_id, strategic_pct=20.0, current_pct=10.0)
    assert c.discount == pytest.approx(expected_discount)
    assert c.target_pct == pytest.approx(20.0 * expected_discount)


# ─── 三种决策分支 ────────────────────────────────────────────────────


def test_decision_add_when_below_corridor():
    # X=20, hold tier → target=17, lower=15, upper=19;Y=10 远低于 → add
    c = compute_corridor("hold", 20.0, 10.0)
    assert c.decision == "add"
    assert c.weekly_step_pct > 0


def test_decision_hold_when_inside_corridor():
    # X=20, hold tier → 走廊 [15, 19];Y=17 居中
    c = compute_corridor("hold", 20.0, 17.0)
    assert c.decision == "hold"
    assert c.weekly_step_pct == 0.0


def test_decision_reduce_when_above_corridor():
    # X=20, pause tier → target=12, upper=14;Y=18 远高 → reduce
    c = compute_corridor("pause", 20.0, 18.0)
    assert c.decision == "reduce"
    assert c.weekly_step_pct < 0


# ─── 边界 ───────────────────────────────────────────────────────────


def test_zero_current_holding_full_pace_add():
    c = compute_corridor("add", 20.0, 0.0, period_weeks=26)
    # 加到 upper=22(20 + 2 tolerance),26 周 → 每周 ~0.85%
    assert c.decision == "add"
    assert c.weekly_step_pct == pytest.approx((20.0 + c.tolerance) / 26)


def test_strategic_zero_no_position_needed():
    c = compute_corridor("pause", 0.0, 5.0)
    # X=0, tier=pause discount=0.6 → target=0, upper=2;Y=5 → reduce
    assert c.decision == "reduce"


def test_summary_arrow_matches_decision():
    add_c = compute_corridor("add", 20.0, 5.0)
    assert "▲" in render_summary(add_c) and "加仓" in render_summary(add_c)

    hold_c = compute_corridor("hold", 20.0, 17.0)
    assert "→" in render_summary(hold_c) and "持有" in render_summary(hold_c)

    reduce_c = compute_corridor("pause", 20.0, 18.0)
    assert "▼" in render_summary(reduce_c) and "减仓" in render_summary(reduce_c)


# ─── 实战案例(对照历史回填数据)──────────────────────────────────────


def test_2024_04_overheat_pause_partial_case():
    """2024-04-21 历史时点是 pause_partial 档(🔴2 + 🟡1)。
    用户假设当时 Y=18%、X=20%、加快减仓 8 周 → 每周减 ~0.75%。"""
    c = compute_corridor("pause_partial", strategic_pct=20.0,
                         current_pct=18.0, period_weeks=8)
    assert c.target_pct == pytest.approx(14.0)
    assert c.decision == "reduce"
    # 8 周降到 12%(下界),每周 -0.75%
    assert c.weekly_step_pct == pytest.approx(-0.75)


def test_default_26w_pace_is_slow_and_steady():
    """yaml 默认 26 周 = 半年匀速,适合战略性建仓/减仓。"""
    c = compute_corridor("pause_partial", strategic_pct=20.0, current_pct=18.0)
    # 默认 26 周,每周 ~0.23%,半年降到 12%
    assert -0.3 < c.weekly_step_pct < -0.2


def test_typical_full_green_situation():
    """🟢 全绿 + 当前低于战略 → 全速建仓节奏。"""
    c = compute_corridor("add", strategic_pct=20.0, current_pct=10.0)
    assert c.target_pct == pytest.approx(20.0)
    assert c.decision == "add"
    assert c.weekly_step_pct > 0
