#!/usr/bin/env python3
"""
一键执行理杏仁全流程：
1) 更新 01_估值分析（最近N天宽表）
2) 更新 02-05 财务模块
3) 运行 extract_recent_data.py 生成最近一个月提取
4) 将提取结果回写到 00_最近一月数据
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


def kb_root() -> Path:
    return Path(__file__).resolve().parents[4]


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def read_companies(companies_csv: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    with companies_csv.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        need = {"folder", "name"}
        if not r.fieldnames or not need.issubset(set(r.fieldnames)):
            raise SystemExit(f"companies.csv 缺少字段 {sorted(need)}，实际: {r.fieldnames}")
        for row in r:
            folder = (row.get("folder") or "").strip()
            name = (row.get("name") or "").strip()
            if folder and name:
                out.append((folder, name))
    if not out:
        raise SystemExit("companies.csv 无有效公司记录")
    return out


def run_cmd(cmd: list[str], cwd: Path) -> None:
    shown = " ".join(cmd)
    print(f"\n▶ {shown}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def sync_recent_month(*, root: Path, base_dir: str, companies: list[tuple[str, str]]) -> None:
    extracted_root = root / "最近一个月数据提取"
    archive_root = root / base_dir
    total = 0
    for folder, name in companies:
        src_dir = extracted_root / folder
        dst_dir = archive_root / folder / "01_基本面数据" / "00_最近一月数据"
        if not src_dir.is_dir():
            print(f"⚠ 跳过 {folder}: 未找到提取目录 {src_dir}")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)

        # 仅替换该公司文件，避免误删目录内其他资料
        for old in dst_dir.glob(f"{name}_*.csv"):
            old.unlink(missing_ok=True)
        for old in dst_dir.glob(f"{name}_*.md"):
            old.unlink(missing_ok=True)

        copied = 0
        for src in src_dir.glob(f"{name}_*.csv"):
            target = dst_dir / src.name
            target.write_bytes(src.read_bytes())
            copied += 1
        for src in src_dir.glob(f"{name}_*.md"):
            target = dst_dir / src.name
            target.write_bytes(src.read_bytes())
            copied += 1
        total += copied
        print(f"✅ 回写 {folder}: {copied} 个文件（含 CSV/MD）")
    print(f"\n🎉 回写完成，总计 {total} 个文件")


def main() -> None:
    p = argparse.ArgumentParser(description="一键执行理杏仁 01-05 + 最近一月回写")
    p.add_argument("--companies-csv", required=True, help="公司清单 CSV（至少包含 folder,stock,name）")
    p.add_argument("--token", required=False, help="理杏仁 token（可省略，走各脚本自动解析）")
    p.add_argument("--base-dir", default="02_公司档案库", help="公司档案库根目录")
    p.add_argument("--days", type=int, default=90, help="01估值分析拉取最近天数（默认90）")
    p.add_argument("--stats-window", default="y10", choices=["fs", "y20", "y10", "y5", "y3", "y1"], help="估值分位点窗口")
    p.add_argument("--years", type=int, default=10, help="02-05 财务模块历史年数（默认10）")
    p.add_argument("--skip-valuation", action="store_true", help="跳过 01_估值分析 更新")
    p.add_argument("--skip-fs", action="store_true", help="跳过 02-05 财务模块 更新")
    p.add_argument("--skip-extract", action="store_true", help="跳过 extract_recent_data.py")
    p.add_argument("--skip-sync", action="store_true", help="跳过回写到 00_最近一月数据")
    p.add_argument("--clean-existing", action="store_true", help="更新前清理脚本生成的同类旧CSV")
    args = p.parse_args()

    root = kb_root()
    companies_csv = (root / args.companies_csv).resolve() if not Path(args.companies_csv).is_absolute() else Path(args.companies_csv)
    companies = read_companies(companies_csv)

    py = sys.executable
    base_flags = ["--companies-csv", str(companies_csv), "--base-dir", args.base_dir]
    token_flags = ["--token", args.token] if (args.token or "").strip() else []
    clean_flags = ["--clean-existing"] if args.clean_existing else []

    if not args.skip_valuation:
        cmd = [
            py,
            str(scripts_dir() / "batch_update_recent_wide.py"),
            *token_flags,
            *base_flags,
            "--days",
            str(args.days),
            "--stats-window",
            args.stats_window,
            *clean_flags,
        ]
        run_cmd(cmd, cwd=root)

    if not args.skip_fs:
        cmd = [
            py,
            str(scripts_dir() / "batch_update_fs_modules.py"),
            *token_flags,
            *base_flags,
            "--years",
            str(args.years),
            *clean_flags,
        ]
        run_cmd(cmd, cwd=root)

    if not args.skip_extract:
        run_cmd([py, "extract_recent_data.py"], cwd=root)

    if not args.skip_sync:
        sync_recent_month(root=root, base_dir=args.base_dir, companies=companies)

    print("\n✅ 全流程执行完成")


if __name__ == "__main__":
    main()

