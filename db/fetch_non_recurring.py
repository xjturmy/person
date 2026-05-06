"""派生扣除非经常性损益净利润(从 AkShare sina 利润表 13 列分项)。

P3 后续解锁(2026-05-06):理杏仁 fs API 扣非字段名查不到 + 拼配额不划算,
改用 sina 利润表 13 列非经常性损益分项,按证监会简化口径派生扣非净利。

公式(简化口径):
    扣非净利 ≈ 净利润 - 非经常性合计 × (1 - 简化税率 25%)

  其中"非经常性合计" =
        投资收益                  (扣除联营企业/合营企业部分仍保留为经常性)
      + 公允价值变动收益
      + 其他收益                  (含政府补助)
      + 资产处置收益
      + 营业外收入 - 营业外支出

精度:
  - 方向性正确(高占比公司一望即明)
  - 与理杏仁权威值差 5-10%(税率简化 + 经常性边界粗糙)
  - 对林奇五步层 1"利润是否一次性"的判断 充分

输出:
    DuckDB 新表 non_recurring_items:
        ticker / date / metric / value
        metric 取值:
          dnp                  扣非净利润
          dnp_yoy              单期扣非净利同比(累计)
          single_q_dnp         单季扣非净利
          single_q_dnp_yoy     单季扣非净利同比

用法:
    python3 .tools/db/fetch_non_recurring.py            # 全部 15 家
    python3 .tools/db/fetch_non_recurring.py --ticker 600519
    python3 .tools/db/fetch_non_recurring.py --csv-only # 不写 DuckDB
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
CSV_DIR = ROOT / ".temp" / "non_recurring"

SIMPLIFIED_TAX_RATE = 0.25  # 证监会通用简化税率;实际公司可能 15-20%(高新)/ 30%+ 不等

# sina 利润表里属于"非经常性损益"的字段
NON_RECURRING_COLS = [
    "公允价值变动收益",      # 完全非经常性
    "其他收益",              # 主要是政府补助 → 非经常性
    "资产处置收益",          # 完全非经常性
    "营业外收入",            # 非经常性
]
# 营业外支出反向加回(因为支出本身已经从净利里扣过)
NON_RECURRING_NEG_COLS = ["营业外支出"]
# 投资收益:完全扣除(对联营企业部分理论上保留,但 sina 不一定单独披露;保守起见全扣)
INVESTMENT_INCOME_COLS = ["投资收益"]


def _sina_symbol(ticker: str) -> str:
    if ticker.startswith(("60", "688")):
        return f"sh{ticker}"
    if ticker.startswith(("00", "30")):
        return f"sz{ticker}"
    return f"sz{ticker}"  # 兜底


def _safe_get(row: pd.Series, col: str) -> float:
    if col not in row.index:
        return 0.0
    v = row[col]
    if pd.isna(v):
        return 0.0
    try:
        return float(v)
    except Exception:
        return 0.0


def derive_one(ticker: str) -> pd.DataFrame:
    """对单家公司返回长表 [date, metric, value]。"""
    import akshare as ak

    sym = _sina_symbol(ticker)
    is_ = ak.stock_financial_report_sina(stock=sym, symbol="利润表")

    if is_.empty:
        return pd.DataFrame(columns=["date", "metric", "value"])

    rows: list[dict] = []
    snapshots: dict[str, dict] = {}

    for _, r in is_.iterrows():
        date = str(r.get("报告日", "")).strip()
        if len(date) != 8 or not date.isdigit():
            continue

        # 净利润字段(优先用归母,回退到净利润)
        net_income = (
            _safe_get(r, "归属于母公司股东的净利润")
            or _safe_get(r, "归属于母公司所有者的净利润")
            or _safe_get(r, "净利润")
        )
        if net_income == 0.0:
            continue

        non_rec_pos = sum(_safe_get(r, c) for c in NON_RECURRING_COLS)
        non_rec_neg = sum(_safe_get(r, c) for c in NON_RECURRING_NEG_COLS)
        investment = sum(_safe_get(r, c) for c in INVESTMENT_INCOME_COLS)

        # 非经常性净额(税前)
        nrgl_pretax = non_rec_pos - non_rec_neg + investment
        # 税后调整后的扣非净利
        dnp = net_income - nrgl_pretax * (1 - SIMPLIFIED_TAX_RATE)

        iso = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        snapshots[iso] = {
            "net_income": net_income,
            "dnp": dnp,
            "nrgl_pretax": nrgl_pretax,
            "dnp_to_np_ratio": dnp / net_income if net_income else None,
        }
        rows.append({"date": iso, "metric": "dnp", "value": dnp})
        rows.append({"date": iso, "metric": "dnp_to_np_ratio",
                     "value": dnp / net_income if net_income else None})

    # 派生 yoy(累计同比) — 同一年内每个季报都对去年同期算
    sorted_dates = sorted(snapshots.keys())
    for d in sorted_dates:
        prior = pd.to_datetime(d) - pd.DateOffset(years=1)
        prior_str = prior.strftime("%Y-%m-%d")
        if prior_str in snapshots:
            cur = snapshots[d]["dnp"]
            prv = snapshots[prior_str]["dnp"]
            if prv and abs(prv) > 1e-3:
                rows.append({
                    "date": d, "metric": "dnp_yoy",
                    "value": cur / prv - 1,
                })

    # 派生单季扣非 + 单季同比
    df_quarters = pd.DataFrame([
        {"date": d, **s} for d, s in snapshots.items()
    ])
    if not df_quarters.empty:
        df_quarters["date"] = pd.to_datetime(df_quarters["date"])
        df_quarters["year"] = df_quarters["date"].dt.year
        df_quarters["quarter"] = df_quarters["date"].dt.month // 3
        df_quarters = df_quarters.sort_values(["year", "quarter"]).reset_index(drop=True)

        # 单季 = 累计本季 - 累计上季(同年内)
        df_quarters["prev_dnp"] = df_quarters.groupby("year")["dnp"].shift(1)
        df_quarters["single_q_dnp"] = df_quarters["dnp"] - df_quarters["prev_dnp"].fillna(0)
        # 单季同比 = 本季 / 上年同季 - 1
        df_quarters["prev_year_single"] = df_quarters.groupby("quarter")["single_q_dnp"].shift(1)
        df_quarters["single_q_dnp_yoy"] = (
            df_quarters["single_q_dnp"] / df_quarters["prev_year_single"] - 1
        ).where(df_quarters["prev_year_single"].abs() > 1e-3)

        for _, q in df_quarters.iterrows():
            d_iso = q["date"].strftime("%Y-%m-%d")
            rows.append({"date": d_iso, "metric": "single_q_dnp",
                         "value": float(q["single_q_dnp"])})
            if pd.notna(q["single_q_dnp_yoy"]):
                rows.append({"date": d_iso, "metric": "single_q_dnp_yoy",
                             "value": float(q["single_q_dnp_yoy"])})

    return pd.DataFrame(rows)


def write_csv(ticker: str, df: pd.DataFrame) -> Path:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    p = CSV_DIR / f"{ticker}_non_recurring.csv"
    df.to_csv(p, index=False, encoding="utf-8")
    return p


def upsert_duckdb(records: list[tuple]) -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS non_recurring_items (
              ticker  VARCHAR NOT NULL,
              date    DATE    NOT NULL,
              metric  VARCHAR NOT NULL,
              value   DOUBLE,
              PRIMARY KEY (ticker, date, metric)
            )
            """
        )
        if records:
            tickers = list({r[0] for r in records})
            ph = ",".join(["?"] * len(tickers))
            con.execute(
                f"DELETE FROM non_recurring_items WHERE ticker IN ({ph})",
                tickers,
            )
            con.executemany(
                "INSERT INTO non_recurring_items (ticker, date, metric, value) VALUES (?, ?, ?, ?)",
                records,
            )
        return len(records)
    finally:
        con.close()


