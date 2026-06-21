"""离线测试 company_search:确保优先级和拼音/行业命中正确。"""

from __future__ import annotations

from pathlib import Path

import pytest

from components.search_bar import CompanySearcher, load_index, search

ROOT = Path(__file__).resolve().parents[4]
CSV_PATH = ROOT / ".config" / "companies.csv"


@pytest.fixture(scope="module")
def index():
    assert CSV_PATH.exists(), f"companies.csv 缺失:{CSV_PATH}"
    idx = load_index(CSV_PATH)
    assert len(idx) >= 15, f"15 家自选不齐:实际 {len(idx)}"
    return idx


def _folder(hits, n=0):
    return hits[n].entry.folder


def test_ticker_exact(index):
    hits = search("600519", index)
    assert len(hits) >= 1
    assert _folder(hits) == "06_贵州茅台"
    assert hits[0].matched_field == "ticker"


def test_ticker_prefix(index):
    hits = search("60", index)
    folders = {h.entry.folder for h in hits}
    assert "01_新华保险" in folders  # 601336
    assert "06_贵州茅台" in folders  # 600519
    assert all(h.entry.ticker.startswith("60") for h in hits)


def test_hk_ticker(index):
    hits = search("02097", index)
    assert _folder(hits) == "03_蜜雪集团"


def test_name_exact(index):
    hits = search("贵州茅台", index)
    assert _folder(hits) == "06_贵州茅台"
    assert hits[0].matched_field == "name"


def test_name_partial(index):
    hits = search("茅台", index)
    folders = {h.entry.folder for h in hits}
    assert "06_贵州茅台" in folders


def test_pinyin_initials(index):
    hits = search("gzmt", index)
    assert _folder(hits) == "06_贵州茅台"
    assert hits[0].matched_field == "pinyin"


def test_pinyin_initials_uppercase(index):
    hits = search("GZMT", index)
    assert _folder(hits) == "06_贵州茅台"


def test_pinyin_full_prefix(index):
    hits = search("guizhou", index)
    folders = {h.entry.folder for h in hits}
    assert "06_贵州茅台" in folders


def test_industry_l2_returns_all_in_industry(index):
    hits = search("白酒", index)
    folders = {h.entry.folder for h in hits}
    # 自选 15 家中白酒应有茅台 + 五粮液
    assert "06_贵州茅台" in folders
    assert "11_五粮液" in folders


def test_industry_l1(index):
    hits = search("食品饮料", index)
    folders = {h.entry.folder for h in hits}
    assert "06_贵州茅台" in folders
    assert "11_五粮液" in folders
    assert "13_伊利股份" in folders
    assert "03_蜜雪集团" in folders


def test_no_match_returns_empty_or_fuzzy(index):
    hits = search("zzzzzznoexist", index)
    # rapidfuzz partial_ratio < 60 不应该匹配明显垃圾串
    assert len(hits) == 0


def test_company_searcher_class_smoke():
    """CompanySearcher class 包装层冒烟。"""
    s = CompanySearcher()
    rs = s.search("茅台")
    assert len(rs) >= 1
    assert rs[0]["ticker"] == "600519"
    assert rs[0]["name"] == "贵州茅台"
    assert "score" in rs[0] and "matched_field" in rs[0]


def test_company_searcher_search_folders():
    s = CompanySearcher()
    folders = s.search_folders("gzmt")
    assert "06_贵州茅台" in folders


def test_l2_fallback_no_op_when_market_db_missing():
    """search_l2_fallback 在 market.duckdb 不存在时静默返回 []。"""
    from components.search_bar import search_l2_fallback
    # 不应抛异常;返回 []
    assert search_l2_fallback("foo") == []


def test_empty_query(index):
    assert search("", index) == []
    assert search("   ", index) == []


def test_priority_ordering(index):
    # 输入 "茅" — name 子串命中(50 分),应该排第一
    hits = search("茅", index)
    assert _folder(hits) == "06_贵州茅台"


def test_score_descending(index):
    hits = search("60", index)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True), f"score 没有降序:{scores}"


def test_limit_capping(index):
    # 食品饮料行业有多家,限制返回数
    hits = search("食品饮料", index, limit=2)
    assert len(hits) <= 2
