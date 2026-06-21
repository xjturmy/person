"""confirm._stamp_confirmed_at / add_focus weight+note 持久化."""
from __future__ import annotations

import datetime as _dt
import shutil
from pathlib import Path

import yaml


def test_stamp_confirmed_at_today(tmp_path, monkeypatch):
    from tabs.industry import confirm as _confirm
    import state as _state

    # 准备临时 focus.yaml
    fake = tmp_path / "focus.yaml"
    fake.write_text(yaml.safe_dump({
        "focus": [{"industry": "白酒", "type": "stalwart", "weight": 1.0}],
        "top_n": 7,
        "market_cap_min": 5_000_000_000,
    }, allow_unicode=True), encoding="utf-8")

    monkeypatch.setattr(_confirm, "_FOCUS_YAML", fake)
    monkeypatch.setattr(_state, "FOCUS_YAML", fake)

    # 直接调 stamp
    n = _confirm._stamp_confirmed_at(["白酒"])
    assert n == 1

    d = yaml.safe_load(fake.read_text(encoding="utf-8"))
    rows = d["focus"]
    today = _dt.date.today().strftime("%Y-%m-%d")
    assert rows[0]["confirmed_at"] == today


def test_stamp_does_not_overwrite_existing(tmp_path, monkeypatch):
    from tabs.industry import confirm as _confirm

    fake = tmp_path / "focus.yaml"
    fake.write_text(yaml.safe_dump({
        "focus": [{
            "industry": "白酒", "type": "stalwart", "weight": 1.0,
            "confirmed_at": "2024-01-01",
        }],
        "top_n": 7, "market_cap_min": 5_000_000_000,
    }, allow_unicode=True), encoding="utf-8")

    monkeypatch.setattr(_confirm, "_FOCUS_YAML", fake)
    n = _confirm._stamp_confirmed_at(["白酒"])
    assert n == 0  # 已有日期,不覆盖

    d = yaml.safe_load(fake.read_text(encoding="utf-8"))
    assert d["focus"][0]["confirmed_at"] == "2024-01-01"


def test_add_focus_preserves_weight_and_note(tmp_path, monkeypatch):
    import state as _state

    fake = tmp_path / "focus.yaml"
    fake.write_text(yaml.safe_dump({
        "focus": [],
        "top_n": 7,
        "market_cap_min": 5_000_000_000,
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(_state, "FOCUS_YAML", fake)

    assert _state.add_focus("化学制品", "cyclical", weight=2.5, note="高景气") is True

    rows = yaml.safe_load(fake.read_text(encoding="utf-8"))["focus"]
    assert len(rows) == 1
    assert rows[0]["industry"] == "化学制品"
    assert rows[0]["type"] == "cyclical"
    assert rows[0]["weight"] == 2.5
    assert rows[0]["note"] == "高景气"


def test_confirm_draft_writes_weight_note(tmp_path, monkeypatch):
    """模拟 confirm 落盘: add_focus 应保留 draft 中的 weight / note."""
    import state as _state

    fake = tmp_path / "focus.yaml"
    fake.write_text(yaml.safe_dump({
        "focus": [],
        "top_n": 7,
        "market_cap_min": 5_000_000_000,
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(_state, "FOCUS_YAML", fake)

    draft = [
        {"industry": "白酒", "type": "stalwart", "weight": 3.0, "note": "核心持仓"},
        {"industry": "电池", "type": "fast_grower", "weight": 1.5, "note": ""},
    ]
    added = []
    for d in draft:
        ind = d.get("industry")
        t_ = d.get("type") or "stalwart"
        w = float(d.get("weight") or 1.0)
        note = d.get("note") or ""
        if ind and _state.add_focus(ind, t_, weight=w, note=note or None):
            added.append(ind)

    assert added == ["白酒", "电池"]
    rows = {r["industry"]: r for r in yaml.safe_load(fake.read_text(encoding="utf-8"))["focus"]}
    assert rows["白酒"]["weight"] == 3.0
    assert rows["白酒"]["note"] == "核心持仓"
    assert rows["电池"]["weight"] == 1.5
    assert "note" not in rows["电池"]
