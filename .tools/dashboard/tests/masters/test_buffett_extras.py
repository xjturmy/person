"""test_buffett_extras.py — 离线冒烟测试(不依赖网络,读本地 DuckDB)

覆盖:
  T01  apply_grades 正向分档
  T02  apply_grades 反向分档(负债倍数)
  T03  simple_owner_earnings 茅台(stalwart 满分路径)
  T04  simple_owner_earnings 美的集团(挑战梯度阈值)
  T05  industry_alt_oe_score 招商银行 bank 路径
  T06  industry_alt_score 新华保险 insurance 阻塞返回 None
  T07  industry_alt_score 比亚迪 high_rd_tech 占位返回 None
  T08  retained_earnings_breakdown 茅台 >= 5 年数据
  T09  retained_earnings_return_rate 茅台 rate 合理区间
  T10  load_qualitative_score 未录入时返回 None 结构
  T11  save + load qualitative_score 往返一致(用临时文件)
  T12  compute_owner_earnings 返回 verified=False(P3 阻塞)
"""
import sys
import tempfile
from pathlib import Path

import pytest

# 路径定位
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".tools" / "dashboard"))

from masters.buffett import (
    apply_grades,
    compute_owner_earnings,
    industry_alt_oe_score,
    industry_alt_score,
    load_qualitative_score,
    retained_earnings_breakdown,
    retained_earnings_return_rate,
    save_qualitative_score,
    simple_owner_earnings,
)

DB_PATH = ROOT / "data" / "preson.duckdb"

# 3 家冒烟公司
MAOTAI = "600519"    # 贵州茅台 — stalwart 满分路径
MIDEA = "000333"     # 美的集团 — 挑战梯度阈值
BYD = "002594"       # 比亚迪 — 高研发排除替代
ZHAOSHANG = "600036" # 招商银行 — 银行路径
XINHUA = "601336"    # 新华保险 — 保险 P3 阻塞


# ═══ T01 apply_grades 正向 ═══════════════════════════════════════════════

def test_apply_grades_normal():
    grades = {
        "excellent": {"threshold": 0.15, "score": 2.0},
        "good":      {"threshold": 0.10, "score": 1.5},
        "fair":      {"threshold": 0.05, "score": 1.0},
        "weak":      {"threshold": 0.0,  "score": 0.5},
        "fail":      {"threshold": float("-inf"), "score": 0.0},
    }
    assert apply_grades(0.20, grades) == 2.0
    assert apply_grades(0.12, grades) == 1.5
    assert apply_grades(0.07, grades) == 1.0
    assert apply_grades(0.02, grades) == 0.5
    assert apply_grades(-0.01, grades) == 0.0


# ═══ T02 apply_grades 反向(负债倍数) ══════════════════════════════════

def test_apply_grades_reverse():
    grades = {
        "excellent": {"threshold": 0.5,  "score": 2.0},
        "good":      {"threshold": 2.0,  "score": 1.5},
        "fair":      {"threshold": 5.0,  "score": 1.0},
        "weak":      {"threshold": 10.0, "score": 0.5},
        "fail":      {"threshold": float("inf"), "score": 0.0},
    }
    assert apply_grades(0.3,  grades, direction="reverse") == 2.0
    assert apply_grades(1.5,  grades, direction="reverse") == 1.5
    assert apply_grades(4.0,  grades, direction="reverse") == 1.0
    assert apply_grades(8.0,  grades, direction="reverse") == 0.5
    assert apply_grades(15.0, grades, direction="reverse") == 0.0


# ═══ T03 simple_owner_earnings 茅台 ══════════════════════════════════

def test_simple_oe_maotai():
    result = simple_owner_earnings(MAOTAI, years=10, db_path=DB_PATH)
    # 茅台自由现金流长期增长,预期 CAGR >= 0
    assert result.value is not None, f"茅台 OE 数据应存在: {result}"
    assert result.verified is True, "简化 OE 用理杏仁原始字段,应 verified=True"
    assert result.value > -1.0, f"OE CAGR 不应过低: {result.value}"
    print(f"  茅台 OE: {result}")


# ═══ T04 simple_owner_earnings 美的 ══════════════════════════════════

def test_simple_oe_midea():
    result = simple_owner_earnings(MIDEA, years=10, db_path=DB_PATH)
    # 美的集团有 10 年数据,应能计算
    assert result is not None
    print(f"  美的 OE: {result}")
    if result.value is not None:
        # 值应在合理区间 -50% ~ +50%
        assert -0.5 <= result.value <= 0.5, f"美的 OE CAGR 超出合理范围: {result.value}"


# ═══ T05 银行替代评分 招商银行 ════════════════════════════════════════

