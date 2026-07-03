"""Preson investment dashboard UI primitives.

This module provides a small, conservative visual system for Streamlit pages:
semantic colors, section headers, metric cards, badges, compact notes, and a
density toggle. Imports are side-effect free; CSS is injected only when called.
"""
from __future__ import annotations

from html import escape
from typing import Literal, TypedDict


Status = Literal[
    "undervalued",
    "fair",
    "overvalued",
    "risk",
    "info",
    "disabled",
    "neutral",
    "success",
    "warning",
]


class SemanticColor(TypedDict):
    fg: str
    bg: str
    border: str
    accent: str
    label: str


_STATUS_ALIASES = {
    "低估": "undervalued",
    "便宜": "undervalued",
    "合理": "fair",
    "中性": "neutral",
    "高估": "overvalued",
    "偏贵": "overvalued",
    "风险": "risk",
    "警示": "risk",
    "信息": "info",
    "提示": "info",
    "禁用": "disabled",
    "无数据": "disabled",
    "neutral": "neutral",
    "undervalued": "undervalued",
    "fair": "fair",
    "overvalued": "overvalued",
    "risk": "risk",
    "info": "info",
    "disabled": "disabled",
    "success": "success",
    "warning": "warning",
}


SEMANTIC_COLORS: dict[str, SemanticColor] = {
    "undervalued": {
        "fg": "#166534",
        "bg": "#ECFDF3",
        "border": "#BBF7D0",
        "accent": "#16A34A",
        "label": "低估",
    },
    "fair": {
        "fg": "#365314",
        "bg": "#F7FEE7",
        "border": "#D9F99D",
        "accent": "#65A30D",
        "label": "合理",
    },
    "overvalued": {
        "fg": "#92400E",
        "bg": "#FFFBEB",
        "border": "#FDE68A",
        "accent": "#D97706",
        "label": "高估",
    },
    "risk": {
        "fg": "#991B1B",
        "bg": "#FEF2F2",
        "border": "#FECACA",
        "accent": "#DC2626",
        "label": "风险",
    },
    "info": {
        "fg": "#1E3A8A",
        "bg": "#EFF6FF",
        "border": "#BFDBFE",
        "accent": "#2563EB",
        "label": "信息",
    },
    "disabled": {
        "fg": "#6B7280",
        "bg": "#F3F4F6",
        "border": "#E5E7EB",
        "accent": "#9CA3AF",
        "label": "禁用",
    },
    "neutral": {
        "fg": "#374151",
        "bg": "#F9FAFB",
        "border": "#E5E7EB",
        "accent": "#6B7280",
        "label": "中性",
    },
    "success": {
        "fg": "#166534",
        "bg": "#F0FDF4",
        "border": "#BBF7D0",
        "accent": "#15803D",
        "label": "良好",
    },
    "warning": {
        "fg": "#854D0E",
        "bg": "#FEFCE8",
        "border": "#FEF08A",
        "accent": "#CA8A04",
        "label": "关注",
    },
}


INVEST_UI_CSS = """
<style>
:root {
  --preson-text: #111827;
  --preson-muted: #6B7280;
  --preson-subtle: #9CA3AF;
  --preson-border: #E5E7EB;
  --preson-border-strong: #D1D5DB;
  --preson-surface: #FFFFFF;
  --preson-surface-soft: #F9FAFB;
  --preson-accent: #1F6FEB;
  --preson-radius: 8px;
  --preson-shadow: 0 1px 2px rgba(17, 24, 39, 0.05);
}

.invest-section-header {
  border-bottom: 1px solid var(--preson-border);
  margin: 20px 0 12px;
  padding: 0 0 10px;
}

.invest-section-eyebrow {
  color: var(--preson-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.3;
  margin-bottom: 4px;
  text-transform: uppercase;
}

.invest-section-title {
  color: var(--preson-text);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0;
}

.invest-section-subtitle {
  color: var(--preson-muted);
  font-size: 13px;
  line-height: 1.55;
  margin-top: 5px;
}

.invest-metric-card {
  background: var(--preson-surface);
  border: 1px solid var(--card-border, var(--preson-border));
  border-left: 3px solid var(--card-accent, var(--preson-accent));
  border-radius: var(--preson-radius);
  box-shadow: var(--preson-shadow);
  min-height: 94px;
  padding: 12px 14px;
}

.invest-metric-label {
  color: var(--preson-muted);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  margin-bottom: 8px;
}

.invest-metric-value {
  color: var(--preson-text);
  font-size: 24px;
  font-weight: 750;
  letter-spacing: 0;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.invest-metric-note {
  color: var(--card-fg, var(--preson-muted));
  font-size: 12px;
  line-height: 1.4;
  margin-top: 8px;
}

.invest-signal-badge {
  align-items: center;
  background: var(--badge-bg, var(--preson-surface-soft));
  border: 1px solid var(--badge-border, var(--preson-border));
  border-radius: 999px;
  color: var(--badge-fg, var(--preson-muted));
  display: inline-flex;
  font-size: 12px;
  font-weight: 650;
  gap: 6px;
  line-height: 1;
  padding: 5px 9px;
  white-space: nowrap;
}

.invest-signal-dot {
  background: var(--badge-accent, var(--preson-subtle));
  border-radius: 999px;
  display: inline-block;
  height: 6px;
  width: 6px;
}

.invest-compact-note {
  background: var(--note-bg, var(--preson-surface-soft));
  border: 1px solid var(--note-border, var(--preson-border));
  border-radius: var(--preson-radius);
  color: var(--note-fg, var(--preson-muted));
  font-size: 13px;
  line-height: 1.55;
  margin: 10px 0;
  padding: 9px 11px;
}

.invest-density-compact .invest-metric-card {
  min-height: 78px;
  padding: 10px 12px;
}

.invest-density-compact .invest-metric-value {
  font-size: 21px;
}

.invest-density-compact .invest-section-header {
  margin-top: 14px;
  padding-bottom: 8px;
}
</style>
"""


