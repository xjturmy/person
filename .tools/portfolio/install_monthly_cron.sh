#!/bin/bash
# 安装 LaunchAgent — 每月 1 号 09:00 自动跑月度复盘 + PDF + 邮件
# 用法:bash .tools/portfolio/install_monthly_cron.sh
# 卸载:launchctl unload ~/Library/LaunchAgents/com.preson.monthly.plist

set -e

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/.tools/portfolio/com.preson.monthly.plist"
DST="$HOME/Library/LaunchAgents/com.preson.monthly.plist"

if [[ ! -f "$SRC" ]]; then
    echo "❌ 模板不存在:$SRC"
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

# 已加载则先 unload
if launchctl list | grep -q com.preson.monthly; then
    echo "♻️  已加载,先 unload"
    launchctl unload "$DST" 2>/dev/null || true
fi

cp "$SRC" "$DST"
launchctl load "$DST"

echo "✅ LaunchAgent 已安装:$DST"
echo "   验证:launchctl list | grep com.preson.monthly"
echo "   触发时机:每月 1 号 09:00"
echo "   日志:.temp/monthly_cron.log / .temp/monthly_cron.err"
echo ""
echo "💡 立即手动跑一次试试:"
echo "   launchctl start com.preson.monthly"
