"""Phase B1 · 同行业分位计算。

输入(ticker, metric)→ 返回 self vs 行业 P25/P50/P75 + percentile_in_peers + 同行明细。
数据源:peers.duckdb 的 peers 表(由 .tools/db/fetch_peers.py 维护)。

不依赖 streamlit;dataclass 返回值,UI 在 components/ 渲染。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PEERS_DB_PATH = ROOT / "data" / "peers.duckdb"


# 指标 → (peer 表列名, self_metrics 表列名) 映射
METRIC_COL_MAP = {
    "PE": ("peer_pe", "pe"),
    "PB": ("peer_pb", "pb"),
    "ROE": ("peer_roe", "roe"),
    "毛利率": ("peer_gross_margin", "gross_margin"),
    "营收YoY": ("peer_revenue_yoy", "revenue_yoy"),
    "净利YoY": ("peer_ni_yoy", "ni_yoy"),
    "PEG": ("peer_peg", "peg"),
    "F-Score lite": ("peer_fscore_lite", "fscore_lite"),
    "市值(亿)": ("peer_market_cap", "market_cap"),
}

# 方向:high_is_good = ROE / 毛利 / 营收YoY / 净利YoY / F-Score / 市值;low_is_good = PE / PB / PEG
HIGH_IS_GOOD = {"ROE", "毛利率", "营收YoY", "净利YoY", "F-Score lite", "市值(亿)"}


@dataclass
class IndustryPercentile:
    ticker: str
    name: str
    industry: str
    metric: str
    self_value: float | None
    peer_p25: float | None
    peer_p50: float | None
    peer_p75: float | None
    percentile: float | None       # self 在同行(含 self)中的百分位 0-100
    n_peers: int                    # 同行数(不含 self)
    direction: Literal["high_good", "low_good"]
    label: str                      # "偏低 / 合理 / 偏高"(站在投资者角度)
    peer_rows: pd.DataFrame         # 含 peer_ticker, peer_name, value


def _percentile_of(value: float, arr: np.ndarray) -> float | None:
    """value 在 arr 中的百分位(0-100,inclusive 含等于)。"""
    if value is None or len(arr) == 0:
        return None
    n = len(arr)
    less = int((arr < value).sum())
    equal = int((arr == value).sum())
    return 100.0 * (less + 0.5 * equal) / n


def _label_from(percentile: float | None, direction: str) -> str:
    if percentile is None:
        return "—"
    # 站投资者角度:high_is_good 高分位 → 偏高(质量好但贵?), low_is_good 低分位 → 偏低(便宜)
    # 但用户视角:用"偏低/合理/偏高"指代该指标自身水平,不指代估值方向
    if percentile < 30:
        return "偏低"
    if percentile > 70:
        return "偏高"
    return "合理"


def industry_percentile(
    ticker: str,
    metric: str,
    db_path: Path = PEERS_DB_PATH,
) -> IndustryPercentile | None:
    """
    返回 ticker 在同行业内某个指标的分位数据。

    self 取自 peers 表中 ticker == 输入 ticker 的行(若存在)。
    若 self 不在 peers 中(比如港股),返回 None。
    """
    if metric not in METRIC_COL_MAP:
        raise ValueError(f"不支持的指标:{metric}(可选:{list(METRIC_COL_MAP)})")
    peer_col, self_col = METRIC_COL_MAP[metric]
    direction = "high_good" if metric in HIGH_IS_GOOD else "low_good"

    if not db_path.exists():
        return None

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        peer_rows = con.execute(
            f"SELECT peer_ticker, peer_name, peer_market_cap, {peer_col} AS value, "
            "industry_em "
            "FROM peers WHERE ticker = ?",
            [ticker],
        ).df()
        if peer_rows.empty:
            return None

        industry = peer_rows.iloc[0]["industry_em"]

        # self 直接从 self_metrics 表读
        self_value = None
        try:
            row = con.execute(
                f"SELECT {self_col} FROM self_metrics WHERE ticker = ?",
                [ticker],
            ).fetchone()
            if row and row[0] is not None:
                self_value = float(row[0])
        except Exception:
            # 兼容旧 schema(无 self_metrics 表)→ 回退到 MAX(peer_col)
            row = con.execute(
                f"SELECT MAX({peer_col}) FROM peers WHERE peer_ticker = ?",
                [ticker],
            ).fetchone()
            self_value = float(row[0]) if row and row[0] is not None else None
    finally:
        con.close()

    # 把 peer 与 self 一起做分位(常见做法:含 self 计算)
    peer_values = peer_rows["value"].dropna().astype(float).values
    arr_with_self = peer_values.copy()
    if self_value is not None:
        arr_with_self = np.append(arr_with_self, [float(self_value)])

    if len(arr_with_self) == 0:
        return IndustryPercentile(
            ticker=ticker, name="", industry=industry, metric=metric,
            self_value=self_value, peer_p25=None, peer_p50=None, peer_p75=None,
            percentile=None, n_peers=len(peer_rows), direction=direction,
            label="—", peer_rows=peer_rows,
        )

    p25, p50, p75 = np.percentile(arr_with_self, [25, 50, 75]).tolist()
    pct = _percentile_of(self_value, arr_with_self) if self_value is not None else None
    label = _label_from(pct, direction)

    return IndustryPercentile(
        ticker=ticker, name="", industry=industry, metric=metric,
        self_value=float(self_value) if self_value is not None else None,
        peer_p25=float(p25), peer_p50=float(p50), peer_p75=float(p75),
        percentile=pct, n_peers=len(peer_rows),
        direction=direction, label=label, peer_rows=peer_rows,
    )


def all_metrics_summary(ticker: str, db_path: Path = PEERS_DB_PATH) -> pd.DataFrame:
    """一次性返回所有指标的分位摘要,适合 Streamlit 主表渲染。"""
    rows = []
    for m in METRIC_COL_MAP:
        ip = industry_percentile(ticker, m, db_path)
        if ip is None:
            continue
        rows.append({
            "指标": m,
            "本公司": ip.self_value,
            "P25": ip.peer_p25,
            "中位": ip.peer_p50,
            "P75": ip.peer_p75,
            "分位 %": round(ip.percentile, 1) if ip.percentile is not None else None,
            "标签": ip.label,
            "同行数": ip.n_peers,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", default="600519", nargs="?")
    args = ap.parse_args()

    print(f"\n=== {args.ticker} 行业横评 ===\n")
    df = all_metrics_summary(args.ticker)
    if df.empty:
        print("(无数据)")
    else:
        print(df.to_string(index=False))
