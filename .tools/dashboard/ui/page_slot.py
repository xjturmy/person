"""Keyed page containers — prevent ghost DOM when switching tabs.

Streamlit may leave ``unsafe_allow_html`` blocks (e.g. industry overview tables)
visible after conditional sub-tab switches. A container whose ``key`` changes forces
a full remount of that subtree.
"""
from __future__ import annotations

import re

import streamlit as st


def _safe_key(part: str) -> str:
    return re.sub(r"[^\w\-]", "_", part)


def page_body(*parts: str) -> st.delta_generator.DeltaGenerator:
    """Return a keyed ``st.container`` for the active navigation slot."""
    slot = "_".join(_safe_key(p) for p in parts if p)
    return st.container(key=f"page_body_{slot}")


__all__ = ["page_body"]
