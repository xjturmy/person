"""周末自动更新管道:akshare 增量 → 全量重 ingest → validate 报告。

用法:
    .venv/bin/python .tools/db/update.py
    .venv/bin/python .tools/db/update.py --skip-akshare   # 仅重新 ingest+validate
    .venv/bin/python .tools/db/update.py --quiet          # 适合 cron(只在异常时报警)

退出码:
    0 = 全部 OK
    1 = validate 报 critical
    2 = akshare 抓取或 ingest 出错
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
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--industry-days", type=int, default=10)
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

    print(f"\nupdate done. log: {log_path}")
    return 1 if rc == 1 else 0


if __name__ == "__main__":
    sys.exit(main())
