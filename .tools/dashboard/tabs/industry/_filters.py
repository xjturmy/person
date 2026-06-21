"""行业预选快捷筛选 — 纯函数,便于单测."""
from __future__ import annotations


def passes_preselect_filters(
    *,
    pe_pct: float | None,
    phase: str | None,
    layer: str | None,
    has_holding: bool,
    in_draft: bool,
    filters: dict[str, bool],
) -> bool:
    """filters keys: pe_low, offensive, bottoming, held, draft_only."""
    if filters.get("draft_only") and not in_draft:
        return False
    if filters.get("pe_low"):
        if pe_pct is None or float(pe_pct) >= 30:
            return False
    if filters.get("offensive") and layer != "offensive":
        return False
    if filters.get("bottoming") and phase != "bottoming":
        return False
    if filters.get("held") and not has_holding:
        return False
    return True


__all__ = ["passes_preselect_filters"]
