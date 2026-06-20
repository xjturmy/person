"""市场与行业 · 共享 session_state + focus_industries.yaml 读写薄包装.

集中三处散落:
  - st.session_state.sel_l1 / sel_l2  跨 tab 的选中 SW L1 / L2
  - focus_industries.yaml 增 / 删 / 读(去重 + 保留 top_n / market_cap_min)
  - 主索引 industry_master.yaml 的 name→meta 字典缓存

仅做轻量包装,不改 schema;复用 industry_focus 的渲染层不受影响.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[2]
FOCUS_YAML = ROOT / ".config" / "focus_industries.yaml"
INDUSTRY_MASTER_YAML = ROOT / ".config" / "industry_master.yaml"


# ─── 主索引 ──────────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def industry_master() -> dict[str, dict]:
    """name → 主索引条目 dict(yaml + companies.csv 合并;csv 出现的 L2 自动补全)."""
    from tabs.industry._master_loader import load_master_merged
    return load_master_merged()


def l2_under_l1(sw_l1: str) -> list[dict]:
    """返回 sw_l1 下的所有 L2 主索引条目(含 name / type / cycle_attrs / etf_codes / ...)."""
    out = []
    for item in (_load_yaml(INDUSTRY_MASTER_YAML).get("industries") or []):
        if (item.get("sw_l1") or "") == sw_l1:
            out.append(item)
    return out


# ─── focus_industries.yaml 读写 ──────────────────────────────────────────


def get_focus_list() -> list[dict]:
    cfg = _load_yaml(FOCUS_YAML)
    return list(cfg.get("focus") or [])


def get_focus_names() -> set[str]:
    return {f["industry"] for f in get_focus_list() if f.get("industry")}


def _write_focus(focus_rows: list[dict], cfg: dict) -> None:
    payload = {
        "focus": focus_rows,
        "top_n": int(cfg.get("top_n", 7)),
        "market_cap_min": int(cfg.get("market_cap_min", 5_000_000_000)),
    }
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    FOCUS_YAML.write_text(text, encoding="utf-8")


def add_focus(
    industry: str,
    type_: str | None = None,
    weight: float = 1.0,
    note: str | None = None,
) -> bool:
    """追加一个 L2 行业到 focus.yaml(去重);返回 True 表示新增,False 已存在."""
    cfg = _load_yaml(FOCUS_YAML)
    rows = list(cfg.get("focus") or [])
    if any(r.get("industry") == industry for r in rows):
        return False
    if type_ is None:
        type_ = (industry_master().get(industry) or {}).get("type", "stalwart")
    row: dict[str, Any] = {"industry": industry, "type": type_}
    if note:
        row["note"] = note
    rows.append(row)
    _write_focus(rows, cfg)
    return True


def remove_focus(industry: str) -> bool:
    cfg = _load_yaml(FOCUS_YAML)
    rows = list(cfg.get("focus") or [])
    new_rows = [r for r in rows if r.get("industry") != industry]
    if len(new_rows) == len(rows):
        return False
    _write_focus(new_rows, cfg)
    return True


# ─── session_state 选中 ──────────────────────────────────────────────────


def get_sel_l1() -> str | None:
    return st.session_state.get("sel_l1")


def set_sel_l1(v: str | None) -> None:
    st.session_state["sel_l1"] = v
    # 切 L1 自动清 L2,避免错位
    st.session_state["sel_l2"] = None


def get_sel_l2() -> str | None:
    return st.session_state.get("sel_l2")


def set_sel_l2(v: str | None) -> None:
    st.session_state["sel_l2"] = v


# ─── 离线自检 ────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import shutil
    bak = FOCUS_YAML.with_suffix(".yaml.selftest_bak")
    shutil.copy(FOCUS_YAML, bak)
    try:
        before = len(get_focus_list())
        added = add_focus("白酒")  # 已在则 False
        print(f"add 白酒 ->", added, "before/after:", before, len(get_focus_list()))
        if added:
            assert remove_focus("白酒")
        # 试一个不在的
        if add_focus("化学制品"):
            print("化学制品 added OK,now remove")
            assert remove_focus("化学制品")
        l2s = l2_under_l1("食品饮料")
        print(f"食品饮料下 L2: {[x['name'] for x in l2s]}")
        print("self-test OK")
    finally:
        shutil.move(bak, FOCUS_YAML)
