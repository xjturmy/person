"""黄金三大范式投票引擎 · D2 Phase 2.4

读 `.tools/rules/gold_paradigm.yaml`,对 15 信号逐一评估激活/钝化,
按 identity_rules 决定主导身份 + 配置区间。

替换 `gold_data.static_paradigm_vote()`,`verified=True` 标记。

╔══════════════════════════════════════════════════════════════════════╗
║ ⚠️ 设计原则:本引擎为「快照型」,无 backfill_history() — 不可回看历史 ║
╠══════════════════════════════════════════════════════════════════════╣
║ 15 个信号 source 分布(2026-05 实测):                                ║
║   • manual_const   10/15  康波 / 地缘 / AI 商用化 / 央行购金 / ...   ║
║   • not_implemented 3/15  VIX / 科技-金价相关性 / 美生产力           ║
║   • gold_metrics    2/15  US_REAL_RATE / SPDR_HOLDINGS(pct_change)  ║
║                                                                      ║
║ 13/15 信号在历史任一日 t 的真实值 **不可知** —                       ║
║ yaml 中 manual_value 只代表当下季度的人工判读快照,                   ║
║ 强行复用最新值回填 5 年会**伪造**「长期主导身份」的时序意义。        ║
║                                                                      ║
║ 因此本引擎只:                                                        ║
║   1. 每次调用 vote() 拿当下结果                                      ║
║   2. record_snapshot() 写「今天」一行到 gold_paradigm_history        ║
║   3. UI 只展示当前快照(15 信号矩阵 + 主导身份),不画时序趋势         ║
║                                                                      ║
║ 如未来 ≥10/15 信号迁出 manual_const(例如 VIX / SPDR 落库 + 地缘     ║
║ 量化指数接入),才考虑实现 backfill_history(),仿 overheat_engine。   ║
╚══════════════════════════════════════════════════════════════════════╝

5 种信号 source:
- gold_metrics    — duckdb 长表 indicator 最新值
- gold_ratios     — duckdb 宽表派生(暂未用,保留)
- manual_const    — yaml 内 manual_value 字段(2026-05 快照,需季度复审)
- manual_csv      — .config/<csv> 读最新一行(预留)
- not_implemented — 走 manual_value 占位 + default_active 兜底
- pct_change      — gold_metrics indicator 近 N 天变化率(% 形式)

判定语法:
- active_when_lt:    < value
- active_when_lte:   <= value
- active_when_gt:    > value
- active_when_gte:   >= value
- active_when_in:    in [list]
- (无判定 + default_active=true) → 直接激活

写入 gold_paradigm_signals(当前快照)+ gold_paradigm_history(每次 cron
追加当天一行;表内多行**无时序意义**,仅作审计追溯)。
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
YAML_PATH = ROOT / ".tools" / "rules" / "gold_paradigm.yaml"


# ─── 数据类 ─────────────────────────────────────────────────────────────


@dataclass
class SignalResult:
    paradigm: str           # economic_financial / tech_revolution / great_power_struggle
    paradigm_label: str     # 中文 + emoji 标签
    signal_id: str
    name: str
    current_value: Any
    threshold_str: str      # 阈值描述(给 UI)
    active: bool
    source: str
    note: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["current_value"] = str(d["current_value"]) if d["current_value"] is not None else None
        return d


@dataclass
class ParadigmVoteV1:
    """yaml 引擎返回类型;字段对齐 gold_data.ParadigmVote 但 verified=True。"""
    p1_active: bool
    p2_active: bool
    p3_active: bool
    p1_count: int
    p2_count: int
    p3_count: int
    dominant_id: str
    dominant_label: str
    suggested_pct: tuple[float, float]
    verified: bool = True
    source: str = "paradigm_engine_v1"
    signals: list[SignalResult] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["suggested_pct"] = list(d["suggested_pct"])
        d["signals"] = [s.to_dict() for s in d["signals"]]
        return d


# ─── 加载配置 ───────────────────────────────────────────────────────────


def load_config(path: Path = YAML_PATH) -> dict:
    """读 yaml,返回 dict。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── 信号取值 ───────────────────────────────────────────────────────────


