"""Smart Streamlit dataframe helpers.

This module is intentionally opt-in: pages can adopt ``render_smart_dataframe``
one table at a time without changing the existing dashboard flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd


_MISSING_TEXT = "-"

_LABELS: dict[str, str] = {
    "ticker": "代码",
    "stock": "代码",
    "symbol": "代码",
    "code": "代码",
    "name": "名称",
    "company": "公司",
    "company_name": "公司",
    "short_name": "简称",
    "industry": "行业",
    "sector": "板块",
    "category": "分类",
    "date": "日期",
    "trade_date": "交易日",
    "report_date": "报告期",
    "period": "期间",
    "year": "年份",
    "quarter": "季度",
    "score": "评分",
    "rank": "排名",
    "rating": "评级",
    "pe": "PE",
    "pe_ttm": "PE(TTM)",
    "pb": "PB",
    "ps": "PS",
    "ps_ttm": "PS(TTM)",
    "peg": "PEG",
    "roe": "ROE",
    "roa": "ROA",
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "dividend_yield": "股息率",
    "market_cap": "市值",
    "revenue": "营收",
    "net_profit": "净利润",
    "profit": "利润",
    "cash_flow": "现金流",
    "free_cash_flow": "自由现金流",
    "debt_ratio": "资产负债率",
    "percentile": "分位点",
}

_PRIORITY_HINTS = (
    "name",
    "company",
    "ticker",
    "stock",
    "code",
    "industry",
    "category",
    "date",
    "trade_date",
    "report_date",
    "score",
    "rank",
    "rating",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "peg",
    "roe",
    "roa",
    "percentile",
    "dividend_yield",
    "market_cap",
)


@dataclass(frozen=True)
class ColumnKind:
    """Column display intent inferred from name and dtype."""

    label: str
    kind: str
    fraction_percent: bool = False


def format_percentile(value: Any) -> str:
    """Format percentile values as friendly Chinese text."""
    number = _to_float(value)
    if number is None:
        return _MISSING_TEXT
    if 0 <= number <= 1:
        number *= 100
    return f"{number:.1f}%"


def format_value(value: Any, *, kind: str | None = None) -> str:
    """Format a scalar value using the same rough rules as smart tables."""
    number = _to_float(value)
    if number is None:
        if isinstance(value, (date, datetime, pd.Timestamp)):
            return pd.Timestamp(value).strftime("%Y-%m-%d")
        return _MISSING_TEXT if pd.isna(value) else str(value)

    if kind in {"percent", "percentile"}:
        if 0 <= number <= 1:
            number *= 100
        return f"{number:.1f}%"
    if kind == "money":
        return _format_money(number)
    if kind == "score":
        return f"{number:.1f}"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:.2f}"


def prepare_display_df(
    df: pd.DataFrame,
    max_default_cols: int | None = None,
    priority_cols: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Return a display-safe copy with useful columns first.

    Numeric columns stay numeric so Streamlit sorting/filtering continues to
    work. Percent-like columns stored as 0-100 are converted to 0-1 in the copy
    because Streamlit's percent format expects a fraction.
    """
    if df is None:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    for column in out.columns:
        kind = infer_column_kind(out[column], column)
        if kind.fraction_percent:
            out[column] = pd.to_numeric(out[column], errors="coerce") / 100
        elif kind.kind == "date":
            out[column] = pd.to_datetime(out[column], errors="coerce")

    ordered = _ordered_columns(list(out.columns), priority_cols)
    if max_default_cols is not None and max_default_cols > 0:
        ordered = ordered[:max_default_cols]
    return out.loc[:, ordered]


def infer_column_config(df: pd.DataFrame) -> dict[str, Any]:
    """Infer Streamlit column config for common investment dashboard columns."""
    return build_column_config(df)


def build_column_config(df: pd.DataFrame) -> dict[str, Any]:
    """Build ``st.dataframe`` column_config with Chinese labels and formats."""
    import streamlit as st

    if df is None:
        return {}

    config: dict[str, Any] = {}
    for column in df.columns:
        series = df[column]
        inferred = infer_column_kind(series, column)
        label = inferred.label

        if inferred.kind in {"date", "datetime"}:
            config[column] = st.column_config.DateColumn(label, format="YYYY-MM-DD")
        elif inferred.kind == "percentile":
            config[column] = st.column_config.ProgressColumn(
                label,
                format="percent",
                min_value=0,
                max_value=1,
            )
        elif inferred.kind == "percent":
            config[column] = st.column_config.NumberColumn(label, format="percent")
        elif inferred.kind == "money":
            config[column] = st.column_config.NumberColumn(label, format="%.2f")
        elif inferred.kind == "score":
            config[column] = st.column_config.ProgressColumn(
                label,
                format="%.1f",
                min_value=0,
                max_value=_score_max(series),
            )
        elif inferred.kind == "integer":
            config[column] = st.column_config.NumberColumn(label, format="%d")
        elif inferred.kind == "number":
            config[column] = st.column_config.NumberColumn(label, format="%.2f")
        else:
            config[column] = st.column_config.TextColumn(label)
    return config


