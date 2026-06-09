"""v2.5 行业估值分位引擎(任务包 02 / E1)。

给定行业名(SW L2,例如「白酒」/「股份制银行」),返回:
  · PE/PB 当前中位数
  · 10y 分位(基于 preson.duckdb.valuation 时序聚合)
  · 行业成份股数
  · 数据源("market.duckdb" / "peers.duckdb" / "self_only" / "no_data")

三级降级策略:
  1. data/market.duckdb 的 market_spot 表(全市场快照 ~5400 行)
  2. data/peers.duckdb 的 peers + self_metrics 表(同行池 ~80 家)
  3. data/preson.duckdb 的 valuation 表(自选 15 家)

不在引擎层缓存(留给 UI 层 @st.cache_data 包一层)。

接口契约(README.md E):
    @dataclass class IndustryPercentile
    def compute(industry: str) -> IndustryPercentile

设计取舍:
  · companies.csv 行业字段是 industry_l2(SW L2);peers.duckdb 是 industry_em(EM 风格)。
    映射策略:不写硬编码 SW↔EM 字典(成本高且易过期),改成「以 self ticker 为锚」 —
    通过 self ticker 在 peers.duckdb 反查 industry_em,然后用同 industry_em 拉 peer 池。
    这样名字层就不依赖映射,自动对齐。
  · market.duckdb 同样 industry_em 字段;若文件不存在或为空,直接跳到 Path 2。
  · 10y 分位:用 preson.duckdb.valuation 的 PE-TTM/PB 时序,日级中位数 → 分位。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import csv

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MARKET_DB = PROJECT_ROOT / "data" / "market.duckdb"
PEERS_DB = PROJECT_ROOT / "data" / "peers.duckdb"
PRESON_DB = PROJECT_ROOT / "data" / "preson.duckdb"
COMPANIES_CSV = PROJECT_ROOT / ".config" / "companies.csv"


@dataclass
class IndustryPercentile:
    industry: str
    pe_median: Optional[float]
    pe_percentile_10y: Optional[float]  # 0-100
    pb_median: Optional[float]
    pb_percentile_10y: Optional[float]
    member_count: int
    as_of: date
    data_source: str  # market.duckdb / peers.duckdb / self_only / no_data
    notes: str = ""


# ─── 公共助手 ────────────────────────────────────────────────────────────


def _empty_result(industry: str, note: str = "无可用数据源") -> IndustryPercentile:
    return IndustryPercentile(
        industry=industry,
        pe_median=None,
        pe_percentile_10y=None,
        pb_median=None,
        pb_percentile_10y=None,
        member_count=0,
        as_of=date.today(),
        data_source="no_data",
        notes=note,
    )


def _load_companies() -> pd.DataFrame:
    """读 .config/companies.csv → DataFrame(stock/industry_l2/category 等)。"""
    if not COMPANIES_CSV.exists():
        return pd.DataFrame(columns=["stock", "name", "industry_l2", "category"])
    rows: list[dict] = []
    with COMPANIES_CSV.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["stock"] = df["stock"].astype(str).str.zfill(6)
    return df


def _self_tickers_for_industry(industry: str) -> list[str]:
    """返回该行业的自选 ticker(按 industry_l2 精确匹配)。"""
    df = _load_companies()
    if df.empty or "industry_l2" not in df.columns:
        return []
    sub = df[df["industry_l2"] == industry]
    return sub["stock"].dropna().astype(str).tolist()


def _safe_median(values: list[float] | pd.Series) -> Optional[float]:
    arr = np.asarray([v for v in values if v is not None and not pd.isna(v) and v > 0],
                     dtype=float)
    if arr.size == 0:
        return None
    return float(np.median(arr))


def _percentile_of(value: Optional[float], series: pd.Series) -> Optional[float]:
    """series 是 10 年时序中位数序列;返回 value 在 series 中的分位(0-100)。"""
    if value is None or series is None or series.empty:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    s = s[s > 0]
    if s.empty:
        return None
    rank = float((s <= value).sum()) / float(len(s)) * 100.0
    return round(rank, 2)


# ─── 10y 分位:基于 preson.duckdb.valuation 时序 ────────────────────────


def _valuation_industry_history(tickers: list[str], metric: str) -> pd.Series:
    """从 preson.duckdb.valuation 拉 ticker 池的 metric 时序,逐日聚合中位数。

    返回 Series(index=date, value=industry-median-of-metric)。
    metric 列是中文原列名(PE-TTM / PB),见 reference_lixinger_data_quirks。
    """
    if not tickers or not PRESON_DB.exists():
        return pd.Series(dtype=float)
    try:
        con = duckdb.connect(str(PRESON_DB), read_only=True)
    except Exception:
        return pd.Series(dtype=float)
    try:
        placeholders = ",".join(["?"] * len(tickers))
        df = con.execute(
            f"""
            SELECT date, value
            FROM valuation
            WHERE metric = ?
              AND ticker IN ({placeholders})
              AND value IS NOT NULL
              AND value > 0
            """,
            [metric, *tickers],
        ).df()
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    series = df.groupby("date")["value"].median().sort_index()
    # 限定 10 年窗口
    cutoff = pd.Timestamp(date.today()) - pd.DateOffset(years=10)
    series = series[series.index >= cutoff]
    return series


def _industry_history_for(self_tickers: list[str], peer_tickers: list[str],
                          metric: str) -> pd.Series:
    """合并 self + peer 池(去重),返回行业内日级中位数时序。"""
    pool = sorted({str(t).zfill(6) for t in (self_tickers + peer_tickers) if t})
    if not pool:
        return pd.Series(dtype=float)
    return _valuation_industry_history(pool, metric)


# ─── Path 1 · market.duckdb ────────────────────────────────────────────


def _try_market_db(industry: str, self_tickers: list[str]) -> Optional[IndustryPercentile]:
    """从 market.duckdb 拉行业内全部成份的 PE/PB 当前快照。

    market_spot 字段:industry_em / pe / pb / snapshot_date(见 fetch_market_spot.py)
    """
    if not MARKET_DB.exists():
        return None
    try:
        con = duckdb.connect(str(MARKET_DB), read_only=True)
    except Exception:
        return None
    try:
        # 表是否存在
        t_exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name='market_spot'"
        ).fetchone()
        if not t_exists or t_exists[0] == 0:
            return None
        cnt = con.execute("SELECT count(*) FROM market_spot").fetchone()[0]
        if cnt == 0:
            return None
        # 模糊匹配:industry_em 与 SW L2 名直接相等(白酒/化学制药/保险等多数重合);
        # 失败时尝试 LIKE 子串。
        df = con.execute(
            """
            WITH last AS (
                SELECT max(snapshot_date) AS d FROM market_spot
            )
            SELECT ticker, pe, pb
            FROM market_spot, last
            WHERE snapshot_date = last.d
              AND (industry_em = ? OR industry_em LIKE ?)
              AND pe IS NOT NULL
            """,
            [industry, f"%{industry}%"],
        ).df()
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()

    if df.empty:
        return None

    pe_med = _safe_median(df["pe"]) if "pe" in df.columns else None
    pb_med = _safe_median(df["pb"]) if "pb" in df.columns else None
    pool_tickers = df["ticker"].astype(str).str.zfill(6).tolist()

    pe_hist = _industry_history_for(self_tickers, pool_tickers, "PE-TTM")
    pb_hist = _industry_history_for(self_tickers, pool_tickers, "PB")
    pe_pct = _percentile_of(pe_med, pe_hist)
    pb_pct = _percentile_of(pb_med, pb_hist)

    note = ""
    if pe_pct is None and pb_pct is None:
        note = "10y 分位待 valuation 时序覆盖该行业后接入"

    return IndustryPercentile(
        industry=industry,
        pe_median=pe_med,
        pe_percentile_10y=pe_pct,
        pb_median=pb_med,
        pb_percentile_10y=pb_pct,
        member_count=len(df),
        as_of=date.today(),
        data_source="market.duckdb",
        notes=note,
    )


# ─── Path 2 · peers.duckdb ─────────────────────────────────────────────


def _try_peers_db(industry: str, self_tickers: list[str]) -> Optional[IndustryPercentile]:
    """从 peers.duckdb 拉行业内 self+peer 池的 PE/PB。

    策略:以 self_tickers 为锚 → 在 peers/self_metrics 反查 industry_em →
    用 industry_em 取同行业全部 peer_ticker;若 self_tickers 空,
    直接尝试用 SW L2 名匹配 industry_em(很多直接相等,如「白酒」)。
    """
    if not PEERS_DB.exists():
        return None
    try:
        con = duckdb.connect(str(PEERS_DB), read_only=True)
    except Exception:
        return None
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "peers" not in tables:
            return None

        # 1) 找 industry_em(优先用 self ticker 反查,缺失时 fallback 直接用 SW L2 名)
        industry_em: Optional[str] = None
        if self_tickers:
            placeholders = ",".join(["?"] * len(self_tickers))
            row = con.execute(
                f"""
                SELECT industry_em FROM peers
                WHERE ticker IN ({placeholders}) AND industry_em IS NOT NULL
                LIMIT 1
                """,
                self_tickers,
            ).fetchone()
            if row and row[0]:
                industry_em = row[0]
        if not industry_em:
            # SW L2 名直接当 industry_em 试一下(多数行业名 SW 与 EM 重合)
            row = con.execute(
                """
                SELECT industry_em FROM peers
                WHERE industry_em = ? OR industry_em LIKE ?
                LIMIT 1
                """,
                [industry, f"%{industry}%"],
            ).fetchone()
            if row and row[0]:
                industry_em = row[0]

        if not industry_em:
            return None

        # 2) 拉同 industry_em 的 peer 池(unique peer_ticker)+ 它们的 PE/PB
        peer_df = con.execute(
            """
            SELECT DISTINCT peer_ticker AS ticker, peer_pe AS pe, peer_pb AS pb
            FROM peers
            WHERE industry_em = ?
            """,
            [industry_em],
        ).df()
        # 3) self_metrics 拉 self 的 PE/PB
        self_df = pd.DataFrame()
        if "self_metrics" in tables:
            try:
                self_df = con.execute(
                    """
                    SELECT ticker, pe, pb FROM self_metrics
                    WHERE industry_em = ?
                    """,
                    [industry_em],
                ).df()
            except Exception:
                self_df = pd.DataFrame()
    except Exception:
        return None
    finally:
        con.close()

    pool = pd.concat([peer_df, self_df], ignore_index=True) if not peer_df.empty or not self_df.empty else pd.DataFrame()
    if pool.empty:
        return None
    pool = pool.dropna(subset=["ticker"]).drop_duplicates(subset=["ticker"], keep="first")

    pe_med = _safe_median(pool["pe"]) if "pe" in pool.columns else None
    pb_med = _safe_median(pool["pb"]) if "pb" in pool.columns else None
    pool_tickers = pool["ticker"].astype(str).str.zfill(6).tolist()

    pe_hist = _industry_history_for(self_tickers, pool_tickers, "PE-TTM")
    pb_hist = _industry_history_for(self_tickers, pool_tickers, "PB")
    pe_pct = _percentile_of(pe_med, pe_hist)
    pb_pct = _percentile_of(pb_med, pb_hist)

    notes_parts = [f"通过 industry_em={industry_em} 匹配,池 {len(pool)} 只"]
    if pe_pct is None and pb_pct is None:
        notes_parts.append("10y 分位待 valuation 时序覆盖")

    return IndustryPercentile(
        industry=industry,
        pe_median=pe_med,
        pe_percentile_10y=pe_pct,
        pb_median=pb_med,
        pb_percentile_10y=pb_pct,
        member_count=len(pool),
        as_of=date.today(),
        data_source="peers.duckdb",
        notes=" / ".join(notes_parts),
    )


# ─── Path 3 · self_only(preson.duckdb.valuation) ──────────────────────


def _try_self_only(industry: str, self_tickers: list[str]) -> Optional[IndustryPercentile]:
    """仅自选成份 — 从 preson.duckdb.valuation 拉每只最新 PE-TTM/PB → 中位数。"""
    if not self_tickers or not PRESON_DB.exists():
        return None
    try:
        con = duckdb.connect(str(PRESON_DB), read_only=True)
    except Exception:
        return None
    try:
        placeholders = ",".join(["?"] * len(self_tickers))
        # 每只取最新 PE-TTM
        pe_df = con.execute(
            f"""
            SELECT v.ticker, v.value AS pe
            FROM valuation v
            INNER JOIN (
                SELECT ticker, MAX(date) AS mdate FROM valuation
                WHERE metric = 'PE-TTM' AND ticker IN ({placeholders})
                GROUP BY ticker
            ) m ON v.ticker = m.ticker AND v.metric = 'PE-TTM' AND v.date = m.mdate
            """,
            self_tickers,
        ).df()
        pb_df = con.execute(
            f"""
            SELECT v.ticker, v.value AS pb
            FROM valuation v
            INNER JOIN (
                SELECT ticker, MAX(date) AS mdate FROM valuation
                WHERE metric = 'PB' AND ticker IN ({placeholders})
                GROUP BY ticker
            ) m ON v.ticker = m.ticker AND v.metric = 'PB' AND v.date = m.mdate
            """,
            self_tickers,
        ).df()
    except Exception:
        return None
    finally:
        con.close()

    if pe_df.empty and pb_df.empty:
        return None

    pe_med = _safe_median(pe_df["pe"]) if not pe_df.empty else None
    pb_med = _safe_median(pb_df["pb"]) if not pb_df.empty else None
    member = max(len(pe_df), len(pb_df))

    # 10y 分位:仅基于自选 ticker 池,可能样本很小;但仍然算
    pe_hist = _valuation_industry_history(self_tickers, "PE-TTM")
    pb_hist = _valuation_industry_history(self_tickers, "PB")
    pe_pct = _percentile_of(pe_med, pe_hist)
    pb_pct = _percentile_of(pb_med, pb_hist)

    return IndustryPercentile(
        industry=industry,
        pe_median=pe_med,
        pe_percentile_10y=pe_pct,
        pb_median=pb_med,
        pb_percentile_10y=pb_pct,
        member_count=member,
        as_of=date.today(),
        data_source="self_only",
        notes=f"仅基于 {member} 家自选成份,行业代表性有限",
    )


# ─── 主入口 ────────────────────────────────────────────────────────────


def compute(industry: str) -> IndustryPercentile:
    """三级降级:market.duckdb → peers.duckdb → self_only → no_data。"""
    if not industry or not isinstance(industry, str):
        return _empty_result(str(industry or ""), "行业名为空")

    self_tickers = _self_tickers_for_industry(industry)

    # Path 1
    r = _try_market_db(industry, self_tickers)
    if r and r.member_count > 0 and (r.pe_median is not None or r.pb_median is not None):
        return r

    # Path 2
    r = _try_peers_db(industry, self_tickers)
    if r and r.member_count > 0 and (r.pe_median is not None or r.pb_median is not None):
        return r

    # Path 3
    r = _try_self_only(industry, self_tickers)
    if r and r.member_count > 0 and (r.pe_median is not None or r.pb_median is not None):
        return r

    # 全失败
    return _empty_result(industry)


__all__ = ["IndustryPercentile", "compute"]
