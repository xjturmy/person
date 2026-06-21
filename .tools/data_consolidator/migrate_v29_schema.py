"""Dashboard v2.9 一次性 schema 迁移脚本 (P0c).

幂等地为 .config/focus_industries.yaml 与 .config/watchlist.yaml 补齐 v2.9
新增字段:

- focus_industries.yaml -> focus[*].confirmed_at  (缺则填 "unknown")
- watchlist.yaml        -> entries[*].source_industry
    缺则反查 companies.csv 的 industry_l2 (按 ticker 匹配);
    反查不命中 -> "unknown"

用法:
    python3 .tools/data_consolidator/migrate_v29_schema.py            # 实际写入
    python3 .tools/data_consolidator/migrate_v29_schema.py --dry-run  # 仅打印 diff

写入前对原文件复制 xxx.yaml.bak (覆盖旧 .bak)。
再次运行检测到两份文件全部条目已有目标字段,提示 already migrated 退出。
"""
from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

# ─── 路径常量 (测试可 monkeypatch) ──────────────────────────────────────────
_PRESON_ROOT = Path(__file__).resolve().parents[2]
FOCUS_YAML_PATH = _PRESON_ROOT / ".config" / "focus_industries.yaml"
WATCHLIST_YAML_PATH = _PRESON_ROOT / ".config" / "watchlist.yaml"
COMPANIES_CSV_PATH = _PRESON_ROOT / ".config" / "companies.csv"

_logger = logging.getLogger("migrate_v29_schema")


# ─── 工具函数 ──────────────────────────────────────────────────────────────
def _normalize_ticker_variants(raw: str) -> list[str]:
    """生成一个 ticker 的所有规范化变体,用于双向匹配.

    输入示例:
        "600519"     -> ["600519", "600519.SH", "600519.SZ"]
        "600519.SH"  -> ["600519", "600519.SH"]
        "2097"       -> ["2097", "002097", "002097.SZ", "002097.SH", "2097.SH", "2097.SZ"]
    """
    if raw is None:
        return []
    s = str(raw).strip().upper()
    if not s:
        return []

    # 拆 base 与后缀
    if "." in s:
        base, _, suffix = s.partition(".")
        variants = {s, base}
    else:
        base = s
        variants = {base}

    # 补到 6 位 (A 股常见)
    if base.isdigit() and len(base) < 6:
        padded = base.zfill(6)
        variants.add(padded)
        variants.add(f"{padded}.SH")
        variants.add(f"{padded}.SZ")

    # 原始数字也加上常见后缀
    if base.isdigit():
        variants.add(f"{base}.SH")
        variants.add(f"{base}.SZ")

    return list(variants)


def _load_industry_lookup(companies_csv: Path) -> dict[str, str]:
    """读 companies.csv,返回 {规范化 ticker 变体 -> industry_l2}.

    每条记录的 stock 字段会展开为所有变体,均映射到同一 industry_l2.
    """
    lookup: dict[str, str] = {}
    if not companies_csv.exists():
        _logger.warning("companies.csv 不存在: %s", companies_csv)
        return lookup

    with companies_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stock = (row.get("stock") or "").strip()
            industry_l2 = (row.get("industry_l2") or "").strip()
            if not stock or not industry_l2:
                continue
            for variant in _normalize_ticker_variants(stock):
                lookup[variant] = industry_l2
    return lookup


def _lookup_industry(ticker: str, lookup: dict[str, str]) -> str | None:
    for variant in _normalize_ticker_variants(ticker):
        if variant in lookup:
            return lookup[variant]
    return None


# ─── focus_industries.yaml 处理 ────────────────────────────────────────────
def _process_focus(data: Any) -> tuple[Any, int, int, list[str]]:
    """返回 (新 data, 已迁移条数, 跳过(已有字段)条数, diff 行)."""
    diffs: list[str] = []
    migrated = 0
    skipped = 0
    if not isinstance(data, dict):
        return data, 0, 0, diffs
    focus = data.get("focus")
    if not isinstance(focus, list):
        return data, 0, 0, diffs
    for item in focus:
        if not isinstance(item, dict):
            continue
        if "confirmed_at" in item:
            skipped += 1
            continue
        item["confirmed_at"] = "unknown"
        migrated += 1
        ind = item.get("industry", "?")
        diffs.append(f"  + focus[{ind}].confirmed_at = 'unknown'")
    return data, migrated, skipped, diffs


