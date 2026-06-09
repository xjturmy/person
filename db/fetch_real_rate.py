"""黄金分析模块 · Phase 2.2-2:抓美国 10Y 名义利率 + CPI → 派生实际利率

数据源(2026-05-14 更新 · FRED 兜底):
- US_10Y_NOMINAL  美国 10 年期国债收益率  ak.bond_zh_us_rate(`美国国债收益率10年`)% · D
- US_CPI_MOM      美国 CPI 月环比          首选 ak.macro_usa_cpi_monthly(jin10 易挂)
                                          兜底 FRED CPIAUCSL(指数水平派生 MoM)% · M

派生:
- US_CPI_LEVEL    CPI 水平指数(从 MoM 累计) (无单位)
- US_CPI_YOY      CPI 同比 = level.pct_change(12)                   % · M
- US_REAL_RATE    实际利率 = US_10Y_NOMINAL - US_CPI_YOY(MoM ffill 到日)% · D

写入:
- gold_metrics(US_10Y_NOMINAL / US_CPI_MOM / US_CPI_YOY / US_REAL_RATE)
- gold_ratios(date / real_rate / nominal_10y / cpi_yoy 三列联动)

用法:
    .venv/bin/python .tools/db/fetch_real_rate.py            # 全抓
    .venv/bin/python .tools/db/fetch_real_rate.py --smoke    # 离线
"""
from __future__ import annotations

import argparse
import io
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

FRED_CPI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"


