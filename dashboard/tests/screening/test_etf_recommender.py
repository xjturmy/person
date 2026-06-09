"""测试 .tools/dashboard/etf_recommender.py — v2.5 任务包 05."""

from __future__ import annotations

import sys
from pathlib import Path

# 允许 pytest 直接从仓库根运行
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

from screening.etf_recommender import (  # noqa: E402
    ETFCandidate,
    list_all_recommendations,
    recommend,
)


# ──────────────────────────────────────────────────────────────────
# 基本类型 / 边界
# ──────────────────────────────────────────────────────────────────


def test_recommend_returns_list():
    r = recommend("白酒", top_n=3)
    assert isinstance(r, list)
    if r:
        assert isinstance(r[0], ETFCandidate)


def test_recommend_baijiu_at_least_one():
    r = recommend("白酒", top_n=3)
    assert len(r) >= 1


def test_recommend_unknown_industry_returns_empty():
    r = recommend("不存在XYZ_行业", top_n=3)
    assert r == []


def test_recommend_top_n_is_respected():
    r = recommend("白酒", top_n=2)
    assert len(r) <= 2


def test_recommend_etf_data_or_none():
    r = recommend("白酒", top_n=3)
    assert r, "白酒至少应该有 1 只 ETF"
    for c in r:
        # 字段要么有合理值,要么显式 None
        assert c.last_close is None or c.last_close > 0
        assert c.return_1y is None or -1.0 < c.return_1y < 5.0
        assert c.avg_turnover_60d is None or c.avg_turnover_60d >= 0
        assert 0 <= c.liquidity_score <= 100
        assert c.code and isinstance(c.code, str)
        assert c.theme in ("主题", "龙头", "红利")
        assert c.rationale  # 不应为空


# ──────────────────────────────────────────────────────────────────
# 8 重点行业全覆盖
# ──────────────────────────────────────────────────────────────────


FOCUS_INDUSTRIES = [
    "白酒",
    "股份制银行",
    "保险",
    "化学制药",
    "电池",
    "通信设备",
    "白色家电",
    "饮料乳品",
]


@pytest.mark.parametrize("industry", FOCUS_INDUSTRIES)
def test_recommend_8_focus_industries(industry):
    """8 个聚焦行业每个都至少返回 1 只 ETF 且不抛异常。"""
    r = recommend(industry, top_n=3)
    assert isinstance(r, list)
    assert len(r) >= 1, f"{industry} 应至少有 1 只 ETF"
    assert len(r) <= 3
    for c in r:
        assert isinstance(c, ETFCandidate)
        assert c.code
        # layer 来自 mapping,8 行业都在 mapping 里,layer 应非空
        assert c.layer in ("defensive", "offensive", "auxiliary")


def test_recommend_layer_target_pct_propagated():
    r = recommend("白酒", top_n=3)
    assert r
    # 白酒 mapping 里 layer=defensive, target_pct=[10, 15]
    assert r[0].layer == "defensive"
    assert r[0].target_pct is not None
    assert r[0].target_pct[0] <= r[0].target_pct[1]


def test_recommend_sorted_by_liquidity_or_in_db():
    """排序约束:在库的排在不在库的前面;库内按 liquidity_score 降序。"""
    r = recommend("白酒", top_n=3)
    assert r
    # 在库标志:last_close is not None
    in_db = [c.last_close is not None for c in r]
    # 不应该出现 不在库 之后又出现 在库 的情况
    seen_off = False
    for flag in in_db:
        if not flag:
            seen_off = True
        elif seen_off:
            pytest.fail("不在库的 ETF 不应排在在库的 ETF 前面")
    # 库内 liquidity 单调
    in_db_scores = [c.liquidity_score for c in r if c.last_close is not None]
    for a, b in zip(in_db_scores, in_db_scores[1:]):
        assert a >= b - 1e-6, "库内应按 liquidity_score 降序"


# ──────────────────────────────────────────────────────────────────
# list_all_recommendations
# ──────────────────────────────────────────────────────────────────


def test_list_all_recommendations_returns_dict():
    d = list_all_recommendations()
    assert isinstance(d, dict)
    assert len(d) >= 8, f"应该至少覆盖 8 个聚焦行业,实际 {len(d)}"


def test_list_all_recommendations_covers_focus_8():
    d = list_all_recommendations()
    for ind in FOCUS_INDUSTRIES:
        assert ind in d, f"{ind} 应该出现在 list_all_recommendations 输出中"
        assert isinstance(d[ind], list)


def test_list_all_recommendations_baijiu_has_etfs():
    d = list_all_recommendations()
    assert "白酒" in d
    assert len(d["白酒"]) >= 1


# ──────────────────────────────────────────────────────────────────
# 数据字段一致性 / 边界
# ──────────────────────────────────────────────────────────────────


def test_unknown_industry_top_n_zero_safe():
    """top_n=0 也应安全返回(空 list 或 ≤0 长度)。"""
    r = recommend("白酒", top_n=0)
    assert isinstance(r, list)
    assert len(r) == 0


def test_etf_candidate_fields_present():
    """ETFCandidate 必备字段都存在。"""
    r = recommend("白酒", top_n=1)
    assert r
    c = r[0]
    for attr in (
        "code",
        "name",
        "theme",
        "fund_type",
        "last_close",
        "return_1y",
        "avg_turnover_60d",
        "liquidity_score",
        "rationale",
        "layer",
        "target_pct",
    ):
        assert hasattr(c, attr), f"缺字段 {attr}"
