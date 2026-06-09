#!/usr/bin/env python3
"""探测某只指数的成分股 — 中证 / 上证 / 申万。

用法:
    .venv/bin/python .tools/explore/akshare_index_cons.py <来源> <指数代码> [行数=10]

来源:
    csindex    中证指数官网(如 000300、000905、000852)
    sse        上交所(如 000016、000300)
    sw         申万(如 801010)
"""
import sys

SOURCES = {
    "csindex": "index_stock_cons_csindex",
    "sse": "index_stock_cons_sina",
    "sw": "index_component_sw",
}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    source = sys.argv[1]
    symbol = sys.argv[2]
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    if source not in SOURCES:
        print(f"未知来源: {source!r}, 可选: {', '.join(SOURCES)}")
        return 2

    if not symbol.isalnum():
        print(f"指数代码只允许字母数字: {symbol!r}")
        return 2

    import akshare as ak

    fn_name = SOURCES[source]
    fn = getattr(ak, fn_name)
    print(f"[{source}] ak.{fn_name}(symbol={symbol!r})")
    df = fn(symbol=symbol)
    print(f"shape: {df.shape}")
    print(f"cols : {list(df.columns)}")
    print(df.head(rows).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