def normalize_status(status: str | None = "neutral") -> str:
    """Return the canonical semantic status name."""
    if not status:
        return "neutral"
    return _STATUS_ALIASES.get(str(status).strip(), "neutral")


def semantic_color(status: str | None = "neutral") -> SemanticColor:
    """Return the semantic color token set for a status."""
    return SEMANTIC_COLORS[normalize_status(status)]


def status_label(status: str | None = "neutral") -> str:
    """Return the Chinese display label for a status."""
    return semantic_color(status)["label"]


def _style_vars(prefix: str, colors: SemanticColor) -> str:
    return (
        f"--{prefix}-fg:{colors['fg']};"
        f"--{prefix}-bg:{colors['bg']};"
        f"--{prefix}-border:{colors['border']};"
        f"--{prefix}-accent:{colors['accent']};"
    )


def inject_invest_ui_css() -> None:
    """Inject the investment UI stylesheet once per Streamlit session."""
    import streamlit as st

    key = "_preson_invest_ui_css_injected"
    if st.session_state.get(key):
        return
    st.session_state[key] = True
    st.markdown(INVEST_UI_CSS, unsafe_allow_html=True)


def section_header_html(
    title: str,
    subtitle: str | None = None,
    eyebrow: str | None = None,
) -> str:
    """Build section header HTML without rendering it."""
    eyebrow_html = (
        f'<div class="invest-section-eyebrow">{escape(eyebrow)}</div>'
        if eyebrow
        else ""
    )
    subtitle_html = (
        f'<div class="invest-section-subtitle">{escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    return (
        '<div class="invest-section-header">'
        f"{eyebrow_html}"
        f'<h3 class="invest-section-title">{escape(title)}</h3>'
        f"{subtitle_html}"
        "</div>"
    )


def render_section_header(
    title: str,
    subtitle: str | None = None,
    eyebrow: str | None = None,
) -> None:
    """Render a restrained page section header."""
    import streamlit as st

    inject_invest_ui_css()
    st.markdown(
        section_header_html(title=title, subtitle=subtitle, eyebrow=eyebrow),
        unsafe_allow_html=True,
    )


def metric_card_html(
    label: str,
    value: object,
    note: str | None = None,
    status: str | None = "neutral",
) -> str:
    """Build a compact metric card HTML fragment."""
    colors = semantic_color(status)
    note_html = (
        f'<div class="invest-metric-note">{escape(note)}</div>'
        if note
        else ""
    )
    return (
        '<div class="invest-metric-card" '
        f'style="{_style_vars("card", colors)}">'
        f'<div class="invest-metric-label">{escape(label)}</div>'
        f'<div class="invest-metric-value">{escape(str(value))}</div>'
        f"{note_html}"
        "</div>"
    )


def render_metric_card(
    label: str,
    value: object,
    note: str | None = None,
    status: str | None = "neutral",
) -> None:
    """Render a compact metric card."""
    import streamlit as st

    inject_invest_ui_css()
    st.markdown(
        metric_card_html(label=label, value=value, note=note, status=status),
        unsafe_allow_html=True,
    )


def badge_html(label: str, status: str | None = "neutral") -> str:
    """Build a semantic status badge HTML fragment."""
    colors = semantic_color(status)
    return (
        '<span class="invest-signal-badge" '
        f'style="{_style_vars("badge", colors)}">'
        '<span class="invest-signal-dot"></span>'
        f"{escape(label)}"
        "</span>"
    )


def render_signal_badge(label: str, status: str | None = "neutral") -> None:
    """Render a semantic signal badge."""
    import streamlit as st

    inject_invest_ui_css()
    st.markdown(badge_html(label=label, status=status), unsafe_allow_html=True)


def compact_note_html(text: str, status: str | None = "info") -> str:
    """Build a quiet contextual note HTML fragment."""
    colors = semantic_color(status)
    return (
        '<div class="invest-compact-note" '
        f'style="{_style_vars("note", colors)}">'
        f"{escape(text)}"
        "</div>"
    )


def render_compact_note(text: str, status: str | None = "info") -> None:
    """Render a compact contextual note."""
    import streamlit as st

    inject_invest_ui_css()
    st.markdown(compact_note_html(text=text, status=status), unsafe_allow_html=True)


def render_density_toggle(
    key: str = "invest_ui_density",
    label: str = "紧凑密度",
    default: bool = False,
) -> bool:
    """Render a reusable density toggle and return whether compact mode is on.

    Pages can wrap their own HTML in ``<div class="invest-density-compact">``
    when this returns True.
    """
    import streamlit as st

    inject_invest_ui_css()
    return st.toggle(label, value=default, key=key)


__all__ = [
    "INVEST_UI_CSS",
    "SEMANTIC_COLORS",
    "Status",
    "badge_html",
    "compact_note_html",
    "inject_invest_ui_css",
    "metric_card_html",
    "normalize_status",
    "render_compact_note",
    "render_density_toggle",
    "render_metric_card",
    "render_section_header",
    "render_signal_badge",
    "section_header_html",
    "semantic_color",
    "status_label",
]
