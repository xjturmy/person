"""Fetch ETF decision data for dynamic price-band upgrades.

This script is intentionally additive: it does not rewrite portfolio.yaml.
It fills data/etf.duckdb with current holding ETF market data, spot/fund-flow
snapshots, technical indicators, and a first-pass price-band snapshot.

Usage:
    .venv/bin/python .tools/db/fetch_etf_decision_data.py
    .venv/bin/python .tools/db/fetch_etf_decision_data.py --years 5
    .venv/bin/python .tools/db/fetch_etf_decision_data.py --only 516020
    .venv/bin/python .tools/db/fetch_etf_decision_data.py --smoke
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "etf.duckdb"
PORTFOLIO_YAML = ROOT / ".config" / "portfolio.yaml"
LIXINGER_ENDPOINT = "https://open.lixinger.com/api/cn/fund/candlestick"

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

CREATE TABLE IF NOT EXISTS etf_instruments (
    etf_code VARCHAR PRIMARY KEY,
    etf_name VARCHAR,
    exchange VARCHAR,
    asset_class VARCHAR,
    strategy_type VARCHAR,
    theme VARCHAR,
    layer VARCHAR,
    tracking_index_code VARCHAR,
    tracking_index_name VARCHAR,
    manager VARCHAR,
    listing_date DATE,
    fee_rate DOUBLE,
    is_portfolio_current BOOLEAN,
    source VARCHAR,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS etf_spot_snapshot (
    etf_code VARCHAR NOT NULL,
    date DATE NOT NULL,
    etf_name VARCHAR,
    latest_price DOUBLE,
    iopv DOUBLE,
    premium_pct DOUBLE,
    pct_change DOUBLE,
    volume DOUBLE,
    turnover DOUBLE,
    turnover_rate DOUBLE,
    volume_ratio DOUBLE,
    main_net_inflow DOUBLE,
    main_net_inflow_pct DOUBLE,
    latest_share DOUBLE,
    float_market_cap DOUBLE,
    total_market_cap DOUBLE,
    source VARCHAR,
    updated_at TIMESTAMP,
    PRIMARY KEY (etf_code, date)
);

CREATE TABLE IF NOT EXISTS etf_technical_daily (
    etf_code VARCHAR NOT NULL,
    date DATE NOT NULL,
    ma20 DOUBLE,
    ma60 DOUBLE,
    ma120 DOUBLE,
    ma250 DOUBLE,
    price_percentile_1y DOUBLE,
    price_percentile_3y DOUBLE,
    price_percentile_5y DOUBLE,
    drawdown_250d DOUBLE,
    volatility_60d DOUBLE,
    rsi_14 DOUBLE,
    momentum_20d DOUBLE,
    momentum_60d DOUBLE,
    turnover_avg_20d DOUBLE,
    liquidity_score DOUBLE,
    source VARCHAR,
    updated_at TIMESTAMP,
    PRIMARY KEY (etf_code, date)
);

CREATE TABLE IF NOT EXISTS etf_price_band_snapshots (
    etf_code VARCHAR NOT NULL,
    as_of DATE NOT NULL,
    rule_version VARCHAR NOT NULL,
    current_price DOUBLE,
    safe_buy_upper DOUBLE,
    buy_upper DOUBLE,
    hold_upper DOUBLE,
    sell_lower DOUBLE,
    signal_score DOUBLE,
    action VARCHAR,
    confidence DOUBLE,
    reason VARCHAR,
    inputs_json VARCHAR,
    created_at TIMESTAMP,
    PRIMARY KEY (etf_code, as_of, rule_version)
);

CREATE TABLE IF NOT EXISTS etf_data_fetch_log (
    task VARCHAR,
    etf_code VARCHAR,
    fetched_at TIMESTAMP,
    ok BOOLEAN,
    row_count BIGINT,
    message VARCHAR
);
"""

