"""dash-03 · 本公司决策时间线 helper。

数据源:.tools/decisions/db.py 的 list_by_ticker(ticker) — DuckDB `decisions` 表。

绘图:Plotly 时间散点图(action 颜色编码)+ 简表;若无决策返回 None。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / ".tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

ACTION_COLOR = {
    "buy": "#1b8a3a",       # 深绿
    "add": "#5cb85c",       # 浅绿
    "trim": "#f0ad4e",      # 黄
    "sell": "#d9534f",      # 红
    "watch": "#888",        # 灰
    "hold": "#0d6efd",      # 蓝(默认)
}
ACTION_ICON = {"buy": "🟢", "add": "🟢", "trim": "🟡", "sell": "🔴", "watch": "👁", "hold": "🔵"}


def load_decisions(ticker: str) -> list[dict]:
    """返回本公司决策 list[dict],按时间正序。失败返回空。"""
    if not ticker:
        return []
    try:
        from decisions import db as ddb
        rows = ddb.list_by_ticker(ticker)
        if not rows:
            return []
        # rows 可能是 dict 或 tuple,统一字段
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append(r)
            else:
                # 假设按 INSERT 顺序:id, ticker, folder, date, action, weight_change, price, rationale, ...
                out.append({
                    "id": r[0], "ticker": r[1], "folder": r[2], "date": r[3],
                    "action": r[4], "weight_change": r[5], "price": r[6],
                    "rationale": r[7] if len(r) > 7 else "",
                })
        out.sort(key=lambda d: pd.to_datetime(d.get("date")))
        return out
    except Exception:
        return []


def timeline_chart(decisions: list[dict], price_df: pd.DataFrame | None = None,
                   height: int = 320) -> go.Figure | None:
    """
    决策散点 + 可选股价底图。
    price_df: optional pd.DataFrame(date, close) — 当前公司 prices,作为浅灰底图。
    """
    if not decisions:
        return None
    df = pd.DataFrame(decisions)
    df["date"] = pd.to_datetime(df["date"])
    fig = go.Figure()
    if price_df is not None and not price_df.empty:
        fig.add_trace(go.Scatter(
            x=price_df["date"], y=price_df["close"],
            mode="lines", name="收盘价",
            line=dict(color="#bbb", width=1.2),
            hovertemplate="%{x|%Y-%m-%d}<br>¥%{y:.2f}<extra></extra>",
        ))
    for action, color in ACTION_COLOR.items():
        sub = df[df["action"] == action]
        if sub.empty:
            continue
        y_vals = sub.get("price")
        if y_vals is None or y_vals.isna().all():
            y_vals = [1.0] * len(sub)  # 占位
        fig.add_trace(go.Scatter(
            x=sub["date"], y=y_vals,
            mode="markers+text",
            marker=dict(size=14, color=color, symbol="diamond",
                        line=dict(color="white", width=1.5)),
            text=[ACTION_ICON.get(action, "") for _ in range(len(sub))],
            textposition="top center",
            name=action,
            customdata=sub[["rationale", "weight_change"]].fillna("").values,
            hovertemplate=(
                "<b>%{x|%Y-%m-%d}</b> · " + action + "<br>"
                "价 ¥%{y:.2f}<br>"
                "权重变 %{customdata[1]}<br>"
                "%{customdata[0]}<extra></extra>"
            ),
        ))
    fig.update_layout(
        height=height, hovermode="closest",
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        xaxis=dict(title=""), yaxis=dict(title="价 / 权重"),
    )
    return fig


def render_summary_table(decisions: list[dict]) -> pd.DataFrame:
    """返回精简表格(date / action / 价 / 权重变 / 理由前 60 字)。"""
    if not decisions:
        return pd.DataFrame()
    rows = []
    for d in decisions:
        rationale = (d.get("rationale") or "")[:60]
        if d.get("rationale") and len(d.get("rationale")) > 60:
            rationale += "…"
        rows.append({
            "日期": pd.to_datetime(d.get("date")).strftime("%Y-%m-%d") if d.get("date") else "—",
            "动作": f"{ACTION_ICON.get(d.get('action', ''), '')} {d.get('action', '')}",
            "价": d.get("price"),
            "权重变": d.get("weight_change"),
            "理由": rationale,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", default="600519", nargs="?")
    args = ap.parse_args()
    ds = load_decisions(args.ticker)
    print(f"\n{args.ticker} 决策记录:{len(ds)} 条")
    if ds:
        print(render_summary_table(ds).to_string(index=False))
