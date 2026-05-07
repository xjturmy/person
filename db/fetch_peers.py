"""为 15 家自选公司选取「同行业 N 家对标」并入库 DuckDB,含多维基本面 + PEG + F-Score lite。

流程:
  1. 读 companies(ticker / name)
  2. 用 stock_individual_info_em 取每家的 EM 二级行业 + 总市值
  3. 用 stock_board_industry_cons_em 取该行业全部成分股(含市值)
  4. 选市值 > 本公司的 top n(不足时补市值最大的 next n)
  5. 对每个 unique peer(含 self)调 stock_financial_abstract 抓 ROE / 毛利率 / YoY / 3y CAGR / F-Score lite
  6. 入库 DuckDB peers 表 + 输出 .config/peers.csv 备份

用法:
    .venv/bin/python .tools/db/fetch_peers.py            # 默认 n=6,完整流程
    .venv/bin/python .tools/db/fetch_peers.py --n 8      # 每家 8 个对标
    .venv/bin/python .tools/db/fetch_peers.py --skip-fundamentals  # 仅刷行业 + 市值,不抓基本面
"""
from __future__ import annotations

import argparse
import math
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


_INDUSTRY_CACHE_DICT: dict[str, dict] | None = None


def _load_industry_cache() -> dict[str, dict]:
    """读 .config/companies_industry.csv 缓存,EM API 挂时兜底。"""
    global _INDUSTRY_CACHE_DICT
    if _INDUSTRY_CACHE_DICT is not None:
        return _INDUSTRY_CACHE_DICT
    if not INDUSTRY_CACHE_CSV.exists():
        _INDUSTRY_CACHE_DICT = {}
        return _INDUSTRY_CACHE_DICT
    df = pd.read_csv(INDUSTRY_CACHE_CSV, dtype={"ticker": str})
    out: dict[str, dict] = {}
    for r in df.itertuples(index=False):
        d = r._asdict()
        out[str(d["ticker"]).zfill(6)] = d
    _INDUSTRY_CACHE_DICT = out
    return out


def _info_for(ticker: str, retries: int = 1) -> dict | None:
    """单家公司的行业 + 市值,SSL 偶发失败重试 retries 次,失败时回退到缓存。"""
    import akshare as ak
    last_err = None
    for attempt in range(retries):
        try:
            info = ak.stock_individual_info_em(symbol=ticker)
            if info is None or info.empty:
                break
            kv = dict(zip(info["item"], info["value"]))
            return {
                "ticker": ticker,
                "name": kv.get("股票简称", ""),
                "industry_em": kv.get("行业", ""),
                "total_market_cap": float(kv.get("总市值", 0) or 0),
                "circulating_market_cap": float(kv.get("流通市值", 0) or 0),
                "_source": "em",
            }
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))

    cache = _load_industry_cache().get(ticker)
    if cache:
        return {
            "ticker": ticker,
            "name": cache.get("name", ""),
            "industry_em": cache.get("industry_em", ""),
            "total_market_cap": float(cache.get("total_market_cap") or 0),
            "circulating_market_cap": float(cache.get("circulating_market_cap") or 0),
            "_source": "cache",
        }
    short_err = str(last_err).split("\n")[0][:80] if last_err else "empty"
    print(f"  ⚠️  {ticker} info 失败({retries} 次重试)+ 无缓存:{short_err}",
          file=sys.stderr)
    return None


_SPOT_CACHE: pd.DataFrame | None = None


def _all_a_spot() -> pd.DataFrame:
    """一次性拉全 A 股最新行情 + 总市值;失败返回空 DF(EM push2 端点偶尔挂)。"""
    global _SPOT_CACHE
    if _SPOT_CACHE is not None:
        return _SPOT_CACHE
    import akshare as ak
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        short = str(e).split("\n")[0][:80]
        print(f"  ⚠️  全 A 股快照失败:{short}(下游 PE/PEG 将不可用)",
              file=sys.stderr)
        _SPOT_CACHE = pd.DataFrame(columns=["ticker", "name", "total_market_cap",
                                              "circulating_market_cap", "pe", "pb"])
        return _SPOT_CACHE
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


