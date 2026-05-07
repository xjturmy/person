"""黄金分析模块 · Phase 2.2-4:派生金油比/金银比 + 历史分位

依赖:必须先跑过 fetch_gold_prices.py(沪金/沪银/WTI 油 + 派生 USD 金价)。

派生:
- gold_oil    = GOLD_USD_DERIVED / OIL_WTI         (无单位 ratio)
- gold_silver = GOLD_SGE_AU99 / SILVER_SGE_AG99    (国内同口径,克对克)

写入:
- gold_ratios(date / gold_oil / gold_silver — 与 fetch_real_rate.py 维护的 nominal/cpi/real 三列共存)
- gold_percentiles 计算 5y / 10y 滑动分位(metric ∈ {gold_oil, gold_silver, real_rate, spdr})

用法:
    .venv/bin/python .tools/db/fetch_gold_ratios.py            # 全派生
    .venv/bin/python .tools/db/fetch_gold_ratios.py --smoke    # 离线
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "db"))
from gold_schema import DB_PATH, ensure_db  # noqa: E402

WINDOWS_DAYS = {
    "5y":  365 * 5,
    "10y": 365 * 10,
    "20y": 365 * 20,
}


# ───── 派生 gold_oil / gold_silver ──────────────────────────────────────


def derive_gold_oil(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """金油比 = GOLD_USD_DERIVED / OIL_WTI(date 内连接,周末 ffill 油价)。"""
    gold = con.execute(
        "SELECT date, value AS gold FROM gold_metrics "
        "WHERE indicator='GOLD_USD_DERIVED' ORDER BY date"
    ).fetchdf()
    oil = con.execute(
        "SELECT date, value AS oil FROM gold_metrics "
        "WHERE indicator='OIL_WTI' ORDER BY date"
    ).fetchdf()
    if gold.empty or oil.empty:
        return pd.DataFrame()

    gold["date"] = pd.to_datetime(gold["date"])
    oil["date"] = pd.to_datetime(oil["date"])

    # 用 gold 日期作为锚点,oil ffill 到 gold 日期
    gold = gold.set_index("date")
    oil = oil.set_index("date").reindex(gold.index, method="ffill")
    df = gold.join(oil).dropna()
    df["gold_oil"] = df["gold"] / df["oil"]
    df = df.reset_index()
    df["date"] = df["date"].dt.date
    return df[["date", "gold_oil"]]


def derive_gold_silver(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """金银比 = SGE_Au99(CNY/g) / SGE_Ag99(CNY/g)。"""
    gold = con.execute(
        "SELECT date, value AS gold FROM gold_metrics "
        "WHERE indicator='GOLD_SGE_AU99' ORDER BY date"
    ).fetchdf()
    silver = con.execute(
        "SELECT date, value AS silver FROM gold_metrics "
        "WHERE indicator='SILVER_SGE_AG99' ORDER BY date"
    ).fetchdf()
    if gold.empty or silver.empty:
        return pd.DataFrame()

    gold["date"] = pd.to_datetime(gold["date"])
    silver["date"] = pd.to_datetime(silver["date"])
    df = gold.merge(silver, on="date", how="inner").dropna()
    df["gold_silver"] = df["gold"] / df["silver"]
    df["date"] = df["date"].dt.date
    return df[["date", "gold_silver"]]


def upsert_ratios(con: duckdb.DuckDBPyConnection,
                  gold_oil: pd.DataFrame, gold_silver: pd.DataFrame) -> int:
    """合并两表 → upsert gold_ratios.gold_oil / gold_silver(其余列不动)。"""
    if gold_oil.empty and gold_silver.empty:
        return 0
    if gold_oil.empty:
        df = gold_silver.copy()
        df["gold_oil"] = None
    elif gold_silver.empty:
        df = gold_oil.copy()
        df["gold_silver"] = None
    else:
        df = pd.merge(gold_oil, gold_silver, on="date", how="outer")
    df = df[["date", "gold_oil", "gold_silver"]]
    con.register("ratios_df", df)
    con.execute("""
        INSERT INTO gold_ratios (date, gold_oil, gold_silver)
        SELECT date, gold_oil, gold_silver FROM ratios_df
        ON CONFLICT (date) DO UPDATE SET
            gold_oil=EXCLUDED.gold_oil,
            gold_silver=EXCLUDED.gold_silver
    """)
    con.unregister("ratios_df")
    return len(df)


# ───── 分位计算 ───────────────────────────────────────────────────────


def compute_percentile(series: pd.Series, current_value: float) -> float | None:
    """series 为历史值,返回 current_value 在历史中的分位(0-1)。"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return float((s <= current_value).sum() / len(s))