def _read_latest_metric(indicator: str, db_path: Path = GOLD_DB) -> Optional[float]:
    if not db_path.exists():
        return None
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute(
            "SELECT value FROM gold_metrics WHERE indicator=? AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT 1", [indicator],
        ).fetchone()
        return float(row[0]) if row else None
    finally:
        con.close()


def _read_pct_change(indicator: str, window_days: int,
                     db_path: Path = GOLD_DB) -> Optional[float]:
    """近 N 天变化 %。"""
    if not db_path.exists():
        return None
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT date, value FROM gold_metrics WHERE indicator=? "
            "AND value IS NOT NULL ORDER BY date", [indicator],
        ).fetchall()
        if len(rows) < 2:
            return None
        latest_date, latest_val = rows[-1]
        # 找 latest_date - window_days 之前最近的一个观测
        target = latest_date.toordinal() - window_days
        prev_val = None
        for d, v in rows:
            if d.toordinal() <= target:
                prev_val = v
            else:
                break
        if prev_val is None or prev_val == 0:
            return None
        return (latest_val - prev_val) / prev_val * 100
    finally:
        con.close()


def _resolve_current_value(sig_def: dict, db_path: Path = GOLD_DB) -> tuple[Any, str]:
    """根据 source 类型拿当前值;返回 (value, note)。"""
    source = sig_def.get("source", "manual_const")

    if source == "gold_metrics":
        ind = sig_def.get("indicator")
        if not ind:
            return (None, "缺 indicator 字段")
        v = _read_latest_metric(ind, db_path)
        return (v, f"gold_metrics:{ind}")

    if source == "pct_change":
        ind = sig_def.get("indicator")
        win = int(sig_def.get("window_days", 180))
        v = _read_pct_change(ind, win, db_path) if ind else None
        return (v, f"pct_change:{ind} {win}d")

    if source == "gold_ratios":
        col = sig_def.get("column")
        if not col or not db_path.exists():
            return (None, "缺 column 或 db")
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            row = con.execute(
                f"SELECT {col} FROM gold_ratios WHERE {col} IS NOT NULL "
                "ORDER BY date DESC LIMIT 1"
            ).fetchone()
            return (float(row[0]) if row else None, f"gold_ratios:{col}")
        finally:
            con.close()

    if source == "manual_const":
        return (sig_def.get("manual_value"), "manual_const")

    if source == "manual_csv":
        # 预留:从 .config/<csv> 读最新行
        return (sig_def.get("manual_value"), "manual_csv (待实现)")

    if source == "not_implemented":
        return (sig_def.get("manual_value"), "未接入(用 manual_value 占位)")

    return (None, f"unknown source: {source}")


# ─── 单信号评估 ────────────────────────────────────────────────────────


def _evaluate(sig_def: dict, db_path: Path = GOLD_DB) -> tuple[bool, Any, str, str]:
    """返回 (active, current, threshold_str, note)。"""
    current, note = _resolve_current_value(sig_def, db_path)

    threshold_parts = []
    if "active_when_lt" in sig_def:
        threshold_parts.append(f"< {sig_def['active_when_lt']}")
    if "active_when_lte" in sig_def:
        threshold_parts.append(f"≤ {sig_def['active_when_lte']}")
    if "active_when_gt" in sig_def:
        threshold_parts.append(f"> {sig_def['active_when_gt']}")
    if "active_when_gte" in sig_def:
        threshold_parts.append(f"≥ {sig_def['active_when_gte']}")
    if "active_when_in" in sig_def:
        threshold_parts.append(f"∈ {sig_def['active_when_in']}")
    threshold_str = " 且 ".join(threshold_parts) if threshold_parts else "(无判定)"

    # 数据缺失 → 走 default_active
    if current is None:
        return (bool(sig_def.get("default_active", False)), None, threshold_str,
                note + " · 缺数据走 default")

    # 数值判定
    if "active_when_lt" in sig_def:
        try:
            if float(current) < float(sig_def["active_when_lt"]):
                return (True, current, threshold_str, note)
            return (False, current, threshold_str, note)
        except (TypeError, ValueError):
            pass
    if "active_when_lte" in sig_def:
        try:
            if float(current) <= float(sig_def["active_when_lte"]):
                return (True, current, threshold_str, note)
            return (False, current, threshold_str, note)
        except (TypeError, ValueError):
            pass
    if "active_when_gt" in sig_def:
        try:
            if float(current) > float(sig_def["active_when_gt"]):
                return (True, current, threshold_str, note)
            return (False, current, threshold_str, note)
        except (TypeError, ValueError):
            pass
    if "active_when_gte" in sig_def:
        try:
            if float(current) >= float(sig_def["active_when_gte"]):
                return (True, current, threshold_str, note)
            return (False, current, threshold_str, note)
        except (TypeError, ValueError):
            pass

    # 类别判定(in)
    if "active_when_in" in sig_def:
        valid = sig_def["active_when_in"]
        if isinstance(valid, list) and current in valid:
            return (True, current, threshold_str, note)
        # 模糊匹配:current 含 valid 元素之一(如"持续 (俄乌+中东)" 含 "持续")
        if isinstance(valid, list) and isinstance(current, str):
            for v in valid:
                if isinstance(v, str) and v in current:
                    return (True, current, threshold_str, note + " · 模糊匹配")
        return (False, current, threshold_str, note)

    # 没有任何判定 → default_active
    return (bool(sig_def.get("default_active", False)), current, threshold_str, note)


