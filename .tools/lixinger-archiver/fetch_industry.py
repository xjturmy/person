"""抓取理杏仁公司行业分类(国证 cni + 申万旧 sw + 申万 2021 sw_2021)。

接口:
  POST https://open.lixinger.com/api/cn/company/industries  (A 股)
  POST https://open.lixinger.com/api/hk/company/industries  (港股)
  body: {"token": "...", "stockCode": "600519"}
  ⚠️ 单数 stockCode,每股票一次调用;且必须 Accept-Encoding: gzip。

response.data 形如:
  [{"areaCode":"cn","stockCode":"C050302","source":"cni","name":"饮料"},        # cni L3
   {"areaCode":"cn","stockCode":"C0503","source":"cni","name":"食品饮料与烟草"},  # cni L2
   {"areaCode":"cn","stockCode":"C05","source":"cni","name":"主要消费"},          # cni L1
   {"areaCode":"cn","stockCode":"340000","source":"sw","name":"食品饮料"},        # sw L1
   {"areaCode":"cn","stockCode":"340300","source":"sw","name":"饮料制造"},        # sw L2
   {"areaCode":"cn","stockCode":"340301","source":"sw","name":"白酒"},            # sw L3
   ...]

层级判断:
  - cni:  code 长度 2/4/7 → L1/L2/L3
  - sw / sw_2021:  6 位代码,末 4 位 "0000"=L1,末 2 位 "00"=L2,否则 L3

输出 .config/companies_industry.csv,扁平宽表;并把 sw_2021_l1_name 回填到 companies.csv 新列 industry。

用法:
  .venv/bin/python .tools/lixinger-archiver/fetch_industry.py
  .venv/bin/python .tools/lixinger-archiver/fetch_industry.py --only 600519,000333
  .venv/bin/python .tools/lixinger-archiver/fetch_industry.py --no-write-companies-csv
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "lixinger-archiver"))
from lixinger_resolve_token import resolve_lixinger_token  # noqa: E402

COMPANIES_CSV = ROOT / ".config" / "companies.csv"
OUT_CSV = ROOT / ".config" / "companies_industry.csv"
ENDPOINT = {
    "cn": "https://open.lixinger.com/api/cn/company/industries",
    "hk": "https://open.lixinger.com/api/hk/company/industries",
}
SOURCES = ("cni", "sw", "sw_2021")


def _post(url: str, payload: dict, timeout: int = 30, retries: int = 4) -> dict:
    """理杏仁 API 调用:requests + 指数退避重试,显式 gzip header。"""
    import requests
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Encoding": "gzip",
        "User-Agent": "preson-archiver/1.0",
    }
    last_exc: Exception | None = None
    for i in range(retries):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_exc = e
            wait = 2 ** i  # 1, 2, 4, 8 秒
            print(f"    重试 {i+1}/{retries} (等 {wait}s) — {type(e).__name__}")
            time.sleep(wait)
        except requests.exceptions.HTTPError as e:
            # HTTP 错误不重试
            raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
    raise RuntimeError(f"4 次重试后仍失败:{last_exc}")


def _level_for(source: str, code: str) -> int | None:
    """根据 source + code 反推 level (1/2/3)。"""
    code = (code or "").strip()
    if not code:
        return None
    if source == "cni":
        return {2: 1, 4: 2, 7: 3}.get(len(code))
    if source in ("sw", "sw_2021"):
        if len(code) != 6 or not code.isdigit():
            return None
        if code.endswith("0000"):
            return 1
        if code.endswith("00"):
            return 2
        return 3
    return None


def _flatten(records: list[dict]) -> dict[str, str]:
    """records → 扁平字典:{cni_l1_code, cni_l1_name, sw_l1_code, ..., sw_2021_l1_code, ...}"""
    out: dict[str, str] = {}
    for r in records or []:
        src = (r.get("source") or "").lower()
        if src not in SOURCES:
            continue
        code = r.get("stockCode") or ""
        name = r.get("name") or ""
        lvl = _level_for(src, code)
        if lvl is None:
            continue
        # source 名做下规范化以适配列名
        col_src = src.replace("-", "_")
        out[f"{col_src}_l{lvl}_code"] = code
        out[f"{col_src}_l{lvl}_name"] = name
    return out


def fetch_one(token: str, market: str, ticker: str) -> tuple[list[dict], str | None]:
    """返回 (records, error_msg)。出错时 records 为 [],error 非 None。"""
    url = ENDPOINT[market]
    try:
        resp = _post(url, {"token": token, "stockCode": ticker})
    except Exception as e:
        return [], str(e)[:200]
    if resp.get("code") not in (0, 1):
        return [], f"API err code={resp.get('code')} msg={resp.get('message')}"
    return resp.get("data") or [], None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=None)
    ap.add_argument("--only", default=None, help="逗号分隔 ticker")
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--no-write-companies-csv", action="store_true",
                    help="不回填 companies.csv 的 industry 列")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="每次调用间隔秒数(避免 API 限流)")
    args = ap.parse_args()

    token = resolve_lixinger_token(args.token)
    if not token:
        print("❌ 找不到理杏仁 token", file=sys.stderr)
        return 2

    df = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
    df = df.rename(columns={"stock": "ticker"})

    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        df = df[df["ticker"].isin(wanted)].reset_index(drop=True)

    def _market(row) -> str:
        return "hk" if str(row.get("category", "")).lower() == "hk" else "cn"
    df["market"] = df.apply(_market, axis=1)

    print(f"待抓 {len(df)} 家(A 股 {sum(df['market']=='cn')} / 港股 {sum(df['market']=='hk')})")

    rows: list[dict] = []
    errors: list[tuple[str, str, str]] = []

    for i, r in df.iterrows():
        ticker = str(r["ticker"])
        name = str(r["name"])
        market = str(r["market"])
        records, err = fetch_one(token, market, ticker)
        flat = _flatten(records)
        row: dict[str, Any] = {
            "ticker": ticker, "name": name, "market": market,
            "category": str(r.get("category", "")),
            "raw_n": len(records),
            "fetched_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        }
        row.update(flat)
        rows.append(row)
        if err:
            errors.append((ticker, name, err))
            print(f"  ❌ {ticker} {name}: {err}")
        else:
            short = (
                flat.get("sw_2021_l1_name")
                or flat.get("sw_l1_name")
                or flat.get("cni_l1_name") or "—"
            )
            print(f"  ✅ {ticker} {name}: {len(records)} entries · 申万一级={short}")
        time.sleep(args.sleep)

    out_df = pd.DataFrame(rows)
    # 列顺序:基础字段 → 三种 source × 三级 = 18 列
    base_cols = ["ticker", "name", "market", "category", "raw_n", "fetched_at"]
    detail_cols = []
    for s in SOURCES:
        s_norm = s.replace("-", "_")
        for lvl in (1, 2, 3):
            for k in ("code", "name"):
                detail_cols.append(f"{s_norm}_l{lvl}_{k}")
    cols_order = base_cols + [c for c in detail_cols if c in out_df.columns]
    cols_order += [c for c in out_df.columns if c not in cols_order]
    out_df = out_df.reindex(columns=cols_order)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n📄 写入 {out_path} ({len(out_df)} 行)")

    preview = out_df[[c for c in (
        "ticker", "name", "sw_2021_l1_name", "sw_2021_l2_name",
        "sw_l1_name", "cni_l1_name") if c in out_df.columns]]
    print("\n抓取结果预览(申万 2021 / 申万旧 / 国证 一级):")
    print(preview.to_string(index=False))

    if errors:
        print(f"\n⚠️ 失败 {len(errors)} 家:")
        for t, n, e in errors:
            print(f"  - {t} {n}: {e}")

    # 回填 companies.csv:加 industry 列(用申万 2021 一级最权威)
    if not args.no_write_companies_csv:
        comp = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
        merged = comp.merge(
            out_df[["ticker", "sw_2021_l1_name", "sw_2021_l2_name", "sw_l1_name"]]
                .rename(columns={"ticker": "stock"}),
            on="stock", how="left",
        )
        # 取首选可用值
        merged["industry"] = merged["sw_2021_l1_name"].fillna(
            merged["sw_l1_name"]).fillna("")
        merged["industry_l2"] = merged["sw_2021_l2_name"].fillna("")
        keep_cols = ["folder", "stock", "name", "category", "industry", "industry_l2"]
        merged = merged[keep_cols]
        merged.to_csv(COMPANIES_CSV, index=False, encoding="utf-8")
        print(f"\n📝 回填 {COMPANIES_CSV}(新增 industry / industry_l2 列)")
        print(merged.to_string(index=False))

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
