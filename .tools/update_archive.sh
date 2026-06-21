#!/bin/bash
# 一键更新公司档案库所有数据（增量）
# 用法：bash update_archive.sh
# 依赖：.venv_lixinger 已安装，环境变量 LIXINGER_TOKEN / TUSHARE_TOKEN 已设置

set -e
cd "$(dirname "$0")"

VENV=".venv_lixinger/bin/activate"
if [ ! -f "$VENV" ]; then
  echo "❌ 未找到 .venv_lixinger，请先创建虚拟环境" >&2
  exit 1
fi
source "$VENV"

echo ""
echo "========================================"
echo " 公司档案库一键更新"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# Step 1: 理杏仁估值宽表 + 财务模块(02-05) + 最近一月回写
echo ""
echo "▶ Step 1/3  理杏仁数据（估值 + 财务 + 最近一月）"
python3 ".cursor/skills/lixinger-wide-archiver/scripts/run_full_pipeline.py" \
  --companies-csv "companies.csv" \
  --days 90 \
  --stats-window y10 \
  --years 10 \
  --clean-existing

# Step 2: 巨潮财报 PDF 增量下载（近2年，已存在则跳过）
echo ""
echo "▶ Step 2/3  财报 PDF 下载（近2年，增量）"
python3 ".cursor/skills/company-financial-report-download/scripts/batch_download_archive_financials.py" \
  --archive-root "02_公司档案库" \
  --companies-csv "02_公司档案库/_财报批量下载/companies.csv" \
  --years 2

# Step 3: 券商分析（新华保险，近2年）
echo ""
echo "▶ Step 3/3  券商分析更新（新华保险）"
python3 "fetch_tushare_broker_analysis.py"

echo ""
echo "========================================"
echo " ✅ 全部完成  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
