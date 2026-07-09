#!/usr/bin/env python3
"""理杏仁 ETF 数据抓取器。

目标:
- 优先用理杏仁补普通 ETF 日线数据,写入 data/etf.duckdb 的 etf_prices / etf_meta。
- 理杏仁 ETF 接口尚未在项目内固化,因此脚本支持 --endpoint / --code-field / --metrics
  覆盖,同时内置常见候选请求格式用于探测。
- 输出 schema 与 .tools/db/fetch_etf.py 保持一致,Dashboard 不需要改读取逻辑。

用法:
    .venv/bin/python .tools/lixinger-archiver/fetch_lixinger_etf.py --only 512590 --years 5
    .venv/bin/python .tools/lixinger-archiver/fetch_lixinger_etf.py --only 512590 --dry-run
    .venv/bin/python .tools/lixinger-archiver/fetch_lixinger_etf.py --endpoint https://open.lixinger.com/api/cn/fund/candlestick --only 512590
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "lixinger-archiver"))

from lixinger_resolve_token import resolve_lixinger_token  # noqa: E402


DB_PATH = ROOT / "data" / "etf.duckdb"
PEERS_CSV = ROOT / ".config" / "peers_etf.csv"

DDL = """
CREATE TABLE IF NOT EXISTS etf_prices (
    etf_code   VARCHAR NOT NULL,
    date       DATE    NOT NULL,
    open       DOUBLE,
    close      DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    volume     BIGINT,
    turnover   DOUBLE,
    pct_change DOUBLE,
    PRIMARY KEY (etf_code, date)
);
CREATE INDEX IF NOT EXISTS idx_etf_date ON etf_prices(date);

CREATE TABLE IF NOT EXISTS etf_meta (
    etf_code   VARCHAR PRIMARY KEY,
    etf_name   VARCHAR,
    etf_type   VARCHAR,
    last_update DATE
);