def _retry(fn, attempts: int = 3, sleep: float = 1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last  # type: ignore[misc]


def fetch_us_10y() -> pd.DataFrame:
    """美国 10Y 名义利率(% · 日)。"""
    import akshare as ak
    df = _retry(lambda: ak.bond_zh_us_rate(), attempts=2, sleep=2.0)
    col = "美国国债收益率10年"
    if col not in df.columns:
        raise RuntimeError(f"列 {col} 不在 bond_zh_us_rate 输出:{df.columns.tolist()}")
    out = df[["日期", col]].rename(columns={"日期": "date", col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "US_10Y_NOMINAL"
    out["unit"] = "%"
    out["frequency"] = "D"
    out["source"] = "akshare:bond_zh_us"
    return out


def _parse_fred_cpi_csv(text: str) -> pd.DataFrame:
    """解析 FRED CPIAUCSL CSV → (date, level) 两列 DataFrame。

    FRED 公开 CSV 格式:
        observation_date,CPIAUCSL
        1947-01-01,21.48
        ...
    历史上也曾用 `DATE` 列名,兼容两者。"""
    df = pd.read_csv(io.StringIO(text))
    # 兼容旧列名 DATE / 新列名 observation_date
    date_col = next((c for c in df.columns if c.lower() in ("date", "observation_date")), None)
    if date_col is None or "CPIAUCSL" not in df.columns:
        raise RuntimeError(f"FRED CSV 列异常:{df.columns.tolist()}")
    df = df.rename(columns={date_col: "date", "CPIAUCSL": "level"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["level"] = pd.to_numeric(df["level"], errors="coerce")
    df = df.dropna().sort_values("date").reset_index(drop=True)
    return df


def fetch_us_cpi_mom_fred() -> pd.DataFrame:
    """FRED 兜底:拉 CPIAUCSL 指数水平 → 派生月环比 %。

    公式:mom_pct[t] = (level[t] / level[t-1] - 1) * 100
    与 BLS/jin10 发布的 CPI MoM 同口径(SA · seasonally adjusted)。
    """
    import requests
    def _pull():
        resp = requests.get(FRED_CPI_URL, timeout=10)
        resp.raise_for_status()
        return resp.text
    text = _retry(_pull, attempts=3, sleep=1.5)
    raw = _parse_fred_cpi_csv(text)
    if len(raw) < 2:
        raise RuntimeError(f"FRED CPIAUCSL 返回 {len(raw)} 行,无法派生 MoM")
    raw["value"] = (raw["level"] / raw["level"].shift(1) - 1) * 100
    out = raw[["date", "value"]].dropna().reset_index(drop=True)
    out["indicator"] = "US_CPI_MOM"
    out["unit"] = "%"
    out["frequency"] = "M"
    out["source"] = "FRED:CPIAUCSL"
    return out


def fetch_us_cpi_mom() -> pd.DataFrame:
    """美国 CPI 月环比(% · 月)。

    主路径:akshare.macro_usa_cpi_monthly(底层 jin10.com,SSL 偶发 EOF)
    兜底:  FRED CPIAUCSL 指数水平派生(St. Louis Fed 公开免费,最稳)
    """
    # 1) 主路径:akshare
    try:
        import akshare as ak
        df = _retry(ak.macro_usa_cpi_monthly)
        out = df[["日期", "今值"]].rename(columns={"日期": "date", "今值": "value"})
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
        out["value"] = pd.to_numeric(out["value"], errors="coerce")
        out = out.dropna().sort_values("date").reset_index(drop=True)
        if out.empty:
            raise RuntimeError("akshare 返回空 DataFrame")
        # 新鲜度检查:akshare 末日落后今天 > 60 天视为"实质失败",切 FRED
        # (jin10 经常返回完整历史但缺最近月份,不抛错却数据过期)
        latest_ak = out["date"].iloc[-1]
        days_behind = (date.today() - latest_ak).days
        if days_behind > 60:
            raise RuntimeError(
                f"akshare 数据末日 {latest_ak} 落后今天 {days_behind} 天(>60),切 FRED"
            )
        out["indicator"] = "US_CPI_MOM"
        out["unit"] = "%"
        out["frequency"] = "M"
        out["source"] = "akshare:macro_usa"
        return out
    except Exception as e_ak:
        print(
            f"   ⚠️ akshare.macro_usa_cpi_monthly 失败({type(e_ak).__name__}),切 FRED 兜底",
            file=sys.stderr,
        )
        # 2) 兜底:FRED
        return fetch_us_cpi_mom_fred()


def derive_cpi_yoy(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """从 US_CPI_MOM 累计出 CPI 水平,再算 YoY。

    公式:
      cpi_level_t = ∏(1 + mom_i/100) for i ≤ t
      cpi_yoy_t   = cpi_level_t / cpi_level_{t-12} - 1
    """
    mom = con.execute(
        "SELECT date, value FROM gold_metrics "
        "WHERE indicator='US_CPI_MOM' ORDER BY date"
    ).fetchdf()
    if len(mom) < 13:
        print(f"   ⚠️ derive_cpi_yoy 跳过:US_CPI_MOM 只有 {len(mom)} 行(需 ≥ 13)")
        return pd.DataFrame()

    mom["date"] = pd.to_datetime(mom["date"])
    mom = mom.sort_values("date").reset_index(drop=True)
    mom["cpi_level"] = (1 + mom["value"] / 100).cumprod() * 100
    mom["cpi_yoy"] = mom["cpi_level"].pct_change(12) * 100
    out = mom[["date", "cpi_yoy"]].dropna().rename(columns={"cpi_yoy": "value"})
    out["date"] = out["date"].dt.date
    out["indicator"] = "US_CPI_YOY"
    out["unit"] = "%"
    out["frequency"] = "M"
    out["source"] = "derived:cpi_mom_cumulative"
    return out


def derive_real_rate(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """实际利率 = US_10Y_NOMINAL - US_CPI_YOY(月→日 ffill)。"""
    nominal = con.execute(
        "SELECT date, value AS nominal FROM gold_metrics "
        "WHERE indicator='US_10Y_NOMINAL' ORDER BY date"
    ).fetchdf()
    cpi = con.execute(
        "SELECT date, value AS cpi_yoy FROM gold_metrics "
        "WHERE indicator='US_CPI_YOY' ORDER BY date"
    ).fetchdf()

    if nominal.empty or cpi.empty:
        print("   ⚠️ derive_real_rate 跳过:nominal 或 cpi_yoy 缺失")
        return pd.DataFrame()

    nominal["date"] = pd.to_datetime(nominal["date"])
    cpi["date"] = pd.to_datetime(cpi["date"])

    # 月频 CPI 扩展到日频 ffill
    daily_dates = pd.date_range(
        start=max(nominal["date"].min(), cpi["date"].min()),
        end=nominal["date"].max(),
        freq="D",
    )
    cpi_d = pd.DataFrame({"date": daily_dates}).merge(cpi, on="date", how="left")
    cpi_d["cpi_yoy"] = cpi_d["cpi_yoy"].ffill()

    df = nominal.merge(cpi_d, on="date", how="inner").dropna()
    df["real_rate"] = df["nominal"] - df["cpi_yoy"]

    out = df[["date", "real_rate"]].rename(columns={"real_rate": "value"})
    out["date"] = out["date"].dt.date
    out["indicator"] = "US_REAL_RATE"
    out["unit"] = "%"
    out["frequency"] = "D"
    out["source"] = "derived:nominal-cpi_yoy"
    return out


def upsert_metrics(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["indicator", "date", "value", "unit", "frequency", "source"]
    df = df[cols].copy()
    con.register("metrics_df", df)
    con.execute(
        "INSERT OR REPLACE INTO gold_metrics "
        "(indicator, date, value, unit, frequency, source) "
        "SELECT * FROM metrics_df"
    )
    con.unregister("metrics_df")
    return len(df)


def upsert_ratios(con: duckdb.DuckDBPyConnection) -> int:
    """从 gold_metrics 重建 gold_ratios 的 real_rate / nominal_10y / cpi_yoy 三列。

    注:gold_ratios 的 gold_oil / gold_silver 由 fetch_gold_ratios.py 维护,这里只更新利率三列。
    """
    sql = """
    WITH n AS (
        SELECT date, value AS nominal_10y FROM gold_metrics
        WHERE indicator='US_10Y_NOMINAL'
    ), c AS (
        SELECT date, value AS cpi_yoy FROM gold_metrics
        WHERE indicator='US_CPI_YOY'
    ), r AS (
        SELECT date, value AS real_rate FROM gold_metrics
        WHERE indicator='US_REAL_RATE'
    ), all_dates AS (
        SELECT date FROM n
        UNION
        SELECT date FROM c
        UNION
        SELECT date FROM r
    )
    SELECT
        d.date,
        n.nominal_10y,
        c.cpi_yoy,
        r.real_rate
    FROM all_dates d
    LEFT JOIN n USING (date)
    LEFT JOIN c USING (date)
    LEFT JOIN r USING (date)
    """
    df = con.execute(sql).fetchdf()
    if df.empty:
        return 0
    # upsert 到 gold_ratios:只更新这三列(gold_oil/gold_silver 不动)
    con.register("rates_df", df)
    con.execute("""
    INSERT INTO gold_ratios (date, nominal_10y, cpi_yoy, real_rate)
    SELECT date, nominal_10y, cpi_yoy, real_rate FROM rates_df
    ON CONFLICT (date) DO UPDATE SET
        nominal_10y = EXCLUDED.nominal_10y,
        cpi_yoy = EXCLUDED.cpi_yoy,
        real_rate = EXCLUDED.real_rate
    """)
    con.unregister("rates_df")
    return len(df)


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_data() -> dict[str, pd.DataFrame]:
    today = date.today()
    out = {}
    out["US_10Y_NOMINAL"] = pd.DataFrame({
        "indicator": "US_10Y_NOMINAL",
        "date": [today - timedelta(days=k) for k in range(5)],
        "value": [4.30, 4.32, 4.28, 4.35, 4.40],
        "unit": "%",
        "frequency": "D",
        "source": "smoke",
    })
    # 13 个月 MoM,后面 derive_cpi_yoy 才有 1 行 yoy
    out["US_CPI_MOM"] = pd.DataFrame({
        "indicator": "US_CPI_MOM",
        "date": [today.replace(day=1) - timedelta(days=30 * k) for k in range(14)],
        "value": [0.4, 0.3, 0.2, 0.4, 0.5, 0.3, 0.4, 0.3, 0.2, 0.4, 0.5, 0.3, 0.4, 0.4],
        "unit": "%",
        "frequency": "M",
        "source": "smoke",
    })
    return out


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    print(f"📈 抓美元利率/CPI/实际利率 → {db_path}")
    if args.smoke:
        print("   (smoke 模式,不联网)")

    rows_total = 0
    failures = []

    # 1. 抓 US_10Y_NOMINAL + US_CPI_MOM
    pipeline = [
        ("US_10Y_NOMINAL", fetch_us_10y),
        ("US_CPI_MOM",     fetch_us_cpi_mom),
    ]
    for ind, fn in pipeline:
        try:
            df = smoke_data()[ind] if args.smoke else fn()
            n = upsert_metrics(con, df)
            print(f"   ✅ {ind:<18} {n:>6} 行")
            rows_total += n
        except Exception as e:
            tb = traceback.format_exc().splitlines()[-1]
            failures.append((ind, f"{type(e).__name__}: {e} · {tb}"))
            print(f"   ❌ {ind:<18} {type(e).__name__}: {e}", file=sys.stderr)

    # 2. 派生 US_CPI_YOY(基于已入库的 MoM)
    try:
        df = derive_cpi_yoy(con)
        n = upsert_metrics(con, df)
        print(f"   ✅ {'US_CPI_YOY':<18} {n:>6} 行 (派生)")
        rows_total += n
    except Exception as e:
        failures.append(("US_CPI_YOY", f"{type(e).__name__}: {e}"))
        print(f"   ❌ {'US_CPI_YOY':<18} {e}", file=sys.stderr)

    # 3. 派生 US_REAL_RATE(基于 nominal + yoy)
    try:
        df = derive_real_rate(con)
        n = upsert_metrics(con, df)
        print(f"   ✅ {'US_REAL_RATE':<18} {n:>6} 行 (派生)")
        rows_total += n
    except Exception as e:
        failures.append(("US_REAL_RATE", f"{type(e).__name__}: {e}"))
        print(f"   ❌ {'US_REAL_RATE':<18} {e}", file=sys.stderr)

    # 4. 同步到 gold_ratios 的三列
    try:
        n = upsert_ratios(con)
        print(f"   ✅ {'gold_ratios:rates':<18} {n:>6} 行(三列联动)")
    except Exception as e:
        failures.append(("gold_ratios", f"{type(e).__name__}: {e}"))
        print(f"   ❌ {'gold_ratios:rates':<18} {e}", file=sys.stderr)

    # 总结
    rows_db = con.execute("SELECT COUNT(*) FROM gold_metrics").fetchone()[0]
    print(f"\n📊 写入 {rows_total} 行,gold_metrics 总计 {rows_db} 行")
    inds = con.execute(
        "SELECT indicator, COUNT(*) FROM gold_metrics "
        "WHERE indicator IN ('US_10Y_NOMINAL','US_CPI_MOM','US_CPI_YOY','US_REAL_RATE') "
        "GROUP BY indicator ORDER BY indicator"
    ).fetchall()
    for ind, n in inds:
        print(f"   {ind:<18} {n:>6}")

    # 当前实际利率快照
    snap = con.execute("""
        SELECT date, value FROM gold_metrics
        WHERE indicator='US_REAL_RATE'
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    if snap:
        print(f"\n   最新实际利率:{snap[0]}  {snap[1]:+.2f}%")

    con.close()

    if failures:
        print(f"\n⚠️  {len(failures)} 项失败:")
        for ind, err in failures:
            print(f"   {ind}: {err}")
        return 1 if rows_total == 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
