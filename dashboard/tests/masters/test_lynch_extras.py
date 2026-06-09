"""test_lynch_extras.py — lynch_extras.py L2-L5 单测

覆盖：
  - L2 insider_proxy_score        — AkShare 缺失/失败/正常 3 路
  - L3 institutional_holding_proxy — AkShare 缺失/失败/正常 3 路
  - L4 peg_curve_grade            — 空 / 不足 / >=60% / <60% 4 路
  - L5 quarterly_continuity_score — 不足 / hits>=7 / hits=6 / hits<6 4 路

  所有 AkShare 调用通过 monkeypatch 注入假 ak 模块；
  所有 DuckDB 调用通过 monkeypatch 替换 build_peg_series / quarterly_continuity。

运行：
    python -m pytest .tools/dashboard/test_lynch_extras.py -v
或：
    python .tools/dashboard/test_lynch_extras.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

# 让脚本既能在仓库根目录跑，也能 cd 到 .tools/dashboard 跑
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import masters.lynch.extras  # noqa: E402
from masters.lynch.extras import (  # noqa: E402
    LynchExtraResult,
    insider_proxy_score,
    institutional_holding_proxy,
    peg_curve_grade,
    quarterly_continuity_score,
)


# ──────────────────────────────────────────────────────────────────
# 工具：构造假 akshare 模块
# ──────────────────────────────────────────────────────────────────

def _fake_ak_module(stock_zh_a_gdhs=None, stock_main_fund_flow=None):
    fake = types.ModuleType("akshare")
    if stock_zh_a_gdhs is not None:
        fake.stock_zh_a_gdhs = stock_zh_a_gdhs
    if stock_main_fund_flow is not None:
        fake.stock_main_fund_flow = stock_main_fund_flow
    return fake


def _install_fake_ak(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "akshare", fake)


def _uninstall_ak(monkeypatch):
    """让 import akshare 抛 ImportError。"""
    monkeypatch.setitem(sys.modules, "akshare", None)


# ──────────────────────────────────────────────────────────────────
# L2 insider_proxy_score
# ──────────────────────────────────────────────────────────────────

def test_l2_insider_akshare_missing(monkeypatch):
    """AkShare 未安装 → score=None，note 含'未安装'。"""
    _uninstall_ak(monkeypatch)
    r = insider_proxy_score("600519")
    assert isinstance(r, LynchExtraResult)
    assert r.score is None
    assert r.value is None
    assert r.verified is False
    assert "未安装" in r.note or "AkShare" in r.note


def test_l2_insider_api_failure(monkeypatch):
    """AkShare 调用抛异常 → 优雅降级 score=None。"""
    def boom(symbol):
        raise RuntimeError("network error")

    fake = _fake_ak_module(stock_zh_a_gdhs=boom)
    _install_fake_ak(monkeypatch, fake)
    r = insider_proxy_score("600519")
    assert r.score is None
    assert r.verified is False
    assert "失败" in r.note or "不可用" in r.note


def test_l2_insider_shrinking_holders(monkeypatch):
    """股东户数显著收缩（-5%）→ score=2。"""
    df = pd.DataFrame({
        "报告日期": ["2025-09-30", "2025-12-31", "2026-03-31", "2026-04-30"],
        "股东户数": [100000.0, 99000.0, 96000.0, 95000.0],  # -5%
    })

    def fake_call(symbol):
        return df

    fake = _fake_ak_module(stock_zh_a_gdhs=fake_call)
    _install_fake_ak(monkeypatch, fake)
    r = insider_proxy_score("600519", window_months=12)
    assert r.score == 2
    assert r.value is not None
    assert r.value < -0.03
    assert r.verified is False
    assert "收缩" in r.note or "买入" in r.note


def test_l2_insider_growing_holders(monkeypatch):
    """股东户数上升（+2%）→ score=0。"""
    df = pd.DataFrame({
        "报告日期": ["2025-09-30", "2025-12-31", "2026-03-31", "2026-04-30"],
        "股东户数": [100000.0, 100500.0, 101500.0, 102000.0],  # +2%
    })

    fake = _fake_ak_module(stock_zh_a_gdhs=lambda symbol: df)
    _install_fake_ak(monkeypatch, fake)
    r = insider_proxy_score("600519", window_months=12)
    assert r.score == 0
    assert r.value is not None
    assert r.value > 0


# ──────────────────────────────────────────────────────────────────
# L3 institutional_holding_proxy
# ──────────────────────────────────────────────────────────────────

def test_l3_institutional_akshare_missing(monkeypatch):
    _uninstall_ak(monkeypatch)
    r = institutional_holding_proxy("600519")
    assert r.score is None
    assert r.verified is False


def test_l3_institutional_api_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("api down")

    fake = _fake_ak_module(stock_main_fund_flow=boom)
    _install_fake_ak(monkeypatch, fake)
    r = institutional_holding_proxy("600519")
    assert r.score is None
    assert r.verified is False


def test_l3_institutional_net_outflow(monkeypatch):
    """主力净流出 → 林奇偏好（机构低关注）→ score=1。"""
    df = pd.DataFrame({
        "日期": ["2026-05-08", "2026-05-09"],
        "主力净流入": [-1.5e8, -2.3e8],     # 净流出
        "成交额": [1.2e10, 1.0e10],
    })

    def fake_call(symbol, market=None):
        # market="北京" 第一次会被传，正常返回
        return df

    fake = _fake_ak_module(stock_main_fund_flow=fake_call)
    _install_fake_ak(monkeypatch, fake)
    r = institutional_holding_proxy("600519")
    assert r.score == 1
    assert r.verified is False
    assert "净流出" in r.note or "低关注" in r.note


def test_l3_institutional_net_inflow(monkeypatch):
    """主力净流入 → 机构高关注 → score=0。"""
    df = pd.DataFrame({
        "日期": ["2026-05-08", "2026-05-09"],
        "主力净流入": [3.5e8, 2.1e8],
        "成交额": [1.2e10, 1.0e10],
    })

    def fake_call(symbol, market=None):
        return df

    fake = _fake_ak_module(stock_main_fund_flow=fake_call)
    _install_fake_ak(monkeypatch, fake)
    r = institutional_holding_proxy("600519")
    assert r.score == 0
    assert "高关注" in r.note or "净流入" in r.note


# ──────────────────────────────────────────────────────────────────
# L4 peg_curve_grade
# ──────────────────────────────────────────────────────────────────

def _patch_build_peg(monkeypatch, df):
    """注入假 build_peg_series。"""
    fake_mod = types.ModuleType("valuation.peg_curve")
    fake_mod.build_peg_series = lambda ticker, db_path=None, lookback_years=5: df
    monkeypatch.setitem(sys.modules, "valuation.peg_curve", fake_mod)


def test_l4_peg_empty(monkeypatch):
    _patch_build_peg(monkeypatch, pd.DataFrame(columns=["date", "peg"]))
    r = peg_curve_grade("600519")
    assert r.score is None
    assert "空" in r.note or "不足" in r.note


def test_l4_peg_insufficient(monkeypatch):
    """有效行数 < 30 → None。"""
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=10),
                       "peg": [0.8] * 10})
    _patch_build_peg(monkeypatch, df)
    r = peg_curve_grade("600519")
    assert r.score is None
    assert "不足" in r.note


def test_l4_peg_below_1_majority(monkeypatch):
    """80% 天数 PEG<1 → score=1。"""
    n = 100
    pegs = [0.5] * 80 + [1.5] * 20
    df = pd.DataFrame({"date": pd.date_range("2021-01-01", periods=n, freq="D"),
                       "peg": pegs})
    _patch_build_peg(monkeypatch, df)
    r = peg_curve_grade("600519")
    assert r.score == 1
    assert r.value is not None
    assert abs(r.value - 0.80) < 1e-6
    assert r.verified is True


def test_l4_peg_below_1_minority(monkeypatch):
    """30% 天数 PEG<1 → score=0。"""
    n = 100
    pegs = [0.5] * 30 + [1.8] * 70
    df = pd.DataFrame({"date": pd.date_range("2021-01-01", periods=n, freq="D"),
                       "peg": pegs})
    _patch_build_peg(monkeypatch, df)
    r = peg_curve_grade("600519")
    assert r.score == 0
    assert abs(r.value - 0.30) < 1e-6


# ──────────────────────────────────────────────────────────────────
# L5 quarterly_continuity_score
# ──────────────────────────────────────────────────────────────────

class _FakeQC:
    """伪造 lynch_classifier.QuarterlyContinuity。"""
    def __init__(self, n_quarters, hits_10pct):
        self.n_quarters = n_quarters
        self.hits_10pct = hits_10pct
        self.hits_20pct = 0
        self.hits_0 = 0


def _patch_quarterly_continuity(monkeypatch, fake_result, db_exists=True):
    """注入假 quarterly_continuity 与 DB.exists。"""
    fake_mod = types.ModuleType("masters.lynch.classifier")

    def fake_func(con, ticker, n_quarters=8):
        return fake_result

    fake_mod.quarterly_continuity = fake_func
    monkeypatch.setitem(sys.modules, "masters.lynch.classifier", fake_mod)

    # 拦截 duckdb.connect（避免真连）
    import duckdb as real_duckdb

    class _FakeCon:
        def close(self):
            pass

    monkeypatch.setattr(real_duckdb, "connect", lambda *a, **kw: _FakeCon())

    # 让 DB_PATH.exists() 可控
    monkeypatch.setattr(masters.lynch.extras.Path, "exists", lambda self: db_exists)


def test_l5_qc_db_missing(monkeypatch):
    """DB 文件不存在 → None。"""
    fake_mod = types.ModuleType("masters.lynch.classifier")
    fake_mod.quarterly_continuity = lambda *a, **kw: _FakeQC(8, 7)
    monkeypatch.setitem(sys.modules, "masters.lynch.classifier", fake_mod)
    monkeypatch.setattr(masters.lynch.extras.Path, "exists", lambda self: False)

    r = quarterly_continuity_score("600519")
    assert r.score is None
    assert "不存在" in r.note or "DuckDB" in r.note


def test_l5_qc_insufficient(monkeypatch):
    """季度数 < 6 → None。"""
    _patch_quarterly_continuity(monkeypatch, _FakeQC(n_quarters=4, hits_10pct=3))
    r = quarterly_continuity_score("600519")
    assert r.score is None
    assert "不足" in r.note


def test_l5_qc_hits_ge_7(monkeypatch):
    """hits_10 = 7 → score=2。"""
    _patch_quarterly_continuity(monkeypatch, _FakeQC(n_quarters=8, hits_10pct=7))
    r = quarterly_continuity_score("600519")
    assert r.score == 2
    assert r.value == 7.0
    assert r.verified is True


def test_l5_qc_hits_eq_6(monkeypatch):
    """hits_10 = 6 → score=1。"""
    _patch_quarterly_continuity(monkeypatch, _FakeQC(n_quarters=8, hits_10pct=6))
    r = quarterly_continuity_score("600519")
    assert r.score == 1
    assert r.value == 6.0


def test_l5_qc_hits_lt_6(monkeypatch):
    """hits_10 = 3 → score=0。"""
    _patch_quarterly_continuity(monkeypatch, _FakeQC(n_quarters=8, hits_10pct=3))
    r = quarterly_continuity_score("600519")
    assert r.score == 0
    assert r.value == 3.0


# ──────────────────────────────────────────────────────────────────
# 直接运行（无 pytest）
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-v"]))
