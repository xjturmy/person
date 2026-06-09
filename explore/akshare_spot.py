#!/usr/bin/env python3
"""探测 akshare 的 spot 类接口:返回 shape / 列名 / 前 N 行。

固化脚本 — 内容受 git 跟踪,不接受任意代码注入。

用法:
    .venv/bin/python .tools/explore/akshare_spot.py [接口] [行数=2]

接口:
    a          A 股全市场快照(stock_zh_a_spot,新浪)
    a_em       A 股全市场快照(stock_zh_a_spot_em,东方财富)
    etf        ETF 全市场快照(fund_etf_spot_em)
    hk         港股全市场快照(stock_hk_spot_em)
    index      A 股指数列表(stock_zh_index_spot_em)
"""
import sys

INTERFACES = {
    "a": ("stock_zh_a_spot", "A 股快照(新浪)"),
    "a_em": ("stock_zh_a_spot_em", "A 股快照(东方财富)"),
    "etf": ("fund_etf_spot_em", "ETF 全市场快照"),
    "hk": ("stock_hk_spot_em", "港股快照"),
    "index": ("stock_zh_index_spot_em", "A 股指数列表"),
}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "a"
    rows = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    if key not in INTERFACES:
        print(f"未知接口: {key!r}")
        print(f"可选: {', '.join(INTERFACES)}")
        return 2

    fn_name, label = INTERFACES[key]
    import akshare as ak

    fn = getattr(ak, fn_name)
    print(f"[{key}] {label} — ak.{fn_name}()")
    df = fn()
    print(f"shape: {df.shape}")
    print(f"cols : {list(df.columns)}")
    print(df.head(rows).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
