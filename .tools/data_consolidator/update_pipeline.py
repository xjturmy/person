#!/usr/bin/env python3
"""
一键更新管道：
1. 从理杏仁抓取最新数据（10 年历史）
2. 自动整合到新目录结构（历史数据/ + 摘要.md）

使用方法：
    python3 .tools/data_consolidator/update_pipeline.py
    python3 .tools/data_consolidator/update_pipeline.py --skip-fetch  # 跳过抓取，仅整合
    python3 .tools/data_consolidator/update_pipeline.py --only=新华保险  # 只处理一家
"""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/gongyong/Desktop/Keyi/preson")
SCRIPTS = ROOT / ".tools"
CONSOLIDATOR = SCRIPTS / "data_consolidator" / "consolidate.py"
FETCH_PIPELINE = SCRIPTS / "lixinger-archiver" / "run_full_pipeline.py"


def run(cmd: list[str]) -> None:
    shown = " ".join(cmd)
    print(f"\n▶ {shown}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"❌ 命令失败（退出码 {result.returncode}）")
        sys.exit(result.returncode)


def main() -> None:
    p = argparse.ArgumentParser(description="一键数据更新：抓取 + 整合")
    p.add_argument("--days", type=int, default=365, help="日线估值数据天数（默认 365）")
    p.add_argument("--years", type=int, default=10, help="财报历史年数（默认 10）")
    p.add_argument("--token", default="", help="理杏仁 token（可省略，从 credentials 解析）")
    p.add_argument("--skip-fetch", action="store_true", help="跳过数据抓取，仅整合")
    p.add_argument("--skip-consolidate", action="store_true", help="跳过整合，仅抓取")
    p.add_argument("--only", default="", help="仅处理特定公司（按名称过滤）")
    args = p.parse_args()

    py = sys.executable

    # 步骤 1：抓取数据
    if not args.skip_fetch:
        print("=" * 60)
        print("📥 步骤 1/2：从理杏仁抓取最新数据")
        print("=" * 60)
        fetch_cmd = [
            py,
            str(FETCH_PIPELINE),
            "--companies-csv",
            ".config/companies.csv",
            "--days",
            str(args.days),
            "--years",
            str(args.years),
            "--base-dir",
            "02_companies",
            "--clean-existing",
        ]
        if args.token:
            fetch_cmd.extend(["--token", args.token])
        run(fetch_cmd)
    else:
        print("⏩ 跳过数据抓取")

    # 步骤 2：整合数据
    if not args.skip_consolidate:
        print("\n" + "=" * 60)
        print("🔧 步骤 2/2：整合数据到新结构")
        print("=" * 60)
        consolidate_cmd = [py, str(CONSOLIDATOR)]
        if args.only:
            consolidate_cmd.append(f"--only={args.only}")
        run(consolidate_cmd)
    else:
        print("⏩ 跳过数据整合")

    print("\n✅ 管道执行完成")


if __name__ == "__main__":
    main()
