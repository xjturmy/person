#!/usr/bin/env python3
"""
批量更新公司档案库 02-05 模块（盈利/成长/现金流/安全性）。

数据来源：
- 理杏仁财报接口：/api/cn/company/fs/{category}
- category: non_financial / bank / security / insurance / other_financial

companies.csv 支持两种表头：
1) folder,stock,name
2) folder,stock,name,category
未提供 category 时默认使用 non_financial。
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from lixinger_csv_to_md import write_md_sidecar
from lixinger_resolve_token import resolve_lixinger_token


API_BASE_CN = "https://open.lixinger.com/api/cn/company/fs"
API_BASE_HK = "https://open.lixinger.com/api/hk/company/fs"


def api_base_for(category: str) -> str:
    """港股走 /api/hk/,A 股 / 金融业走 /api/cn/."""
    return API_BASE_HK if category == "hk" else API_BASE_CN


# 兼容旧导入(若有)
API_BASE = API_BASE_CN

# 各行业分类中理杏仁不支持的指标（API 会返回 400 ValidationError）
_FINANCIAL_EXCLUDED = {"q.m.gp_m.ttm", "q.m.lwi_ta_r.t", "q.m.c_r.t", "q.m.q_r.t"}

# BS 字段(q.bs.*) 与 ROIC 在 fs/non_financial 端点验证有效
# fs/bank、fs/insurance、fs/hk 端点字段命名不同(hk 5xx,金融业 400),需走 P3 单独路径
_NEW_P2_FIELDS = {
    "q.bs.ta.t", "q.bs.tl.t", "q.bs.toe.t",
    "q.bs.ca.t", "q.bs.cl.t", "q.bs.ltl.t",
    "q.bs.mc.t", "q.bs.ar.t",
    "q.m.roic.ttm",
}
CATEGORY_EXCLUDED_METRICS: dict[str, set[str]] = {
    "insurance": _FINANCIAL_EXCLUDED | _NEW_P2_FIELDS,
    "bank": _FINANCIAL_EXCLUDED | _NEW_P2_FIELDS,
    "security": _FINANCIAL_EXCLUDED | _NEW_P2_FIELDS,
    "other_financial": _FINANCIAL_EXCLUDED | _NEW_P2_FIELDS,
    # 港股 /api/hk/non_financial:支持 19 字段;不支持以下 6 项(2026-05-06 实测)
    "hk": {
        "q.m.roic.ttm", "q.m.fcf.ttm", "q.m.lwi_ta_r.t", "q.m.q_r.t",
        "q.bs.ca.t", "q.bs.cl.t", "q.bs.mc.t", "q.bs.ar.t",
    },
}


@dataclass(frozen=True)
class Company:
    folder: str
    stock: str
    name: str
    category: str


def normalize_stock_code(raw: str, category: str) -> str:
    """理杏仁接口要求 A 股 6 位、港股 5 位代码。"""
    s = str(raw).strip()
    if not s.isdigit():
        return s
    if category == "hk":
        return s.zfill(5)
    return s.zfill(6)


def read_companies(path: str, default_category: str) -> list[Company]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            return []
        has_base = {"folder", "stock", "name"}.issubset(set(r.fieldnames))
        if not has_base:
            raise ValueError(f"companies.csv 缺少必需字段 folder/stock/name, 实际: {r.fieldnames}")
        out: list[Company] = []
        for row in r:
            folder = (row.get("folder") or "").strip()
            stock = (row.get("stock") or "").strip()
            name = (row.get("name") or "").strip()
            category = (row.get("category") or default_category).strip() or default_category
            if folder and stock and name:
                stock = normalize_stock_code(stock, category)
                out.append(Company(folder=folder, stock=stock, name=name, category=category))
        return out


def post_api(url: str, payload: dict[str, Any], timeout: int = 60, retries: int = 5) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.status_code == 429:
                wait_s = min(60.0, 2.0 ** i)
                time.sleep(wait_s)
                continue
            r.raise_for_status()
            j = r.json()
            if j.get("code") != 1:
                raise RuntimeError(f"API返回错误: {j}")
            data = j.get("data") or []
            if not isinstance(data, list):
                raise RuntimeError(f"data字段类型异常: {type(data)}")
            return data
        except Exception as e:
            last_err = e
            wait_s = min(60.0, 2.0 ** i)
            time.sleep(wait_s)
    raise RuntimeError(f"调用理杏仁API失败（已重试{retries}次）: {last_err}")


def nested_get(obj: dict[str, Any], metric_path: str) -> Any:
    cur: Any = obj
    for k in metric_path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def fmt_num(v: Any) -> str:
    if v is None:
        return ""
    try:
        x = float(v)
    except Exception:
        return ""
    return f"={x:.15g}"


def map_report_type(rt: str) -> str:
    m = {
        "first_quarterly_report": "一季报",
        "semi_annual_report": "中报",
        "interim_report": "中报",
        "third_quarterly_report": "三季报",
        "third_quarter_report": "三季报",
        "annual_report": "年报",
    }
    return m.get(rt, rt or "")


def map_currency(c: str) -> str:
    return "元" if c == "CNY" else (c or "")


def write_series_csv(
    *,
    out_path: str,
    rows: list[dict[str, Any]],
    value_metric: str,
    value_col: str,
    yoy_metric: str | None,
    yoy_col: str | None,
) -> None:
    header = ["日期", "财报类型", "货币", value_col]
    if yoy_metric and yoy_col:
        header.append(yoy_col)

    # 按财报日期降序（最新在上）
    rows_sorted = sorted(rows, key=lambda r: (r.get("date") or ""), reverse=True)

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows_sorted:
            d = (r.get("date") or "").split("T")[0]
            rt = map_report_type(str(r.get("reportType") or ""))
            cur = map_currency(str(r.get("currency") or ""))
            val = fmt_num(nested_get(r, value_metric))
            row = [d, rt, cur, val]
            if yoy_metric and yoy_col:
                row.append(fmt_num(nested_get(r, yoy_metric)))
            w.writerow(row)


def update_company_fs(
    *,
    token: str,
    company: Company,
    base_dir: str,
    start_date: str,
    end_date: str,
    clean_existing: bool,
) -> None:
    # 港股走 /api/hk/ 域名(2026-05-06 校正);其它走 /api/cn/{category}
    if company.category == "hk":
        url = f"{API_BASE_HK}/non_financial"
    else:
        url = f"{API_BASE_CN}/{company.category}"
    root = Path(base_dir) / company.folder / "01_基本面数据"

    # 02~05 映射：模块目录、文件名后缀、值字段、同比字段
    specs = [
        # 02_盈利分析
        ("02_盈利分析", "净资产收益率(ROE)", "q.m.roe.ttm", None, "净资产收益率(ROE)", None),
        ("02_盈利分析", "总资产收益率(ROA)", "q.m.roa.ttm", None, "总资产收益率(ROA)", None),
        ("02_盈利分析", "毛利率(GM)", "q.m.gp_m.ttm", None, "毛利率(GM)", None),
        ("02_盈利分析", "净利润率", "q.m.np_s_r.ttm", None, "净利润率", None),
        ("02_盈利分析", "资本回报率(ROIC)", "q.m.roic.ttm", None, "资本回报率(ROIC)", None),
        # 03_成长性分析
        ("03_成长性分析", "营业收入", "q.ps.oi.t", "q.ps.oi.t_y2y", "营业收入", "累积同比"),
        ("03_成长性分析", "归属于母公司普通股股东的净利润", "q.ps.npatoshopc.t", "q.ps.npatoshopc.t_y2y", "归属于母公司普通股股东的净利润", "累积同比"),
        ("03_成长性分析", "基本每股收益", "q.ps.beps.t", "q.ps.beps.t_y2y", "基本每股收益", "累积同比"),
        # 04_现金流分析
        ("04_现金流分析", "经营活动产生的现金流量净额", "q.cfs.ncffoa.t", "q.cfs.ncffoa.t_y2y", "经营活动产生的现金流量净额", "累积同比"),
        ("04_现金流分析", "自由现金流量", "q.m.fcf.ttm", None, "自由现金流量", None),
        ("04_现金流分析", "经营活动产生的现金流量净额对净利润的比率", "q.m.ncffoa_np_r.ttm", None, "经营活动产生的现金流量净额对净利润的比率", None),
        # 05_安全性分析
        ("05_安全性分析", "资产负债率", "q.m.tl_ta_r.t", None, "资产负债率", None),
        ("05_安全性分析", "有息负债率", "q.m.lwi_ta_r.t", None, "有息负债率", None),
        ("05_安全性分析", "流动比率", "q.m.c_r.t", None, "流动比率", None),
        ("05_安全性分析", "速动比率", "q.m.q_r.t", None, "速动比率", None),
        # 05_安全性分析 — BS 聚合三件套(P2 缺口)
        ("05_安全性分析", "资产合计", "q.bs.ta.t", None, "资产合计", None),
        ("05_安全性分析", "负债合计", "q.bs.tl.t", None, "负债合计", None),
        ("05_安全性分析", "所有者权益合计", "q.bs.toe.t", None, "所有者权益合计", None),
        ("05_安全性分析", "流动资产合计", "q.bs.ca.t", None, "流动资产合计", None),
        ("05_安全性分析", "流动负债合计", "q.bs.cl.t", None, "流动负债合计", None),
        ("05_安全性分析", "长期负债合计", "q.bs.ltl.t", None, "长期负债合计", None),
        ("05_安全性分析", "货币资金", "q.bs.mc.t", None, "货币资金", None),
        ("05_安全性分析", "应收账款", "q.bs.ar.t", None, "应收账款", None),
    ]

    # 过滤掉当前分类不支持的指标
    excluded = CATEGORY_EXCLUDED_METRICS.get(company.category, set())
    if excluded:
        specs = [s for s in specs if s[2] not in excluded and s[3] not in excluded]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if clean_existing:
        for mod, suffix, *_ in specs:
            d = root / mod
            if not d.is_dir():
                continue
            for old in d.glob(f"{company.name}_{suffix}_合并报表_*.csv"):
                old.unlink(missing_ok=True)
            for old in d.glob(f"{company.name}_{suffix}_合并报表_*.md"):
                old.unlink(missing_ok=True)

    # 4 个模块共享同一 fs/{category} URL,合并到一次 API 请求(1 次代替原来的 4 次)
    seen: set[str] = set()
    metrics: list[str] = []
    for _, _, value_metric, yoy_metric, _, _ in specs:
        for m in (value_metric, yoy_metric):
            if m and m not in seen:
                seen.add(m)
                metrics.append(m)

    payload = {
        "token": token,
        "stockCodes": [company.stock],
        "startDate": start_date,
        "endDate": end_date,
        "metricsList": metrics,
    }
    rows = post_api(url, payload)

    for mod, suffix, value_metric, yoy_metric, value_col, yoy_col in specs:
        out_dir = root / mod
        out_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{company.name}_{suffix}_合并报表_{ts}.csv"
        out_csv = out_dir / out_name
        write_series_csv(
            out_path=str(out_csv),
            rows=rows,
            value_metric=value_metric,
            value_col=value_col,
            yoy_metric=yoy_metric,
            yoy_col=yoy_col,
        )
        write_md_sidecar(out_csv)


def main() -> None:
    p = argparse.ArgumentParser(description="批量更新公司档案库 02-05 财务模块")
    p.add_argument("--token", required=False, help="理杏仁 token（可省略，默认读取环境变量 LIXINGER_TOKEN）")
    p.add_argument("--companies-csv", required=True, help="公司清单CSV（folder,stock,name[,category]）")
    p.add_argument("--base-dir", default="02_companies", help="公司档案库根目录")
    p.add_argument("--years", type=int, default=10, help="拉取历史年数（默认10）")
    p.add_argument("--end-date", default=None, help="结束日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--default-category", default="non_financial", choices=["non_financial", "bank", "security", "insurance", "other_financial"], help="CSV未提供category时的默认分类")
    p.add_argument("--clean-existing", action="store_true", help="清理旧同类文件后再写入")
    p.add_argument("--only-folder", action="append", default=[],
                   help="只更新指定公司目录名,可重复传入")
    args = p.parse_args()

    token = resolve_lixinger_token(args.token)
    if not token.strip():
        raise SystemExit(
            "缺少 token：请传入 --token，或设置环境变量 LIXINGER_TOKEN，"
            "或在知识库根目录创建 .lixinger_token（单行），或设置 LIXINGER_TOKEN_FILE，"
            "或在 03_行业与宏观/账号密码.md 中填写「开放API Token:」"
        )

    end_d = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else date.today()
    start_d = end_d - timedelta(days=365 * args.years)
    start = start_d.strftime("%Y-%m-%d")
    end = end_d.strftime("%Y-%m-%d")

    companies = read_companies(args.companies_csv, args.default_category)
    if args.only_folder:
        only = set(args.only_folder)
        companies = [c for c in companies if c.folder in only]
    if not companies:
        raise SystemExit("companies.csv 无有效公司记录")

    failures: list[tuple[str, str]] = []
    for c in companies:
        try:
            update_company_fs(
                token=token,
                company=c,
                base_dir=args.base_dir,
                start_date=start,
                end_date=end,
                clean_existing=args.clean_existing,
            )
            print(f"✅ 已更新 {c.folder} ({c.stock}) 的 02-05")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {c.folder} ({c.stock}) 失败,跳过:{exc}", flush=True)
            failures.append((c.folder, str(exc)))

    print(f"\n🎉 完成:{len(companies) - len(failures)}/{len(companies)} 家成功,区间 {start} ~ {end}")
    if failures:
        print(f"失败 {len(failures)} 家:")
        for f, err in failures:
            print(f"  - {f}: {err[:120]}")


if __name__ == "__main__":
    main()

