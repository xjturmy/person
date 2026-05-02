#!/usr/bin/env python3
"""
公司基本面数据整合脚本
将分散的 md 文件合并为 CSV + 摘要.md
"""

import re
import os
import glob
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import pandas as pd


COMPANIES_DIR = Path("/Users/gongyong/Desktop/Keyi/preson/02_companies")

MODULES = {
    "00_最近一月数据": "最近一月",
    "01_估值分析": "估值",
    "02_盈利分析": "盈利",
    "03_成长性分析": "成长",
    "04_现金流分析": "现金流",
    "05_安全性分析": "安全性",
}


def parse_md_table(content: str):
    """从 md 内容解析出表格：返回 headers + rows"""
    lines = [l.strip() for l in content.strip().split("\n") if l.strip().startswith("|")]
    if len(lines) < 3:
        return None, None

    headers = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) == len(headers):
            # 过滤非日期格式的第一列（如"数据来源于"）
            if cols[0] and not re.match(r"^\d{4}-\d{2}-\d{2}$", cols[0]):
                continue
            rows.append(cols)
    return headers, rows


# 在所有模块中都需要排除的冗余列（股价、市值等，与指标不强相关）
REDUNDANT_COLS = {
    "理杏仁前复权(元)", "前复权(元)", "后复权(元)", "股价(元)",
    "市值(元)", "流通市值(元)", "自由流通市值(元)",
    "行业中位数",
    "日期", "财报类型", "货币",
}


def clean_col_name(col: str, metric_name: str) -> str:
    """清理列名，去除重复的前缀"""
    # 如果列名以"指标名_"或"指标名 "开头，去除
    for prefix in [f"{metric_name}_", f"{metric_name} ", metric_name]:
        if col.startswith(prefix):
            rest = col[len(prefix):].strip()
            if rest:
                return f"{metric_name}_{rest}"
            else:
                return metric_name
    return col


def extract_metric_name(filename: str, company_name: str) -> str:
    """从文件名提取指标名称"""
    name = Path(filename).stem
    # 移除公司名前缀
    name = name.replace(f"{company_name}_", "", 1)
    # 去除对比公司名（如"_中国人寿_中国平安"）
    # 去除时间戳（如 _20260421_203638）
    name = re.sub(r"_\d{8}_\d{6}$", "", name)
    # 去除日期范围（如 _20260323-20260416 或 _20251231-20251231）
    name = re.sub(r"_\d{8}-\d{8}$", "", name)
    # 去除"合并报表"后缀
    name = name.replace("_合并报表", "")
    # 去除"_行业"（如"_保险"）
    return name


def is_multi_company_file(filename: str) -> bool:
    """判断是否为多公司对比文件"""
    # 如果文件名中有多个公司名（用_分隔），且包含已知公司关键词
    company_keywords = [
        "中国人寿", "中国平安", "比亚迪", "贵州茅台", "五粮液",
        "美的集团", "格力电器", "海尔", "招商银行", "工商银行",
        "恒瑞医药", "宁德时代", "隆基", "中际旭创",
    ]
    name = Path(filename).stem
    count = sum(1 for kw in company_keywords if kw in name)
    return count >= 2


def is_single_date_file(filename: str) -> bool:
    """判断是否为单日期文件（如 _20251231-20251231）"""
    name = Path(filename).stem
    match = re.search(r"_(\d{8})-(\d{8})$", name)
    if match:
        return match.group(1) == match.group(2)
    return False


def get_file_timestamp(filename: str) -> str:
    """获取文件时间戳，用于选择最新的文件"""
    name = Path(filename).stem
    match = re.search(r"_(\d{8}_\d{6})$", name)
    if match:
        return match.group(1)
    match = re.search(r"_(\d{8})-(\d{8})$", name)
    if match:
        return match.group(2)  # 使用结束日期
    return "0"


