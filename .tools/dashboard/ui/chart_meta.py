"""Lightweight chart metadata hints for Streamlit dashboards.

The helpers in this module are intentionally passive: importing them does not
touch Streamlit state, data files, or chart objects. Callers decide where to
place the returned HTML, usually below a chart title or above a chart body.
"""
from __future__ import annotations

from html import escape
from typing import Any


def _clean(value: Any) -> str | None:
    """Return a display-safe string, treating blank-ish values as absent."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chip(label: str, value: Any, *, subtle: bool = False) -> str:
    value_text = _clean(value)
    if value_text is None:
        return ""
    class_name = "preson-chart-meta__chip"
    if subtle:
        class_name += " preson-chart-meta__chip--subtle"
    return (
        f'<span class="{class_name}">'
        f'<span class="preson-chart-meta__label">{escape(label)}</span>'
        f'<span class="preson-chart-meta__value">{escape(value_text)}</span>'
        "</span>"
    )


def chart_meta_html(
    window: Any = None,
    source: Any = None,
    updated: Any = None,
    note: Any = None,
    estimate: bool = False,
) -> str:
    """Build a low-distraction HTML metadata strip for charts.

    Args:
        window: Data window, e.g. ``"近 10 年"`` or ``"TTM / 日频"``.
        source: Data source, e.g. ``"理杏仁"`` or ``"本地 DuckDB"``.
        updated: Last update timestamp or trading day.
        note: Optional short note about methodology or exceptions.
        estimate: Whether the chart uses estimated / derived values.

    Returns:
        A self-contained HTML string. Returns an empty string when no metadata
        was supplied and ``estimate`` is false.
    """
    has_explicit_meta = any(
        _clean(value) is not None for value in (window, source, updated, note)
    )
    chips = [
        _chip("窗口", window),
        _chip("来源", source),
        _chip("更新", updated),
    ]
    if estimate or has_explicit_meta:
        chips.append(_chip("口径", "估算" if estimate else "真实", subtle=not estimate))
    note_text = _clean(note)
    chip_html = "".join(chips)
    note_html = ""
    if note_text:
        note_html = (
            '<span class="preson-chart-meta__note">'
            f"{escape(note_text)}"
            "</span>"
        )

    if not chip_html and not note_html:
        return ""

    return f"""
<style>
.preson-chart-meta {{
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
  margin: -2px 0 6px;
  color: rgba(49, 51, 63, 0.62);
  font-size: 12px;
  line-height: 1.35;
}}
.preson-chart-meta__chip {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 22px;
  padding: 2px 7px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 6px;
  background: rgba(49, 51, 63, 0.035);
  white-space: nowrap;
}}
.preson-chart-meta__chip--subtle {{
  background: transparent;
}}
.preson-chart-meta__label {{
  color: rgba(49, 51, 63, 0.45);
}}
.preson-chart-meta__value {{
  color: rgba(49, 51, 63, 0.70);
  font-weight: 500;
}}
.preson-chart-meta__note {{
  max-width: min(100%, 520px);
  color: rgba(49, 51, 63, 0.54);
}}
</style>
<div class="preson-chart-meta" role="note" aria-label="图表口径与数据来源">
  {chip_html}{note_html}
</div>
""".strip()


def render_chart_meta(
    st: Any,
    window: Any = None,
    source: Any = None,
    updated: Any = None,
    note: Any = None,
    estimate: bool = False,
) -> None:
    """Render chart metadata with a provided Streamlit module/object."""
    html = chart_meta_html(
        window=window,
        source=source,
        updated=updated,
        note=note,
        estimate=estimate,
    )
    if html:
        st.markdown(html, unsafe_allow_html=True)


def wrap_chart_with_meta(
    st: Any,
    fig: Any,
    window: Any = None,
    source: Any = None,
    updated: Any = None,
    note: Any = None,
    estimate: bool = False,
    *,
    width: str | int = "stretch",
    plotly_chart_kwargs: dict[str, Any] | None = None,
) -> Any:
    """Render metadata followed by a Plotly figure without mutating the figure.

    This is a convenience wrapper for the common Streamlit pattern:
    ``render_chart_meta(...)`` then ``st.plotly_chart(fig, ...)``. Additional
    Plotly rendering options can be passed through ``plotly_chart_kwargs``.
    """
    render_chart_meta(
        st,
        window=window,
        source=source,
        updated=updated,
        note=note,
        estimate=estimate,
    )
    kwargs = dict(plotly_chart_kwargs or {})
    kwargs.setdefault("width", width)
    return st.plotly_chart(fig, **kwargs)


maybe_wrap_chart_with_meta = wrap_chart_with_meta


__all__ = [
    "chart_meta_html",
    "render_chart_meta",
    "wrap_chart_with_meta",
    "maybe_wrap_chart_with_meta",
]
