"""黄金分析模块 · Phase 2.2-1:抓金/银/油价格 → gold.duckdb / gold_metrics

数据源(2026-05-07 实测可用):
- GOLD_SGE_AU99    沪金 99.99% 现货  ak.spot_hist_sge('Au99.99')   CNY/g · D
- SILVER_SGE_AG99  沪银 99.99% 现货  ak.spot_hist_sge('Ag99.99')   CNY/g · D
- OIL_WTI          WTI 原油         ak.futures_foreign_hist('CL') USD/bbl · D

派生(可选,需 macro.duckdb 的 USDCNY):
- GOLD_USD_DERIVED  沪金折美元 = SGE Au99.99(CNY/g)/ USDCNY × 31.1035(g/oz) USD/oz · D

注意:
- LBMA 原始金价(`macro_cons_gold_amount`)走 jin10.com,中国 IP SSL 频繁挂 → 不走
- 改用沪金 + USDCNY 折算,误差 < 1%(国内黄金套利充分,与 LBMA 强同步)

写入:data/gold.duckdb / gold_metrics 表(长表)

用法:
    .venv/bin/python .tools/db/fetch_gold_prices.py            # 抓所有 4 项
    .venv/bin/python .tools/db/fetch_gold_prices.py --only OIL_WTI
    .venv/bin/python .tools/db/fetch_gold_prices.py --smoke    # 离线假数据
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "db"))
from gold_schema import DB_PATH, ensure_db  # noqa: E402

MACRO_DB = ROOT / "data" / "macro.duckdb"  # 用于读 USDCNY


def _retry(fn, attempts: int = 3, sleep: float = 1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last  # type: ignore[misc]


# ───── fetcher ────────────────────────────────────────────────────────


def fetch_sge_gold() -> pd.DataFrame:
    """沪金 Au99.99 — CNY/g · 日频。"""
    import akshare as ak
    df = _retry(lambda: ak.spot_hist_sge(symbol="Au99.99"))
    out = df[["date", "close"]].rename(columns={"close": "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "GOLD_SGE_AU99"
    out["unit"] = "CNY/g"
    out["frequency"] = "D"
    out["source"] = "akshare:sge"
    return out


def fetch_sge_silver() -> pd.DataFrame:
    """沪银 Ag99.99 — CNY/g · 日频。

    AkShare `spot_hist_sge('Ag99.99')` 返回的是 CNY/kg(不是 CNY/g)。
    实测 2026-05-07 收盘 19500 ≈ 19.5 CNY/g(对照 LBMA + 国内溢价合理)。
    本函数统一除 1000 → CNY/g,与沪金口径对齐。
    """
    import akshare as ak
    df = _retry(lambda: ak.spot_hist_sge(symbol="Ag99.99"))
    out = df[["date", "close"]].rename(columns={"close": "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce") / 1000.0
    out = out.dropna()
    out["indicator"] = "SILVER_SGE_AG99"
    out["unit"] = "CNY/g"
    out["frequency"] = "D"
    out["source"] = "akshare:sge"
    return out


def fetch_oil_wti() -> pd.DataFrame:
    """WTI 原油 — USD/bbl · 日频。"""
    import akshare as ak
    df = _retry(lambda: ak.futures_foreign_hist(symbol="CL"))
    out = df[["date", "close"]].rename(columns={"close": "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "OIL_WTI"
    out["unit"] = "USD/bbl"
    out["frequency"] = "D"
    out["source"] = "akshare:futures_foreign"
    return out


def derive_gold_usd(con_gold: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """沪金折美元 = AU99 / USDCNY × 31.1035(g→oz)。

    需要 macro.duckdb 的 USDCNY + 本库的 GOLD_SGE_AU99 都已有数据。
    若任一缺失,返回空 DF(不报错)。
    """
    if not MACRO_DB.exists():
        print("   ⚠️ derive_gold_usd 跳过:macro.duckdb 不存在")
        return pd.DataFrame()

    # 读沪金
    sge = con_gold.execute(
        "SELECT date, value FROM gold_metrics "
        "WHERE indicator='GOLD_SGE_AU99' ORDER BY date"
    ).fetchdf()
    if sge.empty:
        print("   ⚠️ derive_gold_usd 跳过:GOLD_SGE_AU99 无数据(先抓沪金)")
        return pd.DataFrame()

    # 读 USDCNY
    con_macro = duckdb.connect(str(MACRO_DB), read_only=True)
    try:
        fx = con_macro.execute(
            "SELECT date, value AS usdcny FROM macro "
            "WHERE indicator='USDCNY' ORDER BY date"
        ).fetchdf()
    finally:
        con_macro.close()

    if fx.empty:
        print("   ⚠️ derive_gold_usd 跳过:macro.USDCNY 无数据")
        return pd.DataFrame()

    # date 对齐 — USDCNY 周末空,forward fill
    sge["date"] = pd.to_datetime(sge["date"])
    fx["date"] = pd.to_datetime(fx["date"])
    df = sge.merge(fx, on="date", how="left")
    df["usdcny"] = df["usdcny"].ffill()
    df = df.dropna(subset=["usdcny"])

    # 折算:CNY/g → USD/oz
    df["value_usd"] = df["value"] / df["usdcny"] * 31.1035

    out = df[["date", "value_usd"]].rename(columns={"value_usd": "value"})
    out["date"] = out["date"].dt.date
    out["indicator"] = "GOLD_USD_DERIVED"
    out["unit"] = "USD/oz"
    out["frequency"] = "D"
    out["source"] = "derived:sge*usdcny"
    return out


FETCHERS = {
    "GOLD_SGE_AU99":   fetch_sge_gold,
    "SILVER_SGE_AG99": fetch_sge_silver,
    "OIL_WTI":         fetch_oil_wti,
    # GOLD_USD_DERIVED 需要其他指标 + USDCNY,在 main 中特殊处理
}


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_data() -> dict[str, pd.DataFrame]:
    today = date.today()
    out = {}
    for ind, unit, vals in [
        ("GOLD_SGE_AU99",   "CNY/g",   [820, 825, 830]),
        ("SILVER_SGE_AG99", "CNY/g",   [9.5, 9.6, 9.7]),
        ("OIL_WTI",         "USD/bbl", [78, 80, 82]),
    ]:
        out[ind] = pd.DataFrame({
            "indicator": ind,
            "date": [today - timedelta(days=k) for k in range(len(vals))],
            "value": vals,
            "unit": unit,
            "frequency": "D",
            "source": "smoke",
        })
    return out


# ───── upsert ──────────────────────────────────────────────────────────


def upsert(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["indicator", "date", "value", "unit", "frequency", "source"]
    df = df[cols].copy()
    con.register("metrics_df", df)
    con.execute(
        "INSERT OR REPLACE INTO gold_metrics "
        "(indicator, date, value, unit, frequency, source) "
        "SELECT indicator, date, value, unit, frequency, source FROM metrics_df"
    )
    con.unregister("metrics_df")
    return len(df)


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--only",
                    help="逗号分隔(GOLD_SGE_AU99,SILVER_SGE_AG99,OIL_WTI,GOLD_USD_DERIVED)")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    targets = (
        [s.strip() for s in args.only.split(",") if s.strip()]
        if args.only else list(FETCHERS.keys()) + ["GOLD_USD_DERIVED"]
    )

    print(f"🥇 抓黄金价格 {len(targets)} 项 → {db_path}")
    if args.smoke:
        print("   (smoke 模式,不联网)")

    rows_total = 0
    failures: list[tuple[str, str]] = []
    for ind in targets:
        try:
            if args.smoke:
                df = smoke_data().get(ind, pd.DataFrame())
            elif ind == "GOLD_USD_DERIVED":
                df = derive_gold_usd(con)
            else:
                if ind not in FETCHERS:
                    failures.append((ind, "未知指标"))
                    continue
                df = FETCHERS[ind]()
            n = upsert(con, df)
            print(f"   ✅ {ind:<18} {n:>6} 行")
            rows_total += n
        except Exception as e:
            tb = traceback.format_exc().splitlines()[-1]
            failures.append((ind, f"{type(e).__name__}: {e} · {tb}"))
            print(f"   ❌ {ind:<18} {type(e).__name__}: {e}", file=sys.stderr)

    rows_db = con.execute("SELECT COUNT(*) FROM gold_metrics").fetchone()[0]
    inds_db = con.execute(
        "SELECT indicator, COUNT(*) FROM gold_metrics GROUP BY indicator ORDER BY indicator"
    ).fetchall()
    con.close()

    print(f"\n📊 写入 {rows_total} 行,gold_metrics 总计 {rows_db} 行")
    for ind, n in inds_db:
        print(f"   {ind:<18} {n:>6}")

    if failures:
        print(f"\n⚠️  {len(failures)} 项失败:")
        for ind, err in failures:
            print(f"   {ind}: {err}")
        return 1 if rows_total == 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