ETF_CLASS_HINTS: dict[str, dict[str, str]] = {
    "510880": {"asset_class": "equity", "strategy_type": "dividend", "theme": "红利", "layer": "defensive"},
    "512890": {"asset_class": "equity", "strategy_type": "dividend", "theme": "红利低波", "layer": "defensive"},
    "512000": {"asset_class": "equity", "strategy_type": "cyclical", "theme": "券商", "layer": "offensive"},
    "516020": {"asset_class": "equity", "strategy_type": "cyclical", "theme": "化工", "layer": "offensive"},
    "512400": {"asset_class": "equity", "strategy_type": "cyclical", "theme": "有色", "layer": "offensive"},
    "515030": {"asset_class": "equity", "strategy_type": "growth", "theme": "新能源车", "layer": "offensive"},
    "562500": {"asset_class": "equity", "strategy_type": "growth", "theme": "机器人", "layer": "offensive"},
    "517520": {"asset_class": "equity", "strategy_type": "gold_stock", "theme": "黄金股", "layer": "hedge"},
    "518660": {"asset_class": "gold", "strategy_type": "gold", "theme": "黄金", "layer": "hedge"},
    "511360": {"asset_class": "bond", "strategy_type": "cash", "theme": "短融", "layer": "cash"},
}


def ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(DDL)
    finally:
        con.close()


def exchange_of(etf_code: str) -> str:
    return "SH" if etf_code.startswith(("5", "6")) else "SZ"


def resolve_lixinger_token() -> str:
    """Read token from env or .config/.lixinger_token only.

    This intentionally avoids .config/credentials.md, which is sensitive in
    this workspace's agent rules.
    """
    token = os.getenv("LIXINGER_TOKEN", "").strip()
    if token:
        return token
    token_file = os.getenv("LIXINGER_TOKEN_FILE", "").strip()
    candidates = [Path(token_file).expanduser()] if token_file else []
    candidates.append(ROOT / ".config" / ".lixinger_token")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            value = path.read_text(encoding="utf-8").splitlines()[0].strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def load_current_etfs() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(PORTFOLIO_YAML.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, Any]] = {}
    for h in raw.get("holdings") or []:
        ticker = str(h.get("ticker") or "").strip()
        if not ticker or h.get("status") != "active":
            continue
        tags = [str(x).upper() for x in (h.get("tags") or [])]
        if "ETF" not in tags and ticker not in ETF_CLASS_HINTS:
            continue
        out[ticker] = h
    return out


def retry(fn, attempts: int = 3, sleep: float = 1.2):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(sleep * (i + 1))
    if last:
        raise last
    raise RuntimeError("retry called without attempts")


