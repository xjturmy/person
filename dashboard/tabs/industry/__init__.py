"""tabs.industry · v2.9 行业分析子标签包.

三个子页:
  - analysis:   只读分析(原 industry_focus 的 A/B/C/D 4 区卡 + 21 SW L1 全景)
  - preselect:  勾选感兴趣行业,写入 session_state 草稿
  - confirm:    草稿 → focus_industries.yaml 落盘 + 已确认清单删除 + 一致性检查

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
