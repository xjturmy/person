"""D3 阶段 C 项 2 · 格雷厄姆 5 维同行雷达。

5 维度(均归一化到 0-100,高=优):
  - PE      : 越低越好(< 15 = 100,> 30 = 0)
  - PB      : 越低越好(< 1 = 100,> 5 = 0)
  - DY %    : 越高越好(> 4 = 100,< 1 = 0)
  - 流动比率 : 越高越好(≥ 2 = 100,< 1 = 0)
  - 资产负债率%: 越低越好(< 30 = 100,> 80 = 0)

数据源:
  · self      : graham_steps.load_graham_metrics(ticker)
  · peers ticker 池: peers.duckdb peers 表(取 self 的 peer_ticker)
  · peers metric  : preson.duckdb valuation + safety 表(每个 peer 各 5 项)

调用:
  fig = graham_radar_chart(self_ticker)  → plotly Figure
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[4]
PRESON_DB = ROOT / "data" / "preson.duckdb"
PEERS_DB = ROOT / "data" / "peers.duckdb"

DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))


GRAHAM_DIMS = [
    ("PE",       "low_good"),
    ("PB",       "low_good"),
    ("DY %",     "high_good"),
    ("流动比率",   "high_good"),
    ("资产负债率%", "low_good"),
]


@dataclass
class GrahamPeerScore:
    ticker: str
    name: str
    raw: dict[str, float | None] = field(default_factory=dict)
    norm: dict[str, float | None] = field(default_factory=dict)  # 0-100


def _normalize_pe(v: float | None) -> float | None:
    if v is None or v <= 0:
        return None
    if v <= 15:
        return 100.0
    if v >= 30:
        return 0.0
    return 100.0 - (v - 15) / (30 - 15) * 100.0


def _normalize_pb(v: float | None) -> float | None:
    if v is None or v <= 0:
        return None
    if v <= 1:
        return 100.0
    if v >= 5:
        return 0.0
    return 100.0 - (v - 1) / (5 - 1) * 100.0


def _normalize_dy(v: float | None) -> float | None:
    if v is None:
        return None
    # v 单位是 %(理杏仁直接给 %,如 4.2 = 4.2%)
    if v >= 4:
        return 100.0
    if v <= 1:
        return 0.0
    return (v - 1) / (4 - 1) * 100.0


def _normalize_current_ratio(v: float | None) -> float | None:
    if v is None or v <= 0:
        return None
    if v >= 2:
        return 100.0
    if v <= 1:
        return 0.0
    return (v - 1) / (2 - 1) * 100.0


def _normalize_debt_ratio(v: float | None) -> float | None:
    if v is None:
        return None
    # v 是 % 形式(如 53.5 = 53.5%)
    if v <= 30:
        return 100.0
    if v >= 80:
        return 0.0
    return 100.0 - (v - 30) / (80 - 30) * 100.0


_NORMALIZERS = {
    "PE": _normalize_pe,
    "PB": _normalize_pb,
    "DY %": _normalize_dy,
    "流动比率": _normalize_current_ratio,
    "资产负债率%": _normalize_debt_ratio,
}


def _latest_value(con: duckdb.DuckDBPyConnection, table: str, ticker: str,
                   metric: str) -> float | None:
    try:
        row = con.execute(
            f"""SELECT value FROM {table}
                WHERE ticker = ? AND metric = ?
                ORDER BY date DESC LIMIT 1""",
            [ticker, metric],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def _load_5metrics_from_db(ticker: str,
                            db_path: Path = PRESON_DB) -> dict[str, float | None]:
    """直接从 preson.duckdb 读 5 项 Graham 指标。

    单位规范化:
      · 股息率 0.0378 → 3.78%(× 100)
      · 资产负债率 0.9043 → 90.43%(× 100)
      · 流动比率(纯比例,不换算)
    """
    out = {"PE": None, "PB": None, "DY %": None,
           "流动比率": None, "资产负债率%": None}
    if not db_path.exists():
        return out
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        out["PE"] = _latest_value(con, "valuation", ticker, "PE-TTM")
        out["PB"] = _latest_value(con, "valuation", ticker, "PB")
        dy = _latest_value(con, "valuation", ticker, "股息率")
        out["DY %"] = (dy * 100) if dy is not None else None
        out["流动比率"] = _latest_value(con, "safety", ticker, "流动比率")
        dr = _latest_value(con, "safety", ticker, "资产负债率")
        out["资产负债率%"] = (dr * 100) if dr is not None else None
    finally:
        con.close()
    return out


def _peer_tickers(self_ticker: str, max_n: int = 4) -> list[tuple[str, str]]:
    """从 peers.duckdb 取 self 对应的 peer_ticker 列表。"""
    if not PEERS_DB.exists():
        return []
    con = duckdb.connect(str(PEERS_DB), read_only=True)
    try:
        rows = con.execute(
            """SELECT peer_ticker, peer_name FROM peers
               WHERE ticker = ? ORDER BY rank LIMIT ?""",
            [self_ticker, max_n],
        ).fetchall()
        return [(t, n) for t, n in rows]
    finally:
        con.close()


def _self_name(ticker: str) -> str:
    if not PRESON_DB.exists():
        return ticker
    con = duckdb.connect(str(PRESON_DB), read_only=True)
    try:
        row = con.execute(
            "SELECT name FROM companies WHERE ticker = ? LIMIT 1",
            [ticker],
        ).fetchone()
        return row[0] if row else ticker
    finally:
        con.close()


def graham_peer_scores(self_ticker: str,
                         max_peers: int = 4) -> list[GrahamPeerScore]:
    """返回 [self] + [peers] 的 5 维 Graham 分数(原值 + 归一化 0-100)。

    peer 没数据时保留 ticker/name 但 raw/norm 全 None;调用方自行决定是否跳过。
    """
    if not self_ticker:
        return []

    rows: list[GrahamPeerScore] = []
    self_raw = _load_5metrics_from_db(self_ticker)
    self_score = GrahamPeerScore(
        ticker=self_ticker, name=_self_name(self_ticker), raw=self_raw,
        norm={k: _NORMALIZERS[k](v) for k, v in self_raw.items()},
    )
    rows.append(self_score)

    for peer_t, peer_n in _peer_tickers(self_ticker, max_n=max_peers):
        peer_raw = _load_5metrics_from_db(peer_t)
        peer_score = GrahamPeerScore(
            ticker=peer_t, name=peer_n, raw=peer_raw,
            norm={k: _NORMALIZERS[k](v) for k, v in peer_raw.items()},
        )
        rows.append(peer_score)
    return rows


def has_data(s: GrahamPeerScore) -> bool:
    """判断该 peer 是否有任意一项原值非 None。"""
    return any(v is not None for v in s.raw.values())


def graham_radar_chart(scores: list[GrahamPeerScore],
                         self_ticker: str, height: int = 460) -> go.Figure:
    """5 维雷达 self 高亮 + peers 虚线叠加。"""
    labels = [d for d, _ in GRAHAM_DIMS]
    labels_closed = labels + [labels[0]]
    fig = go.Figure()
    for s in scores:
        vals = [s.norm.get(d) if s.norm.get(d) is not None else 0
                for d, _ in GRAHAM_DIMS]
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
        polar=dict(radialaxis=dict(visible=True, range=[0, 100],
                                     tickvals=[20, 40, 60, 80])),
        showlegend=True, height=height,
        legend=dict(orientation="h", y=-0.10, x=0.5, xanchor="center"),
        margin=dict(l=20, r=20, t=20, b=60),
        title=dict(text="格雷厄姆 5 维同行雷达(0-100,高=优)", x=0.5, xanchor="center",
                    font=dict(size=14)),
    )
    return fig


def render_summary_table(scores: list[GrahamPeerScore]) -> dict:
    """生成同行 5 项原值 + 归一化对照表(供 streamlit dataframe 渲染)。"""
    import pandas as pd
    rows = []
    for s in scores:
        row = {"代码": s.ticker, "公司": s.name}
        for d, _ in GRAHAM_DIMS:
            raw = s.raw.get(d)
            norm = s.norm.get(d)
            row[d] = "—" if raw is None else (
                f"{raw:.2f}({norm:.0f})" if norm is not None else f"{raw:.2f}"
            )
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", default="600519", nargs="?")
    args = ap.parse_args()

    scores = graham_peer_scores(args.ticker)
    print(f"\n=== {args.ticker} 格雷厄姆 5 维同行雷达 ===\n")
    if not scores:
        print("(无数据)")
    else:
        for s in scores:
            mark = "⭐" if s.ticker == args.ticker else "  "
            print(f"{mark} {s.ticker} {s.name}")
            for d, _ in GRAHAM_DIMS:
                raw = s.raw.get(d)
                norm = s.norm.get(d)
                raw_s = f"{raw:.2f}" if raw is not None else "—"
                norm_s = f"{norm:.0f}" if norm is not None else "—"
                print(f"     {d:10s} 原值={raw_s:>8s} 归一={norm_s:>3s}/100")
            print()
