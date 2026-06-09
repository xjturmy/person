"""黄金短期过热信号引擎 · v2.4 step-D

读 `.tools/rules/gold_overheat.yaml`,对 6 信号逐一评估"红/黄/绿"3 档,
按 verdict_rules 决定综合判定(暂停/持有/加仓)。

替代 paradigm_engine.py 的"长期主导身份"短期对偶 — 长期主导回答 "买不买",
本引擎回答"今天该不该追"。

8 种 source 类型:
- etf_turnover     — gold_etf_prices 最近 N 日 turnover_rate 4 ETF 加权均
- etf_volume_ratio — gold_etf_prices 5 日均 volume / 60 日均 volume(单 ETF 518880 主仓)
- rsi              — gold_metrics indicator 算 RSI-14
- ma_deviation     — gold_metrics indicator close vs MA60 偏离 %
- etf_share_change — gold_etf_share 最新 share_change_5d 4 ETF 均值
- duckdb_indicator — gold_metrics indicator 截至 as_of 最新值(可选 abs / window_mean / lookback_days)
- not_implemented  — 走 manual_value + default_state
- duckdb_query     — 自定义 SQL 兜底(不支持 as_of)

判定语法:
- red_when_gt:    > 红线 → red
- yellow_when_gte: ≥ 黄线 → yellow
- (都不命中)       → green
- (current None)   → default_state(默认 green)

写入 gold_overheat_history(每周一行)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any, Optional

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[3]
GOLD_DB = ROOT / "data" / "gold.duckdb"
YAML_PATH = ROOT / ".tools" / "rules" / "gold_overheat.yaml"


# ─── 数据类 ─────────────────────────────────────────────────────────────


@dataclass
class OverheatSignal:
    signal_id: str
    name: str
    current_value: Any
    state: str               # "red" / "yellow" / "green" / "unknown"
    threshold_str: str       # 阈值描述(给 UI)
    source: str
    note: str = ""
    unit: str = ""

    @property
    def emoji(self) -> str:
        return {"red": "🔴", "yellow": "🟡", "green": "🟢",
                "unknown": "⚪"}.get(self.state, "⚪")

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["current_value"] = (str(d["current_value"])
                              if d["current_value"] is not None else None)
        d["emoji"] = self.emoji
        return d


@dataclass
class OverheatVote:
    red_count: int
    yellow_count: int
    green_count: int
    verdict_id: str
    verdict_label: str
    verdict_action: str
    signals: list[OverheatSignal] = field(default_factory=list)
    verified: bool = True
    source: str = "overheat_engine_v1"
    unknown_count: int = 0   # 冷启动期保护:窗口未满的信号数

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["signals"] = [s.to_dict() for s in d["signals"]]
        return d


# ─── 配置 ───────────────────────────────────────────────────────────────


def load_config(path: Path = YAML_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── 信号取值 ───────────────────────────────────────────────────────────


def _read_etf_turnover_avg(con: duckdb.DuckDBPyConnection,
                           lookback_days: int = 7,
                           as_of: Optional[_date] = None) -> Optional[float]:
    """4 ETF 截至 as_of(默认最新)那一日的 turnover_rate 平均。"""
    if as_of is None:
        rows = con.execute("""
            WITH latest AS (
                SELECT etf_code, MAX(date) AS d FROM gold_etf_prices
                WHERE turnover_rate IS NOT NULL
                GROUP BY etf_code
            )
            SELECT AVG(p.turnover_rate)
            FROM gold_etf_prices p JOIN latest l
              ON p.etf_code = l.etf_code AND p.date = l.d
        """).fetchone()
    else:
        rows = con.execute("""
            WITH latest AS (
                SELECT etf_code, MAX(date) AS d FROM gold_etf_prices
                WHERE turnover_rate IS NOT NULL AND date <= ?
                GROUP BY etf_code
            )
            SELECT AVG(p.turnover_rate)
            FROM gold_etf_prices p JOIN latest l
              ON p.etf_code = l.etf_code AND p.date = l.d
        """, [as_of]).fetchone()
    return float(rows[0]) if rows and rows[0] is not None else None


def _read_etf_volume_ratio(con: duckdb.DuckDBPyConnection,
                           etf_code: str = "518880",
                           as_of: Optional[_date] = None) -> Optional[float]:
    """主仓 ETF 截至 as_of 的 5 日均成交量 / 60 日均成交量。"""
    if as_of is None:
        row = con.execute("""
            SELECT
                AVG(volume) FILTER (WHERE rn <= 5) AS v5,
                AVG(volume) FILTER (WHERE rn <= 60) AS v60
            FROM (
                SELECT volume,
                       ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM gold_etf_prices
                WHERE etf_code = ? AND volume IS NOT NULL
            )
        """, [etf_code]).fetchone()
    else:
        row = con.execute("""
            SELECT
                AVG(volume) FILTER (WHERE rn <= 5) AS v5,
                AVG(volume) FILTER (WHERE rn <= 60) AS v60
            FROM (
                SELECT volume,
                       ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM gold_etf_prices
                WHERE etf_code = ? AND volume IS NOT NULL AND date <= ?
            )
        """, [etf_code, as_of]).fetchone()
    if not row or row[0] is None or row[1] is None or row[1] == 0:
        return None
    return float(row[0]) / float(row[1])


def _compute_rsi(con: duckdb.DuckDBPyConnection,
                 indicator: str, window: int = 14,
                 as_of: Optional[_date] = None) -> Optional[float]:
    """RSI-N 截至 as_of(默认最新)。"""
    if as_of is None:
        rows = con.execute(
            "SELECT date, value FROM gold_metrics "
            "WHERE indicator=? AND value IS NOT NULL ORDER BY date",
            [indicator],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT date, value FROM gold_metrics "
            "WHERE indicator=? AND value IS NOT NULL AND date <= ? ORDER BY date",
            [indicator, as_of],
        ).fetchall()
    if len(rows) < window + 1:
        return None
    closes = [r[1] for r in rows]
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in diffs]
    losses = [-d if d < 0 else 0.0 for d in diffs]
    avg_gain = sum(gains[:window]) / window
    avg_loss = sum(losses[:window]) / window
    for i in range(window, len(diffs)):
        avg_gain = (avg_gain * (window - 1) + gains[i]) / window
        avg_loss = (avg_loss * (window - 1) + losses[i]) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_ma_deviation(con: duckdb.DuckDBPyConnection,
                          indicator: str, window: int = 60,
                          as_of: Optional[_date] = None) -> Optional[float]:
    """(close - MA{window}) / MA{window} × 100,截至 as_of。"""
    if as_of is None:
        rows = con.execute(
            "SELECT value FROM gold_metrics WHERE indicator=? AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT ?",
            [indicator, window],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT value FROM gold_metrics WHERE indicator=? AND value IS NOT NULL "
            "AND date <= ? ORDER BY date DESC LIMIT ?",
            [indicator, as_of, window],
        ).fetchall()
    if len(rows) < window:
        return None
    values = [r[0] for r in rows]
    latest = values[0]
    ma = sum(values) / len(values)
    if ma == 0:
        return None
    return (latest - ma) / ma * 100


def _read_share_change_avg(con: duckdb.DuckDBPyConnection,
                           as_of: Optional[_date] = None) -> Optional[float]:
    """4 ETF 截至 as_of 的 share_change_5d 均值。"""
    if as_of is None:
        row = con.execute("""
            WITH latest AS (
                SELECT etf_code, MAX(date) AS d FROM gold_etf_share
                WHERE share_change_5d IS NOT NULL
                GROUP BY etf_code
            )
            SELECT AVG(s.share_change_5d)
            FROM gold_etf_share s JOIN latest l
              ON s.etf_code = l.etf_code AND s.date = l.d
        """).fetchone()
    else:
        row = con.execute("""
            WITH latest AS (
                SELECT etf_code, MAX(date) AS d FROM gold_etf_share
                WHERE share_change_5d IS NOT NULL AND date <= ?
                GROUP BY etf_code
            )
            SELECT AVG(s.share_change_5d)
            FROM gold_etf_share s JOIN latest l
              ON s.etf_code = l.etf_code AND s.date = l.d
        """, [as_of]).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _read_duckdb_indicator(con: duckdb.DuckDBPyConnection,
                           indicator: str,
                           as_of: Optional[_date] = None,
                           use_abs: bool = False,
                           window_mean: Optional[int] = None,
                           lookback_days: Optional[int] = None,
                           ) -> Optional[float]:
    """读 gold_metrics 表 indicator 时序的"当前值"。

    Args:
        indicator: gold_metrics.indicator 取值
        as_of: 截断日期(默认最新)
        use_abs: True → 返回 abs(value)(用于"基差绝对值"等场景)
        window_mean: 若提供,返回最近 N 个交易日均值(平滑)
        lookback_days: 仅取 (as_of - lookback_days) 之后的数据(默认全历史)
    """
    # 取截止 as_of 的最近 window_mean(或 1)条
    n = int(window_mean) if window_mean else 1
    params: list = [indicator]
    sql_parts = [
        "SELECT value FROM gold_metrics",
        "WHERE indicator = ? AND value IS NOT NULL",
    ]
    if as_of is not None:
        sql_parts.append("AND date <= ?")
        params.append(as_of)
    if lookback_days is not None and as_of is not None:
        from datetime import timedelta as _td
        sql_parts.append("AND date >= ?")
        params.append(as_of - _td(days=int(lookback_days)))
    sql_parts.append("ORDER BY date DESC LIMIT ?")
    params.append(n)

    rows = con.execute(" ".join(sql_parts), params).fetchall()
    if not rows:
        return None

    if window_mean:
        vals = [float(r[0]) for r in rows if r[0] is not None]
        if not vals:
            return None
        v = sum(vals) / len(vals)
    else:
        v = float(rows[0][0])

    return abs(v) if use_abs else v


def _resolve_current_value(sig_def: dict,
                           con: duckdb.DuckDBPyConnection,
                           as_of: Optional[_date] = None) -> tuple[Any, str]:
    """根据 source 取当前值;返回 (value, note)。as_of=None 走最新。"""
    source = sig_def.get("source", "not_implemented")

    try:
        if source == "etf_turnover":
            v = _read_etf_turnover_avg(con, as_of=as_of)
            return (v, "gold_etf_prices.turnover_rate(4 ETF 均)")

        if source == "etf_volume_ratio":
            v = _read_etf_volume_ratio(con, sig_def.get("etf_code", "518880"), as_of=as_of)
            return (v, "gold_etf_prices 5d/60d volume ratio (518880)")

        if source == "rsi":
            ind = sig_def.get("indicator", "GOLD_USD_DERIVED")
            win = int(sig_def.get("window", 14))
            v = _compute_rsi(con, ind, win, as_of=as_of)
            return (v, f"RSI-{win} of {ind}")

        if source == "ma_deviation":
            ind = sig_def.get("indicator", "GOLD_USD_DERIVED")
            win = int(sig_def.get("window", 60))
            v = _compute_ma_deviation(con, ind, win, as_of=as_of)
            return (v, f"close vs MA{win} of {ind}")

        if source == "etf_share_change":
            v = _read_share_change_avg(con, as_of=as_of)
            return (v, "gold_etf_share.share_change_5d(4 ETF 均)")

        if source == "duckdb_indicator":
            ind = sig_def.get("indicator")
            if not ind:
                return (None, "duckdb_indicator 缺 indicator 字段")
            use_abs = bool(sig_def.get("abs", False))
            wm = sig_def.get("window_mean")
            lb = sig_def.get("lookback_days")
            v = _read_duckdb_indicator(
                con, ind, as_of=as_of, use_abs=use_abs,
                window_mean=int(wm) if wm else None,
                lookback_days=int(lb) if lb else None,
            )
            note_bits = [f"gold_metrics.{ind}"]
            if use_abs:
                note_bits.append("abs")
            if wm:
                note_bits.append(f"mean({wm})")
            return (v, " · ".join(note_bits))

        if source == "not_implemented":
            return (sig_def.get("manual_value"), "未接入(走 manual_value)")

        if source == "duckdb_query":
            sql = sig_def.get("query")
            if not sql:
                return (None, "缺 query 字段")
            row = con.execute(sql).fetchone()
            return (float(row[0]) if row and row[0] is not None else None, f"sql:{sql[:30]}")
    except Exception as e:
        return (None, f"{source} 失败:{type(e).__name__}: {e}")

    return (None, f"unknown source: {source}")


# ─── 单信号评估 ────────────────────────────────────────────────────────


def _evaluate(sig_def: dict, con: duckdb.DuckDBPyConnection,
              as_of: Optional[_date] = None) -> OverheatSignal:
    """返回 OverheatSignal(state ∈ red/yellow/green)。as_of=None 走最新。"""
    current, note = _resolve_current_value(sig_def, con, as_of=as_of)

    red = sig_def.get("red_when_gt")
    yellow = sig_def.get("yellow_when_gte")
    threshold_parts = []
    if red is not None:
        threshold_parts.append(f"🔴> {red}")
    if yellow is not None:
        threshold_parts.append(f"🟡≥ {yellow}")
    threshold_str = "  ".join(threshold_parts) if threshold_parts else "(无判定)"

    if current is None:
        source = sig_def.get("source", "—")
        # 冷启动期保护:仅当 yaml 显式给了 default_state 时才走兜底
        # (信号 5 etf_share_change / 信号 6 gold_futures_basis 设计意图保留)。
        # not_implemented 也保留旧行为 — 它一定走 manual_value 路径,
        # current=None 表示 yaml 也没填,继续按 default 处理(若也没 default 则 unknown)。
        has_default = "default_state" in sig_def
        if has_default:
            return OverheatSignal(
                signal_id=sig_def["id"], name=sig_def["name"], current_value=None,
                state=str(sig_def.get("default_state", "green")),
                threshold_str=threshold_str, source=source,
                note=note + " · 缺数据走 default", unit=sig_def.get("unit", ""),
            )
        # 窗口未满 / 数据点不足 → 标 unknown,不走 default green
        return OverheatSignal(
            signal_id=sig_def["id"], name=sig_def["name"], current_value=None,
            state="unknown",
            threshold_str=threshold_str, source=source,
            note=note + " · 窗口未满(数据不足)", unit=sig_def.get("unit", ""),
        )

    state = "green"
    try:
        cv = float(current)
        if red is not None and cv > float(red):
            state = "red"
        elif yellow is not None and cv >= float(yellow):
            state = "yellow"
    except (TypeError, ValueError):
        # 非数值 → 走 default
        state = str(sig_def.get("default_state", "green"))

    return OverheatSignal(
        signal_id=sig_def["id"], name=sig_def["name"], current_value=current,
        state=state, threshold_str=threshold_str,
        source=sig_def.get("source", "—"),
        note=note, unit=sig_def.get("unit", ""),
    )


# ─── 综合判定 ───────────────────────────────────────────────────────────


def _resolve_verdict(red: int, yellow: int, cfg: dict,
                     unknown: int = 0,
                     total_signals: Optional[int] = None) -> tuple[str, str, str]:
    """按 verdict_rules 顺序匹配,先匹配先返回。

    冷启动期保护:若 unknown 信号数 ≥ 总信号数的一半(默认 6 个里 ≥3),
    verdict 直接标 'unknown',跳过正常匹配。
    """
    # 冷启动期保护:大量信号窗口未满,无法可信判定
    n_total = int(total_signals) if total_signals else 6
    threshold = max(1, n_total // 2)  # 6 个信号 → 阈值 3
    if unknown >= threshold:
        return ("unknown", "⚪ 数据不足无法判定", "窗口未满,等待数据积累")

    for rule in cfg.get("verdict_rules", []):
        cond_red = rule.get("when_red_gte")
        cond_yel = rule.get("when_yellow_gte")
        red_ok = cond_red is None or red >= int(cond_red)
        yel_ok = cond_yel is None or yellow >= int(cond_yel)
        if red_ok and yel_ok and (cond_red is not None or cond_yel is not None):
            return (rule["id"], rule["label"], rule.get("action", ""))
    # 兜底:取最后一条(通常是 add 全绿)
    rules = cfg.get("verdict_rules", [])
    if rules:
        last = rules[-1]
        return (last["id"], last["label"], last.get("action", ""))
    return ("add", "🟢 加仓窗口", "")


# ─── 主投票 ─────────────────────────────────────────────────────────────


def vote(db_path: Path = GOLD_DB,
         yaml_path: Path = YAML_PATH,
         as_of: Optional[_date] = None) -> OverheatVote:
    """as_of=None → 最新值;as_of=YYYY-MM-DD → 历史时点(用于回填)。"""
    cfg = load_config(yaml_path)
    if not db_path.exists():
        return OverheatVote(
            red_count=0, yellow_count=0, green_count=len(cfg.get("signals", [])),
            verdict_id="add", verdict_label="🟢 加仓窗口(无数据兜底)",
            verdict_action="数据库未生成,无法判定", verified=False,
        )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        signals: list[OverheatSignal] = []
        for sig_def in cfg.get("signals", []):
            signals.append(_evaluate(sig_def, con, as_of=as_of))
    finally:
        con.close()

    red = sum(1 for s in signals if s.state == "red")
    yellow = sum(1 for s in signals if s.state == "yellow")
    green = sum(1 for s in signals if s.state == "green")
    unknown = sum(1 for s in signals if s.state == "unknown")

    vid, vlabel, vaction = _resolve_verdict(
        red, yellow, cfg, unknown=unknown, total_signals=len(signals),
    )

    return OverheatVote(
        red_count=red, yellow_count=yellow, green_count=green,
        verdict_id=vid, verdict_label=vlabel, verdict_action=vaction,
        signals=signals, unknown_count=unknown,
    )


# ─── 写入 history ───────────────────────────────────────────────────────


def record_snapshot(vote_result: OverheatVote,
                    db_path: Path = GOLD_DB,
                    as_of: Optional[_date] = None) -> int:
    """写入 gold_overheat_history(单行)。返回行数。"""
    as_of = as_of or _date.today()
    if not db_path.exists():
        return 0
    con = duckdb.connect(str(db_path))
    try:
        con.execute("""
            INSERT OR REPLACE INTO gold_overheat_history
            (date, red_count, yellow_count, green_count, verdict_id, verdict_label)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            as_of, int(vote_result.red_count),
            int(vote_result.yellow_count), int(vote_result.green_count),
            vote_result.verdict_id, vote_result.verdict_label,
        ])
        return 1
    finally:
        con.close()