# ─── watchlist.yaml 处理 ──────────────────────────────────────────────────
def _process_watchlist(
    data: Any, industry_lookup: dict[str, str]
) -> tuple[Any, int, int, list[str]]:
    diffs: list[str] = []
    migrated = 0
    skipped = 0
    if not isinstance(data, dict):
        return data, 0, 0, diffs
    entries = data.get("entries")
    if not isinstance(entries, list):
        return data, 0, 0, diffs
    for item in entries:
        if not isinstance(item, dict):
            continue
        if "source_industry" in item:
            skipped += 1
            continue
        ticker = str(item.get("ticker", "")).strip()
        found = _lookup_industry(ticker, industry_lookup) if ticker else None
        value = found if found else "unknown"
        item["source_industry"] = value
        migrated += 1
        name = item.get("name", "?")
        diffs.append(f"  + entries[{ticker} {name}].source_industry = {value!r}")
    return data, migrated, skipped, diffs


# ─── 文件 IO ──────────────────────────────────────────────────────────────
def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dump_yaml(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


# ─── 主入口 ───────────────────────────────────────────────────────────────
def run(
    focus_path: Path = FOCUS_YAML_PATH,
    watchlist_path: Path = WATCHLIST_YAML_PATH,
    companies_path: Path = COMPANIES_CSV_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行迁移,返回结构化报告."""
    report: dict[str, Any] = {
        "focus": {"path": str(focus_path), "migrated": 0, "skipped": 0, "status": "ok"},
        "watchlist": {
            "path": str(watchlist_path),
            "migrated": 0,
            "skipped": 0,
            "status": "ok",
        },
        "dry_run": dry_run,
        "all_migrated": False,
    }

    # ── focus ──
    if not focus_path.exists():
        _logger.info("focus 文件不存在,跳过: %s", focus_path)
        report["focus"]["status"] = "missing"
        focus_diffs: list[str] = []
        focus_data = None
    else:
        focus_data = _load_yaml(focus_path)
        focus_data, fm, fs, focus_diffs = _process_focus(focus_data)
        report["focus"]["migrated"] = fm
        report["focus"]["skipped"] = fs

    # ── watchlist ──
    industry_lookup = _load_industry_lookup(companies_path)
    if not watchlist_path.exists():
        _logger.info("watchlist 文件不存在,跳过: %s", watchlist_path)
        report["watchlist"]["status"] = "missing"
        wl_diffs: list[str] = []
        wl_data = None
    else:
        wl_data = _load_yaml(watchlist_path)
        wl_data, wm, ws, wl_diffs = _process_watchlist(wl_data, industry_lookup)
        report["watchlist"]["migrated"] = wm
        report["watchlist"]["skipped"] = ws

    total_migrated = report["focus"]["migrated"] + report["watchlist"]["migrated"]
    if total_migrated == 0 and (
        report["focus"]["status"] != "missing"
        or report["watchlist"]["status"] != "missing"
    ):
        report["all_migrated"] = True
        print("[migrate_v29] already migrated, skip (两份文件每条目均已有目标字段)")
        return report

    # 输出 diff
    print("=" * 60)
    print(f"[migrate_v29] {'DRY-RUN' if dry_run else 'WRITE'} mode")
    print("=" * 60)
    print(
        f"focus_industries.yaml: migrated={report['focus']['migrated']} "
        f"skipped={report['focus']['skipped']} status={report['focus']['status']}"
    )
    for d in focus_diffs:
        print(d)
    print(
        f"watchlist.yaml      : migrated={report['watchlist']['migrated']} "
        f"skipped={report['watchlist']['skipped']} status={report['watchlist']['status']}"
    )
    for d in wl_diffs:
        print(d)
    print("=" * 60)

    if dry_run:
        print("[migrate_v29] dry-run: 文件未改动")
        return report

    # 实写: 先备份再写
    if focus_data is not None and report["focus"]["migrated"] > 0:
        bak = _backup(focus_path)
        print(f"[migrate_v29] backup -> {bak}")
        _dump_yaml(focus_path, focus_data)
        print(f"[migrate_v29] wrote {focus_path}")
    if wl_data is not None and report["watchlist"]["migrated"] > 0:
        bak = _backup(watchlist_path)
        print(f"[migrate_v29] backup -> {bak}")
        _dump_yaml(watchlist_path, wl_data)
        print(f"[migrate_v29] wrote {watchlist_path}")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dashboard v2.9 schema 迁移")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印 diff,不写文件",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
