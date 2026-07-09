#!/usr/bin/env bash
# 一键刷新“我的持仓视角”数据缺口,并输出最终状态。
# 用法:
#   ./refresh_holding_focus_data.sh
#   ./refresh_holding_focus_data.sh --no-fallback   # 只试理杏仁 ETF,不走行情源兜底

set -uo pipefail

cd "$(dirname "$0")"

PY=".venv/bin/python"
LOG_DIR=".temp"
LOG="$LOG_DIR/holding_focus_refresh.log"
STATUS_BEFORE="$LOG_DIR/holding_focus_status_before.csv"
STATUS_AFTER="$LOG_DIR/holding_focus_status_after.csv"
NO_FALLBACK=0

for arg in "$@"; do
  case "$arg" in
    --no-fallback) NO_FALLBACK=1 ;;
    *)
      echo "未知参数: $arg"
      echo "用法: ./refresh_holding_focus_data.sh [--no-fallback]"
      exit 2
      ;;
  esac
done

mkdir -p "$LOG_DIR"
: > "$LOG"

run() {
  echo "$*" | tee -a "$LOG"
  PYTHONUNBUFFERED=1 "$@" 2>&1 | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

section() {
  echo "" | tee -a "$LOG"
  echo "== $1 ==" | tee -a "$LOG"
}

if [[ ! -x "$PY" ]]; then
  echo "找不到虚拟环境 Python: $PY"
  exit 2
fi

section "0. 清理上一次挂起的 ETF 抓取"
pkill -f ".tools/lixinger-archiver/fetch_lixinger_etf.py" 2>/dev/null || true

section "1. 校验脚本"
run "$PY" -m py_compile \
  .tools/lixinger-archiver/fetch_lixinger_etf.py \
  .tools/db/fetch_etf.py \
  .tools/dashboard/holding_focus_data_status.py
compile_rc=$?
if [[ "$compile_rc" -ne 0 ]]; then
  echo "脚本校验失败,已停止。日志: $LOG"
  exit "$compile_rc"
fi

section "2. 当前持仓数据状态"
run "$PY" .tools/dashboard/holding_focus_data_status.py | tee "$STATUS_BEFORE" >/dev/null

ETF_CODES=()
while IFS= read -r code; do
  [[ -n "$code" ]] && ETF_CODES+=("$code")
done < <("$PY" - <<'PY'
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / ".tools" / "dashboard"))
import holding_focus_data_status as s

for row in s.collect_status():
    if row.pipeline == "etf" and ("ETF行情" in row.missing or "ETF行情过旧" in row.missing):
        print(row.ticker)
PY
)

if [[ "${#ETF_CODES[@]}" -eq 0 ]]; then
  section "3. 无需补普通 ETF"
else
  section "3. 补普通 ETF:理杏仁优先"
  for code in "${ETF_CODES[@]}"; do
    echo "-- ETF $code / 理杏仁 --" | tee -a "$LOG"
    run "$PY" .tools/lixinger-archiver/fetch_lixinger_etf.py --only "$code" --years 5
    lx_rc=$?

    if [[ "$lx_rc" -ne 0 && "$NO_FALLBACK" -eq 0 ]]; then
      echo "-- ETF $code / 行情源兜底 --" | tee -a "$LOG"
      run "$PY" .tools/db/fetch_etf.py --only "$code" --years 5
    elif [[ "$lx_rc" -ne 0 ]]; then
      echo "理杏仁未成功,已按 --no-fallback 跳过行情源兜底。" | tee -a "$LOG"
    fi
  done
fi

section "4. 最终持仓数据状态"
run "$PY" .tools/dashboard/holding_focus_data_status.py --commands | tee "$STATUS_AFTER" >/dev/null

section "5. 摘要"
"$PY" - <<'PY' | tee -a "$LOG"
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / ".tools" / "dashboard"))
import holding_focus_data_status as s

rows = s.collect_status()
missing = [r for r in rows if r.missing]
print(f"持仓标的: {len(rows)}")
print(f"仍有缺口: {len(missing)}")
for row in missing:
    print(f"- {row.name} {row.ticker}: {' / '.join(row.missing)}")
if not missing:
    print("全部 OK")
print(f"日志: .temp/holding_focus_refresh.log")
print(f"最终状态: .temp/holding_focus_status_after.csv")
PY
