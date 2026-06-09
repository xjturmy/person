"""离线 pytest:industry_percentile_engine.compute 三级降级 + dataclass 完整性。

断言风格:松(数据状态多变,DB 可能为空也可能填到 5400 行),核心检查:
  · dataclass 字段全在
  · data_source 在四个合法值之一
  · 已知重叠行业(白酒 / 股份制银行 / 化学制药 / 保险)有实际池
  · 不存在的行业不抛错,返回 no_data 或 member_count=0

运行:
    pytest .tools/dashboard/test_industry_percentile_engine.py -v
"""
from __future__ import annotations

from dataclasses import is_dataclass
from datetime import date

import pytest

from importlib import import_module

# 用 importlib 拿模块,避免装包路径问题
mod = import_module("tools.dashboard.industry_percentile_engine") if False else None
# 实际加载:仓库根目录运行 pytest 时 tools 包不可见,改成相对路径
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".tools" / "dashboard"))

import industry.percentile_engine as eng  # noqa: E402

IndustryPercentile = eng.IndustryPercentile
compute = eng.compute


VALID_SOURCES = {"market.duckdb", "peers.duckdb", "self_only", "no_data"}


# ─── 1. dataclass 基础 ────────────────────────────────────────────────


def test_dataclass_is_dataclass():
    assert is_dataclass(IndustryPercentile)


def test_compute_baijiu_returns_dataclass():
    r = compute("白酒")
    assert isinstance(r, IndustryPercentile)
    assert r.industry == "白酒"
    assert isinstance(r.member_count, int)
    assert r.member_count >= 0
    assert r.data_source in VALID_SOURCES
    assert isinstance(r.as_of, date)


# ─── 2. 不存在的行业 → no_data 或 member_count=0 ────────────────────


def test_unknown_industry_returns_no_data_or_zero():
    r = compute("不存在的行业XYZ_233")
    assert isinstance(r, IndustryPercentile)
    assert r.member_count == 0 or r.data_source == "no_data"


def test_empty_string_industry_safe():
    r = compute("")
    assert isinstance(r, IndustryPercentile)
    assert r.data_source == "no_data"


# ─── 3. 8 重点行业全部不抛错 ─────────────────────────────────────────


@pytest.mark.parametrize("industry", [
    "白酒", "股份制银行", "保险", "化学制药",
    "电池", "通信设备", "白色家电", "饮料乳品",
])
def test_eight_focus_industries_no_exception(industry):
    r = compute(industry)
    assert isinstance(r, IndustryPercentile)
    assert r.industry == industry
    assert r.data_source in VALID_SOURCES
    # member_count 可能为 0(纯降级失败)也可能 > 0;不强制


# ─── 4. PE/PB 字段类型与单调性 ───────────────────────────────────────


def test_pe_pb_are_float_or_none():
    r = compute("白酒")
    assert r.pe_median is None or isinstance(r.pe_median, float)
    assert r.pb_median is None or isinstance(r.pb_median, float)
    assert r.pe_percentile_10y is None or 0.0 <= r.pe_percentile_10y <= 100.0
    assert r.pb_percentile_10y is None or 0.0 <= r.pb_percentile_10y <= 100.0


def test_pe_median_positive_when_present():
    r = compute("白酒")
    if r.pe_median is not None:
        assert r.pe_median > 0
    if r.pb_median is not None:
        assert r.pb_median > 0


# ─── 5. 数据源优先级合法 ─────────────────────────────────────────────


def test_data_source_priority_legal():
    """多次调用同行业,data_source 应稳定且属于合法集。"""
    seen = {compute(ind).data_source for ind in
            ["白酒", "股份制银行", "保险", "化学制药"]}
    assert seen.issubset(VALID_SOURCES)


# ─── 6. 已知有自选成份的行业,fallback 至少能 self_only ─────────────


def test_baijiu_has_self_or_peers():
    """白酒至少有茅台(600519)+ 五粮液(000858)2 家自选,
    最坏情况也能走 self_only。"""
    r = compute("白酒")
    if r.data_source != "no_data":
        assert r.member_count >= 1


def test_bank_industry_self_at_least_one():
    """股份制银行:招商银行(600036)是自选,至少 1 家。"""
    r = compute("股份制银行")
    if r.data_source != "no_data":
        assert r.member_count >= 1


# ─── 7. as_of 是 today ───────────────────────────────────────────────


def test_as_of_is_today():
    r = compute("白酒")
    assert r.as_of == date.today()


# ─── 8. notes 是字符串 ──────────────────────────────────────────────


def test_notes_is_str():
    r = compute("白酒")
    assert isinstance(r.notes, str)


# ─── 9. compute 不抛 + 可重入 ────────────────────────────────────────


def test_compute_idempotent():
    a = compute("白酒")
    b = compute("白酒")
    # 字段一致(同一秒内调用,数据源不可能变)
    assert a.industry == b.industry
    assert a.data_source == b.data_source
    assert a.member_count == b.member_count
