#!/usr/bin/env python3
"""
批量更新多家公司：只拉“最近N天宽表” + 批量获取分位点统计（省token/省请求）。

策略（对应建议 3 + 4）：
1) 先用 date=<endDate> 对所有 stockCodes 批量请求一次，获取：
   - sp/mc/cmc/ecmc + PB/PE/PS/股息率等值
   - 以及 pb.y10.cvpos/q2v/q5v/q8v 等统计字段（y10）
   返回每个 stockCode 一行，作为“统计快照”（后续在宽表中每行复用）
2) 再对每家公司单独请求 startDate~endDate 的日频数据（只取值字段，不取统计字段），行数很少
3) 输出宽表 CSV 到公司档案库的 01_估值分析/，并可选覆盖生成最近一月目录

输入 companies.csv 格式（UTF-8）：
folder,stock,name
09_三花智控,002050,三花智控
07_美的集团,000333,美的集团
...
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from pathlib import Path
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

from lixinger_csv_to_md import write_md_sidecar
from lixinger_resolve_token import resolve_lixinger_token


API_URL = "https://open.lixinger.com/api/cn/company/fundamental/non_financial"


@dataclass(frozen=True)
class Company:
    folder: str  # e.g. 09_三花智控
    stock: str   # e.g. 002050
    name: str    # e.g. 三花智控


def _fmt_date(d: str) -> str:
    return (d or "").split("T")[0]


def _fmt_num(v: Any, digits: int | None = None) -> str:
    if v is None:
        return ""
    try:
        x = float(v)
    except Exception:
        return ""
    if digits is None:
        s = str(x)
    else:
        s = f"{x:.{digits}f}"
    return f"={s}"


def post_api(payload: dict[str, Any], timeout_s: int = 60, retries: int = 5) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            resp = requests.post(API_URL, json=payload, timeout=timeout_s)
            # 常见：触发限流（429），做退避重试
            if resp.status_code == 429:
                wait_s = min(60.0, 2.0 ** i)
                time.sleep(wait_s)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 1:
                raise RuntimeError(f"API返回错误: {data}")
            rows = data.get("data") or []
            if not isinstance(rows, list):
                raise RuntimeError(f"API返回data类型异常: {type(rows)}")
            return rows
        except Exception as e:
            last_err = e
            wait_s = min(60.0, 2.0 ** i)
            time.sleep(wait_s)
    raise RuntimeError(f"调用理杏仁API失败（已重试{retries}次）: {last_err}")


def read_companies_csv(path: str) -> list[Company]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        need = {"folder", "stock", "name"}
        if not r.fieldnames or not need.issubset(set(r.fieldnames)):
            raise ValueError(f"companies.csv 需要表头: {sorted(need)}，实际: {r.fieldnames}")
        out: list[Company] = []
        for row in r:
            folder = (row.get("folder") or "").strip()
            stock = (row.get("stock") or "").strip()
            name = (row.get("name") or "").strip()
            if not (folder and stock and name):
                continue
            out.append(Company(folder=folder, stock=stock, name=name))
        return out


def build_stats_metrics(stats_window: str) -> list[str]:
    # 估值统计指标：metricsName.granularity.statisticsDataType
    # granularity: fs/y20/y10/y5/y3/y1（这里默认 y10，可由参数控制）
    w = stats_window
    def m(base: str) -> list[str]:
        return [f"{base}.{w}.cvpos", f"{base}.{w}.q8v", f"{base}.{w}.q5v", f"{base}.{w}.q2v"]

    metrics = []
    for base in ("pe_ttm", "d_pe_ttm", "pb", "pb_wo_gw", "ps_ttm"):
        metrics.extend(m(base))
    return metrics


def fetch_stats_snapshot(*, token: str, stocks: list[str], as_of: str, stats_window: str) -> dict[str, dict[str, Any]]:
    metrics = [
        "sp",
        "mc",
        "cmc",
        "ecmc",
        "pe_ttm",
        "d_pe_ttm",
        "pb",
        "pb_wo_gw",
        "ps_ttm",
        "dyr",
        *build_stats_metrics(stats_window),
    ]
    payload = {
        "token": token,
        "stockCodes": stocks,
        "date": as_of,
        "metricsList": metrics,
    }
    rows = post_api(payload)
    snap: dict[str, dict[str, Any]] = {}
    for r in rows:
        sc = r.get("stockCode")
        if isinstance(sc, str) and sc:
            snap[sc] = r
    return snap


def fetch_recent_series(*, token: str, stock: str, start: str, end: str) -> list[dict[str, Any]]:
    # 日频仅取值字段，减少返回体量
    metrics = ["sp", "mc", "cmc", "ecmc", "pe_ttm", "d_pe_ttm", "pb", "pb_wo_gw", "ps_ttm", "dyr"]
    payload = {
        "token": token,
        "stockCodes": [stock],
        "startDate": start,
        "endDate": end,
        "metricsList": metrics,
    }
    return post_api(payload)


def write_wide(
    *,
    out_path: str,
    rows: list[dict[str, Any]],
    snap: dict[str, Any],
    metric_key: str,
    metric_label: str,
    include_stats: bool,
    stats_window: str,
) -> None:
    base_header = [
        "日期",
        "理杏仁前复权(元)",
        "前复权(元)",
        "后复权(元)",
        "股价(元)",
        "市值(元)",
        "流通市值(元)",
        "自由流通市值(元)",
        "行业中位数",
    ]
    header = base_header + [metric_label]
    if include_stats:
        header += [
            f"{metric_label} 分位点",
            f"{metric_label} 80%分位点值",
            f"{metric_label} 50%分位点值",
            f"{metric_label} 20%分位点值",
        ]

    rows_sorted = sorted(rows, key=lambda r: (r.get("date") or ""), reverse=True)

    stats_prefix = f"{metric_key}.{stats_window}"
    k_cvpos = f"{stats_prefix}.cvpos"
    k_q8v = f"{stats_prefix}.q8v"
    k_q5v = f"{stats_prefix}.q5v"
    k_q2v = f"{stats_prefix}.q2v"

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows_sorted:
            d = _fmt_date(r.get("date", ""))
            sp = r.get("sp")
            mc = r.get("mc")
            cmc = r.get("cmc")
            ecmc = r.get("ecmc")
            metric_val = r.get(metric_key)

            row = [
                d,
                _fmt_num(sp, 4),
                _fmt_num(sp, 4),
                _fmt_num(sp, 4),
                _fmt_num(sp, 4),
                _fmt_num(mc, None),
                _fmt_num(cmc, None),
                _fmt_num(ecmc, None),
                "",
                _fmt_num(metric_val, 4),
            ]

            if include_stats:
                row += [
                    _fmt_num(snap.get(k_cvpos), 4),
                    _fmt_num(snap.get(k_q8v), 4),
                    _fmt_num(snap.get(k_q5v), 4),
                    _fmt_num(snap.get(k_q2v), 4),
                ]

            w.writerow(row)


def main() -> None:
    p = argparse.ArgumentParser(description="批量拉取最近N天宽表（含批量分位点统计快照）")
    p.add_argument("--token", required=False, help="理杏仁 token（可省略，默认读取环境变量 LIXINGER_TOKEN）")
    p.add_argument("--companies-csv", required=True, help="公司列表CSV（folder,stock,name）")
    p.add_argument("--base-dir", default="02_companies", help="公司档案库根目录（默认：02_companies）")
    p.add_argument("--days", type=int, default=90, help="拉取最近天数（默认90）")
    p.add_argument("--stats-window", default="y10", choices=["fs", "y20", "y10", "y5", "y3", "y1"], help="分位点统计窗口（默认y10）")
    p.add_argument("--date", default=None, help="截止日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--clean-existing", action="store_true", help="写入前清理该公司估值分析目录下旧的同类宽表CSV")
    args = p.parse_args()

    token = resolve_lixinger_token(args.token)
    if not token.strip():
        raise SystemExit(
            "缺少 token：请传入 --token，或设置环境变量 LIXINGER_TOKEN，"
            "或在知识库根目录创建 .lixinger_token（单行），或设置 LIXINGER_TOKEN_FILE，"
            "或在 03_行业与宏观/账号密码.md 中填写「开放API Token:」"
        )

    end_d = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    start_d = end_d - timedelta(days=args.days)
    start = start_d.strftime("%Y-%m-%d")
    end = end_d.strftime("%Y-%m-%d")

    companies = read_companies_csv(args.companies_csv)
    if not companies:
        raise SystemExit("companies.csv 为空或无有效行")

    stocks = [c.stock for c in companies]
    snap_map = fetch_stats_snapshot(token=token, stocks=stocks, as_of=end, stats_window=args.stats_window)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mapping = [
        ("pe_ttm", "PE-TTM", True, "{name}_PE-TTM_{ts}.csv"),
        ("d_pe_ttm", "PE-TTM(扣非)", True, "{name}_Deduction of PE-TTM_{ts}.csv"),
        ("pb", "PB", True, "{name}_PB_{ts}.csv"),
        ("pb_wo_gw", "PB(不含商誉)", True, "{name}_PB without goodwill_{ts}.csv"),
        ("ps_ttm", "PS-TTM", True, "{name}_PS-TTM_{ts}.csv"),
        ("dyr", "股息率", False, "{name}_Dividend Yield Ratio_{ts}.csv"),
    ]

    for c in companies:
        series = fetch_recent_series(token=token, stock=c.stock, start=start, end=end)
        out_dir = os.path.join(args.base_dir, c.folder, "01_基本面数据", "01_估值分析")
        os.makedirs(out_dir, exist_ok=True)
        snap = snap_map.get(c.stock, {})

        if args.clean_existing:
            out_dir_path = Path(out_dir)
            for pat in [
                f"{c.name}_PE-TTM_*.csv",
                f"{c.name}_Deduction of PE-TTM_*.csv",
                f"{c.name}_PB_*.csv",
                f"{c.name}_PB without goodwill_*.csv",
                f"{c.name}_PS-TTM_*.csv",
                f"{c.name}_Dividend Yield Ratio_*.csv",
            ]:
                for old in out_dir_path.glob(pat):
                    old.unlink(missing_ok=True)
                md_pat = pat.replace(".csv", ".md")
                for old in out_dir_path.glob(md_pat):
                    old.unlink(missing_ok=True)

        for key, label, with_stats, tpl in mapping:
            out_path = os.path.join(out_dir, tpl.format(name=c.name, ts=ts))
            write_wide(
                out_path=out_path,
                rows=series,
                snap=snap,
                metric_key=key,
                metric_label=label,
                include_stats=with_stats,
                stats_window=args.stats_window,
            )
            write_md_sidecar(out_path)

    print(f"✅ 批量完成：{len(companies)} 家公司（{start}~{end}，stats={args.stats_window}）")


if __name__ == "__main__":
    main()

