"""观察池数据层 — .config/watchlist.yaml 的统一读写入口.

替代旧的 .temp/watchlist.md(markdown 文本无结构),提供:
  - 结构化条目(WatchlistEntry dataclass)
  - 跨 Tab 一致的 is_in_watchlist / ticker_status_map 查询
  - 原子写 + .bak 备份
  - 从旧 markdown 一次性迁移

存储:`.config/watchlist.yaml`
schema:
  entries:
    - ticker: "000333"
      name: 美的集团
      added_at: "2026-06-11"
      preset: 林奇分类器
      score: 78           # 可空
      rating: A           # 可空
      status: pending     # pending | closed
      notes: ""
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
WATCHLIST_YAML = ROOT / ".config" / "watchlist.yaml"
LEGACY_MD = ROOT / ".temp" / "watchlist.md"

VALID_STATUSES = {"pending", "closed"}


@dataclass
class WatchlistEntry:
    ticker: str
    name: str
    added_at: str
    preset: str = ""
    score: float | None = None
    rating: str | None = None
    status: str = "pending"
    notes: str = ""
    # v2.9 P0c/P1:行业来源(写入时 funnel.layers 反查;旧文件缺该字段默认 "unknown")
    source_industry: str = "unknown"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WatchlistEntry":
        si = d.get("source_industry")
        return cls(
            ticker=str(d.get("ticker", "")).zfill(6),
            name=str(d.get("name", "")),
            added_at=str(d.get("added_at", "")),
            preset=str(d.get("preset", "") or ""),
            score=_to_float(d.get("score")),
            rating=(str(d["rating"]) if d.get("rating") not in (None, "") else None),
            status=str(d.get("status", "pending") or "pending"),
            notes=str(d.get("notes", "") or ""),
            source_industry=(str(si) if si not in (None, "") else "unknown"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        if pd.isna(f):
            return None
        return f
    except Exception:
        return None


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ─── 持久化 ─────────────────────────────────────────────────────────────


def load() -> list[WatchlistEntry]:
    """读 yaml,缺失则返回 []。会先尝试从旧 md 迁移。"""
    migrate_from_md_if_needed()
    if not WATCHLIST_YAML.exists():
        return []
    try:
        data = yaml.safe_load(WATCHLIST_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    raw = data.get("entries") or []
    return [WatchlistEntry.from_dict(e) for e in raw if e.get("ticker")]


def save(entries: list[WatchlistEntry]) -> None:
    """原子写 + .bak 备份。"""
    WATCHLIST_YAML.parent.mkdir(parents=True, exist_ok=True)
    if WATCHLIST_YAML.exists():
        shutil.copy2(WATCHLIST_YAML, WATCHLIST_YAML.with_suffix(".yaml.bak"))

    payload = {"entries": [e.to_dict() for e in entries]}
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)

    fd, tmp = tempfile.mkstemp(
        prefix=".watchlist.", suffix=".tmp", dir=str(WATCHLIST_YAML.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, WATCHLIST_YAML)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def add(rows: pd.DataFrame, preset: str) -> int:
    """把 DataFrame 行加入观察池(按 ticker 去重),返回新增数。

    rows 需含 ticker / name 列;可选 score / rating / max_score。
    """
    if rows is None or rows.empty:
        return 0
    existing = load()
    existing_tickers = {e.ticker for e in existing}
    added_n = 0
    today = _today()
    for _, row in rows.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker or ticker in existing_tickers:
            continue
        score = _to_float(row.get("score"))
        rating = row.get("rating") if pd.notna(row.get("rating", None)) else None
        # v2.9: 可选 source_industry 列(funnel 反查得来,缺则 "unknown")
        si_val = row.get("source_industry") if "source_industry" in rows.columns else None
        if si_val is None or (isinstance(si_val, float) and pd.isna(si_val)) or si_val == "":
            source_industry = "unknown"
        else:
            source_industry = str(si_val)
        existing.append(WatchlistEntry(
            ticker=ticker,
            name=str(row.get("name", "")),
            added_at=today,
            preset=preset or "",
            score=score,
            rating=(str(rating) if rating is not None else None),
            status="pending",
            source_industry=source_industry,
        ))
        existing_tickers.add(ticker)
        added_n += 1
    if added_n:
        save(existing)
    return added_n


def remove(ticker: str) -> bool:
    """硬删一条。"""
    ticker = str(ticker).zfill(6)
    entries = load()
    out = [e for e in entries if e.ticker != ticker]
    if len(out) == len(entries):
        return False
    save(out)
    return True


def set_status(ticker: str, status: str) -> bool:
    """切状态(pending ↔ closed)。"""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    ticker = str(ticker).zfill(6)
    entries = load()
    hit = False
    for e in entries:
        if e.ticker == ticker:
            e.status = status
            hit = True
    if hit:
        save(entries)
    return hit


def close(ticker: str) -> bool:
    return set_status(ticker, "closed")


# ─── 查询 ───────────────────────────────────────────────────────────────


def is_in_watchlist(ticker: str, only_pending: bool = True) -> bool:
    ticker = str(ticker).zfill(6)
    for e in load():
        if e.ticker == ticker:
            if only_pending and e.status != "pending":
                return False
            return True
    return False


def get_entry(ticker: str) -> WatchlistEntry | None:
    ticker = str(ticker).zfill(6)
    for e in load():
        if e.ticker == ticker:
            return e
    return None


def ticker_status_map(only_pending: bool = True) -> dict[str, str]:
    """批量查询:ticker → status,给 Top7/Top5 表用。"""
    out: dict[str, str] = {}
    for e in load():
        if only_pending and e.status != "pending":
            continue
        out[e.ticker] = e.status
    return out


# ─── 迁移 ───────────────────────────────────────────────────────────────


def migrate_from_md_if_needed() -> int:
    """yaml 不存在 + 旧 md 存在 → 解析 md 灌入 + md 改名 .bak。返回迁移条数。"""
    if WATCHLIST_YAML.exists():
        return 0
    if not LEGACY_MD.exists():
        return 0
    try:
        text = LEGACY_MD.read_text(encoding="utf-8")
    except Exception:
        return 0

    entries: list[WatchlistEntry] = []
    seen: set[str] = set()
    today = _today()
    line_re = re.compile(r"\*\*([^*]+)\*\*\s*\(\s*(\d{5,6})\s*\)")
    preset_re = re.compile(r"\)\s*[—-]\s*([^·\n]+?)\s*通过")
    date_re = re.compile(r"·\s*(\d{4}-\d{2}-\d{2})")
    score_re = re.compile(r"评分\s*([\d.]+)")

    for line in text.splitlines():
        if not line.strip().startswith("- ["):
            continue
        m = line_re.search(line)
        if not m:
            continue
        name = m.group(1).strip()
        ticker = m.group(2).zfill(6)
        if ticker in seen:
            continue
        preset_m = preset_re.search(line)
        date_m = date_re.search(line)
        score_m = score_re.search(line)
        is_closed = line.lstrip("- ").startswith("[x]")
        entries.append(WatchlistEntry(
            ticker=ticker,
            name=name,
            added_at=(date_m.group(1) if date_m else today),
            preset=(preset_m.group(1).strip() if preset_m else "迁移自 md"),
            score=_to_float(score_m.group(1)) if score_m else None,
            status=("closed" if is_closed else "pending"),
        ))
        seen.add(ticker)

    if not entries:
        # md 是空模板 → 也归档掉,避免每次再触发
        try:
            LEGACY_MD.rename(LEGACY_MD.with_suffix(".md.bak"))
        except Exception:
            pass
        return 0

    save(entries)
    try:
        LEGACY_MD.rename(LEGACY_MD.with_suffix(".md.bak"))
    except Exception:
        pass
    return len(entries)


__all__ = [
    "WatchlistEntry",
    "WATCHLIST_YAML",
    "load", "save", "add", "remove",
    "set_status", "close",
    "is_in_watchlist", "get_entry", "ticker_status_map",
    "migrate_from_md_if_needed",
]
