#!/usr/bin/env python3
"""把 generate_wide_valuation.py 输出的 4 个估值宽表 CSV 合并到 历史数据/估值.csv

只处理估值,不动 摘要.md / 其他历史数据。完成后清理 01_估值分析/。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

# 目标 历史数据/估值.csv 列顺序(参考老格式,但 core3 仅含 PE-TTM/PB/PS-TTM/股息率)
# 2026-05-06:加入"市值(元)"以解锁 graham/lynch/buffett 的市值阈值规则
TARGET_COLS = [
    "date",
    "PE-TTM", "PE-TTM_分位点", "PE-TTM_80%分位点值", "PE-TTM_50%分位点值", "PE-TTM_20%分位点值",
    "股息率",
    "PS-TTM", "PS-TTM_分位点", "PS-TTM_80%分位点值", "PS-TTM_50%分位点值", "PS-TTM_20%分位点值",
    "PB", "PB_分位点", "PB_80%分位点值", "PB_50%分位点值", "PB_20%分位点值",
    "市值(元)",
]

# 文件名模式 → (核心列前缀, 是否带分位点)
FILE_SPECS = [
    ("PE-TTM", "PE-TTM", True),
    ("PB",     "PB",     True),
    ("PS-TTM", "PS-TTM", True),
    ("Dividend Yield Ratio", "股息率", False),
]


def strip_excel_eq(v):
    if isinstance(v, str) and v.startswith("="):
        return v[1:]
    return v


def load_one(csv_path: Path, prefix: str, with_quantile: bool) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # 处理 BOM 列名
    df.columns = [c.lstrip("﻿").strip() for c in df.columns]
    if "日期" not in df.columns:
        raise ValueError(f"{csv_path.name} 缺少 日期 列")

    out = pd.DataFrame()
    out["date"] = df["日期"]

    if prefix == "股息率":
        if "股息率" not in df.columns:
            raise ValueError(f"{csv_path.name} 缺少 股息率 列")
        out["股息率"] = df["股息率"].map(strip_excel_eq)
    else:
        cols_map = {
            prefix: prefix,
            f"{prefix} 分位点": f"{prefix}_分位点",
            f"{prefix} 80%分位点值": f"{prefix}_80%分位点值",
            f"{prefix} 50%分位点值": f"{prefix}_50%分位点值",
            f"{prefix} 20%分位点值": f"{prefix}_20%分位点值",
        }
        for src, tgt in cols_map.items():
            if src in df.columns:
                out[tgt] = df[src].map(strip_excel_eq)

    # 市值列(每个 wide CSV 都带,只在 PE-TTM 文件取一次,其他文件留空避免冲突)
    if prefix == "PE-TTM" and "市值(元)" in df.columns:
        out["市值(元)"] = df["市值(元)"].map(strip_excel_eq)

    return out


def merge_company(out_dir: Path, name: str) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for fname_key, prefix, with_q in FILE_SPECS:
        # 找文件:{name}_{fname_key}_{ts}.csv
        pat = f"{name}_{fname_key}_*.csv"
        files = sorted(out_dir.glob(pat))
        if not files:
            print(f"  ⚠️ 未找到 {pat}", file=sys.stderr)
            continue
        # 取最新的(按文件名时间戳)
        csv_path = files[-1]
        df = load_one(csv_path, prefix, with_q)
        parts.append(df)

    if not parts:
        raise RuntimeError(f"{name}: 无任何估值 CSV 可合并")

    merged = parts[0]
    for p in parts[1:]:
        merged = pd.merge(merged, p, on="date", how="outer")

    # 按目标列顺序排列(缺列就跳过)
    cols_present = [c for c in TARGET_COLS if c in merged.columns]
    merged = merged[cols_present]
    merged = merged.sort_values("date", ascending=False).reset_index(drop=True)
    return merged


def process_company(folder: Path, name: str, dry_run: bool = False) -> tuple[int, str]:
    base = folder / "01_基本面数据"
    out_dir = base / "01_估值分析"
    if not out_dir.exists():
        return 0, f"无 01_估值分析 目录"

    merged = merge_company(out_dir, name)
    history_dir = base / "历史数据"
    history_dir.mkdir(exist_ok=True)
    target = history_dir / "估值.csv"

    # outer-merge with existing: 新数据覆盖同 date,旧 date 保留 + 列做 outer-join 不丢
    if target.exists():
        old = pd.read_csv(target)
        # 新数据日期范围内的行视为权威 → 从 old 删掉重叠 date 后再 concat
        new_dates = set(merged["date"].astype(str))
        old_keep = old[~old["date"].astype(str).isin(new_dates)]
        # outer-concat 让两边都有的列对齐,各自独有列也保留
        combined = pd.concat([merged, old_keep], ignore_index=True, sort=False)
        # 列顺序:目标列 first,其他列追加
        target_first = [c for c in TARGET_COLS if c in combined.columns]
        extra = [c for c in combined.columns if c not in target_first]
        combined = combined[target_first + extra]
        combined = combined.sort_values("date", ascending=False).reset_index(drop=True)
        merged = combined

    if not dry_run:
        merged.to_csv(target, index=False)
        # 清理 01_估值分析/
        shutil.rmtree(out_dir)

    return len(merged), str(target)


def main() -> int:
    p = argparse.ArgumentParser(description="把 generate_wide_valuation 输出合并到 历史数据/估值.csv")
    p.add_argument("--companies-csv", required=True)
    p.add_argument("--base-dir", default="02_companies")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    base_dir = Path(args.base_dir)
    df = pd.read_csv(args.companies_csv, dtype={"stock": str})

    fail = 0
    for _, row in df.iterrows():
        folder = base_dir / row["folder"]
        name = row["name"]
        try:
            n, target = process_company(folder, name, args.dry_run)
            print(f"✅ {name}: {n} 行 → {target}")
        except Exception as exc:
            print(f"❌ {name}: {exc}")
            fail += 1
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
