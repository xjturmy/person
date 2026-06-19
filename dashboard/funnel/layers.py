"""funnel.layers · 聚焦行业 → 候选 ticker → screener universe.

数据链路:
  focus_industries.yaml → state.get_focus_names()
    → expand_focus_to_tickers() (每行业三级降级走 industry.screener)
    → get_screener_universe() (反查 companies.csv 拿 name/industry_l2)

缓存:
  模块级字典缓存,key = (frozenset(focus_names),
                       companies_csv_mtime,
                       industry_master_yaml_mtime)
  不使用 @st.cache_data — 单测无 streamlit runtime 会报错。
  ``_clear_cache()`` 给测试用。
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# preson 根 / 常量
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_COMPANIES_CSV = _PROJECT_ROOT / ".config" / "companies.csv"
_INDUSTRY_MASTER_YAML = _PROJECT_ROOT / ".config" / "industry_master.yaml"

# 让 dashboard 内部模块可被 import (与 industry.screener 一致的做法)
_DASH_DIR = str(Path(__file__).resolve().parents[1])
if _DASH_DIR not in sys.path:
    sys.path.insert(0, _DASH_DIR)


# ─── focus 列表读取 (薄包装 state.py) ─────────────────────────────────


def get_focus_industries() -> list[dict]:
    """[{industry, type, weight, ...}] — 直接读 state.get_focus_list()."""
    import state as _state  # noqa: WPS433
    return list(_state.get_focus_list() or [])


def get_focus_names() -> set[str]:
    """聚焦行业名集合 — 直接读 state.get_focus_names()."""
    import state as _state  # noqa: WPS433
    return set(_state.get_focus_names() or set())


# ─── 缓存 ──────────────────────────────────────────────────────────────


# key: (frozenset[str], float, float) → value: set[str] | DataFrame
_expand_cache: dict[tuple, set[str]] = {}
_universe_cache: dict[tuple, pd.DataFrame] = {}


def _mtime(path: Path) -> float:
    try:
        return os.path.getmtime(path)
    except (OSError, FileNotFoundError):
        return 0.0


def _cache_key(focus_names: set[str]) -> tuple:
    return (
        frozenset(focus_names),
        _mtime(_COMPANIES_CSV),
        _mtime(_INDUSTRY_MASTER_YAML),
    )


def _clear_cache() -> None:
    """测试钩子 — 清空所有模块级缓存。"""
    _expand_cache.clear()
    _universe_cache.clear()


# ─── companies.csv 读取 ──────────────────────────────────────────────


def _load_companies_csv() -> pd.DataFrame:
    """读 .config/companies.csv → DataFrame(stock/name/industry_l2/...).

    NOTE: companies.csv 的 industry_l2 可能与 industry_master.yaml.name
    大小写或全角不一致;本期不做规范化,精确匹配。TODO 留给 P1。
    """
    if not _COMPANIES_CSV.exists():
        return pd.DataFrame(columns=["stock", "name", "industry_l2"])
    rows: list[dict] = []
    with _COMPANIES_CSV.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty and "stock" in df.columns:
        df["stock"] = df["stock"].astype(str).str.zfill(6)
    return df


# ─── 行业 → ticker 展开 ──────────────────────────────────────────────


def expand_focus_to_tickers(focus_names: set[str]) -> set[str]:
    """把行业名集合展开成 ticker 集合.

    实现:对每个行业调用 industry.screener.screen_industry(top_n=None)
    取所有 candidate.ticker 并集;若该行业三级降级仍空,
    fallback 直接 join companies.csv WHERE industry_l2 == industry。
    """
    key = _cache_key(focus_names)
    if key in _expand_cache:
        return set(_expand_cache[key])

    tickers: set[str] = set()
    if not focus_names:
        _expand_cache[key] = tickers
        return set(tickers)

    # 延迟 import — 避免 funnel 包导入时拉起 duckdb 等重依赖
    try:
        from industry import screener as _scr  # noqa: WPS433
    except Exception:
        _scr = None

    df_csv = _load_companies_csv()

    for industry in focus_names:
        got: set[str] = set()
        if _scr is not None:
            try:
                # screen_industry 的 type 必填 (评分用);展开用 type='stalwart'
                # 占位即可 — 这里只取 ticker 列,不在意 score。
                # 但评分慢,所以走更轻量的 list_industry_candidates。
                cands = _scr.list_industry_candidates(industry)
                got = {str(c["ticker"]).zfill(6) for c in (cands or [])
                       if c.get("ticker")}
            except Exception:
                got = set()
        # fallback: companies.csv WHERE industry_l2 == industry
        if not got and not df_csv.empty and "industry_l2" in df_csv.columns:
            sub = df_csv[df_csv["industry_l2"] == industry]
            got = set(sub["stock"].astype(str).tolist())
        tickers |= got

    _expand_cache[key] = set(tickers)
    return tickers


# ─── screener universe ───────────────────────────────────────────────


_UNIVERSE_COLS = ["ticker", "name", "industry_l2"]


def get_screener_universe() -> pd.DataFrame:
    """聚焦行业展开后的全市场子集 (ticker/name/industry_l2).

    focus 为空 → 空 DataFrame (列结构保留)。
    """
    focus = get_focus_names()
    key = _cache_key(focus)
    if key in _universe_cache:
        return _universe_cache[key].copy()

    if not focus:
        empty = pd.DataFrame(columns=_UNIVERSE_COLS)
        _universe_cache[key] = empty
        return empty.copy()

    tickers = expand_focus_to_tickers(focus)
    if not tickers:
        empty = pd.DataFrame(columns=_UNIVERSE_COLS)
        _universe_cache[key] = empty
        return empty.copy()

    df_csv = _load_companies_csv()
    if df_csv.empty:
        empty = pd.DataFrame(columns=_UNIVERSE_COLS)
        _universe_cache[key] = empty
        return empty.copy()

    # 反查:companies.csv 里有的取 name/industry_l2;没有的填空
    csv_idx = df_csv.set_index("stock") if "stock" in df_csv.columns else None
    rows: list[dict] = []
    for t in sorted(tickers):
        name = ""
        ind = ""
        if csv_idx is not None and t in csv_idx.index:
            row = csv_idx.loc[t]
            # 防止多行同 ticker (理论上 unique)
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            name = str(row.get("name", "") or "")
            ind = str(row.get("industry_l2", "") or "")
        rows.append({"ticker": t, "name": name, "industry_l2": ind})

    df = pd.DataFrame(rows, columns=_UNIVERSE_COLS)
    _universe_cache[key] = df
    return df.copy()


# ─── watchlist tickers ───────────────────────────────────────────────


def get_watchlist_tickers() -> set[str]:
    """watchlist.yaml 中所有 entry 的 ticker 集合。"""
    import watchlist as _wl  # noqa: WPS433
    try:
        entries = _wl.load() or []
    except Exception:
        return set()
    return {getattr(e, "ticker", "") for e in entries if getattr(e, "ticker", "")}


__all__ = [
    "get_focus_industries",
    "get_focus_names",
    "expand_focus_to_tickers",
    "get_screener_universe",
    "get_watchlist_tickers",
    "_clear_cache",
]
