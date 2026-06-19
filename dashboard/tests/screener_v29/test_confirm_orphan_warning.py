"""tabs.screener.confirm 一致性检查 · focus 之外的 ticker 上报为 orphan."""
from __future__ import annotations

import pytest


class _Entry:
    def __init__(self, ticker, name, source_industry=None):
        self.ticker = ticker
        self.name = name
        if source_industry is not None:
            self.source_industry = source_industry


@pytest.fixture
def fake_companies_csv(tmp_path, monkeypatch):
    from funnel import orphans as fo
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(
        "folder,stock,name,category,industry,industry_l2\n"
        "01,600519,贵州茅台,non_financial,食品饮料,白酒\n"
        "02,603259,药明康德,non_financial,医药生物,化学制药\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fo, "_COMPANIES_CSV", csv_path)
    return csv_path


def test_orphan_detected_when_industry_outside_focus(monkeypatch, fake_companies_csv):
    from funnel import orphans as fo
    import watchlist as _wl

    # focus = {白酒};watchlist 持有化学制药股(药明康德)
    monkeypatch.setattr(_wl, "load", lambda: [_Entry("603259", "药明康德")])

    out = fo.find_orphan_watchlist(focus_names={"白酒"})
    assert len(out) == 1
    assert out[0]["ticker"] == "603259"
    assert out[0]["industry"] == "化学制药"
