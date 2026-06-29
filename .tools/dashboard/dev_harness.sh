#!/usr/bin/env bash
# 子单元隔离台(L2)一行启动 —— 跑在 8502,与主 app(8501)并存。
# 清单见 dev/units.py;配 .streamlit/config.toml 热重载,改完存盘秒级刷新。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/streamlit"
[ -x "$PY" ] || PY="streamlit"

echo "🧪 子单元隔离台 → http://localhost:8502"
exec "$PY" run .tools/dashboard/dev_harness.py --server.port 8502