def backfill_history(years: int = 5,
                     freq_days: int = 7,
                     db_path: Path = GOLD_DB,
                     yaml_path: Path = YAML_PATH,
                     verbose: bool = False) -> int:
    """对过去 `years` 年逐周(默认 7 天间隔)反算过热投票,写入 history。

    返回写入行数。已存在 (date) 行会被 INSERT OR REPLACE 覆盖。
    """
    from datetime import timedelta
    if not db_path.exists():
        return 0

    end = _date.today()
    start = _date(end.year - years, end.month, end.day) if end.month != 2 or end.day != 29 \
        else _date(end.year - years, 2, 28)

    sample_dates: list[_date] = []
    cur = start
    while cur <= end:
        sample_dates.append(cur)
        cur += timedelta(days=freq_days)

    written = 0
    unknown_dates = 0
    for d in sample_dates:
        try:
            res = vote(db_path, yaml_path, as_of=d)
        except Exception as e:
            if verbose:
                print(f"  ⚠️  {d}: vote 失败 {type(e).__name__}: {e}")
            continue
        n = record_snapshot(res, db_path, as_of=d)
        written += n
        if res.verdict_id == "unknown":
            unknown_dates += 1
        if verbose:
            print(f"  {d}  🔴 {res.red_count} / 🟡 {res.yellow_count} / "
                  f"🟢 {res.green_count} / ⚪ {res.unknown_count}  "
                  f"→ {res.verdict_label}")
    if verbose and unknown_dates:
        print(f"\n  ⚪ {unknown_dates}/{len(sample_dates)} 个采样日 verdict=unknown "
              f"(窗口未满 — 冷启动期保护)")
    elif verbose:
        print(f"\n  ⚪ 0 个采样日 verdict=unknown(所有采样日窗口已满足)")
    return written


