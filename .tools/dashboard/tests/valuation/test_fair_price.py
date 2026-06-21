"""fair_price.py 离线 pytest — 覆盖 5 档 verdict 边界 + portfolio 加载 + 4 公司实测。"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

import valuation.fair_price as fp


# ─── Verdict 5 档边界 ────────────────────────────────────────────────
@pytest.mark.parametrize("current,expected_code", [
    (100.0,  "extreme_high"),    # 100 / 50 = 2.0 → > 1.33 → 极度高估
    (66.6,   "extreme_high"),    # > 50 × 1.33 → 极度高估
    (66.5,   "high"),             # = 50 × 1.33 → ≤ 1.33 命中 high
    (57.0,   "fair"),             # < 50 × 1.15 → fair(避开浮点临界)
    (58.0,   "high"),             # > 50 × 1.15 → high
    (50.0,   "fair"),             # = Graham → 合理
    (43.0,   "fair"),             # > 50 × 0.85 → fair
    (42.0,   "low"),              # < 50 × 0.85 → low
    (34.0,   "low"),              # > 50 × 0.67 → low
    (33.4,   "extreme_low"),      # < 50 × 0.67 → 极度低估
    (20.0,   "extreme_low"),
])
def test_verdict_boundaries(current, expected_code):
    code, _ = fp._classify_verdict(current, 50.0)
    assert code == expected_code, f"current={current}, graham=50 → {code} (expected {expected_code})"


# ─── portfolio.yaml 加载 ─────────────────────────────────────────────
def test_load_portfolio_returns_15_companies():
    portfolio = fp.load_portfolio()
    assert len(portfolio) == 15, f"expected 15 positions, got {len(portfolio)}"


def test_portfolio_entry_fields_complete():
    portfolio = fp.load_portfolio()
    entry = portfolio["600519"]
    assert entry.ticker == "600519"
    assert entry.name == "贵州茅台"
    assert entry.school == "价值"
    assert len(entry.rationale) > 0
    assert len(entry.criteria_met) >= 3
    assert len(entry.review_triggers) >= 2


def test_is_in_portfolio_known_and_unknown():
    assert fp.is_in_portfolio("600519") is True
    assert fp.is_in_portfolio("999999") is False


# ─── compute_fair_range — 4 公司实测 ────────────────────────────────
def test_compute_moutai_verified():
    """贵州茅台:Graham 适用,verdict 必出。"""
    r = fp.compute_fair_range("600519", "贵州茅台")
    assert r.verified is True
    assert r.graham_number is not None and r.graham_number > 0
    assert r.low is not None and r.high is not None
    assert r.low < r.high
    assert r.current_price is not None and r.current_price > 0
    # 茅台真实股价应在 ¥800-¥2000 区间(数据库现状)
    assert 800 < r.current_price < 2200
    # PE × PB 远超 22.5,应判极度高估或高估
    assert r.verdict_code in ("high", "extreme_high")


def test_compute_zhaohang_extreme_low():
    """招商银行:Graham 数学上 PE×PB 极小,verdict 必为极度低估。"""
    r = fp.compute_fair_range("600036", "招商银行")
    assert r.verified is True
    assert r.verdict_code == "extreme_low"
    # 招行真实股价应在 ¥25-¥60
    assert 25 < r.current_price < 60


def test_compute_meidi_intermediate():
    """美的:Graham 应判高估区(PE×PB > 22.5 但不极端)。"""
    r = fp.compute_fair_range("000333", "美的集团")
    assert r.verified is True
    assert r.verdict_code in ("high", "extreme_high")
    assert 50 < r.current_price < 150


def test_compute_mixue_hk_not_applicable():
    """蜜雪集团 02097 港股:市值缺失,降级 ⚪。"""
    r = fp.compute_fair_range("02097", "蜜雪集团")
    assert r.verified is False
    assert r.verdict_code == "na"
    assert r.skip_reason is not None
    assert r.graham_number is None
    assert r.low is None


# ─── 格式化辅助 ─────────────────────────────────────────────────────
def test_format_price_with_value():
    assert fp.format_price(1234.5678) == "¥1,234.57"
    assert fp.format_price(1000.0, decimals=0) == "¥1,000"


def test_format_price_none():
    assert fp.format_price(None) == "—"


def test_verdict_color_known_codes():
    for code in ["extreme_low", "low", "fair", "high", "extreme_high", "na"]:
        bg, txt = fp.verdict_color(code)
        assert bg.startswith("#") and txt.startswith("#")


def test_verdict_color_unknown_defaults_to_na():
    bg_na, _ = fp.verdict_color("na")
    bg_unknown, _ = fp.verdict_color("nonsense")
    assert bg_unknown == bg_na


# ─── Graham Number 数学正确性 ───────────────────────────────────────
def test_graham_number_formula_consistency():
    """验证 Graham = current × √(22.5/(PE×PB)) 数学公式。

    茅台:PE≈21,PB≈6.4,当前价 ≈¥1,375。
    Graham 应 ≈ 1375 × √(22.5/(21×6.4)) ≈ 1375 × √(0.167) ≈ 1375 × 0.409 ≈ 562。
    """
    r = fp.compute_fair_range("600519", "贵州茅台")
    if r.verified:
        expected = r.current_price * math.sqrt(fp.GRAHAM_RATIO / (r.pe_ttm * r.pb))
        assert abs(r.graham_number - expected) < 0.01
