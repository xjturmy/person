"""决策日志 → 交易级账本(单 ticker)。

数据源:decisions.duckdb / decisions 表(see .tools/decisions/db.py)

字段映射(决策表 weight_change 是占组合权重的 Δ,本模块按"金额近似 = |Δ权重| × 总市值"反推):
    - action ∈ {买入, 加仓}     → 买入侧
    - action ∈ {减仓, 清仓}     → 卖出侧
    - action == 观察            → 忽略
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

BUY_ACTIONS = {"买入", "加仓"}
SELL_ACTIONS = {"减仓", "清仓"}


@dataclass
class TradeLedger:
    """单 ticker 交易级账本。"""
    trades: pd.DataFrame                # 列: date / action / price / weight_change / est_amount / est_shares
    total_buy_amount: float             # Σ 估算买入金额
    total_sell_amount: float            # Σ 估算卖出金额
    net_amount: float                   # 净投入(买 - 卖)
    realized_pnl: float                 # 已实现损益(粗算:卖出金额 - 卖出股数 × 移动平均买入成本)
    avg_buy_price: Optional[float]      # 加权平均买入价(按估算金额)
    n_buys: int
    n_sells: int


def _load_decisions_for_ticker(ticker: str):
    """读 decisions.duckdb 单 ticker 全部决策(读写隔离用 read_only)。"""
    import sys
    here = Path(__file__).resolve()
    tools_root = here.parents[2]
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))
    from decisions import db as _ddb  # type: ignore
    df = _ddb.list_by_ticker(ticker)
    return df


def compute_trade_ledger(ticker: str, total_mv: Optional[float] = None) -> TradeLedger:
    """对单 ticker 装配交易账本。

    Args:
        ticker:股票代码
        total_mv:当前组合总市值,用于把 weight_change 反推成估算金额。
                 None 时金额列为 NaN,但 trades / n_buys / n_sells 仍可用。
    """
    df = _load_decisions_for_ticker(ticker)
    if df is None or df.empty:
        return TradeLedger(
            trades=pd.DataFrame(),
            total_buy_amount=0.0, total_sell_amount=0.0,
            net_amount=0.0, realized_pnl=0.0,
            avg_buy_price=None, n_buys=0, n_sells=0,
        )

    df = df.copy()
    df = df[df["action"].isin(BUY_ACTIONS | SELL_ACTIONS)]
    if df.empty:
        return TradeLedger(
            trades=pd.DataFrame(),
            total_buy_amount=0.0, total_sell_amount=0.0,
            net_amount=0.0, realized_pnl=0.0,
            avg_buy_price=None, n_buys=0, n_sells=0,
        )

    df = df.sort_values("date").reset_index(drop=True)

    # 估算金额 = |Δ权重| × 总市值
    if total_mv:
        df["est_amount"] = df["weight_change"].abs() * total_mv
    else:
        df["est_amount"] = float("nan")

    # 估算股数 = 金额 / 价格
    df["est_shares"] = df.apply(
        lambda r: (r["est_amount"] / r["price"]) if (pd.notna(r["est_amount"]) and r["price"]) else float("nan"),
        axis=1,
    )

    buys = df[df["action"].isin(BUY_ACTIONS)]
    sells = df[df["action"].isin(SELL_ACTIONS)]

    total_buy = float(buys["est_amount"].sum(skipna=True)) if not buys.empty else 0.0
    total_sell = float(sells["est_amount"].sum(skipna=True)) if not sells.empty else 0.0
    net = total_buy - total_sell

    # 加权平均买入价(用估算金额做权重)
    if not buys.empty and buys["est_amount"].sum() > 0:
        avg_buy = float((buys["price"] * buys["est_amount"]).sum() / buys["est_amount"].sum())
    else:
        avg_buy = None

    # 已实现损益(粗算):Σ (sell_price - avg_buy) × est_shares
    realized = 0.0
    if avg_buy is not None and not sells.empty:
        realized = float(((sells["price"] - avg_buy) * sells["est_shares"]).sum(skipna=True))

    # 友好列名给 UI
    view = df[["date", "action", "price", "weight_change", "est_amount", "est_shares", "rationale"]].copy()
    view["距今天数"] = (pd.Timestamp.today().normalize() - pd.to_datetime(view["date"])).dt.days
    view = view.rename(columns={
        "date": "日期", "action": "动作", "price": "价格",
        "weight_change": "Δ权重", "est_amount": "估算金额",
        "est_shares": "估算股数", "rationale": "理由",
    })
    # 按日期倒序展示
    view = view.sort_values("日期", ascending=False).reset_index(drop=True)

    return TradeLedger(
        trades=view,
        total_buy_amount=total_buy,
        total_sell_amount=total_sell,
        net_amount=net,
        realized_pnl=realized,
        avg_buy_price=avg_buy,
        n_buys=int(len(buys)),
        n_sells=int(len(sells)),
    )


__all__ = ["TradeLedger", "compute_trade_ledger", "BUY_ACTIONS", "SELL_ACTIONS"]
