"""watchlist.py 单元测试 — yaml 持久化 + add 去重 + md 迁移。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

DASHBOARD = Path(__file__).resolve().parents[1]
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

import watchlist as wl  # noqa: E402


@pytest.fixture(autouse=True)
def redirect_paths(tmp_path, monkeypatch):
    yaml_path = tmp_path / "watchlist.yaml"
    md_path = tmp_path / "watchlist.md"
    monkeypatch.setattr(wl, "WATCHLIST_YAML", yaml_path)
    monkeypatch.setattr(wl, "LEGACY_MD", md_path)
    yield


def _df(*rows):
    return pd.DataFrame(rows)


def test_empty_load_returns_empty_list():
    assert wl.load() == []


def test_add_writes_yaml_and_dedups():
    df = _df(
        {"ticker": "000333", "name": "美的集团", "score": 78, "rating": "A"},
        {"ticker": "600519", "name": "贵州茅台", "score": 92, "rating": "A"},
    )
    n = wl.add(df, preset="林奇分类器")
    assert n == 2
    entries = wl.load()
    assert {e.ticker for e in entries} == {"000333", "600519"}
    meidi = next(e for e in entries if e.ticker == "000333")
    assert meidi.name == "美的集团"
    assert meidi.score == 78
    assert meidi.rating == "A"
    assert meidi.preset == "林奇分类器"
    assert meidi.status == "pending"

    # 再 add 一次 → 全去重
    n2 = wl.add(df, preset="林奇分类器")
    assert n2 == 0
    assert len(wl.load()) == 2


def test_add_with_short_ticker_pads():
    df = _df({"ticker": 333, "name": "美的"})
    wl.add(df, preset="x")
    assert wl.load()[0].ticker == "000333"


def test_save_load_roundtrip_preserves_fields():
    entries = [wl.WatchlistEntry(
        ticker="000001", name="平安银行", added_at="2026-06-11",
        preset="格雷厄姆银行", score=85.0, rating="B", status="pending",
        notes="低估观察",
    )]
    wl.save(entries)
    loaded = wl.load()
    assert len(loaded) == 1
    e = loaded[0]
    assert e.ticker == "000001"
    assert e.notes == "低估观察"
    assert e.score == 85.0


def test_is_in_watchlist_respects_status():
    wl.add(_df({"ticker": "000333", "name": "美的"}), preset="x")
    assert wl.is_in_watchlist("000333") is True
    wl.close("000333")
    assert wl.is_in_watchlist("000333") is False
    assert wl.is_in_watchlist("000333", only_pending=False) is True


def test_ticker_status_map_filters_pending():
    wl.add(_df(
        {"ticker": "000333", "name": "美的"},
        {"ticker": "600519", "name": "茅台"},
    ), preset="x")
    wl.close("600519")
    m = wl.ticker_status_map(only_pending=True)
    assert m == {"000333": "pending"}
    m2 = wl.ticker_status_map(only_pending=False)
    assert set(m2.keys()) == {"000333", "600519"}


def test_remove_deletes_entry():
    wl.add(_df({"ticker": "000333", "name": "美的"}), preset="x")
    assert wl.remove("000333") is True
    assert wl.load() == []
    assert wl.remove("000333") is False  # 已无


def test_set_status_invalid_raises():
    wl.add(_df({"ticker": "000333", "name": "美的"}), preset="x")
    with pytest.raises(ValueError):
        wl.set_status("000333", "bogus")


def test_migrate_from_md_parses_lines(tmp_path, monkeypatch):
    md = (
        "# 📋 观察池\n\n"
        "> 由 dash-02 公司筛选写入 · 勾选 ☑ 表示决策已闭环可移除\n\n"
        "- [ ] **美的集团** (000333) — 林奇分类器 通过 · 2026-06-10 · 评分 78 · PE 分位 23%\n"
        "- [x] **贵州茅台** (600519) — 格雷厄姆 通过 · 2026-06-09 · 评分 92\n"
        "- [ ] **平安银行** (1234) — gone bad line\n"  # ticker 不足 5 位 → 跳过
    )
    wl.LEGACY_MD.parent.mkdir(parents=True, exist_ok=True)
    wl.LEGACY_MD.write_text(md, encoding="utf-8")
    assert not wl.WATCHLIST_YAML.exists()

    n = wl.migrate_from_md_if_needed()
    assert n == 2
    assert wl.WATCHLIST_YAML.exists()
    # md 已重命名为 .bak
    assert not wl.LEGACY_MD.exists()
    assert wl.LEGACY_MD.with_suffix(".md.bak").exists()

    entries = wl.load()
    tickers = {e.ticker: e for e in entries}
    assert tickers["000333"].preset == "林奇分类器"
    assert tickers["000333"].added_at == "2026-06-10"
    assert tickers["000333"].score == 78
    assert tickers["000333"].status == "pending"
    assert tickers["600519"].status == "closed"


def test_migrate_idempotent_when_yaml_exists():
    wl.add(_df({"ticker": "000333", "name": "美的"}), preset="x")
    wl.LEGACY_MD.parent.mkdir(parents=True, exist_ok=True)
    wl.LEGACY_MD.write_text(
        "- [ ] **新条目** (000651) — x 通过 · 2026-06-01\n", encoding="utf-8"
    )
    n = wl.migrate_from_md_if_needed()
    assert n == 0
    # yaml 内容不变
    assert {e.ticker for e in wl.load()} == {"000333"}


def test_save_creates_bak_on_overwrite():
    wl.add(_df({"ticker": "000333", "name": "美的"}), preset="v1")
    wl.add(_df({"ticker": "600519", "name": "茅台"}), preset="v2")
    bak = wl.WATCHLIST_YAML.with_suffix(".yaml.bak")
    assert bak.exists()
