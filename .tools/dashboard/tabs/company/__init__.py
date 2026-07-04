"""Tab: 🏢 单公司详情(SWS 风格 Hero + 雪花图 + 2 个主判断区块)。

由 .tools/dashboard/app.py 在 page == PAGE_COMPANY 时调用 render(app_globals)。

子模块布局:
  hero    — 段 1:SWS Hero + 当前定位 + 投资判断预览
  block_a — 区块 A:看结论(雪花图 + 同行业建议 + 优势短板 Top3)
  block_b — 区块 B:大师评分体系(矩阵 + 同行雷达)
"""
from __future__ import annotations

from . import _helpers, block_a, block_b, hero, investment_judgement


def render(app_globals: dict) -> None:
    """app.py 在 dispatch 时把 globals() 传过来,把这些名字注入到各 sub-module globals。

    原 tabs/company.py 的单文件模式依赖把 app 全局直接注入到模块字典;
    拆包后改为把同一份字典注入到每个 sub-module 的字典。
    """
    for mod in (_helpers, hero, block_a, block_b, investment_judgement):
        g = mod.__dict__
        for _k, _v in app_globals.items():
            if _k != "__builtins__":
                g[_k] = _v
    hero.render()
    block_a.render()
    block_b.render()
