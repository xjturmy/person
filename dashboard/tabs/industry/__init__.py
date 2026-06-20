"""tabs.industry · v2.9 行业分析子标签包.

三个子页:
  - analysis:   全市场扫描(估值矩阵 + SW L1 全景),只读,不依赖 focus
  - preselect:  带 Top1/ETF/轻量详情的勾选工作台
  - confirm:    草稿落盘 + 已确认清单 + 行业档案(完整 4 区卡)

约定:
  - 所有"会写 yaml"的逻辑集中在 confirm.py
  - analysis.py 不写
  - preselect.py 只写 session_state(草稿),不写 yaml
"""
from __future__ import annotations

from . import analysis, preselect, confirm

render_analysis = analysis.render
render_preselect = preselect.render
render_confirm = confirm.render

__all__ = ["analysis", "preselect", "confirm",
           "render_analysis", "render_preselect", "render_confirm"]