def standardize_hist(df: pd.DataFrame, etf_code: str) -> pd.DataFrame:
    rename = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "turnover",
        "涨跌幅": "pct_change",
        "amount": "turnover",
    }
    df = df.rename(columns=rename).copy()
    keep = ["date", "open", "close", "high", "low", "volume", "turnover", "pct_change"]
    missing = [c for c in ["date", "open", "close", "high", "low", "volume"] if c not in df.columns]
    if missing:
        raise ValueError(f"{etf_code} missing hist columns: {missing}")
    if "turnover" not in df.columns:
        df["turnover"] = pd.NA
    if "pct_change" not in df.columns:
        df["pct_change"] = pd.NA

    df = df[keep]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    for c in ("open", "close", "high", "low", "turnover", "pct_change"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    df["pct_change"] = df["pct_change"].fillna(df["close"].pct_change() * 100)
    df.insert(0, "etf_code", etf_code)
    return df


def fetch_hist_one(etf_code: str, years: int) -> pd.DataFrame:
    import akshare as ak

    start = (date.today() - timedelta(days=365 * years)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")

    def fetch_sina() -> pd.DataFrame:
        symbol = ("sh" if exchange_of(etf_code) == "SH" else "sz") + etf_code
        return ak.fund_etf_hist_sina(symbol=symbol)

    def fetch_em() -> pd.DataFrame:
        return ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )

    try:
        df = retry(fetch_sina, attempts=2, sleep=1.0)
        df = standardize_hist(df, etf_code)
        cutoff = date.today() - timedelta(days=365 * years)
        return df[df["date"] >= cutoff].reset_index(drop=True)
    except Exception as sina_exc:
        df = retry(fetch_em, attempts=2, sleep=1.0)
        out = standardize_hist(df, etf_code)
        print(f"    ↳ sina failed, used eastmoney: {type(sina_exc).__name__}: {sina_exc}", flush=True)
        return out


def fetch_lixinger_hist_one(etf_code: str, years: int, token: str) -> pd.DataFrame:
    """Fetch ETF candlestick data from Lixinger and normalize to etf_prices."""
    if not token:
        raise RuntimeError("missing Lixinger token")

    archiver = ROOT / ".tools" / "lixinger-archiver"
    if str(archiver) not in sys.path:
        sys.path.insert(0, str(archiver))
    from fetch_lixinger_etf import (  # type: ignore
        FetchAttempt,
        _build_payload,
        _flatten_rows,
        _post_api,
        normalize_rows,
    )

    end = date.today()
    start = end - timedelta(days=365 * years)
    attempt = FetchAttempt(endpoint=LIXINGER_ENDPOINT, code_field="stockCode", include_metrics=False)
    payload = _build_payload(
        token=token,
        etf_code=etf_code,
        start=start,
        end=end,
        code_field=attempt.code_field,
        metrics=[],
        include_metrics=False,
    )
    data = _post_api(LIXINGER_ENDPOINT, payload, timeout_s=12, retries=2)
    df = normalize_rows(_flatten_rows(data), etf_code)
    if df.empty:
        raise RuntimeError("Lixinger returned no normalizable rows")
    return df


def fetch_hist_prefer_lixinger(etf_code: str, years: int, token: str, source: str) -> tuple[pd.DataFrame, str]:
    if source in {"auto", "lixinger"}:
        try:
            return fetch_lixinger_hist_one(etf_code, years, token), "lixinger"
        except Exception as exc:
            if source == "lixinger":
                raise
            print(f"    ↳ lixinger failed, fallback to akshare: {type(exc).__name__}: {exc}", flush=True)
    return fetch_hist_one(etf_code, years), "akshare"


def upsert_hist(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    con.register("hist_df", df)
    con.execute(
        """
        INSERT OR REPLACE INTO etf_prices
        SELECT etf_code, date, open, close, high, low, volume, turnover, pct_change
        FROM hist_df
        """
    )
    con.unregister("hist_df")
    return len(df)


def fetch_spot() -> pd.DataFrame:
    import akshare as ak

    df = retry(ak.fund_etf_spot_em, attempts=2, sleep=2.0)
    return df.copy() if df is not None else pd.DataFrame()


def norm_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def spot_rows(spot: pd.DataFrame, codes: set[str]) -> pd.DataFrame:
    if spot.empty or "代码" not in spot.columns:
        return pd.DataFrame()
    s = spot[spot["代码"].astype(str).isin(codes)].copy()
    if s.empty:
        return s
    today = pd.to_datetime(s.get("数据日期", date.today()), errors="coerce").dt.date
    out = pd.DataFrame({
        "etf_code": s["代码"].astype(str),
        "date": today,
        "etf_name": s.get("名称"),
        "latest_price": norm_num(s.get("最新价")),
        "iopv": norm_num(s.get("IOPV实时估值")),
        "premium_pct": norm_num(s.get("基金折价率")),
        "pct_change": norm_num(s.get("涨跌幅")),
        "volume": norm_num(s.get("成交量")),
        "turnover": norm_num(s.get("成交额")),
        "turnover_rate": norm_num(s.get("换手率")),
        "volume_ratio": norm_num(s.get("量比")),
        "main_net_inflow": norm_num(s.get("主力净流入-净额")),
        "main_net_inflow_pct": norm_num(s.get("主力净流入-净占比")),
        "latest_share": norm_num(s.get("最新份额")),
        "float_market_cap": norm_num(s.get("流通市值")),
        "total_market_cap": norm_num(s.get("总市值")),
        "source": "akshare:fund_etf_spot_em",
        "updated_at": datetime.now(),
    })
    return out.dropna(subset=["date"])


def upsert_spot(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = [
        "etf_code", "date", "etf_name", "latest_price", "iopv", "premium_pct",
        "pct_change", "volume", "turnover", "turnover_rate", "volume_ratio",
        "main_net_inflow", "main_net_inflow_pct", "latest_share",
        "float_market_cap", "total_market_cap", "source", "updated_at",
    ]
    df = df[cols].copy()
    con.register("spot_df", df)
    con.execute(f"INSERT OR REPLACE INTO etf_spot_snapshot ({', '.join(cols)}) SELECT {', '.join(cols)} FROM spot_df")
    con.unregister("spot_df")
    return len(df)


def upsert_instruments(con: duckdb.DuckDBPyConnection, holdings: dict[str, dict[str, Any]], spot: pd.DataFrame) -> int:
    rows: list[dict[str, Any]] = []
    spot_names = {}
    if not spot.empty and "代码" in spot.columns:
        spot_names = dict(zip(spot["代码"].astype(str), spot.get("名称", "")))
    for code, h in holdings.items():
        hints = ETF_CLASS_HINTS.get(code, {})
        name = spot_names.get(code) or h.get("name") or code
        rows.append({
            "etf_code": code,
            "etf_name": name,
            "exchange": exchange_of(code),
            "asset_class": hints.get("asset_class", "equity"),
            "strategy_type": hints.get("strategy_type", ""),
            "theme": hints.get("theme", ""),
            "layer": hints.get("layer", ""),
            "tracking_index_code": None,
            "tracking_index_name": None,
            "manager": None,
            "listing_date": None,
            "fee_rate": None,
            "is_portfolio_current": True,
            "source": "portfolio+akshare",
            "updated_at": datetime.now(),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    con.register("inst_df", df)
    con.execute(
        """
        INSERT INTO etf_instruments
        SELECT * FROM inst_df
        ON CONFLICT (etf_code) DO UPDATE SET
            etf_name=EXCLUDED.etf_name,
            exchange=EXCLUDED.exchange,
            asset_class=EXCLUDED.asset_class,
            strategy_type=EXCLUDED.strategy_type,
            theme=EXCLUDED.theme,
            layer=EXCLUDED.layer,
            is_portfolio_current=EXCLUDED.is_portfolio_current,
            source=EXCLUDED.source,
            updated_at=EXCLUDED.updated_at
        """
    )
    con.unregister("inst_df")
    return len(df)


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def percentile_of_last(series: pd.Series, days: int) -> float | None:
    window = series.dropna().tail(days)
    if window.empty:
        return None
    last = window.iloc[-1]
    return float((window <= last).sum() / len(window))


def compute_technical(code: str, hist: pd.DataFrame) -> dict[str, Any] | None:
    df = hist.sort_values("date").copy()
    if df.empty:
        return None
    close = pd.to_numeric(df["close"], errors="coerce")
    ret = close.pct_change()
    latest = df.iloc[-1]
    max_250 = close.tail(250).max()
    drawdown = (close.iloc[-1] / max_250 - 1) if max_250 and pd.notna(max_250) else None
    turnover = pd.to_numeric(df.get("turnover"), errors="coerce")
    return {
        "etf_code": code,
        "date": latest["date"],
        "ma20": close.rolling(20).mean().iloc[-1],
        "ma60": close.rolling(60).mean().iloc[-1],
        "ma120": close.rolling(120).mean().iloc[-1],
        "ma250": close.rolling(250).mean().iloc[-1],
        "price_percentile_1y": percentile_of_last(close, 250),
        "price_percentile_3y": percentile_of_last(close, 750),
        "price_percentile_5y": percentile_of_last(close, 1250),
        "drawdown_250d": drawdown,
        "volatility_60d": float(ret.tail(60).std() * (252 ** 0.5)) if len(ret.dropna()) >= 20 else None,
        "rsi_14": rsi(close).iloc[-1],
        "momentum_20d": float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else None,
        "momentum_60d": float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) > 61 else None,
        "turnover_avg_20d": turnover.tail(20).mean() if turnover is not None else None,
        "liquidity_score": None,
        "source": "derived:etf_prices",
        "updated_at": datetime.now(),
    }


def upsert_technical(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    df = pd.DataFrame([r for r in rows if r])
    if df.empty:
        return 0
    cols = [
        "etf_code", "date", "ma20", "ma60", "ma120", "ma250",
        "price_percentile_1y", "price_percentile_3y", "price_percentile_5y",
        "drawdown_250d", "volatility_60d", "rsi_14", "momentum_20d", "momentum_60d",
        "turnover_avg_20d", "liquidity_score", "source", "updated_at",
    ]
    df = df[cols].copy()
    con.register("tech_df", df)
    con.execute(f"INSERT OR REPLACE INTO etf_technical_daily ({', '.join(cols)}) SELECT {', '.join(cols)} FROM tech_df")
    con.unregister("tech_df")
    return len(df)


def infer_action(score: float, strategy_type: str) -> str:
    if strategy_type == "cash":
        return "cash_manage"
    if score >= 75:
        return "add"
    if score >= 55:
        return "buy_or_hold"
    if score >= 35:
        return "hold"
    return "reduce_or_wait"


def build_band_snapshot(code: str, h: dict[str, Any], tech: dict[str, Any] | None, spot_map: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    band = h.get("price_band") or {}
    latest = spot_map.get(code, {}).get("latest_price") or h.get("last_price")
    if latest is None and tech:
        latest = tech.get("close")
    if latest is None:
        return None
    hints = ETF_CLASS_HINTS.get(code, {})
    strategy = hints.get("strategy_type", "")
    price_pct = tech.get("price_percentile_3y") if tech else None
    if price_pct is None and tech:
        price_pct = tech.get("price_percentile_1y")
    score = 50.0 if price_pct is None else max(0.0, min(100.0, (1.0 - float(price_pct)) * 100))
    if strategy in {"dividend", "gold"}:
        score += 5.0
    if strategy in {"growth", "gold_stock"} and tech and (tech.get("rsi_14") or 50) > 70:
        score -= 10.0
    score = max(0.0, min(100.0, score))
    inputs = {
        "strategy_type": strategy,
        "manual_price_band": band,
        "technical": tech,
        "spot": spot_map.get(code, {}),
    }
    return {
        "etf_code": code,
        "as_of": date.today(),
        "rule_version": "v0_technical_snapshot",
        "current_price": latest,
        "safe_buy_upper": band.get("add_below"),
        "buy_upper": band.get("buy_below"),
        "hold_upper": band.get("trim_above"),
        "sell_lower": band.get("exit_above"),
        "signal_score": score,
        "action": infer_action(score, strategy),
        "confidence": 0.45 if band else 0.30,
        "reason": "第一版数据快照:理杏仁/行情源价格+技术分位+手工纪律线;指数估值/份额时序接入后提高置信度",
        "inputs_json": json.dumps(inputs, ensure_ascii=False, default=str),
        "created_at": datetime.now(),
    }


def upsert_band_snapshots(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    df = pd.DataFrame([r for r in rows if r])
    if df.empty:
        return 0
    cols = [
        "etf_code", "as_of", "rule_version", "current_price", "safe_buy_upper",
        "buy_upper", "hold_upper", "sell_lower", "signal_score", "action",
        "confidence", "reason", "inputs_json", "created_at",
    ]
    df = df[cols].copy()
    con.register("band_df", df)
    con.execute(f"INSERT OR REPLACE INTO etf_price_band_snapshots ({', '.join(cols)}) SELECT {', '.join(cols)} FROM band_df")
    con.unregister("band_df")
    return len(df)


def log(con: duckdb.DuckDBPyConnection, task: str, code: str, ok: bool, row_count: int, message: str = "") -> None:
    con.execute(
        "INSERT INTO etf_data_fetch_log VALUES (?, ?, ?, ?, ?, ?)",
        [task, code, datetime.now(), ok, row_count, message[:1000]],
    )


def smoke() -> None:
    ensure_db()
    con = duckdb.connect(str(DB_PATH))
    try:
        today = date.today()
        df = pd.DataFrame({
            "etf_code": ["510880"] * 5,
            "date": [today - timedelta(days=i) for i in range(4, -1, -1)],
            "open": [1, 1.01, 1.02, 1.01, 1.03],
            "close": [1.01, 1.02, 1.01, 1.03, 1.04],
            "high": [1.02, 1.03, 1.02, 1.04, 1.05],
            "low": [0.99, 1.0, 1.0, 1.01, 1.02],
            "volume": [1000, 1100, 1200, 1300, 1400],
            "turnover": [1000, 1111, 1222, 1333, 1444],
            "pct_change": [0, 1, -1, 2, 1],
        })
        print("smoke hist rows", upsert_hist(con, df))
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--only", help="Only one ETF code")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument(
        "--source",
        choices=["auto", "lixinger", "akshare"],
        default="auto",
        help="历史行情源: auto=理杏仁优先,失败后 AkShare/Sina 兜底",
    )
    args = ap.parse_args(argv)

    if args.smoke:
        smoke()
        return 0

    ensure_db()
    holdings = load_current_etfs()
    if args.only:
        holdings = {k: v for k, v in holdings.items() if k == args.only}
    if not holdings:
        print("No current ETF holdings found.")
        return 2

    codes = set(holdings)
    lixinger_token = resolve_lixinger_token()
    if args.source in {"auto", "lixinger"} and not lixinger_token:
        msg = "Lixinger token not found in env/.config/.lixinger_token"
        if args.source == "lixinger":
            print(msg)
            return 2
        print(f"{msg}; fallback to AkShare for historical prices")

    print(f"ETF decision data: {len(codes)} codes · years={args.years} · source={args.source}")
    spot = pd.DataFrame()
    try:
        spot = fetch_spot()
        print(f"  spot snapshot source ok: {len(spot)} rows")
    except Exception as exc:
        print(f"  spot snapshot failed: {type(exc).__name__}: {exc}")
        if args.debug:
            traceback.print_exc()

    con = duckdb.connect(str(DB_PATH))
    technical_rows: list[dict[str, Any]] = []
    band_rows: list[dict[str, Any]] = []
    try:
        n_inst = upsert_instruments(con, holdings, spot)
        n_spot = upsert_spot(con, spot_rows(spot, codes))
        print(f"  instruments={n_inst}, spot_rows={n_spot}")

        spot_norm = spot_rows(spot, codes)
        spot_map = {r["etf_code"]: r for r in spot_norm.to_dict("records")} if not spot_norm.empty else {}

        ok = fail = 0
        for code, h in holdings.items():
            try:
                hist, hist_source = fetch_hist_prefer_lixinger(
                    code,
                    years=args.years,
                    token=lixinger_token,
                    source=args.source,
                )
                n = upsert_hist(con, hist)
                tech = compute_technical(code, hist)
                if tech:
                    technical_rows.append(tech)
                snap = build_band_snapshot(code, h, tech, spot_map)
                if snap:
                    band_rows.append(snap)
                con.execute(
                    "INSERT OR REPLACE INTO etf_meta VALUES (?, ?, ?, ?)",
                    [code, h.get("name") or code, "holding_current", hist["date"].max() if not hist.empty else None],
                )
                log(con, f"hist:{hist_source}", code, True, n, "")
                print(f"  ok {code} {h.get('name', '')}: {n} hist rows · {hist_source}")
                ok += 1
            except Exception as exc:
                log(con, "hist", code, False, 0, f"{type(exc).__name__}: {exc}")
                print(f"  fail {code} {h.get('name', '')}: {type(exc).__name__}: {exc}")
                if args.debug:
                    traceback.print_exc()
                fail += 1
            time.sleep(0.25)

        n_tech = upsert_technical(con, technical_rows)
        n_band = upsert_band_snapshots(con, band_rows)
        print(f"  technical_rows={n_tech}, band_snapshots={n_band}")
        print(f"Done: ok={ok}, fail={fail}, db={DB_PATH}")
        return 0 if fail == 0 else 1
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
