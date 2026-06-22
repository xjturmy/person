#!/usr/bin/env bash
# 新电脑一键还原 preson 开发环境
#
# 用法 (推荐手动 cd 到目标目录后运行):
#   bash setup_new_machine.sh                    # 默认 clone 到当前目录下 preson/
#   TARGET=~/work/preson bash setup_new_machine.sh
#   SOURCE_HOST=mac-air.local bash setup_new_machine.sh  # 配置 scp/rsync 来源主机
#
# 步骤:
#   1. git clone main 分支
#   2. merge_assets.py 还原 DuckDB
#   3. Python venv + 依赖
#   4. 提示从 SOURCE_HOST 拉取凭据 + 私有目录
#   5. 校验 streamlit 可启动
#
# 前置:
#   - 已配置 GitHub SSH key (ssh git@github.com 能通)
#   - python3 + git 已装
#   - (可选) 已配置 SOURCE_HOST 的 SSH 免密以同步凭据

set -eu

REPO_URL="${REPO_URL:-git@github.com:xjturmy/person.git}"
TARGET="${TARGET:-$(pwd)/preson}"
SOURCE_HOST="${SOURCE_HOST:-}"
SOURCE_PATH="${SOURCE_PATH:-~/Desktop/Keyi/preson}"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err]${NC} $*" >&2; }

# ─── Step 1: clone ───────────────────────────────────────────
if [ -d "$TARGET/.git" ]; then
  log "$TARGET 已是 git 仓库,跳过 clone"
  cd "$TARGET"
  git fetch origin --prune
  git checkout main 2>/dev/null || git checkout -b main origin/main
  git pull --ff-only origin main
else
  log "Clone $REPO_URL → $TARGET"
  git clone "$REPO_URL" "$TARGET"
  cd "$TARGET"
fi

# ─── Step 2: 还原 DuckDB ─────────────────────────────────────
# 基于 manifest 判断: 只要 manifest 里任一库在 data/ 缺失就 --restore-all
# (旧逻辑只看 preson 在不在,会漏掉 6 个小库 macro/etf/gold/turnover/market/decisions)
if [ -f .tools/github_upload/merge_assets.py ] && [ -f .github_blob_store/manifest.json ]; then
  MISSING=$(python3 - <<'PY'
import json, os
m = json.load(open(".github_blob_store/manifest.json"))
missing = [e["original"] for e in m.get("files", []) if not os.path.exists(e["original"])]
print(len(missing))
for o in missing:
    print(o)
PY
)
  N_MISSING=$(echo "$MISSING" | head -1)
  if [ "${N_MISSING:-0}" -gt 0 ]; then
    log "还原 DuckDB (manifest 中 $N_MISSING 个库缺失 → 从 .github_blob_store/ 分片合并)"
    echo "$MISSING" | tail -n +2 | sed 's/^/    缺: /'
    python3 .tools/github_upload/merge_assets.py --restore-all
  else
    log "manifest 中全部库已存在,跳过还原"
  fi
else
  warn "找不到 .github_blob_store/manifest.json,跳过 DuckDB 还原"
  warn "Dashboard 会进入 CSV 兜底模式 (功能受限)"
fi

# ─── Step 3: Python 虚拟环境 ─────────────────────────────────
if [ -d .venv ]; then
  log "venv 已存在,跳过创建"
else
  log "创建 venv"
  python3 -m venv .venv
fi
source .venv/bin/activate
log "升级 pip"
pip install -U pip --quiet

log "安装依赖"
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
elif [ -f .tools/requirements.txt ]; then
  pip install -r .tools/requirements.txt
else
  warn "未找到 requirements.txt,装核心包"
  pip install streamlit duckdb pandas plotly numpy \
              akshare tushare lixinger pyyaml requests \
              rapidfuzz pypinyin ocrmypdf 2>/dev/null \
    || pip install streamlit duckdb pandas plotly numpy \
                  akshare tushare pyyaml requests rapidfuzz pypinyin
fi

# ─── Step 4: 凭据 + 非 shard 内容同步 ──────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Step 4: 从本机同步凭据 + 未推送内容 (手动执行)"
echo "═══════════════════════════════════════════════════════════════"

NEED_SCP=()
[ ! -f .config/credentials.md ]    && NEED_SCP+=(".config/credentials.md")
[ ! -f .config/.lixinger_token ]   && NEED_SCP+=(".config/.lixinger_token")
[ ! -f .config/smtp.yaml ]         && NEED_SCP+=(".config/smtp.yaml (可选)")
[ ! -d "01_knowledge/04_知识体系/04_参考资料/01_外部资料" ] && NEED_SCP+=("01_知识体系/04_参考资料/01_外部资料/")

if [ "${#NEED_SCP[@]}" -eq 0 ]; then
  log "凭据 + 私有内容齐全 ✓"
else
  warn "以下文件缺失,请从本机同步:"
  for f in "${NEED_SCP[@]}"; do echo "       - $f"; done
  echo ""
  if [ -n "$SOURCE_HOST" ]; then
    log "建议命令 (SOURCE_HOST=$SOURCE_HOST):"
    cat <<EOF

  scp $SOURCE_HOST:$SOURCE_PATH/.config/credentials.md      .config/
  scp $SOURCE_HOST:$SOURCE_PATH/.config/.lixinger_token     .config/
  scp $SOURCE_HOST:$SOURCE_PATH/.config/smtp.yaml           .config/ 2>/dev/null || true

  rsync -avz --progress \\
    $SOURCE_HOST:$SOURCE_PATH/01_knowledge/04_知识体系/04_参考资料/01_外部资料/ \\
    01_knowledge/04_知识体系/04_参考资料/01_外部资料/

EOF
  else
    warn "未设置 SOURCE_HOST,无法生成 scp/rsync 命令"
    warn "重跑: SOURCE_HOST=mac-air.local bash $0"
  fi
fi

# ─── Step 5: 校验 ─────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Step 5: 验证"
echo "═══════════════════════════════════════════════════════════════"

log "git 状态"
git log --oneline -1
echo "  分支: $(git branch --show-current)"
echo "  远端: $(git remote get-url origin)"

log "目录大小"
for d in 01_knowledge 02_companies 03_macro .tools docs data; do
  [ -d "$d" ] && printf "  %-20s %s\n" "$d" "$(du -sh "$d" 2>/dev/null | awk '{print $1}')"
done

if [ -f data/preson.duckdb ]; then
  log "DuckDB ✓ ($(du -h data/preson.duckdb | awk '{print $1}'))"
fi

echo ""
log "下一步:"
echo "  source .venv/bin/activate"
echo "  streamlit run .tools/dashboard/app.py"
echo "  浏览器: http://localhost:8501"
echo ""
log "完成 🎉"
