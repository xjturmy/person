"""统一错误类型 + 时效字段工具。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


class MCPError(Exception):
    """MCP 工具层基础异常,带稳定的 code 标签。"""

    code: str = "ERROR"

    def __init__(self, message: str, **fields: Any) -> None:
        super().__init__(message)
        self.message = message
        self.fields = fields

    def to_text(self) -> str:
        head = f"❌ [{self.code}] {self.message}"
        if not self.fields:
            return head
        body = "\n".join(f"  - {k}: {v}" for k, v in self.fields.items())
        return f"{head}\n{body}"


class TickerNotFound(MCPError):
    code = "TICKER_NOT_FOUND"


class MetricNotFound(MCPError):
    code = "METRIC_NOT_FOUND"


class NoData(MCPError):
    code = "NO_DATA"


class BadArgument(MCPError):
    code = "BAD_ARGUMENT"


def freshness(latest_date: date | datetime | str | None) -> dict:
    """返回 {latest_date, lag_days, freshness} 元数据。"""
    if latest_date is None:
        return {"latest_date": None, "lag_days": None, "freshness": "unknown"}
    if isinstance(latest_date, str):
        d = datetime.strptime(latest_date, "%Y-%m-%d").date()
    elif isinstance(latest_date, datetime):
        d = latest_date.date()
    else:
        d = latest_date

    lag = (date.today() - d).days
    if lag <= 3:
        tag = "fresh"
    elif lag <= 14:
        tag = "stale"
    elif lag <= 60:
        tag = "very_stale"
    else:
        tag = "outdated"
    return {
        "latest_date": d.strftime("%Y-%m-%d"),
        "lag_days": lag,
        "freshness": tag,
    }


def freshness_badge(meta: dict) -> str:
    """生成一行可读的时效提示。"""
    lag = meta.get("lag_days")
    if lag is None:
        return "⚠️ 数据时效:未知"
    tag = meta["freshness"]
    icon = {"fresh": "🟢", "stale": "🟡", "very_stale": "🟠", "outdated": "🔴"}[tag]
    return f"{icon} 数据时效:{meta['latest_date']}(滞后 {lag} 天)"
