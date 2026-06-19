"""funnel.orphans · 检测 watchlist 中游离于 focus 之外的标的.

不依赖 streamlit;纯数据层。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_COMPANIES_CSV = _PROJECT_ROOT / ".config" / "companies.csv"

# 让 dashboard 内部模块可被 import
_DASH_DIR = str(Path(__file__).resolve().parents[1])
if _DASH_DIR not in sys.path:
    sys.path.insert(0, _DASH_DIR)


def _load_ticker_to_industry() -> dict[str, str]:
    """companies.csv → {ticker → industry_l2}.

    NOTE: 不做行业名规范化,精确匹配 (TODO P1)。
    """
    if not _COMPANIES_CSV.exists():
        return {}
    out: dict[str, str] = {}
    with _COMPANIES_CSV.open() as f:
        for r in csv.DictReader(f):
            t = str(r.get("stock", "")).zfill(6)
            if not t:
                continue
            out[t] = str(r.get("industry_l2", "") or "")
    return out


def find_orphan_watchlist(focus_names: set[str]) -> list[dict]:
    """返回 watchlist 中 industry 不在 focus 的条目.

    每条:{ticker, name, industry, reason}
    industry 取值优先级:entry.source_industry → companies.csv.industry_l2 → ""

    focus_names 为空时,所有 entry 都算 orphan (industry 未匹配)。
    """
    import watchlist as _wl  # noqa: WPS433
    try:
        entries = _wl.load() or []
    except Exception:
        return []

    t2i = _load_ticker_to_industry()
    out: list[dict] = []
    for e in entries:
        ticker = getattr(e, "ticker", "") or ""
        name = getattr(e, "name", "") or ""
        # entry.source_industry 当前 WatchlistEntry 未定义,留兼容空位
        industry: Optional[str] = getattr(e, "source_industry", None)
        if not industry:
            industry = t2i.get(ticker, "") or ""
        if industry in focus_names:
            continue
        out.append({
            "ticker": ticker,
            "name": name,
            "industry": industry,
            "reason": (
                f"行业 [{industry}] 不在聚焦列表"
                if industry else "未识别行业"
            ),
        })
    return out


__all__ = ["find_orphan_watchlist"]
