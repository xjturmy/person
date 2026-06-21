"""preselect/confirm 之间靠 funnel.session 草稿传递."""
from __future__ import annotations


def test_draft_set_then_get_roundtrip(monkeypatch):
    from funnel import session as _session

    # fake session_state
    fake_ss: dict = {}
    monkeypatch.setattr(_session, "_session_state", lambda: fake_ss)

    draft = [
        {"industry": "光伏设备", "type": "fast_grower", "weight": 1.0, "note": "底部"},
        {"industry": "煤炭开采", "type": "cyclical",    "weight": 0.5, "note": ""},
    ]
    _session.set_draft(_session.FUNNEL_INDUSTRY_DRAFT, draft)

    got = _session.get_draft(_session.FUNNEL_INDUSTRY_DRAFT, [])
    assert got == draft

    # clear
    assert _session.clear_draft(_session.FUNNEL_INDUSTRY_DRAFT) is True
    assert _session.get_draft(_session.FUNNEL_INDUSTRY_DRAFT, "EMPTY") == "EMPTY"


def test_confirm_module_imports():
    """合约:tabs.industry 包及三个模块可干净 import."""
    from tabs.industry import analysis, preselect, confirm
    assert callable(analysis.render)
    assert callable(preselect.render)
    assert callable(confirm.render)
    assert callable(confirm._stamp_confirmed_at)
    assert callable(confirm._preview_orphans_after_removal)
