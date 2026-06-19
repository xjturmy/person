"""test_buffett_classifier.py — Buffett 分类自适应评分单元测试。

覆盖:
  - classify():三类分支(compounder / cyclical_value / quality_growth)+ 数据缺失兜底
  - 5 个 _score_*:边界值 + 数据缺失分支
  - overall_buffett:加权求和 + 缺失维度补 50

不依赖 DuckDB — 全部用 dict 直喂 classify / compute_buffett_dims。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DASH = HERE.parent.parent  # .tools/dashboard
if str(DASH) not in sys.path:
    sys.path.insert(0, str(DASH))

from masters.buffett.classifier import (  # noqa: E402
    classify, compute_buffett_dims, overall_buffett,
)


# ─── classify: 三类分支 ─────────────────────────────────────────────

def test_classify_compounder():
    """ROE 长期稳定 + CAGR 温和 → 复利稳健型"""
    m = {"rev_cagr_5y": 0.10, "roe": 0.20, "roe_10y_mean": 0.22}
    r = classify(m)
    assert r.cls_id == "compounder"
    assert r.confidence >= 0.80
    assert "复利稳健" in r.cls_name


def test_classify_quality_growth():
    """CAGR ≥ 20% + FCF 正向 → 高质量成长型"""
    m = {"rev_cagr_5y": 0.35, "roe": 0.18, "fcf_cagr_10y": 0.12, "cfo_to_ni": 0.9}
    r = classify(m)
    assert r.cls_id == "quality_growth"
    assert r.confidence >= 0.80


def test_classify_quality_growth_fcf_pending():
    """高增长但 FCF 未转正 → quality_growth 但低信心"""
    m = {"rev_cagr_5y": 0.40, "roe": 0.15, "fcf_cagr_10y": None, "cfo_to_ni": 0.2}
    r = classify(m)
    assert r.cls_id == "quality_growth"
    assert r.confidence < 0.80


def test_classify_cyclical_value():
    """净利率波动大但 ROE 长期为正 → 周期价值型"""
    m = {"rev_cagr_5y": 0.08, "roe": 0.12, "net_margin_5y_cv": 0.45}
    r = classify(m)
    assert r.cls_id == "cyclical_value"


def test_classify_missing_data_fallback():
    """关键字段缺失 → compounder 兜底,低信心"""
    m = {"rev_cagr_5y": None, "roe": None}
    r = classify(m)
    assert r.cls_id == "compounder"
    assert r.confidence <= 0.50


# ─── 5 维评分:边界 + 缺失 ──────────────────────────────────────────

def test_dim_moat_quality_compounder_full():
    """compounder + ROE=18% → 护城河 ≈ 100"""
    m = {"roe": 0.18, "roe_10y_mean": 0.18}
    dims = compute_buffett_dims(m, "compounder")
    moat = next(d for d in dims if d.key == "moat_quality")
    assert moat.score >= 95


def test_dim_moat_quality_cyclical_relaxed():
    """cyclical_value 阈值放宽 — ROE 12% 已满分"""
    m = {"roe_10y_mean": 0.12}
    dims = compute_buffett_dims(m, "cyclical_value")
    moat = next(d for d in dims if d.key == "moat_quality")
    assert moat.score >= 95


def test_dim_moat_quality_missing():
    dims = compute_buffett_dims({}, "compounder")
    moat = next(d for d in dims if d.key == "moat_quality")
    assert moat.score is None
    assert moat.badge == "⚪"


def test_dim_financial_safety_low_debt_full():
    """compounder + 负债率 30% → 财务安全满分(40% 满分线以下)"""
    m = {"debt_ratio": 0.30}
    dims = compute_buffett_dims(m, "compounder")
    safety = next(d for d in dims if d.key == "financial_safety")
    assert safety.score >= 95


def test_dim_financial_safety_high_debt_zero():
    """负债率 70% → 0 分"""
    m = {"debt_ratio": 0.70}
    dims = compute_buffett_dims(m, "compounder")
    safety = next(d for d in dims if d.key == "financial_safety")
    assert safety.score <= 5


def test_dim_valuation_low_percentile_high_score():
    """PE 10y 分位 10% → 高分(≥85)"""
    m = {"pe_pct_10y": 0.10, "pe_ttm": 12, "pb": 1.2}
    dims = compute_buffett_dims(m, "compounder")
    val = next(d for d in dims if d.key == "valuation")
    assert val.score >= 85


def test_dim_valuation_high_percentile_low_score():
    """PE 10y 分位 95% → 低分(<30)"""
    m = {"pe_pct_10y": 0.95, "pe_ttm": 60, "pb": 8}
    dims = compute_buffett_dims(m, "compounder")
    val = next(d for d in dims if d.key == "valuation")
    assert val.score < 30


# ─── overall_buffett:加权 + 缺失补 50 ──────────────────────────────

def test_overall_all_full():
    """5 维全 100 → 综合 100"""
    m = {
        "roe_10y_mean": 0.25, "roe": 0.25,
        "fcf_cagr_10y": 0.15,
        "cfo_to_ni": 1.2,
        "debt_ratio": 0.20,
        "pe_pct_10y": 0.10, "pe_ttm": 12, "pb": 1.0,
    }
    dims = compute_buffett_dims(m, "compounder")
    overall, badge = overall_buffett(dims)
    assert overall >= 95
    assert badge == "🟢"


def test_overall_missing_neutral_50():
    """全维度缺失 → 综合 50(中性补值)"""
    dims = compute_buffett_dims({}, "compounder")
    overall, badge = overall_buffett(dims)
    assert overall == pytest.approx(50.0, abs=0.5)
    assert badge == "🟠"


def test_overall_weights_sum_to_one():
    """5 维权重和 = 1.0"""
    dims = compute_buffett_dims({}, "compounder")
    assert sum(d.weight for d in dims) == pytest.approx(1.0)


# ─── rating threshold 边界 ────────────────────────────────────────

def test_rating_thresholds():
    """75/60/45 三档对应 🟢🟡🟠"""
    from masters.buffett.classifier import _badge
    assert _badge(80) == "🟢"
    assert _badge(75) == "🟢"
    assert _badge(70) == "🟡"
    assert _badge(60) == "🟡"
    assert _badge(50) == "🟠"
    assert _badge(45) == "🟠"
    assert _badge(40) == "🔴"
    assert _badge(None) == "⚪"
