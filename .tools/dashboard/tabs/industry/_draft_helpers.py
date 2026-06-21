"""行业漏斗草稿 helper — 分析页「加入预选」与预选页共用."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[4]
DRAFT_YAML = _ROOT / ".config" / "industry_preselect_draft.yaml"


def _load_draft_file() -> list[dict]:
    if not DRAFT_YAML.exists():
        return []
    try:
        import yaml

        data = yaml.safe_load(DRAFT_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    rows = data.get("draft") or []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("industry"):
            continue
        out.append({
            "industry": str(r["industry"]),
            "type": str(r.get("type") or "stalwart"),
            "weight": float(r.get("weight") or 1.0),
            "note": str(r.get("note") or ""),
        })
    return out


def _save_draft_file(draft: list[dict]) -> None:
    import yaml

    DRAFT_YAML.parent.mkdir(parents=True, exist_ok=True)
    if DRAFT_YAML.exists():
        shutil.copy2(DRAFT_YAML, DRAFT_YAML.with_suffix(".yaml.bak"))

    payload = {"draft": draft}
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    fd, tmp = tempfile.mkstemp(
        prefix=".industry_preselect_draft.",
        suffix=".tmp",
        dir=str(DRAFT_YAML.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, DRAFT_YAML)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _clear_draft_file() -> None:
    if DRAFT_YAML.exists():
        DRAFT_YAML.unlink()


def set_industry_draft(draft: list[dict]) -> None:
    """写入 session + 落盘,刷新后仍可恢复勾选."""
    from funnel import session as _session

    _session.set_draft(_session.FUNNEL_INDUSTRY_DRAFT, draft)
    _save_draft_file(draft)


def clear_industry_draft() -> None:
    from funnel import session as _session

    _session.clear_draft(_session.FUNNEL_INDUSTRY_DRAFT)
    _clear_draft_file()


def get_industry_draft() -> list[dict]:
    from funnel import session as _session

    ss = _session._session_state()
    key = _session.FUNNEL_INDUSTRY_DRAFT
    if ss is not None and key in ss:
        return list(ss.get(key) or [])
    file_draft = _load_draft_file()
    if ss is not None:
        ss[key] = file_draft
    return file_draft


def industry_in_draft(industry: str) -> bool:
    return any(d.get("industry") == industry for d in get_industry_draft())


def add_industry_to_draft(
    industry: str,
    *,
    type_: str = "stalwart",
    weight: float = 1.0,
    note: str = "",
) -> bool:
    """追加行业到草稿;已 focus 或已在草稿中则返回 False."""
    if not industry:
        return False
    try:
        from funnel import layers as _layers

        if industry in (_layers.get_focus_names() or set()):
            return False
    except Exception:
        pass

    draft = get_industry_draft()
    if any(d.get("industry") == industry for d in draft):
        return False

    draft.append({
        "industry": industry,
        "type": type_,
        "weight": float(weight),
        "note": note or "",
    })
    set_industry_draft(draft)
    return True


def merge_draft_from_session_state(
    industry: str,
    *,
    type_: str,
    weight: float,
    note: str,
    checked: bool,
    draft_out: list[dict],
) -> None:
    """预选行渲染时合并单行到 draft_out(由 render 最后 set_draft)."""
    if checked:
        draft_out.append({
            "industry": industry,
            "type": type_,
            "weight": float(weight),
            "note": note or "",
        })


_COMPANIES_CSV = _ROOT / ".config" / "companies.csv"


def load_companies_l1_to_l2() -> dict[str, list[str]]:
    """companies.csv: SW L1 → 候选池内出现的 L2 列表."""
    if not _COMPANIES_CSV.exists():
        return {}
    import csv

    out: dict[str, set[str]] = {}
    with _COMPANIES_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            l1 = str(row.get("industry") or "").strip()
            l2 = str(row.get("industry_l2") or "").strip()
            if l1 and l2:
                out.setdefault(l1, set()).add(l2)
    return {k: sorted(v) for k, v in out.items()}


def build_l1_to_l2_map(
    master: dict[str, dict],
    *,
    include_companies: bool = True,
) -> dict[str, list[str]]:
    """sw_l1 → [L2 name, ...]; 合并 industry_master + companies 候选池."""
    out: dict[str, list[str]] = {}
    for name, meta in master.items():
        l1 = meta.get("sw_l1") or "—"
        out.setdefault(str(l1), []).append(str(name))
    if include_companies:
        for l1, l2s in load_companies_l1_to_l2().items():
            out[l1] = sorted(set(out.get(l1, [])) | set(l2s))
    for l1 in out:
        out[l1] = sorted(set(out[l1]))
    return out


def l1_marked_in_draft(l1: str, l1_to_l2: dict[str, list[str]], draft_inds: set[str]) -> bool:
    """L1 下任一 L2 已在草稿 → 表格勾选为 True."""
    l2s = l1_to_l2.get(l1) or []
    return any(l2 in draft_inds for l2 in l2s)


def sync_l1_table_selection(
    selected_l1s: set[str],
    l1_to_l2: dict[str, list[str]],
    master: dict[str, dict],
    *,
    table_l1_names: set[str],
    focus_names: set[str] | None = None,
) -> list[dict]:
    """L1 全景表勾选 → 同步 FUNNEL_INDUSTRY_DRAFT(L2 粒度).

    - 表格管辖的 L2: 随 L1 勾选增删
    - 非表格来源的草稿(如 L2 知识块「加入预选」): 保留
    """
    focus_names = focus_names or set()
    draft = get_industry_draft()
    table_managed_l2: set[str] = set()
    for l1 in table_l1_names:
        table_managed_l2.update(l1_to_l2.get(l1, []))

    should: set[str] = set()
    for l1 in selected_l1s:
        for l2 in l1_to_l2.get(l1, []):
            if l2 not in focus_names:
                should.add(l2)

    new_draft: list[dict] = []
    for d in draft:
        ind = d.get("industry")
        if not ind:
            continue
        if ind not in table_managed_l2:
            new_draft.append(d)
        elif ind in should:
            new_draft.append(d)

    existing = {d["industry"] for d in new_draft}
    for l2 in sorted(should):
        if l2 in existing:
            continue
        meta = master.get(l2, {})
        l1 = meta.get("sw_l1", "—")
        new_draft.append({
            "industry": l2,
            "type": meta.get("type", "stalwart"),
            "weight": 1.0,
            "note": f"全景·{l1}",
        })
        existing.add(l2)

    set_industry_draft(new_draft)
    return new_draft


__all__ = [
    "DRAFT_YAML",
    "get_industry_draft",
    "set_industry_draft",
    "clear_industry_draft",
    "industry_in_draft",
    "add_industry_to_draft",
    "merge_draft_from_session_state",
    "build_l1_to_l2_map",
    "load_companies_l1_to_l2",
    "l1_marked_in_draft",
    "sync_l1_table_selection",
]
