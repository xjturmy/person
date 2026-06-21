#!/usr/bin/env bash
# 推送 develop 分支到远端 (multi-parent 合并方案,目标 <1 min)
#
# 用法:
#   cd /Users/gongyong/Desktop/Keyi/preson
#   bash .tools/github_upload/push_develop.sh
#
# 远端 develop 分支建好后:
#   另一台电脑: git clone -b develop git@github.com:xjturmy/person.git
#               + python3 .tools/github_upload/merge_assets.py --restore-all
#   一步到位,无需 merge_shards.sh

set -eu
set -o pipefail

cd "$(cd "$(dirname "$0")/../.." && pwd)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Push develop 分支 (multi-parent 合并方案)"
echo "═══════════════════════════════════════════════════════════════"

# 1) 远端已有 11 shard?
REMOTE_SHARDS=$(git ls-remote --heads origin 'refs/heads/shard/*' | wc -l | tr -d ' ')
echo "[1/5] 远端 shard 数: $REMOTE_SHARDS (应=11)"
if [ "$REMOTE_SHARDS" -lt 11 ]; then
  echo "❌ 远端 shard 不足,先把 shard 推完"; exit 1
fi

# 2) 删除老的 main-merged / develop 本地分支
echo "[2/5] 清理本地老分支"
git update-ref -d refs/heads/main-merged 2>/dev/null && echo "  main-merged 已删" || true
git update-ref -d refs/heads/develop 2>/dev/null && echo "  develop 已删" || true

# 3) 构造 orphan 合并树 (各 shard read-tree 到对应前缀 + 从 main 取 01_knowledge 余下)
echo "[3/5] 构造合并树"
git checkout --orphan _develop_build
git rm -rf . >/dev/null 2>&1 || true

git read-tree --reset -u origin/shard/root
git read-tree --prefix=.tools/                origin/shard/tools
git read-tree --prefix=02_companies/          origin/shard/companies
git read-tree --prefix=03_macro/              origin/shard/macro
git read-tree --prefix=.github_blob_store/    origin/shard/blobs
git read-tree --prefix=.config/               origin/shard/config
git read-tree --prefix=docs/                  origin/shard/docs
# 4 个子 shard 拼回 01_knowledge
git config core.quotePath false
git read-tree --prefix="01_knowledge/04_知识体系/04_参考资料/02_价值投资/" origin/shard/k-value
git read-tree --prefix="01_knowledge/04_知识体系/04_参考资料/04_经济周期/" origin/shard/k-cycle
git read-tree --prefix="01_knowledge/04_知识体系/04_参考资料/05_黄金投资/" origin/shard/k-gold
git read-tree --prefix="01_knowledge/04_知识体系/04_参考资料/03_成长投资/" origin/shard/k-growth
# 01_knowledge 余下 (markdown 笔记 + 01_外部资料) 从 main HEAD 取
git checkout main -- 01_knowledge
git add 01_knowledge

# checkout 工作区使 read-tree 内容可见 (read-tree 已写 index, -u 写 worktree,但安全起见)
git checkout-index -a -f >/dev/null 2>&1 || true

# 4) 写 tree + multi-parent commit (parent 用 origin/shard/* 远端引用 = 一定在远端)
echo "[4/5] 构造 multi-parent commit"
TREE=$(git write-tree)
COMMIT=$(git commit-tree "$TREE" \
  -p origin/shard/root -p origin/shard/tools -p origin/shard/companies \
  -p origin/shard/macro -p origin/shard/blobs -p origin/shard/config -p origin/shard/docs \
  -p origin/shard/k-value -p origin/shard/k-cycle -p origin/shard/k-gold -p origin/shard/k-growth \
  -m "develop: merge all 11 shards into single working tree $(date +%Y-%m-%d)")
git update-ref refs/heads/develop "$COMMIT"
echo "  develop = $COMMIT"
echo "  parent 数: $(git cat-file -p develop | grep -c '^parent')"

# 5) 后台 push + 实时进度
LOG="/tmp/push_develop_$(date +%H%M%S).log"
echo "[5/5] 启动 push (日志: $LOG)"
echo "──────────────────────────────────────────────"

# 切回 main 让 _develop_build 可安全释放
git checkout main 2>/dev/null
git update-ref -d refs/heads/_develop_build 2>/dev/null || true

git push --progress origin develop:refs/heads/develop --force > "$LOG" 2>&1 &
PUSH_PID=$!
echo "  PID=$PUSH_PID"

START=$(date +%s)
PREV_BYTES=0
while kill -0 "$PUSH_PID" 2>/dev/null; do
  sleep 2
  SSH_PID=$(pgrep -P "$PUSH_PID" -f "ssh" | head -1 || echo "")
  BYTES=0
  if [ -n "$SSH_PID" ]; then
    BYTES=$(nettop -P -L 1 -x -J bytes_out 2>/dev/null | grep "ssh.${SSH_PID}" | head -1 | awk -F, '{print $2}')
    BYTES=${BYTES:-0}
  fi
  RATE=$(( (BYTES - PREV_BYTES) / 2 / 1024 ))
  PREV_BYTES=$BYTES
  MB=$(awk "BEGIN{printf \"%.1f\", $BYTES/1024/1024}")
  ELAPSED=$(( $(date +%s) - START ))
  LAST=$(tail -c 150 "$LOG" 2>/dev/null | tr '\r' '\n' | tail -1 | head -c 90)
  printf "[%3ds] 上传 %s MB | 速率 %d KB/s | %s\n" "$ELAPSED" "$MB" "$RATE" "$LAST"
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Push 结果"
echo "═══════════════════════════════════════════════════════════════"
tail -c 1500 "$LOG" | tr '\r' '\n' | tail -15
echo ""
REMOTE_DEV=$(git ls-remote origin refs/heads/develop | awk '{print $1}')
LOCAL_DEV=$(git rev-parse develop)
echo "本地 develop:  $LOCAL_DEV"
echo "远端 develop:  ${REMOTE_DEV:-(空)}"
if [ "$REMOTE_DEV" = "$LOCAL_DEV" ]; then
  echo ""
  echo "✅ 远端 develop 已就绪"
  echo ""
  echo "另一台电脑用:"
  echo "  git clone -b develop git@github.com:xjturmy/person.git preson"
  echo "  cd preson && python3 .tools/github_upload/merge_assets.py --restore-all"
else
  echo "❌ 推送失败,检查 $LOG"; exit 1
fi
