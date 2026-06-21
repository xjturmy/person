"""测试 industry_cycle_engine.py(任务包 04 / E2)。

运行:
    cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate
    pytest .tools/dashboard/test_industry_cycle_engine.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 industry_cycle_engine 可被 import(同目录,绕过 tools.dashboard 包导入)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import pytest  # noqa: E402

from industry.cycle import (  # noqa: E402
    IndustryCycle,
    PHASE_CN,
    RULE_TABLE,
    diagnose,
)


VALID_PHASES = {"rising", "topping", "falling", "bottoming", "sideways"}

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


# ─── 1. 接口/类型 ──────────────────────────────────────────────────────


def test_diagnose_returns_dataclass():
    r = diagnose("白酒")
    assert isinstance(r, IndustryCycle)
    assert r.phase in VALID_PHASES
    assert 0.0 <= r.confidence <= 1.0
    assert r.phase_cn in PHASE_CN.values()
    assert isinstance(r.rationale, str) and len(r.rationale) > 0
    assert isinstance(r.signals, dict)


def test_diagnose_unknown_industry_low_confidence():
    """不存在的行业:meta 缺失,无法读 etf/leader → 信号大概率全无 → 低 confidence。"""
    r = diagnose("不存在的虚构行业XYZ")
    assert r.phase in VALID_PHASES
    # 全无信号时 phase 必须是 sideways,confidence 0.1
    if not r.signals:
        assert r.phase == "sideways"
        assert r.confidence <= 0.2
    else:
        # 也允许部分信号(估值引擎自选 fallback);至少不会高 confidence
        assert r.confidence < 0.7


def test_diagnose_empty_string():
    r = diagnose("")
    assert isinstance(r, IndustryCycle)
    assert r.phase == "sideways"
    assert r.confidence <= 0.2


def test_diagnose_none_safe():
    """None 也不应抛错。"""
    r = diagnose(None)  # type: ignore[arg-type]
    assert isinstance(r, IndustryCycle)
    assert r.phase == "sideways"


# ─── 2. RULE_TABLE 完备性 ──────────────────────────────────────────────


def test_rule_table_complete():
    """9 个组合(估值×1y 趋势)都必须有映射。"""
    for v in ("high", "mid", "low"):
        for t in ("up", "flat", "down"):
            assert (v, t) in RULE_TABLE
            assert RULE_TABLE[(v, t)] in VALID_PHASES


def test_rule_table_high_pct_implies_topping_or_falling():
    """高估值不应映射到 rising/bottoming。"""
    for t in ("up", "flat", "down"):
        assert RULE_TABLE[("high", t)] in ("topping", "falling")


def test_rule_table_low_pct_implies_rising_or_bottoming():
    """低估值不应映射到 topping/falling。"""
    for t in ("up", "flat", "down"):
        assert RULE_TABLE[("low", t)] in ("rising", "bottoming")


def test_phase_cn_covers_all_phases():
    for phase in VALID_PHASES:
        assert phase in PHASE_CN
        assert isinstance(PHASE_CN[phase], str) and PHASE_CN[phase]


# ─── 3. 8 重点行业实测 ────────────────────────────────────────────────


@pytest.mark.parametrize("industry", FOCUS_INDUSTRIES)
def test_diagnose_focus_industries_no_crash(industry):
    """8 重点行业 diagnose 不抛错,phase 在 5 类内。"""
    r = diagnose(industry)
    assert isinstance(r, IndustryCycle)
    assert r.phase in VALID_PHASES
    assert 0.0 <= r.confidence <= 1.0
    assert r.industry == industry
    # rationale 必含 phase_cn
    assert r.phase_cn in r.rationale


def test_baijiu_kondratieff_position_loaded():
    """白酒应从 industry_master.yaml 读到康波定位(萧条期防御核心)。"""
    r = diagnose("白酒")
    # 防御 / 萧条 任一关键字存在即可
    assert r.kondratieff_position
    assert ("防御" in r.kondratieff_position) or ("萧条" in r.kondratieff_position)
    assert r.cycle_type in ("成长", "价值", "防御", "周期", "未知")
    # 白酒明确是防御
    assert r.cycle_type == "防御"


def test_battery_cycle_type():
    """电池在 yaml 里是 fast_grower / 成长。"""
    r = diagnose("电池")
    assert r.cycle_type == "成长"


def test_bank_cycle_type():
    """股份制银行是 价值。"""
    r = diagnose("股份制银行")
    assert r.cycle_type == "价值"


# ─── 4. signals dict / rationale 健全性 ───────────────────────────────


def test_signals_dict_keys_in_whitelist():
    """signals 只能含三个白名单 key。"""
    whitelist = {"valuation_pct", "1y_return", "roe_trend"}
    for industry in FOCUS_INDUSTRIES:
        r = diagnose(industry)
        for k in r.signals:
            assert k in whitelist, f"{industry} signals 含意外 key: {k}"


def test_rationale_has_arrow_and_phase():
    """rationale 模板:'... → 见顶(置信 0.6)' 格式。"""
    r = diagnose("白酒")
    assert "→" in r.rationale
    assert "置信" in r.rationale


def test_confidence_bounded():
    for industry in FOCUS_INDUSTRIES + ["不存在的虚构行业XYZ", ""]:
        r = diagnose(industry)
        assert 0.0 <= r.confidence <= 1.0
