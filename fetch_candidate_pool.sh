#!/usr/bin/env bash
# 候选池数据抓取 wrapper — 串行执行某一组 manifest 的 3 步流水线
# 用法: bash .tools/fetch_candidate_pool.sh <group_id>
# 例子: bash .tools/fetch_candidate_pool.sh 1
#
# 读 .temp/fetch_manifest/group_<id>.json,逐家公司跑:
#   1. generate_wide_valuation.py(估值 10 年)
#   2. batch_update_fs_modules.py(财报 10 年)
#   3. consolidate.py(整合到 历史数据/)
#
# 注意:不跑 ingest.py — 主线程统一跑(避免 DuckDB WAL 锁冲突)

set -u  # 未定义变量报错;不用 -e,要让单家失败也继续

GROUP_ID="${1:?usage: $0 <group_id>}"
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate

MANIFEST=".temp/fetch_manifest/group_${GROUP_ID}.json"
LOG=".temp/fetch_progress/group_${GROUP_ID}.log"
RESULT=".temp/fetch_progress/group_${GROUP_ID}.json"
mkdir -p .temp/fetch_progress

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: manifest not found: $MANIFEST" >&2
  exit 1
fi

START_TS=$(date +%s)
echo "=== Group ${GROUP_ID} start at $(date '+%H:%M:%S') ===" | tee "$LOG"

# 用 python 解析 manifest 输出一行一家:stock|name|folder|category
ENTRIES=$(python3 -c "
import json, sys
with open('$MANIFEST') as f:
    data = json.load(f)
for r in data:
    print(f\"{r['stock']}|{r['name']}|{r['folder']}|{r['category']}\")
")

TOTAL=$(echo "$ENTRIES" | wc -l | tr -d ' ')
echo "Total: $TOTAL companies" | tee -a "$LOG"

# 用 python 同步写 result JSON
SUCCESS_PY=()
FAILED_PY=()
i=0
while IFS='|' read -r STOCK NAME FOLDER CATEGORY; do
  i=$((i+1))
  echo "" | tee -a "$LOG"
  echo "[$i/$TOTAL] $NAME ($STOCK, $CATEGORY) ----" | tee -a "$LOG"

  STEP_FAIL=""
  ERR_MSG=""

  # 步骤 1: 估值
  OUT_DIR="02_companies/${FOLDER}/01_基本面数据/01_估值分析"
  mkdir -p "$OUT_DIR"
  if ! python3 .tools/lixinger-archiver/generate_wide_valuation.py \
        --stock "$STOCK" --name "$NAME" \
        --out-dir "$OUT_DIR" \
        --years 10 --metrics-preset core3 --clean-existing \
        >> "$LOG" 2>&1; then
    STEP_FAIL="1"
    ERR_MSG="generate_wide_valuation failed"
    echo "  ✗ STEP 1 FAIL" | tee -a "$LOG"
  fi

  # 步骤 2: 财报(只在步骤 1 成功时跑)
  if [[ -z "$STEP_FAIL" ]]; then
    CSVF=".temp/c_${STOCK}.csv"
    echo "folder,stock,name,category" > "$CSVF"
    echo "${FOLDER},${STOCK},${NAME},${CATEGORY}" >> "$CSVF"
    if ! python3 .tools/lixinger-archiver/batch_update_fs_modules.py \
          --companies-csv "$CSVF" --base-dir 02_companies \
          --years 10 --clean-existing \
          >> "$LOG" 2>&1; then
      STEP_FAIL="2"
      ERR_MSG="batch_update_fs_modules failed"
      echo "  ✗ STEP 2 FAIL" | tee -a "$LOG"
    fi
  fi

  # 步骤 3: consolidate
  if [[ -z "$STEP_FAIL" ]]; then
    if ! python3 .tools/data_consolidator/consolidate.py --only="$NAME" \
          >> "$LOG" 2>&1; then
      STEP_FAIL="3"
      ERR_MSG="consolidate failed"
      echo "  ✗ STEP 3 FAIL" | tee -a "$LOG"
    fi
  fi

  # 记录结果
  if [[ -z "$STEP_FAIL" ]]; then
    CSV_COUNT=$(ls "02_companies/${FOLDER}/01_基本面数据/历史数据/"*.csv 2>/dev/null | wc -l | tr -d ' ')
    echo "  ✓ done, csv=$CSV_COUNT" | tee -a "$LOG"
    SUCCESS_PY+=("{\"stock\":\"$STOCK\",\"name\":\"$NAME\",\"folder\":\"$FOLDER\",\"category\":\"$CATEGORY\",\"csv_files\":$CSV_COUNT}")
  else
    # JSON escape 简单处理
    ESCAPED_ERR=$(echo "$ERR_MSG" | sed 's/"/\\"/g')
    FAILED_PY+=("{\"stock\":\"$STOCK\",\"name\":\"$NAME\",\"step\":\"$STEP_FAIL\",\"error\":\"$ESCAPED_ERR\"}")
  fi

  sleep 1  # 缓速避免 API 撞墙
done <<< "$ENTRIES"

END_TS=$(date +%s)
DUR=$((END_TS - START_TS))

# 拼最终 JSON
SUCCESS_JOIN=$(IFS=','; echo "${SUCCESS_PY[*]:-}")
FAILED_JOIN=$(IFS=','; echo "${FAILED_PY[*]:-}")
cat > "$RESULT" <<EOF
{
  "group": ${GROUP_ID},
  "total": ${TOTAL},
  "success": [${SUCCESS_JOIN}],
  "failed": [${FAILED_JOIN}],
  "duration_sec": ${DUR}
}
EOF

echo "" | tee -a "$LOG"
echo "=== Group ${GROUP_ID} done in ${DUR}s — ${#SUCCESS_PY[@]} ok / ${#FAILED_PY[@]} fail ===" | tee -a "$LOG"
echo "Result JSON: $RESULT"
