"""overheat_engine 冷启动期保护 + 核心兼容 · 离线测试。

主要验证 _evaluate / _resolve_verdict / vote 在窗口未满时的新行为:
- 窗口未满信号 → state='unknown'(而非旧的 default green)
- 半数信号 unknown → verdict_id='unknown'
- 显式 default_state=green 的信号(etf_share_change / gold_futures_basis)
  缺数据时仍走 green(设计意图保留)
- 正常场景(全数据齐) 仍返回 add / pause / hold 等
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pytest
import yaml

from gold.overheat import (
    OverheatSignal,
    OverheatVote,
    _evaluate,
    _resolve_verdict,
    load_config,
    vote,
)


YAML_PATH = Path(__file__).resolve().parents[3] / "rules" / "gold_overheat.yaml"


# ─── 单元:_evaluate 窗口未满 → unknown ──────────────────────────────────


def test_evaluate_unknown_when_no_default_state():
    """sig_def 不带 default_state + current=None → state='unknown'。"""
    sig_def = {
        "id": "gold_rsi_14",
        "name": "金价 RSI-14",
        "source": "rsi",
        "indicator": "GOLD_USD_DERIVED",
        "window": 14,
        "red_when_gt": 75,
        "yellow_when_gte": 65,
        # 注意:没有 default_state
    }
    # 用临时空 duckdb,RSI 取不到数 → None
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "empty.duckdb"
        con = duckdb.connect(str(db))
        con.execute("""
            CREATE TABLE gold_metrics (
                date DATE, indicator VARCHAR, value DOUBLE
            )
        """)
        sig = _evaluate(sig_def, con)
        con.close()
    assert isinstance(sig, OverheatSignal)
    assert sig.state == "unknown"
    assert sig.current_value is None
    assert sig.emoji == "⚪"
    assert "窗口未满" in sig.note


def test_evaluate_default_state_preserved():
    """sig_def 带 default_state=green + current=None → state='green'(旧行为)。"""
    sig_def = {
        "id": "etf_share_change_5d",
        "name": "ETF 份额 5 日变化",
        "source": "etf_share_change",
        "red_when_gt": 5.0,
        "yellow_when_gte": 2.0,
        "default_state": "green",  # 显式!
    }
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "empty.duckdb"
        con = duckdb.connect(str(db))
        con.execute("""
            CREATE TABLE gold_etf_share (
                etf_code VARCHAR, date DATE, share_change_5d DOUBLE
            )
        """)
        sig = _evaluate(sig_def, con)
        con.close()
    assert sig.state == "green"
    assert sig.emoji == "🟢"


def test_evaluate_normal_red():
    """有数据 + 超过红线 → state='red'。"""
    sig_def = {
        "id": "etf_turnover_rate",
        "name": "测试",
        "source": "etf_turnover",
        "red_when_gt": 5.0,
        "yellow_when_gte": 2.0,
    }
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.duckdb"
        con = duckdb.connect(str(db))
        con.execute("""
            CREATE TABLE gold_etf_prices (
                etf_code VARCHAR, date DATE, turnover_rate DOUBLE
            )
        """)
        con.execute("INSERT INTO gold_etf_prices VALUES ('518880', '2026-05-01', 8.5)")
        sig = _evaluate(sig_def, con)
        con.close()
    assert sig.state == "red"
    assert sig.current_value == 8.5


# ─── 单元:_resolve_verdict 冷启动保护 ──────────────────────────────────


def test_resolve_verdict_unknown_when_half_signals_missing():
    """6 个信号里 3 个 unknown → verdict_id='unknown'。"""
    cfg = load_config(YAML_PATH)
    vid, vlabel, vaction = _resolve_verdict(
        red=0, yellow=0, cfg=cfg, unknown=3, total_signals=6,
    )
    assert vid == "unknown"
    assert "⚪" in vlabel
    assert "窗口未满" in vaction or "数据" in vaction


def test_resolve_verdict_unknown_threshold_exact_half():
    """unknown 恰好 = 总数 / 2 (= 3 for 6) 也触发兜底。"""
    cfg = load_config(YAML_PATH)
    vid, _, _ = _resolve_verdict(0, 0, cfg, unknown=3, total_signals=6)
    assert vid == "unknown"


def test_resolve_verdict_below_threshold_normal():
    """6 个信号里只有 2 个 unknown(< 3)→ 走正常规则。"""
    cfg = load_config(YAML_PATH)
    # 0 红 0 黄 → 兜底取最后一条 add
    vid, _, _ = _resolve_verdict(0, 0, cfg, unknown=2, total_signals=6)
    assert vid == "add"


def test_resolve_verdict_normal_pause():
    """红 ≥ 3 → pause(unknown=0)。"""
    cfg = load_config(YAML_PATH)
    vid, vlabel, _ = _resolve_verdict(3, 0, cfg, unknown=0, total_signals=6)
    assert vid == "pause"
    assert "🔴" in vlabel


def test_resolve_verdict_normal_add_default():
    """无任何红黄 → 兜底取最后一条 verdict_rule(默认 add)。"""
    cfg = load_config(YAML_PATH)
    vid, _, _ = _resolve_verdict(0, 0, cfg, unknown=0, total_signals=6)
    assert vid == "add"


# ─── 集成:vote() 在空库 → 5 信号 unknown + 1 信号 green(默认)──────────


def _make_empty_gold_db(path: Path) -> None:
    """建一个 schema 齐全但表全空的 gold.duckdb,模拟"无数据"场景。"""
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE gold_etf_prices (
            etf_code VARCHAR, date DATE,
            close DOUBLE, volume DOUBLE, turnover_rate DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE gold_etf_share (
            etf_code VARCHAR, date DATE, share_change_5d DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE gold_metrics (
            date DATE, indicator VARCHAR, value DOUBLE
        )
    """)
    con.close()


