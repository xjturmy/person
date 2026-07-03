"""v2.4 候选 ⑨ Phase 1 · L1 全市场快照层

抓全 A 股最新行情快照(~5400 行)+ EM 板块行业映射,写入 data/market.duckdb。

数据源:
- ak.stock_zh_a_spot_em()                   全 A 实时行情(单次,~3-15s)
- ak.stock_board_industry_name_em()         EM 板块行业 list(~80 个)
- ak.stock_board_industry_cons_em(industry) 单个行业成分股(用于建 ticker→industry 映射)

写入:
- market_spot 表    全 A × ~22 列(每周日刷,主键 (ticker, snapshot_date))
- ingestion_log 表  最近一次抓取的 row 数 / 行业数 / 时间戳

用法:
    .venv/bin/python .tools/db/fetch_market_spot.py            # 全量抓
    .venv/bin/python .tools/db/fetch_market_spot.py --skip-industry  # 仅刷 spot,跳过行业映射(快)
    .venv/bin/python .tools/db/fetch_market_spot.py --smoke    # 不写库,纯打日志测试
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "market.duckdb"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"
INDUSTRY_CACHE_CSV = ROOT / ".config" / "companies_industry.csv"


# ───── DB schema ───────────────────────────────────────────────────────

def ensure_db(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS market_spot (
            ticker                  VARCHAR,
            name                    VARCHAR,
            industry_em             VARCHAR,
            last_price              DOUBLE,
            change_pct              DOUBLE,
            change_amount           DOUBLE,
            volume                  DOUBLE,
            amount                  DOUBLE,
            amplitude               DOUBLE,
            high                    DOUBLE,
            low                     DOUBLE,
            open                    DOUBLE,
            prev_close              DOUBLE,
            volume_ratio            DOUBLE,
            turnover_rate           DOUBLE,
            pe                      DOUBLE,
            pb                      DOUBLE,
            total_market_cap        DOUBLE,
            circulating_market_cap  DOUBLE,
            change_60d              DOUBLE,
            change_ytd              DOUBLE,
            snapshot_date           DATE,
            PRIMARY KEY (ticker, snapshot_date)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_log (
            run_at         TIMESTAMP,
            spot_rows      INTEGER,
            industry_count INTEGER,
            mapped_rows    INTEGER,
            note           VARCHAR
        )
    """)


# ───── fetch ───────────────────────────────────────────────────────────

_RENAME_SPOT = {
    "代码": "ticker",
    "名称": "name",
    "最新价": "last_price",
    "涨跌幅": "change_pct",
    "涨跌额": "change_amount",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "最高": "high",
    "最低": "low",
    "今开": "open",
    "昨收": "prev_close",
    "量比": "volume_ratio",
    "换手率": "turnover_rate",
    "市盈率-动态": "pe",
    "市净率": "pb",
    "总市值": "total_market_cap",
    "流通市值": "circulating_market_cap",
    "60日涨跌幅": "change_60d",
    "年初至今涨跌幅": "change_ytd",
}


