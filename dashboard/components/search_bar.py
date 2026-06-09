"""全局公司搜索栏(候选 ⑩ · v2.4 step-B)。

支持:股票代码 / 中文名 / 拼音首字母 / 行业关键词。
优先级降序匹配 + rapidfuzz 模糊兜底。

数据源:`.config/companies.csv` 的 L3 自选 15 家。
扩展位:候选 ⑨ Phase 2 落地后 L2 fallback(`search_l2_fallback`)启用。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypinyin import Style, lazy_pinyin
from rapidfuzz import fuzz


@dataclass(frozen=True)
class CompanyEntry:
    folder: str
    ticker: str
    name: str
    category: str
    industry: str
    industry_l2: str
    pinyin_full: str
    pinyin_initials: str


@dataclass(frozen=True)
class SearchHit:
    entry: CompanyEntry
    score: int
    matched_field: str


def _pinyin_of(text: str) -> tuple[str, str]:
    full = "".join(lazy_pinyin(text)).lower()
    initials = "".join(lazy_pinyin(text, style=Style.FIRST_LETTER)).lower()
    return full, initials


def load_index(csv_path: Path) -> list[CompanyEntry]:
    """从 companies.csv 构建搜索索引。"""
    rows: list[CompanyEntry] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            full, initials = _pinyin_of(name)
            rows.append(
                CompanyEntry(
                    folder=(r.get("folder") or "").strip(),
                    ticker=(r.get("stock") or "").strip(),
                    name=name,
                    category=(r.get("category") or "").strip(),
                    industry=(r.get("industry") or "").strip(),
                    industry_l2=(r.get("industry_l2") or "").strip(),
                    pinyin_full=full,
                    pinyin_initials=initials,
                )
            )
    return rows


def _norm_ticker(t: str) -> str:
    """规范化 ticker:去前导零(港股 '02097' / A 股 '000333' 等价于 '2097' / '333')。

    与 DuckDB 历史存储口径一致:数字串走 int 去零,非数字保持原样。
    """
    if not t:
        return t
    s = t.strip()
    if not s:
        return s
    try:
        return s.zfill(6) if len(s) >= 5 else s
    except (ValueError, TypeError):
        return s


def _match_one(q: str, e: CompanyEntry) -> tuple[int, str] | None:
    """返回 (score, matched_field) 或 None。score 越高越靠前。"""
    if not q:
        return None
    # ticker 规范化对比:支持 '02097' 命中 '2097'、'000333' 命中 '333'
    q_norm = _norm_ticker(q)
    t_norm = _norm_ticker(e.ticker)
    if q == e.ticker or (q_norm == t_norm and q_norm.isdigit()):
        return 100, "ticker"
    if q == e.name:
        return 95, "name"
    if e.ticker.startswith(q) or (q_norm.isdigit() and t_norm.startswith(q_norm)):
        return 85, "ticker"
    if e.name.startswith(q):
        return 80, "name"
    if q == e.pinyin_initials:
        return 75, "pinyin"
    if e.pinyin_initials.startswith(q):
        return 70, "pinyin"
    if e.pinyin_full.startswith(q):
        return 65, "pinyin"
    if q == e.industry_l2 or q == e.industry:
        return 60, "industry"
    if q in e.industry_l2 or q in e.industry:
        return 55, "industry"
    if q in e.name:
        return 50, "name"
    if q in e.pinyin_full or q in e.pinyin_initials:
        return 45, "pinyin"
    return None


def _fuzzy_score(q: str, e: CompanyEntry) -> int | None:
    """rapidfuzz 模糊兜底。

    - WRatio 跨长度更稳健,避免 partial_ratio 在短拼音上的高噪声(zgzc vs zzzz=67%)
    - 阈值 75:实测垃圾串 < 60,真错字 75-90,弱关联 60-75
    """
    candidates = (e.name, e.pinyin_full, e.pinyin_initials, e.industry_l2)
    best = max(fuzz.WRatio(q, c) for c in candidates if c)
    if best >= 75:
        # 把 75-100 的 WRatio 分映射到 30-44(低于硬规则,作为兜底)
        return int(30 + (best - 75) * 14 / 25)
    return None


def search(query: str, index: Iterable[CompanyEntry], limit: int = 10) -> list[SearchHit]:
    """优先级降序匹配。空 query 返回 []。

    1. 硬规则匹配(_match_one,score 45-100)
    2. 无命中则 rapidfuzz 兜底(score 30-44)
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    hits: list[SearchHit] = []
    seen: set[str] = set()
    for e in index:
        m = _match_one(q, e)
        if m is None:
            continue
        score, field = m
        hits.append(SearchHit(entry=e, score=score, matched_field=field))
        seen.add(e.folder)

    if not hits:
        for e in index:
            if e.folder in seen:
                continue
            f = _fuzzy_score(q, e)
            if f is None:
                continue
            hits.append(SearchHit(entry=e, score=f, matched_field="fuzzy"))
            seen.add(e.folder)

    hits.sort(key=lambda h: (-h.score, h.entry.folder))
    return hits[:limit]


def search_folders(query: str, index: Iterable[CompanyEntry], limit: int = 10) -> list[str]:
    """便捷封装:只返回 folder 列表。"""
    return [h.entry.folder for h in search(query, index, limit=limit)]


def search_l2_fallback(query: str, limit: int = 10) -> list[dict]:
    """L2 行业代表池兜底搜索 — 候选 ⑨ Phase 2 落地后启用。

    当前 L3 命中 < 5 时调用,失败静默(market.duckdb 可能尚未落地)。
    """
    try:
        import duckdb  # noqa: WPS433
    except ImportError:
        return []
    db_path = Path(__file__).resolve().parents[3] / "data" / "market.duckdb"
    if not db_path.exists():
        return []
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        # TODO(候选 ⑨ Phase 2):industry_pool 表落地后,在此实现 ticker / name / industry 三字段 LIKE
        con.close()
    except Exception:
        return []
    return []


class CompanySearcher:
    """高层封装:一次性构建索引,后续 search() 复用。"""

    def __init__(self, csv_path: Path | str | None = None):
        if csv_path is None:
            root = Path(__file__).resolve().parents[3]
            csv_path = root / ".config" / "companies.csv"
        self.csv_path = Path(csv_path)
        self.index: list[CompanyEntry] = load_index(self.csv_path) if self.csv_path.exists() else []

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """返回 [{ticker, name, folder, industry, industry_l2, score, matched_field}, ...]。"""
        hits = search(query, self.index, limit=limit)
        if len(hits) < 5:
            # 预留 L2 fallback,当前是 no-op
            search_l2_fallback(query, limit=limit - len(hits))
        return [
            {
                "ticker": h.entry.ticker,
                "name": h.entry.name,
                "folder": h.entry.folder,
                "industry": h.entry.industry,
                "industry_l2": h.entry.industry_l2,
                "score": h.score,
                "matched_field": h.matched_field,
            }
            for h in hits
        ]

    def search_folders(self, query: str, limit: int = 10) -> list[str]:
        return [h["folder"] for h in self.search(query, limit=limit)]


def render_search_bar(searcher: CompanySearcher, key: str = "global_search") -> str | None:
    """Streamlit 入口:画搜索框,返回当前 query 字符串(空字符串 = 未输入)。

    命中后调用方根据 searcher.search_folders(query) 决定 selectbox options。
    """
    import streamlit as st  # 延迟 import:核心模块离线可测

    return st.text_input(
        "🔍 搜索",
        placeholder="代码 / 名称 / 拼音 / 行业,如 gzmt · 茅台 · 白酒",
        key=key,
        label_visibility="collapsed",
    )
