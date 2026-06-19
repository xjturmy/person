"""confirm._preview_orphans_after_removal:删 focus 行业前预演 orphan."""
from __future__ import annotations


class _FakeEntry:
    def __init__(self, ticker, name, source_industry=None):
        self.ticker = ticker
        self.name = name
        self.source_industry = source_industry


def test_preview_orphans_returns_orphan_after_remove(monkeypatch):
    """模拟:focus={白酒,电池};watchlist 含 600519(白酒);删白酒 → 该股变孤立."""
    from funnel import layers as _layers
    from funnel import orphans as _orphans
    from tabs.industry import confirm as _confirm

    # mock focus_names
    monkeypatch.setattr(_layers, "get_focus_names", lambda: {"白酒", "电池"})

    # mock watchlist.load → 一只白酒股
    import sys as _sys
    fake_wl = type(_sys)("watchlist_fake")
    fake_wl.load = lambda: [_FakeEntry("600519", "贵州茅台", source_industry="白酒")]
    monkeypatch.setitem(_sys.modules, "watchlist", fake_wl)

    # 删白酒 → 应有孤立
    orphans_after = _confirm._preview_orphans_after_removal({"白酒"})
    assert any(o["ticker"] == "600519" for o in orphans_after), \
        f"expect 600519 orphan, got {orphans_after}"

    # 不删任何 → 应无孤立
    orphans_none = _confirm._preview_orphans_after_removal(set())
    assert not any(o["ticker"] == "600519" for o in orphans_none)
