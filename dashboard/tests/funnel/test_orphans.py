"""funnel.orphans 单测 — watchlist 中游离于 focus 的标的检测."""
from __future__ import annotations

import pytest

from funnel import orphans as fo


class _Entry:
    def __init__(self, ticker, name, source_industry=None):
        self.ticker = ticker
        self.name = name
        if source_industry is not None:
            self.source_industry = source_industry


@pytest.fixture
def fake_companies_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(
        "folder,stock,name,category,industry,industry_l2\n"
        "01,600519,贵州茅台,non_financial,食品饮料,白酒\n"
        "02,603259,药明康德,non_financial,医药生物,化学制药\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fo, "_COMPANIES_CSV", csv_path)
    return csv_path


def test_orphan_when_industry_not_in_focus(monkeypatch, fake_companies_csv):
    import watchlist as _wl
    monkeypatch.setattr(_wl, "load",
                        lambda: [_Entry("600519", "贵州茅台")])

    out = fo.find_orphan_watchlist(focus_names={"化学制药"})
    assert len(out) == 1
    assert out[0]["ticker"] == "600519"
    assert out[0]["industry"] == "白酒"
    assert "不在聚焦列表" in out[0]["reason"]


def test_not_orphan_when_industry_in_focus(monkeypatch, fake_companies_csv):
    import watchlist as _wl
    monkeypatch.setattr(_wl, "load",
                        lambda: [_Entry("600519", "贵州茅台")])

    out = fo.find_orphan_watchlist(focus_names={"白酒"})
    assert out == []


def test_source_industry_takes_priority(monkeypatch, fake_companies_csv):
    """entry.source_industry 存在时,优先于 csv 反查."""
    import watchlist as _wl
    # ticker 在 csv 中是「白酒」,但 entry 自带 source_industry="化学制药"
    monkeypatch.setattr(_wl, "load",
                        lambda: [_Entry("600519", "贵州茅台",
                                        source_industry="化学制药")])

    # focus = 白酒 → 应是 orphan (因为 source_industry=化学制药 ∉ focus)
    out = fo.find_orphan_watchlist(focus_names={"白酒"})
    assert len(out) == 1
    assert out[0]["industry"] == "化学制药"

    # focus = 化学制药 → 不是 orphan
    out = fo.find_orphan_watchlist(focus_names={"化学制药"})
    assert out == []


def test_unknown_industry_marked(monkeypatch, fake_companies_csv):
    import watchlist as _wl
    # ticker 不在 csv
    monkeypatch.setattr(_wl, "load",
                        lambda: [_Entry("999999", "未知股")])

    out = fo.find_orphan_watchlist(focus_names={"白酒"})
    assert len(out) == 1
    assert out[0]["industry"] == ""
    assert out[0]["reason"] == "未识别行业"


def test_empty_focus_returns_all(monkeypatch, fake_companies_csv):
    import watchlist as _wl
    monkeypatch.setattr(_wl, "load", lambda: [
        _Entry("600519", "贵州茅台"),
        _Entry("603259", "药明康德"),
    ])
    out = fo.find_orphan_watchlist(focus_names=set())
    assert len(out) == 2
