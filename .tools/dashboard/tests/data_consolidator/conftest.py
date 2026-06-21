"""data_consolidator 测试公共夹具 — 注入 .tools 路径到 sys.path."""
from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[3]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
