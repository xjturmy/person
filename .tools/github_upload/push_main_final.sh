#!/usr/bin/env bash
# 推送 main-merged → main (multi-parent 方案,秒级完成)
#
# 用法:
#   cd /Users/gongyong/Desktop/Keyi/preson
#   bash .tools/github_upload/push_main_final.sh
#
# 已就绪状态(本脚本运行前):
#   - 本地分支 main-merged 已是 multi-parent commit (引用 11 个 shard)
#   - 远端已有 11 个 shard/* 分支,所有 blob 已上传
#
# 本次 push 应该只传:
#   - 1 个 commit object (~几百字节)
#   - 0 或极少 tree objects (~几 KB)
#   - 完成时间预计 <30 秒

set -eu
set -o pipefail

cd "$(cd "$(dirname "$0")/../.." && pwd)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Push main-merged → main (multi-parent 方案)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# 1) 前置检查
echo "[1/4] 检查本地分支状态..."
CURRENT_BRANCH=$(git branch --show-current)
echo "  当前分支: $CURRENT_BRANCH"

PARENT_COUNT=$(git cat-file -p main-merged | grep -c "^parent" || echo 0)
echo "  main-merged parent 数量: $PARENT_COUNT (应为 11)"

if [ "$PARENT_COUNT" -lt 11 ]; then
  echo "❌ main-merged 不是 multi-parent commit,先重建:"
  echo ""
  echo "   TREE=\$(git rev-parse main-merged^{tree})"
  echo "   NEW=\$(git commit-tree \$TREE \\"
  echo "     -p shard/root -p shard/tools -p shard/companies \\"
  echo "     -p shard/macro -p shard/blobs -p shard/config -p shard/docs \\"
  echo "     -p shard/k-value -p shard/k-cycle -p shard/k-gold -p shard/k-growth \\"
  echo "     -m \"merge: parallel shard upload \$(date +%Y-%m-%d)\")"
  echo "   git update-ref refs/heads/main-merged \$NEW"
  exit 1
fi

LOCAL_MAIN=$(git rev-parse main-merged)
echo "  main-merged sha: $LOCAL_MAIN"
echo ""

# 2) 远端状态
echo "[2/4] 远端 shard 数量..."
REMOTE_SHARDS=$(git ls-remote --heads origin 'refs/heads/shard/*' | wc -l | tr -d ' ')
echo "  远端 shard/* 数: $REMOTE_SHARDS (应 ≥ 11)"
REMOTE_MAIN=$(git ls-remote origin refs/heads/main | awk '{print $1}')
echo "  远端 main 当前: ${REMOTE_MAIN:-(空)}"
echo ""

# 3) 后台启动 push,日志写文件
LOG="/tmp/push_main_$(date +%H%M%S).log"
echo "[3/4] 启动 push (日志: $LOG)"
echo "──────────────────────────────────────────────"

# 在后台启动,把 stderr 和 stdout 合并写到日志(无 pipe 缓冲)
git push --progress origin main-merged:refs/heads/main > "$LOG" 2>&1 &
PUSH_PID=$!
echo "  PID=$PUSH_PID"
echo ""

# 4) 实时监控: 每秒采样进度 + 网络速率
echo "[4/4] 实时进度 (按 Ctrl+C 中断监控,push 继续后台)"
echo "──────────────────────────────────────────────"

PREV_BYTES=0
START_TS=$(date +%s)

while kill -0 "$PUSH_PID" 2>/dev/null; do
  sleep 2

  # 当前 ssh 累计上传字节
  SSH_PID=$(pgrep -P "$PUSH_PID" -f "ssh.*github" | head -1 || echo "")
  if [ -n "$SSH_PID" ]; then
    BYTES=$(nettop -P -L 1 -x -J bytes_out 2>/dev/null | grep "ssh.${SSH_PID}" | head -1 | awk -F, '{print $2}')
    BYTES=${BYTES:-0}
    if [ "$PREV_BYTES" -gt 0 ]; then
      RATE_BPS=$(( (BYTES - PREV_BYTES) / 2 ))
      RATE_KBS=$(( RATE_BPS / 1024 ))
    else
      RATE_KBS=0
    fi
    PREV_BYTES=$BYTES
    MB=$(awk "BEGIN{printf \"%.1f\", $BYTES/1024/1024}")
  else
    MB="N/A"
    RATE_KBS=0
  fi

  # 最新日志行 (Writing objects... 进度)
  LATEST=$(tail -c 200 "$LOG" 2>/dev/null | tr '\r' '\n' | tail -1 | head -c 100)

  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TS))
  printf "[%3ds] 上传 %s MB | 速率 %d KB/s | %s\n" "$ELAPSED" "$MB" "$RATE_KBS" "$LATEST"
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Push 结束 — 最终日志:"
echo "═══════════════════════════════════════════════════════════════"
tail -c 1500 "$LOG" | tr '\r' '\n' | tail -15
echo ""

# 5) 验证
echo "═══════════════════════════════════════════════════════════════"
echo "  验证远端"
echo "═══════════════════════════════════════════════════════════════"
REMOTE_MAIN_NEW=$(git ls-remote origin refs/heads/main | awk '{print $1}')
echo "  远端 main: ${REMOTE_MAIN_NEW:-(空)}"
echo "  本地 main-merged: $LOCAL_MAIN"
if [ "$REMOTE_MAIN_NEW" = "$LOCAL_MAIN" ]; then
  echo "  ✅ 远端 main 已同步"
  echo ""
  echo "下一步:"
  echo "  git checkout main"
  echo "  git merge --ff-only main-merged   # 把本地 main 也指过去"
  echo "  git push origin main              # 同步本地 main 引用 (可选)"
else
  echo "  ❌ 远端 main 未同步,检查日志: $LOG"
  exit 1
fi
