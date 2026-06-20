"""行业重组 helper 单测."""
from __future__ import annotations


def test_add_industry_to_draft(monkeypatch, tmp_path):
    from tabs.industry import _draft_helpers as dh

    fake_ss: dict = {}
    monkeypatch.setattr(
        "funnel.session._session_state", lambda: fake_ss
    )
    monkeypatch.setattr(
        "funnel.layers.get_focus_names", lambda: {"白酒"}
    )
    monkeypatch.setattr(dh, "DRAFT_YAML", tmp_path / "industry_preselect_draft.yaml")

    assert dh.add_industry_to_draft("白酒") is False
    assert dh.add_industry_to_draft("光伏设备", type_="fast_grower", note="test") is True
    assert dh.industry_in_draft("光伏设备") is True
    assert dh.add_industry_to_draft("光伏设备") is False

    draft = dh.get_industry_draft()
    assert draft[0]["industry"] == "光伏设备"
    assert draft[0]["type"] == "fast_grower"
    assert draft[0]["note"] == "test"


def test_passes_preselect_filters():
    from tabs.industry._filters import passes_preselect_filters

    base = dict(
        pe_pct=25.0,
        phase="bottoming",
        layer="offensive",
        has_holding=True,
        in_draft=True,
    )
    assert passes_preselect_filters(**base, filters={}) is True
    assert passes_preselect_filters(**base, filters={"pe_low": True}) is True
    assert passes_preselect_filters(
        **{**base, "pe_pct": 50.0}, filters={"pe_low": True}
    ) is False
    assert passes_preselect_filters(
        **{**base, "layer": "defensive"}, filters={"offensive": True}
    ) is False
    assert passes_preselect_filters(
        **{**base, "in_draft": False}, filters={"draft_only": True}
    ) is False


def test_sync_l1_table_selection(monkeypatch, tmp_path):
    from tabs.industry import _draft_helpers as dh

    fake_ss: dict = {}
    monkeypatch.setattr("funnel.session._session_state", lambda: fake_ss)
    monkeypatch.setattr("funnel.layers.get_focus_names", lambda: set())
    monkeypatch.setattr(dh, "DRAFT_YAML", tmp_path / "industry_preselect_draft.yaml")

    master = {
        "白酒": {"sw_l1": "食品饮料", "type": "stalwart"},
        "啤酒": {"sw_l1": "食品饮料", "type": "cyclical"},
        "银行": {"sw_l1": "银行", "type": "bank"},
    }
    l1_to_l2 = dh.build_l1_to_l2_map(master, include_companies=False)
    assert set(l1_to_l2["食品饮料"]) == {"白酒", "啤酒"}

    out = dh.sync_l1_table_selection(
        {"食品饮料"},
        l1_to_l2,
        master,
        table_l1_names={"食品饮料", "银行"},
    )
    assert len(out) == 2
    assert {d["industry"] for d in out} == {"白酒", "啤酒"}
    assert all(d["note"].startswith("全景·") for d in out)

    out2 = dh.sync_l1_table_selection(
        set(),
        l1_to_l2,
        master,
        table_l1_names={"食品饮料", "银行"},
    )
    assert out2 == []


def test_industry_draft_persists_across_session(monkeypatch, tmp_path):
    """刷新(清空 session)后仍能从 yaml 恢复勾选."""
    from tabs.industry import _draft_helpers as dh

    draft_path = tmp_path / "industry_preselect_draft.yaml"
    monkeypatch.setattr(dh, "DRAFT_YAML", draft_path)

    fake_ss: dict = {}
    monkeypatch.setattr("funnel.session._session_state", lambda: fake_ss)
    monkeypatch.setattr("funnel.layers.get_focus_names", lambda: set())

    dh.set_industry_draft([
        {"industry": "乘用车", "type": "cyclical", "weight": 1.0, "note": "全景·汽车"},
    ])
    assert draft_path.exists()

    fake_ss.clear()
    got = dh.get_industry_draft()
    assert len(got) == 1
    assert got[0]["industry"] == "乘用车"

    dh.clear_industry_draft()
    assert not draft_path.exists()
    fake_ss.clear()
    assert dh.get_industry_draft() == []


def test_build_l1_to_l2_map_merges_companies():
    from tabs.industry import _draft_helpers as dh

    master = {
        "保险": {"sw_l1": "非银金融", "type": "bank"},
    }
    l1_map = dh.build_l1_to_l2_map(master, include_companies=True)
    assert "非银金融" in l1_map
    assert "保险" in l1_map["非银金融"]
    # companies.csv 候选池还有证券,应合并进来
    assert "证券" in l1_map["非银金融"]
    assert "有色金属" in l1_map
    assert "工业金属" in l1_map["有色金属"]
