#!/usr/bin/env python3
"""
preson MCP Server — A股基本面投研工具

工具列表:
  query_metric           查询单一指标时间序列(带数据时效)
  valuation_percentile   返回某指标当前值在历史窗口的分位
  compare_peers          横向对比多家公司同一指标
  latest_snapshot        获取公司五维快照(估值/盈利/成长/现金流/安全性)

数据源:data/preson.duckdb (DuckDB 后端,只读)。

启动方式:
  source .venv/bin/activate
  python3 .tools/mcp/server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
import data_source as ds
from errors import MCPError, freshness_badge

mcp = FastMCP("preson-research")

ALL_TICKERS = [
    "601336", "603379", "02097", "601766", "600519",
    "000333", "002475", "002050", "002594", "000858",
    "600036", "600887", "300308", "600276", "300750",
]


def _err(e: MCPError) -> str:
    return e.to_text()


@mcp.tool()
def query_metric(ticker: str, metric: str, period: str = "3y") -> str:
    """
    查询单家公司的某项指标时间序列(带数据时效)。

    参数:
      ticker  公司代码(如 600519)或中文名(如 茅台、贵州茅台)
      metric  指标名,中英文别名都支持(详见 metric_map.yaml)
      period  时间范围:1y / 3y / 5y / 10y / 1m / 6m / all(默认 3y)

    返回:
      Markdown 表格 + 最新值 + 数据时效徽章。
      数据滞后超过 14 天会显示橙色/红色警示。
    """
    try:
        res = ds.query_metric(ticker, metric, period)
    except MCPError as e:
        return _err(e)

    rows = res["rows"]
    meta = res["meta"]
    latest = rows[0]
    lines = [
        f"## {meta['name']} ({meta['ticker']}) — {metric} ({meta['col']})",
        freshness_badge(meta),
        f"**最新值**:{latest['value']:.4f}({latest['date']})",
        f"**区间**:{rows[-1]['date']} ~ {rows[0]['date']},共 {meta['count']} 个数据点",
        "",
        "| 日期 | 值 |",
        "|------|----|",
    ]
    for r in rows[:20]:
        lines.append(f"| {r['date']} | {r['value']:.4f} |")
    if meta["count"] > 20:
        lines.append(f"| ... | (共 {meta['count']} 条,只显示最新 20 条)|")
    return "\n".join(lines)


@mcp.tool()
def valuation_percentile(ticker: str, metric: str, window: str = "all") -> str:
    """
    计算某指标当前值在历史窗口内的分位(0-100,值越大代表当前在区间内越高)。

    参数:
      ticker  公司代码或中文名
      metric  指标名(支持估值/盈利/成长/安全性等所有指标)
      window  统计窗口:1y / 3y / 5y / 10y / all(默认 all,用全部历史)

    返回:
      当前值、区间 min/max/mean/median、分位 %、样本量、数据时效。
      ⚠️ 样本量 < 60 时分位数仅供参考。
    """
    try:
        res = ds.percentile(ticker, metric, window)
    except MCPError as e:
        return _err(e)

    meta = res["meta"]
    pct = res["percentile"]
    if pct >= 80:
        verdict = "🔴 高位"
    elif pct >= 60:
        verdict = "🟠 偏高"
    elif pct >= 40:
        verdict = "🟡 居中"
    elif pct >= 20:
        verdict = "🟢 偏低"
    else:
        verdict = "🟢 低位"

    sample_warn = ""
    if res["sample_size"] < 60:
        sample_warn = f"\n⚠️ 样本仅 {res['sample_size']} 个,分位数仅供参考(window={res['window']})"

    return "\n".join([
        f"## {meta['name']} ({meta['ticker']}) — {metric} ({meta['col']}) 历史分位",
        freshness_badge(meta),
        f"**当前值**:{res['current']:.4f}  →  **{pct:.1f}% 分位** {verdict}",
        f"**窗口**:{res['window']},样本 {res['sample_size']} 个",
        "",
        "| 统计 | 值 |",
        "|------|----|",
        f"| 当前 | {res['current']:.4f} |",
        f"| 最小 | {res['min']:.4f} |",
        f"| 最大 | {res['max']:.4f} |",
        f"| 均值 | {res['mean']:.4f} |",
        f"| 中位 | {res['median']:.4f} |",
        sample_warn,
    ])


@mcp.tool()
def compare_peers(tickers: str, metric: str, period: str = "1y") -> str:
    """
    横向对比多家公司同一指标,输出最新值排行表。

    参数:
      tickers  逗号分隔的代码或中文名;"all" 表示全部 15 家
      metric   指标名
      period   时间范围(默认 1y),用于计算区间均值
    """
    try:
        ds.resolve_metric(metric)
    except MCPError as e:
        return _err(e)

    ticker_list = (
        ALL_TICKERS if tickers.strip().lower() == "all"
        else [t.strip() for t in tickers.split(",") if t.strip()]
    )

    data = ds.compare_peers(ticker_list, metric, period)
    rows_summary = []
    for label, payload in data["companies"].items():
        if "error" in payload:
            rows_summary.append((label, None, None, f"[{payload['error']}] {payload['message']}"))
            continue
        series = payload["rows"]
        if not series:
            rows_summary.append((label, None, None, "无数据"))
            continue
        latest_val = series[0]["value"]
        avg_val = sum(r["value"] for r in series) / len(series)
        rows_summary.append((label, latest_val, avg_val, None))

    rows_summary.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0))

    lines = [
        f"## 横向对比:{metric} ({data['col']})  |  区间 {period}",
        freshness_badge(data["meta"]),
        "",
        "| 排名 | 公司 | 最新值 | 区间均值 | 备注 |",
        "|------|------|--------|----------|------|",
    ]
    rank = 1
    for label, latest_val, avg_val, err in rows_summary:
        if err:
            lines.append(f"| — | {label} | — | — | {err} |")
        else:
            lines.append(f"| {rank} | {label} | {latest_val:.4f} | {avg_val:.4f} | |")
            rank += 1
    return "\n".join(lines)


@mcp.tool()
def latest_snapshot(ticker: str) -> str:
    """
    获取单家公司最新五维快照:估值 / 盈利 / 成长 / 现金流 / 安全性。
    """
    try:
        snap = ds.latest_snapshot(ticker)
    except MCPError as e:
        return _err(e)

    meta = snap["meta"]

    def fmt_section(title: str, data: dict, fmt_map: dict) -> list[str]:
        if not data:
            return [f"### {title}", "_无数据_", ""]
        out = [f"### {title}", "| 指标 | 值 |", "|------|----|"]
        for key, label in fmt_map.items():
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, float):
                if key.endswith("_pct"):
                    out.append(f"| {label} | {val:.1%} |")
                elif abs(val) < 100:
                    out.append(f"| {label} | {val:.2f} |")
                else:
                    out.append(f"| {label} | {val:,.0f} |")
            else:
                out.append(f"| {label} | {val} |")
        out.append("")
        return out

    val_map = {
        "pe_ttm": "PE-TTM", "pe_ttm_pct": "PE分位", "pb": "PB",
        "pb_pct": "PB分位", "ps_ttm": "PS-TTM", "dividend_yield": "股息率",
    }
    prof_map = {
        "roe": "ROE", "roa": "ROA",
        "gross_margin": "毛利率", "net_margin": "净利润率",
    }
    growth_map = {
        "revenue": "营业收入", "net_profit": "净利润",
        "eps": "EPS", "yoy": "同比增速",
    }
    cf_map = {
        "fcf": "自由现金流", "cfo": "经营现金流",
        "cfo_to_profit": "经营现金流/净利润",
    }
    safety_map = {
        "debt_ratio": "资产负债率", "quick_ratio": "速动比率",
        "current_ratio": "流动比率", "interest_debt": "有息负债率",
    }

    out = [
        f"# {snap['company']} ({snap['ticker']}) — 最新快照",
        freshness_badge(meta),
    ]
    if meta.get("valuation_latest") and meta.get("valuation_latest") != meta.get("latest_date"):
        out.append(f"*估值数据截至:{meta['valuation_latest']}*")
    out.append("")
    out += fmt_section("📊 估值", snap["valuation"], val_map)
    out += fmt_section("💰 盈利能力", snap["profitability"], prof_map)
    out += fmt_section("📈 成长性", snap["growth"], growth_map)
    out += fmt_section("💧 现金流", snap["cashflow"], cf_map)
    out += fmt_section("🛡️ 安全性", snap["safety"], safety_map)
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run(transport="stdio")