def process_module_folder(folder: Path, company_name: str) -> tuple:
    """
    处理一个模块目录的所有 md 文件
    返回：(时间线DataFrame, 单点数据DataFrame, 对比文件列表)
    """
    if not folder.exists():
        return None, None, []

    # 按指标分组，只保留每个指标的最新时间戳文件
    metric_files = defaultdict(list)  # metric -> [(timestamp, filepath)]
    comparison_files = []  # 多公司对比文件

    for md_file in folder.glob("*.md"):
        if md_file.name.startswith("README"):
            continue

        if is_multi_company_file(md_file.name):
            comparison_files.append(md_file)
            continue

        metric = extract_metric_name(md_file.name, company_name)
        timestamp = get_file_timestamp(md_file.name)
        metric_files[metric].append((timestamp, md_file))

    # 对每个指标，选择最新的文件
    latest_files = {}
    for metric, files in metric_files.items():
        files.sort(key=lambda x: x[0], reverse=True)
        latest_files[metric] = files[0][1]

    # 分成"时间线"和"单点"
    timeline_data = {}  # metric -> DataFrame（多行）
    point_data = {}     # metric -> value（单行）

    for metric, filepath in latest_files.items():
        try:
            content = filepath.read_text(encoding="utf-8")
            headers, rows = parse_md_table(content)
            if not headers or not rows:
                continue

            # 找到"日期"列
            date_col = None
            for i, h in enumerate(headers):
                if h == "日期":
                    date_col = i
                    break
            if date_col is None:
                continue

            # 数据列：排除冗余的股价/市值类列和日期/财报类型等
            data_cols = [(i, h) for i, h in enumerate(headers) if h not in REDUNDANT_COLS]

            if len(rows) == 1:
                # 单点数据：metric 作为 key
                row = rows[0]
                date = row[date_col]
                # 取第一个数据列作为主要值
                for i, col_name in data_cols:
                    if i < len(row) and row[i]:
                        clean_key = clean_col_name(col_name, metric)
                        point_data[clean_key] = {
                            "date": date,
                            "value": row[i],
                            "column": col_name,
                        }
                        break  # 只取第一个有效数据列
            else:
                # 时间线数据：保留所有行，列名清理
                df_rows = []
                for row in rows:
                    d = {"date": row[date_col]}
                    for i, col_name in data_cols:
                        if i < len(row):
                            clean_key = clean_col_name(col_name, metric)
                            d[clean_key] = row[i]
                    df_rows.append(d)
                df = pd.DataFrame(df_rows)
                timeline_data[metric] = df
        except Exception as e:
            print(f"  ⚠️ 解析失败 {filepath.name}: {e}")

    return timeline_data, point_data, comparison_files


def merge_timeline_data(timeline_data: dict) -> pd.DataFrame:
    """将多个指标的时间线合并为一个宽表"""
    if not timeline_data:
        return pd.DataFrame()

    merged = None
    for metric, df in timeline_data.items():
        if df.empty:
            continue

        if merged is None:
            merged = df.copy()
        else:
            # 避免重复列：两边都有的列（除 date 外）用左侧的
            overlapping = set(merged.columns) & set(df.columns) - {"date"}
            if overlapping:
                df = df.drop(columns=list(overlapping))
            if len(df.columns) > 1:  # 至少有 date 和一个数据列
                merged = pd.merge(merged, df, on="date", how="outer")

    if merged is not None:
        merged = merged.sort_values("date", ascending=False).reset_index(drop=True)
        return merged
    return pd.DataFrame()