# ─── 主投票 ─────────────────────────────────────────────────────────────


def vote(db_path: Path = GOLD_DB,
         yaml_path: Path = YAML_PATH) -> ParadigmVoteV1:
    """读 yaml + db,执行投票。"""
    cfg = load_config(yaml_path)
    paradigms_cfg = cfg["paradigms"]

    all_signals: list[SignalResult] = []
    paradigm_results: dict[str, dict] = {}

    for p_id, p_cfg in paradigms_cfg.items():
        threshold = int(p_cfg.get("threshold", 3))
        signal_defs = p_cfg.get("signals", [])
        active_count = 0
        for sig_def in signal_defs:
            act, cur, thr, note = _evaluate(sig_def, db_path)
            sig_res = SignalResult(
                paradigm=p_id,
                paradigm_label=p_cfg.get("label", p_id),
                signal_id=sig_def["id"],
                name=sig_def["name"],
                current_value=cur,
                threshold_str=thr,
                active=act,
                source=sig_def.get("source", "manual_const"),
                note=note,
            )
            all_signals.append(sig_res)
            if act:
                active_count += 1
        paradigm_results[p_id] = {
            "active_count": active_count,
            "active": active_count >= threshold,
            "label": p_cfg.get("label", p_id),
            "name": p_cfg.get("name", p_id),
        }

    p1 = paradigm_results.get("economic_financial", {})
    p2 = paradigm_results.get("tech_revolution", {})
    p3 = paradigm_results.get("great_power_struggle", {})

    p1_active = bool(p1.get("active", False))
    p2_active = bool(p2.get("active", False))
    p3_active = bool(p3.get("active", False))

    # 主导身份匹配
    dominant_id = "weak"
    dominant_label = "黄金弱势期"
    suggested_pct = (0.0, 5.0)
    note = ""
    for rule in cfg.get("identity_rules", []):
        cond = rule.get("when", {})
        if (cond.get("p1") == p1_active and
            cond.get("p2") == p2_active and
            cond.get("p3") == p3_active):
            dominant_id = rule["id"]
            dominant_label = rule["label"]
            sug = rule.get("suggested_pct", [0, 5])
            suggested_pct = (float(sug[0]), float(sug[1]))
            note = rule.get("note", "")
            break

    return ParadigmVoteV1(
        p1_active=p1_active, p2_active=p2_active, p3_active=p3_active,
        p1_count=int(p1.get("active_count", 0)),
        p2_count=int(p2.get("active_count", 0)),
        p3_count=int(p3.get("active_count", 0)),
        dominant_id=dominant_id, dominant_label=dominant_label,
        suggested_pct=suggested_pct,
        signals=all_signals, note=note,
    )


# ─── 写入 paradigm_signals / paradigm_history ───────────────────────────