def fetch_spot(retries: int = 5) -> pd.DataFrame:
    """全 A 实时快照,EM 主路径(20 列 + PE/市值)+ sina 兜底(基础 6 列)。

    EM push2 端点开市时偶尔 SSL 挂(memory: reference_akshare_sina_fallback);重试 5 次后 sina 兜底。
    """
    import akshare as ak
    last_err: Exception | None = None
    df = None
    # 主路径:EM
    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_spot_em()
            break
        except Exception as e:
            last_err = e
            print(f"  ⚠️  EM spot 第 {attempt + 1}/{retries} 次失败:{str(e)[:80]}", file=sys.stderr)
            time.sleep(min(5 * (attempt + 1), 30))

    # 兜底:sina(列少但能跑;industry / pe / market_cap 由后续行业映射 + 单家个股补)
    if df is None:
        print(f"  ⚠️  EM 全失败,切 sina spot…", file=sys.stderr)
        sdf = None
        sina_err: Exception | None = None
        for attempt in range(retries):
            try:
                sdf = ak.stock_zh_a_spot()
                break
            except Exception as e:
                sina_err = e
                print(f"  ⚠️  sina 第 {attempt + 1}/{retries} 次失败:{str(e)[:80]}", file=sys.stderr)
                time.sleep(min(8 * (attempt + 1), 40))
        if sdf is None:
            print(f"  ✗ sina 兜底也全失败:{sina_err}", file=sys.stderr)
            raise last_err  # type: ignore[misc]

        # 2026-06 实测:akshare sina spot 现在返回中文列(14 列,无 pe/pb/市值/换手率)
        # 早期英文列已废弃,改为中文映射;缺失列由后续行业映射 + 个股单查补
        sdf = sdf.rename(columns={
            "代码": "ticker", "名称": "name",
            "最新价": "last_price", "涨跌额": "change_amount",
            "涨跌幅": "change_pct", "昨收": "prev_close",
            "今开": "open", "最高": "high", "最低": "low",
            "成交量": "volume", "成交额": "amount",
        })
        if "ticker" not in sdf.columns:
            raise RuntimeError(f"sina 返回列对不上,实际列:{list(sdf.columns)}")
        sdf["ticker"] = sdf["ticker"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True).str.zfill(6)
        df = sdf
        print(f"  ✓ sina 兜底成功:{len(df)} 行", file=sys.stderr)

    df = df.rename(columns=_RENAME_SPOT)
    keep = [c for c in _RENAME_SPOT.values() if c in df.columns]
    df = df[keep].copy()

    # 数值列转 float;非数值(N/A、—)→ NaN
    num_cols = [c for c in keep if c not in {"ticker", "name"}]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df = df.dropna(subset=["ticker"])
    df = df.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)
    return df


def fetch_industry_mapping(quiet: bool = False) -> pd.DataFrame:
    """遍历 EM 板块行业 list,逐个抓成分股,返回 (ticker, industry_em) 长表。

    ~80 个行业 × ~3s/行业 ≈ 4-5 分钟。失败的单个行业跳过(只丢失该行业的映射)。
    """
    import akshare as ak

    try:
        boards = ak.stock_board_industry_name_em()
    except Exception as e:
        print(f"  ⚠️  EM 行业 list 抓取失败:{str(e)[:80]}", file=sys.stderr)
        return pd.DataFrame(columns=["ticker", "industry_em"])

    if "板块名称" not in boards.columns:
        print(f"  ⚠️  EM 行业 list 列不符合预期:{boards.columns.tolist()}", file=sys.stderr)
        return pd.DataFrame(columns=["ticker", "industry_em"])

    industries = boards["板块名称"].dropna().tolist()
    if not quiet:
        print(f"  → 共 {len(industries)} 个 EM 行业,开始逐个抓成分股…")

    rows: list[dict] = []
    fail = 0
    for i, ind in enumerate(industries, 1):
        try:
            cons = ak.stock_board_industry_cons_em(symbol=ind)
            if cons is None or cons.empty or "代码" not in cons.columns:
                fail += 1
                continue
            for t in cons["代码"].astype(str).str.zfill(6).tolist():
                rows.append({"ticker": t, "industry_em": ind})
        except Exception as e:
            fail += 1
            if not quiet:
                print(f"     [{i}/{len(industries)}] {ind} 失败:{str(e)[:60]}",
                      file=sys.stderr)
            continue
        if not quiet and i % 10 == 0:
            print(f"     [{i}/{len(industries)}] 累计 {len(rows)} 条映射,失败 {fail}")

    if not rows:
        return pd.DataFrame(columns=["ticker", "industry_em"])

    df = pd.DataFrame(rows)
    # 同一只票出现在多个行业时取第一个(EM 板块默认按主行业归类)
    df = df.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)
    if not quiet:
        print(f"  ✓ 行业映射完成:{len(df)} 只票 / {df['industry_em'].nunique()} 行业 / 失败 {fail}")
    return df


def fallback_industry_mapping() -> pd.DataFrame:
    """本地行业映射兜底。

    EM 行业接口经常在开市时断连;此时至少用本地公司清单/缓存覆盖自选池,
    避免 Dashboard 对核心 100 家完全无行业标签。
    """
    frames: list[pd.DataFrame] = []
    if INDUSTRY_CACHE_CSV.exists():
        cache = pd.read_csv(INDUSTRY_CACHE_CSV, dtype={"ticker": str})
        if {"ticker", "industry_em"}.issubset(cache.columns):
            frames.append(cache[["ticker", "industry_em"]].copy())
    if COMPANIES_CSV.exists():
        comp = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
        if {"stock", "industry_l2"}.issubset(comp.columns):
            local = comp.rename(columns={"stock": "ticker", "industry_l2": "industry_em"})
            local["ticker"] = local.apply(
                lambda r: str(r["ticker"]).zfill(5 if r.get("category") == "hk" else 6),
                axis=1,
            )
            frames.append(local[["ticker", "industry_em"]].copy())
    if not frames:
        return pd.DataFrame(columns=["ticker", "industry_em"])
    df = pd.concat(frames, ignore_index=True)
    df["ticker"] = df["ticker"].astype(str)
    df["industry_em"] = df["industry_em"].fillna("").astype(str).str.strip()
    df = df[df["industry_em"] != ""]
    return df.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)


