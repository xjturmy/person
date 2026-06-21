"""tabs.screener._universe.get_or_block · focus 空时 stop + 含 focus 时返回正确 universe."""
from __future__ import annotations

import pandas as pd
import pytest


def test_universe_empty_focus_calls_stop(monkeypatch):
    """focus 为空 → st.stop 被调用(我们 monkeypatch 让它抛异常以便捕获)。"""
    from tabs.screener import _universe as _u
    from funnel import layers as _layers

    monkeypatch.setattr(_layers, "get_focus_names", lambda: set())
    monkeypatch.setattr(_layers, "get_screener_universe",
                        lambda: pd.DataFrame(columns=["ticker", "name", "industry_l2"]))

    # 让 st.stop 抛 StopIteration,以便测试断言它被调
    sentinel = RuntimeError("STOP_CALLED")

    class _FakeSt:
        session_state = {}
        def warning(self, *a, **k): pass
        def button(self, *a, **k): return False
        def error(self, *a, **k): pass
        def stop(self): raise sentinel

    monkeypatch.setattr(_u, "st", _FakeSt())

    with pytest.raises(RuntimeError, match="STOP_CALLED"):
        _u.get_or_block()


def test_universe_with_focus_returns_dataframe(monkeypatch):
    """focus 非空 → 返回 universe DataFrame,且 ticker→industry 写入 session 草稿。"""
    from tabs.screener import _universe as _u
    from funnel import layers as _layers
    from funnel import session as _session

    fake_universe = pd.DataFrame([
        {"ticker": "600519", "name": "贵州茅台", "industry_l2": "白酒"},
        {"ticker": "000858", "name": "五粮液",   "industry_l2": "白酒"},
    ])
    monkeypatch.setattr(_layers, "get_focus_names", lambda: {"白酒"})
    monkeypatch.setattr(_layers, "get_screener_universe", lambda: fake_universe)

    # 用一个最小 session_state(dict)替代 streamlit.session_state
    fake_ss = {}

    def _ss_or_none():
        return fake_ss

    monkeypatch.setattr(_session, "_session_state", _ss_or_none)

    # st 必须存在以便 get_or_block 走"正常"分支(不进 warning/stop)
    class _FakeSt:
        session_state = fake_ss
        def warning(self, *a, **k): pass
        def button(self, *a, **k): return False
        def stop(self): raise RuntimeError("should not stop")

    monkeypatch.setattr(_u, "st", _FakeSt())

    out = _u.get_or_block()
    assert out is not None
    assert len(out) == 2
    assert "600519" in out["ticker"].tolist()

    # session 草稿应已写入
    mp = fake_ss.get(_session.FUNNEL_SCREENER_TICKER_INDUSTRY)
    assert mp is not None
    assert mp["600519"] == "白酒"
    assert mp["000858"] == "白酒"