def trend_combo_advice(verdict_id: str, paradigm_actives: int,
                       yaml_path: Path = YAML_PATH) -> str:
    """根据范式投票数(0-3)+ 短期判定 给联动建议。"""
    cfg = load_config(yaml_path)
    trend = "看好" if paradigm_actives >= 2 else "看空"
    for combo in cfg.get("trend_combo", []):
        if combo.get("trend") == trend and combo.get("short") == verdict_id:
            return combo.get("advice", "")
    return ""


# ─── 金股 ETF 杠杆建议(v2.6 主题 3 板块 H)───────────────────────────


@dataclass(frozen=True)
class StockEtfAdvice:
    """金股 ETF 建议矩阵命中结果。

    matched_id: add_low_beta / add_high_beta / hold_any /
                reduce_high_beta / reduce_low_beta / beta_missing / unmatched
    """
    matched_id: str
    advice: str
    position_multiplier: float
    rationale: str
    verdict_id: str
    beta: Optional[float]

    def to_dict(self) -> dict:
        return {
            "matched_id": self.matched_id,
            "advice": self.advice,
            "position_multiplier": self.position_multiplier,
            "rationale": self.rationale,
            "verdict_id": self.verdict_id,
            "beta": self.beta,
        }


def stock_etf_advice(verdict_id: str,
                     beta: Optional[float],
                     yaml_path: Path = YAML_PATH,
                     r_squared: Optional[float] = None) -> StockEtfAdvice:
    """给定金价 verdict + 金股 β,返回建议矩阵命中结果。

    匹配规则:
    - β=None → 走 beta_missing 兜底(advice='⚪ β 数据未就绪,建议持有观望',
      multiplier=1.0,matched_id='beta_missing')
    - r_squared 非 None 且 < cfg.min_r_squared(默认 0.5)→ 走 beta_low_r2 兜底
      (β 拟合不可信,建议持有观望,multiplier=1.0)
    - matrix 自上而下顺序匹配,先匹配先返回
    - when_beta_lt / when_beta_gte 边界:β=1.1 时不满足 lt(1.1),满足 gte(1.1)
      → 等于阈值走 high_beta
    - 未命中 → 走 unmatched 兜底(multiplier=1.0)

    Args:
        verdict_id: 金价 verdict('add'/'add_caution'/'hold'/'pause_partial'/'pause')
        beta: 金股 ETF 对金价的 β(None = 数据缺)
        yaml_path: gold_overheat.yaml 路径
        r_squared: 60d 回归 R²(None = 不校验拟合可信度,向后兼容)
    """
    cfg = load_config(yaml_path).get("stock_etf_position", {})
    matrix = cfg.get("matrix", [])

    if beta is None:
        return StockEtfAdvice(
            matched_id="beta_missing",
            advice="⚪ β 数据未就绪,建议持有观望",
            position_multiplier=1.0,
            rationale="缺 β 数据(金股 ETF 数据不足或表未建)",
            verdict_id=verdict_id,
            beta=None,
        )

    min_r2 = float(cfg.get("min_r_squared", 0.5))
    if r_squared is not None and r_squared < min_r2:
        return StockEtfAdvice(
            matched_id="beta_low_r2",
            advice=f"⚪ β 拟合不可信(R²<{min_r2:.2f}),建议持有观望",
            position_multiplier=1.0,
            rationale=f"R²={r_squared:.2f} 太低,β 线性关系不显著,不据此调仓",
            verdict_id=verdict_id,
            beta=beta,
        )

    for rule in matrix:
        verdicts = rule.get("when_verdict", [])
        if verdict_id not in verdicts:
            continue
        beta_lt = rule.get("when_beta_lt")
        beta_gte = rule.get("when_beta_gte")
        if beta_lt is not None and not (beta < float(beta_lt)):
            continue
        if beta_gte is not None and not (beta >= float(beta_gte)):
            continue
        return StockEtfAdvice(
            matched_id=rule["id"],
            advice=str(rule.get("advice", "")),
            position_multiplier=float(rule.get("position_multiplier", 1.0)),
            rationale=str(rule.get("rationale", "")),
            verdict_id=verdict_id,
            beta=beta,
        )

    # 未匹配 → 兜底
    return StockEtfAdvice(
        matched_id="unmatched",
        advice="⚪ 未匹配建议矩阵(yaml 检查)",
        position_multiplier=1.0,
        rationale=f"verdict={verdict_id}, beta={beta} 未命中任何规则",
        verdict_id=verdict_id,
        beta=beta,
    )


