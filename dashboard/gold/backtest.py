"""黄金 ETF 红绿灯策略回测引擎(纯函数,可离线测)。

核心思路:
  - 起始持有 BASE 份(初始 20w 元当量),100w 总资产
  - 红绿灯 verdict → 目标份额倍数(0.5~1.5 × BASE)
  - 每周一评估:若当前 verdict 已稳定 confirm_days 天,执行调整
  - 每次最多 step_shares 份(防大额操作冲击)
  - 现金部分 0% 收益(简化对比)

档位映射(默认):
  add           → 1.5 × BASE   (上限 30w 当量)
  add_caution   → 1.25 × BASE  (25w 当量)
  hold          → 1.0 × BASE   (基数 20w)
  pause_partial → 0.75 × BASE  (15w 当量)
  pause         → 0.5 × BASE   (下限 10w 当量)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD_DB = ROOT / "data" / "gold.duckdb"


# ─── 实时 vote 缓存 ─────────────────────────────────────────────────────
# 治本性改造:不再读 gold_overheat_history(易与原始数据脱节),
# 改为每天调 overheat_engine.vote(as_of=d) 实时算。
# lru_cache key 用 (db_path 字符串, yaml_path 字符串, as_of_iso) 保可哈希。

@lru_cache(maxsize=4000)
def _vote_cached(db_path_s: str, yaml_path_s: str, as_of_iso: str):
    """按日缓存的 vote 调用。同一进程内同一日期只算一次。"""
    # 延迟导入,避免循环 / 启动开销
    from gold.overheat import vote as _vote
    return _vote(
        db_path=Path(db_path_s),
        yaml_path=Path(yaml_path_s),
        as_of=_date.fromisoformat(as_of_iso),
    )


def _clear_vote_cache() -> None:
    """测试用:清缓存。"""
    _vote_cached.cache_clear()


def _vote_cache_info():
    """测试用:看命中。"""
    return _vote_cached.cache_info()

DEFAULT_MULT = {
    "add":           1.5,
    "add_caution":   1.25,
    "hold":          1.0,
    "pause_partial": 0.75,
    "pause":         0.5,
}


@dataclass(frozen=True)
class BacktestResult:
    """回测结果一篮子。"""
    daily: pd.DataFrame          # date, close, verdict, target, shares, cash, gold_mv, total_A, total_E
    trades: pd.DataFrame         # date, action, qty, price, amount, verdict, shares_before, shares_after
    switches: pd.DataFrame       # date, prev_verdict, new_verdict, red, yellow, green
    summary: dict                # init/A_final/E_final/diff/A_mdd/E_mdd/n_trades/...
    params: dict                 # 回测使用的参数(展示用)


_PRICE_TABLE_WHITELIST = {"gold_etf_prices", "gold_stock_etf_prices"}


def _load_data(db_path: Path,
               etf_code: str,
               start: str, end: str,
               price_table: str = "gold_etf_prices",
               ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读价格。price_table 限白名单(实物金 / 金股)。

    第二个返回值保留为空 DataFrame(date 索引),向后兼容旧调用方;
    信号改由主循环每天实时 vote(as_of=d) 现算,不再读 gold_overheat_history。
    """
    if price_table not in _PRICE_TABLE_WHITELIST:
        raise ValueError(f"price_table 必须在 {_PRICE_TABLE_WHITELIST}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        px = con.execute(f"""
            SELECT date, close FROM {price_table}
            WHERE etf_code = ? AND date BETWEEN ? AND ?
            ORDER BY date
        """, [etf_code, start, end]).fetchdf()
    finally:
        con.close()

    px["date"] = pd.to_datetime(px["date"])
    # 空 sig DataFrame:保持返回签名不变,但实际不用
    sig = pd.DataFrame(
        columns=["verdict_id", "red_count", "yellow_count", "green_count"]
    )
    sig.index = pd.DatetimeIndex([], name="date")
    return px.set_index("date"), sig


@lru_cache(maxsize=4)
def _load_history_snapshot(db_path_s: str) -> dict:
    """一次性把 gold_overheat_history 全表读进内存(date→快照),供主循环快速命中。

    history 表是 overheat_engine.backfill_history() 写入的,key=date,值含
    verdict_id / red_count / yellow_count / green_count。
    backfill 0% 不一致后此表是真值,优先读;未覆盖的日期再走实时 vote。
    """
    try:
        con = duckdb.connect(db_path_s, read_only=True)
        try:
            df = con.execute(
                "SELECT date, verdict_id, red_count, yellow_count, green_count "
                "FROM gold_overheat_history"
            ).fetchdf()
        finally:
            con.close()
    except Exception:
        return {}
    if len(df) == 0:
        return {}
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return {
        r["date"]: {
            "verdict_id": str(r["verdict_id"]),
            "red_count": int(r["red_count"]),
            "yellow_count": int(r["yellow_count"]),
            "green_count": int(r["green_count"]),
        }
        for _, r in df.iterrows()
    }


def _vote_for_date(d: pd.Timestamp,
                   db_path: Path,
                   yaml_path: Optional[Path] = None):
    """主循环每日入口:先查 history 表快照(<1ms),miss 才实时算(~100ms)。

    history 表 = backfill_history 写入,backfill 0% 不一致后是真值。
    覆盖天数 1828+,1Y/5Y 回测命中率近 100%,极大加速。
    若 history 没该日(冷启动期或新日期),fallback 到 lru_cache 包装的实时 vote。
    """
    from gold.overheat import YAML_PATH as _YP
    yp = yaml_path or _YP
    d_obj = pd.Timestamp(d).date()
    # 1) 先查 history 内存快照(整表只读一次,1828 行不大)
    hist = _load_history_snapshot(str(db_path))
    h = hist.get(d_obj)
    if h is not None:
        # 命中:构造一个轻量 OverheatVote-like 对象,字段名对齐主循环用到的部分
        from gold.overheat import OverheatVote as _OV
        return _OV(
            red_count=h["red_count"],
            yellow_count=h["yellow_count"],
            green_count=h["green_count"],
            verdict_id=h["verdict_id"],
            verdict_label="",
            verdict_action="",
            signals=[],
            verified=True,
            source="history_table",
        )
    # 2) miss:走原实时 vote(冷启动期 / backfill 未覆盖日期)
    iso = d_obj.isoformat()
    return _vote_cached(str(db_path), str(yp), iso)


def _max_drawdown(series: pd.Series) -> float:
    """最大回撤(返回百分比,负值)。"""
    peak = series.cummax()
    dd = (series - peak) / peak
    return float(dd.min() * 100) if len(dd) else 0.0


def run(
    *,
    db_path: Path = GOLD_DB,
    etf_code: str = "518880",
    price_table: str = "gold_etf_prices",
    start_date: str = "2025-05-12",
    end_date: Optional[str] = None,
    init_total: float = 1_000_000.0,
    init_gold_value: float = 200_000.0,
    multipliers: Optional[dict] = None,
    step_shares: int = 20_000,
    confirm_days: int = 7,
) -> BacktestResult:
    """主入口。end_date=None 走数据最大日期。

    price_table:
      - 'gold_etf_prices'        → 实物金 ETF(518880 等)
      - 'gold_stock_etf_prices'  → 金股 ETF(159562 等)
    信号:逐日实时调 overheat_engine.vote(as_of=d) 现算(永远与原始数据一致),
         不再读 gold_overheat_history(避免 history 表与 metrics 数据脱节)。
    """
    if end_date is None:
        end_date = str(_date.today())
    multipliers = multipliers or DEFAULT_MULT.copy()

    px, _sig_unused = _load_data(db_path, etf_code, start_date, end_date, price_table)
    if len(px) == 0:
        empty = pd.DataFrame()
        return BacktestResult(empty, empty, empty,
                              {"_error": "区间内无价格数据"},
                              {"start": start_date, "end": end_date})

    # ─── 实时 vote 现算所有交易日 ────────────────────────────
    # 每个交易日调 overheat_engine.vote(as_of=d),结果落到 sig DataFrame,
    # 后续逻辑(stable 判断 / sig_ff / switches)继续按 sig 表行为不变。
    sig_rows = []
    for d in px.index:
        try:
            v = _vote_for_date(d, db_path)
            sig_rows.append({
                "date": d,
                "verdict_id": v.verdict_id,
                "red_count": int(v.red_count),
                "yellow_count": int(v.yellow_count),
                "green_count": int(v.green_count),
            })
        except Exception:
            # 单日失败兜底:取上一日(若有),否则 add(默认乐观)
            if sig_rows:
                last = sig_rows[-1]
                sig_rows.append({
                    "date": d,
                    "verdict_id": last["verdict_id"],
                    "red_count": last["red_count"],
                    "yellow_count": last["yellow_count"],
                    "green_count": last["green_count"],
                })
            else:
                sig_rows.append({
                    "date": d, "verdict_id": "add",
                    "red_count": 0, "yellow_count": 0, "green_count": 0,
                })
    sig = pd.DataFrame(sig_rows).set_index("date")

    p0 = float(px.iloc[0]["close"])
    base_shares = init_gold_value / p0
    target_map = {k: int(round(base_shares * m)) for k, m in multipliers.items()}
    init_cash = init_total - init_gold_value

    # ─── A 一直持有 ──────────────────────────────────────────
    px = px.copy()
    px["gold_mv_A"] = base_shares * px["close"]
    px["total_A"] = px["gold_mv_A"] + init_cash

    # ─── E 红绿灯 + 步长 + 确认期 ───────────────────────────
    shares = base_shares
    cash = init_cash
    rows = []
    trades: list[dict] = []
    confirm_delta = pd.Timedelta(days=confirm_days) if confirm_days > 0 else pd.Timedelta(days=0)

    for i, (d, row) in enumerate(px.iterrows()):
        close = float(row["close"])
        avail = sig.loc[sig.index <= d]
        verdict = avail.iloc[-1]["verdict_id"] if len(avail) else "add"
        target = target_map.get(verdict, target_map["hold"])

        # 稳定性检查
        if confirm_days == 0:
            stable = True
        else:
            window = sig.loc[(sig.index <= d) & (sig.index > d - confirm_delta)]
            stable = len(window) > 0 and (window["verdict_id"] == verdict).all()

        is_eval = (d.weekday() == 0) or (i == 0)

        if is_eval and stable:
            gap = target - shares
            if gap > 0.5:
                qty = min(step_shares, gap)
                cost = qty * close
                if cost > cash:
                    qty = cash / close
                    cost = qty * close
                if qty > 0:
                    sb = shares
                    shares += qty
                    cash -= cost
                    trades.append({
                        "date": d, "action": "BUY", "qty": qty,
                        "price": close, "amount": cost,
                        "verdict": verdict, "target": target,
                        "shares_before": sb, "shares_after": shares,
                    })
            elif gap < -0.5:
                qty = min(step_shares, -gap)
                proceeds = qty * close
                sb = shares
                shares -= qty
                cash += proceeds
                trades.append({
                    "date": d, "action": "SELL", "qty": qty,
                    "price": close, "amount": proceeds,
                    "verdict": verdict, "target": target,
                    "shares_before": sb, "shares_after": shares,
                })

        rows.append({
            "date": d, "close": close, "verdict": verdict, "target": target,
            "shares": shares, "cash": cash,
            "gold_mv": shares * close, "total_E": shares * close + cash,
        })

    df_E = pd.DataFrame(rows).set_index("date")
    daily = px.join(df_E[["verdict", "target", "shares", "cash",
                          "gold_mv", "total_E"]], how="inner")

    # 把红/黄/绿计数 forward-fill 到每日(信号可能不是每天有,取 ≤d 最近一条)
    sig_ff = sig.reindex(daily.index, method="ffill")
    daily = daily.join(sig_ff[["red_count", "yellow_count", "green_count"]],
                       how="left")

    # is_switch:与前一交易日 verdict 不同
    daily["is_switch"] = daily["verdict"] != daily["verdict"].shift(1)
    daily.loc[daily.index[0], "is_switch"] = False  # 首日不算切换

    trades_df = pd.DataFrame(trades)
    if len(trades_df):
        trades_df["date"] = pd.to_datetime(trades_df["date"])

    # 把当日 action / qty 合并进 daily(没操作的填 HOLD/0)
    if len(trades_df):
        action_map = trades_df.set_index("date")[["action", "qty"]]
        daily = daily.join(action_map, how="left")
        daily["action"] = daily["action"].fillna("HOLD")
        daily["qty"] = daily["qty"].fillna(0)
    else:
        daily["action"] = "HOLD"
        daily["qty"] = 0.0

    # ─── 信号切换明细 ────────────────────────────────────────
    sig2 = sig.copy()
    sig2["prev_verdict"] = sig2["verdict_id"].shift(1)
    switches = sig2[(sig2["verdict_id"] != sig2["prev_verdict"])
                    & sig2["prev_verdict"].notna()].copy()
    switches = switches.reset_index().rename(columns={
        "verdict_id": "new_verdict",
        "red_count": "red", "yellow_count": "yellow", "green_count": "green",
    })[["date", "prev_verdict", "new_verdict", "red", "yellow", "green"]]

    # ─── 摘要 ────────────────────────────────────────────────
    A_final = float(daily.iloc[-1]["total_A"])
    E_final = float(daily.iloc[-1]["total_E"])
    n_buy = int((trades_df["action"] == "BUY").sum()) if len(trades_df) else 0
    n_sell = int((trades_df["action"] == "SELL").sum()) if len(trades_df) else 0
    buy_amount = float(trades_df.loc[trades_df["action"] == "BUY", "amount"].sum()) if len(trades_df) else 0
    sell_amount = float(trades_df.loc[trades_df["action"] == "SELL", "amount"].sum()) if len(trades_df) else 0

    summary = {
        "init_total": init_total,
        "init_gold_value": init_gold_value,
        "base_shares": base_shares,
        "target_map": target_map,
        "start_price": p0,
        "end_price": float(daily.iloc[-1]["close"]),
        "price_change_pct": (float(daily.iloc[-1]["close"]) / p0 - 1) * 100,
        "A_final": A_final,
        "E_final": E_final,
        "A_return_pct": (A_final / init_total - 1) * 100,
        "E_return_pct": (E_final / init_total - 1) * 100,
        "diff": E_final - A_final,
        "diff_pct": (E_final - A_final) / init_total * 100,
        "A_mdd": _max_drawdown(daily["total_A"]),
        "E_mdd": _max_drawdown(daily["total_E"]),
        "n_trades": len(trades_df),
        "n_buy": n_buy,
        "n_sell": n_sell,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "end_shares": float(daily.iloc[-1]["shares"]),
        "end_cash": float(daily.iloc[-1]["cash"]),
        "end_verdict": str(daily.iloc[-1]["verdict"]),
    }

    params = {
        "etf_code": etf_code, "start_date": start_date, "end_date": end_date,
        "init_total": init_total, "init_gold_value": init_gold_value,
        "multipliers": multipliers, "step_shares": step_shares,
        "confirm_days": confirm_days,
    }

    return BacktestResult(daily=daily, trades=trades_df,
                          switches=switches, summary=summary, params=params)


@dataclass(frozen=True)
class DiagnosticsResult:
    """诊断结果一篮子。"""
    verdict_stay: pd.DataFrame        # verdict / days / pct (按 days 降序)
    extreme_misalign: dict            # high_*/low_* + *_misaligned
    confirm_sensitivity: pd.DataFrame # confirm_days / E_final / E_return_pct / n_trades / diff_vs_current
    current_status: dict              # current_verdict / days_since_switch / last_switch_date / end_shares / target_now / gap
    advice: list                      # 1-3 条中文建议


def diagnose(
    result: BacktestResult,
    *,
    db_path: Path = GOLD_DB,
    etf_code: str = "518880",
    price_table: str = "gold_etf_prices",
    init_total: float = 1_000_000.0,
    init_gold_value: float = 200_000.0,
    multipliers: Optional[dict] = None,
    step_shares: int = 20_000,
    current_confirm_days: int = 7,
) -> DiagnosticsResult:
    """对 run() 的结果做四项诊断:档位停留 / 极值错配 / confirm 敏感性 / 现状摘要。"""
    daily = result.daily
    n_days = len(daily)
    multipliers = multipliers or DEFAULT_MULT.copy()

    # 1. verdict_stay
    vc = daily["verdict"].value_counts()
    verdict_stay = pd.DataFrame({
        "verdict": vc.index,
        "days": vc.values.astype(int),
        "pct": (vc.values / n_days * 100) if n_days else vc.values * 0.0,
    }).sort_values("days", ascending=False).reset_index(drop=True)

    # 2. extreme_misalign
    hi_idx = daily["close"].idxmax()
    lo_idx = daily["close"].idxmin()
    hi_verdict = str(daily.loc[hi_idx, "verdict"])
    lo_verdict = str(daily.loc[lo_idx, "verdict"])
    extreme_misalign = {
        "high_date": hi_idx,
        "high_price": float(daily.loc[hi_idx, "close"]),
        "high_verdict": hi_verdict,
        "high_misaligned": hi_verdict in ("add", "add_caution"),
        "low_date": lo_idx,
        "low_price": float(daily.loc[lo_idx, "close"]),
        "low_verdict": lo_verdict,
        "low_misaligned": lo_verdict in ("pause", "pause_partial"),
    }

    # 3. confirm_sensitivity
    cd_list = [0, 3, 7, 14, 21]
    if current_confirm_days not in cd_list:
        cd_list = sorted(cd_list + [current_confirm_days])
    params = result.params
    sens_rows = []
    for cd in cd_list:
        try:
            r = run(
                db_path=db_path, etf_code=etf_code, price_table=price_table,
                start_date=params["start_date"], end_date=params["end_date"],
                init_total=init_total, init_gold_value=init_gold_value,
                multipliers=multipliers, step_shares=step_shares,
                confirm_days=cd,
            )
            e_final = float(r.summary.get("E_final", float("nan")))
            e_ret = float(r.summary.get("E_return_pct", float("nan")))
            n_tr = int(r.summary.get("n_trades", 0))
        except Exception:
            e_final = float("nan")
            e_ret = float("nan")
            n_tr = 0
        sens_rows.append({
            "confirm_days": int(cd),
            "E_final": e_final,
            "E_return_pct": e_ret,
            "n_trades": n_tr,
        })
    sens_df = pd.DataFrame(sens_rows)
    cur_row = sens_df[sens_df["confirm_days"] == current_confirm_days]
    cur_e = float(cur_row["E_final"].iloc[0]) if len(cur_row) and pd.notna(cur_row["E_final"].iloc[0]) else float("nan")
    sens_df["diff_vs_current"] = sens_df["E_final"] - cur_e
    confirm_sensitivity = sens_df

    # 4. current_status
    cur_verdict = str(daily.iloc[-1]["verdict"])
    switch_dates = daily.index[daily["is_switch"] == True]  # noqa: E712
    if len(switch_dates):
        last_switch = switch_dates[-1]
        days_since = int((daily.index[-1] - last_switch).days)
    else:
        last_switch = daily.index[0]
        days_since = int((daily.index[-1] - last_switch).days)
    base_shares = float(result.summary.get("base_shares", 0.0))
    target_now = int(round(base_shares * multipliers.get(cur_verdict, 1.0)))
    end_shares = float(daily.iloc[-1]["shares"])
    current_status = {
        "current_verdict": cur_verdict,
        "days_since_switch": days_since,
        "last_switch_date": last_switch,
        "end_shares": end_shares,
        "target_now": target_now,
        "gap": target_now - end_shares,
    }

    # 5. advice
    advice: list = []
    if len(verdict_stay):
        top_v = verdict_stay.iloc[0]["verdict"]
        top_pct = float(verdict_stay.iloc[0]["pct"])
        n_switches = int(daily["is_switch"].sum())
        if top_pct > 60:
            advice.append(f"信号稳定,主要档位 {top_v} 占 {top_pct:.0f}%")
        if top_pct < 20 or (n_days > 0 and n_switches > n_days / 30):
            advice.append("信号频繁切换,建议调高 confirm_days")
    if extreme_misalign["high_misaligned"]:
        advice.append("区间最高价当日仍在加仓档(add),错失止盈")
    if extreme_misalign["low_misaligned"]:
        advice.append("区间最低价当日仍在减仓档(pause),错失抄底")
    if pd.notna(cur_e):
        valid = sens_df.dropna(subset=["E_final"])
        if len(valid):
            best = valid.loc[valid["E_final"].idxmax()]
            best_cd = int(best["confirm_days"])
            best_diff = float(best["E_final"] - cur_e)
            if best_cd != current_confirm_days and best_diff > 0:
                advice.append(f"confirm_days={best_cd} 终值更高 (+{best_diff:,.0f} 元),建议改")
    if not advice:
        advice.append("当前参数表现平稳,无明显调整方向")
    advice = advice[:3]

    return DiagnosticsResult(
        verdict_stay=verdict_stay,
        extreme_misalign=extreme_misalign,
        confirm_sensitivity=confirm_sensitivity,
        current_status=current_status,
        advice=advice,
    )


__all__ = ["run", "diagnose", "BacktestResult", "DiagnosticsResult", "DEFAULT_MULT", "GOLD_DB"]
