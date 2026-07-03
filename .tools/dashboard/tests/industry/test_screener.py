"""industry_screener 测试套(任务包 03 / E4)。

10+ 项;离线运行;允许部分行业候选池为空(数据降级容错)。

执行:
    cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate
    pytest .tools/dashboard/test_industry_screener.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

# 让本测试可以从 .tools/dashboard/ 内 import
_DASH = Path(__file__).resolve().parent
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))

from industry.screener import (  # noqa: E402
    IndustryCandidate,
    list_industry_candidates,
    score_company,
    screen_industry,
    screen_all_focus,
    _load_focus_yaml,
    _load_type_map,
    _normalize_to_100,
    _rating_from_score,
    _LYNCH_PRIMARY_TYPES,
    _DIRECT_GRAHAM_PRIMARY,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FOCUS_YAML = PROJECT_ROOT / ".config" / "focus_industries.yaml"
TYPE_MAP_YAML = PROJECT_ROOT / ".tools" / "rules" / "industry_type_map.yaml"


# ─── 1) yaml 结构校验 ────────────────────────────────────────────────────


def test_focus_yaml_valid():
    """focus_industries.yaml 含 ≥ 8 项 + top_n=7 + market_cap_min。"""
    assert FOCUS_YAML.exists(), f"missing {FOCUS_YAML}"
    d = yaml.safe_load(FOCUS_YAML.read_text(encoding="utf-8"))
    assert "focus" in d
    assert len(d["focus"]) >= 8
    assert d.get("top_n") == 7
    assert d.get("market_cap_min") == 5_000_000_000
    # 每项必须有 industry + type
    for item in d["focus"]:
        assert "industry" in item and "type" in item


def test_focus_yaml_industries_align_with_master():
    """focus_industries 的 industry 必须出现在运行时合并主索引。"""
    from tabs.industry._master_loader import load_master_merged
    master_names = set(load_master_merged())
    focus = yaml.safe_load(FOCUS_YAML.read_text(encoding="utf-8"))
    for item in focus["focus"]:
        assert item["industry"] in master_names, \
            f"{item['industry']} 不在运行时行业主索引"


def test_type_map_yaml_valid():
    """6 类型必须齐全 + 每个类型有 primary/secondary/weights。"""
    assert TYPE_MAP_YAML.exists(), f"missing {TYPE_MAP_YAML}"
    d = yaml.safe_load(TYPE_MAP_YAML.read_text(encoding="utf-8"))
    tm = d.get("type_to_scoring", {})
    for t in ("stalwart", "fast_grower", "cyclical", "slow_grower",
              "bank", "insurance"):
        assert t in tm, f"missing type {t}"
        cfg = tm[t]
        assert "primary" in cfg
        assert "weights" in cfg
        # weights 总和应为正(允许不为 1,引擎层会归一化)
        assert sum(cfg["weights"].values()) > 0


def test_bank_insurance_primary_not_lynch():
    """bank/insurance 的 primary 不能用 lynch_classifier(会抛错)。"""
    tm = (_load_type_map() or {}).get("type_to_scoring", {})
    assert tm["bank"]["primary"] != "lynch"
    assert tm["insurance"]["primary"] != "lynch"
    assert tm["bank"]["primary"] == "graham_bank"
    assert tm["insurance"]["primary"] == "graham_insurance"


# ─── 2) 候选池(数据降级)──────────────────────────────────────────────


def test_list_candidates_baijiu_at_least_two_self():
    """白酒至少能拿到茅台 + 五粮液(自选保底)。"""
    cands = list_industry_candidates("白酒")
    tickers = {c["ticker"] for c in cands}
    assert "600519" in tickers, f"missing 茅台,got: {tickers}"
    assert "000858" in tickers, f"missing 五粮液,got: {tickers}"
    # data_source 字段必须存在
    for c in cands:
        assert "data_source" in c
        assert "ticker" in c
        assert "name" in c


def test_list_candidates_bank_has_zhaoshang():
    """股份制银行至少有招商银行(自选)。"""
    cands = list_industry_candidates("股份制银行")
    tickers = {c["ticker"] for c in cands}
    assert "600036" in tickers


def test_list_candidates_unknown_returns_empty():
    """无效行业名 → 空列表。"""
    cands = list_industry_candidates("不存在的行业XYZ")
    assert isinstance(cands, list)
    assert len(cands) == 0


# ─── 3) 单股评分 ────────────────────────────────────────────────────────


def test_score_company_returns_dataclass():
    cand = score_company("600519", "stalwart", name="贵州茅台", is_owned=True)
    assert isinstance(cand, IndustryCandidate)
    assert cand.ticker == "600519"
    assert cand.is_owned is True
    assert cand.primary_master in {"lynch", "graham_bank", "graham_insurance"}
    assert cand.rating  # 非空 emoji 字符串
    assert isinstance(cand.breakdown, dict)


def test_score_company_unknown_type_safe():
    """未知评分类型不应抛错,返回 ⚪ 数据不足。"""
    cand = score_company("600519", "non_existent_type", name="贵州茅台")
    assert cand.score is None
    assert cand.rating == "⚪ 数据不足"


def test_score_company_bank_uses_graham_bank():
    cand = score_company("600036", "bank", name="招商银行", is_owned=True)
    assert cand.primary_master == "graham_bank"


def test_score_company_insurance_uses_graham_insurance():
    cand = score_company("601336", "insurance", name="新华保险", is_owned=True)
    assert cand.primary_master == "graham_insurance"


# ─── 4) 行业 Top N ─────────────────────────────────────────────────────


_REQUIRED_COLS = [
    "rank", "ticker", "name", "score", "rating", "reason",
    "is_owned", "primary_master", "data_source",
]


def test_screen_industry_returns_dataframe():
    df = screen_industry("白酒", "stalwart", top_n=5)
    assert isinstance(df, pd.DataFrame)
    for col in _REQUIRED_COLS:
        assert col in df.columns, f"missing col {col}"
    # 茅台 + 五粮液 至少 2 家
    assert len(df) >= 2
    tickers = set(df["ticker"].astype(str))
    assert "600519" in tickers
    assert "000858" in tickers


def test_screen_industry_rank_is_1_based():
    df = screen_industry("白酒", "stalwart", top_n=5)
    if not df.empty:
        assert df["rank"].iloc[0] == 1
        assert list(df["rank"]) == list(range(1, len(df) + 1))


def test_screen_industry_bank_has_zhaoshang():
    df = screen_industry("股份制银行", "bank", top_n=3)
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        # primary_master 必须是 graham_bank
        assert (df["primary_master"] == "graham_bank").any()


def test_screen_industry_unknown_returns_empty():
    df = screen_industry("不存在的行业XYZ", "stalwart", top_n=7)
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    # 列结构仍应保留
    for col in _REQUIRED_COLS:
        assert col in df.columns


def test_screen_industry_top_n_caps():
    """top_n 上限有效。"""
    df = screen_industry("白酒", "stalwart", top_n=1)
    assert len(df) <= 1


# ─── 5) 全聚焦批量 ─────────────────────────────────────────────────────


def test_screen_all_focus_returns_dict():
    results = screen_all_focus()
    assert isinstance(results, dict)
    focus = yaml.safe_load(FOCUS_YAML.read_text(encoding="utf-8"))["focus"]
    assert len(results) == len(focus)
    for industry, df in results.items():
        assert isinstance(industry, str)
        assert isinstance(df, pd.DataFrame)
        # 列结构必须固定
        for col in _REQUIRED_COLS:
            assert col in df.columns, f"{industry} missing col {col}"


def test_screen_all_focus_baijiu_nonempty():
    """白酒至少 2 家(自选茅台 + 五粮液保底)。"""
    results = screen_all_focus()
    focus_names = {f["industry"] for f in yaml.safe_load(FOCUS_YAML.read_text(encoding="utf-8"))["focus"]}
    if "白酒" not in focus_names:
        pytest.skip("当前聚焦配置未包含白酒")
    df = results.get("白酒")
    assert df is not None
    assert len(df) >= 2


# ─── 6) 工具函数 ────────────────────────────────────────────────────────


def test_normalize_to_100():
    # 100 max 直接返回
    assert _normalize_to_100(82.0, 100) == 82.0
    # 9 max(piotroski) 缩放
    assert _normalize_to_100(9, 9) == 100.0
    assert _normalize_to_100(0, 9) == 0.0
    # NaN/None 安全
    assert _normalize_to_100(None, 100) is None
    assert _normalize_to_100(float("nan"), 100) is None
    # max=None 时,0-100 范围允许
    assert _normalize_to_100(50.0, None) == 50.0
    assert _normalize_to_100(150.0, None) is None


def test_rating_from_score_thresholds():
    assert _rating_from_score(80) == "🟢 优秀"
    assert _rating_from_score(70) == "🟡 合格"
    assert _rating_from_score(50) == "🟠 警戒"
    assert _rating_from_score(30) == "🔴 不及格"
    assert _rating_from_score(None) == "⚪ 数据不足"
    assert _rating_from_score(float("nan")) == "⚪ 数据不足"


def test_load_focus_yaml():
    cfg = _load_focus_yaml()
    assert "focus" in cfg
    assert len(cfg["focus"]) >= 8


def test_lynch_primary_type_set():
    """4 类走 lynch_classifier,2 类走 graham_X。"""
    assert _LYNCH_PRIMARY_TYPES == {
        "stalwart", "fast_grower", "cyclical", "slow_grower"
    }
    assert _DIRECT_GRAHAM_PRIMARY == {
        "bank": "graham_bank",
        "insurance": "graham_insurance",
    }
