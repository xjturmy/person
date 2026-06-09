"""周末自动更新管道:akshare 增量 → 全量重 ingest → validate → 同行刷新。

用法:
    .venv/bin/python .tools/db/update.py
    .venv/bin/python .tools/db/update.py --skip-akshare   # 仅重新 ingest+validate
    .venv/bin/python .tools/db/update.py --skip-peers     # 跳过 peers 刷新
    .venv/bin/python .tools/db/update.py --quiet          # 适合 cron(只在异常时报警)

退出码:
    0 = 全部 OK
    1 = validate 报 critical
    2 = akshare 抓取或 ingest 出错
    (peers 刷新失败仅 warning,不阻塞退出码)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"
LOG_DIR = ROOT / ".temp"


def run(label: str, cmd: list[str], log_path: Path, quiet: bool) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >> {label}")
    print(f"   cmd: {' '.join(str(c) for c in cmd)}")
    print(f"   log: {log_path}")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n\n===== {label} @ {datetime.now()} =====\n")
        f.flush()
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if proc.returncode != 0 and not quiet:
        print(f"   ! exit={proc.returncode}, see log")
    elif not quiet:
        print(f"   ok")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-akshare", action="store_true")
    parser.add_argument("--skip-peers", action="store_true",
                        help="跳过 peers 刷新(同行池 + 基本面 + PEG)")
    parser.add_argument("--skip-gold", action="store_true",
                        help="跳过黄金模块更新(prices + real_rate + ETF + ratios)")
    parser.add_argument("--skip-market-spot", action="store_true",
                        help="跳过 v2.4 L1 全市场快照刷新(market.duckdb,~13 分钟)")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--industry-days", type=int, default=10)
    parser.add_argument("--peers-n", type=int, default=6,
                        help="每家公司选 n 个行业对标(默认 6)")
    parser.add_argument("--quiet", action="store_true",
                        help="仅在异常时打印(适合 cron)")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d")
    log_path = LOG_DIR / f"update_{stamp}.log"

    if not args.skip_akshare:
        rc = run(
            "fetch_akshare (incremental)",
            [str(PY), str(ROOT / ".tools/db/fetch_akshare.py"),
             "--years", str(args.years),
             "--industry-days", str(args.industry_days)],
            log_path, args.quiet,
        )
        if rc != 0:
            print(f"\nFAILED at fetch_akshare (see {log_path})")
            return 2

    rc = run("ingest (full rebuild)",
             [str(PY), str(ROOT / ".tools/db/ingest.py")],
             log_path, args.quiet)
    if rc != 0:
        print(f"\nFAILED at ingest (see {log_path})")
        return 2

    rc = run("validate", [str(PY), str(ROOT / ".tools/db/validate.py")],
             log_path, args.quiet)
    validate_rc = rc

    if not args.skip_peers:
        peers_rc = run(
            "fetch_peers (industry + fundamentals + PEG + F-Score lite)",
            [str(PY), str(ROOT / ".tools/db/fetch_peers.py"),
             "--n", str(args.peers_n)],
            log_path, args.quiet,
        )
        if peers_rc != 0 and not args.quiet:
            print(f"   ⚠️  peers 刷新失败(non-blocking),见 {log_path}")

    # ───── v2.4 候选 ⑨ Phase 1:L1 全市场快照(独立 market.duckdb,~13 分钟,失败不阻塞)─────
    if not args.skip_market_spot:
        spot_rc = run(
            "fetch_market_spot (L1 全 A 快照 + EM 行业映射)",
            [str(PY), str(ROOT / ".tools/db/fetch_market_spot.py"), "--quiet"],
            log_path, args.quiet,
        )
        if spot_rc != 0 and not args.quiet:
            print(f"   ⚠️  market_spot 刷新失败(non-blocking),见 {log_path}")

    # ───── 黄金模块(独立 gold.duckdb,失败不阻塞主流程)─────
    if not args.skip_gold:
        gold_steps = [
            ("fetch_gold_prices",     ".tools/db/fetch_gold_prices.py"),
            ("fetch_real_rate",       ".tools/db/fetch_real_rate.py"),
            ("fetch_gold_etf",        ".tools/db/fetch_gold_etf.py"),
            ("fetch_gold_etf_share",  ".tools/db/fetch_gold_etf_share.py"),  # v2.4 step-D
            ("fetch_gold_stock_etf",  ".tools/db/fetch_gold_stock_etf.py"),  # v2.6 主题 3 板块 F
            ("fetch_gold_ratios",     ".tools/db/fetch_gold_ratios.py"),
        ]
        for label, script in gold_steps:
            extra = ["--skip-spdr"] if label == "fetch_gold_etf" else []
            gold_rc = run(label,
                          [str(PY), str(ROOT / script), *extra],
                          log_path, args.quiet)
            if gold_rc != 0 and not args.quiet:
                print(f"   ⚠️  {label} 失败(non-blocking),见 {log_path}")

        # Phase 2.4 范式引擎:每周记录一次投票快照
        engine_rc = run(
            "paradigm_engine (vote + record snapshot)",
            [str(PY), str(ROOT / ".tools/dashboard/paradigm_engine.py"), "--write"],
            log_path, args.quiet,
        )
        if engine_rc != 0 and not args.quiet:
            print(f"   ⚠️  paradigm_engine 失败(non-blocking),见 {log_path}")

        # v2.4 step-D · 短期过热引擎:每周记录一次投票快照
        overheat_rc = run(
            "overheat_engine (gold short-term overheat vote)",
            [str(PY), str(ROOT / ".tools/dashboard/overheat_engine.py"), "--write"],
            log_path, args.quiet,
        )
        if overheat_rc != 0 and not args.quiet:
            print(f"   ⚠️  overheat_engine 失败(non-blocking),见 {log_path}")

    print(f"\nupdate done. log: {log_path}")
    return 1 if validate_rc == 1 else 0


if __name__ == "__main__":
    sys.exit(main())