def record_snapshot(vote_result: ParadigmVoteV1,
                    db_path: Path = GOLD_DB,
                    as_of: Optional[_date] = None) -> tuple[int, int]:
    """写入 gold_paradigm_signals(当前 15 行)+ gold_paradigm_history(单行)。

    ⚠️ 快照型设计 —— 每次 cron 仅写「当天」一行,
    gold_paradigm_history 表内多行**无时序意义**,仅作审计追溯。
    13/15 信号是 manual_const / not_implemented,历史日真实值不可知,
    因此本模块**不提供** backfill_history()(详见文件顶 docstring)。

    返回 (signals_inserted, history_inserted)。
    """
    as_of = as_of or _date.today()
    if not db_path.exists():
        return (0, 0)

    con = duckdb.connect(str(db_path))
    try:
        # 1. paradigm_signals — upsert 15 行
        rows_sig = []
        for sig in vote_result.signals:
            rows_sig.append({
                "paradigm": sig.paradigm,
                "signal_id": sig.signal_id,
                "name": sig.name,
                "value": str(sig.current_value) if sig.current_value is not None else None,
                "threshold": sig.threshold_str,
                "active": bool(sig.active),
                "as_of": as_of,
            })
        if rows_sig:
            import pandas as pd
            df_sig = pd.DataFrame(rows_sig)
            con.register("sig_df", df_sig)
            con.execute("""
                INSERT OR REPLACE INTO gold_paradigm_signals
                (paradigm, signal_id, name, value, threshold, active, as_of)
                SELECT paradigm, signal_id, name, value, threshold, active, as_of
                FROM sig_df
            """)
            con.unregister("sig_df")

        # 2. paradigm_history — 1 行
        con.execute("""
            INSERT OR REPLACE INTO gold_paradigm_history
            (date, p1_active_count, p2_active_count, p3_active_count,
             p1_active, p2_active, p3_active,
             dominant_id, suggested_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            as_of,
            vote_result.p1_count, vote_result.p2_count, vote_result.p3_count,
            bool(vote_result.p1_active), bool(vote_result.p2_active), bool(vote_result.p3_active),
            vote_result.dominant_id,
            float(vote_result.suggested_pct[1]),  # 区间上限作为单值快照
        ])

        return (len(rows_sig), 1)
    finally:
        con.close()


# ─── CLI ──────────────────────────────────────────────────────────────


def _cli() -> int:
    """命令行:跑一次投票 + 打印 + 写入 history。"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(GOLD_DB))
    ap.add_argument("--yaml", default=str(YAML_PATH))
    ap.add_argument("--write", action="store_true",
                    help="写入 gold_paradigm_signals + history(默认仅打印)")
    args = ap.parse_args()

    db_path = Path(args.db)
    yaml_path = Path(args.yaml)

    res = vote(db_path, yaml_path)
    print(f"🥇 黄金三大范式投票({as_of})")
    print(f"   范式投票:{res.p1_count}-{res.p2_count}-{res.p3_count}  "
          f"({sum([res.p1_active, res.p2_active, res.p3_active])}/3 激活)")
    print(f"   主导身份:{res.dominant_label}")
    print(f"   建议配置:{res.suggested_pct[0]:.0f}-{res.suggested_pct[1]:.0f}%")
    print(f"   说明:{res.note}")
    print()
    print("信号矩阵:")
    last_p = ""
    for sig in res.signals:
        if sig.paradigm != last_p:
            print(f"\n  --- {sig.paradigm_label} ---")
            last_p = sig.paradigm
        flag = "✅" if sig.active else "⚪"
        cur = sig.current_value if sig.current_value is not None else "—"
        print(f"  {flag} {sig.name:32s} {str(cur):>20}  阈值:{sig.threshold_str}")

    if args.write:
        n_sig, n_hist = record_snapshot(res, db_path)
        print(f"\n✅ 已写入 gold_paradigm_signals {n_sig} 行 + gold_paradigm_history {n_hist} 行")

    return 0


# 兼容 _cli 顶部使用 as_of(避免 NameError)
as_of = _date.today()


if __name__ == "__main__":
    import sys
    sys.exit(_cli())


__all__ = ["vote", "load_config", "record_snapshot",
           "ParadigmVoteV1", "SignalResult"]
