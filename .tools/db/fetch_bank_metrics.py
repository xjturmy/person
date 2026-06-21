"""拉取银行业派生指标(从 AkShare sina 财报衍生)。

P3 部分解锁(2026-05-05):理杏仁 fs/bank 端点 metric 字典未公开,转用
sina 财报(`stock_financial_report_sina` BS+IS+CFS 共 358 列)算 4 个银行核心指标的
**派生代理**,写入新表 `bank_metrics`(长表 ticker/date/metric/value)。

派生指标说明:
- provision_to_loans       = 减:贷款损失准备 / 发放贷款及垫款
                             (代理"拨备覆盖率",通常 3% 对应 200% 拨备覆盖)
- net_interest_to_revenue  = 净利息收入 / 营业收入
                             (反映利息业务依赖度,银行 50-70% 健康)
- net_interest_yoy         = yoy(净利息收入)
                             (代理 NIM 改善方向)
- loans_yoy                = yoy(发放贷款及垫款)
                             (规模扩张速度,过快需警惕)

仍硬阻塞(无法从公开报表派生):
- NPL 不良贷款率(sina BS 不分项披露)
- CET1 核心一级资本充足率(银保监单独披露)
- 真实拨备覆盖率(缺 NPL 分母)
- 保险公司 EV/NBV(sina/akshare 完全没,需 wind/同花顺付费)

用法:
    python3 .tools/db/fetch_bank_metrics.py            # 默认全部银行(招行)
    python3 .tools/db/fetch_bank_metrics.py --ticker 600036
    python3 .tools/db/fetch_bank_metrics.py --csv-only # 只导 CSV 不入 DuckDB
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "preson.duckdb"
CSV_DIR = ROOT / ".temp" / "bank_metrics"

# A 股银行清单(按公司清单匹配) — 当前只有招行
BANK_TICKERS = {
    "600036": "sh600036",  # 招商银行
}

# sina 数据列映射(prefix sh/sz)
def _sina_symbol(ticker: str) -> str:
    """600/601/603/605/688 → sh,000/002/300 → sz。"""
    if ticker.startswith(("60", "688")):
        return f"sh{ticker}"
    return f"sz{ticker}"


def _to_float(v) -> float | None:
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def _safe_div(num, den) -> float | None:
    n, d = _to_float(num), _to_float(den)
    if n is None or d is None or d == 0:
        return None
    return n / d


def fetch_one_bank(ticker: str) -> pd.DataFrame:
    """返回长表 [date, metric, value] (不含 ticker 列,调用方拼)。"""
    import akshare as ak

    sina_sym = _sina_symbol(ticker)
    bs = ak.stock_financial_report_sina(stock=sina_sym, symbol="资产负债表")
    is_ = ak.stock_financial_report_sina(stock=sina_sym, symbol="利润表")

    bs = bs.set_index("报告日")
    is_ = is_.set_index("报告日")
    common_dates = sorted(set(bs.index) & set(is_.index), reverse=True)

    rows: list[dict] = []

    # 按日期降序,先算各期截面指标,再单独跑 yoy
    snapshot: dict[str, dict[str, float | None]] = {}
    for d in common_dates:
        loans = bs.loc[d].get("发放贷款及垫款")
        provision = bs.loc[d].get("减:贷款损失准备")
        net_int = is_.loc[d].get("净利息收入")
        rev = is_.loc[d].get("营业收入")

        snap = {
            "loans": _to_float(loans),
            "provision": _to_float(provision),
            "net_interest_income": _to_float(net_int),
            "operating_revenue": _to_float(rev),
            "provision_to_loans": _safe_div(provision, loans),
            "net_interest_to_revenue": _safe_div(net_int, rev),
        }
        snapshot[d] = snap

    # yoy(净利息收入) / yoy(贷款) — 取同期(年度报或季度报对齐到上年同期)
    sorted_dates = sorted(snapshot.keys())
    for i, d in enumerate(sorted_dates):
        snap = snapshot[d]
        # 找 1 年前同月日(或最近的)
        target = pd.to_datetime(d) - pd.DateOffset(years=1)
        prior_str = target.strftime("%Y%m%d")
        if prior_str in snapshot:
            prior = snapshot[prior_str]
            snap["net_interest_yoy"] = (
                (snap["net_interest_income"] / prior["net_interest_income"] - 1)
                if (snap["net_interest_income"] is not None
                    and prior["net_interest_income"] not in (None, 0))
                else None
            )
            snap["loans_yoy"] = (
                (snap["loans"] / prior["loans"] - 1)
                if (snap["loans"] is not None
                    and prior["loans"] not in (None, 0))
                else None
            )

    # 转长表
    iso_date = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    derived_metrics = [
        "provision_to_loans", "net_interest_to_revenue",
        "net_interest_yoy", "loans_yoy",
        "net_interest_income", "operating_revenue", "loans",
    ]
    for d, snap in snapshot.items():
        for m in derived_metrics:
            v = snap.get(m)
            if v is not None:
                rows.append({"date": iso_date(d), "metric": m, "value": v})

    return pd.DataFrame(rows)


def write_csv(ticker: str, df: pd.DataFrame) -> Path:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    p = CSV_DIR / f"{ticker}_bank_metrics.csv"
    df.to_csv(p, index=False, encoding="utf-8")
    return p


def upsert_duckdb(records: list[tuple[str, str, str, float]]) -> int:
    """records = [(ticker, date, metric, value), ...]。返回写入行数。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_metrics (
              ticker  VARCHAR NOT NULL,
              date    DATE    NOT NULL,
              metric  VARCHAR NOT NULL,
              value   DOUBLE,
              PRIMARY KEY (ticker, date, metric)
            )
            """
        )
        # upsert: 删后插
        if records:
            tickers = list({r[0] for r in records})
            placeholders = ",".join(["?"] * len(tickers))
            con.execute(
                f"DELETE FROM bank_metrics WHERE ticker IN ({placeholders})",
                tickers,
            )
            con.executemany(
                "INSERT INTO bank_metrics (ticker, date, metric, value) VALUES (?, ?, ?, ?)",
                records,
            )
        return len(records)
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", help="单家银行 ticker(默认全部)")
    ap.add_argument("--csv-only", action="store_true", help="只导 CSV 不入 DuckDB")
    args = ap.parse_args(argv)

    targets: Iterable[str] = (
        [args.ticker] if args.ticker else list(BANK_TICKERS.keys())
    )

    all_records: list[tuple] = []
    for t in targets:
        if t not in BANK_TICKERS:
            print(f"⚠️  {t} 不在已知银行清单,跳过(扩 BANK_TICKERS 字典即可)")
            continue
        print(f"🏦 抓取 {t}…", file=sys.stderr)
        try:
            df = fetch_one_bank(t)
        except Exception as e:
            print(f"❌ {t} 抓取失败:{e}", file=sys.stderr)
            continue
        if df.empty:
            print(f"⚠️  {t} 无派生指标(数据可能不全)", file=sys.stderr)
            continue
        csv_path = write_csv(t, df)
        print(f"  📄 CSV → {csv_path.relative_to(ROOT)} ({len(df)} 行)")
        for _, row in df.iterrows():
            all_records.append((t, row["date"], row["metric"], row["value"]))

    if args.csv_only:
        print(f"✅ 仅 CSV 模式,未入 DuckDB({len(all_records)} 条)")
        return 0

    n = upsert_duckdb(all_records)
    print(f"✅ DuckDB.bank_metrics 已写入 {n} 行,覆盖 {len(targets)} 家银行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