def render_smart_dataframe(
    st: Any,
    df: pd.DataFrame,
    *,
    hide_index: bool = True,
    width: str | int = "stretch",
    priority_cols: list[str] | tuple[str, ...] | None = None,
    height: int | None = None,
    max_default_cols: int | None = None,
) -> Any:
    """Render a dataframe with preson defaults and inferred column formatting."""
    display_df = prepare_display_df(
        df,
        max_default_cols=max_default_cols,
        priority_cols=priority_cols,
    )
    kwargs: dict[str, Any] = {
        "hide_index": hide_index,
        "column_config": build_column_config(display_df),
    }
    if height is not None:
        kwargs["height"] = height
    _apply_width_kwarg(kwargs, width)
    return st.dataframe(display_df, **kwargs)


def infer_column_kind(series: pd.Series, column: str) -> ColumnKind:
    """Infer display type for one dataframe column."""
    key = _normalize(column)
    label = _label_for(column, key)
    dtype = series.dtype

    if _is_date_key(key) or pd.api.types.is_datetime64_any_dtype(dtype):
        return ColumnKind(label, "date")
    if _is_percentile_key(key):
        return ColumnKind(
            _percentile_label(column, key),
            "percentile",
            _should_scale_100_to_1(series),
        )
    if _is_percent_key(key):
        return ColumnKind(label, "percent", _should_scale_100_to_1(series))
    if _is_money_key(key):
        return ColumnKind(label, "money")
    if _is_score_key(key):
        return ColumnKind(label, "score")
    if pd.api.types.is_integer_dtype(dtype) and _is_rank_key(key):
        return ColumnKind(label, "integer")
    if pd.api.types.is_numeric_dtype(dtype):
        return ColumnKind(label, "number")
    return ColumnKind(label, "text")


def _apply_width_kwarg(kwargs: dict[str, Any], width: str | int) -> None:
    if width == "stretch":
        kwargs["width"] = "stretch"
    elif isinstance(width, int):
        kwargs["width"] = width
    elif width not in {None, "auto"}:
        kwargs["width"] = "stretch"


def _ordered_columns(
    columns: list[str],
    priority_cols: list[str] | tuple[str, ...] | None,
) -> list[str]:
    requested = list(priority_cols or [])
    requested_keys = {_normalize(col) for col in requested}
    out: list[str] = []

    for wanted in requested:
        match = _find_column(columns, wanted)
        if match and match not in out:
            out.append(match)

    for hint in _PRIORITY_HINTS:
        if hint in requested_keys:
            continue
        match = _find_column(columns, hint)
        if match and match not in out:
            out.append(match)

    out.extend(col for col in columns if col not in out)
    return out


def _find_column(columns: list[str], wanted: str) -> str | None:
    wanted_key = _normalize(wanted)
    for column in columns:
        if _normalize(column) == wanted_key:
            return column
    for column in columns:
        key = _normalize(column)
        if wanted_key in key or key in wanted_key:
            return column
    return None


def _label_for(column: str, key: str) -> str:
    if key in _LABELS:
        return _LABELS[key]
    for hint, label in _LABELS.items():
        if hint and hint in key:
            return label
    return str(column).replace("_", " ")


def _percentile_label(column: str, key: str) -> str:
    base_key = key
    for token in ("percentile", "quantile", "分位点", "分位", "百分位"):
        base_key = base_key.replace(token, "")
    base_key = base_key.strip("_")
    base_label = _label_for(column, base_key) if base_key else ""
    if base_label and base_label != str(column).replace("_", " "):
        return f"{base_label}分位点"
    return "分位点"


def _normalize(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("（", "_")
        .replace("）", "_")
        .replace("(", "_")
        .replace(")", "_")
    )


def _is_date_key(key: str) -> bool:
    return any(part in key for part in ("date", "日期", "交易日", "报告期"))


def _is_percentile_key(key: str) -> bool:
    return any(part in key for part in ("percentile", "quantile", "分位", "百分位"))


def _is_percent_key(key: str) -> bool:
    hints = (
        "pct",
        "percent",
        "ratio",
        "rate",
        "yield",
        "margin",
        "roe",
        "roa",
        "growth",
        "增速",
        "增长",
        "率",
        "占比",
    )
    return _is_percentile_key(key) or any(part in key for part in hints)


def _is_money_key(key: str) -> bool:
    hints = (
        "amount",
        "market_cap",
        "mkt_cap",
        "revenue",
        "profit",
        "income",
        "cash",
        "资产",
        "市值",
        "营收",
        "收入",
        "利润",
        "现金",
        "金额",
    )
    return any(part in key for part in hints)


def _is_score_key(key: str) -> bool:
    return any(part in key for part in ("score", "评分", "得分"))


def _is_rank_key(key: str) -> bool:
    return any(part in key for part in ("rank", "排名", "序号"))


def _should_scale_100_to_1(series: pd.Series) -> bool:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return False
    lower = values.quantile(0.05)
    upper = values.quantile(0.95)
    return bool(lower >= -100 and 1.5 < upper <= 100)


def _score_max(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return 100.0
    upper = float(values.quantile(0.95))
    if upper <= 5:
        return 5.0
    if upper <= 10:
        return 10.0
    return 100.0


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_money(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿"
    if abs_value >= 10_000:
        return f"{value / 10_000:.2f}万"
    return f"{value:,.2f}"
