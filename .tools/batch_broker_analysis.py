#!/usr/bin/env python3
"""
批量抓取公司档案库中所有公司（A股 + 港股）的券商分析数据。

读取 companies.csv，对每家公司调用 Tushare report_rc 接口（A股与港股均尝试），
收盘价港股用 hk_daily，A股用 daily，将结果写入各公司档案库的 04_券商分析/ 文件夹。

用法：
    python batch_broker_analysis.py [--token TOKEN] [--start-date YYYYMMDD] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


def _kb_root() -> Path:
    return Path(__file__).resolve().parent


def _infer_exchange(code: str, category: str = "") -> str:
    """根据 category 或代码前缀推断交易所后缀。"""
    if category.lower() == "hk":
        return "HK"
    if code.startswith(("60", "68")):
        return "SH"
    if code.startswith(("00", "30", "002", "003")):
        return "SZ"
    if code.startswith(("83", "87", "43")):
        return "BJ"
    return "SH"


def _normalize_hk_code(code: str) -> str:
    """港股代码补齐5位，如 02097 → 02097，2097 → 02097。"""
    return code.zfill(5)


def _load_companies(csv_path: Path) -> list[dict]:
    companies = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skip = (row.get("skip") or "").strip()
            stock = (row.get("stock") or "").strip()
            folder = (row.get("folder") or "").strip()
            name = (row.get("name") or folder).strip()
            category = (row.get("category") or "").strip()
            if skip or not stock or not folder:
                continue
            exchange = _infer_exchange(stock, category)
            if exchange == "HK":
                ts_code = f"{_normalize_hk_code(stock)}.HK"
            else:
                ts_code = f"{stock}.{exchange}"
            companies.append(
                {
                    "folder": folder,
                    "stock": stock,
                    "ts_code": ts_code,
                    "name": name,
                    "is_hk": exchange == "HK",
                }
            )
    return companies


def _run_one(
    pro,
    company: dict,
    start_date: str,
    end_date: str,
    kb_root: Path,
    latest_close_cache: dict,
) -> tuple[bool, str]:
    """对单家公司拉取数据并写入文件，返回 (success, message)。"""
    # 延迟导入，避免在 dry-run 时也依赖
    from fetch_tushare_broker_analysis import (
        _build_consensus_file,
        _build_revision_file,
        _build_target_file,
        _extract_rows,
        _latest_close,
        _write_summary_md,
    )

    ts_code = company["ts_code"]
    name = company["name"]
    is_hk = company.get("is_hk", False)
    output_dir = (kb_root / "02_companies" / company["folder"] / "04_research").resolve()

    df = None
    rc_note = ""
    try:
        df = pro.report_rc(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as exc:
        if is_hk:
            # 港股 report_rc 可能不支持，写空文件 + 说明，不视为失败
            rc_note = f"report_rc 未返回数据（{exc}）"
        else:
            return False, f"report_rc 拉取失败：{exc}"

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _extract_rows(df if df is not None else [])

    if ts_code not in latest_close_cache:
        try:
            latest_close_cache[ts_code] = _latest_close(pro, ts_code)
        except Exception:
            latest_close_cache[ts_code] = None
    latest_close = latest_close_cache[ts_code]

    _build_consensus_file(rows, output_dir / "01_盈利预测与一致预期.csv")
    _build_target_file(rows, latest_close, output_dir / "02_评级与目标价.csv")
    _build_revision_file(rows, output_dir / "03_预期修正与分歧跟踪.csv")
    _write_summary_md(rows, output_dir / "04_券商观点摘要.md", company_name=name)

    # 港股额外写一个说明文件
    if is_hk and rc_note:
        note_path = output_dir / "00_港股研报说明.md"
        note_path.write_text(
            f"# 港股研报说明（{name}）\n\n"
            f"- **股票代码**：{ts_code}\n"
            f"- **Tushare report_rc**：{rc_note}\n\n"
            "## 建议获取途径\n\n"
            "- **富途牛牛 / 老虎证券**：港股研报聚合，免费浏览\n"
            "- **Bloomberg / Wind**：付费，覆盖完整\n"
            "- **各大内资券商 App**（国泰君安、中信证券等）：对开户用户免费提供港股研报\n"
            "- **公司官网投资者关系**：业绩发布材料、路演 PPT\n",
            encoding="utf-8",
        )

    row_count = 0 if df is None else len(df)
    suffix = f"（港股，{rc_note}）" if is_hk and rc_note else ""
    return True, f"report_rc {row_count} 行{suffix} → {output_dir}"


def main() -> int:
    parser = argparse.ArgumentParser(description="批量抓取公司档案库券商分析数据")
    parser.add_argument("--token", default="", help="Tushare Pro token")
    parser.add_argument(
        "--start-date",
        default=(datetime.now() - timedelta(days=365 * 2)).strftime("%Y%m%d"),
        help="开始日期，格式 YYYYMMDD，默认近2年",
    )
    parser.add_argument(
        "--end-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="结束日期，格式 YYYYMMDD，默认今天",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将要处理的公司列表，不实际拉取数据",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="每家公司之间的等待秒数，避免触发频率限制（默认 1.5s）",
    )
    parser.add_argument(
        "--company",
        default="",
        help="只处理指定公司（文件夹名或股票代码），留空则处理全部",
    )
    args = parser.parse_args()

    kb_root = _kb_root()
    # 优先使用 .config/companies.csv（含 name 字段），fallback 到档案库内
    csv_path = kb_root / ".config" / "companies.csv"
    if not csv_path.is_file():
        # 旧位置备选
        csv_path = kb_root / "companies.csv"
    if not csv_path.is_file():
        # 最后备选：存档目录
        csv_path = kb_root / ".archive" / "financials_batch" / "companies.csv"
    if not csv_path.is_file():
        print(f"找不到 companies.csv：{csv_path}")
        return 2

    companies = _load_companies(csv_path)
    if not companies:
        print("companies.csv 中没有可处理的公司（检查 skip 列）。")
        return 2

    # 按指定公司过滤
    if args.company:
        filter_val = args.company.strip().lower()
        companies = [
            c for c in companies
            if filter_val in c["folder"].lower()
            or filter_val in c["stock"].lower()
            or filter_val in c["name"].lower()
        ]
        if not companies:
            print(f"未找到匹配公司：{args.company}")
            return 2

    print(f"共 {len(companies)} 家公司待处理：")
    for c in companies:
        print(f"  {c['folder']}  {c['ts_code']}  {c['name']}")

    if args.dry_run:
        print("\n[dry-run] 不实际拉取，退出。")
        return 0

    # 解析 token
    token = (args.token or os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        token_file = kb_root / ".tushare_token"
        if token_file.is_file():
            token = token_file.read_text(encoding="utf-8").splitlines()[0].strip()
    if not token:
        account_md = kb_root / "03_行业与宏观" / "账号密码.md"
        if account_md.is_file():
            import re
            text = account_md.read_text(encoding="utf-8")
            for line in text.splitlines():
                m = re.search(r"(?i)tushare.*token\s*[:：]\s*(\S+)", line)
                if m:
                    token = m.group(1).strip()
                    break
    if not token:
        print("未找到 Tushare Token。请通过 --token 或环境变量 TUSHARE_TOKEN 提供。")
        return 2

    import tushare as ts
    pro = ts.pro_api(token)

    results: list[tuple[str, bool, str]] = []
    latest_close_cache: dict = {}

    for i, company in enumerate(companies):
        label = f"[{i+1}/{len(companies)}] {company['name']} ({company['ts_code']})"
        print(f"\n{label} 处理中…")
        success, msg = _run_one(
            pro, company, args.start_date, args.end_date, kb_root, latest_close_cache
        )
        status = "✓" if success else "✗"
        print(f"  {status} {msg}")
        results.append((company["name"], success, msg))

        if i < len(companies) - 1:
            time.sleep(args.delay)

    print("\n" + "=" * 50)
    print("批量处理完成汇总：")
    ok = [r for r in results if r[1]]
    fail = [r for r in results if not r[1]]
    print(f"  成功：{len(ok)} 家 / 失败：{len(fail)} 家")
    if fail:
        print("  失败列表：")
        for name, _, msg in fail:
            print(f"    {name}：{msg}")

    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
