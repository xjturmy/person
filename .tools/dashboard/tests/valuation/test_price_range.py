"""price_range.py 离线 pytest — 覆盖三模型聚合、降级、全缺失场景。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import valuation.price_range as pr_mod
from valuation.fair_price import FairPriceRange
from valuation.price_range import (
    ModelEstimate, compute_next_quarter_range,
)


def _fake_fpr(current=50.0, graham=60.0, pe=20.0, verified=True, skip=None) -> FairPriceRange:
    return FairPriceRange(
        ticker="600000", name="测试", verified=verified, as_of=None,
        graham_number=graham if verified else None,
        low=(graham * 0.85) if verified else None,
        high=(graham * 1.15) if verified else None,
        current_price=current if verified else None,
        verdict_code="fair", verdict_label="🟡 合理", deviation_pct=0.0,
        eps_ttm=2.5, bps=12.0, pe_ttm=pe, pb=4.0,
        market_cap=1e10, shares_outstanding=2e8,
        skip_reason=skip,
    )


# ─── 1. 三模型都有数据 → 区间合理且含当前价 ─────────────────────────
def test_all_three_models_produce_range():
    """三模型都有数据时:floor ≤ mid ≤ ceiling,且 mid 是加权均值。"""
    fpr = _fake_fpr(current=50.0, graham=60.0, pe=20.0)
    peg_est = ModelEstimate("PEG=1", 55.0, 0.0, True, "fake")
    ddm_est = ModelEstimate("Gordon DDM", 70.0, 0.0, True, "fake")
    with patch.object(pr_mod, "compute_fair_range", return_value=fpr), \
         patch.object(pr_mod, "_peg_fair_price", return_value=peg_est), \
         patch.object(pr_mod, "_gordon_fair_price", return_value=ddm_est):
        out = compute_next_quarter_range("600000", name="测试")

    assert out.floor == 55.0      # min(60, 55, 70)
    assert out.ceiling == 70.0    # max
    assert 55.0 <= out.mid <= 70.0
    assert out.verdict_code in ("below_floor", "in_lower")  # current=50 < floor=55
    # 三个模型都被记录
    names = {m.name for m in out.models}
    assert names == {"Graham", "PEG=1", "Gordon DDM"}


# ─── 2. 单模型降级 → 仍能产出区间 + note ─────────────────────────────
def test_one_model_degraded():
    """PEG 缺数据时,仅 Graham + DDM 参与,区间正常输出且 note 记录降级。"""
    fpr = _fake_fpr(current=50.0, graham=60.0)
    peg_est = ModelEstimate("PEG=1", None, 0.0, False, "3y CAGR ≤ 0")
    ddm_est = ModelEstimate("Gordon DDM", 70.0, 0.0, True, "fake")
    with patch.object(pr_mod, "compute_fair_range", return_value=fpr), \
         patch.object(pr_mod, "_peg_fair_price", return_value=peg_est), \
         patch.object(pr_mod, "_gordon_fair_price", return_value=ddm_est):
        out = compute_next_quarter_range("600000", name="测试", lynch_type="stalwart")

    assert out.floor == 60.0
    assert out.ceiling == 70.0
    # 仅两个模型参与加权
    active = [m for m in out.models if m.weight > 0]
    assert len(active) == 2
    assert any("PEG=1 降级" in n for n in out.notes)


# ─── 3. 三模型全缺 → verdict=na ──────────────────────────────────────
def test_all_models_unavailable():
    """Graham 不可得 + PEG/DDM 都缺数据,返回 verdict=na。"""
    fpr = _fake_fpr(verified=False, skip="PE/PB 缺失")
    peg_est = ModelEstimate("PEG=1", None, 0.0, False, "no data")
    ddm_est = ModelEstimate("Gordon DDM", None, 0.0, False, "no dividend")
    with patch.object(pr_mod, "compute_fair_range", return_value=fpr), \
         patch.object(pr_mod, "_peg_fair_price", return_value=peg_est), \
         patch.object(pr_mod, "_gordon_fair_price", return_value=ddm_est):
        out = compute_next_quarter_range("600000", name="测试")

    assert out.verdict_code == "na"
    assert out.floor is None and out.ceiling is None and out.mid is None
    assert len(out.notes) >= 1


# ─── 4. 权重按 lynch_type 调整 ───────────────────────────────────────
def test_weights_by_lynch_type():
    """fast_grower 类型下 PEG 权重应明显高于 Graham。"""
    fpr = _fake_fpr(current=50.0, graham=60.0)
    peg_est = ModelEstimate("PEG=1", 80.0, 0.0, True, "fake")
    ddm_est = ModelEstimate("Gordon DDM", 70.0, 0.0, True, "fake")
    with patch.object(pr_mod, "compute_fair_range", return_value=fpr), \
         patch.object(pr_mod, "_peg_fair_price", return_value=peg_est), \
         patch.object(pr_mod, "_gordon_fair_price", return_value=ddm_est):
        out = compute_next_quarter_range("600000", lynch_type="fast_grower")

    peg_weight = next(m.weight for m in out.models if m.name == "PEG=1")
    graham_weight = next(m.weight for m in out.models if m.name == "Graham")
    assert peg_weight > graham_weight
    # 应靠近 PEG 公允价 80,而不是 Graham 60
    assert out.mid > 70.0
