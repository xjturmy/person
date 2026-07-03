"""数据校验脚本 - 检测 preson DuckDB 中各公司各表的缺口与异常。

输出:
- 控制台:汇总表(覆盖度评分 + 关键缺口)
- .temp/validate_report.md:详细报告(每家公司每张表 + 异常值列表)

用法:
    .venv/bin/python .tools/db/validate.py
    .venv/bin/python .tools/db/validate.py --target-years 10
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "preson.duckdb"
REPORT_PATH = ROOT / ".temp" / "validate_report.md"

CORE_METRICS = {
    "valuation":     ["PE-TTM", "PB", "PS-TTM", "股息率"],
    "profitability": ["净资产收益率(ROE)", "总资产收益率(ROA)", "净利润率", "毛利率(GM)"],
    "growth":        ["营业收入", "归属于母公司普通股股东的净利润", "基本每股收益"],
    "cashflow":      ["经营活动产生的现金流量净额", "自由现金流量"],
    "safety":        ["资产负债率", "流动比率", "速动比率"],
}

QUARTERLY_TABLES = {"profitability", "growth", "cashflow", "safety"}

# 不同公司类型的指标口径豁免:
# - 银行/保险不适用毛利率、流动比率、速动比率这类制造业安全性指标
# - 港股接口当前缺少部分现金流/安全性字段,按已知可得字段校验
EXEMPTIONS = {
    "毛利率(GM)": {"bank", "insurance"},
    "流动比率": {"bank", "insurance"},
    "速动比率": {"bank", "insurance", "hk"},
    "自由现金流量": {"hk"},
}

# 已知新上市 / 回 A / 港股样本的可比数据起点。
# 校验历史跨度时不再要求这些公司补到上市/可得数据之前。
DATA_START_OVERRIDES: dict[str, dict[str, date]] = {
    # 蜜雪集团:港股,现有港股估值从 2025-03 起,财务可追溯到 2021 年年报。
    "02097": {
        "valuation": date(2025, 3, 3),
        "profitability": date(2021, 12, 31),
        "growth": date(2021, 12, 31),
        "cashflow": date(2021, 12, 31),
        "safety": date(2021, 12, 31),
    },
    # A 股新上市/回 A:估值只能从 A 股上市后开始;财务上游可得起点短于 10 年。
    "600938": {  # 中国海油
        "valuation": date(2022, 4, 21),
        "profitability": date(2018, 12, 31),
        "growth": date(2018, 12, 31),
        "cashflow": date(2018, 12, 31),
        "safety": date(2018, 12, 31),
    },
    "600905": {  # 三峡能源
        "valuation": date(2021, 6, 10),
        "profitability": date(2017, 12, 31),
        "growth": date(2017, 12, 31),
        "cashflow": date(2017, 12, 31),
        "safety": date(2017, 12, 31),
    },
    "600941": {  # 中国移动
        "valuation": date(2022, 1, 5),
        "profitability": date(2018, 12, 31),
        "growth": date(2018, 12, 31),
        "cashflow": date(2018, 12, 31),
        "safety": date(2018, 12, 31),
    },
    "601728": {  # 中国电信
        "valuation": date(2021, 8, 20),
        "profitability": date(2018, 12, 31),
        "growth": date(2018, 12, 31),
        "cashflow": date(2018, 12, 31),
        "safety": date(2018, 12, 31),
    },
}

# 异常值阈值:[低, 高] 任一边超出即标记
OUTLIER_RULES = {
    ("valuation", "PE-TTM"):   (0, 500),
    ("valuation", "PB"):       (0, 50),
    ("valuation", "PS-TTM"):   (0, 100),
    ("valuation", "股息率"):    (-0.01, 0.30),
    ("profitability", "净资产收益率(ROE)"): (-1.0, 1.0),
    ("profitability", "总资产收益率(ROA)"): (-1.0, 1.0),
    ("profitability", "净利润率"):           (-2.0, 2.0),
    ("profitability", "毛利率(GM)"):         (-1.0, 1.0),
    ("safety", "资产负债率"):                (0, 1.5),
}


def expected_quarters(start: date, end: date) -> set[date]:
    """返回 [start, end] 区间内所有季报截止日 (3/31, 6/30, 9/30, 12/31)。"""
    out = set()
    for y in range(start.year, end.year + 1):
        for m, d in [(3, 31), (6, 30), (9, 30), (12, 31)]:
            qd = date(y, m, d)
            if start <= qd <= end:
                out.add(qd)
    return out


def expected_report_dates(start: date, end: date, category: str) -> set[date]:
    """按公司类型返回应检查的报告期。

    A 股常规财务表按季度检查;港股披露节奏不稳定,这里只要求年报点,
    避免把接口/披露频率差异误判为数据损坏。
    """
    if category == "hk":
        return {date(y, 12, 31) for y in range(start.year, end.year + 1) if start <= date(y, 12, 31) <= end}
    return expected_quarters(start, end)


def applicable_core_metrics(table: str, category: str) -> list[str]:
    """返回当前公司类型实际适用的核心指标。"""
    return [
        metric for metric in CORE_METRICS[table]
        if category not in EXEMPTIONS.get(metric, set())
    ]


def effective_target_start(ticker: str, table: str, target_start: date) -> date:
    """历史跨度目标起点:全局目标与公司可得数据起点取较晚者。"""
    override = DATA_START_OVERRIDES.get(str(ticker), {}).get(table)
    if override is None:
        return target_start
    return max(target_start, override)


def check_company_table(con, ticker: str, folder: str, category: str,
                        table: str, target_start: date, target_end: date) -> dict:
    """对单个 (公司, 表) 运行所有检查,返回 issue 列表。"""
    issues: list[str] = []
    applicable_metrics = applicable_core_metrics(table, category)
    df = con.execute(
        f"SELECT date, metric, value FROM {table} WHERE ticker = ?", [ticker]
    ).fetchdf()

    if df.empty:
        return {
            "ticker": ticker, "folder": folder, "table": table,
            "first_date": None, "last_date": None, "n_dates": 0,
            "n_metrics": 0, "missing_core_metrics": applicable_metrics,
            "date_span_ok": False, "missing_quarters": [], "outliers": 0,
            "score": 0, "issues": ["EMPTY"],
        }

    df["date"] = pd.to_datetime(df["date"]).dt.date
    first_date = df["date"].min()
    last_date = df["date"].max()
    n_dates = df["date"].nunique()
    metrics_present = set(df["metric"].unique())

    # 1. 核心 metric 缺失
    missing_core = []
    for m in applicable_metrics:
        if m in metrics_present:
            continue
        missing_core.append(m)
    if missing_core:
        issues.append(f"missing_metrics={missing_core}")

    # 2. 历史跨度
    effective_start = effective_target_start(str(ticker), table, target_start)
    # 跨度检查只看可比窗口长度,不因最新财报/估值滞后数周到数月而重复扣分。
    effective_end = min(target_end, last_date)
    target_days = max((effective_end - effective_start).days, 1)
    actual_days = (last_date - first_date).days
    span_ratio = actual_days / target_days if target_days else 0
    date_span_ok = span_ratio >= 0.9
    if not date_span_ok:
        issues.append(
            f"span_too_short: {first_date}~{last_date} "
            f"({actual_days}d, {span_ratio:.0%} of {target_days}d target)"
        )

    # 3. 季度缺口(仅季频表)
    missing_quarters: list[date] = []
    if table in QUARTERLY_TABLES:
        report_start = max(first_date, effective_start)
        expected = expected_report_dates(report_start, last_date, category)
        actual = set(df["date"].unique())
        missing_quarters = sorted(expected - actual)
        if missing_quarters:
            label = "missing_reports" if category == "hk" else "missing_quarters"
            issues.append(f"{label}={len(missing_quarters)}")

    # 4. 异常值
    outliers = 0
    for (tbl, metric), (lo, hi) in OUTLIER_RULES.items():
        if tbl != table:
            continue
        sub = df[df["metric"] == metric]
        if sub.empty:
            continue
        bad = sub[(sub["value"] < lo) | (sub["value"] > hi)]
        if not bad.empty:
            outliers += len(bad)
    if outliers:
        issues.append(f"outliers={outliers}")

    # 评分:满分 100
    score = 100
    if missing_core:
        score -= 30 * len(missing_core) // max(1, len(applicable_metrics))
    if not date_span_ok:
        score -= int(40 * (1 - span_ratio))
    if missing_quarters:
        score -= min(20, len(missing_quarters) * 2)
    if outliers:
        score -= min(10, outliers)
    score = max(0, score)

    return {
        "ticker": ticker, "folder": folder, "table": table,
        "first_date": first_date, "last_date": last_date, "n_dates": n_dates,
        "n_metrics": len(metrics_present),
        "missing_core_metrics": missing_core,
        "date_span_ok": date_span_ok,
        "span_ratio": round(span_ratio, 2),
        "missing_quarters": missing_quarters,
        "outliers": outliers,
        "score": score,
        "issues": issues,
    }


def render_report(rows: list[dict], target_years: int) -> str:
    """生成 markdown 报告。"""
    lines = [
        f"# preson 数据校验报告",
        "",
        f"- 生成时间: {date.today()}",
        f"- 目标历史长度: {target_years} 年",
        f"- 检查项: 核心 metric 覆盖 / 历史跨度 / 报告期缺口 / 异常值",
        f"- 口径:按公司类型校准核心指标与历史起点(港股/金融业/新上市或回 A 不套用一刀切 10 年规则)",
        "",
        "## 校验口径调整",
        "",
        "- 港股:不强制季度完整,按年报点检查;豁免当前接口不可得的自由现金流量/速动比率。",
        "- 银行/保险:豁免毛利率、流动比率、速动比率等制造业口径指标。",
        "- 新上市/回 A 公司:估值和财务历史跨度从已知可比数据起点开始计算。",
        "",
        "## 概览(评分 0-100,满分代表完整)",
        "",
        "| 公司 | valuation | profitability | growth | cashflow | safety | 平均 |",
        "|------|----------:|--------------:|-------:|---------:|-------:|-----:|",
    ]

    df = pd.DataFrame(rows)
    pivot = df.pivot(index="folder", columns="table", values="score")
    pivot = pivot.reindex(columns=["valuation", "profitability", "growth", "cashflow", "safety"])
    pivot["平均"] = pivot.mean(axis=1).round(0).astype(int)
    pivot = pivot.sort_values("平均")

    for folder, row in pivot.iterrows():
        cells = [folder] + [
            f"{int(v)}" if pd.notna(v) else "—"
            for v in row.tolist()
        ]
        lines.append("| " + " | ".join(cells) + " |")

    # 关键缺口列表(score<80)
    lines += ["", "## 关键缺口 (score < 80)", ""]
    bad = [r for r in rows if r["score"] < 80]
    if not bad:
        lines.append("_无_")
    else:
        for r in sorted(bad, key=lambda x: (x["score"], x["folder"])):
            lines.append(
                f"- **{r['folder']} / {r['table']}** (score={r['score']}): "
                + "; ".join(r["issues"])
            )

    # 历史跨度概览
    lines += ["", "## 估值表历史跨度", "", "| 公司 | first | last | 天数 | ratio |", "|------|-------|------|-----:|------:|"]
    for r in sorted([x for x in rows if x["table"] == "valuation"], key=lambda x: x["first_date"] or date(2000, 1, 1)):
        if r["first_date"] is None:
            lines.append(f"| {r['folder']} | — | — | 0 | 0 |")
        else:
            actual = (r["last_date"] - r["first_date"]).days
            lines.append(f"| {r['folder']} | {r['first_date']} | {r['last_date']} | {actual} | {r['span_ratio']:.0%} |")

    # 异常值总数
    total_outliers = sum(r["outliers"] for r in rows)
    lines += ["", f"## 异常值总数: {total_outliers}", ""]
    if total_outliers:
        lines.append("| 公司 | 表 | 异常值数 |")
        lines.append("|------|----|--------:|")
        for r in sorted([x for x in rows if x["outliers"] > 0], key=lambda x: -x["outliers"]):
            lines.append(f"| {r['folder']} | {r['table']} | {r['outliers']} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--target-years", type=int, default=10,
                        help="期望的历史年份数(默认 10)")
    parser.add_argument("--report", default=str(REPORT_PATH))
    args = parser.parse_args()

    target_end = date.today()
    target_start = target_end - timedelta(days=365 * args.target_years)

    con = duckdb.connect(args.db, read_only=True)
    companies = con.execute("SELECT ticker, folder, category FROM companies ORDER BY folder").fetchdf()

    rows: list[dict] = []
    for _, c in companies.iterrows():
        for table in ["valuation", "profitability", "growth", "cashflow", "safety"]:
            rows.append(check_company_table(
                con, c["ticker"], c["folder"], c.get("category") or "",
                table, target_start, target_end,
            ))

    # 控制台:精简版
    df = pd.DataFrame(rows)
    pivot = df.pivot(index="folder", columns="table", values="score")
    pivot = pivot.reindex(columns=["valuation", "profitability", "growth", "cashflow", "safety"])
    pivot["avg"] = pivot.mean(axis=1).round(0).astype(int)
    pivot = pivot.sort_values("avg")
    print("=== 数据完整度评分(0-100)===")
    print(pivot.to_string())

    n_critical = sum(1 for r in rows if r["score"] < 50)
    n_warn = sum(1 for r in rows if 50 <= r["score"] < 80)
    n_ok = sum(1 for r in rows if r["score"] >= 80)
    print(f"\n汇总: ok={n_ok}  warn={n_warn}  critical={n_critical}  (共 {len(rows)} 个 公司×表)")

    # 写完整报告
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(rows, args.target_years), encoding="utf-8")
    print(f"\n详细报告 → {report_path}")

    con.close()
    return 0 if n_critical == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