# ─── CLI ──────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(GOLD_DB))
    ap.add_argument("--yaml", default=str(YAML_PATH))
    ap.add_argument("--write", action="store_true",
                    help="写入 gold_overheat_history(默认仅打印)")
    ap.add_argument("--backfill", action="store_true",
                    help="反算历史并批量写入 gold_overheat_history(配合 --years / --freq-days)")
    ap.add_argument("--years", type=int, default=5,
                    help="--backfill 时回填年数(默认 5)")
    ap.add_argument("--freq-days", type=int, default=7,
                    help="--backfill 采样间隔(默认 7 天 / 周)")
    args = ap.parse_args()

    if args.backfill:
        n = backfill_history(years=args.years, freq_days=args.freq_days,
                             db_path=Path(args.db), yaml_path=Path(args.yaml),
                             verbose=True)
        print(f"\n✅ 回填完成 {n} 行(近 {args.years} 年 × 每 {args.freq_days} 天)")
        return 0

    res = vote(Path(args.db), Path(args.yaml))
    print(f"⏱  黄金短期过热扫描({_date.today()})")
    print(f"   信号统计:🔴 {res.red_count} / 🟡 {res.yellow_count} / 🟢 {res.green_count}")
    print(f"   综合判定:{res.verdict_label}")
    print(f"   操作建议:{res.verdict_action}")
    print()
    print("信号矩阵:")
    for sig in res.signals:
        cur = (f"{sig.current_value:.2f}{sig.unit}"
               if isinstance(sig.current_value, (int, float))
               else (str(sig.current_value) if sig.current_value is not None else "—"))
        print(f"  {sig.emoji} {sig.name:30s} 当前 {cur:>14}  阈值 {sig.threshold_str}")
        if sig.note:
            print(f"     · {sig.note}")

    if args.write:
        n = record_snapshot(res, Path(args.db))
        print(f"\n✅ 已写入 gold_overheat_history {n} 行")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())


__all__ = ["vote", "load_config", "record_snapshot", "trend_combo_advice",
           "backfill_history", "stock_etf_advice",
           "OverheatVote", "OverheatSignal", "StockEtfAdvice"]