def test_vote_empty_db_yields_unknown_verdict():
    """空 gold.duckdb:
    - 信号 1-4 (etf_turnover/etf_volume_ratio/rsi/ma_deviation):无 default_state → unknown
    - 信号 5 etf_share_change:default_state=green → green
    - 信号 6 gold_futures_basis:default_state=green → green
    => 4 unknown >= 3 阈值 → verdict_id='unknown'
    """
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "empty_gold.duckdb"
        _make_empty_gold_db(db)
        res = vote(db_path=db, yaml_path=YAML_PATH)
    assert isinstance(res, OverheatVote)
    assert res.unknown_count == 4
    assert res.green_count == 2  # etf_share_change + gold_futures_basis 走 default
    assert res.red_count == 0
    assert res.yellow_count == 0
    assert res.verdict_id == "unknown"
    assert "⚪" in res.verdict_label


def test_vote_partial_data_below_unknown_threshold():
    """造数:让 4 个 unknown 信号中 2 个能算出值,2 个还窗口未满。
    总信号 6 个,unknown=2 < 3 → 应走正常 verdict_rules。
    """
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "partial_gold.duckdb"
        con = duckdb.connect(str(db))
        con.execute("""
            CREATE TABLE gold_etf_prices (
                etf_code VARCHAR, date DATE,
                close DOUBLE, volume DOUBLE, turnover_rate DOUBLE
            )
        """)
        con.execute("""
            CREATE TABLE gold_etf_share (
                etf_code VARCHAR, date DATE, share_change_5d DOUBLE
            )
        """)
        con.execute("""
            CREATE TABLE gold_metrics (
                date DATE, indicator VARCHAR, value DOUBLE
            )
        """)
        # 信号 1 etf_turnover:1 条数据足够
        con.execute("INSERT INTO gold_etf_prices VALUES "
                    "('518880', '2026-05-01', 100.0, 1e7, 1.5)")
        # 信号 2 etf_volume_ratio:需要 5 + 60 个交易日才稳定 — 给 60+ 条让它能算
        # (insert 60 行 volume=1e7 → 5d/60d ≈ 1.0,green)
        for i in range(60):
            con.execute("INSERT INTO gold_etf_prices VALUES (?, ?, ?, ?, ?)",
                        ["518880", f"2026-03-{(i % 28) + 1:02d}", 100.0, 1e7, None])
        # 信号 3 rsi 14:不给数据 → unknown
        # 信号 4 ma60:不给数据 → unknown
        # 信号 5 etf_share_change:不给数据 → default green
        # 信号 6 futures_basis:不给数据 → default green
        con.close()
        res = vote(db_path=db, yaml_path=YAML_PATH)
    # rsi + ma_deviation 两路窗口未满 → unknown
    assert res.unknown_count == 2
    # 2 < 3 阈值 → 不走 unknown 兜底,走正常规则
    assert res.verdict_id != "unknown"


def test_vote_dataclass_has_unknown_count():
    """OverheatVote 必须有 unknown_count 字段(向后兼容默认 0)。"""
    v = OverheatVote(
        red_count=0, yellow_count=0, green_count=6,
        verdict_id="add", verdict_label="🟢", verdict_action="",
    )
    assert hasattr(v, "unknown_count")
    assert v.unknown_count == 0


def test_overheat_signal_unknown_emoji():
    """state='unknown' → emoji='⚪'。"""
    s = OverheatSignal(
        signal_id="t", name="t", current_value=None,
        state="unknown", threshold_str="", source="rsi",
    )
    assert s.emoji == "⚪"
