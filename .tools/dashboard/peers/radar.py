"""dash-03 · 同行雷达叠加 helper。

同行必须来自同一细分行业:
1. 优先使用 data/peers.duckdb / .config/peers.csv 的行业成分缓存;
2. 缓存缺失时,只从 .config/companies.csv 里找同二级行业公司;
3. 仍不足时返回空,由页面提示刷新同行库,不跨大类硬凑同行。

绘图:多个 Scatterpolar 叠加,本公司高亮(粗线 + 填充),同行虚线半透明。

不依赖 streamlit;Plotly Figure 由调用方 st.plotly_chart 渲染。
"""
from __future__ import annotations

import csv
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
PEERS_DB_PATH = ROOT / "data" / "peers.duckdb"
PEERS_CSV = ROOT / ".config" / "peers.csv"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"

DIM_ORDER = ["valuation", "profitability", "growth", "cashflow", "safety", "strategies"]


def _norm_ticker(ticker: str) -> str:
    s = str(ticker or "").strip()
    return s.zfill(6) if s.isdigit() and len(s) <= 6 else s


def _clean_industry(value: str | None) -> str:
    text = str(value or "").strip()
    return text.removesuffix("Ⅱ").strip()


def _read_peer_rows_from_db(ticker: str, max_n: int) -> list[dict]:
    if not PEERS_DB_PATH.exists():
        return []
    con = duckdb.connect(str(PEERS_DB_PATH), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT *
            FROM peers
            WHERE ticker = ?
            ORDER BY rank
            LIMIT ?
            """,
            [_norm_ticker(ticker), max_n],
        ).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()
    return [dict(zip(cols, row)) for row in rows]


def _read_peer_rows_from_csv(ticker: str, max_n: int) -> list[dict]:
    if not PEERS_CSV.exists():
        return []
    out: list[dict] = []
    with PEERS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if _norm_ticker(row.get("ticker", "")) != _norm_ticker(ticker):
                continue
            out.append(row)
            if len(out) >= max_n:
                break
    return out


def _companies_rows() -> list[dict]:
    if not COMPANIES_CSV.exists():
        return []
    with COMPANIES_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _peer_rows_from_company_industry(ticker: str, max_n: int) -> list[dict]:
    rows = _companies_rows()
    current = next((r for r in rows if _norm_ticker(r.get("stock", "")) == _norm_ticker(ticker)), None)
    if not current:
        return []
    industry_l2 = _clean_industry(current.get("industry_l2"))
    if not industry_l2:
        return []
    peers = []
    for r in rows:
        pt = _norm_ticker(r.get("stock", ""))
        if pt == _norm_ticker(ticker):
            continue
        if _clean_industry(r.get("industry_l2")) != industry_l2:
            continue
        peers.append({
            "ticker": _norm_ticker(ticker),
            "name": current.get("name", ""),
            "industry_em": industry_l2,
            "rank": len(peers) + 1,
            "peer_ticker": pt,
            "peer_name": r.get("name", ""),
            "_source": "companies.csv",
        })
        if len(peers) >= max_n:
            break
    return peers


def peer_pool_rows(ticker: str, db_path: Path = DB_PATH, max_n: int = 5) -> list[dict]:
    """返回严格同细分行业的同行明细;不再按 non_financial 等宽分类兜底。"""
    if not ticker:
        return []
    rows = _read_peer_rows_from_db(ticker, max_n)
    if rows:
        return rows
    rows = _read_peer_rows_from_csv(ticker, max_n)
    if rows:
        return rows
    return _peer_rows_from_company_industry(ticker, max_n)


def peer_pool(ticker: str, db_path: Path = DB_PATH, max_n: int = 5) -> list[tuple[str, str]]:
    """返回严格同细分行业的其他公司 [(ticker, name), ...],最多 max_n 家。"""
    rows = peer_pool_rows(ticker, db_path=db_path, max_n=max_n)
    return [
        (_norm_ticker(r.get("peer_ticker", "")), str(r.get("peer_name", "") or _norm_ticker(r.get("peer_ticker", ""))))
        for r in rows
        if r.get("peer_ticker")
    ]


def peer_group_label(ticker: str, max_n: int = 5) -> str:
    rows = peer_pool_rows(ticker, max_n=max_n)
    if not rows:
        return "暂无同细分行业同行"
    industry = str(rows[0].get("industry_em") or "").strip()
    industry_label = f"同细分行业「{industry}」" if industry else "同细分行业"
    names = "、".join(str(r.get("peer_name") or r.get("peer_ticker")) for r in rows if r.get("peer_ticker"))
    return f"{industry_label}同行({len(rows)}家):{names}"


def _to_float(value) -> float | None:
    try:
        if value in ("", None):
            return None
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _linear(value: float | None, lo: float, hi: float) -> float | None:
    if value is None or hi == lo:
        return None
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100.0))


def _inverse(value: float | None, lo: float, hi: float) -> float | None:
    s = _linear(value, lo, hi)
    return None if s is None else 100.0 - s


def cached_peer_score(row: dict):
    """把 peers 缓存中的外部同行指标转为雷达可读的 CompanyScore。

    外部同行通常不在 companies 主库,无法跑完整 6 维规则;这里只使用已抓到的
    PE/PB/ROE/增长/F-Score,缺口保持中性,避免用错行业公司替补。
    """
    ticker = _norm_ticker(row.get("peer_ticker", ""))
    name = str(row.get("peer_name") or ticker)
    pe = _to_float(row.get("peer_pe"))
    pb = _to_float(row.get("peer_pb"))
    roe = _to_float(row.get("peer_roe"))
    revenue_yoy = _to_float(row.get("peer_revenue_yoy"))
    ni_yoy = _to_float(row.get("peer_ni_yoy"))
    fscore = _to_int(row.get("peer_fscore_lite"))

    val_parts = [x for x in (_inverse(pe, 8, 45), _inverse(pb, 0.8, 6)) if x is not None]
    growth_parts = [x for x in (_linear(revenue_yoy, -10, 35), _linear(ni_yoy, -20, 50)) if x is not None]
    valuation = round(sum(val_parts) / len(val_parts), 1) if val_parts else None
    growth = round(sum(growth_parts) / len(growth_parts), 1) if growth_parts else None
    profitability = round(_linear(roe, 0, 25), 1) if roe is not None else None
    safety = round((fscore or 0) / 4 * 100, 1) if fscore is not None else None

    dims = {
        "valuation": sc.DimResult(valuation, pe, "估值", "同行缓存 PE/PB 近似", "🟡" if valuation is not None else "⚪"),
        "profitability": sc.DimResult(profitability, roe, "盈利", "同行缓存 ROE", "🟡" if profitability is not None else "⚪"),
        "growth": sc.DimResult(growth, revenue_yoy, "成长", "同行缓存收入/利润增长", "🟡" if growth is not None else "⚪"),
        "cashflow": sc.DimResult(None, None, "现金流", "同行缓存暂无现金流", "⚪"),
        "safety": sc.DimResult(safety, fscore, "安全", "F-Score lite 近似", "🟡" if safety is not None else "⚪"),
        "strategies": sc.DimResult(None, None, "策略", "外部同行未跑大师规则", "⚪"),
    }
    overall, badge = sc.overall_score(dims)
    return sc.CompanyScore(
        ticker=ticker,
        name=name,
        category=str(row.get("industry_em") or ""),
        dims=dims,
        overall=overall,
        overall_badge=badge,
    )


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
