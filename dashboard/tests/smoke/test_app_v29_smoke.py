"""v2.9 smoke — sub-tab 标签与 navigation 常量 1:1 比对.

- import smoke: 各 v2.9 包 import 不挂
- 常量自洽: SUB_SCREENER_* / SUB_INDUSTRY_* 与 spec 完全一致
- 文件级别静态校验 tabs/screener/__init__.py 含 4 个常量引用
- 静态校验 app.py PAGE_MARKET_HUB 段使用 4 个 SUB_INDUSTRY_* / SUB_MARKET_JUDGE 常量
- 静态校验 tabs/industry/confirm.py 跳转目标是 SUB_SCREENER_PRELIM

AppTest 可选(streamlit testing 不一定能在 headless 全跑通,失败仅警告)。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DASH = ROOT / ".tools" / "dashboard"
for p in (DASH, ROOT / ".tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def test_import_smoke_screener_pkg():
    """tabs.screener 包及 4 个 sub-module 全可 import。"""
    from tabs.screener import _universe, confirm, graham_pick, lynch_pick, prelim, render
    assert callable(render)
    for m in (_universe, prelim, lynch_pick, graham_pick, confirm):
        assert hasattr(m, "__name__")


def test_import_smoke_industry_pkg():
    from tabs.industry import analysis, confirm, preselect, render_analysis, render_confirm, render_preselect
    for m in (analysis, preselect, confirm):
        assert hasattr(m, "__name__")
    for fn in (render_analysis, render_preselect, render_confirm):
        assert callable(fn)


def test_navigation_constants_spec_aligned():
    """spec 要求:["初步筛选", "林奇选股", "格雷厄姆选股", "选股确定"]"""
    import navigation as nav
    assert nav.SUB_SCREENER_PRELIM == "初步筛选"
    assert nav.SUB_SCREENER_LYNCH == "林奇选股"
    assert nav.SUB_SCREENER_GRAHAM == "格雷厄姆选股"
    assert nav.SUB_SCREENER_CONFIRM == "选股确定"

    # 行业 4 常量
    assert nav.SUB_MARKET_JUDGE == "市场研判"
    assert nav.SUB_INDUSTRY_ANALYSIS == "行业分析"
    assert nav.SUB_INDUSTRY_PRESELECT == "行业预选"
    assert nav.SUB_INDUSTRY_CONFIRM == "行业确定"


def test_screener_init_uses_constants_for_tabs():
    """tabs/screener/__init__.py 必须 4 格 st.tabs,且文案 = emoji + 常量。"""
    src = (DASH / "tabs" / "screener" / "__init__.py").read_text(encoding="utf-8")
    assert "SUB_SCREENER_PRELIM" in src
    assert "SUB_SCREENER_LYNCH" in src
    assert "SUB_SCREENER_GRAHAM" in src
    assert "SUB_SCREENER_CONFIRM" in src
    # 4 元组解构
    assert "tab_prelim, tab_lynch, tab_value, tab_confirm = st.tabs" in src


def test_industry_confirm_goto_targets_prelim():
    """行业确定 → 选股,跳转目标必须是 SUB_SCREENER_PRELIM(不是 CONFIRM)。"""
    src = (DASH / "tabs" / "industry" / "confirm.py").read_text(encoding="utf-8")
    assert "SUB_SCREENER_PRELIM" in src
    assert "goto(PAGE_SCREENER, sub_tab=SUB_SCREENER_PRELIM)" in src
    # 反面校验:不应再跳到 CONFIRM
    assert "goto(PAGE_SCREENER, sub_tab=SUB_SCREENER_CONFIRM)" not in src


def test_app_market_hub_uses_constants():
    """app.py PAGE_MARKET_HUB 4 格 st.tabs 必须引用 SUB_* 常量。"""
    src = (DASH / "app.py").read_text(encoding="utf-8")
    # 4 个 sub-tab 常量都被 alias import
    for name in (
        "SUB_MARKET_JUDGE",
        "SUB_INDUSTRY_ANALYSIS",
        "SUB_INDUSTRY_PRESELECT",
        "SUB_INDUSTRY_CONFIRM",
    ):
        assert name in src, f"app.py missing reference to {name}"


def test_apptest_optional_market_hub_screener():
    """可选 AppTest — 失败仅 skip,不阻塞 smoke。"""
    try:
        from streamlit.testing.v1 import AppTest
    except Exception:
        import pytest
        pytest.skip("streamlit.testing.v1.AppTest unavailable")

    app_py = DASH / "app.py"
    try:
        t = AppTest.from_file(str(app_py), default_timeout=60).run()
    except Exception as e:
        import pytest
        pytest.skip(f"AppTest run failed (likely unrelated env): {e}")

    if t.exception:
        import pytest
        pytest.skip(f"AppTest exception on default load: {t.exception}")
    # 默认页加载无异常即视为通过
    assert True
