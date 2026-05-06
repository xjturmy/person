"""为 15 家自选公司选取「同行业市值更大的 2 家对标」并入库 DuckDB。

流程:
  1. 读 companies(ticker / name)
  2. 用 stock_individual_info_em 取每家的 EM 二级行业 + 总市值
  3. 用 stock_board_industry_cons_em 取该行业全部成分股(含市值)
  4. 选市值 > 本公司的 top 2(不足时补市值最大的 next 2)
  5. 入库 DuckDB peers 表 + 输出 .config/peers.csv 备份

用法:
    .venv/bin/python .tools/db/fetch_peers.py            # 一次性建表
    .venv/bin/python .tools/db/fetch_peers.py --refresh  # 强制刷新(默认就刷新)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "preson.duckdb"           # 仅用于读 companies 表(read-only 不撞锁)
PEERS_DB_PATH = ROOT / "data" / "peers.duckdb"      # 独立写库,与 streamlit 解耦
PEERS_CSV = ROOT / ".config" / "peers.csv"
INDUSTRY_CACHE_CSV = ROOT / ".config" / "companies_industry.csv"


def _info_for(ticker: str, retries: int = 3) -> dict | None:
    """单家公司的行业 + 市值,SSL 偶发失败重试 retries 次。"""
    import akshare as ak
    last_err = None
    for attempt in range(retries):
        try:
            info = ak.stock_individual_info_em(symbol=ticker)
            if info is None or info.empty:
                return None
            kv = dict(zip(info["item"], info["value"]))
            return {
                "ticker": ticker,
                "name": kv.get("股票简称", ""),
                "industry_em": kv.get("行业", ""),
                "total_market_cap": float(kv.get("总市值", 0) or 0),
                "circulating_market_cap": float(kv.get("流通市值", 0) or 0),
            }
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    short_err = str(last_err).split("\n")[0][:80]
    print(f"  ⚠️  {ticker} info 失败({retries} 次重试):{short_err}",
          file=sys.stderr)
    return None


_SPOT_CACHE: pd.DataFrame | None = None


def _all_a_spot() -> pd.DataFrame:
    """一次性拉全 A 股最新行情 + 总市值;之后所有行业 peer 选取走这个表。"""
    global _SPOT_CACHE
    if _SPOT_CACHE is not None:
        return _SPOT_CACHE
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    rename = {
        "代码": "ticker", "名称": "name",
        "总市值": "total_market_cap",
        "流通市值": "circulating_market_cap",
        "市盈率-动态": "pe", "市净率": "pb",
    }
    df = df.rename(columns=rename)
    keep = [c for c in ["ticker", "name", "total_market_cap",
                        "circulating_market_cap", "pe", "pb"]
            if c in df.columns]
    df = df[keep].copy()
    df["total_market_cap"] = pd.to_numeric(df["total_market_cap"],
                                            errors="coerce")
    df = df.dropna(subset=["total_market_cap"]).reset_index(drop=True)
    _SPOT_CACHE = df
    return df


def _industry_constituents(industry_em: str) -> pd.DataFrame:
    """行业成分股 ticker list ⨯ 全 A 快照市值 → 行业内 ticker + 市值表。"""
    import akshare as ak
    try:
        cons = ak.stock_board_industry_cons_em(symbol=industry_em)
        if cons is None or cons.empty:
            return pd.DataFrame()
        cons = cons.rename(columns={"代码": "ticker", "名称": "name"})
        tickers = cons["ticker"].astype(str).tolist()
    except Exception as e:
        print(f"  ⚠️  行业 {industry_em} 成分股 list 失败: {e}", file=sys.stderr)
        return pd.DataFrame()
    spot = _all_a_spot()
    df = spot[spot["ticker"].astype(str).isin(tickers)].copy()
    df = df.sort_values("total_market_cap", ascending=False).reset_index(drop=True)
    return df


def _pick_peers(self_info: dict, peers_df: pd.DataFrame, n: int = 2) -> list[dict]:
    """市值 > 本公司 → 取最近 n 家;不足时补最大的次龙头。"""
    if peers_df.empty:
        return []
    self_t = self_info["ticker"]
    self_mcap = self_info["total_market_cap"] or 0
    df = peers_df[peers_df["ticker"] != self_t].copy()
    if df.empty:
        return []

    above = df[df["total_market_cap"] > self_mcap].sort_values("total_market_cap")
    picked = above.tail(n).copy()
    if len(picked) < n:
        below = df[df["total_market_cap"] <= self_mcap].sort_values(
            "total_market_cap", ascending=False
        ).head(n - len(picked))
        picked = pd.concat([picked, below])
    picked = picked.head(n)

    out = []
    for rank, row in enumerate(picked.itertuples(index=False), start=1):
        d = row._asdict()
        d["rank"] = rank
        d["is_above_self"] = d["total_market_cap"] > self_mcap
        out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2, help="每家选 n 个对标(默认 2)")
    ap.add_argument("--sleep", type=float, default=0.5, help="API 间隔")
    ap.add_argument("--cache-industry", action="store_true",
                    help="只刷新行业映射缓存,不抓成分股")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"❌ DuckDB 不存在: {DB_PATH}", file=sys.stderr)
        return 1

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT ticker, name, category FROM companies ORDER BY folder"
        ).fetchall()
    finally:
        con.close()

    print(f"📋 共 {len(rows)} 家自选公司")

    print("📡 拉每家公司的行业 + 市值 ...")
    self_infos: list[dict] = []
    for t, name, cat in rows:
        if cat == "hk":
            print(f"  ⏭️  {t} {name} 港股,暂跳过(EM 接口不支持)")
            continue
        info = _info_for(t)
        if info:
            info["folder_name"] = name
            info["category"] = cat
            self_infos.append(info)
            print(f"  ✅ {t} {name} 行业={info['industry_em']} "
                  f"市值={info['total_market_cap']/1e8:.0f} 亿")
        else:
            print(f"  ❌ {t} {name} 取不到行业")
        time.sleep(args.sleep)

    PEERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(self_infos).to_csv(INDUSTRY_CACHE_CSV, index=False)
    print(f"💾 行业映射 → {INDUSTRY_CACHE_CSV}")

    if args.cache_industry:
        return 0

    print("📡 抓行业成分股 + 选 peer ...")
    industries_seen: dict[str, pd.DataFrame] = {}
    all_peers: list[dict] = []
    for info in self_infos:
        ind = info["industry_em"]
        if not ind:
            continue
        if ind not in industries_seen:
            industries_seen[ind] = _industry_constituents(ind)
            time.sleep(args.sleep)
        cons = industries_seen[ind]
        peers = _pick_peers(info, cons, n=args.n)
        if not peers:
            print(f"  ⚠️  {info['ticker']} {info['name']} 行业 {ind} 无可用 peer")
            continue
        for p in peers:
            all_peers.append({
                "ticker": info["ticker"],
                "name": info["name"],
                "industry_em": ind,
                "self_market_cap": info["total_market_cap"],
                "rank": p["rank"],
                "peer_ticker": p["ticker"],
                "peer_name": p["name"],
                "peer_market_cap": p["total_market_cap"],
                "peer_pe": p.get("pe"),
                "peer_pb": p.get("pb"),
                "peer_roe": p.get("roe"),
                "is_above_self": p["is_above_self"],
            })
        names = " / ".join(f"{p['name']}({p['total_market_cap']/1e8:.0f}亿"
                           f"{'⬆' if p['is_above_self'] else '⬇'})"
                           for p in peers)
        print(f"  ✅ {info['ticker']} {info['name']} → {names}")

    if not all_peers:
        print("❌ 没产出任何 peer 记录", file=sys.stderr)
        return 1

    df = pd.DataFrame(all_peers)
    df.to_csv(PEERS_CSV, index=False)
    print(f"💾 peer 清单 → {PEERS_CSV} ({len(df)} 行)")

    con = duckdb.connect(str(PEERS_DB_PATH))
    try:
        con.execute("DROP TABLE IF EXISTS peers")
        con.execute("""
            CREATE TABLE peers (
                ticker VARCHAR,
                name VARCHAR,
                industry_em VARCHAR,
                self_market_cap DOUBLE,
                rank INTEGER,
                peer_ticker VARCHAR,
                peer_name VARCHAR,
                peer_market_cap DOUBLE,
                peer_pe DOUBLE,
                peer_pb DOUBLE,
                peer_roe DOUBLE,
                is_above_self BOOLEAN,
                refreshed_at TIMESTAMP DEFAULT now()
            )
        """)
        con.executemany(
            "INSERT INTO peers (ticker, name, industry_em, self_market_cap, rank, "
            "peer_ticker, peer_name, peer_market_cap, peer_pe, peer_pb, peer_roe, "
            "is_above_self) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["ticker"], r["name"], r["industry_em"], r["self_market_cap"],
                 r["rank"], r["peer_ticker"], r["peer_name"], r["peer_market_cap"],
                 r["peer_pe"], r["peer_pb"], r["peer_roe"], r["is_above_self"])
                for r in all_peers
            ],
        )
        n = con.execute("SELECT COUNT(*) FROM peers").fetchone()[0]
        print(f"✅ DuckDB peers 表已写入 {n} 行")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
