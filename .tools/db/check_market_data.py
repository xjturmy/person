#!/usr/bin/env python3
"""Audit data readiness for the Dashboard market-judgement tab.

This is a read-only checker. It inspects data/macro.duckdb and the static
Kondratieff yaml, then writes a Markdown report explaining missing/stale inputs
for the market judgement page.

Usage:
    .venv/bin/python .tools/db/check_market_data.py
    .venv/bin/python .tools/db/check_market_data.py --json
    .venv/bin/python .tools/db/check_market_data.py --report .temp/market_data_audit.md
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[2]
MACRO_DB = ROOT / "data" / "macro.duckdb"
KONDRATIEFF_YAML = ROOT / ".tools" / "dashboard" / "data" / "kondratieff.yaml"
DEFAULT_REPORT = ROOT / ".temp" / "market_data_audit.md"

REQUIRED_INDICATORS = {
    "M2_YOY": {"label": "M2 同比", "frequency": "M", "stale_days": 180},
    "CPI_YOY": {"label": "CPI 同比", "frequency": "M", "stale_days": 180},
    "10Y_YIELD": {"label": "10Y 国债", "frequency": "D", "stale_days": 21},
    "USDCNY": {"label": "USD/CNY", "frequency": "D", "stale_days": 21},
    "A_FULL_PE": {"label": "A 股全指 PE", "frequency": "D", "stale_days": 21},
}

OPTIONAL_INDICATORS = {
    "A50_PE": "上证 50 PE",
    "HS300_PE": "沪深 300 PE",
}


@dataclass
class IndicatorStatus:
    indicator: str
    label: str
    status: str
    rows: int = 0
    non_null: int = 0
    min_date: str | None = None
    max_date: str | None = None
    latest_value: float | None = None
    latest_date: str | None = None
    n_5y: int = 0
    age_days: int | None = None
    reason: str = ""
    action: str = ""


def _safe_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _has_macro_table(con: duckdb.DuckDBPyConnection) -> bool:
    tables = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    return "macro" in tables


def _indicator_status(
    con: duckdb.DuckDBPyConnection,
    indicator: str,
    label: str,
    stale_days: int,
) -> IndicatorStatus:
    row = con.execute(
        """
        SELECT COUNT(*) AS row_count,
               COUNT(value) AS non_null,
               MIN(date) AS min_date,
               MAX(date) AS max_date
        FROM macro
        WHERE indicator = ?
        """,
        [indicator],
    ).fetchone()
    rows, non_null, min_date, max_date = row

    latest = con.execute(
        """
        SELECT date, value
        FROM macro
        WHERE indicator = ? AND value IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
        """,
        [indicator],
    ).fetchone()
    n_5y = con.execute(
        """
        SELECT COUNT(*)
        FROM macro
        WHERE indicator = ?
          AND value IS NOT NULL
          AND date >= CURRENT_DATE - INTERVAL 5 YEAR
        """,
        [indicator],
    ).fetchone()[0]

    latest_date = _safe_date(latest[0]) if latest else None
    age_days = (date.today() - latest_date).days if latest_date else None
    latest_value = float(latest[1]) if latest else None

    if non_null == 0:
        status = "missing"
        reason = "macro 表中没有该 indicator 的有效值"
        action = f"运行 .venv/bin/python .tools/db/fetch_macro.py --only {indicator}"
    elif age_days is not None and age_days > stale_days:
        status = "stale"
        reason = f"最新值距今 {age_days} 天，超过阈值 {stale_days} 天"
        action = f"重跑 .venv/bin/python .tools/db/fetch_macro.py --only {indicator}"
    else:
        status = "ok"
        reason = ""
        action = ""

    if indicator == "A_FULL_PE" and status == "missing":
        token_file = ROOT / ".config" / ".lixinger_token"
        credentials_file = ROOT / ".config" / "credentials.md"
        token_hint = []
        if not token_file.exists():
            token_hint.append(".config/.lixinger_token 不存在")
        if not credentials_file.exists():
            token_hint.append(".config/credentials.md 不存在")
        suffix = f"；{'; '.join(token_hint)}" if token_hint else "；token 文件存在但未验证内容"
        reason = "A_FULL_PE 来自理杏仁 000985 pe_ttm.mcw，抓取需要 token" + suffix
        action = "配置理杏仁 token 后运行 .venv/bin/python .tools/db/fetch_macro.py --only A_FULL_PE"

    return IndicatorStatus(
        indicator=indicator,
        label=label,
        status=status,
        rows=int(rows or 0),
        non_null=int(non_null or 0),
        min_date=str(min_date) if min_date else None,
        max_date=str(max_date) if max_date else None,
        latest_value=latest_value,
        latest_date=str(latest_date) if latest_date else None,
        n_5y=int(n_5y or 0),
        age_days=age_days,
        reason=reason,
        action=action,
    )


def collect() -> dict[str, Any]:
    result: dict[str, Any] = {
        "checked_at": date.today().isoformat(),
        "macro_db": str(MACRO_DB),
        "macro_db_exists": MACRO_DB.exists(),
        "kondratieff_yaml_exists": KONDRATIEFF_YAML.exists(),
        "indicators": {},
        "optional_indicators": {},
        "derived": {},
        "components": {},
    }

    if not MACRO_DB.exists():
        result["error"] = "data/macro.duckdb 不存在"
        return result

    con = duckdb.connect(str(MACRO_DB), read_only=True)
    try:
        if not _has_macro_table(con):
            result["error"] = "macro.duckdb 中没有 macro 表"
            return result

        for indicator, meta in REQUIRED_INDICATORS.items():
            status = _indicator_status(
                con,
                indicator,
                meta["label"],
                int(meta["stale_days"]),
            )
            result["indicators"][indicator] = asdict(status)

        for indicator, label in OPTIONAL_INDICATORS.items():
            status = _indicator_status(con, indicator, label, stale_days=21)
            result["optional_indicators"][indicator] = asdict(status)

        same_date = con.execute(
            """
            WITH pe AS (
                SELECT date, value AS pe
                FROM macro
                WHERE indicator = 'A_FULL_PE' AND value IS NOT NULL AND value > 0
            ),
            yld AS (
                SELECT date, value AS yld
                FROM macro
                WHERE indicator = '10Y_YIELD' AND value IS NOT NULL
            )
            SELECT COUNT(*) AS row_count, MIN(pe.date) AS min_date, MAX(pe.date) AS max_date
            FROM pe JOIN yld ON pe.date = yld.date
            """
        ).fetchone()
        result["derived"]["graham_diff_same_date"] = {
            "rows": int(same_date[0] or 0),
            "min_date": str(same_date[1]) if same_date[1] else None,
            "max_date": str(same_date[2]) if same_date[2] else None,
        }
    finally:
        con.close()

    ind = result["indicators"]
    has_a_full = ind["A_FULL_PE"]["status"] != "missing"
    has_10y = ind["10Y_YIELD"]["status"] != "missing"
    has_k = result["kondratieff_yaml_exists"]
    graham_rows = result["derived"]["graham_diff_same_date"]["rows"]

    result["components"] = {
        "banner": {
            "status": "ok" if has_k and has_a_full and has_10y else "partial",
            "requires": ["kondratieff.yaml", "A_FULL_PE", "10Y_YIELD"],
            "impact": "缺 A_FULL_PE 时，股债收益差和 A 股全指 PE 5y 分位显示数据缺，仅康波信号有效。",
        },
        "kondratieff_card": {
            "status": "ok" if has_k else "missing",
            "requires": ["kondratieff.yaml"],
            "impact": "缺失时康波周期定位卡降级为空提示。",
        },
        "graham_index": {
            "status": "ok" if has_a_full and has_10y else "missing",
            "requires": ["A_FULL_PE", "10Y_YIELD"],
            "impact": "缺任一指标时整段显示 A_FULL_PE 或 10Y_YIELD 缺数据。",
        },
        "graham_trend": {
            "status": "ok" if graham_rows > 0 else "missing",
            "requires": ["A_FULL_PE and 10Y_YIELD same-date rows"],
            "impact": "同日样本为 0 时，股债差历史时序图为空。",
        },
        "thermometer": {
            "status": "ok" if all(v["status"] != "missing" for v in ind.values()) else "partial",
            "requires": list(REQUIRED_INDICATORS),
            "impact": "缺失指标会在温度计中显示为 — / 无数据。",
        },
        "a_full_pe_band": {
            "status": "ok" if ind["A_FULL_PE"]["non_null"] >= 30 else "missing",
            "requires": ["A_FULL_PE >= 30 rows"],
            "impact": "A_FULL_PE 样本不足时，估值分位带不渲染。",
        },
    }
    return result


def _status_emoji(status: str) -> str:
    return {"ok": "✅", "partial": "🟡", "stale": "🟠", "missing": "❌"}.get(status, "⚪")


def render_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# 市场研判数据缺失检查\n")
    lines.append(f"> 检查日期：{data.get('checked_at')} · 脚本：`.tools/db/check_market_data.py`\n")
    lines.append("## 总览\n")
    lines.append(f"- macro 库：`{data.get('macro_db')}`")
    lines.append(f"- macro 库存在：{data.get('macro_db_exists')}")
    lines.append(f"- 康波 yaml 存在：{data.get('kondratieff_yaml_exists')}")
    if data.get("error"):
        lines.append(f"- 错误：{data['error']}")
        return "\n".join(lines) + "\n"

    lines.append("\n## 页面组件状态\n")
    lines.append("| 组件 | 状态 | 依赖 | 影响 |")
    lines.append("|---|---:|---|---|")
    for name, comp in data["components"].items():
        lines.append(
            f"| `{name}` | {_status_emoji(comp['status'])} {comp['status']} | "
            f"{', '.join(comp['requires'])} | {comp['impact']} |"
        )

    lines.append("\n## 核心指标覆盖\n")
    lines.append("| indicator | 名称 | 状态 | 行数 | 最新日期 | 最新值 | 5y样本 | 原因 | 建议动作 |")
    lines.append("|---|---|---:|---:|---|---:|---:|---|---|")
    for indicator in REQUIRED_INDICATORS:
        row = data["indicators"][indicator]
        latest = "" if row["latest_value"] is None else f"{row['latest_value']:.4g}"
        lines.append(
            f"| `{indicator}` | {row['label']} | {_status_emoji(row['status'])} {row['status']} | "
            f"{row['non_null']} | {row['latest_date'] or '-'} | {latest or '-'} | {row['n_5y']} | "
            f"{row['reason'] or '-'} | {row['action'] or '-'} |"
        )

    lines.append("\n## 派生信号\n")
    g = data["derived"]["graham_diff_same_date"]
    lines.append(
        f"- 股债差历史同日样本：{g['rows']} 行"
        f"（{g['min_date'] or '-'} → {g['max_date'] or '-'}）。"
    )
    if g["rows"] == 0:
        lines.append("- 原因：`A_FULL_PE` 缺失时无法与 `10Y_YIELD` 做同日 join。")

    lines.append("\n## 可用但未替代的近似指标\n")
    lines.append("| indicator | 名称 | 状态 | 最新日期 | 最新值 | 备注 |")
    lines.append("|---|---|---:|---|---:|---|")
    for indicator in OPTIONAL_INDICATORS:
        row = data["optional_indicators"][indicator]
        latest = "" if row["latest_value"] is None else f"{row['latest_value']:.4g}"
        lines.append(
            f"| `{indicator}` | {row['label']} | {_status_emoji(row['status'])} {row['status']} | "
            f"{row['latest_date'] or '-'} | {latest or '-'} | 可作显式标注的代理参考，但不能冒充 A 股全指 PE。 |"
        )

    lines.append("\n## 结论\n")
    a_full = data["indicators"]["A_FULL_PE"]
    if a_full["status"] == "missing":
        lines.append(
            "- 最大缺口：`A_FULL_PE` 完全缺失，导致 banner、格雷厄姆指数、A 股全指 PE 分位带、温度计第五项降级。"
        )
        lines.append(f"- 根因判断：{a_full['reason']}")
        lines.append(f"- 修复入口：{a_full['action']}")
    stale = [v for v in data["indicators"].values() if v["status"] == "stale"]
    if stale:
        names = "、".join(f"`{v['indicator']}`({v['latest_date']})" for v in stale)
        lines.append(f"- 过期指标：{names}。建议先重跑对应 `fetch_macro.py --only ...`，若仍不前进则归为上游源滞后。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Markdown 报告输出路径")
    parser.add_argument("--json", action="store_true", help="同时打印 JSON 到 stdout")
    args = parser.parse_args()

    data = collect()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(data), encoding="utf-8")

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"wrote {report_path}")
        if data.get("error"):
            print(f"error: {data['error']}")
        else:
            missing = [
                k for k, v in data["indicators"].items()
                if v["status"] == "missing"
            ]
            stale = [
                k for k, v in data["indicators"].items()
                if v["status"] == "stale"
            ]
            print(f"missing={missing or []} stale={stale or []}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
