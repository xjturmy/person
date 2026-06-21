#!/usr/bin/env bash
# clone 后合并 GitHub 上的 shard/* 分支 → 完整工作区
#
# 用法:
#   git clone git@github.com:xjturmy/person.git preson && cd preson
#   bash .tools/github_upload/merge_shards.sh
#
# 若远程已有 main 且已合并, 直接 git checkout main 即可, 无需本脚本。
set -eu
set -o pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REMOTE="${REMOTE:-origin}"

log() { echo "[merge_shards] $*"; }

fetch_shards() {
  log "fetch $REMOTE shard 分支..."
  git fetch "$REMOTE" \
    'refs/heads/shard/*:refs/remotes/'"$REMOTE"'/shard/*' 2>/dev/null \
    || git fetch "$REMOTE"
}

branch_exists() {
  git show-ref --verify --quiet "refs/remotes/${REMOTE}/$1"
}

read_shard() {
  local branch="$1"
  local prefix="$2"
  if ! branch_exists "$branch"; then
    log "跳过(远程无): $branch"
    return 0
  fi
  log "合并 ${REMOTE}/${branch} → ${prefix:-/}"
  if [[ -z "$prefix" ]]; then
    git read-tree --reset -u "${REMOTE}/${branch}"
  else
    git read-tree --prefix="${prefix}/" -u "${REMOTE}/${branch}"
  fi
}

main() {
  if git show-ref --verify --quiet refs/heads/main \
     && git ls-remote --exit-code "$REMOTE" refs/heads/main &>/dev/null; then
    log "远程存在 main, 建议: git checkout main"
    log "若 main 已是最新合并结果, 无需 merge_shards。"
  fi

  fetch_shards

  if ! git show-ref --verify --quiet refs/remotes/${REMOTE}/shard/root \
     && ! git show-ref --verify --quiet refs/remotes/${REMOTE}/shard/tools; then
    echo "错误: 未找到 shard 分支。请确认已 push 或 remote 正确。"
    exit 1
  fi

  WORK_BRANCH="${WORK_BRANCH:-workspace}"
  git checkout --orphan "$WORK_BRANCH" 2>/dev/null \
    || git checkout "$WORK_BRANCH"
  git rm -rf . >/dev/null 2>&1 || true

  # 启用中文路径直传(否则 read-tree --prefix 中文目录会因 octal 编码失败)
  git config core.quotePath false

  read_shard shard/root ""
  read_shard shard/tools ".tools"
  read_shard shard/companies "02_companies"
  read_shard shard/macro "03_macro"
  read_shard shard/blobs ".github_blob_store"
  read_shard shard/config ".config"
  read_shard shard/docs "docs"
  # 01_knowledge 分 4 个子 shard 拼接(无 shard/knowledge 总分支)
  read_shard shard/k-value  "01_knowledge/04_知识体系/04_参考资料/02_价值投资"
  read_shard shard/k-cycle  "01_knowledge/04_知识体系/04_参考资料/04_经济周期"
  read_shard shard/k-gold   "01_knowledge/04_知识体系/04_参考资料/05_黄金投资"
  read_shard shard/k-growth "01_knowledge/04_知识体系/04_参考资料/03_成长投资"
  # 注: 01_knowledge 的非 PDF 部分(markdown 笔记 + 01_外部资料)未推送到远端,
  # clone 方需另行同步(或忽略,这些内容体积小可重生成)。

  git add -A
  git commit -m "workspace: merge shard branches $(date +%Y-%m-%d)" || true

  log "完成。当前分支: $WORK_BRANCH"
  log "下一步: python3 .tools/github_upload/merge_assets.py --restore-all"
}

main "$@"
