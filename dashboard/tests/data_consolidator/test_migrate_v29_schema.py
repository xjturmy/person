"""migrate_v29_schema 单测 — 幂等 / 反查 / dry-run."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from data_consolidator import migrate_v29_schema as mig


# ─── 辅助 ────────────────────────────────────────────────────────────────
def _write_yaml(path: Path, data) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture
def companies_csv(tmp_path) -> Path:
    p = tmp_path / "companies.csv"
    p.write_text(
        "folder,stock,name,category,industry,industry_l2\n"
        "06_贵州茅台,600519,贵州茅台,non_financial,食品饮料,白酒\n"
        "07_美的集团,333,美的集团,non_financial,家用电器,白色家电\n"
        "12_招商银行,600036,招商银行,bank,银行,股份制银行\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def old_focus_yaml(tmp_path) -> Path:
    p = tmp_path / "focus_industries.yaml"
    _write_yaml(
        p,
        {
            "focus": [
                {"industry": "白酒", "type": "stalwart", "weight": 1.0},
                {"industry": "股份制银行", "type": "bank", "weight": 1.0},
            ],
            "top_n": 7,
        },
    )
    return p


@pytest.fixture
def old_watchlist_yaml(tmp_path) -> Path:
    p = tmp_path / "watchlist.yaml"
    _write_yaml(
        p,
        {
            "entries": [
                {"ticker": "600519", "name": "贵州茅台", "status": "pending"},
                {"ticker": "000333", "name": "美的集团", "status": "closed"},
                {"ticker": "999999", "name": "不存在公司", "status": "pending"},
            ]
        },
    )
    return p


# ─── 用例 ────────────────────────────────────────────────────────────────
def test_focus_migration_adds_confirmed_at(
    old_focus_yaml, companies_csv, tmp_path
):
    """1. 旧 focus.yaml(无 confirmed_at) → 每条都有 confirmed_at='unknown',.bak 存在."""
    wl = tmp_path / "watchlist.yaml"
    _write_yaml(wl, {"entries": []})  # 占位空 watchlist

    report = mig.run(
        focus_path=old_focus_yaml,
        watchlist_path=wl,
        companies_path=companies_csv,
        dry_run=False,
    )

    data = _read_yaml(old_focus_yaml)
    assert all(item["confirmed_at"] == "unknown" for item in data["focus"])
    assert report["focus"]["migrated"] == 2
    assert report["focus"]["skipped"] == 0
    bak = old_focus_yaml.with_suffix(".yaml.bak")
    assert bak.exists(), ".bak 备份应存在"


def test_already_migrated_focus_is_skipped(
    tmp_path, companies_csv
):
    """2. 已迁移 focus.yaml → 再跑提示 already migrated,不动文件."""
    focus = tmp_path / "focus_industries.yaml"
    _write_yaml(
        focus,
        {
            "focus": [
                {"industry": "白酒", "type": "stalwart", "confirmed_at": "2026-06-01"},
            ],
        },
    )
    wl = tmp_path / "watchlist.yaml"
    _write_yaml(
        wl,
        {
            "entries": [
                {"ticker": "600519", "name": "贵州茅台", "source_industry": "白酒"},
            ]
        },
    )
    mtime_before = focus.stat().st_mtime

    report = mig.run(
        focus_path=focus,
        watchlist_path=wl,
        companies_path=companies_csv,
        dry_run=False,
    )

    assert report["all_migrated"] is True
    assert report["focus"]["migrated"] == 0
    assert report["focus"]["skipped"] == 1
    # 文件未动 (mtime 不变)
    assert focus.stat().st_mtime == mtime_before
    # 原值保留
    data = _read_yaml(focus)
    assert data["focus"][0]["confirmed_at"] == "2026-06-01"


def test_watchlist_lookup_hits_industry(
    old_focus_yaml, old_watchlist_yaml, companies_csv
):
    """3. 旧 watchlist + companies.csv 含茅台 → 茅台 source_industry='白酒'."""
    mig.run(
        focus_path=old_focus_yaml,
        watchlist_path=old_watchlist_yaml,
        companies_path=companies_csv,
        dry_run=False,
    )
    data = _read_yaml(old_watchlist_yaml)
    by_ticker = {e["ticker"]: e for e in data["entries"]}
    assert by_ticker["600519"]["source_industry"] == "白酒"
    assert by_ticker["000333"]["source_industry"] == "白色家电"


def test_watchlist_ticker_format_normalization(
    old_focus_yaml, tmp_path
):
    """4. companies.csv 写 '600519.SH',watchlist 写 '600519' → 仍能匹配."""
    csv_p = tmp_path / "companies.csv"
    csv_p.write_text(
        "folder,stock,name,category,industry,industry_l2\n"
        "06_贵州茅台,600519.SH,贵州茅台,non_financial,食品饮料,白酒\n",
        encoding="utf-8",
    )
    wl = tmp_path / "watchlist.yaml"
    _write_yaml(wl, {"entries": [{"ticker": "600519", "name": "贵州茅台"}]})

    mig.run(
        focus_path=old_focus_yaml,
        watchlist_path=wl,
        companies_path=csv_p,
        dry_run=False,
    )
    data = _read_yaml(wl)
    assert data["entries"][0]["source_industry"] == "白酒"


def test_watchlist_unknown_ticker_gets_unknown(
    old_focus_yaml, old_watchlist_yaml, companies_csv
):
    """5. watchlist 含 companies.csv 不存在的 ticker → source_industry='unknown'."""
    mig.run(
        focus_path=old_focus_yaml,
        watchlist_path=old_watchlist_yaml,
        companies_path=companies_csv,
        dry_run=False,
    )
    data = _read_yaml(old_watchlist_yaml)
    by_ticker = {e["ticker"]: e for e in data["entries"]}
    assert by_ticker["999999"]["source_industry"] == "unknown"


def test_dry_run_does_not_write(
    old_focus_yaml, old_watchlist_yaml, companies_csv, capsys
):
    """6. --dry-run:diff 打印但文件不变."""
    focus_before = old_focus_yaml.read_text(encoding="utf-8")
    wl_before = old_watchlist_yaml.read_text(encoding="utf-8")

    report = mig.run(
        focus_path=old_focus_yaml,
        watchlist_path=old_watchlist_yaml,
        companies_path=companies_csv,
        dry_run=True,
    )
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "dry-run: 文件未改动" in out
    assert "+ focus[白酒].confirmed_at" in out
    # 文件原封不动
    assert old_focus_yaml.read_text(encoding="utf-8") == focus_before
    assert old_watchlist_yaml.read_text(encoding="utf-8") == wl_before
    # 无 .bak
    assert not old_focus_yaml.with_suffix(".yaml.bak").exists()
    assert report["dry_run"] is True
