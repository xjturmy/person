"""ticker 规范化单一可信源(dashboard 侧)。

口径(与 .tools/db/ingest.py 一致):
  - A 股 6 位 zero-padded 字符串(如 '000333' / '600519' / '000001')
  - 港股 5 位 zero-padded 字符串(如 '02097')
  - 非纯数字串:原样返回(防御性)
  - 空 / None:原样返回

判定港股的优先级:
  1. 显式传入 market='hk' / category='hk'
  2. 否则按长度推断:已是 5 位且首位为 '0' 视为港股保留(如 '02097');
     其他全部 zfill 到 6 位。

注意:历史上 DuckDB 写入层(.tools/db/ingest.py)已统一为此口径。
读取层(fair_price / graham / search_bar 等)以前各自维护副本,
现在全部 import 这里的 normalize_ticker。
"""

from __future__ import annotations


def normalize_ticker(symbol: str | int | None,
                     market: str | None = None) -> str:
    """规范化 ticker。

    Args:
        symbol: 原始 ticker(可能形如 '333' / '000333' / 333 / '02097' / '2097')。
        market: 可选,'hk' 表示港股(zfill 到 5 位);其它情况按长度推断。

    Returns:
        规范化后的 ticker 字符串。空输入原样返回。
    """
    if symbol is None:
        return ""
    s = str(symbol).strip()
    if not s:
        return s
    if not s.isdigit():
        return s

    # 显式港股
    if market and str(market).strip().lower() == "hk":
        return s.zfill(5)

    # 长度推断:5 位首位 '0' 当港股(02097)保留;否则全 A 股 6 位
    if len(s) == 5 and s.startswith("0"):
        return s
    return s.zfill(6)


__all__ = ["normalize_ticker"]
