"""v2.6 · 沪金主力期货 vs Au99.99 现货 基差时序抓取。

输出指标:GOLD_FUTURES_BASIS_PCT — (沪金主力期货收盘 - Au99.99 现货收盘) / 现货 × 100
单位:% · 日频

数据源(2026-05 实测,akshare 期货接口易变):
1. 首选:`ak.futures_main_sina(symbol='AU0')`   — 沪金主连日线(新浪),包含 close
2. 备选:`ak.futures_zh_daily_sina(symbol='AU0')` — 老版本同源新浪日线
3. 备选:`ak.get_futures_daily(start_date, end_date, market='SHFE', code='AU')`
        — SHFE 历史日线(按日期范围,合约层数据)

现货读 gold_metrics 表 `indicator='GOLD_SGE_AU99'`(沪金 Au99.99 现货,CNY/g)
期货单位也是 CNY/g(沪金合约规则),无需单位换算。

写入:data/gold.duckdb / gold_metrics 表
PK: (indicator='GOLD_FUTURES_BASIS_PCT', date) — INSERT OR REPLACE 幂等

用法:
    .venv/bin/python .tools/db/fetch_gold_futures_basis.py             # 默认 5 年
    .venv/bin/python .tools/db/fetch_gold_futures_basis.py --years 3
    .venv/bin/python .tools/db/fetch_gold_futures_basis.py --smoke     # 离线假数据

关键决策:
- 基差正负都可能是过热信号(负基差 = 现货溢价 = 实物紧缺也是高位讯号),
  所以我们写入有正负号的原始基差%,engine 那一层负责 abs() 阈值判定。
- 用沪金主连(AU0)而非具体合约月,避免合约切换的人工跳跃。
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

INDICATOR = "GOLD_FUTURES_BASIS_PCT"
SPOT_INDICATOR = "GOLD_SGE_AU99"


def _retry(fn, attempts: int = 3, sleep: float = 1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last  # type: ignore[misc]


# ───── 期货抓取 ────────────────────────────────────────────────────────


def _normalize_futures_df(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """统一为 [date, close] 两列,date 是 datetime.date。"""
    if df is None or df.empty:
        raise ValueError(f"{label}: empty dataframe")

    # 找日期列
    date_col = None
    for cand in ("date", "日期", "trade_date", "datetime"):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is None:
        raise ValueError(f"{label}: 找不到日期列;cols={list(df.columns)}")

    # 找收盘列
    close_col = None
    for cand in ("close", "收盘", "收盘价", "settle", "结算价"):
        if cand in df.columns:
            close_col = cand
            break
    if close_col is None:
        raise ValueError(f"{label}: 找不到收盘列;cols={list(df.columns)}")

    out = df[[date_col, close_col]].rename(
        columns={date_col: "date", close_col: "close"}
    ).copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna()
    return out.sort_values("date").reset_index(drop=True)


def fetch_futures_main_sina() -> pd.DataFrame:
    """首选:ak.futures_main_sina(symbol='AU0') — 沪金主连日线。"""
    import akshare as ak
    df = _retry(lambda: ak.futures_main_sina(symbol="AU0"), attempts=2, sleep=2.0)
    return _normalize_futures_df(df, "futures_main_sina(AU0)")


def fetch_futures_zh_daily_sina() -> pd.DataFrame:
    """备选 1:ak.futures_zh_daily_sina(symbol='AU0') — 老版本同源。"""
    import akshare as ak
    df = _retry(lambda: ak.futures_zh_daily_sina(symbol="AU0"), attempts=2, sleep=2.0)
    return _normalize_futures_df(df, "futures_zh_daily_sina(AU0)")


def fetch_get_futures_daily(start: date, end: date) -> pd.DataFrame:
    """备选 2:ak.get_futures_daily(market='SHFE', code='AU')。

    该接口按日期范围请求,SHFE 黄金需要逐月合约 (AU2606 ...) 拼接,
    工程量大且 SHFE 接口对中国 IP 经常 SSL 挂。仅作最后兜底,先返回失败让用户感知。
    """
    import akshare as ak

    df = _retry(
        lambda: ak.get_futures_daily(
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            market="SHFE",
        ),
        attempts=2,
        sleep=2.0,
    )
    if df is None or df.empty:
        raise ValueError("get_futures_daily: empty dataframe")
    # SHFE 返回的是所有合约;筛选 AU + 取主力(成交量最大)
    if "symbol" in df.columns:
        au = df[df["symbol"].astype(str).str.startswith("AU")].copy()
    elif "variety" in df.columns:
        au = df[df["variety"].astype(str).str.upper() == "AU"].copy()
    else:
        au = df.copy()
    if au.empty:
        raise ValueError("get_futures_daily: AU 合约空")
    # 每个交易日取成交量最大的合约 = 主力
    if "volume" in au.columns:
        au["volume"] = pd.to_numeric(au["volume"], errors="coerce").fillna(0)
        au = au.sort_values(["date", "volume"], ascending=[True, False])
        au = au.drop_duplicates(subset=["date"], keep="first")
    return _normalize_futures_df(au, "get_futures_daily(SHFE,AU)")


def fetch_futures_series(years: int) -> tuple[pd.DataFrame, str]:
    """主抓取入口 — 顺序尝试 3 个接口,返回 (df, source_label)。

    df: 列 [date, close]。失败抛 RuntimeError(包含所有 fallback 的错误)。
    """
    end = date.today()
    start = date(end.year - years, end.month, end.day) if not (
        end.month == 2 and end.day == 29
    ) else date(end.year - years, 2, 28)

    errors: list[str] = []

    # 1) 首选
    try:
        df = fetch_futures_main_sina()
        # 截断到回填范围
        df = df[df["date"] >= start].reset_index(drop=True)
        if df.empty:
            errors.append("futures_main_sina: 时间范围内空")
        else:
            return df, "akshare:futures_main_sina(AU0)"
    except Exception as e:
        errors.append(f"futures_main_sina: {type(e).__name__}: {e}")

    # 2) 备选 1
    try:
        df = fetch_futures_zh_daily_sina()
        df = df[df["date"] >= start].reset_index(drop=True)
        if df.empty:
            errors.append("futures_zh_daily_sina: 时间范围内空")
        else:
            return df, "akshare:futures_zh_daily_sina(AU0)"
    except Exception as e:
        errors.append(f"futures_zh_daily_sina: {type(e).__name__}: {e}")

    # 3) 备选 2(SHFE 全合约)
    try:
        df = fetch_get_futures_daily(start, end)
        if df.empty:
            errors.append("get_futures_daily: 范围内空")
        else:
            return df, "akshare:get_futures_daily(SHFE,AU)"
    except Exception as e:
        errors.append(f"get_futures_daily: {type(e).__name__}: {e}")

    raise RuntimeError("所有 akshare 期货接口都失败:\n  · " + "\n  · ".join(errors))


# ───── 现货读取 ────────────────────────────────────────────────────────


def read_spot(con: duckdb.DuckDBPyConnection, start: date) -> pd.DataFrame:
    """从 gold_metrics 读 Au99.99 现货时序(CNY/g)。"""
    df = con.execute(
        "SELECT date, value AS spot FROM gold_metrics "
        "WHERE indicator = ? AND value IS NOT NULL AND date >= ? "
        "ORDER BY date",
        [SPOT_INDICATOR, start],
    ).fetchdf()
    if df.empty:
        raise RuntimeError(
            f"gold_metrics 没有 {SPOT_INDICATOR} 现货数据(请先跑 fetch_gold_prices.py)"
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["spot"] = pd.to_numeric(df["spot"], errors="coerce")
    return df.dropna().reset_index(drop=True)


# ───── 基差计算 ────────────────────────────────────────────────────────


def compute_basis(futures: pd.DataFrame, spot: pd.DataFrame) -> pd.DataFrame:
    """(期货 - 现货) / 现货 × 100。

    按 date inner join,丢掉非交易日 / 单边缺数据的日期。
    """
    f = futures[["date", "close"]].rename(columns={"close": "fut"}).copy()
    s = spot[["date", "spot"]].copy()
    merged = f.merge(s, on="date", how="inner")
    merged = merged[merged["spot"] > 0].copy()
    merged["value"] = (merged["fut"] - merged["spot"]) / merged["spot"] * 100.0
    merged = merged.dropna(subset=["value"])

    out = merged[["date", "value"]].copy()
    out["indicator"] = INDICATOR
    out["unit"] = "%"
    out["frequency"] = "D"
    return out


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_data() -> pd.DataFrame:
    today = date.today()
    rows = []
    for k in range(5):
        rows.append({
            "indicator": INDICATOR,
            "date": today - timedelta(days=k),
            "value": 0.5 + k * 0.1,  # 0.5 ~ 0.9 % 假数据
            "unit": "%",
            "frequency": "D",
            "source": "smoke",
        })
    return pd.DataFrame(rows)


# ───── upsert ──────────────────────────────────────────────────────────


def upsert(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, source: str) -> int:
    if df.empty:
        return 0
    df = df.copy()
    df["source"] = source
    cols = ["indicator", "date", "value", "unit", "frequency", "source"]
    df = df[cols]
    con.register("basis_df", df)
    con.execute(
        "INSERT OR REPLACE INTO gold_metrics "
        "(indicator, date, value, unit, frequency, source) "
        "SELECT indicator, date, value, unit, frequency, source FROM basis_df"
    )
    con.unregister("basis_df")
    return len(df)


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="抓沪金主力期货 vs Au99.99 现货基差,写入 gold_metrics"
    )
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--years", type=int, default=5, help="回填年数(默认 5)")
    ap.add_argument("--smoke", action="store_true", help="离线假数据(不联网)")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    print(f"🥇 抓沪金主力期货基差(回填 {args.years} 年) → {db_path}")

    try:
        if args.smoke:
            df = smoke_data()
            n = upsert(con, df, "smoke")
            print(f"   ✅ smoke 写入 {n} 行")
            source_label = "smoke"
        else:
            # 1) 期货
            end = date.today()
            start = date(end.year - args.years, end.month, end.day) if not (
                end.month == 2 and end.day == 29
            ) else date(end.year - args.years, 2, 28)

            print(f"   ⏳ 拉期货时序 [{start} ~ {end}] ...")
            try:
                fut, source_label = fetch_futures_series(args.years)
            except Exception as e:
                print(f"   ❌ 期货抓取失败:{e}", file=sys.stderr)
                con.close()
                return 2
            print(f"   ✅ 期货 {len(fut)} 行,源:{source_label}")

            # 2) 现货
            print(f"   ⏳ 读现货 {SPOT_INDICATOR} ...")
            try:
                spot = read_spot(con, start)
            except Exception as e:
                print(f"   ❌ 现货读取失败:{e}", file=sys.stderr)
                con.close()
                return 3
            print(f"   ✅ 现货 {len(spot)} 行")

            # 3) 计算基差
            df = compute_basis(fut, spot)
            if df.empty:
                print("   ❌ 基差计算后空(期货/现货日期无重叠)", file=sys.stderr)
                con.close()
                return 4

            # 4) 写入
            n = upsert(con, df, source_label)
            print(f"   ✅ 写入 {n} 行 → indicator={INDICATOR}")

        # 5) 汇报最近 5 行 + 统计
        recent = con.execute(
            "SELECT date, value FROM gold_metrics WHERE indicator = ? "
            "ORDER BY date DESC LIMIT 5",
            [INDICATOR],
        ).fetchall()
        stats = con.execute(
            "SELECT COUNT(*), MIN(value), MAX(value), AVG(value), MIN(date), MAX(date) "
            "FROM gold_metrics WHERE indicator = ?",
            [INDICATOR],
        ).fetchone()

        print(f"\n📊 {INDICATOR} 统计:")
        print(f"   总行数 {stats[0]:>6}  范围 [{stats[4]} ~ {stats[5]}]")
        print(f"   min/max/mean = {stats[1]:.4f}% / {stats[2]:.4f}% / {stats[3]:.4f}%")
        print(f"\n   最近 5 行:")
        for d, v in recent:
            print(f"     {d}   basis = {v:>8.4f}%")

    except Exception:
        traceback.print_exc()
        con.close()
        return 1

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
