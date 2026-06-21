#!/usr/bin/env bash
# 全量上传 GitHub 前准备: 拆分超大文件 + 提示后续 git 命令
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "==> 扫描并拆分超大文件 (并行 workers=${WORKERS:-4})"
python3 .tools/github_upload/split_assets.py --apply --workers "${WORKERS:-4}"

echo ""
echo "==> 本地大文件仍保留; Git 将跟踪 .github_blob_store/ 分片"
echo "    clone 后运行: python3 .tools/github_upload/merge_assets.py --restore-all"
echo ""
echo "==> 建议创建 **私有** 仓库: https://github.com/new"
echo "    名称: preson  |  不要勾选「Add README」"
echo ""
echo "==> 然后执行:"
echo "    git remote add origin https://github.com/xjturmy/preson.git"
echo "    git add .github_blob_store .tools/github_upload"
echo "    git commit -m 'chore: add blob store parts for GitHub upload'"
echo "    git push -u origin main"