def calc_percentiles(con: duckdb.DuckDBPyConnection,
                     as_of: date | None = None) -> pd.DataFrame:
    """对 4 个核心指标算 5y/10y/20y 滑动分位。"""
    as_of = as_of or date.today()
    rows: list[dict] = []

    metrics_query = [
        ("gold_oil",    "SELECT date, gold_oil    AS value FROM gold_ratios WHERE gold_oil    IS NOT NULL"),
        ("gold_silver", "SELECT date, gold_silver AS value FROM gold_ratios WHERE gold_silver IS NOT NULL"),
        ("real_rate",   "SELECT date, real_rate   AS value FROM gold_ratios WHERE real_rate   IS NOT NULL"),
        ("spdr",        "SELECT date, value FROM gold_metrics WHERE indicator='SPDR_HOLDINGS'"),
    ]

    for metric, sql in metrics_query:
        df = con.execute(sql).fetchdf()
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        latest = df.iloc[-1]
        current_value = float(latest["value"])

        for win, win_days in WINDOWS_DAYS.items():
            cutoff = pd.Timestamp(as_of) - pd.Timedelta(days=win_days)
            window_df = df[df["date"] >= cutoff]
            if len(window_df) < 30:  # 不足 30 个观测点跳过
                continue
            pct = compute_percentile(window_df["value"], current_value)
            if pct is None:
                continue
            rows.append({
                "metric": metric,
                "window_label": win,
                "as_of": as_of,
                "value": current_value,
                "percentile": pct,
                "n_obs": int(len(window_df)),
            })

    return pd.DataFrame(rows)


def upsert_percentiles(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    con.register("pct_df", df)
    con.execute("""
        INSERT OR REPLACE INTO gold_percentiles
        (metric, window_label, as_of, value, percentile, n_obs)
        SELECT metric, window_label, as_of, value, percentile, n_obs FROM pct_df
    """)
    con.unregister("pct_df")
    return len(df)


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_fill_metrics(con: duckdb.DuckDBPyConnection) -> None:
    """smoke 模式:保证 gold_metrics 有 USD/油/沪金/沪银/SPDR 的最少数据。"""
    today = date.today()
    rows = []
    for ind, vals, unit in [
        ("GOLD_USD_DERIVED", [2700, 2710, 2720], "USD/oz"),
        ("OIL_WTI",          [78, 80, 82],       "USD/bbl"),
        ("GOLD_SGE_AU99",    [820, 825, 830],    "CNY/g"),
        ("SILVER_SGE_AG99",  [9.5, 9.6, 9.7],    "CNY/g"),
        ("SPDR_HOLDINGS",    [870, 868, 872],    "tonnes"),
    ]:
        for k, v in enumerate(vals):
            rows.append({
                "indicator": ind, "date": today - timedelta(days=k),
                "value": v, "unit": unit, "frequency": "D", "source": "smoke",
            })
    df = pd.DataFrame(rows)
    con.register("smoke_df", df)
    con.execute(
        "INSERT OR REPLACE INTO gold_metrics "
        "(indicator, date, value, unit, frequency, source) "
        "SELECT * FROM smoke_df"
    )
    con.unregister("smoke_df")


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    print(f"📊 派生金油比/金银比 + 计算分位 → {db_path}")
    if args.smoke:
        print("   (smoke 模式)")
        smoke_fill_metrics(con)

    # 1. 派生 gold_oil / gold_silver
    go = derive_gold_oil(con)
    gs = derive_gold_silver(con)
    n_ratios = upsert_ratios(con, go, gs)
    print(f"   ✅ {'gold_ratios:派生':<22} {n_ratios:>6} 行(gold_oil:{len(go)} / gold_silver:{len(gs)})")

    # 2. 计算分位
    pct_df = calc_percentiles(con)
    n_pct = upsert_percentiles(con, pct_df)
    print(f"   ✅ {'gold_percentiles':<22} {n_pct:>6} 行")
    if n_pct:
        for _, row in pct_df.iterrows():
            print(f"      {row['metric']:12s} {row['window_label']:4s} "
                  f"value={row['value']:.2f}  pct={row['percentile']:.2%}  n={row['n_obs']}")

    rows_total = n_ratios + n_pct
    rows_db_ratios = con.execute("SELECT COUNT(*) FROM gold_ratios").fetchone()[0]
    rows_db_pct = con.execute("SELECT COUNT(*) FROM gold_percentiles").fetchone()[0]
    con.close()

    print(f"\n📊 gold_ratios 总计 {rows_db_ratios} 行 / gold_percentiles 总计 {rows_db_pct} 行")
    return 0 if rows_total > 0 or args.smoke else 1


if __name__ == "__main__":
    sys.exit(main())