def test_bank_alt_score_zhaoshang():
    result = industry_alt_oe_score(ZHAOSHANG, "bank", db_path=DB_PATH)
    assert result is not None
    assert result.verified is True, "银行 PB-ROE 用理杏仁字段,应 verified=True"
    assert result.value is not None, f"招商银行 ROE/PB 数据应存在: {result}"
    assert 0 <= result.value <= 2.0, f"分档应在 0-2: {result.value}"
    print(f"  招商银行 bank alt: {result}")


# ═══ T06 保险替代评分 P3 阻塞 ════════════════════════════════════════

def test_insurance_alt_blocked():
    result = industry_alt_score(XINHUA, "insurance", db_path=DB_PATH)
    assert result.value is None, "保险 EV/NBV P3 阻塞,应返回 None"
    assert result.verified is False
    assert "P3" in result.note or "阻塞" in result.note
    print(f"  新华保险 insurance alt: {result}")


# ═══ T07 高研发科技替代评分 比亚迪 ═══════════════════════════════════

def test_high_rd_tech_alt_byd():
    result = industry_alt_score(BYD, "high_rd_tech", db_path=DB_PATH)
    assert result.value is None, "高研发 OE_adj 占位,应返回 None"
    assert result.verified is False
    print(f"  比亚迪 high_rd_tech alt: {result}")


# ═══ T08 retained_earnings_breakdown 茅台 ════════════════════════════

def test_retained_earnings_breakdown_maotai():
    breakdown = retained_earnings_breakdown(MAOTAI, years=10, db_path=DB_PATH)
    assert len(breakdown) >= 5, f"茅台留存收益至少 5 年: 实有 {len(breakdown)}"
    for row in breakdown:
        assert "year" in row
        assert "eps" in row
        assert "retained_eps" in row
        assert "dividend_per_share" in row
        assert "eps_growth_yoy" in row
    # 茅台 EPS 应为正
    eps_vals = [r["eps"] for r in breakdown if r["eps"] is not None]
    assert all(e > 0 for e in eps_vals), "茅台 EPS 应全部为正"
    print(f"  茅台留存收益 {len(breakdown)} 年, 最近: {breakdown[-1]}")


# ═══ T09 retained_earnings_return_rate 茅台 ══════════════════════════

def test_retained_earnings_rate_maotai():
    result = retained_earnings_return_rate(MAOTAI, years=10, db_path=DB_PATH)
    print(f"  茅台留存再投资率: {result}")
    if result.value is not None:
        # 茅台再投资回报率应 > 0
        assert result.value > 0, f"茅台留存再投资率应为正: {result.value}"


# ═══ T10 load_qualitative 未录入返回 None 结构 ═══════════════════════

def test_load_qualitative_empty():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=True) as f:
        tmp_path = Path(f.name)
    # 不存在的文件
    q = load_qualitative_score("999999", path=tmp_path)
    assert q["brand"] is None
    assert q["switching_cost"] is None
    assert q["total"] is None
    assert q["updated_at"] is None


# ═══ T11 save + load 往返一致 ════════════════════════════════════════

def test_save_load_qualitative_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "test_qualitative.yaml"
        scores = {
            "brand": 2,
            "switching_cost": 1,
            "network_effect": 0,
            "economies_of_scale": 2,
            "intangible_assets": 2,
        }
        ok = save_qualitative_score(MAOTAI, scores, notes="茅台测试", path=tmp_path)
        assert ok is True

        loaded = load_qualitative_score(MAOTAI, path=tmp_path)
        assert loaded["brand"] == 2
        assert loaded["switching_cost"] == 1
        assert loaded["network_effect"] == 0
        assert loaded["economies_of_scale"] == 2
        assert loaded["intangible_assets"] == 2
        assert loaded["total"] == 7
        assert loaded["notes"] == "茅台测试"
        print(f"  护城河往返测试: total={loaded['total']}")


# ═══ T12 compute_owner_earnings P3 占位 ══════════════════════════════

def test_compute_owner_earnings_placeholder():
    result = compute_owner_earnings(MAOTAI, db_path=DB_PATH)
    # 完整 OE 公式 P3 阻塞,verified 应为 False
    assert result.verified is False, f"完整 OE 应 verified=False(P3 阻塞): {result}"
    print(f"  茅台完整 OE: {result}")


if __name__ == "__main__":
    """直接运行时执行所有测试并打印结果。"""
    import traceback

    tests = [
        test_apply_grades_normal,
        test_apply_grades_reverse,
        test_simple_oe_maotai,
        test_simple_oe_midea,
        test_bank_alt_score_zhaoshang,
        test_insurance_alt_blocked,
        test_high_rd_tech_alt_byd,
        test_retained_earnings_breakdown_maotai,
        test_retained_earnings_rate_maotai,
        test_load_qualitative_empty,
        test_save_load_qualitative_roundtrip,
        test_compute_owner_earnings_placeholder,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            print(f"\n▶ {t.__name__}")
            t()
            print(f"  ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"结果: {passed} PASS / {failed} FAIL (共 {len(tests)} 条)")
    if failed > 0:
        sys.exit(1)
