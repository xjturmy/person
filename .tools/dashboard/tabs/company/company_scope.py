"""公司研究页的公司范围过滤辅助。

供页面选择器按「当前持仓 / 观察池 / 全部公司」过滤公司目录列表。
模块只做数据读取和纯过滤,不直接渲染 Streamlit UI。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
TOOLS_DIR = ROOT / ".tools"
for _p in (DASHBOARD_DIR, TOOLS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SCOPE_ACTIVE = "当前持仓"
SCOPE_WATCH = "观察池"
SCOPE_ALL = "全部公司"
SCOPE_OPTIONS = (SCOPE_ACTIVE, SCOPE_WATCH, SCOPE_ALL)


def _normalize_ticker(ticker: object) -> str:
    """统一 ticker 字符串,兼容 A/H 股以及带交易所后缀的写法。"""
    value = str(ticker or "").strip()
    if not value:
        return ""
    value = value.split(".", 1)[0]
    if value.isdigit() and len(value) < 6:
        return value.zfill(6)
    return value


def _ticker_set(rows: Iterable[object]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        ticker = _normalize_ticker(getattr(row, "ticker", row))
        if ticker:
            out.add(ticker)
    return out


def load_active_portfolio_tickers() -> set[str]:
    """读取 portfolio 中 status=active 的 ticker 集合;失败时返回空集合。"""
    try:
        from portfolio.loader import load_portfolio

        return _ticker_set(load_portfolio().active())
    except Exception:
        return set()


def load_watch_tickers() -> set[str]:
    """读取观察池 ticker 集合:portfolio watch + watchlist.yaml pending entries。"""
    tickers: set[str] = set()
    try:
        from portfolio.loader import load_portfolio

        tickers |= _ticker_set(load_portfolio().watch())
    except Exception:
        pass

    try:
        import watchlist as _watchlist

        tickers |= _ticker_set(_watchlist.ticker_status_map(only_pending=True).keys())
    except Exception:
        pass

    return tickers


def _scope_tickers(scope: str) -> set[str] | None:
    if scope == SCOPE_ACTIVE:
        return load_active_portfolio_tickers()
    if scope == SCOPE_WATCH:
        return load_watch_tickers()
    return None


def filter_companies_by_scope(
    companies: Iterable[str],
    folder_to_ticker: dict[str, str],
    scope: str,
) -> tuple[list[str], str]:
    """按范围过滤公司列表,返回 (过滤后的 companies, 提示信息)。

    - 「全部公司」或未知 scope:原样返回全部公司。
    - 「当前持仓」为空时返回空列表,提示中包含可降级信息,方便页面 fallback。
    - 「观察池」合并 portfolio watch 与 watchlist.yaml pending entries。
    """
    company_list = list(companies)
    if scope not in SCOPE_OPTIONS:
        return company_list, f"未知范围「{scope}」,已使用全部公司。"
    if scope == SCOPE_ALL:
        return company_list, f"全部公司:共 {len(company_list)} 家。"

    wanted = _scope_tickers(scope) or set()
    if not wanted:
        if scope == SCOPE_ACTIVE:
            return [], "当前持仓为空,页面可降级显示全部公司。"
        return [], "观察池为空,页面可降级显示全部公司。"

    filtered = [
        folder for folder in company_list
        if _normalize_ticker(folder_to_ticker.get(folder)) in wanted
    ]
    missing = len(wanted) - len(filtered)
    hint = f"{scope}:匹配 {len(filtered)} 家。"
    if missing > 0:
        hint += f"另有 {missing} 个 ticker 不在当前公司清单中。"
    if not filtered:
        hint += "页面可降级显示全部公司。"
    return filtered, hint


__all__ = [
    "SCOPE_ACTIVE",
    "SCOPE_WATCH",
    "SCOPE_ALL",
    "SCOPE_OPTIONS",
    "filter_companies_by_scope",
    "load_active_portfolio_tickers",
    "load_watch_tickers",
]
