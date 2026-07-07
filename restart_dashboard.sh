#!/usr/bin/env bash
# 关闭所有正在运行的 Streamlit Dashboard 进程,然后启动一个干净的新实例
# 用法: ./restart_dashboard.sh [端口]   端口缺省 8501

set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-8501}"
APP=".tools/dashboard/app.py"
LOG=".temp/dashboard.log"

mkdir -p .temp

echo "[1/3] 杀掉所有 streamlit 进程..."
pkill -f "streamlit run .tools/dashboard/app.py" 2>/dev/null || true
pkill -f "python -m streamlit run .tools/dashboard/app.py" 2>/dev/null || true
# 兜底:端口占用的进程也清掉
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "      端口 $PORT 仍被占用,强制释放..."
  lsof -ti tcp:"$PORT" | xargs kill -9 2>/dev/null || true
fi
sleep 1

echo "[2/3] 激活 venv..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[3/3] 启动 Dashboard (port=$PORT) → 日志 $LOG"
nohup .venv/bin/python -m streamlit run "$APP" \
  --server.port "$PORT" \
  --server.headless true \
  > "$LOG" 2>&1 &

PID=$!
sleep 3

if curl -fsS "http://localhost:$PORT/_stcore/health" >/dev/null 2>&1 || lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "✅ 已启动 PID=$PID  http://localhost:$PORT"
  echo "   tail -f $LOG    # 看实时日志"
  echo "   ./restart_dashboard.sh $PORT    # 重启"
else
  echo "❌ 启动失败,看日志:"
  tail -n 30 "$LOG"
  exit 1
fi