# ───── write ───────────────────────────────────────────────────────────

def upsert_spot(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """按主键 (ticker, snapshot_date) 覆盖写入。"""
    if df.empty:
        return 0
    cols = [
        "ticker", "name", "industry_em", "last_price", "change_pct", "change_amount",
        "volume", "amount", "amplitude", "high", "low", "open", "prev_close",
        "volume_ratio", "turnover_rate", "pe", "pb",
        "total_market_cap", "circulating_market_cap",
        "change_60d", "change_ytd", "snapshot_date",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols].copy()

    con.register("spot_df", df)
    # 同日重抓:先删当日,再插
    snapshot = df["snapshot_date"].iloc[0]
    con.execute("DELETE FROM market_spot WHERE snapshot_date = ?", [snapshot])
    con.execute(f"INSERT INTO market_spot SELECT {', '.join(cols)} FROM spot_df")
    con.unregister("spot_df")
    return len(df)


def log_run(con: duckdb.DuckDBPyConnection, spot_rows: int, ind_count: int,
            mapped: int, note: str = "") -> None:
    con.execute(
        "INSERT INTO ingestion_log VALUES (?, ?, ?, ?, ?)",
        [datetime.now(), spot_rows, ind_count, mapped, note],
    )


# ───── main ────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-industry", action="store_true",
                        help="跳过 EM 行业映射(快;industry_em 列将为空)")
    parser.add_argument("--smoke", action="store_true",
                        help="不写库,只打日志验证管道")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    t0 = time.time()
    print(f"[fetch_market_spot] {datetime.now():%Y-%m-%d %H:%M:%S}")

    # Step 1: spot
    print("→ 1/2 抓全 A 实时快照…")
    try:
        spot = fetch_spot()
    except Exception as e:
        print(f"FAILED at fetch_spot: {e}", file=sys.stderr)
        traceback.print_exc()
        return 2
    print(f"  ✓ {len(spot)} 行 / {len(spot.columns)} 列  耗时 {time.time() - t0:.1f}s")

    # Step 2: industry mapping
    industry_df = pd.DataFrame(columns=["ticker", "industry_em"])
    if not args.skip_industry:
        print("→ 2/2 抓 EM 行业映射…")
        try:
            industry_df = fetch_industry_mapping(quiet=args.quiet)
        except Exception as e:
            print(f"  ⚠️  industry 映射失败(non-blocking):{e}", file=sys.stderr)
        if industry_df.empty:
            industry_df = fallback_industry_mapping()
            if not industry_df.empty:
                print(f"  ✓ 本地行业映射兜底:{len(industry_df)} 只票")

    # merge
    if not industry_df.empty:
        spot = spot.merge(industry_df, on="ticker", how="left", suffixes=("", "_y"))
        if "industry_em_y" in spot.columns:
            spot["industry_em"] = spot["industry_em_y"]
            spot = spot.drop(columns=["industry_em_y"])
    else:
        spot["industry_em"] = None

    spot["snapshot_date"] = datetime.now().date()

    mapped = int(spot["industry_em"].notna().sum())
    print(f"  ✓ 总计 {len(spot)} 票,行业映射命中 {mapped} ({mapped/max(len(spot),1)*100:.1f}%)")

    if args.smoke:
        print("--smoke 模式不写库;退出。")
        print(spot.head(8).to_string(index=False))
        return 0

    # write
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        ensure_db(con)
        n = upsert_spot(con, spot)
        log_run(con, n, industry_df["industry_em"].nunique() if not industry_df.empty else 0,
                mapped, note="ok" if mapped > 0 else "no-industry")
        print(f"✓ 写入 {DB_PATH}  {n} 行  累计耗时 {time.time() - t0:.1f}s")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
