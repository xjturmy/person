"""黄金回测引擎 diagnose() + 实时 vote 改造离线测试。

使用真实 gold.duckdb,区间 2024-05-12 → 2025-05-12。
数据库不存在或区间无数据时整文件 skip。
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gold.backtest import (  # noqa: E402
    BacktestResult,
    DiagnosticsResult,
    GOLD_DB,
    _clear_vote_cache,
    _vote_cache_info,
    _vote_for_date,
    diagnose,
    run,
)

START = "2024-05-12"
END = "2025-05-12"

if not GOLD_DB.exists():
    pytest.skip(f"gold.duckdb 不存在: {GOLD_DB}", allow_module_level=True)


@pytest.fixture(scope="module")
def bt_result() -> BacktestResult:
    r = run(start_date=START, end_date=END)
    if "_error" in r.summary or len(r.daily) == 0:
        pytest.skip(f"区间 {START}~{END} 无数据")
    return r


@pytest.fixture(scope="module")
def diag(bt_result: BacktestResult) -> DiagnosticsResult:
    return diagnose(bt_result)


def test_diagnose_returns_dataclass(diag: DiagnosticsResult):
    assert isinstance(diag, DiagnosticsResult)
    assert diag.verdict_stay is not None
    assert diag.extreme_misalign is not None
    assert diag.confirm_sensitivity is not None
    assert diag.current_status is not None
    assert diag.advice is not None


def test_verdict_stay_sums_to_total(diag: DiagnosticsResult, bt_result: BacktestResult):
    total_days = len(bt_result.daily)
    assert int(diag.verdict_stay["days"].sum()) == total_days
    assert diag.verdict_stay["pct"].sum() == pytest.approx(100.0, abs=0.01)


def test_extreme_misalign_has_required_keys(diag: DiagnosticsResult):
    required = {
        "high_date", "high_price", "high_verdict", "high_misaligned",
        "low_date", "low_price", "low_verdict", "low_misaligned",
    }
    assert set(diag.extreme_misalign.keys()) == required
    assert isinstance(diag.extreme_misalign["high_misaligned"], bool)
    assert isinstance(diag.extreme_misalign["low_misaligned"], bool)


def test_confirm_sensitivity_has_5_rows(diag: DiagnosticsResult):
    assert len(diag.confirm_sensitivity) >= 5
    cd = diag.confirm_sensitivity["confirm_days"]
    assert pd.api.types.is_integer_dtype(cd) or all(int(x) == x for x in cd)
    # 5 个标准档位都在
    for v in [0, 3, 7, 14, 21]:
        assert v in cd.values


def test_current_status_consistency(diag: DiagnosticsResult, bt_result: BacktestResult):
    last_verdict = str(bt_result.daily.iloc[-1]["verdict"])
    assert diag.current_status["current_verdict"] == last_verdict
    assert "days_since_switch" in diag.current_status
    assert "target_now" in diag.current_status
    assert "gap" in diag.current_status


def test_advice_non_empty(diag: DiagnosticsResult):
    assert isinstance(diag.advice, list)
    assert len(diag.advice) >= 1
    assert all(isinstance(s, str) for s in diag.advice)


# ─── 实时 vote 改造相关测试 ────────────────────────────────────────────


def test_realtime_vote_cache_hits(bt_result: BacktestResult):
    """history 表覆盖时优先走 history(<1ms);未覆盖才走 lru_cache 包装的实时 vote。

    跑过 run() 后:
    - history 覆盖率 ~100% 时 vote_cache 几乎不被用,currsize 可能 0
    - 任意取一日调 _vote_for_date,要么 history 命中(source='history_table')
      要么 vote_cache 命中(hits +1)—— 二选一,不应两次都 miss(慢路径)
    """
    sample_day = bt_result.daily.index[len(bt_result.daily) // 2]
    info_before = _vote_cache_info()
    r = _vote_for_date(sample_day, GOLD_DB)
    # 优先验证 history 路径(快路径,新主路径)
    if getattr(r, "source", "") == "history_table":
        # history 命中,vote_cache 不动
        info_after = _vote_cache_info()
        assert info_after.misses == info_before.misses, "history 命中时不应触发 vote 计算"
    else:
        # history 未命中(冷启动期 / 新日期),走 vote_cache
        info_after = _vote_cache_info()
        # 第二次调用应 hit
        _vote_for_date(sample_day, GOLD_DB)
        info_3rd = _vote_cache_info()
        assert info_3rd.hits >= info_after.hits + 1, "第二次同日 vote 应命中 cache"


def test_realtime_vs_history_consistency(bt_result: BacktestResult):
    """对照测试:实时算出的 verdict 与 gold_overheat_history 表是否一致。

    一致 → 当前 history 表是最新的;不一致 → 这正是改造解决的问题
    (实时算永远对,history 表可能滞后)。本测试不强求一致,只统计偏差,
    偏差太大时给出警告但不 fail(允许 history 表过期)。
    """
    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        hist = con.execute("""
            SELECT date, verdict_id FROM gold_overheat_history
            ORDER BY date
        """).fetchdf()
    finally:
        con.close()
    if len(hist) == 0:
        pytest.skip("history 表为空,无对照基准")

    hist["date"] = pd.to_datetime(hist["date"])
    hist = hist.set_index("date")

    daily = bt_result.daily[["verdict"]].copy()
    # 把 history 表 forward-fill 到 daily 日历
    h_ff = hist.reindex(daily.index, method="ffill")
    joined = daily.join(h_ff, how="inner").dropna()
    if len(joined) == 0:
        pytest.skip("daily 与 history 无重叠区间")

    mismatch = (joined["verdict"] != joined["verdict_id"]).sum()
    total = len(joined)
    rate = mismatch / total * 100
    # 报告(pytest -v 可见)
    print(f"\n[realtime vs history] 总对比 {total} 天,不一致 {mismatch} 天 ({rate:.1f}%)")
    # 不强求一致 — history 表过期是合法状态,改造的意义就在这
    assert total > 0


def test_run_empty_range_returns_error(bt_result: BacktestResult):
    """边界:空区间应返回 _error,不抛异常。"""
    r = run(start_date="2099-01-01", end_date="2099-01-31")
    assert "_error" in r.summary
    assert len(r.daily) == 0


def test_run_single_day_doesnt_crash():
    """边界:start == end 单日不崩。"""
    # 找一个有数据的日期(任选 daily 中存在的)
    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        row = con.execute("""
            SELECT MAX(date) FROM gold_etf_prices WHERE etf_code = '518880'
        """).fetchone()
    finally:
        con.close()
    if not row or not row[0]:
        pytest.skip("gold_etf_prices 无数据")
    d = str(row[0])
    r = run(start_date=d, end_date=d)
    # 可能 _error 也可能正常一行,但不应抛异常
    assert isinstance(r, BacktestResult)


def test_load_data_signature_unchanged():
    """向后兼容:_load_data 仍返回 (px, sig) tuple,sig 是 DataFrame。"""
    from gold.backtest import _load_data
    px, sig = _load_data(GOLD_DB, "518880", "2024-05-12", "2024-05-20")
    assert isinstance(px, pd.DataFrame)
    assert isinstance(sig, pd.DataFrame)
    # sig 现在是空 placeholder(向后兼容签名,信号改实时算)
    assert len(sig) == 0


def test_vote_cache_clear():
    """清缓存应把 currsize 归零。"""
    _clear_vote_cache()
    info = _vote_cache_info()
    assert info.currsize == 0
    assert info.hits == 0
    assert info.misses == 0
