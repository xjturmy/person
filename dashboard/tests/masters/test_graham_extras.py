"""graham_extras + graham_router + derived_metrics 集成测试(v2.5 TODO#1)。

测试覆盖:
  - G1: graham_router 4 公司路由正确
  - G2: g7 OR 条件逻辑正确
  - G3: derived_metrics.years_continuous_dividend 函数可调用
  - G4: graham_extras.compute_ncav_status 返回结构完整
  - G6: graham_schloss_view.schloss_quick_score 结构完整

运行:
    cd /Users/gongyong/Desktop/Keyi/preson
    source .venv/bin/activate
    python3 -m pytest .tools/dashboard/test_graham_extras.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
SCORE_DIR = ROOT / ".tools" / "score"
DB_PATH = ROOT / "data" / "preson.duckdb"

for p in [str(DASHBOARD_DIR), str(SCORE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest


# ─── 导入模块 ─────────────────────────────────────────────────────────────

def test_imports_graham_router():
    """G1: graham_router 模块可正常导入。"""
    import masters.graham.router  # noqa: F401


def test_imports_graham_extras():
    """G2/G4: graham_extras 模块可正常导入。"""
    import masters.graham.extras  # noqa: F401


def test_imports_graham_schloss_view():
    """G6: graham_schloss_view 模块可正常导入。"""
    import masters.graham.schloss  # noqa: F401


def test_imports_derived_metrics():
    """G3: derived_metrics 模块可正常导入。"""
    from masters.graham.extras import STEPS_TO_YAML_RULES_MAP  # noqa: F401
    # derived_metrics 在 dashboard dir 下
    import valuation.derived_metrics  # noqa: F401


# ─── G1:路由测试 ──────────────────────────────────────────────────────────

def test_router_bank():
    """G1: 招商银行(600036,股份制银行)→ graham_bank.yaml。"""
    from masters.graham.router import route_by_ticker
    path = route_by_ticker("600036")
    assert "graham_bank" in path, f"期望 graham_bank.yaml,实际: {path}"


def test_router_insurance():
    """G1: 新华保险(601336,保险)→ graham_insurance.yaml。"""
    from masters.graham.router import route_by_ticker
    path = route_by_ticker("601336")
    assert "graham_insurance" in path, f"期望 graham_insurance.yaml,实际: {path}"


def test_router_main_maotai():
    """G1: 贵州茅台(600519,白酒)→ graham.yaml(主)。"""
    from masters.graham.router import route_by_ticker
    path = route_by_ticker("600519")
    assert path.endswith("graham.yaml"), f"期望 graham.yaml,实际: {path}"


def test_router_main_midea():
    """G1: 美的集团(000333,白色家电)→ graham.yaml(主)。"""
    from masters.graham.router import route_by_ticker
    path = route_by_ticker("000333")
    assert path.endswith("graham.yaml"), f"期望 graham.yaml,实际: {path}"


def test_router_unknown_ticker():
    """G1: 未知 ticker → 默认 graham.yaml(不崩溃)。"""
    from masters.graham.router import route_by_ticker
    path = route_by_ticker("999999")
    assert path.endswith("graham.yaml"), f"未知 ticker 应返回主 yaml,实际: {path}"


# ─── G2:g7 OR 条件测试 ────────────────────────────────────────────────────

def test_g7_primary_pass():
    """G2: PB ≤ 1.5 主条件通过。"""
    from masters.graham.extras import parse_g7_or
    r = parse_g7_or(pb=1.2, pe=15.0)
    assert r["pass"] is True
    assert r["primary_pass"] is True
    assert r["score"] == 2


def test_g7_alt_pass():
    """G2: PB > 1.5,但 PE×PB ≤ 22.5 替代条件通过。"""
    from masters.graham.extras import parse_g7_or
    r = parse_g7_or(pb=3.0, pe=7.0)   # PE×PB = 21.0 ≤ 22.5
    assert r["pass"] is True
    assert r["primary_pass"] is False
    assert r["alt_pass"] is True
    assert r["pe_x_pb"] == pytest.approx(21.0, abs=0.1)
    assert r["score"] == 2


def test_g7_both_fail():
    """G2: PB > 1.5 且 PE×PB > 22.5 两条件均不满足。"""
    from masters.graham.extras import parse_g7_or
    r = parse_g7_or(pb=8.0, pe=25.0)  # PE×PB = 200 > 22.5
    assert r["pass"] is False
    assert r["score"] == 0


def test_g7_no_pe():
    """G2: PE 缺失时仅看 PB 主条件。"""
    from masters.graham.extras import parse_g7_or
    r = parse_g7_or(pb=2.0, pe=None)
    assert r["alt_pass"] is None
    assert r["pass"] is False  # PB 2.0 > 1.5 且无 PE


def test_g7_no_pb():
    """G2: PB 缺失时返回不通过(数据缺失)。"""
    from masters.graham.extras import parse_g7_or
    r = parse_g7_or(pb=None, pe=10.0)
    assert r["pass"] is False
    assert r["score"] == 0


# ─── G4:NCAV 结构测试 ─────────────────────────────────────────────────────

def test_ncav_structure():
    """G4: compute_ncav_status 返回必要字段,不崩溃。"""
    from masters.graham.extras import compute_ncav_status
    required_keys = {"ticker", "ncav", "market_cap", "ratio", "status", "score_bonus", "note"}
    if not DB_PATH.exists():
        pytest.skip("preson.duckdb 不存在,跳过 NCAV 测试")
    r = compute_ncav_status("600519")  # 贵州茅台
    assert required_keys.issubset(r.keys()), f"缺字段: {required_keys - r.keys()}"
    assert r["ticker"] == "600519"
    assert r["status"] in {"extreme_undervalue", "undervalue", "fair", "negative_ncav", "no_data"}
    assert r["score_bonus"] in (0, 3)


def test_ncav_no_crash_unknown():
    """G4: 未知 ticker 不崩溃,返回 no_data。"""
    from masters.graham.extras import compute_ncav_status
    if not DB_PATH.exists():
        pytest.skip("preson.duckdb 不存在")
    r = compute_ncav_status("000000")
    assert r["status"] in {"no_data", "negative_ncav", "fair", "undervalue", "extreme_undervalue"}
    assert r["score_bonus"] == 0


# ─── G3:连续派息年数测试 ──────────────────────────────────────────────────

def test_years_continuous_dividend_structure():
    """G3: years_continuous_dividend 返回 DerivedResult,不崩溃。"""
    if not DB_PATH.exists():
        pytest.skip("preson.duckdb 不存在")
    import duckdb
    from valuation.derived_metrics import years_continuous_dividend, DerivedResult
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        r = years_continuous_dividend(con, "600519")  # 贵州茅台
        assert isinstance(r, DerivedResult)
        assert r.value is None or r.value >= 0
        assert isinstance(r.note, str)
    finally:
        con.close()


def test_years_continuous_dividend_four_companies():
    """G3: 4 家公司至少有 1 家连续派息年数非零。"""
    if not DB_PATH.exists():
        pytest.skip("preson.duckdb 不存在")
    import duckdb
    from valuation.derived_metrics import years_continuous_dividend
    con = duckdb.connect(str(DB_PATH), read_only=True)
    results = {}
    try:
        for ticker in ["600519", "000333", "600036", "601336"]:
            r = years_continuous_dividend(con, ticker)
            results[ticker] = r.value
    finally:
        con.close()
    non_zero = [v for v in results.values() if v is not None and v > 0]
    assert len(non_zero) >= 1, f"期望至少 1 家非零派息年数,实际: {results}"


# ─── G6:Schloss 评分结构测试 ──────────────────────────────────────────────

def test_schloss_structure():
    """G6: schloss_quick_score 返回正确结构。"""
    if not DB_PATH.exists():
        pytest.skip("preson.duckdb 不存在")
    from masters.graham.schloss import schloss_quick_score
    r = schloss_quick_score("600519")
    required = {"ticker", "score", "total", "passed", "failed", "na", "pct", "grade", "items"}
    assert required.issubset(r.keys())
    assert r["total"] == 15
    assert 0 <= r["score"] <= 15
    assert isinstance(r["passed"], list)
    assert isinstance(r["failed"], list)
    assert isinstance(r["na"], list)
    assert len(r["passed"]) + len(r["failed"]) + len(r["na"]) == 15
    assert r["grade"] in ("A", "B", "C", "D")


def test_schloss_four_companies():
    """G6: 4 家公司全部可打分,不崩溃。"""
    if not DB_PATH.exists():
        pytest.skip("preson.duckdb 不存在")
    from masters.graham.schloss import schloss_quick_score
    for ticker in ["600036", "600519", "000333", "601336"]:
        r = schloss_quick_score(ticker)
        assert r["ticker"] == ticker
        assert 0 <= r["score"] <= 15, f"{ticker} 分数异常: {r['score']}"


def test_schloss_items_count():
    """G6: SCHLOSS_ITEMS 恰好 15 条。"""
    from masters.graham.schloss import SCHLOSS_ITEMS
    assert len(SCHLOSS_ITEMS) == 15, f"期望 15 条,实际 {len(SCHLOSS_ITEMS)}"


# ─── G5:steps map 结构测试 ────────────────────────────────────────────────

def test_steps_map_structure():
    """G5: STEPS_TO_YAML_RULES_MAP 包含 5 个步骤键。"""
    from masters.graham.extras import STEPS_TO_YAML_RULES_MAP
    assert len(STEPS_TO_YAML_RULES_MAP) >= 5
    for key, val in STEPS_TO_YAML_RULES_MAP.items():
        assert "desc" in val
        assert "yaml_rules" in val
        assert "note" in val


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
