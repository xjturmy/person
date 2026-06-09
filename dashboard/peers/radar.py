"""dash-03 · 同行雷达叠加 helper。

按 companies.category 分组(non_financial / bank / insurance / hk),返回与本公司同组的其他 ticker。
绘图:多个 Scatterpolar 叠加,本公司高亮(粗线 + 填充),同行虚线半透明。

不依赖 streamlit;Plotly Figure 由调用方 st.plotly_chart 渲染。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import duckdb  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

import ui.score_card as sc  # noqa: E402

DB_PATH = ROOT / "data" / "preson.duckdb"

DIM_ORDER = ["valuation", "profitability", "growth", "cashflow", "safety", "strategies"]


def peer_pool(ticker: str, db_path: Path = DB_PATH, max_n: int = 5) -> list[tuple[str, str]]:
    """返回与 ticker 同 category 的其他公司 [(ticker, name), ...],最多 max_n 家。"""
    if not ticker:
        return []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute(
            "SELECT category FROM companies WHERE ticker = ?", [ticker]
        ).fetchone()
        if not row:
            return []
        cat = row[0]
        peers = con.execute(
            "SELECT ticker, name FROM companies "
            "WHERE category = ? AND ticker != ? "
            "ORDER BY folder LIMIT ?",
            [cat, ticker, max_n],
        ).fetchall()
        return [(t, n) for t, n in peers]
    finally:
        con.close()


def peer_radar_chart(scores: list, self_ticker: str, height: int = 460) -> go.Figure:
    """
    scores: list[CompanyScore]
    self_ticker: 本公司 ticker(高亮)
    """
    labels = [sc.DIM_LABEL[k] for k in DIM_ORDER]
    labels_closed = labels + [labels[0]]
    fig = go.Figure()
    for s in scores:
        vals = []
        for k in DIM_ORDER:
            d = s.dims.get(k)
            vals.append(d.score if (d and d.score is not None) else 50)
        vals_closed = vals + [vals[0]]
        is_self = s.ticker == self_ticker
        if is_self:
            fig.add_trace(go.Scatterpolar(
                r=vals_closed, theta=labels_closed,
                name=f"⭐ {s.name}",
                line=dict(color="#0d6efd", width=3),
                fill="toself", fillcolor="rgba(13,110,253,0.20)",
            ))
        else:
            fig.add_trace(go.Scatterpolar(
                r=vals_closed, theta=labels_closed,
                name=s.name,
                line=dict(width=1.4, dash="dot"),
                opacity=0.7,
            ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickvals=[20, 40, 60, 80])),
        showlegend=True, height=height,
        legend=dict(orientation="h", y=-0.10, x=0.5, xanchor="center"),
        margin=dict(l=20, r=20, t=20, b=60),
    )
    return fig


if __name__ == "__main__":
    # CLI 自检
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", default="600519", nargs="?")
    args = ap.parse_args()
    peers = peer_pool(args.ticker)
    print(f"\n{args.ticker} 同行 ({len(peers)} 家):")
    for t, n in peers:
        print(f"  {t}  {n}")
    if peers:
        print("\n抓 6 维评分中…")
        all_t = [args.ticker] + [t for t, _ in peers]
        scores = []
        for t in all_t:
            try:
                scores.append(sc.compute_dimensions(t))
                print(f"  ✅ {t}")
            except Exception as e:
                print(f"  ❌ {t}: {e}")
        print(f"\n总维度评分(0-100):")
        for s in scores:
            tag = "⭐" if s.ticker == args.ticker else "  "
            line = " ".join(
                f"{sc.DIM_LABEL[k][:2]}{(s.dims[k].score or 0):3.0f}" for k in DIM_ORDER
            )
            print(f"  {tag} {s.name:6s}  {line}  ★{s.overall:.0f}")