def _industry_constituents(industry_em: str, retries: int = 1) -> pd.DataFrame:
    """行业成分股 ticker list ⨯ 全 A 快照市值 → 行业内 ticker + 市值表。"""
    import akshare as ak
    last_err = None
    cons = None
    for attempt in range(retries):
        try:
            cons = ak.stock_board_industry_cons_em(symbol=industry_em)
            if cons is None or cons.empty:
                cons = None
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    if cons is None:
        short = str(last_err).split("\n")[0][:80] if last_err else "empty"
        print(f"  ⚠️  行业 {industry_em} 成分股 list 失败({retries} 次):{short}",
              file=sys.stderr)
        return pd.DataFrame()
    cons = cons.rename(columns={"代码": "ticker", "名称": "name"})
    tickers = cons["ticker"].astype(str).tolist()
    spot = _all_a_spot()
    df = spot[spot["ticker"].astype(str).isin(tickers)].copy()
    df = df.sort_values("total_market_cap", ascending=False).reset_index(drop=True)
    return df


def _pick_peers(self_info: dict, peers_df: pd.DataFrame, n: int = 6) -> list[dict]:
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


# ─────────────────────────────────────────────────────────────────────────
# Phase A2/A3/A4 · 基本面同步 + PEG + F-Score lite
# ─────────────────────────────────────────────────────────────────────────

_FUND_CACHE: dict[str, dict] = {}

# 常用指标行 → 标准化字段名
_INDICATOR_MAP = {
    "归母净利润": "ni",
    "营业总收入": "revenue",
    "经营现金流量净额": "cfo",
    "净资产收益率(ROE)": "roe",
    "毛利率": "gross_margin",
    "营业总收入增长率": "revenue_yoy",
    "归属母公司净利润增长率": "ni_yoy",
}


def _fundamentals_for(ticker: str, pe_ttm: float | None,
                       retries: int = 2) -> dict:
    """
    抓单家公司基本面(最近年报口径)+ 衍生 PEG / F-Score lite。

    返回 dict:
      roe, gross_margin, revenue_yoy, ni_yoy(均来自最近年报)
      peg          = pe_ttm / (3y NI CAGR × 100)
      fscore_lite  = 0-4(NI>0, CFO>0, ROE↑, Revenue↑)
      latest_year  = 最近年报的 4 位年份字符串
      verified     = True/False(数据是否完整)

    缓存:_FUND_CACHE 按 ticker 去重,避免同行交叉重复抓取。
    """
    if ticker in _FUND_CACHE:
        cached = dict(_FUND_CACHE[ticker])
        cached["pe_ttm"] = pe_ttm
        # PEG 依赖 pe_ttm,需重算
        cached["peg"] = _calc_peg(pe_ttm, cached.get("ni_3y_cagr"))
        return cached

    import akshare as ak
    last_err = None
    df = None
    for attempt in range(retries):
        try:
            df = ak.stock_financial_abstract(symbol=ticker)
            if df is None or df.empty:
                df = None
            break
        except Exception as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))

    if df is None:
        short = str(last_err).split("\n")[0][:60] if last_err else "empty"
        print(f"  ⚠️  {ticker} 基本面失败:{short}", file=sys.stderr)
        out = {"roe": None, "gross_margin": None, "revenue_yoy": None,
               "ni_yoy": None, "peg": None, "fscore_lite": None,
               "latest_year": None, "verified": False, "pe_ttm": pe_ttm,
               "ni_3y_cagr": None}
        _FUND_CACHE[ticker] = dict(out)
        return out

    annual_cols = sorted(
        [c for c in df.columns if isinstance(c, str) and c.endswith("1231")
         and len(c) == 8 and c[:4].isdigit()],
        reverse=True,
    )
    # 只看 "常用指标" 选项,避免 ROE 在多个 section 同名造成歧义
    common = df[df["选项"] == "常用指标"]
    growth = df[df["选项"] == "成长能力"]

    def _row(src: pd.DataFrame, name: str) -> pd.Series | None:
        sub = src[src["指标"] == name]
        return sub.iloc[0] if len(sub) else None

    def _val(row: pd.Series | None, col: str) -> float | None:
        if row is None or col not in row.index:
            return None
        v = row[col]
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (TypeError, ValueError):
            return None

    if not annual_cols:
        out = {"roe": None, "gross_margin": None, "revenue_yoy": None,
               "ni_yoy": None, "peg": None, "fscore_lite": None,
               "latest_year": None, "verified": False, "pe_ttm": pe_ttm,
               "ni_3y_cagr": None}
        _FUND_CACHE[ticker] = dict(out)
        return out

    latest_col = annual_cols[0]
    prev_col = annual_cols[1] if len(annual_cols) > 1 else None
    cagr_end_col = latest_col
    cagr_start_col = annual_cols[3] if len(annual_cols) > 3 else None

    roe = _val(_row(common, "净资产收益率(ROE)"), latest_col)
    gross_margin = _val(_row(common, "毛利率"), latest_col)
    revenue_yoy = _val(_row(growth, "营业总收入增长率"), latest_col)
    ni_yoy = _val(_row(growth, "归属母公司净利润增长率"), latest_col)

    # 3y CAGR(归母净利润)
    ni_row = _row(common, "归母净利润")
    ni_latest = _val(ni_row, cagr_end_col)
    ni_3y_ago = _val(ni_row, cagr_start_col) if cagr_start_col else None
    ni_3y_cagr = None
    if ni_latest and ni_3y_ago and ni_3y_ago > 0 and ni_latest > 0:
        ni_3y_cagr = (ni_latest / ni_3y_ago) ** (1 / 3) - 1

    peg = _calc_peg(pe_ttm, ni_3y_cagr)

    # F-Score lite(4 规则)
    fs_pass = 0
    fs_total = 0
    # rule 1: NI > 0
    if ni_latest is not None:
        fs_total += 1
        if ni_latest > 0:
            fs_pass += 1
    # rule 2: CFO > 0
    cfo_latest = _val(_row(common, "经营现金流量净额"), latest_col)
    if cfo_latest is not None:
        fs_total += 1
        if cfo_latest > 0:
            fs_pass += 1
    # rule 3: ROE 同比上升
    roe_prev = _val(_row(common, "净资产收益率(ROE)"), prev_col) if prev_col else None
    if roe is not None and roe_prev is not None:
        fs_total += 1
        if roe > roe_prev:
            fs_pass += 1
    # rule 4: 营收 同比上升
    rev_latest = _val(_row(common, "营业总收入"), latest_col)
    rev_prev = _val(_row(common, "营业总收入"), prev_col) if prev_col else None
    if rev_latest is not None and rev_prev is not None:
        fs_total += 1
        if rev_latest > rev_prev:
            fs_pass += 1

    fscore_lite = fs_pass if fs_total >= 3 else None

    out = {
        "roe": roe,
        "gross_margin": gross_margin,
        "revenue_yoy": revenue_yoy,
        "ni_yoy": ni_yoy,
        "ni_3y_cagr": ni_3y_cagr,
        "peg": peg,
        "fscore_lite": fscore_lite,
        "latest_year": latest_col[:4],
        "verified": all(x is not None for x in [roe, gross_margin, revenue_yoy, ni_yoy]),
        "pe_ttm": pe_ttm,
    }
    _FUND_CACHE[ticker] = dict(out)
    return out


