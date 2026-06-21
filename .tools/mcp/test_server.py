#!/usr/bin/env python3
"""
MCP server 本地调试脚本(不需要 Claude,直接测试工具函数)。

用法:
  source .venv/bin/activate
  python3 .tools/mcp/test_server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from server import (
    query_metric,
    valuation_percentile,
    compare_peers,
    latest_snapshot,
)

SEP = "─" * 60


def run(label, fn, *args, **kwargs):
    print(f"\n{SEP}\n▶ {label}\n{SEP}")
    print(fn(*args, **kwargs))


if __name__ == "__main__":
    # —— 基础查询 ——
    run("query_metric: 茅台 PE-TTM 1y", query_metric, "茅台", "pe_ttm", "1y")
    run("query_metric: 宁德时代 ROE 3y", query_metric, "300750", "ROE", "3y")
    run("query_metric: 招商银行 资产负债率 5y", query_metric, "600036", "资产负债率", "5y")

    # —— 新工具:分位 ——
    run("valuation_percentile: 茅台 PE-TTM all", valuation_percentile, "茅台", "pe_ttm", "all")
    run("valuation_percentile: 茅台 PB all", valuation_percentile, "茅台", "pb", "all")
    run("valuation_percentile: 招行 PB 3y", valuation_percentile, "招行", "pb", "3y")

    # —— 错误路径:验证统一格式 ——
    run("ERR: 公司不存在", query_metric, "不存在的公司", "pe_ttm", "1y")
    run("ERR: 指标不存在", query_metric, "茅台", "不存在的指标", "1y")
    run("ERR: 无数据(无效 period)", query_metric, "茅台", "pe_ttm", "garbage")
    run("ERR: 分位 - 公司不存在", valuation_percentile, "XXXXXX", "pe_ttm", "all")

    # —— 横向对比 ——
    run(
        "compare_peers: PE-TTM (茅台/五粮液/宁德/恒瑞/招行)",
        compare_peers,
        "600519,000858,300750,600276,600036",
        "pe_ttm",
        "1y",
    )

    # —— 五维快照 ——
    run("latest_snapshot: 贵州茅台", latest_snapshot, "600519")
    run("latest_snapshot: 招商银行", latest_snapshot, "600036")

    print(f"\n{SEP}\n✅ 全部测试完成\n{SEP}")
