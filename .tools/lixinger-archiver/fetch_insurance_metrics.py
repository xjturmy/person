#!/usr/bin/env python3
"""抓取保险公司专属指标(EV/NBV)并写入公司历史数据 + DuckDB。

当前已验证的理杏仁 fs/insurance 字段:
- q.m.ev.t   → 内含价值(EV)
- q.m.nbv.t  → 新业务价值(NBV)

偿付能力字段在本轮常见路径探测中未确认,暂不盲拉。
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
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

API_URL = "https://open.lixinger.com/api/cn/company/fs/insurance"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
COMPANIES_DIR = ROOT / "02_companies"
DB_PATH = ROOT / "data" / "preson.duckdb"

METRICS = {
    "内含价值(EV)": "q.m.ev.t",
    "新业务价值(NBV)": "q.m.nbv.t",
}


@dataclass(frozen=True)
class Company:
    folder: str
    ticker: str
    name: str


def _norm_ticker(raw: str) -> str:
    s = str(raw).strip()
    return s.zfill(6) if s.isdigit() else s


def read_insurance_companies(path: Path = COMPANIES_CSV) -> list[Company]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        out = []
        for r in rows:
            category = (r.get("category") or "").strip().lower()
            industry = f"{r.get('industry') or ''} {r.get('industry_l2') or ''}"
            name = (r.get("name") or "").strip()
            if category == "insurance" or "保险" in industry or "保险" in name:
                out.append(
                    Company(
                        folder=(r.get("folder") or "").strip(),
                        ticker=_norm_ticker(r.get("stock") or ""),
                        name=name,
                    )
                )
    return [c for c in out if c.folder and c.ticker and c.name]


def nested_get(obj: dict[str, Any], metric_path: str) -> Any:
    cur: Any = obj
    for k in metric_path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def post_api(payload: dict[str, Any], retries: int = 4) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            r = requests.post(API_URL, json=payload, timeout=60)
            if r.status_code == 429:
                time.sleep(min(60.0, 2.0 ** i))
                continue
            r.raise_for_status()
            j = r.json()
            if j.get("code") != 1:
                raise RuntimeError(f"API 返回错误:{j}")
            data = j.get("data") or []
            if not isinstance(data, list):
                raise RuntimeError(f"data 类型异常:{type(data)}")
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(min(60.0, 2.0 ** i))
    raise RuntimeError(f"调用理杏仁保险接口失败:{last_err}")


def fetch_company(token: str, company: Company, start: str, end: str) -> pd.DataFrame:
    payload = {
        "token": token,
        "stockCodes": [company.ticker],
        "startDate": start,
        "endDate": end,
        "metricsList": list(METRICS.values()),
    }
    rows = post_api(payload)
    records: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda x: x.get("date") or "", reverse=True):
        d = str(row.get("date") or "").split("T")[0]
        if not d:
            continue
        rec: dict[str, Any] = {"date": d}
        for label, path in METRICS.items():
            value = nested_get(row, path)
            rec[label] = float(value) if value is not None else None
        records.append(rec)
    return pd.DataFrame(records)


def write_company_csv(company: Company, df: pd.DataFrame) -> Path:
    hist = COMPANIES_DIR / company.folder / "01_基本面数据" / "历史数据"
    hist.mkdir(parents=True, exist_ok=True)
    out = hist / "保险.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    return out


def upsert_duckdb(company_frames: list[tuple[Company, pd.DataFrame]], db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS insurance_metrics (
                ticker VARCHAR NOT NULL,
                date   DATE    NOT NULL,
                metric VARCHAR NOT NULL,
                value  DOUBLE,
                PRIMARY KEY (ticker, date, metric)
            )
            """
        )
        for company, df in company_frames:
            if df.empty:
                continue
            long = df.copy()
            long["date"] = pd.to_datetime(long["date"], errors="coerce").dt.date
            long = long.dropna(subset=["date"])
            long = long.melt(id_vars=["date"], var_name="metric", value_name="value")
            long["value"] = pd.to_numeric(long["value"], errors="coerce")
            long = long.dropna(subset=["value"])
            long["ticker"] = company.ticker
            long = long[["ticker", "date", "metric", "value"]]
            con.register("insurance_df", long)
            con.execute(
                "INSERT OR REPLACE INTO insurance_metrics "
                "SELECT ticker, date, metric, value FROM insurance_df"
            )
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取保险公司 EV/NBV 指标")
    parser.add_argument("--token", help="理杏仁 token;缺省读取 .config/.lixinger_token")
    parser.add_argument("--companies-csv", default=str(COMPANIES_CSV))
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--end-date")
    parser.add_argument("--only", help="逗号分隔 ticker 或公司名")
    parser.add_argument("--no-db", action="store_true", help="只写 CSV,不写 DuckDB")
    args = parser.parse_args()

    token = resolve_lixinger_token(args.token)
    end_d = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else date.today()
    start_d = end_d - timedelta(days=365 * args.years)
    start, end = start_d.isoformat(), end_d.isoformat()

    companies = read_insurance_companies(Path(args.companies_csv))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        companies = [c for c in companies if c.ticker in wanted or c.name in wanted or c.folder in wanted]
    if not companies:
        raise SystemExit("未找到 insurance 公司")

    written: list[tuple[Company, pd.DataFrame]] = []
    for c in companies:
        df = fetch_company(token, c, start, end)
        out = write_company_csv(c, df)
        written.append((c, df))
        valid = int(df.drop(columns=["date"], errors="ignore").count().sum()) if not df.empty else 0
        print(f"✅ {c.name} {c.ticker}: {len(df)} 期 / {valid} 个值 → {out.relative_to(ROOT)}")

    if not args.no_db:
        try:
            upsert_duckdb(written)
            print(f"✅ 已写入 DuckDB: {DB_PATH.relative_to(ROOT)} / insurance_metrics")
        except duckdb.IOException as exc:
            print(f"⚠️ DuckDB 当前被前端占用,已跳过入库:{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
