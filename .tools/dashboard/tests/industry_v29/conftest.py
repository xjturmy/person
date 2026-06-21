"""industry_v29 测试共享夹具 — 注入 dashboard 路径到 sys.path."""
from __future__ import annotations

import sys
from pathlib import Path

_DASH = Path(__file__).resolve().parents[2]
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))
