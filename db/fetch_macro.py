"""dash-01 数据层:AkShare + 理杏仁 抓 7 项宏观 + 入库 DuckDB.

7 项指标:
- M2_YOY     M2 同比(月度,%)         ak.macro_china_m2_yearly
- CPI_YOY    CPI 同比(月度,%)         ak.macro_china_cpi_yearly
- 10Y_YIELD  10 年期国债收益率(日度,%)  ak.bond_zh_us_rate(取「中国国债收益率10年」)
- USDCNY     USD/CNY 即期汇率(日度)    ak.currency_boc_safe(美元中间价 ÷ 100)
- A50_PE     上证 50 PE-TTM(日度)     ak.stock_index_pe_lg(symbol="上证50")
- HS300_PE   沪深 300 PE-TTM(日度)    ak.stock_index_pe_lg(symbol="沪深300")
- A_FULL_PE  A 股全指 PE-TTM 市值加权(日度,理杏仁口径,000985 中证全指)
              格雷厄姆指数主算指标 — 与理杏仁制图工具同口径
              POST https://open.lixinger.com/api/cn/index/fundamental
              metricsList=['pe_ttm.mcw'] · token 由 lixinger_resolve_token 提供

容错:任一项失败不影响其它,合并写入 macro 表(PK = indicator+date,重复忽略)。

用法:
    .venv/bin/python .tools/db/fetch_macro.py            # 抓所有 7 项
    .venv/bin/python .tools/db/fetch_macro.py --only A_FULL_PE
    .venv/bin/python .tools/db/fetch_macro.py --smoke    # 不联网,各插 3 行假数据
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
# macro 用独立 DB,避免与主 preson.duckdb 上的 MCP/Streamlit 读锁冲突
# (与 decisions.duckdb 同思路)
DB_PATH = ROOT / "data" / "macro.duckdb"

# ───── DDL(idempotent,与 ingest.py 保持一致)─────
DDL = """
CREATE TABLE IF NOT EXISTS macro (
    indicator VARCHAR NOT NULL,
    date      DATE    NOT NULL,
    value     DOUBLE,
    unit      VARCHAR,
    frequency VARCHAR,
    source    VARCHAR DEFAULT 'akshare',
    PRIMARY KEY (indicator, date)
);
CREATE INDEX IF NOT EXISTS idx_macro_date ON macro(date);
"""


def _retry(fn, attempts: int = 3, sleep: float = 1.0):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last  # type: ignore[misc]


# ───── 5 项 fetcher ───────────────────────────────────────────────────


def fetch_m2_yoy() -> pd.DataFrame:
    """商品/日期/今值/预测值/前值 → indicator=M2_YOY · 单位 %."""
    import akshare as ak
    df = _retry(ak.macro_china_m2_yearly)
    out = df[["日期", "今值"]].rename(columns={"日期": "date", "今值": "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "M2_YOY"
    out["unit"] = "%"
    out["frequency"] = "M"
    return out


def fetch_cpi_yoy() -> pd.DataFrame:
    import akshare as ak
    df = _retry(ak.macro_china_cpi_yearly)
    out = df[["日期", "今值"]].rename(columns={"日期": "date", "今值": "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "CPI_YOY"
    out["unit"] = "%"
    out["frequency"] = "M"
    return out


def fetch_10y_yield() -> pd.DataFrame:
    """中国 10 年期国债收益率,日度。来源 bond_zh_us_rate(慢但稳)。"""
    import akshare as ak
    df = _retry(ak.bond_zh_us_rate, attempts=2, sleep=2.0)
    col = "中国国债收益率10年"
    if col not in df.columns:
        raise RuntimeError(f"列 {col} 不在 bond_zh_us_rate 输出中:{df.columns.tolist()}")
    out = df[["日期", col]].rename(columns={"日期": "date", col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = "10Y_YIELD"
    out["unit"] = "%"
    out["frequency"] = "D"
    return out


def fetch_usdcny() -> pd.DataFrame:
    """USD/CNY = 中行美元中间价 ÷ 100(原始报价为百元美元对应人民币)."""
    import akshare as ak
    df = _retry(ak.currency_boc_safe)
    out = df[["日期", "美元"]].rename(columns={"日期": "date", "美元": "raw"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["raw"] = pd.to_numeric(out["raw"], errors="coerce")
    out = out.dropna()
    out["value"] = out["raw"] / 100.0
    out["indicator"] = "USDCNY"
    out["unit"] = "CNY/USD"
    out["frequency"] = "D"
    return out[["indicator", "date", "value", "unit", "frequency"]]


def _fetch_index_pe(ak_symbol: str, indicator: str) -> pd.DataFrame:
    """指数 PE-TTM(日度) — 复用 ak.stock_index_pe_lg。"""
    import akshare as ak
    df = _retry(lambda: ak.stock_index_pe_lg(symbol=ak_symbol))
    col = "滚动市盈率"
    if col not in df.columns:
        raise RuntimeError(f"列 {col} 不在 stock_index_pe_lg 输出中:{df.columns.tolist()}")
    out = df[["日期", col]].rename(columns={"日期": "date", col: "value"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna()
    out["indicator"] = indicator
    out["unit"] = "x"
    out["frequency"] = "D"
    return out


def fetch_a50_pe() -> pd.DataFrame:
    """上证 50 滚动市盈率."""
    return _fetch_index_pe("上证50", "A50_PE")


def fetch_hs300_pe() -> pd.DataFrame:
    """沪深 300 滚动市盈率(akshare 来源,作为辅助参考)."""
    return _fetch_index_pe("沪深300", "HS300_PE")


def fetch_a_full_pe() -> pd.DataFrame:
    """A 股全指 PE-TTM 市值加权 — 理杏仁口径(000985 中证全指)。

    格雷厄姆指数(差值法)主算指标 — 与理杏仁制图工具完全同口径。
    POST https://open.lixinger.com/api/cn/index/fundamental
    metricsList=['pe_ttm.mcw'] · 单次拉 10 年约 2429 行 / 3 秒。
    """
    import sys
    archiver = ROOT / ".tools" / "lixinger-archiver"
    if str(archiver) not in sys.path:
        sys.path.insert(0, str(archiver))
    from lixinger_resolve_token import resolve_lixinger_token
    import requests

    token = resolve_lixinger_token(None)
    if not token:
        raise RuntimeError("理杏仁 token 未找到 — 检查 .config/.lixinger_token 或 credentials.md")

    end_dt = date.today()
    start_dt = end_dt - timedelta(days=365 * 10 + 30)
    payload = {
        "token": token,
        "startDate": start_dt.strftime("%Y-%m-%d"),
        "endDate":   end_dt.strftime("%Y-%m-%d"),
        "stockCodes": ["000985"],   # 中证全指 = 理杏仁"A股全指"
        "metricsList": ["pe_ttm.mcw"],
    }

    def _post():
        r = requests.post("https://open.lixinger.com/api/cn/index/fundamental",
                          json=payload, timeout=60)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 1:
            raise RuntimeError(f"理杏仁 API 错误: {j}")
        return j.get("data") or []

    rows = _retry(_post, attempts=3, sleep=2.0)
    if not rows:
        raise RuntimeError("理杏仁返回空数据(000985 pe_ttm.mcw)")

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_convert("Asia/Shanghai").dt.date
    df["value"] = pd.to_numeric(df["pe_ttm.mcw"], errors="coerce")
    out = df[["date", "value"]].dropna()
    out["indicator"] = "A_FULL_PE"
    out["unit"] = "x"
    out["frequency"] = "D"
    out["source"] = "lixinger"
    return out[["indicator", "date", "value", "unit", "frequency"]]


FETCHERS = {
    "M2_YOY":    fetch_m2_yoy,
    "CPI_YOY":   fetch_cpi_yoy,
    "10Y_YIELD": fetch_10y_yield,
    "USDCNY":    fetch_usdcny,
    "A50_PE":    fetch_a50_pe,
    "HS300_PE":  fetch_hs300_pe,
    "A_FULL_PE": fetch_a_full_pe,
}


# ───── smoke 模式(离线,单元测试用)───────────────────────────────


def smoke_data() -> dict[str, pd.DataFrame]:
    today = date.today()
    out: dict[str, pd.DataFrame] = {}
    for ind, unit, freq, vals in [
        ("M2_YOY",    "%",       "M", [8.4, 8.2, 8.5]),
        ("CPI_YOY",   "%",       "M", [-0.1, 0.1, 0.0]),
        ("10Y_YIELD", "%",       "D", [1.65, 1.68, 1.70]),
        ("USDCNY",    "CNY/USD", "D", [7.20, 7.18, 7.21]),
        ("A50_PE",    "x",       "D", [9.5, 9.7, 9.6]),
        ("HS300_PE",  "x",       "D", [12.5, 12.7, 12.6]),
        ("A_FULL_PE", "x",       "D", [22.5, 23.0, 23.3]),
    ]:
        df = pd.DataFrame({
            "indicator": ind,
            "date": [today - timedelta(days=k * 30) for k in range(len(vals))],
            "value": vals,
            "unit": unit,
            "frequency": freq,
        })
        out[ind] = df
    return out


# ───── 写入 DuckDB ───────────────────────────────────────────────────


def upsert(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = ["indicator", "date", "value", "unit", "frequency"]
    df = df[cols].copy()
    con.register("macro_df", df)
    con.execute(
        "INSERT OR REPLACE INTO macro (indicator, date, value, unit, frequency) "
        "SELECT indicator, date, value, unit, frequency FROM macro_df"
    )
    con.unregister("macro_df")
    return len(df)


# ───── CLI ───────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--only", help="逗号分隔指标 (M2_YOY,CPI_YOY,10Y_YIELD,USDCNY,A50_PE,HS300_PE,A_FULL_PE)")
    ap.add_argument("--smoke", action="store_true", help="离线写假数据(不联网)")
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(DDL)

    if args.only:
        targets = [s.strip() for s in args.only.split(",") if s.strip()]
    else:
        targets = list(FETCHERS.keys())

    print(f"📡 抓取 {len(targets)} 项宏观 → {db_path}")
    if args.smoke:
        print("   (smoke 模式,不联网)")

    rows_total = 0
    failures: list[tuple[str, str]] = []
    for ind in targets:
        if ind not in FETCHERS:
            failures.append((ind, f"未知指标(可选 {list(FETCHERS.keys())})"))
            continue
        try:
            if args.smoke:
                df = smoke_data().get(ind, pd.DataFrame())
            else:
                df = FETCHERS[ind]()
            n = upsert(con, df)
            print(f"   ✅ {ind:<11} {n:>5} 行")
            rows_total += n
        except Exception as e:
            tb = traceback.format_exc().splitlines()[-1]
            failures.append((ind, f"{type(e).__name__}: {e} · {tb}"))
            print(f"   ❌ {ind:<11} {type(e).__name__}: {e}", file=sys.stderr)

    rows_db = con.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
    inds_db = con.execute(
        "SELECT indicator, COUNT(*) FROM macro GROUP BY indicator ORDER BY indicator"
    ).fetchall()
    con.close()

    print(f"\n📊 写入 {rows_total} 行,DB 总计 {rows_db} 行")
    for ind, n in inds_db:
        print(f"   {ind:<11} {n:>6}")

    if failures:
        print(f"\n⚠️  {len(failures)} 项失败:")
        for ind, err in failures:
            print(f"   {ind}: {err}")
        return 1 if rows_total == 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
