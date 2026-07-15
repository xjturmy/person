from __future__ import annotations

from valuation.external_reference import ExternalPriceReference, compare_with_internal


def test_external_aligned_when_diff_within_ten_percent():
    ref = ExternalPriceReference(
        ticker="600000", name="测试", source="Wind", as_of=None,
        target_mid=105.0, target_low=100.0, target_high=110.0,
        coverage=10, current_price=90.0,
    )

    out = compare_with_internal("600000", "测试", 100.0, external=ref)

    assert out.verdict_code == "aligned"


def test_external_lower_flags_internal_optimism():
    ref = ExternalPriceReference(
        ticker="600000", name="测试", source="Wind", as_of=None,
        target_mid=80.0, target_low=75.0, target_high=85.0,
        coverage=10, current_price=90.0,
    )

    out = compare_with_internal("600000", "测试", 100.0, external=ref)

    assert out.verdict_code == "external_lower"
    assert out.diff_pct < -0.10
