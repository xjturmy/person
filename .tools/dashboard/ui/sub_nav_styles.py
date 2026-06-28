"""Horizontal sub-navigation styling — larger labels for page-level sub-tabs."""
from __future__ import annotations

import streamlit as st

# Injected immediately before each sub-nav st.radio (see sub_nav_marker).
SUB_NAV_MARKER = '<div class="dash-sub-nav-bar" aria-hidden="true"></div>'

_SUB_NAV_CSS = """
<style>
/* 子模块顶栏:marker 后的第一个 radio 组 — 字号对齐侧边栏(16px) */
section.main div:has(> .dash-sub-nav-bar) + div [data-testid="stRadio"] label p {
  font-size: 16px !important;
  line-height: 1.6 !important;
  font-weight: 500 !important;
}

section.main div:has(> .dash-sub-nav-bar) + div [data-testid="stRadio"] > div > label {
  padding: 8px 16px !important;
  margin-right: 6px !important;
  border-radius: 8px;
  border: 1px solid rgba(128, 128, 128, 0.35);
  background: rgba(128, 128, 128, 0.08);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

section.main div:has(> .dash-sub-nav-bar) + div [data-testid="stRadio"] > div > label:has(input:checked) {
  background: #1f77b4 !important;
  border-color: #1f77b4 !important;
}

section.main div:has(> .dash-sub-nav-bar) + div [data-testid="stRadio"] > div > label:has(input:checked) p {
  color: white !important;
  font-weight: 600 !important;
}

section.main div:has(> .dash-sub-nav-bar) + div [data-testid="stRadio"] > div {
  gap: 4px;
  flex-wrap: wrap;
}
</style>
"""


def inject_sub_nav_styles() -> None:
    """Inject once per rerun."""
    st.markdown(_SUB_NAV_CSS, unsafe_allow_html=True)


def sub_nav_marker() -> None:
    """Place immediately before a horizontal sub-nav ``st.radio``."""
    st.markdown(SUB_NAV_MARKER, unsafe_allow_html=True)


__all__ = ["SUB_NAV_MARKER", "inject_sub_nav_styles", "sub_nav_marker"]