def _calc_peg(pe_ttm: float | None, ni_3y_cagr: float | None) -> float | None:
    """理杏仁口径:PE-TTM ÷ (3y NI CAGR × 100)。负增长返回 None。"""
    if pe_ttm is None or ni_3y_cagr is None:
        return None
    if pe_ttm <= 0 or ni_3y_cagr <= 0:
        return None
    return pe_ttm / (ni_3y_cagr * 100)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="每家选 n 个对标(默认 6)")
    ap.add_argument("--sleep", type=float, default=0.4, help="API 间隔")
    ap.add_argument("--cache-industry", action="store_true",
                    help="只刷新行业映射缓存,不抓成分股")
    ap.add_argument("--skip-fundamentals", action="store_true",
                    help="跳过基本面 + PEG + F-Score 抓取(仅市值/PE/PB 快照)")
    ap.add_argument("--use-cached-peers", action="store_true",
                    help="跳过 EM 行业成分股抓取,直接用 .config/peers.csv 老 peer 清单(EM push2 端点挂时使用)")
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

    self_infos: list[dict] = []
    if args.use_cached_peers:
        print("📂 --use-cached-peers · 跳过 EM 行业接口,从缓存读 self info")
        cache = _load_industry_cache()
        for t, name, cat in rows:
            if cat == "hk":
                print(f"  ⏭️  {t} {name} 港股,暂跳过")
                continue
            c = cache.get(t)
            if not c:
                print(f"  ⚠️  {t} {name} 缓存缺失,跳过")
                continue
            self_infos.append({
                "ticker": t,
                "name": c.get("name", name),
                "industry_em": c.get("industry_em", ""),
                "total_market_cap": float(c.get("total_market_cap") or 0),
                "circulating_market_cap": float(c.get("circulating_market_cap") or 0),
                "folder_name": name,
                "category": cat,
                "_source": "cache",
            })
            print(f"  📂 {t} {name} 行业={c.get('industry_em')} "
                  f"市值={float(c.get('total_market_cap') or 0)/1e8:.0f} 亿(缓存)")
    else:
        print("📡 拉每家公司的行业 + 市值 ...")
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
    fresh = [info for info in self_infos if info.get("_source") == "em"]
    fresh_ratio = len(fresh) / max(len(self_infos), 1)
    if fresh_ratio >= 0.8:
        pd.DataFrame([{k: v for k, v in info.items() if not k.startswith("_")}
                      for info in self_infos]).to_csv(INDUSTRY_CACHE_CSV, index=False)
        print(f"💾 行业映射 → {INDUSTRY_CACHE_CSV} (fresh={len(fresh)}/{len(self_infos)})")
    else:
        print(f"⏭️  行业映射缓存保留(fresh={len(fresh)}/{len(self_infos)} < 80%)")

    if args.cache_industry:
        return 0

    all_peers: list[dict] = []

    if args.use_cached_peers:
        print(f"⏭️  --use-cached-peers · 跳过 EM 行业成分股,直接读 {PEERS_CSV}")
    else:
        print(f"📡 抓行业成分股 + 选 peer (n={args.n}) ...")
        industries_seen: dict[str, pd.DataFrame] = {}
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
                    "is_above_self": p["is_above_self"],
                })
            names = " / ".join(f"{p['name']}({p['total_market_cap']/1e8:.0f}亿"
                               f"{'⬆' if p['is_above_self'] else '⬇'})"
                               for p in peers[:3])
            suffix = f" 等 {len(peers)} 家" if len(peers) > 3 else ""
            print(f"  ✅ {info['ticker']} {info['name']} → {names}{suffix}")

    if not all_peers and PEERS_CSV.exists():
        print("⚠️  EM 成分股全失败,回退读 .config/peers.csv 老 peer 清单",
              file=sys.stderr)
        try:
            old = pd.read_csv(PEERS_CSV, dtype={
                "ticker": str, "peer_ticker": str,
            })
            for r in old.itertuples(index=False):
                d = r._asdict()
                # 只保留有效字段,新基本面列稍后填
                all_peers.append({
                    "ticker": str(d["ticker"]).zfill(6),
                    "name": d.get("name", ""),
                    "industry_em": d.get("industry_em", ""),
                    "self_market_cap": float(d.get("self_market_cap") or 0),
                    "rank": int(d.get("rank") or 0),
                    "peer_ticker": str(d["peer_ticker"]).zfill(6),
                    "peer_name": d.get("peer_name", ""),
                    "peer_market_cap": float(d.get("peer_market_cap") or 0),
                    "peer_pe": float(d["peer_pe"]) if pd.notna(d.get("peer_pe")) else None,
                    "peer_pb": float(d["peer_pb"]) if pd.notna(d.get("peer_pb")) else None,
                    "is_above_self": bool(d.get("is_above_self")),
                })
            print(f"  ✅ 回退加载 {len(all_peers)} 行老 peer", file=sys.stderr)
        except Exception as e:
            print(f"  ❌ 回退也失败:{e}", file=sys.stderr)

    if not all_peers:
        print("❌ 没产出任何 peer 记录(EM 全挂 + 缓存空)", file=sys.stderr)
        return 1

    # ── A2/A3/A4 · 基本面 + PEG + F-Score lite ──
    if not args.skip_fundamentals:
        unique_tickers = sorted({r["peer_ticker"] for r in all_peers}
                                 | {r["ticker"] for r in all_peers})
        print(f"📡 抓基本面(unique={len(unique_tickers)} 家,~{len(unique_tickers)*args.sleep:.0f}s)...")

        # 构建 ticker → PE 映射:优先 all_peers 中的 peer_pe(来自 spot 或 csv),
        # 不命中再走 _all_a_spot。--use-cached-peers 时跳过 spot 整体调用(58 页太慢)。
        pe_map: dict[str, float | None] = {}
        for r in all_peers:
            if r.get("peer_pe") is not None:
                pe_map[str(r["peer_ticker"]).zfill(6)] = r["peer_pe"]

        if not args.use_cached_peers:
            try:
                spot = _all_a_spot()
                if "pe" in spot.columns and not spot.empty:
                    for t, pe in zip(spot["ticker"], spot["pe"]):
                        key = str(t).zfill(6)
                        if key not in pe_map and pe is not None:
                            pe_map[key] = pe
            except Exception as e:
                print(f"  ⚠️  spot 拉取失败,PEG 仅依赖 csv 内 PE:{str(e)[:60]}",
                      file=sys.stderr)
        # valuation 表兜底:为 self 公司补 PE-TTM(spot 拉不到时)
        try:
            _vcon = duckdb.connect(str(DB_PATH), read_only=True)
            try:
                _vdf = _vcon.execute("""
                    SELECT v.ticker, v.value
                    FROM valuation v
                    INNER JOIN (
                        SELECT ticker, MAX(date) AS mdate FROM valuation
                        WHERE metric = 'PE-TTM' GROUP BY ticker
                    ) m ON v.ticker = m.ticker AND v.metric = 'PE-TTM' AND v.date = m.mdate
                """).df()
            finally:
                _vcon.close()
            for _, row in _vdf.iterrows():
                key = str(row["ticker"]).zfill(6)
                if key not in pe_map:
                    pe_map[key] = float(row["value"])
        except Exception as _e:
            pass
        print(f"  📊 PE map 覆盖 {len(pe_map)}/{len(unique_tickers)} 家(其余 PEG 为空)")

        for i, t in enumerate(unique_tickers, 1):
            pe = pe_map.get(str(t))
            try:
                fund = _fundamentals_for(str(t), pe)
                tag = "✅" if fund["verified"] else "⚠️"
                roe_s = f"{fund['roe']:.1f}" if fund["roe"] is not None else "—"
                gm_s = f"{fund['gross_margin']:.1f}" if fund["gross_margin"] is not None else "—"
                peg_s = f"{fund['peg']:.2f}" if fund["peg"] is not None else "—"
                fs_s = str(fund["fscore_lite"]) if fund["fscore_lite"] is not None else "—"
                print(f"  {tag} [{i}/{len(unique_tickers)}] {t}  "
                      f"ROE={roe_s} GM={gm_s} PEG={peg_s} F={fs_s}/4")
            except Exception as e:
                print(f"  ❌ [{i}/{len(unique_tickers)}] {t}: {str(e)[:60]}",
                      file=sys.stderr)
            time.sleep(args.sleep)

        # 把基本面挂到每行
        for r in all_peers:
            fund = _FUND_CACHE.get(r["peer_ticker"], {})
            r["peer_roe"] = fund.get("roe")
            r["peer_gross_margin"] = fund.get("gross_margin")
            r["peer_revenue_yoy"] = fund.get("revenue_yoy")
            r["peer_ni_yoy"] = fund.get("ni_yoy")
            r["peer_peg"] = fund.get("peg")
            r["peer_fscore_lite"] = fund.get("fscore_lite")
            r["peer_latest_year"] = fund.get("latest_year")
    else:
        for r in all_peers:
            r["peer_roe"] = None
            r["peer_gross_margin"] = None
            r["peer_revenue_yoy"] = None
            r["peer_ni_yoy"] = None
            r["peer_peg"] = None
            r["peer_fscore_lite"] = None
            r["peer_latest_year"] = None

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
                peer_gross_margin DOUBLE,
                peer_revenue_yoy DOUBLE,
                peer_ni_yoy DOUBLE,
                peer_peg DOUBLE,
                peer_fscore_lite INTEGER,
                peer_latest_year VARCHAR,
                is_above_self BOOLEAN,
                refreshed_at TIMESTAMP DEFAULT now()
            )
        """)
        con.executemany(
            "INSERT INTO peers (ticker, name, industry_em, self_market_cap, rank, "
            "peer_ticker, peer_name, peer_market_cap, peer_pe, peer_pb, peer_roe, "
            "peer_gross_margin, peer_revenue_yoy, peer_ni_yoy, peer_peg, "
            "peer_fscore_lite, peer_latest_year, is_above_self) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["ticker"], r["name"], r["industry_em"], r["self_market_cap"],
                 r["rank"], r["peer_ticker"], r["peer_name"], r["peer_market_cap"],
                 r["peer_pe"], r["peer_pb"], r["peer_roe"],
                 r["peer_gross_margin"], r["peer_revenue_yoy"], r["peer_ni_yoy"],
                 r["peer_peg"], r["peer_fscore_lite"], r["peer_latest_year"],
                 r["is_above_self"])
                for r in all_peers
            ],
        )
        n = con.execute("SELECT COUNT(*) FROM peers").fetchone()[0]
        nonnull = con.execute(
            "SELECT COUNT(*) FROM peers WHERE peer_roe IS NOT NULL"
        ).fetchone()[0]
        print(f"✅ DuckDB peers 表已写入 {n} 行(ROE 非空 {nonnull})")

        # ── self_metrics 表 · 自家公司基本面 ──
        self_tickers = sorted({r["ticker"] for r in all_peers})
        con.execute("DROP TABLE IF EXISTS self_metrics")
        con.execute("""
            CREATE TABLE self_metrics (
                ticker VARCHAR PRIMARY KEY,
                name VARCHAR,
                industry_em VARCHAR,
                market_cap DOUBLE,
                pe DOUBLE,
                pb DOUBLE,
                roe DOUBLE,
                gross_margin DOUBLE,
                revenue_yoy DOUBLE,
                ni_yoy DOUBLE,
                peg DOUBLE,
                fscore_lite INTEGER,
                latest_year VARCHAR,
                refreshed_at TIMESTAMP DEFAULT now()
            )
        """)
        # 把 self 信息聚合(从 all_peers 取行业/市值,从 _FUND_CACHE 取基本面)
        self_info_map = {r["ticker"]: r for r in all_peers}
        # self 的 PE/PB:三层兜底
        # 1) 从 self 在他人 peer_ticker 出现的行 lookup(精度最高,实时 spot 来源)
        # 2) 从 spot 全 A 快照(--use-cached-peers 时跳过)
        # 3) 从 preson.duckdb / valuation 表最新行 lookup(权威 + 落地数据)
        self_pe_pb: dict[str, dict] = {}
        for r in all_peers:
            pt = str(r.get("peer_ticker") or "").zfill(6)
            if pt and r.get("peer_pe") is not None and pt not in self_pe_pb:
                self_pe_pb[pt] = {"pe": r.get("peer_pe"), "pb": r.get("peer_pb")}
        spot_map: dict[str, dict] = {}
        if not args.use_cached_peers and _SPOT_CACHE is not None and not _SPOT_CACHE.empty:
            spot_rows = _SPOT_CACHE
            spot_map = {str(t).zfill(6): {"pe": pe, "pb": pb}
                         for t, pe, pb in zip(spot_rows.get("ticker", []),
                                                spot_rows.get("pe", []),
                                                spot_rows.get("pb", []))}
        # valuation 表兜底(从 preson.duckdb 读 PE-TTM + PB 最新值)
        valuation_map: dict[str, dict] = {}
        try:
            vcon = duckdb.connect(str(DB_PATH), read_only=True)
            try:
                vdf = vcon.execute("""
                    SELECT v.ticker, v.metric, v.value
                    FROM valuation v
                    INNER JOIN (
                        SELECT ticker, metric, MAX(date) AS mdate
                        FROM valuation
                        WHERE metric IN ('PE-TTM', 'PB')
                        GROUP BY ticker, metric
                    ) m ON v.ticker = m.ticker AND v.metric = m.metric AND v.date = m.mdate
                """).df()
            finally:
                vcon.close()
            for _, row in vdf.iterrows():
                key = str(row["ticker"]).zfill(6)
                if key not in valuation_map:
                    valuation_map[key] = {}
                col = "pe" if row["metric"] == "PE-TTM" else "pb"
                valuation_map[key][col] = float(row["value"])
        except Exception as e:
            print(f"  ⚠️  valuation 兜底加载失败:{str(e)[:60]}", file=sys.stderr)
        rows_self = []
        for t in self_tickers:
            base = self_info_map.get(t, {})
            fund = _FUND_CACHE.get(t, {})
            tk = str(t).zfill(6)
            pe_pb = self_pe_pb.get(tk) or spot_map.get(tk, {}) or valuation_map.get(tk, {})
            rows_self.append((
                t, base.get("name", ""), base.get("industry_em", ""),
                base.get("self_market_cap"),
                pe_pb.get("pe"), pe_pb.get("pb"),
                fund.get("roe"), fund.get("gross_margin"),
                fund.get("revenue_yoy"), fund.get("ni_yoy"),
                fund.get("peg"), fund.get("fscore_lite"),
                fund.get("latest_year"),
            ))
        if rows_self:
            con.executemany(
                "INSERT INTO self_metrics (ticker, name, industry_em, market_cap, "
                "pe, pb, roe, gross_margin, revenue_yoy, ni_yoy, peg, "
                "fscore_lite, latest_year) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows_self,
            )
            ns = con.execute("SELECT COUNT(*) FROM self_metrics").fetchone()[0]
            print(f"✅ DuckDB self_metrics 表已写入 {ns} 行")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
