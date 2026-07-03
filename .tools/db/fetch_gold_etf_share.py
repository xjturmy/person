"""v2.4 step-D · ETF 份额时序抓取(资金流入流出信号)。

数据源:
- 优先 `.config/gold_etf_share_manual.csv`(列:date,etf_code,share)
- 备选:gold_etf_prices.volume 的 5 日变化(成交量爆量代理)
- 可选 AkShare `fund_etf_fund_info_em(symbol, ...)`;当前没有稳定份额字段,默认不启用

写入:
- gold_etf_share(etf_code, date, share, share_change_5d)

share_change_5d 由本脚本预算好,signal 引擎读取最新一行直接判定。

用法:
    .venv/bin/python .tools/db/fetch_gold_etf_share.py
    .venv/bin/python .tools/db/fetch_gold_etf_share.py --only 518880
    .venv/bin/python .tools/db/fetch_gold_etf_share.py --smoke
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

MANUAL_CSV = ROOT / ".config" / "gold_etf_share_manual.csv"

ETF_CODES = ["518880", "159937", "159934", "518800"]


def _retry(fn, attempts: int = 3, sleep: float = 1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last  # type: ignore[misc]


# ───── AkShare 抓取 ────────────────────────────────────────────────────


def fetch_share_one_akshare(etf_code: str) -> pd.DataFrame:
    """单只 ETF 累计份额时序(AkShare fund_etf_fund_info_em)。

    返回列:date / share(亿份)
    """
    import akshare as ak

    df = _retry(lambda: ak.fund_etf_fund_info_em(fund=etf_code), attempts=2, sleep=2.0)
    if df is None or df.empty:
        raise ValueError(f"empty for {etf_code}")

    # 列名典型:['净值日期', '单位净值', '累计净值', '日增长率']
    # 这个接口返回的是净值不是份额。份额需要用 fund_etf_category_sina 或 fund_value_em
    # 实际上 AkShare 没有稳定的「ETF 历史份额」接口。
    # ⇒ 该接口返回空 / 列结构不符,统一抛出让上层走手填 / 派生路径
    raise NotImplementedError(
        "AkShare 暂无稳定的 ETF 份额时序接口;走手填 CSV 或 volume 派生路径"
    )


# ───── 手填 CSV ────────────────────────────────────────────────────────


def fetch_share_manual_csv() -> pd.DataFrame:
    """从 .config/gold_etf_share_manual.csv 读手填份额数据。

    CSV 格式:date,etf_code,share(亿份)
    """
    if not MANUAL_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(MANUAL_CSV)
    needed = {"date", "etf_code", "share"}
    if not needed.issubset(set(df.columns)):
        print(f"   ⚠️ {MANUAL_CSV.name} 缺列(需 {needed}):{df.columns.tolist()}")
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["share"] = pd.to_numeric(df["share"], errors="coerce")
    df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    return df.dropna(subset=["date", "share"])


def derive_share_proxy_from_volume(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """用 ETF 成交量派生资金流代理。

    AkShare 当前没有稳定的 ETF 历史份额接口。为避免 gold_etf_share 长期空表,
    用 volume 的 5 日变化近似 share_change_5d;share 字段保存成交量(手)代理值。
    过热引擎只读取 share_change_5d,所以该代理能让信号 5 进入可判定状态。
    """
    try:
        df = con.execute("""
            SELECT etf_code, date, volume
            FROM gold_etf_prices
            WHERE etf_code IN ('518880', '159937', '159934', '518800')
              AND volume IS NOT NULL
            ORDER BY etf_code, date
        """).df()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()
    out = []
    for code, sub in df.groupby("etf_code"):
        sub = sub.sort_values("date").copy()
        sub["share"] = pd.to_numeric(sub["volume"], errors="coerce")
        sub["share_change_5d"] = sub["share"].pct_change(periods=5) * 100
        out.append(sub[["etf_code", "date", "share", "share_change_5d"]])
    return pd.concat(out, ignore_index=True).dropna(subset=["date", "share"])


# ───── 计算 share_change_5d ────────────────────────────────────────────


def compute_change_5d(df: pd.DataFrame) -> pd.DataFrame:
    """单 etf 内排序 + 5 日变化 %。"""
    if df.empty:
        return df
    out = []
    for code, sub in df.groupby("etf_code"):
        sub = sub.sort_values("date").copy()
        sub["share_change_5d"] = sub["share"].pct_change(periods=5) * 100
        out.append(sub)
    return pd.concat(out, ignore_index=True)


# ───── 写库 ────────────────────────────────────────────────────────────


def upsert_share(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["etf_code", "date", "share", "share_change_5d"]
    df = df[[c for c in cols if c in df.columns]].copy()
    con.register("share_df", df)
    con.execute("""
        INSERT OR REPLACE INTO gold_etf_share (etf_code, date, share, share_change_5d)
        SELECT etf_code, date, share, share_change_5d FROM share_df
    """)
    con.unregister("share_df")
    return len(df)


# ───── smoke ──────────────────────────────────────────────────────────


def smoke_share() -> pd.DataFrame:
    """构造 4 ETF × 30 天的合成 share 数据。"""
    today = date.today()
    rows = []
    for code, base in zip(ETF_CODES, [320.0, 95.0, 78.0, 42.0]):
        for k in range(30):
            d = today - timedelta(days=k)
            # 随天数线性增长 + 小幅波动
            share = base + (29 - k) * 0.5 + (k % 3 - 1) * 0.3
            rows.append({"etf_code": code, "date": d, "share": share})
    return pd.DataFrame(rows)


# ───── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--only", help="单只 ETF code(只走手填 CSV)")
    ap.add_argument("--smoke", action="store_true", help="不联网,合成数据")
    ap.add_argument("--try-akshare", action="store_true",
                    help="尝试 AkShare 份额接口(当前已知不稳定,默认跳过)")
    ap.add_argument("--no-volume-proxy", action="store_true",
                    help="手填 CSV 缺失时不写成交量代理")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    ensure_db(db_path)
    con = duckdb.connect(str(db_path))

    print(f"📈 抓 ETF 份额时序 → {db_path}")

    df = pd.DataFrame()
    source = ""

    if args.smoke:
        df = smoke_share()
        source = "smoke"
    else:
        # 1. manual CSV:明确、可审计的真实份额源
        if df.empty:
            df = fetch_share_manual_csv()
            if not df.empty:
                source = "manual_csv"

        # 2. AkShare:当前无稳定份额字段,仅显式调试时尝试
        if df.empty and args.try_akshare:
            try:
                akshare_dfs = []
                targets = [args.only] if args.only else ETF_CODES
                for code in targets:
                    try:
                        one = fetch_share_one_akshare(code)
                        one["etf_code"] = code
                        akshare_dfs.append(one)
                    except NotImplementedError:
                        raise  # 一个不支持就全部不支持,fail-fast
                    except Exception as e:
                        tb = traceback.format_exc().splitlines()[-1]
                        print(f"   ❌ {code} AkShare {type(e).__name__}: {e} · {tb}",
                              file=sys.stderr)
                if akshare_dfs:
                    df = pd.concat(akshare_dfs, ignore_index=True)
                    source = "akshare"
            except NotImplementedError:
                print("   ⚪ AkShare 无稳定份额接口(已知)→ 走 volume proxy")

        # 3. volume proxy:真实份额源缺失时的稳定可复现兜底
        if df.empty and not args.no_volume_proxy:
            df = derive_share_proxy_from_volume(con)
            if not df.empty:
                source = "volume_proxy"

    if df.empty:
        print(f"   ⚪ 无份额数据(AkShare 不支持 + 手填 CSV {MANUAL_CSV.name} 缺 + volume proxy 不可用)")
        print(f"      手填示例(亿份):date,etf_code,share")
        print(f"      过热引擎将自动走 volume 派生分支(成交量爆量代理 信号 5)")
        con.close()
        return 0

    # 3. 计算 share_change_5d + 入库
    df = compute_change_5d(df)
    n = upsert_share(con, df)
    print(f"   ✅ gold_etf_share        {n:>6} 行 (源:{source})")

    n_db = con.execute("SELECT COUNT(*) FROM gold_etf_share").fetchone()[0]
    n_etf = con.execute("SELECT COUNT(DISTINCT etf_code) FROM gold_etf_share").fetchone()[0]
    con.close()
    print(f"\n📊 gold_etf_share 总 {n_db} 行 / {n_etf} 只 ETF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