CREATE TABLE IF NOT EXISTS etf_lixinger_fetch_log (
    etf_code    VARCHAR,
    fetched_at  TIMESTAMP,
    endpoint    VARCHAR,
    code_field  VARCHAR,
    ok          BOOLEAN,
    row_count   BIGINT,
    message     VARCHAR
);
"""

DEFAULT_ENDPOINTS = [
    "https://open.lixinger.com/api/cn/fund/candlestick",
]

DEFAULT_METRICS: list[str] = []

DATE_KEYS = ("date", "tradingDate", "tradeDate", "endDate", "navDate", "netValueDate")
CODE_KEYS = ("fundCode", "etfCode", "stockCode", "securityCode", "code", "symbol")
CLOSE_KEYS = ("close", "closePrice", "sp", "price", "nav", "unit_nav", "unitNav", "unitNetValue", "net_value", "netValue")
OPEN_KEYS = ("open", "openPrice")
HIGH_KEYS = ("high", "highPrice")
LOW_KEYS = ("low", "lowPrice")
VOLUME_KEYS = ("volume", "vol", "tradeVolume")
TURNOVER_KEYS = ("turnover", "amount", "tradeAmount", "transactionAmount")
PCT_KEYS = ("pct_change", "pctChange", "change", "changePercent", "changePct")


@dataclass(frozen=True)
class ETF:
    code: str
    name: str
    etf_type: str


@dataclass(frozen=True)
class FetchAttempt:
    endpoint: str
    code_field: str
    include_metrics: bool


def _ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(DDL)
    finally:
        con.close()


def _read_etfs(path: Path) -> list[ETF]:
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在")

    seen: set[str] = set()
    out: list[ETF] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = str(row.get("etf_code") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(
                ETF(
                    code=code,
                    name=str(row.get("etf_name") or code).strip(),
                    etf_type=str(row.get("etf_type") or "etf").strip(),
                )
            )
    return out


def _parse_csv_arg(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _date_to_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _build_payload(
    *,
    token: str,
    etf_code: str,
    start: date,
    end: date,
    code_field: str,
    metrics: list[str],
    include_metrics: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "token": token,
        "startDate": _date_to_str(start),
        "endDate": _date_to_str(end),
    }
    payload[code_field] = etf_code if code_field == "stockCode" else [etf_code]
    if include_metrics and metrics:
        payload["metricsList"] = metrics
    return payload


def _post_api(endpoint: str, payload: dict[str, Any], *, timeout_s: int, retries: int) -> Any:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            resp = requests.post(endpoint, json=payload, timeout=timeout_s)
            if resp.status_code == 429:
                time.sleep(min(60.0, 2.0 ** i))
                continue
            resp.raise_for_status()
            data = resp.json()
            code = data.get("code") if isinstance(data, dict) else None
            if code not in (None, 1):
                raise RuntimeError(f"API返回错误: {data}")
            return data.get("data") if isinstance(data, dict) else data
        except Exception as exc:
            last_err = exc
            if i < retries - 1:
                time.sleep(min(60.0, 2.0 ** i))
    raise RuntimeError(f"调用理杏仁 ETF API 失败: {last_err}")


def _short_error(exc: Exception, limit: int = 180) -> str:
    msg = str(exc).replace("\n", " ")
    if len(msg) > limit:
        msg = msg[:limit] + "..."
    return f"{type(exc).__name__}: {msg}"


def _flatten_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("items", "rows", "list", "data", "values"):
            val = data.get(key)
            if isinstance(val, list):
                rows = val
                break
        else:
            rows = [data]
    else:
        rows = []

    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    return out


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    if f is None:
        return None
    return int(f)


def _normalize_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value, errors="coerce").date()
    except Exception:
        return None


def normalize_rows(rows: list[dict[str, Any]], etf_code: str) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        row_code = str(_first(row, CODE_KEYS) or etf_code).strip()
        if row_code and row_code != etf_code:
            continue

        dt = _normalize_date(_first(row, DATE_KEYS))
        close = _to_float(_first(row, CLOSE_KEYS))
        if dt is None or close is None:
            continue

        open_ = _to_float(_first(row, OPEN_KEYS))
        high = _to_float(_first(row, HIGH_KEYS))
        low = _to_float(_first(row, LOW_KEYS))
        normalized.append(
            {
                "etf_code": etf_code,
                "date": dt,
                "open": open_ if open_ is not None else close,
                "close": close,
                "high": high if high is not None else close,
                "low": low if low is not None else close,
                "volume": _to_int(_first(row, VOLUME_KEYS)),
                "turnover": _to_float(_first(row, TURNOVER_KEYS)),
                "pct_change": _to_float(_first(row, PCT_KEYS)),
            }
        )

    df = pd.DataFrame(normalized)
    if df.empty:
        return df

    df = df.drop_duplicates(subset=["etf_code", "date"], keep="last")
    df = df.sort_values("date").reset_index(drop=True)
    if df["pct_change"].isna().all():
        df["pct_change"] = df["close"].pct_change() * 100
    return df


def _upsert(df: pd.DataFrame, etf: ETF) -> int:
    if df.empty:
        return 0
    con = duckdb.connect(str(DB_PATH))
    try:
        con.register("etf_df", df)
        con.execute(
            "INSERT OR REPLACE INTO etf_prices "
            "SELECT etf_code, date, open, close, high, low, volume, turnover, pct_change "
            "FROM etf_df"
        )
        con.execute(
            "INSERT OR REPLACE INTO etf_meta VALUES (?, ?, ?, ?)",
            [etf.code, etf.name, etf.etf_type, df["date"].max()],
        )
        return len(df)
    finally:
        con.close()


def _log(etf_code: str, attempt: FetchAttempt, ok: bool, row_count: int, message: str) -> None:
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(
            "INSERT INTO etf_lixinger_fetch_log VALUES (?, current_timestamp, ?, ?, ?, ?, ?)",
            [etf_code, attempt.endpoint, attempt.code_field, ok, row_count, message[:1000]],
        )
    finally:
        con.close()


def _attempts(args: argparse.Namespace) -> list[FetchAttempt]:
    endpoints = _parse_csv_arg(args.endpoint) or DEFAULT_ENDPOINTS
    code_fields = _parse_csv_arg(args.code_field) or ["stockCode"]
    attempts: list[FetchAttempt] = []
    for endpoint in endpoints:
        for code_field in code_fields:
            attempts.append(FetchAttempt(endpoint=endpoint, code_field=code_field, include_metrics=False))
            if args.metrics:
                attempts.append(FetchAttempt(endpoint=endpoint, code_field=code_field, include_metrics=True))
    if args.max_attempts and args.max_attempts > 0:
        return attempts[:args.max_attempts]
    return attempts


def fetch_one(
    etf: ETF,
    *,
    token: str,
    start: date,
    end: date,
    metrics: list[str],
    attempts: list[FetchAttempt],
    timeout_s: int,
    retries: int,
    debug: bool,
) -> tuple[pd.DataFrame, FetchAttempt]:
    errors: list[str] = []
    for idx, attempt in enumerate(attempts, start=1):
        payload = _build_payload(
            token=token,
            etf_code=etf.code,
            start=start,
            end=end,
            code_field=attempt.code_field,
            metrics=metrics,
            include_metrics=attempt.include_metrics,
        )
        try:
            print(
                f"    · 尝试 {idx}/{len(attempts)} "
                f"{attempt.endpoint.rsplit('/', 1)[-1]} / {attempt.code_field} "
                f"{'含metrics' if attempt.include_metrics else '无metrics'}",
                flush=True,
            )
            data = _post_api(attempt.endpoint, payload, timeout_s=timeout_s, retries=retries)
            rows = _flatten_rows(data)
            df = normalize_rows(rows, etf.code)
            if not df.empty:
                return df, attempt
            errors.append(f"{attempt.endpoint} {attempt.code_field}: 返回 {len(rows)} 行,但无法归一化")
        except Exception as exc:
            endpoint_name = attempt.endpoint.rsplit("/", 1)[-1]
            errors.append(f"{endpoint_name}/{attempt.code_field}: {_short_error(exc)}")
            if debug:
                traceback.print_exc(file=sys.stderr)

    raise RuntimeError("; ".join(errors[-3:]) if errors else "无可用请求格式")


def main() -> int:
    parser = argparse.ArgumentParser(description="用理杏仁开放 API 抓普通 ETF 数据并写入 data/etf.duckdb")
    parser.add_argument("--token", help="理杏仁 token;默认读取 LIXINGER_TOKEN / .config/.lixinger_token")
    parser.add_argument("--peers-csv", default=str(PEERS_CSV), help="ETF 清单 CSV,默认 .config/peers_etf.csv")
    parser.add_argument("--only", help="只抓单只 ETF code,如 512590")
    parser.add_argument("--years", type=int, default=2, help="历史年数,默认 2")
    parser.add_argument("--start-date", help="起始日期 YYYY-MM-DD;优先级高于 --years")
    parser.add_argument("--end-date", help="截止日期 YYYY-MM-DD;默认今天")
    parser.add_argument("--endpoint", help="逗号分隔的理杏仁 ETF API endpoint;默认 cn/fund/candlestick")
    parser.add_argument("--code-field", help="逗号分隔的代码字段;默认 stockCode")
    parser.add_argument("--metrics", help="逗号分隔 metricsList;K线接口默认不需要")
    parser.add_argument("--dry-run", action="store_true", help="只打印请求形态,不联网、不写库")
    parser.add_argument("--debug", action="store_true", help="失败时打印完整技术堆栈")
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=0, help="最多探测几组请求形态;0 表示全部")
    args = parser.parse_args()

    etfs = _read_etfs(Path(args.peers_csv))
    if args.only:
        etfs = [e for e in etfs if e.code == args.only]
        if not etfs:
            print(f"❌ {args.only} 不在 {args.peers_csv}", file=sys.stderr)
            return 2

    end = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else date.today()
    start = (
        datetime.strptime(args.start_date, "%Y-%m-%d").date()
        if args.start_date else end - timedelta(days=365 * args.years)
    )
    metrics = _parse_csv_arg(args.metrics) or DEFAULT_METRICS
    attempts = _attempts(args)

    if args.dry_run:
        sample = etfs[0] if etfs else ETF("512590", "红利低波ETF", "holding_focus")
        payload = _build_payload(
            token="<hidden>",
            etf_code=sample.code,
            start=start,
            end=end,
            code_field=attempts[0].code_field,
            metrics=metrics,
            include_metrics=attempts[0].include_metrics,
        )
        print(f"准备抓 {len(etfs)} 只 ETF · {start} → {end}")
        print(f"候选请求形态: {len(attempts)} 组")
        print(json.dumps({"endpoint": attempts[0].endpoint, "payload": payload}, ensure_ascii=False, indent=2))
        return 0

    token = resolve_lixinger_token(args.token)
    if not token.strip():
        print("❌ 缺少理杏仁 token:请传 --token 或设置 LIXINGER_TOKEN / .config/.lixinger_token", file=sys.stderr)
        return 2

    _ensure_db()
    print(f"准备用理杏仁抓 {len(etfs)} 只 ETF · {start} → {end}")
    ok, fail = 0, 0
    for etf in etfs:
        try:
            df, attempt = fetch_one(
                etf,
                token=token,
                start=start,
                end=end,
                metrics=metrics,
                attempts=attempts,
                timeout_s=args.timeout,
                retries=args.retries,
                debug=args.debug,
            )
            n = _upsert(df, etf)
            _log(etf.code, attempt, True, n, "ok")
            print(f"  ✅ {etf.code} {etf.name:18s} {n} 行 · {attempt.endpoint} · {attempt.code_field}")
            ok += 1
        except Exception as exc:
            fail += 1
            fallback_attempt = attempts[0] if attempts else FetchAttempt("", "", False)
            _log(etf.code, fallback_attempt, False, 0, str(exc))
            print(f"  ❌ {etf.code} {etf.name:18s} {type(exc).__name__}: {exc}")
        time.sleep(0.3)

    print(f"\n完成:✅ {ok} · ❌ {fail} · 库:{DB_PATH}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
