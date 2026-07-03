#!/usr/bin/env python3
"""Read-only health check for preson DuckDB data files.

Usage:
    python .tools/db/healthcheck.py
    .venv/bin/python .tools/db/healthcheck.py

Outputs:
    - console summary
    - .temp/db_healthcheck.md

Exit code:
    - 1 if any critical issue is found
    - 0 otherwise; warnings do not fail the run
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import duckdb
except ModuleNotFoundError:  # pragma: no cover - depends on caller environment
    print("CRITICAL: Python package 'duckdb' is not installed in this environment.")
    print("Hint: run with the project virtualenv, for example .venv/bin/python .tools/db/healthcheck.py")
    raise SystemExit(1)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
REPORT_PATH = ROOT / ".temp" / "db_healthcheck.md"

CHECKED_DBS = [
    "preson.duckdb",
    "analytics.duckdb",
    "market.duckdb",
    "peers.duckdb",
    "gold.duckdb",
    "etf.duckdb",
    "decisions.duckdb",
]

PRESON_REQUIRED_TABLES = {
    "companies",
    "valuation",
    "prices",
    "profitability",
    "growth",
    "cashflow",
    "safety",
}
FINANCIAL_TABLES = ["profitability", "growth", "cashflow", "safety"]
FRESHNESS_LIMIT_DAYS = {
    "valuation": 45,
    "prices": 10,
}


@dataclass
class Issue:
    severity: str
    component: str
    message: str


@dataclass
class CheckResult:
    checked_at: datetime
    dbs: dict[str, dict[str, Any]] = field(default_factory=dict)
    preson: dict[str, Any] = field(default_factory=dict)
    analytics: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "critical")

    @property
    def warn_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warn")


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def issue(result: CheckResult, severity: str, component: str, message: str) -> None:
    result.issues.append(Issue(severity=severity, component=component, message=message))


def safe_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def safe_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def expected_report_period(today: date) -> date:
    """Latest CN-listed-company report period whose deadline has normally passed."""
    year = today.year
    if today >= date(year, 11, 1):
        return date(year, 9, 30)
    if today >= date(year, 9, 1):
        return date(year, 6, 30)
    if today >= date(year, 5, 1):
        return date(year, 3, 31)
    return date(year - 1, 9, 30)


def connect_readonly(path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path), read_only=True)


def list_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        row[0]
        for row in con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            """
        ).fetchall()
    }


