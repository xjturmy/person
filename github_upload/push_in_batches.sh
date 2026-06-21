#!/usr/bin/env bash
# 分批推送到 GitHub — 按 commit 递增更新 main
set -eu
set -o pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
BATCH_SIZE="${BATCH_SIZE:-3}"
SLEEP_SEC="${SLEEP_SEC:-2}"

if ! git remote get-url "$REMOTE" &>/dev/null; then
  echo "错误: 未配置 remote '$REMOTE'"
  exit 1
fi

commits=($(git rev-list --reverse "$BRANCH"))
total=${#commits[@]}
echo "仓库: $(git remote get-url "$REMOTE")"
echo "分支: $BRANCH | commit 总数: $total | 每批: $BATCH_SIZE"
echo ""

idx=0
while [[ "$idx" -lt "$total" ]]; do
  idx=$((idx + BATCH_SIZE))
  [[ "$idx" -gt "$total" ]] && idx=$total
  target="${commits[$((idx - 1))]}"
  echo ">>> 批次 $idx/$total  $(git log -1 --format='%h %s' "$target")"
  git push "$REMOTE" "${target}:refs/heads/${BRANCH}" || exit 1
  [[ "$idx" -lt "$total" ]] && sleep "$SLEEP_SEC"
done
echo "✅ 完成"
