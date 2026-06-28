"""分析预计算读层 — 读 data/analytics.duckdb,给页面提供"已算好"的结果。

配合 .tools/analytics/precompute.py。所有访问器在库缺失 / ticker 不存在 /
blob 损坏时返回 None / 空,调用方据此降级回 live 计算 —— 所以首次预计算前
或 ticker 未覆盖时,页面仍正确(只是慢)。

缓存按 analytics.duckdb mtime 失效(precompute 原子替换 → mtime 变 → 自动刷新)。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS_DB = ROOT / "data" / "analytics.duckdb"


def analytics_mtime() -> float:
    """每次 rerun 读一次;库被 precompute 替换即触发下游 cache 失效。"""
    try:
        return ANALYTICS_DB.stat().st_mtime
    except OSError:
        return 0.0


def is_available() -> bool:
    return ANALYTICS_DB.exists() and analytics_mtime() > 0.0


@st.cache_resource
def _conn(mtime: float):
    if duckdb is None or mtime == 0.0:
        return None
    try:
        return duckdb.connect(str(ANALYTICS_DB), read_only=True)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def wide_table(mtime: float) -> pd.DataFrame:
    """选股页全市场扁平表(screener_wide)。库缺失返回空 DataFrame。"""
    con = _conn(mtime)
    if con is None:
        return pd.DataFrame()
    try:
        return con.execute("SELECT * FROM screener_wide").fetchdf()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _meta(mtime: float) -> dict:
    con = _conn(mtime)
    if con is None:
        return {}
    try:
        rows = con.execute("SELECT key, value FROM meta").fetchall()
        return {k: v for k, v in rows}
    except Exception:
        return {}


def wide_year() -> int | None:
    """screener_wide 预计算时用的财年;库缺失返回 None。"""
    v = _meta(analytics_mtime()).get("year")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def wide_table_for(year: int) -> pd.DataFrame | None:
    """按年份匹配返回选股扁平表。年份不符 / 库缺失 / 空 → None(调用方降级 live)。"""
    if wide_year() != year:
        return None
    df = wide_table(analytics_mtime())
    return df if not df.empty else None


@st.cache_data(ttl=600, show_spinner=False)
def _value_scored(master_id: str, mtime: float) -> pd.DataFrame:
    con = _conn(mtime)
    if con is None or master_id not in ("graham", "buffett"):
        return pd.DataFrame()
    try:
        return con.execute(f"SELECT * FROM value_scored_{master_id}").fetchdf()
    except Exception:
        return pd.DataFrame()


def value_scored_for(master_id: str, year: int) -> pd.DataFrame | None:
    """格雷厄姆/巴菲特价值评分全市场表;年份不符/库缺失/空 → None(降级 live)。"""
    if wide_year() != year:
        return None
    df = _value_scored(master_id, analytics_mtime())
    return df if not df.empty else None


@st.cache_data(ttl=600, show_spinner=False)
def _bundle_bytes(ticker: str, mtime: float) -> bytes | None:
    con = _conn(mtime)
    if con is None or not ticker:
        return None
    try:
        row = con.execute(
            "SELECT payload FROM company_bundle WHERE ticker = ?", [ticker]
        ).fetchone()
        return bytes(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def bundle(ticker: str) -> dict | None:
    """单家公司的预计算 bundle(score / price_range / peers / lynch_metrics)。

    缺失或反序列化失败返回 None → 调用方降级 live 计算。
    """
    raw = _bundle_bytes(ticker, analytics_mtime())
    if raw is None:
        return None
    try:
        return pickle.loads(raw)  # noqa: S301 (本地可信数据)
    except Exception:
        return None


# ─── 便捷访问器 ─────────────────────────────────────────────────────────
def company_score(ticker: str):
    """预计算 CompanyScore(6 维 + 7 大师);缺失返回 None。"""
    b = bundle(ticker)
    return b.get("score") if b else None


def price_range(ticker: str):
    b = bundle(ticker)
    return b.get("price_range") if b else None


def peers(ticker: str) -> list:
    b = bundle(ticker)
    return (b.get("peers") if b else None) or []


def master_matrix_from_store(tickers: list[str]) -> list[dict] | None:
    """从各 ticker 的预计算 bundle.score.masters 组装大师矩阵(替代 sc.master_matrix)。

    任一 ticker 缺 bundle 或 score → 返回 None,调用方降级 live。
    """
    out: list[dict] = []
    for t in tickers:
        b = bundle(t)
        if not b or b.get("score") is None:
            return None
        score = b["score"]
        masters = getattr(score, "masters", None)
        if masters is None:
            return None
        out.append({"ticker": t, "name": getattr(score, "name", t), "masters": masters})
    return out