def table_columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    return {
        row[0]
        for row in con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'main' AND table_name = ?
            """,
            [table],
        ).fetchall()
    }


def table_summary(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, Any]:
    qtable = quote_ident(table)
    row_count = con.execute(f"SELECT COUNT(*) FROM {qtable}").fetchone()[0]
    columns = table_columns(con, table)
    summary: dict[str, Any] = {"rows": int(row_count or 0)}
    if "date" in columns:
        min_date, max_date = con.execute(f"SELECT MIN(date), MAX(date) FROM {qtable}").fetchone()
        summary["min_date"] = str(min_date) if min_date else None
        summary["max_date"] = str(max_date) if max_date else None
    if "ticker" in columns:
        tickers = con.execute(f"SELECT COUNT(DISTINCT ticker) FROM {qtable}").fetchone()[0]
        summary["tickers"] = int(tickers or 0)
    return summary


def check_database_files(result: CheckResult) -> None:
    for name in CHECKED_DBS:
        path = DATA_DIR / name
        entry: dict[str, Any] = {
            "path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "readable": False,
            "tables": {},
        }
        result.dbs[name] = entry
        if not path.exists():
            severity = "critical" if name == "preson.duckdb" else "warn"
            issue(result, severity, name, "database file is missing")
            continue

        entry["size_mb"] = round(path.stat().st_size / 1024 / 1024, 2)
        entry["mtime"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        try:
            con = connect_readonly(path)
            try:
                tables = sorted(list_tables(con))
                entry["readable"] = True
                entry["table_count"] = len(tables)
                for table in tables:
                    try:
                        entry["tables"][table] = table_summary(con, table)
                    except Exception as exc:  # noqa: BLE001 - report and continue
                        entry["tables"][table] = {"error": f"{type(exc).__name__}: {exc}"}
                        issue(result, "warn", f"{name}:{table}", "failed to summarize table")
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001 - database may be corrupt or locked
            severity = "critical" if name == "preson.duckdb" else "warn"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            issue(result, severity, name, f"cannot open read-only: {entry['error']}")


def check_preson(result: CheckResult) -> None:
    path = DATA_DIR / "preson.duckdb"
    detail: dict[str, Any] = {
        "required_tables": sorted(PRESON_REQUIRED_TABLES),
        "expected_report_period": str(expected_report_period(result.checked_at.date())),
        "tables": {},
    }
    result.preson = detail
    if not path.exists():
        return

    try:
        con = connect_readonly(path)
    except Exception:
        return

    try:
        tables = list_tables(con)
        missing = sorted(PRESON_REQUIRED_TABLES - tables)
        detail["missing_tables"] = missing
        for table in missing:
            issue(result, "critical", f"preson:{table}", "required table is missing")

        for table in sorted(PRESON_REQUIRED_TABLES & tables):
            try:
                summary = table_summary(con, table)
                detail["tables"][table] = summary
                if summary.get("rows", 0) == 0:
                    issue(result, "critical", f"preson:{table}", "required table is empty")
            except Exception as exc:  # noqa: BLE001
                detail["tables"][table] = {"error": f"{type(exc).__name__}: {exc}"}
                issue(result, "critical", f"preson:{table}", "failed to inspect required table")

        if "companies" in tables:
            row = con.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM companies").fetchone()
            detail["companies"] = {"rows": int(row[0] or 0), "tickers": int(row[1] or 0)}
            if int(row[1] or 0) < 100:
                issue(result, "warn", "preson:companies", f"company count below 100: {row[1]}")

        report_target = expected_report_period(result.checked_at.date())
        financial_status: dict[str, Any] = {}
        for table in FINANCIAL_TABLES:
            if table not in tables:
                continue
            max_date = safe_date(detail["tables"].get(table, {}).get("max_date"))
            status = "ok" if max_date and max_date >= report_target else "stale"
            financial_status[table] = {
                "latest_date": str(max_date) if max_date else None,
                "target": str(report_target),
                "status": status,
            }
            if status == "stale":
                issue(
                    result,
                    "warn",
                    f"preson:{table}",
                    f"latest report date {max_date or '-'} is older than target {report_target}",
                )
        detail["financial_report_periods"] = financial_status

        freshness: dict[str, Any] = {}
        today = result.checked_at.date()
        for table, limit_days in FRESHNESS_LIMIT_DAYS.items():
            if table not in tables:
                continue
            max_date = safe_date(detail["tables"].get(table, {}).get("max_date"))
            age_days = (today - max_date).days if max_date else None
            status = "ok" if age_days is not None and age_days <= limit_days else "stale"
            freshness[table] = {
                "latest_date": str(max_date) if max_date else None,
                "age_days": age_days,
                "limit_days": limit_days,
                "status": status,
            }
            if status == "stale":
                issue(
                    result,
                    "warn",
                    f"preson:{table}",
                    f"latest date {max_date or '-'} is older than {limit_days} days",
                )
        detail["freshness"] = freshness
    except Exception as exc:  # noqa: BLE001
        detail["error"] = f"{type(exc).__name__}: {exc}"
        issue(result, "critical", "preson", f"failed during detailed checks: {detail['error']}")
    finally:
        con.close()


def check_analytics(result: CheckResult) -> None:
    path = DATA_DIR / "analytics.duckdb"
    preson_path = DATA_DIR / "preson.duckdb"
    detail: dict[str, Any] = {"path": str(path.relative_to(ROOT)), "meta": {}}
    result.analytics = detail
    if not path.exists():
        issue(result, "warn", "analytics.duckdb", "analytics database is missing")
        return

    try:
        con = connect_readonly(path)
    except Exception as exc:  # noqa: BLE001
        issue(result, "warn", "analytics.duckdb", f"cannot open read-only: {type(exc).__name__}: {exc}")
        return

    try:
        tables = list_tables(con)
        detail["tables"] = sorted(tables)
        if "meta" not in tables:
            issue(result, "warn", "analytics:meta", "meta table is missing")
            return

        meta = {key: value for key, value in con.execute("SELECT key, value FROM meta").fetchall()}
        detail["meta"] = meta
        for key in ("year", "built_at"):
            if not meta.get(key):
                issue(result, "warn", "analytics:meta", f"meta key '{key}' is missing")

        built_at = safe_datetime(meta.get("built_at"))
        detail["built_at"] = built_at.isoformat(timespec="seconds") if built_at else None
        if preson_path.exists():
            preson_mtime = preson_path.stat().st_mtime
            analytics_mtime = path.stat().st_mtime
            src_mtime = None
            try:
                src_mtime = float(meta.get("src_mtime", ""))
            except ValueError:
                pass
            detail["preson_mtime"] = datetime.fromtimestamp(preson_mtime).isoformat(timespec="seconds")
            detail["analytics_mtime"] = datetime.fromtimestamp(analytics_mtime).isoformat(timespec="seconds")
            detail["src_mtime"] = (
                datetime.fromtimestamp(src_mtime).isoformat(timespec="seconds") if src_mtime else None
            )

            stale_by_file = analytics_mtime + 1 < preson_mtime
            stale_by_meta = src_mtime is None or src_mtime + 1 < preson_mtime
            detail["stale"] = bool(stale_by_file or stale_by_meta)
            if stale_by_file:
                issue(result, "warn", "analytics.duckdb", "file mtime is older than preson.duckdb")
            if stale_by_meta:
                issue(result, "warn", "analytics:meta", "src_mtime is missing or older than preson.duckdb")
        else:
            detail["stale"] = None
    except Exception as exc:  # noqa: BLE001
        detail["error"] = f"{type(exc).__name__}: {exc}"
        issue(result, "warn", "analytics.duckdb", f"failed during detailed checks: {detail['error']}")
    finally:
        con.close()


def collect() -> CheckResult:
    result = CheckResult(checked_at=datetime.now())
    check_database_files(result)
    check_preson(result)
    check_analytics(result)
    return result


def status_label(result: CheckResult) -> str:
    if result.critical_count:
        return "CRITICAL"
    if result.warn_count:
        return "WARN"
    return "OK"


def display(value: Any) -> Any:
    return "-" if value is None or value == "" else value


def render_console(result: CheckResult) -> str:
    lines = [
        f"DB healthcheck: {status_label(result)} "
        f"(critical={result.critical_count}, warn={result.warn_count})",
        f"Report: {REPORT_PATH.relative_to(ROOT)}",
        "",
        "Databases:",
    ]
    for name in CHECKED_DBS:
        db = result.dbs.get(name, {})
        state = "ok" if db.get("exists") and db.get("readable") else "issue"
        table_count = db.get("table_count", 0)
        size = db.get("size_mb", "-")
        lines.append(f"- {name}: {state}, tables={table_count}, size_mb={size}")

    preson = result.preson
    companies = preson.get("companies", {})
    lines += [
        "",
        "preson.duckdb:",
        f"- companies: rows={companies.get('rows', '-')}, tickers={companies.get('tickers', '-')}",
    ]
    for table in ["valuation", "prices", *FINANCIAL_TABLES]:
        summary = preson.get("tables", {}).get(table, {})
        lines.append(
            f"- {table}: rows={display(summary.get('rows'))}, "
            f"tickers={display(summary.get('tickers'))}, latest={display(summary.get('max_date'))}"
        )

    analytics = result.analytics
    meta = analytics.get("meta", {})
    lines += [
        "",
        "analytics.duckdb:",
        f"- year={meta.get('year', '-')}, built_at={meta.get('built_at', '-')}, stale={analytics.get('stale', '-')}",
    ]

    if result.issues:
        lines += ["", "Issues:"]
        for item in result.issues:
            lines.append(f"- {item.severity.upper()} {item.component}: {item.message}")
    return "\n".join(lines)


def render_markdown(result: CheckResult) -> str:
    lines = [
        "# 数据库健康检查",
        "",
        f"- 检查时间: {result.checked_at.isoformat(timespec='seconds')}",
        f"- 状态: **{status_label(result)}**",
        f"- critical: {result.critical_count}",
        f"- warn: {result.warn_count}",
        f"- 退出码规则: critical 为 1；仅 warn 仍为 0",
        "",
        "## 数据库文件",
        "",
        "| 数据库 | 存在 | 可读 | 表数 | 大小 MB | 修改时间 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name in CHECKED_DBS:
        db = result.dbs.get(name, {})
        lines.append(
        f"| `{name}` | {db.get('exists', False)} | {db.get('readable', False)} | "
            f"{db.get('table_count', 0)} | {display(db.get('size_mb'))} | {display(db.get('mtime'))} |"
        )

    lines += [
        "",
        "## preson.duckdb 核心表",
        "",
        f"- 目标最新报告期: `{result.preson.get('expected_report_period', '-')}`",
        "",
        "| 表 | 行数 | 公司数 | 最早日期 | 最新日期 |",
        "|---|---:|---:|---|---|",
    ]
    for table in ["companies", "valuation", "prices", *FINANCIAL_TABLES]:
        summary = result.preson.get("tables", {}).get(table, {})
        lines.append(
            f"| `{table}` | {display(summary.get('rows'))} | {display(summary.get('tickers'))} | "
            f"{display(summary.get('min_date'))} | {display(summary.get('max_date'))} |"
        )

    companies = result.preson.get("companies", {})
    lines += [
        "",
        f"- companies 数: `{companies.get('tickers', '-')}`",
        "",
        "### 财务表报告期",
        "",
        "| 表 | 最新日期 | 目标日期 | 状态 |",
        "|---|---|---|---|",
    ]
    for table, row in result.preson.get("financial_report_periods", {}).items():
        lines.append(f"| `{table}` | {row.get('latest_date')} | {row.get('target')} | {row.get('status')} |")

    lines += [
        "",
        "### 估值与价格新鲜度",
        "",
        "| 表 | 最新日期 | 距今天数 | 阈值天数 | 状态 |",
        "|---|---|---:|---:|---|",
    ]
    for table, row in result.preson.get("freshness", {}).items():
        lines.append(
            f"| `{table}` | {row.get('latest_date')} | {row.get('age_days')} | "
            f"{row.get('limit_days')} | {row.get('status')} |"
        )

    analytics = result.analytics
    meta = analytics.get("meta", {})
    lines += [
        "",
        "## analytics.duckdb",
        "",
        f"- 存在: `{(DATA_DIR / 'analytics.duckdb').exists()}`",
        f"- meta.year: `{display(meta.get('year'))}`",
        f"- meta.built_at: `{display(meta.get('built_at'))}`",
        f"- meta.src_mtime: `{display(analytics.get('src_mtime'))}`",
        f"- preson.duckdb mtime: `{display(analytics.get('preson_mtime'))}`",
        f"- analytics.duckdb mtime: `{display(analytics.get('analytics_mtime'))}`",
        f"- stale: `{display(analytics.get('stale'))}`",
        "",
        "## Issues",
        "",
    ]
    if not result.issues:
        lines.append("_无_")
    else:
        lines += ["| 级别 | 组件 | 问题 |", "|---|---|---|"]
        for item in result.issues:
            lines.append(f"| {item.severity} | `{item.component}` | {item.message} |")

    lines += [
        "",
        "## 表行数明细",
        "",
    ]
    for db_name in CHECKED_DBS:
        db = result.dbs.get(db_name, {})
        lines.append(f"### {db_name}")
        tables = db.get("tables") or {}
        if not tables:
            lines.append("")
            lines.append("_无可读表_")
            lines.append("")
            continue
        lines.append("")
        lines.append("| 表 | 行数 | 公司数 | 最新日期 |")
        lines.append("|---|---:|---:|---|")
        for table, summary in sorted(tables.items()):
            lines.append(
                f"| `{table}` | {display(summary.get('rows'))} | "
                f"{display(summary.get('tickers'))} | {display(summary.get('max_date'))} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    result = collect()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_markdown(result), encoding="utf-8")
    print(render_console(result))
    return 1 if result.critical_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
