"""tabs.industry.confirm · 行业确定(草稿落盘 + 已确认管理 + 一致性检查).

三段 UI:
  1. 本层已确认清单 — focus_industries.yaml 当前条目,可勾选删除(删前预演 orphan 警告)
  2. 待确认草稿     — funnel.session 中 FUNNEL_INDUSTRY_DRAFT,点「确认新增」落盘
  3. 一致性检查     — orphans.find_orphan_watchlist 列出留下的孤立股
  4. 末尾跳转       — 「→ 去选股」 navigation.goto(PAGE_SCREENER, sub_tab="初步筛选")

写入策略(避免大改 state.py):
  - 删除走 state.remove_focus
  - 新增走 state.add_focus,然后单独 yaml 读 → 给新增条目补 confirmed_at(YYYY-MM-DD)→ 写回
  - 删除二次确认走 session_state checkbox(在 streamlit 单 render 内是优雅且可行的)
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import streamlit as st
import yaml

_ROOT = Path(__file__).resolve().parents[4]
_FOCUS_YAML = _ROOT / ".config" / "focus_industries.yaml"


# ─── yaml 工具 ────────────────────────────────────────────────────────


def _load_focus_yaml() -> dict:
    if not _FOCUS_YAML.exists():
        return {"focus": [], "top_n": 7, "market_cap_min": 5_000_000_000}
    return yaml.safe_load(_FOCUS_YAML.read_text(encoding="utf-8")) or {}


def _write_focus_yaml(payload: dict) -> None:
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    _FOCUS_YAML.write_text(text, encoding="utf-8")


def _stamp_confirmed_at(industries: list[str], date_str: str | None = None) -> int:
    """给 focus_industries.yaml 中指定行业补 confirmed_at;返回更新条数。"""
    if not industries:
        return 0
    d = _load_focus_yaml()
    rows = list(d.get("focus") or [])
    today = date_str or _dt.date.today().strftime("%Y-%m-%d")
    n = 0
    for r in rows:
        if r.get("industry") in industries and not r.get("confirmed_at"):
            r["confirmed_at"] = today
            n += 1
    d["focus"] = rows
    if n:
        _write_focus_yaml(d)
    return n


def _preview_orphans_after_removal(removed: set[str]) -> list[dict]:
    """预演删除某些行业后,watchlist 中新增的孤立股清单。"""
    try:
        from funnel import layers as _layers
        from funnel import orphans as _orphans
    except Exception:
        return []
    cur_focus = _layers.get_focus_names() or set()
    remaining = cur_focus - set(removed)
    return _orphans.find_orphan_watchlist(remaining)


# ─── 三段渲染 ────────────────────────────────────────────────────────


def _render_section_confirmed() -> None:
    st.markdown("### ① 本层已确认清单")
    try:
        from funnel import layers as _layers
    except Exception as e:
        st.error(f"funnel.layers 加载失败:{e}")
        return

    focus_list = list(_layers.get_focus_industries() or [])
    if not focus_list:
        st.info("尚未确认任何行业 — 到「🎯 行业预选」勾选,再回来确认")
        return

    show_note = any(f.get("note") for f in focus_list)
    col_weights = [0.4, 2, 1.2, 0.8, 1.5]
    if show_note:
        col_weights.insert(4, 1.5)

    hcols = st.columns(col_weights)
    hcols[0].markdown("**选**")
    hcols[1].markdown("**行业**")
    hcols[2].markdown("**type**")
    hcols[3].markdown("**weight**")
    if show_note:
        hcols[4].markdown("**note**")
        hcols[5].markdown("**确认日**")
    else:
        hcols[4].markdown("**确认日**")

    selected_for_remove: list[str] = []
    for f in focus_list:
        ind = f.get("industry")
        cols = st.columns(col_weights)
        chk = cols[0].checkbox(
            "选", value=False, key=f"confirmed_chk_{ind}", label_visibility="collapsed",
        )
        cols[1].markdown(f"**{ind}**")
        cols[2].markdown(f"`{f.get('type','—')}`")
        cols[3].markdown(f"{f.get('weight','—')}")
        if show_note:
            cols[4].markdown(f"{f.get('note') or '—'}")
            cols[5].markdown(f"{f.get('confirmed_at','—')}")
        else:
            cols[4].markdown(f"{f.get('confirmed_at','—')}")
        if chk:
            selected_for_remove.append(ind)

    if not selected_for_remove:
        return

    # 删除预演
    new_orphans = _preview_orphans_after_removal(set(selected_for_remove))

    btn_cols = st.columns([2, 1])
    with btn_cols[0]:
        if new_orphans:
            st.warning(
                f"⚠️ 删除后将留下 **{len(new_orphans)}** 只孤立观察股,可在「选股确定」中手动删除:\n\n"
                + "\n".join(
                    f"- `{o['ticker']}` {o['name']}(行业 [{o['industry'] or '?'}])"
                    for o in new_orphans[:10]
                )
                + (f"\n- … 还有 {len(new_orphans) - 10} 只" if len(new_orphans) > 10 else "")
            )
            ack = st.checkbox("我已知晓上述孤立股", key="confirm_remove_ack")
        else:
            ack = True
            st.caption("✅ 删除后无新增孤立股,可直接删除")

    with btn_cols[1]:
        if st.button("🗑️ 删除选中", disabled=not ack, use_container_width=True,
                     key="confirm_remove_btn"):
            try:
                import state as _state
                removed = 0
                for ind in selected_for_remove:
                    if _state.remove_focus(ind):
                        removed += 1
                st.success(f"✅ 已删除 {removed} 个行业")
                # 清掉孤立股复选 + 二次确认
                for ind in selected_for_remove:
                    st.session_state.pop(f"confirmed_chk_{ind}", None)
                st.session_state.pop("confirm_remove_ack", None)
                _layers._clear_cache()
                st.rerun()
            except Exception as e:
                st.error(f"删除失败:{e}")


def _render_section_draft() -> None:
    st.markdown("### ② 待确认草稿")
    try:
        from funnel import session as _session
        from funnel import layers as _layers
    except Exception as e:
        st.error(f"funnel 加载失败:{e}")
        return

    draft = list(_session.get_draft(_session.FUNNEL_INDUSTRY_DRAFT, []) or [])
    if not draft:
        st.info("草稿为空 — 切到「🎯 行业预选」勾选行业")
        return

    import pandas as pd
    show = pd.DataFrame(draft)
    st.dataframe(show, hide_index=True, use_container_width=True)

    if st.button("✅ 确认新增", type="primary", key="confirm_add_btn"):
        try:
            import state as _state
            added = []
            skipped = []
            for d in draft:
                ind = d.get("industry")
                t_ = d.get("type") or "stalwart"
                w = float(d.get("weight") or 1.0)
                note = d.get("note") or ""
                if not ind:
                    continue
                if _state.add_focus(ind, t_, weight=w, note=note or None):
                    added.append(ind)
                else:
                    skipped.append(ind)
            if added:
                _stamp_confirmed_at(added)
            # 清草稿
            _session.clear_draft(_session.FUNNEL_INDUSTRY_DRAFT)
            _layers._clear_cache()
            msg = f"✅ 新增 {len(added)} 个"
            if skipped:
                msg += f",跳过 {len(skipped)} 个已存在"
            st.success(msg)
            st.rerun()
        except Exception as e:
            st.error(f"落盘失败:{e}")


def _render_section_consistency() -> None:
    st.markdown("### ③ 一致性检查")
    try:
        from funnel import layers as _layers
        from funnel import orphans as _orphans
    except Exception as e:
        st.error(f"funnel 加载失败:{e}")
        return

    focus_names = _layers.get_focus_names() or set()
    orphan_list = _orphans.find_orphan_watchlist(focus_names) or []

    if not orphan_list:
        st.success("✅ 无孤立观察股 — focus 行业覆盖完整")
        return

    st.warning(f"⚠️ watchlist 中有 **{len(orphan_list)}** 只孤立股(行业不在 focus):")
    import pandas as pd
    show = pd.DataFrame(orphan_list)
    st.dataframe(show, hide_index=True, use_container_width=True)


def _render_nav_to_screener() -> None:
    st.markdown("---")
    cols = st.columns([3, 1])
    cols[0].caption("行业确定后 → 进入候选公司初步筛选")
    with cols[1]:
        if st.button("→ 去选股", type="primary", use_container_width=True, key="confirm_goto_screener"):
            try:
                from navigation import goto, PAGE_SCREENER, SUB_SCREENER_PRELIM
                goto(PAGE_SCREENER, sub_tab=SUB_SCREENER_PRELIM)
            except Exception as e:
                st.error(f"跳转失败:{e}")


def render() -> None:
    st.markdown("## ✅ 行业确定")
    _render_section_confirmed()
    st.markdown("---")
    _render_section_draft()
    st.markdown("---")
    _render_section_consistency()
    _render_nav_to_screener()


__all__ = ["render", "_stamp_confirmed_at", "_preview_orphans_after_removal"]
