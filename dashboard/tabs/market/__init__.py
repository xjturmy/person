"""dash-01 L1 市场周期 Tab — 回答"现在是好时机吗?"。

v2.1 (2026-05-05) 切理杏仁口径:差值法 + A 股全指(000985 中证全指)PE-TTM.mcw
布局:
  ⓪ 综合结论 banner — 三信号(康波/格雷厄姆差值/A股全指 PE 分位)合成
  ① 康波周期定位卡 — 静态 yaml,知识库驱动
  ② 格雷厄姆指数 — (1/A股全指 PE) − 10Y 国债 = 差值法 %(理杏仁口径)
  ③ 5 项宏观时序(M2/CPI/10Y/USDCNY/A_FULL_PE)+ 阈值红绿灯
  ④ A 股全指 PE 全周期分位带
  ⑤ 行业 PE 热力图(已迁至 🏭 行业分析 sub-tab)

数据源:
  - 5 项宏观:DuckDB `macro` 表(.tools/db/fetch_macro.py)
    A_FULL_PE 由理杏仁 API 拉(open.lixinger.com/api/cn/index/fundamental,000985 pe_ttm.mcw)
  - 行业 PE: DuckDB `industry_pe` 表
  - 康波周期:.tools/dashboard/data/kondratieff.yaml
  - 格雷厄姆评级:01_knowledge/02_权益类动态调整/04_格雷厄姆指数.md
"""
from __future__ import annotations

import streamlit as st

from ._helpers import DB_PATH, MACRO_DB
from .banner import _section_verdict_banner
from .graham import _section_graham_index
from .industry import _section_industry_drilldown, _section_industry_heatmap
from .kondratieff import _section_kondratieff_card
from .thermometer import _section_thermometer_trends
from .valuation_band import _section_a_full_band


def render(*args, **kwargs) -> None:
    """L1 市场周期 Tab 入口。

    兼容多种调用签名:
      render()
      render(db_mtime)
      render(companies, selected, db_mtime)
    """
    db_mtime = 0.0
    selected = ""
    if len(args) == 1 and isinstance(args[0], (int, float)):
        db_mtime = float(args[0])
    elif len(args) >= 3 and isinstance(args[2], (int, float)):
        db_mtime = float(args[2])
        selected = args[1] if isinstance(args[1], str) else ""
    elif "db_mtime" in kwargs:
        db_mtime = float(kwargs["db_mtime"])
    elif DB_PATH.exists():
        db_mtime = DB_PATH.stat().st_mtime
    if not selected:
        selected = kwargs.get("selected", "") or st.session_state.get("company", "")

    st.subheader("📊 L1 市场周期 · 现在是好时机吗?")

    macro_path = str(MACRO_DB)
    macro_mtime = MACRO_DB.stat().st_mtime if MACRO_DB.exists() else 0.0
    main_path = str(DB_PATH)

    # ⓪ 综合结论 banner
    _section_verdict_banner(macro_path, macro_mtime)

    # ① 康波周期定位卡
    st.markdown("### ① 康波周期定位 · 我们处在哪个大周期?")
    _section_kondratieff_card()

    # ② 格雷厄姆指数
    st.markdown("### ② 格雷厄姆指数 · 股票比债券更值得买吗?")
    _section_graham_index(macro_path, macro_mtime)

    # ③ 5 项宏观时序(原段 1 改提问式)
    st.markdown("---")
    st.markdown("### ③ 五大宏观信号 · 流动性、通胀、利率怎么样?")
    _section_thermometer_trends(macro_path, macro_mtime)

    # ④ A 股全指 PE 分位带
    st.markdown("---")
    st.markdown("### ④ 大盘估值水位 · A 股全指 PE 处于历史什么位置?")
    _section_a_full_band(macro_path, macro_mtime)

    # ⑤ 行业估值矩阵 — 已迁至 🏭 行业分析 sub-tab(避免重复)
    st.caption("💡 行业估值矩阵已迁至「🏭 行业分析」sub-tab,点击上方切换查看")


__all__ = [
    "render",
    "DB_PATH",
    "_section_industry_heatmap",
    "_section_industry_drilldown",
]