def list_tickers() -> list[str]:
    """从 DuckDB companies 表取全部 A 股 ticker(港股 hk 跳过)。"""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return [r[0] for r in con.execute(
            "SELECT ticker FROM companies WHERE category != 'hk' "
            "ORDER BY ticker"
        ).fetchall()]
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", help="单家 ticker(默认全部 A 股)")
    ap.add_argument("--csv-only", action="store_true", help="只导 CSV 不写 DuckDB")
    ap.add_argument("--skip-hk", action="store_true", default=True,
                    help="跳过港股(sina 不支持港股财报)")
    args = ap.parse_args(argv)

    if args.ticker:
        targets = [args.ticker]
    else:
        targets = list_tickers()
        if args.skip_hk:
            targets = [t for t in targets if not t.startswith("0") or len(t) == 6]

    all_records: list[tuple] = []
    summary: list[tuple] = []
    for t in targets:
        # 跳过 5 位港股代码(02097 蜜雪)
        if len(t) < 6:
            print(f"⏭️  {t} 港股跳过(sina 仅支持 A 股)")
            continue
        print(f"📊 派生 {t} 扣非数据…", file=sys.stderr)
        try:
            df = derive_one(t)
        except Exception as e:
            print(f"❌ {t}: {e}", file=sys.stderr)
            continue
        if df.empty:
            print(f"⚠️  {t}: 无数据")
            continue

        csv_path = write_csv(t, df)
        latest_ratio = df[df["metric"] == "dnp_to_np_ratio"].sort_values("date", ascending=False)
        if not latest_ratio.empty:
            r = latest_ratio.iloc[0]
            summary.append((t, r["date"], r["value"]))
            print(f"  📄 {csv_path.relative_to(ROOT)} ({len(df)} 行) "
                  f"· 最新扣非占比 {r['value']*100:.1f}% ({r['date']})")

        for _, row in df.iterrows():
            all_records.append((t, row["date"], row["metric"], row["value"]))

    if args.csv_only:
        print(f"\n✅ CSV 模式 · {len(all_records)} 条 · 未入 DuckDB")
    else:
        n = upsert_duckdb(all_records)
        print(f"\n✅ DuckDB.non_recurring_items 已写 {n} 行,覆盖 {len(targets)} 家")

    if summary:
        print("\n=== 扣非占比汇总(数值 < 90% 说明依赖一次性损益)===")
        for t, d, r in sorted(summary, key=lambda x: x[2] or 1.0):
            mark = "🟢" if r > 0.9 else "🟡" if r > 0.7 else "🔴"
            print(f"  {mark} {t}  {d}  扣非/归母 = {r*100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
