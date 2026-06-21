"""A 股实时不复权价(spot)。

prices 表存的是 hfq(后复权),用于技术分析 K 线连续性;但持仓详情的「当前价」
要与「成本价」直接对照,必须用名义市价。本模块走 sina hq 单股接口
(http://hq.sinajs.cn/list=sz000333),毫秒级,LRU + 60 秒 TTL 缓存。

eastmoney spot 接口走 SSL 在本机被墙,新浪批量接口慢,故采用 sina 单股 GET。
"""
from __future__ import annotations

import re
import time

import requests

_CACHE: dict[str, tuple[float, float]] = {}  # ticker -> (price, ts)
_TTL_SEC = 60.0
_TIMEOUT = 3.0
_HEADERS = {
    "Referer": "http://finance.sina.com.cn/",
    "User-Agent": "Mozilla/5.0",
}


def _sina_symbol(ticker: str) -> str | None:
    """000333 → sz000333 / 600519 → sh600519。非 6 位数字返回 None。"""
    if not (ticker and len(ticker) == 6 and ticker.isdigit()):
        return None
    return ("sh" if ticker.startswith("6") else "sz") + ticker


def _fetch_batch(symbols: list[str]) -> dict[str, float]:
    """单次 GET 拉多只,sina 支持 list=sz000333,sh600519,..."""
    if not symbols:
        return {}
    url = "http://hq.sinajs.cn/list=" + ",".join(symbols)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        r.encoding = "gbk"
        text = r.text
    except Exception:
        return {}
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = re.match(r'var hq_str_(\w+)="([^"]*)"', line)
        if not m:
            continue
        sym, payload = m.group(1), m.group(2)
        if not payload:
            continue
        parts = payload.split(",")
        if len(parts) < 4:
            continue
        try:
            px = float(parts[3])  # 当前价
        except ValueError:
            continue
        if px > 0:
            out[sym[2:]] = px  # sz000333 → 000333
    return out


def get_spot_prices(tickers: list[str]) -> dict[str, float]:
    """返回 {ticker: 不复权 spot 价}。失败的 ticker 不出现在 dict 中。"""
    if not tickers:
        return {}
    now = time.time()
    fresh: dict[str, float] = {}
    miss: list[str] = []
    for tk in tickers:
        cached = _CACHE.get(tk)
        if cached and (now - cached[1]) < _TTL_SEC:
            fresh[tk] = cached[0]
        else:
            miss.append(tk)
    if miss:
        symbols = [s for s in (_sina_symbol(tk) for tk in miss) if s]
        if symbols:
            got = _fetch_batch(symbols)
            for tk, px in got.items():
                _CACHE[tk] = (px, now)
                fresh[tk] = px
    return fresh


def get_spot_price(ticker: str) -> float | None:
    return get_spot_prices([ticker]).get(ticker)
