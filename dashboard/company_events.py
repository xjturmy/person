"""公司事件库加载 + plotly annotation 注入。

提供 load_events(ticker) / add_event_annotations(fig, ticker)。
yaml 缺失 / 无该 ticker / 无可用 trace → 静默 no-op,不抛异常。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

_YAML_PATH = Path(__file__).parent / "company_events.yaml"

_TYPE_COLOR = {
    "pe_anomaly": "#dc2626",   # 红
    "dividend":   "#16a34a",   # 绿
    "split":      "#7c3aed",   # 紫
    "buyback":    "#0ea5e9",   # 蓝
    "earnings":   "#f59e0b",   # 橙
    "other":      "#6b7280",   # 灰
}


def _normalize_ticker(t: str) -> str:
    """000858.SZ / sh600519 / 600519 → 6 位裸 ticker。"""
    if not t:
        return ""
    s = str(t).strip().upper()
    for prefix in ("SH", "SZ", "BJ", "HK"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if "." in s:
        s = s.split(".")[0]
    return s.lstrip("0").rjust(len(s), "0") if s.isdigit() else s


def load_events(ticker: str) -> list[dict]:
    """读 yaml,返回该 ticker 的事件列表。文件 / key 缺失返回 []。"""
    if not _YAML_PATH.exists() or not ticker:
        return []
    try:
        import yaml
        with _YAML_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    nt = _normalize_ticker(ticker)
    # 同时尝试原始 key 和归一化 key
    events = data.get(ticker) or data.get(nt) or []
    if not isinstance(events, list):
        return []
    out = []
    for e in events:
        if isinstance(e, dict) and "date" in e:
            out.append({
                "date": str(e["date"]),
                "type": str(e.get("type", "other")),
                "note": str(e.get("note", "")),
            })
    return out


def add_event_annotations(fig: Any, ticker: str, max_n: int = 8) -> Any:
    """在 fig 的可见日期范围内,注入 annotation。返回原 fig(原地修改)。

    - y 取 fig 数据 trace y 值范围的 90% 高度
    - 超出 x 范围的事件丢弃
    - 异常静默
    """
    if fig is None:
        return fig
    events = load_events(ticker)
    if not events:
        return fig

    try:
        # 收集 x 范围 + y 范围
        x_min, x_max = None, None
        y_min, y_max = None, None
        for tr in fig.data:
            xs = getattr(tr, "x", None)
            ys = getattr(tr, "y", None)
            if xs is not None and len(xs) > 0:
                xs_ser = pd.to_datetime(pd.Series(xs), errors="coerce").dropna()
                if len(xs_ser):
                    lo, hi = xs_ser.min(), xs_ser.max()
                    x_min = lo if x_min is None else min(x_min, lo)
                    x_max = hi if x_max is None else max(x_max, hi)
            if ys is not None and len(ys) > 0:
                ys_ser = pd.to_numeric(pd.Series(ys), errors="coerce").dropna()
                if len(ys_ser):
                    lo, hi = ys_ser.min(), ys_ser.max()
                    y_min = lo if y_min is None else min(y_min, lo)
                    y_max = hi if y_max is None else max(y_max, hi)
        if x_min is None or y_min is None or y_max is None:
            return fig

        y_anno = y_min + (y_max - y_min) * 0.90

        added = 0
        for e in events:
            if added >= max_n:
                break
            try:
                d = pd.to_datetime(e["date"])
            except Exception:
                continue
            if x_max is not None and (d < x_min or d > x_max):
                continue
            color = _TYPE_COLOR.get(e["type"], _TYPE_COLOR["other"])
            label = f"{e['type']}: {e['note']}" if e["note"] else e["type"]
            fig.add_annotation(
                x=d, y=y_anno,
                text=label,
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.2,
                arrowcolor=color,
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor=color, borderwidth=1, borderpad=3,
                font=dict(size=10, color=color),
                ax=0, ay=-30,
            )
            added += 1
    except Exception:
        pass
    return fig
