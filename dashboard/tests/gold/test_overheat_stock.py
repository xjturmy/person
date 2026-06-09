"""金股 ETF 杠杆建议矩阵 · 测试(v2.6 主题 3 板块 H)

全部离线 — 用真实 gold_overheat.yaml 跑,验证 5 路径 + beta_missing + 边界 + 兜底。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gold.overheat import StockEtfAdvice, stock_etf_advice


YAML_PATH = Path(__file__).resolve().parents[3] / "rules" / "gold_overheat.yaml"


# ─── 5 主路径 ────────────────────────────────────────────────────────


def test_add_low_beta_hits():
    """verdict=add + β=1.0(< 阈值 1.1)→ matched_id=add_low_beta + multiplier=1.2"""
    res = stock_etf_advice("add", 1.0, yaml_path=YAML_PATH)
    assert isinstance(res, StockEtfAdvice)
    assert res.matched_id == "add_low_beta"
    assert res.position_multiplier == 1.2
    assert "🟢" in res.advice
    assert res.beta == 1.0
    assert res.verdict_id == "add"


def test_add_high_beta_hits():
    """verdict=add_caution + β=1.5(≥ 阈值 1.1)→ matched_id=add_high_beta + multiplier=1.0"""
    res = stock_etf_advice("add_caution", 1.5, yaml_path=YAML_PATH)
    assert res.matched_id == "add_high_beta"
    assert res.position_multiplier == 1.0
    assert "🟡" in res.advice
    assert "β" in res.advice or "波动放大" in res.advice


def test_hold_any_hits():
    """verdict=hold + β=任意 → matched_id=hold_any"""
    # 低 β
    res_low = stock_etf_advice("hold", 0.9, yaml_path=YAML_PATH)
    assert res_low.matched_id == "hold_any"
    assert res_low.position_multiplier == 1.0
    # 高 β 也走 hold_any(when_verdict=[hold] 无 β 限定)
    res_high = stock_etf_advice("hold", 3.0, yaml_path=YAML_PATH)
    assert res_high.matched_id == "hold_any"
    assert res_high.position_multiplier == 1.0


def test_reduce_high_beta_hits():
    """verdict=pause + β=1.5(≥ 阈值 1.1)→ matched_id=reduce_high_beta + multiplier=0.6"""
    res = stock_etf_advice("pause", 1.5, yaml_path=YAML_PATH)
    assert res.matched_id == "reduce_high_beta"
    assert res.position_multiplier == 0.6
    assert "🔴" in res.advice
    assert "优先减" in res.advice or "高 β" in res.advice


def test_reduce_low_beta_hits():
    """verdict=pause_partial + β=1.0(< 阈值 1.1)→ matched_id=reduce_low_beta + multiplier=0.8"""
    res = stock_etf_advice("pause_partial", 1.0, yaml_path=YAML_PATH)
    assert res.matched_id == "reduce_low_beta"
    assert res.position_multiplier == 0.8
    assert "🔴" in res.advice


# ─── beta_missing 兜底 ──────────────────────────────────────────────


def test_beta_none_returns_beta_missing():
    """β=None → matched_id=beta_missing + advice 含'未就绪'"""
    res = stock_etf_advice("add", None, yaml_path=YAML_PATH)
    assert res.matched_id == "beta_missing"
    assert "未就绪" in res.advice
    assert res.position_multiplier == 1.0
    assert res.beta is None
    assert res.verdict_id == "add"

    # 任何 verdict 下 β=None 都走 beta_missing
    for vid in ("add", "add_caution", "hold", "pause_partial", "pause"):
        r = stock_etf_advice(vid, None, yaml_path=YAML_PATH)
        assert r.matched_id == "beta_missing"


# ─── 边界条件 ───────────────────────────────────────────────────────


def test_boundary_beta_1_1_high():
    """verdict=add + β=1.1(等于阈值)→ matched_id=add_high_beta

    匹配规则:when_beta_lt=1.1 要求 β<1.1,β=1.1 不满足 → 落到 add_high_beta(gte 1.1)
    """
    res = stock_etf_advice("add", 1.1, yaml_path=YAML_PATH)
    assert res.matched_id == "add_high_beta"
    assert res.position_multiplier == 1.0


def test_boundary_beta_1_1_high_reduce():
    """verdict=pause + β=1.1(等于阈值)→ matched_id=reduce_high_beta

    匹配规则:reduce_high_beta when_beta_gte=1.1,β=1.1 满足 → 走 high
    """
    res = stock_etf_advice("pause", 1.1, yaml_path=YAML_PATH)
    assert res.matched_id == "reduce_high_beta"
    assert res.position_multiplier == 0.6


# ─── 额外覆盖(unmatched / dataclass 不可变 / β 回写)─────────────


def test_unmatched_verdict_returns_unmatched():
    """非法 verdict → unmatched 兜底,multiplier=1.0"""
    res = stock_etf_advice("unknown_verdict", 1.5, yaml_path=YAML_PATH)
    assert res.matched_id == "unmatched"
    assert res.position_multiplier == 1.0
    assert res.beta == 1.5


def test_dataclass_is_frozen():
    """StockEtfAdvice frozen — 不可写"""
    res = stock_etf_advice("add", 1.5, yaml_path=YAML_PATH)
    with pytest.raises((AttributeError, Exception)):
        res.matched_id = "tampered"  # type: ignore[misc]


def test_beta_echoed_in_result():
    """β 入参原样回写到结果 — UI 直接读"""
    res = stock_etf_advice("add", 1.85, yaml_path=YAML_PATH)
    assert res.beta == 1.85
    res2 = stock_etf_advice("pause", 2.41, yaml_path=YAML_PATH)
    assert res2.beta == 2.41


# ─── R² 可信度门槛(v2.6 后期补丁)────────────────────────────────────


def test_low_r_squared_returns_beta_low_r2():
    """R²=0.26 < 0.5 → matched_id=beta_low_r2(β 拟合不可信兜底)

    场景:588120 科创黄金股票 ETF 实测 R²=0.258,β=0.43,虽 β 看上去
    像低 β,但拟合极差不应据此调仓。
    """
    res = stock_etf_advice("pause", 0.43, yaml_path=YAML_PATH, r_squared=0.258)
    assert res.matched_id == "beta_low_r2"
    assert res.position_multiplier == 1.0
    assert "不可信" in res.advice or "R²" in res.advice
    assert res.beta == 0.43
    # 高 R² 不被拦截
    res_ok = stock_etf_advice("pause", 0.43, yaml_path=YAML_PATH, r_squared=0.997)
    assert res_ok.matched_id != "beta_low_r2"


def test_r_squared_default_none_backward_compat():
    """不传 r_squared(默认 None)→ 不校验拟合,走原 matrix"""
    res = stock_etf_advice("add", 1.0, yaml_path=YAML_PATH)
    assert res.matched_id == "add_low_beta"
    assert res.position_multiplier == 1.2


def test_beta_none_takes_priority_over_r_squared():
    """β=None 优先走 beta_missing,即使 R² 也低"""
    res = stock_etf_advice("pause", None, yaml_path=YAML_PATH, r_squared=0.1)
    assert res.matched_id == "beta_missing"
