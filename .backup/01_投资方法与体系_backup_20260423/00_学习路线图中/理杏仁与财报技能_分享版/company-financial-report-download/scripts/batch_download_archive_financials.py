#!/usr/bin/env python3
"""
公司档案库：按映射表批量下载最近 N 年定期报告 PDF 至各公司 02_公司财报/（复用 download_cninfo_reports）。

默认包含：年报 + 一季报 + 半年报 + 三季报（巨潮四类 category）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

# 同目录单公司脚本
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from download_cninfo_reports import (  # noqa: E402
    download_reports,
    guess_column,
    load_org_id,
)

# 巨潮「深沪」定期报告分类（与网站 history-notice.js 一致）
DEFAULT_CATEGORIES = (
    "category_ndbg_szsh",  # 年度报告
    "category_yjdbg_szsh",  # 一季度报告
    "category_bndbg_szsh",  # 半年度报告
    "category_sjdbg_szsh",  # 三季度报告
)

CATEGORY_LABEL_ZH = {
    "category_ndbg_szsh": "年度报告",
    "category_yjdbg_szsh": "一季度报告",
    "category_bndbg_szsh": "半年度报告",
    "category_sjdbg_szsh": "三季度报告",
}


def _parse_date(s: str) -> dt.date:
    y, m, d = (int(x) for x in s.strip().split("-"))
    return dt.date(y, m, d)


def _years_ago(end: dt.date, years: int) -> dt.date:
    y = end.year - years
    try:
        return dt.date(y, end.month, end.day)
    except ValueError:
        return dt.date(y, end.month, 28)


def folder_to_company_name(folder: str) -> str:
    parts = folder.split("_", 1)
    if len(parts) == 2 and parts[1].strip():
        return parts[1].strip()
    return folder.strip()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            if not raw:
                continue
            folder = (raw.get("folder") or "").strip()
            if not folder or folder.startswith("#"):
                continue
            stock = (raw.get("stock") or "").strip()
            skip = (raw.get("skip") or "").strip()
            rows.append({"folder": folder, "stock": stock, "skip": skip})
    return rows


def main() -> None:
    p = argparse.ArgumentParser(
        description="公司档案库：批量下载最近 N 年定期报告（默认年报+一季报+半年报+三季报）至 02_公司财报/"
    )
    p.add_argument(
        "--archive-root",
        type=Path,
        default=Path("02_公司档案库"),
        help="档案库根目录（相对当前工作目录或绝对路径）",
    )
    p.add_argument(
        "--companies-csv",
        type=Path,
        default=Path("02_公司档案库/_财报批量下载/companies.csv"),
        help="映射表 CSV：列 folder, stock, skip",
    )
    p.add_argument("--years", type=int, default=10, help="回溯年数，默认 10")
    p.add_argument(
        "--end-date",
        default=None,
        help="公告日期区间结束日 YYYY-MM-DD，默认今天",
    )
    p.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="逗号分隔的巨潮 category；默认年报+一季报+半年报+三季报四类",
    )
    p.add_argument(
        "--category",
        default=None,
        metavar="CAT",
        help="仅下载单一分类（如仅年报 category_ndbg_szsh），指定时忽略 --categories",
    )
    p.add_argument("--sleep", type=float, default=0.8, help="单次下载间隔秒数")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--only-folder",
        default=None,
        help="只处理某一文件夹名，如 06_贵州茅台",
    )
    p.add_argument(
        "--exclude-in-title",
        default="摘要,英文版,English",
        help="逗号分隔；标题含任一子串则跳过。默认排除摘要/英文版；置空表示不过滤",
    )
    args = p.parse_args()

    root = args.archive_root.resolve()
    csv_path = args.companies_csv
    if not csv_path.is_absolute():
        csv_path = (Path.cwd() / csv_path).resolve()

    if not csv_path.is_file():
        raise SystemExit(f"找不到映射表: {csv_path}")

    end_d = _parse_date(args.end_date) if args.end_date else dt.date.today()
    start_d = _years_ago(end_d, args.years)

    rows = load_rows(csv_path)
    if args.only_folder:
        rows = [r for r in rows if r["folder"] == args.only_folder]
        if not rows:
            raise SystemExit(f"--only-folder 未匹配任何行: {args.only_folder}")

    excl = [s.strip() for s in (args.exclude_in_title or "").split(",") if s.strip()]

    if args.category:
        cat_list = [args.category.strip()]
    else:
        cat_list = [s.strip() for s in (args.categories or "").split(",") if s.strip()]
    if not cat_list:
        raise SystemExit("未指定任何 --categories")

    cat_desc = ", ".join(CATEGORY_LABEL_ZH.get(c, c) for c in cat_list)
    print(
        f"区间: {start_d.isoformat()} ~ {end_d.isoformat()} | 根: {root}\n"
        f"分类 ({len(cat_list)}): {cat_desc}"
    )
    if excl:
        print(f"标题过滤（含则跳过）: {excl}")

    for i, row in enumerate(rows):
        folder = row["folder"]
        stock = row["stock"]
        skip = row["skip"]
        if skip:
            print(f"[跳过] {folder} ({skip})")
            continue
        if not stock or len(stock.replace(" ", "")) < 6:
            print(f"[跳过] {folder}（未填写 stock）")
            continue

        out_dir = root / folder / "02_公司财报"
        company_name = folder_to_company_name(folder)
        print(
            f"\n--- ({i + 1}/{len(rows)}) {folder} -> {stock} -> {out_dir} | 公司名: {company_name} ---"
        )
        code = stock.strip().zfill(6)
        oid = load_org_id(code)
        col = guess_column(code)
        for cat in cat_list:
            label = CATEGORY_LABEL_ZH.get(cat, cat)
            print(f"\n  ▸ [{label}] {cat}")
            download_reports(
                code=stock,
                org_id=oid,
                column=col,
                category=cat,
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                out_dir=out_dir,
                sleep_s=args.sleep,
                dry_run=args.dry_run,
                title_exclude_substrings=excl or None,
                company_name=company_name,
            )


if __name__ == "__main__":
    main()
