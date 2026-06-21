#!/usr/bin/env bash
# 多路并行推送到 GitHub
#
# 策略: 按顶层目录 subtree split → 多个 shard 分支 → 并行 push → 合并为 main
#
# 用法:
#   git remote set-url origin https://github.com/xjturmy/person.git
#   PARALLEL=4 bash .tools/github_upload/push_parallel.sh
#
# 环境变量:
#   PARALLEL=4       同时 push 的分支数
#   REMOTE=origin
#   SKIP_SPLIT=1     跳过 split(分支已存在时)
#   SKIP_MERGE=1     只 push shard, 不合并 main
#   FORCE_ROOT=1     强制重建 shard/root(修复误含大文件)
set -eu
set -o pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REMOTE="${REMOTE:-origin}"
PARALLEL="${PARALLEL:-4}"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
MERGE_BRANCH="${MERGE_BRANCH:-main-merged}"

SHARDS=(
  ".tools:shard/tools"
  "02_companies:shard/companies"
  "03_macro:shard/macro"
  ".github_blob_store:shard/blobs"
  ".config:shard/config"
  "docs:shard/docs"
)
# 01_knowledge 不进 SHARDS: 走 4 个子 shard 并行(避免单分支 enumerate 瓶颈),
# merge_to_main 直接从 main HEAD 取 01_knowledge — blob 已通过 k-* 子 shard 上传到远端.

log() { echo "[$(date +%H:%M:%S)] $*"; }

ensure_remote() {
  if ! git remote get-url "$REMOTE" &>/dev/null; then
    echo "错误: 未配置 remote '$REMOTE'"
    exit 1
  fi
  log "remote: $(git remote get-url "$REMOTE")"
}

create_root_shard() {
  if git show-ref --verify --quiet "refs/heads/shard/root" \
     && [[ "${FORCE_ROOT:-}" != "1" ]]; then
    # 若已有 root 且含超大文件, 提示 FORCE_ROOT=1
    if git ls-tree -r --name-only shard/root 2>/dev/null | grep -q '^data/preson\.duckdb$'; then
      echo "错误: shard/root 含 data/preson.duckdb, 请 FORCE_ROOT=1 重建"
      exit 1
    fi
    log "shard/root 已存在, 跳过"
    return
  fi

  git branch -D shard/root 2>/dev/null || true
  log "创建 shard/root (仅顶层小文件, 不含 data/ 目录)..."

  git checkout --orphan shard/root-build
  git rm -rf . >/dev/null 2>&1 || true

  root_blobs=()
  while IFS= read -r name; do
    root_blobs+=("$name")
  done < <(git ls-tree "$MAIN_BRANCH" | awk '$2=="blob"{print $4}')
  if [[ ${#root_blobs[@]} -eq 0 ]]; then
    echo "错误: $MAIN_BRANCH 顶层无 blob 文件"
    git checkout "$MAIN_BRANCH"
    exit 1
  fi
  git checkout "$MAIN_BRANCH" -- "${root_blobs[@]}"

  # 禁止 git add -A — 会把工作区 data/ 等目录加进来
  git commit -m "shard: root files only"
  git branch -M shard/root
  git checkout "$MAIN_BRANCH"
  log "shard/root 文件: $(git ls-tree --name-only shard/root | tr '\n' ' ')"
}

split_shards() {
  create_root_shard

  if [[ "${SKIP_SPLIT:-}" == "1" ]]; then
    log "SKIP_SPLIT=1, 跳过 subtree split"
    return
  fi

  for entry in "${SHARDS[@]}"; do
    path="${entry%%:*}"
    branch="${entry##*:}"
    if [[ ! -e "$path" ]]; then
      log "跳过(不存在): $path"
      continue
    fi
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      log "分支已存在, 跳过 split: $branch"
      continue
    fi
    log "subtree split: $path → $branch (可能较慢)..."
    git subtree split -P "$path" -b "$branch"
  done
}

push_shards_parallel() {
  local branches=()
  branches+=("shard/root")
  for entry in "${SHARDS[@]}"; do
    branch="${entry##*:}"
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      branches+=("$branch")
    fi
  done

  log "并行 push ${#branches[@]} 个分支 (PARALLEL=$PARALLEL)..."
  local failed=0
  for b in "${branches[@]}"; do
    while [[ "$(jobs -r | wc -l | tr -d ' ')" -ge "$PARALLEL" ]]; do
      sleep 1
    done
    (
      log "push → $b"
      if git push "$REMOTE" "${b}:refs/heads/${b}"; then
        log "✓ $b"
      else
        log "✗ $b 失败"
        exit 1
      fi
    ) &
  done
  for job in $(jobs -p); do
    wait "$job" || failed=1
  done
  return "$failed"
}

merge_to_main() {
  if [[ "${SKIP_MERGE:-}" == "1" ]]; then
    log "SKIP_MERGE=1, 不合并 main"
    return
  fi

  log "合并 shard → $MERGE_BRANCH ..."
  git branch -D "$MERGE_BRANCH" 2>/dev/null || true
  git checkout --orphan "$MERGE_BRANCH"
  git rm -rf . >/dev/null 2>&1 || true

  # bash 3.2 兼容: 用 case 替代关联数组
  prefix_for() {
    case "$1" in
      shard/root)      echo "" ;;
      shard/tools)     echo ".tools" ;;
      shard/companies) echo "02_companies" ;;
      shard/macro)     echo "03_macro" ;;
      shard/blobs)     echo ".github_blob_store" ;;
      shard/config)    echo ".config" ;;
      shard/docs)      echo "docs" ;;
      *) echo "" ;;
    esac
  }

  for branch in shard/root "${SHARDS[@]##*:}"; do
    git show-ref --verify --quiet "refs/heads/$branch" || continue
    prefix="$(prefix_for "$branch")"
    log "  read-tree $branch → ${prefix:-/}"
    if [[ -z "$prefix" ]]; then
      git read-tree --reset -u "$branch"
    else
      git read-tree --prefix="${prefix}/" -u "$branch"
    fi
  done

  # 01_knowledge 直接从 main HEAD 取(blob 已通过 k-* 子 shard 推到远端)
  log "  checkout 01_knowledge from $MAIN_BRANCH (blobs already on remote via k-* shards)"
  git checkout "$MAIN_BRANCH" -- 01_knowledge
  git add 01_knowledge

  git commit -m "merge: parallel shard upload $(date +%Y-%m-%d)"
  log "push $MERGE_BRANCH → $MAIN_BRANCH ..."
  git push "$REMOTE" "${MERGE_BRANCH}:refs/heads/${MAIN_BRANCH}"
  git checkout "$MAIN_BRANCH"
  log "✅ main 已更新"
}

main() {
  ensure_remote
  split_shards
  if push_shards_parallel; then
    merge_to_main
  else
    echo ""
    echo "部分 shard push 失败; 修复后重新运行。"
    echo "若 shard/root 因大文件失败: FORCE_ROOT=1 PARALLEL=4 bash .tools/github_upload/push_parallel.sh"
    exit 1
  fi
}

main "$@"
