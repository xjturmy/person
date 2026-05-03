#!/usr/bin/env bash
# 嵌入式 Web 终端启动器(ttyd + iframe 方案)
#
# 用法:
#   bash launch_terminal.sh              # 前台启动(自动 exec claude)
#   bash launch_terminal.sh --daemon     # 后台 daemon(写 PID 到 .temp/ttyd.pid)
#   bash launch_terminal.sh --stop       # 停止后台 daemon
#   bash launch_terminal.sh --status     # 查看 daemon 状态
#   AUTO_CLAUDE=0 bash launch_terminal.sh # 强制走普通 shell
#
# 安装(首次):/opt/homebrew/bin/brew install ttyd

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${TTYD_PORT:-7681}"
PID_FILE="$ROOT/.temp/ttyd.pid"
LOG_FILE="$ROOT/.temp/ttyd.log"
mkdir -p "$ROOT/.temp"

# 解析子命令
CMD="${1:-start}"

resolve_ttyd() {
  if command -v ttyd >/dev/null 2>&1; then
    command -v ttyd
  elif [ -x /opt/homebrew/bin/ttyd ]; then
    echo /opt/homebrew/bin/ttyd
  else
    echo "❌ ttyd 未安装。请先执行:" >&2
    echo "   /opt/homebrew/bin/brew install ttyd" >&2
    exit 1
  fi
}

is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

case "$CMD" in
  --stop|stop)
    if is_running; then
      pid=$(cat "$PID_FILE")
      kill "$pid" && rm -f "$PID_FILE"
      echo "🛑 ttyd 已停止 (PID $pid)"
    else
      echo "ℹ️  没有运行中的 ttyd daemon"
      rm -f "$PID_FILE"
    fi
    exit 0
    ;;
  --status|status)
    if is_running; then
      echo "🟢 运行中 (PID $(cat "$PID_FILE"))  →  http://127.0.0.1:${PORT}"
    else
      echo "🔴 未运行"
      exit 1
    fi
    exit 0
    ;;
esac

# 已运行检测
if is_running; then
  echo "⚠️  ttyd 已在运行 (PID $(cat "$PID_FILE")) →  http://127.0.0.1:${PORT}"
  echo "    用 --stop 停止,或 --status 查看"
  exit 0
fi

TTYD=$(resolve_ttyd)
AUTO_CLAUDE="${AUTO_CLAUDE:-1}"

# 防止从 VS Code 的 Claude Code 终端启动时 CLAUDECODE=1 让子 claude 误判嵌套
CLEAN_ENV='unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH CLAUDE_AGENT_SDK_VERSION CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING AI_AGENT 2>/dev/null'

# 解析 claude 路径
# 优先级:VS Code 扩展自带的 native-binary(已登录) > 系统 PATH > brew/usr 兜底
# 原因:brew 版本可能老,Keychain 凭据格式不兼容;VS Code 自带 binary 与 Keychain 同步
resolve_claude() {
  local vscode_claude
  vscode_claude=$(ls -t "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude 2>/dev/null | head -1)
  if [ -n "$vscode_claude" ] && [ -x "$vscode_claude" ]; then
    echo "$vscode_claude"
  elif command -v claude >/dev/null 2>&1; then
    command -v claude
  elif [ -x /opt/homebrew/bin/claude ]; then
    echo /opt/homebrew/bin/claude
  elif [ -x /usr/local/bin/claude ]; then
    echo /usr/local/bin/claude
  else
    echo ""
  fi
}

CLAUDE_BIN=$(resolve_claude)

if [[ "$AUTO_CLAUDE" == "1" ]] && [[ -n "$CLAUDE_BIN" ]]; then
  START_CMD="$CLEAN_ENV; cd '$ROOT' && exec '$CLAUDE_BIN'"
  MODE_DESC="自动进 claude ($CLAUDE_BIN)"
else
  START_CMD="$CLEAN_ENV; cd '$ROOT' && exec \${SHELL:-bash} -l"
  MODE_DESC="shell 模式"
  [[ "$AUTO_CLAUDE" == "1" ]] && MODE_DESC="$MODE_DESC (claude 不在 PATH,降级)"
fi

run_ttyd() {
  exec "$TTYD" \
    -p "$PORT" \
    -i 127.0.0.1 \
    -W \
    --writable \
    bash -lc "$START_CMD"
}

if [[ "$CMD" == "--daemon" || "$CMD" == "daemon" ]]; then
  echo "🚀 后台启动 ttyd → http://127.0.0.1:${PORT} ($MODE_DESC)"
  echo "   日志: $LOG_FILE"
  echo "   停止: bash $0 --stop"
  cd "$ROOT"
  nohup bash -c "$(declare -f run_ttyd resolve_ttyd is_running); TTYD='$TTYD' START_CMD=\"$START_CMD\" PORT='$PORT' run_ttyd" >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 0.5
  if is_running; then
    echo "✅ PID $(cat "$PID_FILE")"
  else
    echo "❌ 启动失败,查看 $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
  fi
else
  echo "🚀 启动 ttyd → http://127.0.0.1:${PORT} ($MODE_DESC)"
  echo "   工作目录: $ROOT"
  echo "   按 Ctrl-C 退出 · 后台运行用 --daemon"
  cd "$ROOT"
  run_ttyd
fi
