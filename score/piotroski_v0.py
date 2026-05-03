"""
Piotroski v0 原型 — 跨公司、多年份批量验证 F-Score 规则。

数据源:`data/preson.duckdb`(由 .tools/db/ingest.py 生成);
读 companies 表的 ticker × 4 张 fs 表的年末(12-31)数据,输出 F-Score 时间线。

用法:
    python3 .tools/score/piotroski_v0.py                 # 默认 5 家
    python3 .tools/score/piotroski_v0.py --tickers 600519,600887,000333
    python3 .tools/score/piotroski_v0.py --all            # 全部 15 家
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from importlib.machinery import SourceFileLoader

ENGINE = SourceFileLoader(
    "engine",
    str(Path(__file__).parent / "engine.py")
).load_module()

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "preson.duckdb"

DEFAULT_TICKERS = ["600519", "600887", "000333", "000858", "300750"]


def list_all_tickers() -> list[tuple[str, str]]:
    import duckdb
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(
            "SELECT ticker, name FROM companies ORDER BY folder"
        ).fetchall()
    finally:
        con.close()


def run(tickers: list[str], years: list[int]):
    rules_path = ROOT / ".tools" / "rules" / "piotroski.yaml"

    print(f"\n{'='*80}")
    print(f"  Piotroski F-Score v0 跨公司 / 多年份验证 (DuckDB 数据源)")
    print(f"{'='*80}\n")

    header = f"{'公司':<14}" + "".join(f"{y:>8}" for y in years)
    print(header)
    print("-" * len(header))

    for ticker in tickers:
        try:
            data = ENGINE.load_duckdb_data(ticker)
        except (ValueError, FileNotFoundError) as e:
            print(f"⚠️  {ticker} 加载失败:{e}")
            continue

        scores: list[str] = []
        for y in years:
            result = ENGINE.run_score(rules_path, data, y)
            if result is None:
                scores.append("skip")
            else:
                non_none = sum(1 for d in result.details if d.passed is not None)
                scores.append(f"{int(result.total_score)}/{non_none}")

        row = f"{data.name:<12}" + "".join(f"{s:>8}" for s in scores)
        print(row)

    print()
    print("📌 格式:得分/有效项数(None = 数据缺失,不计入分母)")
    print("📌 P1 已解锁:f4/f5/f7/f9 用衍生指标改写,非金融公司满分项数 = 9")
    print("📌 P3 待办:银行/保险公司部分指标(roa/cfo)不返回,显示 X/6 而非 X/9")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                    help="逗号分隔的 ticker(默认 5 家)")
    ap.add_argument("--all", action="store_true", help="跑全部 15 家")
    ap.add_argument("--years", default="2020,2021,2022,2023,2024,2025",
                    help="逗号分隔的年份")
    args = ap.parse_args()

    if args.all:
        tickers = [t for t, _ in list_all_tickers()]
    else:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    years = [int(y) for y in args.years.split(",")]

    run(tickers, years)


if __name__ == "__main__":
    main()
