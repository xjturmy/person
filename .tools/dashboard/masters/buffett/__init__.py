"""巴菲特评分体系包。

历史包袱:曾存在 `masters/buffett.py`(extras)与 `masters/buffett/`(classifier)
同名冲突 → `import masters.buffett` 命中 .py 文件,`masters.buffett.classifier` 报
"not a package"(Hero 卡 Buffett 分类静默失效)。现统一为包:

- `masters.buffett.extras`     — v2.5 OE/留存/护城河打分(原 buffett.py)
- `masters.buffett.classifier` — v2 分类自适应评分器

包顶层 re-export extras 的全部公开名,保持 `from masters.buffett import compute_owner_earnings`
等旧调用不变。
"""
from masters.buffett.extras import *  # noqa: F401,F403
