"""子单元 manifest —— 1.0 开发验证脚手架 L2 的底座。

每个子单元登记为一个 Unit:
  - key:        唯一把手("我在改 X"里的 X)
  - label:      隔离台下拉显示名
  - render:     无参渲染适配器(闭包),内部用 sample_inputs 调真实渲染/计算函数
  - test_path:  该单元对应的离线测试(验回归时跑它)
  - full_app_only: True 表示强耦合 session_state、进不了隔离台,只能在主 app
                   (8501) + verify_refactor.py 里验

用法:
  - 隔离台 dev_harness.py 读本清单,sidebar 选 key → 只渲染那一个。
  - 新增子单元 = 在 UNITS 里追加一条;补 test_path 让它进覆盖清单。

约定:render 适配器里才 import streamlit / 真实模块,避免本文件被
pytest 收集时强依赖 streamlit 运行时。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = Path(__file__).resolve().parents[1]
PRESON_DB = ROOT / "data" / "preson.duckdb"


@dataclass
class Unit:
    key: str
    label: str
    render: Callable[[], None] | None = None
    test_path: str = ""
    full_app_only: bool = False
    sample: str = ""


# ── 渲染适配器(无参闭包;在函数体内才 import 真实模块/streamlit)──────────────

def _render_peg_curve() -> None:
    """PEG 时间曲线 — 已纯函数化,只需 ticker。"""
    import streamlit as st
    from valuation.peg_curve import render_peg_curve

    st.caption("样本:000333 美的集团")
    render_peg_curve("000333", name="美的集团", db_path=PRESON_DB)


def _render_peg_grade() -> None:
    """PEG 评级表 — 纯函数 grade_peg 的展示。"""
    import streamlit as st
    from valuation.peg_curve import grade_peg

    rows = [(v, grade_peg(v)) for v in (0.4, 0.8, 1.0, 1.5, 2.5)]
    st.table({
        "PEG": [v for v, _ in rows],
        "评级": [g.label for _, g in rows],
    })


def _render_industry_percentile() -> None:
    """行业分位 — compute() 返回 dataclass,这里展示。"""
    import streamlit as st
    from industry.percentile_engine import compute

    industry = st.text_input("行业(L2)", value="白酒")
    r = compute(industry)
    c1, c2, c3 = st.columns(3)
    c1.metric("PE 中位", f"{r.pe_median:.1f}" if r.pe_median is not None else "—")
    c2.metric("PE 10y 分位", f"{r.pe_percentile_10y:.0f}%" if r.pe_percentile_10y is not None else "—")
    c3.metric("成员数", r.member_count)
    st.caption(f"数据源:{r.data_source} · as_of {r.as_of} · {r.notes}")


# ── 子单元清单 ─────────────────────────────────────────────────────────────

UNITS: list[Unit] = [
    Unit(
        key="peg_curve",
        label="PEG 时间曲线(估值)",
        render=_render_peg_curve,
        test_path=".tools/dashboard/tests/valuation/test_peg_curve.py",
        sample="000333",
    ),
    Unit(
        key="peg_grade",
        label="PEG 五档评级(纯函数)",
        render=_render_peg_grade,
        test_path=".tools/dashboard/tests/valuation/test_peg_curve.py",
    ),
    Unit(
        key="industry_percentile",
        label="行业分位卡(行业)",
        render=_render_industry_percentile,
        test_path=".tools/dashboard/tests/industry/test_percentile_engine.py",
        sample="白酒",
    ),
    # ── 强耦合整 tab:不进隔离台,走主 app(8501) + verify_refactor.py ──
    Unit(
        key="munger_tab",
        label="芒格 Tab(强耦合)",
        full_app_only=True,
        test_path=".tools/dashboard/tests/tabs/test_munger_tab.py",
    ),
    Unit(
        key="graham_analysis",
        label="格雷厄姆分析 Tab(强耦合)",
        full_app_only=True,
        test_path=".tools/dashboard/tests/masters/test_graham_steps.py",
    ),
    Unit(
        key="decision_center",
        label="决策中心(强耦合)",
        full_app_only=True,
    ),
]


def by_key(key: str) -> Unit | None:
    return next((u for u in UNITS if u.key == key), None)


def isolatable() -> list[Unit]:
    """可进隔离台的子单元(有 render 适配器、非 full_app_only)。"""
    return [u for u in UNITS if u.render is not None and not u.full_app_only]
