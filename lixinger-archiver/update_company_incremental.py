#!/usr/bin/env python3
"""
单家公司增量更新:从 历史数据/{估值,盈利,成长,现金流,安全性}.csv 读 max(date),
只请求增量段,merge 回 CSV。

设计要点:
- 估值接口指标 + 字段名 严格 匹配 现有 CSV 列(分位点字段名保持理杏仁原样,不重算)
- 财报接口同 category 4 模块共享一次 API 调用(同 batch_update_fs_modules 的优化逻辑)
- 增量段为空(已是最新)时跳过,不发任何请求
- merge 时用 (date, [reportType]) 去重,新值覆盖旧值
- 仅写入 历史数据/*.csv,不动 01_估值分析/02_盈利分析 等中间目录(那些已被 consolidate 删除)

使用:
  python3 .tools/lixinger-archiver/update_company_incremental.py \\
    --stock 000333 --name 美的集团 --folder 07_美的集团 [--category non_financial]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lixinger_resolve_token import resolve_lixinger_token


VAL_API = "https://open.lixinger.com/api/cn/company/fundamental/non_financial"
FS_API_BASE = "https://open.lixinger.com/api/cn/company/fs"

VAL_BASE_KEYS_FULL = ["pe_ttm", "d_pe_ttm", "pb_wo_gw", "pb", "ps_ttm"]
VAL_BASE_LABELS = {
    "pe_ttm": "PE-TTM",
    "d_pe_ttm": "PE-TTM(扣非)",
    "pb": "PB",
    "pb_wo_gw": "PB(不含商誉)",
    "ps_ttm": "PS-TTM",
}

FS_SPECS = [
    ("盈利", "毛利率(GM)", "q.m.gp_m.ttm", None),
    ("盈利", "净资产收益率(ROE)", "q.m.roe.ttm", None),
    ("盈利", "总资产收益率(ROA)", "q.m.roa.ttm", None),
    ("盈利", "净利润率", "q.m.np_s_r.ttm", None),
    ("成长", "营业收入", "q.ps.oi.t", "q.ps.oi.t_y2y"),
    ("成长", "归属于母公司普通股股东的净利润", "q.ps.npatoshopc.t", "q.ps.npatoshopc.t_y2y"),
    ("成长", "基本每股收益", "q.ps.beps.t", "q.ps.beps.t_y2y"),
    ("现金流", "经营活动产生的现金流量净额", "q.cfs.ncffoa.t", "q.cfs.ncffoa.t_y2y"),
    ("现金流", "自由现金流量", "q.m.fcf.ttm", None),
    ("现金流", "经营活动产生的现金流量净额对净利润的比率", "q.m.ncffoa_np_r.ttm", None),
    ("安全性", "资产负债率", "q.m.tl_ta_r.t", None),
    ("安全性", "有息负债率", "q.m.lwi_ta_r.t", None),
    ("安全性", "流动比率", "q.m.c_r.t", None),
    ("安全性", "速动比率", "q.m.q_r.t", None),
]


def post_api(url: str, payload: dict[str, Any], timeout: int = 60, retries: int = 5) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.status_code == 429:
                time.sleep(min(60.0, 2.0 ** i))
                continue
            r.raise_for_status()
            j = r.json()
            if j.get("code") != 1:
                raise RuntimeError(f"API 返回错误: {j}")
            data = j.get("data") or []
            if not isinstance(data, list):
                raise RuntimeError(f"data 类型异常: {type(data)}")
            return data
        except Exception as e:
            last_err = e
            time.sleep(min(60.0, 2.0 ** i))
    raise RuntimeError(f"调用 API 失败: {last_err}")


def nested(obj: dict, path: str) -> Any:
    cur: Any = obj
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def fmt_num(v: Any, digits: int = 4) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.{digits}f}"
    except (ValueError, TypeError):
        return ""


def load_existing_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str).fillna("")
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)
    return df


def max_date(df: pd.DataFrame) -> str | None:
    if df.empty or "date" not in df.columns:
        return None
    dates = sorted(d for d in df["date"].tolist() if d)
    return dates[-1] if dates else None


def build_val_metrics(base_keys: list[str]) -> list[str]:
    metrics = ["sp", "mc", "cmc", "ecmc"]
    for k in base_keys:
        metrics.append(k)
        metrics.extend([f"{k}.y10.cvpos", f"{k}.y10.q8v", f"{k}.y10.q5v", f"{k}.y10.q2v"])
    metrics.append("dyr")
    return metrics


def val_row_to_dict(r: dict, base_keys: list[str]) -> dict[str, str]:
    """API 行 → CSV 列字典(列名严格匹配 历史数据/估值.csv)"""
    out: dict[str, str] = {"date": (r.get("date") or "").split("T")[0]}
    for k in base_keys:
        label = VAL_BASE_LABELS[k]
        out[label] = fmt_num(r.get(k))
        out[f"{label}_分位点"] = fmt_num(r.get(f"{k}.y10.cvpos"))
        out[f"{label}_80%分位点值"] = fmt_num(r.get(f"{k}.y10.q8v"))
        out[f"{label}_50%分位点值"] = fmt_num(r.get(f"{k}.y10.q5v"))
        out[f"{label}_20%分位点值"] = fmt_num(r.get(f"{k}.y10.q2v"))
    out["股息率"] = fmt_num(r.get("dyr"))
    return out


def merge_csv(existing: pd.DataFrame, new_rows: list[dict], key_cols: list[str]) -> pd.DataFrame:
    new_df = pd.DataFrame(new_rows)
    if existing.empty:
        merged = new_df
    else:
        for c in new_df.columns:
            if c not in existing.columns:
                existing[c] = ""
        for c in existing.columns:
            if c not in new_df.columns:
                new_df[c] = ""
        new_df = new_df[existing.columns]
        merged = pd.concat([existing, new_df], ignore_index=True)
    if all(c in merged.columns for c in key_cols):
        merged = merged.drop_duplicates(subset=key_cols, keep="last")
    if "date" in merged.columns:
        merged = merged.sort_values("date", ascending=False).reset_index(drop=True)
    return merged


def update_valuation(*, token: str, stock: str, history_dir: Path, base_keys: list[str], end: str) -> int:
    csv_path = history_dir / "估值.csv"
    existing = load_existing_csv(csv_path)
    last = max_date(existing)
    if last:
        start_d = (datetime.strptime(last, "%Y-%m-%d").date() + timedelta(days=1))
    else:
        start_d = date.today() - timedelta(days=365 * 10)
    if start_d.strftime("%Y-%m-%d") > end:
        print(f"  ⏩ 估值已是最新({last}),跳过")
        return 0

    metrics = build_val_metrics(base_keys)
    payload = {
        "token": token,
        "stockCodes": [stock],
        "startDate": start_d.strftime("%Y-%m-%d"),
        "endDate": end,
        "metricsList": metrics,
    }
    rows = post_api(VAL_API, payload)
    new_rows = [val_row_to_dict(r, base_keys) for r in rows if (r.get("date") or "").split("T")[0]]
    if not new_rows:
        print(f"  ⏩ 估值无新数据({start_d} ~ {end})")
        return 0
    merged = merge_csv(existing, new_rows, key_cols=["date"])
    merged.to_csv(csv_path, index=False)
    print(f"  ✓ 估值新增 {len(new_rows)} 行 → {csv_path.name}({len(merged)} 行)")
    return len(new_rows)


def update_fs(*, token: str, stock: str, category: str, history_dir: Path, end: str) -> dict[str, int]:
    """同 category 一次 API 拉所有指标,然后按"模块"分发到 4 个 CSV"""
    counts: dict[str, int] = {}

    # 找到各模块当前 CSV 的 max(date),取最早的作为本次请求 startDate
    starts: dict[str, str | None] = {}
    for mod in ("盈利", "成长", "现金流", "安全性"):
        df = load_existing_csv(history_dir / f"{mod}.csv")
        starts[mod] = max_date(df)

    if all(d is not None for d in starts.values()):
        earliest = min(starts.values())  # type: ignore[arg-type]
        start_d = datetime.strptime(earliest, "%Y-%m-%d").date() + timedelta(days=1)
    else:
        start_d = date.today() - timedelta(days=365 * 10)

    if start_d.strftime("%Y-%m-%d") > end:
        print(f"  ⏩ 财报已是最新,跳过")
        return counts

    seen: set[str] = set()
    metrics: list[str] = []
    for _, _, val_m, yoy_m in FS_SPECS:
        for m in (val_m, yoy_m):
            if m and m not in seen:
                seen.add(m)
                metrics.append(m)

    payload = {
        "token": token,
        "stockCodes": [stock],
        "startDate": start_d.strftime("%Y-%m-%d"),
        "endDate": end,
        "metricsList": metrics,
    }
    url = f"{FS_API_BASE}/{category}"
    rows = post_api(url, payload)
    if not rows:
        print(f"  ⏩ 财报无新数据({start_d} ~ {end})")
        return counts

    # 按模块分组写
    by_mod: dict[str, list[tuple[str, str, str | None]]] = {}
    for mod, label, val_m, yoy_m in FS_SPECS:
        by_mod.setdefault(mod, []).append((label, val_m, yoy_m))

    for mod, items in by_mod.items():
        last_mod = starts.get(mod)
        existing = load_existing_csv(history_dir / f"{mod}.csv")
        new_rows: list[dict] = []
        for r in rows:
            d = (r.get("date") or "").split("T")[0]
            if not d:
                continue
            if last_mod and d <= last_mod:
                continue
            row: dict[str, str] = {"date": d}
            for label, val_m, yoy_m in items:
                row[label] = fmt_num(nested(r, val_m))
                if yoy_m:
                    row[f"{label}_累积同比"] = fmt_num(nested(r, yoy_m))
            new_rows.append(row)
        if not new_rows:
            print(f"  ⏩ {mod} 无新数据")
            continue
        merged = merge_csv(existing, new_rows, key_cols=["date"])
        merged.to_csv(history_dir / f"{mod}.csv", index=False)
        print(f"  ✓ {mod} 新增 {len(new_rows)} 行")
        counts[mod] = len(new_rows)
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="单家公司增量更新(读本地 max(date),只取增量)")
    p.add_argument("--token", required=False)
    p.add_argument("--stock", required=True, help="如 000333")
    p.add_argument("--name", required=True, help="如 美的集团")
    p.add_argument("--folder", required=True, help="如 07_美的集团")
    p.add_argument("--category", default="non_financial", choices=["non_financial", "bank", "security", "insurance", "other_financial"])
    p.add_argument("--base-dir", default="02_companies", help="公司档案库根目录(相对 preson/)")
    p.add_argument(
        "--metrics-preset",
        default="full",
        choices=["full", "core3"],
        help="估值指标预设(默认 full,core3=只 PE-TTM/PB/PS-TTM)",
    )
    p.add_argument("--end-date", default=None, help="截止日期 YYYY-MM-DD(默认今天)")
    p.add_argument("--skip-valuation", action="store_true")
    p.add_argument("--skip-fs", action="store_true")
    args = p.parse_args()

    token = resolve_lixinger_token(args.token)
    if not token.strip():
        raise SystemExit("缺少 token,见 lixinger_resolve_token 解析顺序")

    base_keys = ["pe_ttm", "pb", "ps_ttm"] if args.metrics_preset == "core3" else VAL_BASE_KEYS_FULL
    end = args.end_date or date.today().strftime("%Y-%m-%d")

    preson_root = Path(__file__).resolve().parents[2]
    history_dir = preson_root / args.base_dir / args.folder / "01_基本面数据" / "历史数据"
    if not history_dir.exists():
        raise SystemExit(f"历史数据目录不存在: {history_dir} (先跑一次首抓 + consolidate)")

    print(f"📦 增量更新: {args.name} ({args.stock}) → {history_dir.relative_to(preson_root)}")
    print(f"   截止日期: {end} | 估值预设: {args.metrics_preset}")

    api_calls = 0
    if not args.skip_valuation:
        n = update_valuation(token=token, stock=args.stock, history_dir=history_dir, base_keys=base_keys, end=end)
        if n > 0:
            api_calls += 1
    if not args.skip_fs:
        counts = update_fs(token=token, stock=args.stock, category=args.category, history_dir=history_dir, end=end)
        if counts:
            api_calls += 1

    print(f"\n✅ 完成,本次 API 调用 {api_calls} 次")


if __name__ == "__main__":
    main()
