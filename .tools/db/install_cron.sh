#!/usr/bin/env bash
# 安装 / 卸载 / 触发 preson 周末数据更新 LaunchAgent。
# 默认调度:每周日 21:00 跑 update.py(akshare 增量 → ingest → validate)。
#
# 用法:
#   .tools/db/install_cron.sh install     # 安装并启用
#   .tools/db/install_cron.sh uninstall   # 停用并移除
#   .tools/db/install_cron.sh status      # 查看状态
#   .tools/db/install_cron.sh trigger     # 手动跑一次

set -euo pipefail

LABEL="com.preson.update.weekly"
ROOT="/Users/gongyong/Desktop/Keyi/preson"
SRC_PLIST="$ROOT/.tools/db/$LABEL.plist"
DST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

cmd="${1:-status}"

case "$cmd" in
    install)
        if [ ! -f "$SRC_PLIST" ]; then
            echo "missing template: $SRC_PLIST" >&2; exit 1
        fi
        mkdir -p "$HOME/Library/LaunchAgents"
        cp "$SRC_PLIST" "$DST_PLIST"
        launchctl unload "$DST_PLIST" 2>/dev/null || true
        launchctl load "$DST_PLIST"
        echo "installed: $DST_PLIST"
        echo "next fire: 周日 21:00 (StartCalendarInterval)"
        ;;
    uninstall)
        if [ -f "$DST_PLIST" ]; then
            launchctl unload "$DST_PLIST" 2>/dev/null || true
            rm "$DST_PLIST"
            echo "removed: $DST_PLIST"
        else
            echo "not installed"
        fi
        ;;
    status)
        if [ -f "$DST_PLIST" ]; then
            echo "installed: $DST_PLIST"
            launchctl list | grep "$LABEL" || echo "(not loaded)"
        else
            echo "not installed (template at $SRC_PLIST)"
        fi
        ;;
    trigger)
        if [ ! -f "$DST_PLIST" ]; then
            echo "not installed; run: $0 install" >&2; exit 1
        fi
        launchctl start "$LABEL"
        echo "triggered $LABEL — see $ROOT/.temp/launchd_*.log"
        ;;
    *)
        echo "usage: $0 {install|uninstall|status|trigger}" >&2; exit 1
        ;;
esac