def try_float(val):
    """尝试转为浮点数"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def is_core_valuation_col(col: str) -> bool:
    """判断是否为核心估值列（排除分位点阈值等常数列）"""
    # 排除分位点阈值列（80%分位点值、50%分位点值、20%分位点值）
    if "分位点值" in col:
        return False
    return True


def format_value(val, is_percent=False):
    """格式化数值显示"""
    f = try_float(val)
    if f is None:
        return str(val) if val else "N/A"
    if abs(f) >= 1e8:
        return f"{f/1e8:.2f}亿"
    if abs(f) >= 1e4:
        return f"{f/1e4:.2f}万"
    if is_percent or (0 < abs(f) < 1 and "率" in str(val)):
        return f"{f*100:.2f}%"
    return f"{f:.4f}" if abs(f) < 100 else f"{f:.2f}"


def build_stats_row(col: str, series: pd.Series, latest_val) -> str:
    """构建统计行"""
    vals = series.apply(try_float).dropna()
    if len(vals) < 2:
        return ""
    cur = try_float(latest_val)
    cur_s = f"{cur:.4f}" if cur is not None else "N/A"
    return f"| {col} | {cur_s} | {vals.mean():.4f} | {vals.median():.4f} | {vals.max():.4f} | {vals.min():.4f} |"


def module_summary_section(title: str, emoji: str, df: pd.DataFrame, with_stats: bool = False, core_filter=None) -> list:
    """生成一个模块的摘要段落"""
    lines = []
    if df is None or df.empty:
        return lines

    latest = df.iloc[0]
    cols = [c for c in df.columns if c != "date"]
    if core_filter:
        cols = [c for c in cols if core_filter(c)]

    lines.append(f"## {emoji} {title}")
    lines.append("")
    lines.append(f"**最新日期**：{latest.get('date', 'N/A')}")
    lines.append("")
    lines.append("| 指标 | 当前值 |")
    lines.append("|------|--------|")
    for col in cols:
        val = latest.get(col)
        if pd.notna(val) and str(val).strip() not in ("", "nan"):
            lines.append(f"| {col} | {val} |")
    lines.append("")

    if with_stats and len(df) > 2:
        lines.append(f"### {title}历史统计")
        lines.append("")
        lines.append("| 指标 | 当前 | 均值 | 中位 | 最高 | 最低 |")
        lines.append("|------|------|------|------|------|------|")
        for col in cols:
            row = build_stats_row(col, df[col], latest.get(col))
            if row:
                lines.append(row)
        lines.append("")

    return lines


def generate_summary(company_name: str, all_data: dict) -> str:
    """生成摘要 md"""
    lines = []
    lines.append(f"# {company_name} 基本面摘要")
    lines.append("")
    lines.append(f"> 最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 估值：带统计
    lines += module_summary_section(
        "估值快照", "📊",
        all_data.get("估值_时间线"),
        with_stats=True,
        core_filter=is_core_valuation_col,
    )

    # 盈利
    lines += module_summary_section(
        "盈利能力", "💰",
        all_data.get("盈利_时间线"),
        with_stats=False,
    )

    # 成长性
    lines += module_summary_section(
        "成长性", "📈",
        all_data.get("成长_时间线"),
        with_stats=False,
    )

    # 现金流
    lines += module_summary_section(
        "现金流", "💵",
        all_data.get("现金流_时间线"),
        with_stats=False,
    )

    # 安全性
    lines += module_summary_section(
        "安全性", "🛡️",
        all_data.get("安全性_时间线"),
        with_stats=False,
    )

    lines.append("---")
    lines.append("")
    lines.append("## 📂 数据文件")
    lines.append("")
    lines.append("详细时间线数据请查看 `历史数据/` 目录下的 CSV 文件：")
    lines.append("")
    lines.append("- `估值.csv` - 估值指标时间线")
    lines.append("- `盈利.csv` - 盈利指标时间线")
    lines.append("- `成长.csv` - 成长性指标时间线")
    lines.append("- `现金流.csv` - 现金流指标时间线")
    lines.append("- `安全性.csv` - 安全性指标时间线")
    lines.append("")

    return "\n".join(lines)


def process_company(company_dir: Path, dry_run: bool = False):
    """处理一家公司"""
    company_name_raw = company_dir.name
    # 去掉编号前缀（如 "01_"）
    company_name = re.sub(r"^\d+_", "", company_name_raw)

    print(f"\n📦 处理: {company_name_raw} ({company_name})")

    base_data_dir = company_dir / "01_基本面数据"
    if not base_data_dir.exists():
        print(f"  ⚠️ 无 01_基本面数据 目录，跳过")
        return

    # 新建历史数据目录
    history_dir = base_data_dir / "历史数据"
    if not dry_run:
        history_dir.mkdir(exist_ok=True)

    all_data = {}  # "估值_时间线" -> DataFrame

    # 处理各模块
    for module_folder, module_name in MODULES.items():
        folder = base_data_dir / module_folder
        if not folder.exists():
            continue

        print(f"  🔍 扫描 {module_folder}...")
        timeline_data, point_data, comparison_files = process_module_folder(folder, company_name)

        if timeline_data:
            merged = merge_timeline_data(timeline_data)
            if not merged.empty:
                all_data[f"{module_name}_时间线"] = merged

                csv_path = history_dir / f"{module_name}.csv"
                if not dry_run:
                    merged.to_csv(csv_path, index=False)
                print(f"    ✓ 合并 {len(timeline_data)} 个指标 → {csv_path.name} ({len(merged)} 行)")

        if point_data:
            # 单点数据合并到一个快照 CSV
            rows = []
            for metric, info in point_data.items():
                rows.append({
                    "date": info["date"],
                    "metric": metric,
                    "value": info["value"],
                })
            point_df = pd.DataFrame(rows)
            csv_path = history_dir / f"{module_name}_快照.csv"
            if not dry_run:
                point_df.to_csv(csv_path, index=False)
            print(f"    ✓ 合并 {len(point_data)} 个单点指标 → {csv_path.name}")

            # 把单点数据也合并到时间线数据中（以 metric 为列名）
            if point_data:
                snapshot_row = {"date": list(point_data.values())[0]["date"]}
                for metric, info in point_data.items():
                    snapshot_row[metric] = info["value"]
                snapshot_df = pd.DataFrame([snapshot_row])
                key = f"{module_name}_快照"
                all_data[key] = snapshot_df

        # 保存对比文件信息
        if comparison_files:
            print(f"    📎 发现 {len(comparison_files)} 个行业对比文件（将保留到 行业对比/）")

    # 处理"最近一月数据"：把它作为数据源整合到各模块的时间线中
    recent_data = all_data.pop("最近一月_时间线", None)
    recent_snapshot = all_data.pop("最近一月_快照", None)

    # 如果估值时间线没有最近一月的高频日线，用"最近一月"补充
    if recent_data is not None:
        if "估值_时间线" in all_data:
            # 合并：优先使用 01_估值分析 的数据，补充近期日线
            pass  # 暂时不合并，因为数据已经足够
        all_data["估值_时间线"] = recent_data if "估值_时间线" not in all_data else all_data["估值_时间线"]

    # 如果单点快照数据（年报）存在，把它合并到盈利/安全性/现金流时间线前
    if recent_snapshot is not None:
        # 年报快照是最新年报数据，值得保留
        snapshot_csv = history_dir / "年报快照.csv"
        if not dry_run:
            recent_snapshot.to_csv(snapshot_csv, index=False)
        print(f"  ✓ 保存年报快照 → 年报快照.csv")

    # 生成摘要.md
    summary = generate_summary(company_name, all_data)
    summary_path = base_data_dir / "摘要.md"
    if not dry_run:
        summary_path.write_text(summary, encoding="utf-8")
    print(f"  ✓ 生成摘要 → 摘要.md")

    # 移动行业对比文件到单独目录
    comparison_dir = base_data_dir / "行业对比"
    for module_folder, module_name in MODULES.items():
        folder = base_data_dir / module_folder
        if not folder.exists():
            continue
        for md_file in list(folder.glob("*.md")):
            if md_file.name.startswith("README"):
                continue
            if is_multi_company_file(md_file.name):
                if not dry_run:
                    comparison_dir.mkdir(exist_ok=True)
                    target = comparison_dir / md_file.name
                    shutil.move(str(md_file), str(target))

    # 删除原始模块目录（除了99_原始数据）
    if not dry_run:
        for module_folder in MODULES:
            folder = base_data_dir / module_folder
            if folder.exists():
                shutil.rmtree(folder)
                print(f"  🗑️  删除 {module_folder}")

    print(f"  ✅ 完成 {company_name_raw}")


def main():
    import sys
    dry_run = "--dry-run" in sys.argv
    only = None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = arg.split("=", 1)[1]

    if dry_run:
        print("🔍 DRY RUN 模式，不会修改文件")

    companies = sorted(COMPANIES_DIR.glob("*"))
    for company_dir in companies:
        if not company_dir.is_dir():
            continue
        if company_dir.name.startswith("_") or company_dir.name.startswith("."):
            continue
        if only and only not in company_dir.name:
            continue
        try:
            process_company(company_dir, dry_run=dry_run)
        except Exception as e:
            print(f"❌ 处理 {company_dir.name} 失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n🎉 全部完成！")


if __name__ == "__main__":
    main()
