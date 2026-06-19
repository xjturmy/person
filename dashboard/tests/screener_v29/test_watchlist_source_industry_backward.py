"""watchlist.WatchlistEntry 兼容 — 旧 yaml 无 source_industry 字段 → 默认 "unknown"."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def redirect_paths(tmp_path, monkeypatch):
    import watchlist as wl
    monkeypatch.setattr(wl, "WATCHLIST_YAML", tmp_path / "watchlist.yaml")
    monkeypatch.setattr(wl, "LEGACY_MD", tmp_path / "watchlist.md")


def test_load_old_yaml_defaults_unknown():
    import watchlist as wl

    # 写一个不含 source_industry 字段的旧 yaml
    wl.WATCHLIST_YAML.parent.mkdir(parents=True, exist_ok=True)
    wl.WATCHLIST_YAML.write_text(
        "entries:\n"
        "  - ticker: '000333'\n"
        "    name: 美的集团\n"
        "    added_at: '2026-06-10'\n"
        "    preset: 林奇\n"
        "    status: pending\n",
        encoding="utf-8",
    )

    entries = wl.load()
    assert len(entries) == 1
    assert entries[0].source_industry == "unknown"
    assert entries[0].name == "美的集团"


def test_new_save_persists_source_industry():
    import pandas as pd
    import watchlist as wl

    df = pd.DataFrame([
        {"ticker": "600519", "name": "茅台", "source_industry": "白酒"},
    ])
    n = wl.add(df, preset="v2.9")
    assert n == 1

    # 回读
    e = wl.load()[0]
    assert e.source_industry == "白酒"

    # 文件 raw 也应带该字段
    raw = wl.WATCHLIST_YAML.read_text(encoding="utf-8")
    assert "source_industry" in raw
    assert "白酒" in raw


def test_add_without_source_industry_defaults_unknown():
    import pandas as pd
    import watchlist as wl

    df = pd.DataFrame([{"ticker": "600519", "name": "茅台"}])
    wl.add(df, preset="v2.9")
    e = wl.load()[0]
    assert e.source_industry == "unknown"
