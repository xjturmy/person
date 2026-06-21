"""自选股集合解析 — 合并 .config/portfolio.yaml + .tools/portfolio/portfolio.yaml + .temp/watchlist.md。

公司研究 tab 用它来识别"我的池子",把 ⭐ 标记 + 置顶。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_CONFIG = ROOT / ".config" / "portfolio.yaml"
PORTFOLIO_TOOL = ROOT / ".tools" / "portfolio" / "portfolio.yaml"
WATCHLIST_MD = ROOT / ".temp" / "watchlist.md"

_TICKER_IN_PAREN = re.compile(r"\((\d{4,6}[A-Z]*)\)")


def _load_yaml_tickers(path: Path, list_keys: tuple[str, ...]) -> set[str]:
    """从 yaml 抽 ticker 集合。

    - list_keys: 顶层数组字段名,例如 ('positions',) 或 ('holdings',)
    - 仅保留 status ∈ {active, watch} 或无 status 的条目;exited 排除。
    """
    if not path.exists():
        return set()
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    out: set[str] = set()
    for k in list_keys:
        for row in (doc.get(k) or []):
            if not isinstance(row, dict):
                continue
            t = row.get("ticker")
            if not t:
                continue
            status = (row.get("status") or "").lower()
            if status == "exited":
                continue
            out.add(str(t).strip())
    return out


def _load_watchlist_tickers(path: Path) -> set[str]:
    """从 .temp/watchlist.md 抽括号里的 ticker。

    格式示例:`- [ ] **蜜雪集团** (02097) — ...`
    勾选与否都算"我关注"(checkbox 仅表示决策闭环,不代表移出池子)。
    """
    if not path.exists():
        return set()
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    return set(_TICKER_IN_PAREN.findall(text))


def load_self_selected_tickers() -> set[str]:
    """返回 portfolio + watchlist 合并后的自选 ticker 集合(已 strip,字符串)。"""
    return (
        _load_yaml_tickers(PORTFOLIO_CONFIG, ("positions",))
        | _load_yaml_tickers(PORTFOLIO_TOOL, ("holdings",))
        | _load_watchlist_tickers(WATCHLIST_MD)
    )


__all__ = ["load_self_selected_tickers"]
