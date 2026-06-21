#!/usr/bin/env python3
"""
从理杏仁开放API生成“估值宽表”CSV（公司档案库用）。

要点：
- 接口：https://open.lixinger.com/api/cn/company/fundamental/non_financial
- 同一次请求拉取：股价/市值/流通/自由流通 + 估值指标 + y10 分位点统计值
- 输出：写入公司档案库的 01_估值分析/，文件名带时间戳

限制：
- 开放API文档未提供“行业中位数”的直接字段，该列留空（与网页导出仍有一列差异）。
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from lixinger_csv_to_md import write_md_sidecar
from lixinger_resolve_token import resolve_lixinger_token


API_URL = "https://open.lixinger.com/api/cn/company/fundamental/non_financial"


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


def fetch_dataset(*, token: str, stock: str, start: str, end: str, metrics: list[str], timeout_s: int = 60, retries: int = 5) -> list[dict[str, Any]]:
    payload = {
        "token": token,
        "stockCodes": [stock],
        "startDate": start,
        "endDate": end,
        "metricsList": metrics,
    }
    last_err: Exception | None = None
    for i in range(retries):
        try:
            resp = requests.post(API_URL, json=payload, timeout=timeout_s)
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


def write_wide_csv(
    *,
    out_path: str,
    rows: list[dict[str, Any]],
    metric_key: str,
    metric_label: str,
    include_stats: bool,
    sp_digits: int = 4,
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

    stats_prefix = f"{metric_key}.y10"
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
                _fmt_num(sp, sp_digits),
                _fmt_num(sp, sp_digits),
                _fmt_num(sp, sp_digits),
                _fmt_num(sp, sp_digits),
                _fmt_num(mc, None),
                _fmt_num(cmc, None),
                _fmt_num(ecmc, None),
                "",
                _fmt_num(metric_val, 4),
            ]

            if include_stats:
                row += [
                    _fmt_num(r.get(k_cvpos), 4),
                    _fmt_num(r.get(k_q8v), 4),
                    _fmt_num(r.get(k_q5v), 4),
                    _fmt_num(r.get(k_q2v), 4),
                ]

            w.writerow(row)


def main() -> None:
    p = argparse.ArgumentParser(description="生成理杏仁估值宽表CSV（含y10分位点统计）")
    p.add_argument("--token", required=False, help="理杏仁 token（可省略，默认读取环境变量 LIXINGER_TOKEN）")
    p.add_argument("--stock", required=True, help="股票代码，如002050")
    p.add_argument("--name", required=True, help="公司名，如三花智控")
    p.add_argument("--out-dir", required=True, help="输出目录（公司档案库/01_估值分析）")
    p.add_argument("--years", type=int, default=10, help="回溯年数（默认10）")
    p.add_argument("--clean-existing", action="store_true", help="写入前清理该目录下旧的同类宽表CSV")
    args = p.parse_args()

    token = resolve_lixinger_token(args.token)
    if not token.strip():
        raise SystemExit(
            "缺少 token：请传入 --token，或设置环境变量 LIXINGER_TOKEN，"
            "或在知识库根目录创建 .lixinger_token（单行），或设置 LIXINGER_TOKEN_FILE，"
            "或在 03_行业与宏观/账号密码.md 中填写「开放API Token:」"
        )

    end_d = date.today()
    start_d = end_d - timedelta(days=365 * args.years)
    start = start_d.strftime("%Y-%m-%d")
    end = end_d.strftime("%Y-%m-%d")

    metrics = [
        "sp",
        "mc",
        "cmc",
        "ecmc",
        "pe_ttm",
        "pe_ttm.y10.cvpos",
        "pe_ttm.y10.q8v",
        "pe_ttm.y10.q5v",
        "pe_ttm.y10.q2v",
        "d_pe_ttm",
        "d_pe_ttm.y10.cvpos",
        "d_pe_ttm.y10.q8v",
        "d_pe_ttm.y10.q5v",
        "d_pe_ttm.y10.q2v",
        "pb",
        "pb.y10.cvpos",
        "pb.y10.q8v",
        "pb.y10.q5v",
        "pb.y10.q2v",
        "pb_wo_gw",
        "pb_wo_gw.y10.cvpos",
        "pb_wo_gw.y10.q8v",
        "pb_wo_gw.y10.q5v",
        "pb_wo_gw.y10.q2v",
        "ps_ttm",
        "ps_ttm.y10.cvpos",
        "ps_ttm.y10.q8v",
        "ps_ttm.y10.q5v",
        "ps_ttm.y10.q2v",
        "dyr",
    ]

    rows = fetch_dataset(token=token, stock=args.stock, start=start, end=end, metrics=metrics)
    os.makedirs(args.out_dir, exist_ok=True)

    if args.clean_existing:
        out_dir_path = Path(args.out_dir)
        for pat in [
            f"{args.name}_PE-TTM_*.csv",
            f"{args.name}_Deduction of PE-TTM_*.csv",
            f"{args.name}_PB_*.csv",
            f"{args.name}_PB without goodwill_*.csv",
            f"{args.name}_PS-TTM_*.csv",
            f"{args.name}_Dividend Yield Ratio_*.csv",
        ]:
            for old in out_dir_path.glob(pat):
                old.unlink(missing_ok=True)
            md_pat = pat.replace(".csv", ".md")
            for old in out_dir_path.glob(md_pat):
                old.unlink(missing_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mapping = [
        ("pe_ttm", "PE-TTM", True, f"{args.name}_PE-TTM_{ts}.csv"),
        ("d_pe_ttm", "PE-TTM(扣非)", True, f"{args.name}_Deduction of PE-TTM_{ts}.csv"),
        ("pb", "PB", True, f"{args.name}_PB_{ts}.csv"),
        ("pb_wo_gw", "PB(不含商誉)", True, f"{args.name}_PB without goodwill_{ts}.csv"),
        ("ps_ttm", "PS-TTM", True, f"{args.name}_PS-TTM_{ts}.csv"),
        ("dyr", "股息率", False, f"{args.name}_Dividend Yield Ratio_{ts}.csv"),
    ]

    for key, label, with_stats, filename in mapping:
        out_p = os.path.join(args.out_dir, filename)
        write_wide_csv(
            out_path=out_p,
            rows=rows,
            metric_key=key,
            metric_label=label,
            include_stats=with_stats,
        )
        write_md_sidecar(out_p)

    print(f"✅ 已生成宽表文件到: {os.path.abspath(args.out_dir)}")


if __name__ == "__main__":
    main()

