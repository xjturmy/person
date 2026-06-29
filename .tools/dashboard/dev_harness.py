"""子单元隔离台 —— 1.0 开发验证脚手架 L2。

只渲染一个子单元,配合 .streamlit/config.toml 的热重载(L1),改完存盘秒级看效果。
与主 app(8501)并存,跑在 8502:

    bash .tools/dashboard/dev_harness.sh
    # 或
    cd <preson> && .venv/bin/streamlit run .tools/dashboard/dev_harness.py --server.port 8502

清单见 dev/units.py。说"我在改 X" → 这里选 X 看效果 → pytest <test_path> 验回归。
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# ── 复刻 app.py 的 sys.path 设置,让子单元 import 路径一致 ──────────────────
ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
SCORE_DIR = ROOT / ".tools" / "score"
RULES_DIR = ROOT / ".tools" / "rules"
MCP_DIR = ROOT / ".tools" / "mcp"
TOOLS_DIR = ROOT / ".tools"
for _p in (MCP_DIR, SCORE_DIR, DASHBOARD_DIR, TOOLS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dev.units import UNITS, by_key  # noqa: E402

st.set_page_config(page_title="preson · 子单元隔离台", layout="wide")

# 注入最小 session_state 默认值,让读少数 key 的单元不崩
st.session_state.setdefault("nav", "🔍 选股")

with st.sidebar:
    try:
        _ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        _ver = "?"
    st.markdown(f"### 🧪 子单元隔离台\n`preson v{_ver}`")
    st.caption("L2 脚手架 · 只渲染一个子单元 · 配热重载秒级迭代")

    labels = {u.key: f"{u.label}{' ⛔' if u.full_app_only else ''}" for u in UNITS}
    sel_key = st.radio(
        "选择子单元",
        [u.key for u in UNITS],
        format_func=lambda k: labels[k],
        key="harness_unit",
    )

unit = by_key(sel_key)

# 顶部:让"我在改哪个单元"有唯一把手
st.markdown(f"## `{unit.key}` — {unit.label}")
cols = st.columns([3, 2])
with cols[0]:
    if unit.test_path:
        st.caption(f"🧪 回归测试:`pytest {unit.test_path}`")
    if unit.sample:
        st.caption(f"📌 样本输入:{unit.sample}")
with cols[1]:
    st.caption("改完存盘 → 本页自动 rerun(热重载已开)")

st.divider()

if unit.full_app_only:
    st.warning(
        f"⛔ `{unit.key}` 强耦合 `st.session_state`,进不了隔离台。\n\n"
        "请在主 app(8501)里验,或跑 "
        "`.venv/bin/python .tools/dashboard/verify_refactor.py`(扫全页签 st.error)。"
    )
elif unit.render is None:
    st.info("该单元尚未提供隔离台渲染适配器(render)。")
else:
    try:
        unit.render()
    except Exception as e:  # noqa: BLE001 — 隔离台要把异常显式摊出来,不吞
        st.error(f"渲染异常:{type(e).__name__}: {e}")
        st.exception(e)
