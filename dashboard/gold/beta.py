"""金股 ETF · 相对黄金 ETF 滚动 β 计算 · v2.6 主题 3 板块 G

金股 ETF(金矿股 / 黄金股 ETF)相对实物黄金 ETF 通常具有 1.5-2.5 的杠杆放大,
本模块用日**简单收益率**回归算 3 档窗口(30/60/180 日)的 β,以及 60 日窗口的 R²。

口径选择
--------
- 收益率:简单收益 ``R_t = close_t / close_{t-1} - 1``(非对数,贴合金融实务)
- β:``β = Cov(R_stock, R_gold) / Var(R_gold)``,统一用 ``ddof=1`` 样本协方差
  (``np.cov`` 默认 ddof=1,这里改用 ``np.cov(...)[1,1]`` 取分母保证一致)
- 对齐:股票 ETF 与黄金 ETF 按日期 ``inner join``,两边都有 close 才入回归
- R²:60 日窗口标准最小二乘 ``r² = 1 - SS_res / SS_tot``

降级策略
--------
表不存在 / 数据 < 30 obs / 黄金 ETF 缺数据 → 返回的 dataclass 各字段为 None,
``note`` 写原因,**不抛**。

纯函数 — 不依赖 streamlit,可离线测试。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD_DB = ROOT / "data" / "gold.duckdb"

WINDOWS = (30, 60, 180)
LOOKBACK_DAYS = 300  # 拉的原始 close 行数(>180 留缓冲)


@dataclass(frozen=True)
class GoldStockBeta:
    """单只金股 ETF 的 β 结果。

    Attributes
    ----------
    etf_code : str
        金股 ETF 代码(如 ``"159562"``)
    beta_30d / beta_60d / beta_180d : Optional[float]
        三档窗口 β;窗口内有效对齐观测 < 窗口长度时为 None
    r_squared_60d : Optional[float]
        60 日窗口拟合优度,主仓口径;None 同上
    as_of : date
        计算基准日(默认今天)
    n_obs_max : int
        最长窗口(180)实际对齐观测数,诊断用
    note : str
        降级原因(数据不足 / 表缺失 / 等)
    """
    etf_code: str
    beta_30d: Optional[float]
    beta_60d: Optional[float]
    beta_180d: Optional[float]
    r_squared_60d: Optional[float]
    as_of: _date
    n_obs_max: int
    note: str = ""


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    rows = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='main' AND table_name=?",
        [table_name],
    ).fetchall()
    return bool(rows)


def _load_prices(con: duckdb.DuckDBPyConnection,
                 etf_code: str,
                 table: str,
                 lookback_days: int = LOOKBACK_DAYS,
                 as_of: Optional[_date] = None) -> pd.DataFrame:
    """读 (date, close);倒序取 lookback_days 行,返回按日期升序的 DataFrame。

    表不存在 / 没数据 → 返回空 DataFrame(不抛)。
    """
    if not _table_exists(con, table):
        return pd.DataFrame(columns=["date", "close"])

    if as_of is None:
        as_of_str = "9999-12-31"
    else:
        as_of_str = as_of.isoformat()

    rows = con.execute(
        f"""
        SELECT date, close
        FROM {table}
        WHERE etf_code = ? AND date <= CAST(? AS DATE) AND close IS NOT NULL
        ORDER BY date DESC
        LIMIT ?
        """,
        [etf_code, as_of_str, int(lookback_days)],
    ).fetchall()

    if not rows:
        return pd.DataFrame(columns=["date", "close"])

    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    return df


def _to_returns(df: pd.DataFrame) -> pd.DataFrame:
    """加一列 ret(简单日收益),首行 NaN 已剔除。"""
    if df.empty or len(df) < 2:
        return pd.DataFrame(columns=["date", "close", "ret"])
    out = df.copy()
    out["ret"] = out["close"].pct_change()
    out = out.dropna(subset=["ret"]).reset_index(drop=True)
    return out


def _beta_one_window(r_stock: np.ndarray, r_gold: np.ndarray) -> Optional[float]:
    """β = Cov / Var,统一 ddof=1。obs<2 或 Var=0 返回 None。"""
    if r_stock.size < 2 or r_gold.size < 2:
        return None
    cov_mat = np.cov(r_stock, r_gold, ddof=1)  # 2x2
    var_gold = cov_mat[1, 1]
    if not np.isfinite(var_gold) or var_gold <= 0.0:
        return None
    beta = cov_mat[0, 1] / var_gold
    if not np.isfinite(beta):
        return None
    return float(beta)


def _r_squared(r_stock: np.ndarray, r_gold: np.ndarray, beta: float) -> Optional[float]:
    """OLS R² with intercept(α 用样本均值消掉)。"""
    if r_stock.size < 2:
        return None
    alpha = float(np.mean(r_stock) - beta * np.mean(r_gold))
    pred = alpha + beta * r_gold
    ss_res = float(np.sum((r_stock - pred) ** 2))
    ss_tot = float(np.sum((r_stock - np.mean(r_stock)) ** 2))
    if ss_tot <= 0.0 or not np.isfinite(ss_tot):
        return None
    r2 = 1.0 - ss_res / ss_tot
    if not np.isfinite(r2):
        return None
    # 数值上可能略 < 0 或略 > 1,裁剪到 [0, 1] 更稳
    return float(max(0.0, min(1.0, r2)))


def compute_beta(stock_etf_code: str,
                 gold_etf_code: str = "518880",
                 db_path: Path = GOLD_DB,
                 as_of: Optional[_date] = None) -> GoldStockBeta:
    """主入口:算单只金股 ETF 三档 β + 60 日 R²。

    Parameters
    ----------
    stock_etf_code : str
        金股 ETF 代码
    gold_etf_code : str
        参考实物黄金 ETF 代码,默认主仓 518880
    db_path : Path
        gold.duckdb 路径(测试可指向 tmp_path)
    as_of : date | None
        基准日;None=不限,取最新可得 close
    """
    today = as_of if as_of is not None else datetime.now().date()

    if not Path(db_path).exists():
        return GoldStockBeta(
            etf_code=stock_etf_code,
            beta_30d=None, beta_60d=None, beta_180d=None,
            r_squared_60d=None, as_of=today, n_obs_max=0,
            note=f"DB 不存在: {db_path}",
        )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df_stock = _load_prices(con, stock_etf_code,
                                "gold_stock_etf_prices",
                                LOOKBACK_DAYS, as_of)
        df_gold = _load_prices(con, gold_etf_code,
                               "gold_etf_prices",
                               LOOKBACK_DAYS, as_of)
    finally:
        con.close()

    if df_stock.empty:
        return GoldStockBeta(
            etf_code=stock_etf_code,
            beta_30d=None, beta_60d=None, beta_180d=None,
            r_squared_60d=None, as_of=today, n_obs_max=0,
            note="缺数据: gold_stock_etf_prices 表无该 ETF 或表不存在",
        )
    if df_gold.empty:
        return GoldStockBeta(
            etf_code=stock_etf_code,
            beta_30d=None, beta_60d=None, beta_180d=None,
            r_squared_60d=None, as_of=today, n_obs_max=0,
            note=f"缺数据: gold_etf_prices 无 {gold_etf_code}",
        )

    rs = _to_returns(df_stock).rename(columns={"ret": "r_stock"})[["date", "r_stock"]]
    rg = _to_returns(df_gold).rename(columns={"ret": "r_gold"})[["date", "r_gold"]]
    merged = rs.merge(rg, on="date", how="inner").sort_values("date").reset_index(drop=True)
    n_total = len(merged)

    if n_total < min(WINDOWS):  # < 30
        return GoldStockBeta(
            etf_code=stock_etf_code,
            beta_30d=None, beta_60d=None, beta_180d=None,
            r_squared_60d=None, as_of=today, n_obs_max=n_total,
            note=f"缺数据: 对齐观测数 {n_total} < 30",
        )

    betas: dict[int, Optional[float]] = {}
    for w in WINDOWS:
        if n_total >= w:
            tail = merged.tail(w)
            betas[w] = _beta_one_window(
                tail["r_stock"].to_numpy(dtype=float),
                tail["r_gold"].to_numpy(dtype=float),
            )
        else:
            betas[w] = None

    # R² 用 60 日(若不足则 None)
    r2 = None
    if betas[60] is not None and n_total >= 60:
        tail = merged.tail(60)
        r2 = _r_squared(
            tail["r_stock"].to_numpy(dtype=float),
            tail["r_gold"].to_numpy(dtype=float),
            betas[60],
        )

    return GoldStockBeta(
        etf_code=stock_etf_code,
        beta_30d=betas[30],
        beta_60d=betas[60],
        beta_180d=betas[180],
        r_squared_60d=r2,
        as_of=today,
        n_obs_max=n_total,
        note="" if n_total >= max(WINDOWS) else f"对齐观测 {n_total} 不足 180,长窗口已降级",
    )


def compute_all(db_path: Path = GOLD_DB,
                gold_etf_code: str = "518880",
                as_of: Optional[_date] = None) -> list[GoldStockBeta]:
    """对 gold_stock_etf_master 里所有 ETF 批量算 β。

    master 表不存在或为空 → 返回 []。
    """
    if not Path(db_path).exists():
        return []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if not _table_exists(con, "gold_stock_etf_master"):
            return []
        rows = con.execute(
            "SELECT etf_code FROM gold_stock_etf_master ORDER BY etf_code"
        ).fetchall()
    finally:
        con.close()

    codes = [r[0] for r in rows if r and r[0]]
    return [compute_beta(c, gold_etf_code=gold_etf_code,
                         db_path=db_path, as_of=as_of) for c in codes]


__all__ = ["GoldStockBeta", "compute_beta", "compute_all"]
