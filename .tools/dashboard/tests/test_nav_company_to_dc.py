"""P0 阶段 2 · 公司研究 → 决策中心 跳转 prefill 消费测试。

测试两件事:
1. block_d 的「📝 记此决策」按钮通过 goto() 写入正确 intent(含 price / reason_template)
2. decision_center.render() 入口能从 session_state.nav_prefill 取出 price / reason_template
   并注入到 dc_price / dc_rationale_short 表单字段。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1]
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

import streamlit as st  # noqa: E402

import navigation as nav  # noqa: E402


@pytest.fixture(autouse=True)
def clear_session():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    yield
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def test_goto_dc_with_price_and_reason():
    """模拟 block_d 按钮被点击 — goto() 应写出含 price + reason_template + sub_tab 的 intent。"""
    nav.goto(
        nav.PAGE_DC,
        company="美的集团",
        sub_tab=nav.SUB_DC_LOG,
        prefill={"price": 65.4, "reason_template": "[来自公司研究 · 美的集团] "},
    )
    intent = st.session_state["nav_intent"]
    assert intent["page"] == nav.PAGE_DC
    assert intent["company"] == "美的集团"
    assert intent["sub_tab"] == nav.SUB_DC_LOG
    assert intent["prefill"]["price"] == pytest.approx(65.4)
    assert intent["prefill"]["reason_template"].startswith("[来自公司研究")


def test_goto_dc_missing_price_still_ok():
    """当前价拿不到时,prefill 只含 reason_template,goto 不报错。"""
    nav.goto(
        nav.PAGE_DC,
        company="新华保险",
        prefill={"reason_template": "[来自公司研究 · 新华保险] "},
    )
    intent = st.session_state["nav_intent"]
    assert intent["prefill"] == {"reason_template": "[来自公司研究 · 新华保险] "}


def _consume_prefill_simulating_render() -> None:
    """复刻 decision_center.render() 入口的 prefill 消费片段(不依赖外部模块)。"""
    from tabs.decision_center import apply_nav_prefill
    apply_nav_prefill(st.session_state.pop("nav_prefill", None))


def test_decision_center_consumes_full_prefill():
    """app.py 把 prefill 暂存到 nav_prefill;render 入口应将其注入到 widget keys。"""
    st.session_state["nav_prefill"] = {
        "price": 65.4,
        "reason_template": "[来自公司研究 · 美的集团] ",
    }
    _consume_prefill_simulating_render()
    assert "nav_prefill" not in st.session_state  # 消费后清空
    assert st.session_state["dc_price"] == pytest.approx(65.4)
    assert st.session_state["dc_rationale_short"].startswith("[来自公司研究")


def test_decision_center_consumes_partial_prefill_price_only():
    st.session_state["nav_prefill"] = {"price": 1500.0}
    _consume_prefill_simulating_render()
    assert st.session_state["dc_price"] == pytest.approx(1500.0)
    assert "dc_rationale_short" not in st.session_state


def test_decision_center_consumes_partial_prefill_reason_only():
    st.session_state["nav_prefill"] = {"reason_template": "[xxx] "}
    _consume_prefill_simulating_render()
    assert st.session_state["dc_rationale_short"] == "[xxx] "
    assert "dc_price" not in st.session_state


def test_decision_center_no_prefill_no_op():
    """无 nav_prefill 时,不应往 session_state 写任何 dc_* key。"""
    _consume_prefill_simulating_render()
    assert "dc_price" not in st.session_state
    assert "dc_rationale_short" not in st.session_state


def test_decision_center_ignores_non_dict_prefill():
    st.session_state["nav_prefill"] = "not a dict"
    _consume_prefill_simulating_render()
    assert "dc_price" not in st.session_state
    assert "dc_rationale_short" not in st.session_state


def test_decision_center_handles_bad_price_type():
    """price 不可转 float 时静默跳过,不抛。"""
    st.session_state["nav_prefill"] = {"price": "not a number", "reason_template": "ok"}
    _consume_prefill_simulating_render()
    assert "dc_price" not in st.session_state
    assert st.session_state["dc_rationale_short"] == "ok"
