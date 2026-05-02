#!/usr/bin/env python3
"""
ETF 数据定期更新机制

设置:
  成分股列表: 按季度更新（每个季度第一天）
  财务数据: 按月度更新（每个月第一天）

使用方式:
  python3 update_etf_data_scheduler.py --schedule
  python3 update_etf_data_scheduler.py --now --type constituents
  python3 update_etf_data_scheduler.py --now --type fundamentals
"""

import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import json

class ETFDataScheduler:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.config_file = self.project_root / ".tools" / "etf_update_schedule.json"
        self.load_config()

    def load_config(self):
        """加载更新计划配置"""
        if self.config_file.exists():
            with open(self.config_file) as f:
                self.config = json.load(f)
        else:
            self.config = {
                "last_constituents_update": None,
                "last_fundamentals_update": None,
                "constituents_update_interval_days": 90,  # 按季度
                "fundamentals_update_interval_days": 30   # 按月
            }
            self.save_config()

    def save_config(self):
        """保存更新计划配置"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)

    def should_update_constituents(self):
        """判断是否需要更新成分股"""
        last_update = self.config.get("last_constituents_update")
        interval = self.config.get("constituents_update_interval_days", 90)

        if not last_update:
            return True

        last_date = datetime.fromisoformat(last_update)
        days_since = (datetime.now() - last_date).days

        return days_since >= interval

    def should_update_fundamentals(self):
        """判断是否需要更新财务数据"""
        last_update = self.config.get("last_fundamentals_update")
        interval = self.config.get("fundamentals_update_interval_days", 30)

        if not last_update:
            return True

        last_date = datetime.fromisoformat(last_update)
        days_since = (datetime.now() - last_date).days

        return days_since >= interval

    def run_update_constituents(self):
        """运行成分股更新脚本"""
        script = self.project_root / ".tools" / "fetch_etf_constituents.py"

        if not script.exists():
            print(f"❌ 脚本不存在: {script}")
            return False

        print("\n" + "=" * 80)
        print("📊 更新 ETF 成分股列表")
        print("=" * 80)

        try:
            result = subprocess.run(
                [sys.executable, str(script), "--all", "--source", "sample"],
                cwd=self.project_root
            )

            if result.returncode == 0:
                self.config["last_constituents_update"] = datetime.now().isoformat()
                self.save_config()
                print("\n✅ 成分股更新成功")
                return True
            else:
                print("\n❌ 成分股更新失败")
                return False

        except Exception as e:
            print(f"\n❌ 执行脚本失败: {str(e)}")
            return False

    def run_update_fundamentals(self):
        """运行财务数据更新脚本"""
        script = self.project_root / ".tools" / "fetch_etf_fundamentals.py"

        if not script.exists():
            print(f"❌ 脚本不存在: {script}")
            return False

        print("\n" + "=" * 80)
        print("📈 更新 ETF 成分股财务数据")
        print("=" * 80)

        try:
            result = subprocess.run(
                [sys.executable, str(script), "--all", "--source", "sample"],
                cwd=self.project_root
            )

            if result.returncode == 0:
                self.config["last_fundamentals_update"] = datetime.now().isoformat()
                self.save_config()
                print("\n✅ 财务数据更新成功")
                return True
            else:
                print("\n❌ 财务数据更新失败")
                return False

        except Exception as e:
            print(f"\n❌ 执行脚本失败: {str(e)}")
            return False

    def check_and_update(self):
        """检查并执行需要的更新"""
        print("=" * 80)
        print("ETF 数据定期更新检查")
        print("=" * 80)

        updated = False

        if self.should_update_constituents():
            print("\n📌 成分股需要更新")
            if self.run_update_constituents():
                updated = True
        else:
            last_update = self.config.get("last_constituents_update", "未更新过")
            print(f"\n✅ 成分股列表已是最新 (上次更新: {last_update})")

        if self.should_update_fundamentals():
            print("\n📌 财务数据需要更新")
            if self.run_update_fundamentals():
                updated = True
        else:
            last_update = self.config.get("last_fundamentals_update", "未更新过")
            print(f"\n✅ 财务数据已是最新 (上次更新: {last_update})")

        if updated:
            print("\n" + "=" * 80)
            print("✅ 所有必要的数据已更新")
            print("=" * 80)
            return True
        else:
            print("\n" + "=" * 80)
            print("ℹ️  暂不需要更新")
            print("=" * 80)
            return False

def main():
    parser = argparse.ArgumentParser(description="ETF数据定期更新管理")
    parser.add_argument("--schedule", action="store_true",
                       help="检查并执行定期更新")
    parser.add_argument("--now", action="store_true",
                       help="立即执行更新")
    parser.add_argument("--type", choices=["constituents", "fundamentals"],
                       help="更新类型 (与 --now 一起使用)")
    parser.add_argument("--project-root", default="/Users/gongyong/Desktop/Keyi/Ruby/preson",
                       help="项目根目录")
    parser.add_argument("--show-config", action="store_true",
                       help="显示当前配置")

    args = parser.parse_args()

    scheduler = ETFDataScheduler(args.project_root)

    if args.show_config:
        print("\n当前更新配置:")
        print(json.dumps(scheduler.config, indent=2, ensure_ascii=False))
        return 0

    if args.schedule:
        return 0 if scheduler.check_and_update() else 1

    if args.now:
        if not args.type:
            print("❌ 错误: --now 需要指定 --type")
            parser.print_help()
            return 1

        if args.type == "constituents":
            return 0 if scheduler.run_update_constituents() else 1
        else:
            return 0 if scheduler.run_update_fundamentals() else 1

    # 默认行为：检查并更新
    return 0 if scheduler.check_and_update() else 1

if __name__ == "__main__":
    sys.exit(main())
