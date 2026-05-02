#!/usr/bin/env python3
"""
提取公司档案库中最近一个月的数据
生成新的CSV文件，文件名格式：公司名_数据类型_时间段.csv
使用标准库，无需安装额外依赖
"""

import csv
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

_LIXINGER_SCRIPTS = Path(__file__).resolve().parent / "lixinger-archiver"
if str(_LIXINGER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_LIXINGER_SCRIPTS))
from lixinger_csv_to_md import write_md_sidecar

# 设置最近一个月的时间范围（滚动）
# 说明：不假设“今天”一定有交易数据；实际切片范围以文件中命中的最小/最大日期为准。
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=30)

print(f"提取数据时间范围：{START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}")
print("=" * 60)

# 路径（自动计算项目根目录，脚本在 .tools/ 子目录）
_script_dir = Path(__file__).resolve().parent.parent
root = _script_dir
base_path = root / "02_companies"
output_dir = root / ".temp/recent_month_extract"
output_dir.mkdir(parents=True, exist_ok=True)

def discover_companies() -> list[str]:
    """自动发现公司目录，形如 07_美的集团。"""
    if not base_path.is_dir():
        return []
    companies: list[str] = []
    for p in sorted(base_path.iterdir()):
        if p.is_dir() and re.match(r"^\d{2}_.+$", p.name):
            companies.append(p.name)
    return companies

companies = discover_companies()
if not companies:
    raise SystemExit(f"未找到公司目录：{base_path}")

for company in companies:
    (output_dir / company).mkdir(exist_ok=True)

# 统计信息
stats = {
    "total_files": 0,
    "processed_files": 0,
    "skipped_files": 0,
    "companies": {}
}

def parse_date(date_str):
    """解析日期字符串"""
    formats = ['%Y-%m-%d', '%Y/%m/%d', '%Y%m%d']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def extract_data_type_from_filename(filename, company_short):
    """从文件名中提取数据类型"""
    basename = os.path.basename(filename)
    basename = basename.replace('.csv', '')
    
    # 移除日期部分
    basename = re.sub(r'_\d{8}_\d{6}$', '', basename)
    basename = re.sub(r'_\d{8}$', '', basename)
    
    # 移除公司名前缀（包括对比公司）
    company_prefixes = [
        company_short,
        "新华保险", "中国人寿", "中国平安",
        "三美股份", "巨化股份", "昊华科技",
        "蜜雪集团", "古茗", "霸王集团",
        "中国中车",
        "贵州茅台", "五粮液", "山西汾酒",
        "美的集团",
        "立讯精密",
        "比亚迪"
    ]
    
    for prefix in company_prefixes:
        if basename.startswith(prefix + "_"):
            basename = basename[len(prefix)+1:]
    
    # 移除行业分类前缀
    industry_prefixes = ["保险_", "白酒_", "氟化工及制冷剂_", "非酒精饮料_", 
                         "铁路设备_", "电子零部件制造_", "空调_"]
    for prefix in industry_prefixes:
        basename = basename.replace(prefix, "")
    
    # 移除"合并报表"后缀
    basename = basename.replace("_合并报表", "")
    
    return basename

def process_csv_file(filepath: str, company_name: str, company_short: str):
    """处理单个CSV文件，提取最近一个月的数据"""
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            headers = next(reader)
            
            # 查找日期列
            date_col_idx = None
            for i, h in enumerate(headers):
                if h.strip() == '日期':
                    date_col_idx = i
                    break
            
            if date_col_idx is None:
                return None, "无日期列"
            
            dated_rows: list[tuple[datetime, list[str]]] = []
            window_rows: list[list[str]] = []

            for row in reader:
                if len(row) <= date_col_idx:
                    continue
                date_str = row[date_col_idx].strip()
                date_obj = parse_date(date_str)
                if not date_obj:
                    continue
                dated_rows.append((date_obj, row))
                if START_DATE <= date_obj <= END_DATE:
                    window_rows.append(row)

            if not dated_rows:
                return None, "无可解析日期数据"

            # 优先使用“滚动窗口”的最近30天；若窗口内为空，则回退到“文件内最后一个月可用数据”。
            if window_rows:
                recent_rows = window_rows
            else:
                dated_rows.sort(key=lambda x: x[0])
                last_date = dated_rows[-1][0]
                fallback_start = last_date - timedelta(days=30)
                recent_rows = [r for (d, r) in dated_rows if fallback_start <= d <= last_date]
                if not recent_rows:
                    recent_rows = [r for (_, r) in dated_rows[-30:]]

            # 计算实际输出日期范围
            min_date = None
            max_date = None
            for row in recent_rows:
                d = parse_date(row[date_col_idx].strip())
                if not d:
                    continue
                if min_date is None or d < min_date:
                    min_date = d
                if max_date is None or d > max_date:
                    max_date = d

            if min_date is None or max_date is None:
                return None, "无有效日期范围"
            
            # 生成输出文件名
            data_type = extract_data_type_from_filename(str(filepath), company_short)
            
            # 清理数据类型名称
            data_type = data_type.strip('_')
            
            # 新文件名格式
            date_range = f"{min_date.strftime('%Y%m%d')}-{max_date.strftime('%Y%m%d')}"
            output_filename = f"{company_short}_{data_type}_{date_range}.csv"
            output_path = output_dir / company_name / output_filename
            
            # 保存数据
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as out_f:
                writer = csv.writer(out_f)
                writer.writerow(headers)
                writer.writerows(recent_rows)

            write_md_sidecar(output_path)

            return {
                "output_file": output_filename,
                "records": len(recent_rows),
                "date_range": f"{min_date.strftime('%Y-%m-%d')} 至 {max_date.strftime('%Y-%m-%d')}"
            }, None
            
    except Exception as e:
        return None, str(e)

def clean_company_output(company: str, company_short: str):
    """清理公司在输出目录下的旧切片，避免遗留文件混入。"""
    d = output_dir / company
    if not d.is_dir():
        return
    for p in d.glob("*.csv"):
        p.unlink(missing_ok=True)
    for p in d.glob(f"{company_short}_*.md"):
        p.unlink(missing_ok=True)
    # README 后面会重建
    (d / "README.md").unlink(missing_ok=True)

def write_readme(target_dir: Path, company: str, start: datetime, end: datetime, files: list[dict]):
    target_dir.mkdir(parents=True, exist_ok=True)
    readme = target_dir / "README.md"
    file_lines = "\n".join([f"- {f['output_file']}（{f['records']}条，{f['date_range']}）" for f in files]) or "- （本次无输出文件）"
    content = "\n".join([
        f"# {company} 最近一月数据",
        "",
        f"- 时间窗口（滚动）：{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}",
        "- 数据来源：公司档案库各模块 CSV（01-06）",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 文件列表",
        file_lines,
        "",
    ])
    readme.write_text(content, encoding="utf-8")

def sync_back_to_archive(company: str, company_short: str):
    """把输出目录的切片覆盖回写到公司档案库 00_最近一月数据。"""
    src_dir = output_dir / company
    dst_dir = base_path / company / "01_基本面数据" / "00_最近一月数据"
    dst_dir.mkdir(parents=True, exist_ok=True)

    src_files = list(src_dir.glob(f"{company_short}_*.csv"))
    if not src_files:
        # 没有新切片则不覆盖，避免误删历史文件
        return

    # 清理旧CSV/MD，避免混入
    for p in dst_dir.glob(f"{company_short}_*.csv"):
        p.unlink(missing_ok=True)
    for p in dst_dir.glob(f"{company_short}_*.md"):
        p.unlink(missing_ok=True)

    for p in src_files:
        shutil.copy2(p, dst_dir / p.name)

    for p in src_dir.glob(f"{company_short}_*.md"):
        shutil.copy2(p, dst_dir / p.name)

    # 同步 README
    src_readme = src_dir / "README.md"
    if src_readme.exists():
        shutil.copy2(src_readme, dst_dir / "README.md")

for company in companies:
    company_path = base_path / company
    if not company_path.exists():
        print(f"跳过 {company}（目录不存在）")
        continue
    
    print(f"\n处理 {company}...")
    company_short = company.split('_')[1] if '_' in company else company
    clean_company_output(company, company_short)
    
    company_stats = {
        "total": 0,
        "processed": 0,
        "skipped": 0,
        "files": []
    }
    files_by_name: dict[str, dict] = {}
    
    # 查找所有CSV文件
    # 只处理标准模块目录下的CSV，避免把 00_最近一月数据 / 99_其他 的原始窄表也一起切片
    modules = ("01_估值分析", "02_盈利分析", "03_成长性分析", "04_现金流分析", "05_安全性分析", "06_行业对比")
    csv_files: list[Path] = []
    for mod in modules:
        d = company_path / "01_基本面数据" / mod
        if d.is_dir():
            csv_files.extend(d.rglob("*.csv"))
    
    for csv_file in csv_files:
        stats["total_files"] += 1
        company_stats["total"] += 1
        
        result, error = process_csv_file(str(csv_file), company, company_short)
        
        if result:
            stats["processed_files"] += 1
            company_stats["processed"] += 1
            # 同名输出文件只保留一份（避免 README 重复）
            files_by_name[result["output_file"]] = result
        else:
            stats["skipped_files"] += 1
            company_stats["skipped"] += 1
    
    company_stats["files"] = [files_by_name[k] for k in sorted(files_by_name.keys())]
    stats["companies"][company] = company_stats
    print(f"  完成：处理了 {company_stats['processed']}/{company_stats['total']} 个文件")

    # README + 回写
    write_readme(output_dir / company, company, START_DATE, END_DATE, company_stats["files"])
    sync_back_to_archive(company, company_short)

# 输出统计信息
print("\n" + "=" * 60)
print("处理完成统计")
print("=" * 60)
print(f"总文件数：{stats['total_files']}")
print(f"成功处理：{stats['processed_files']}")
print(f"跳过文件：{stats['skipped_files']}")
print(f"\n输出目录：{output_dir}")

print("\n各公司处理详情：")
for company, company_stats in stats["companies"].items():
    print(f"\n{company}: {company_stats['processed']}/{company_stats['total']} 个文件")
    # 列出前5个文件
    for f in company_stats["files"][:5]:
        print(f"  ✓ {f['output_file']} ({f['records']}条)")
    if len(company_stats["files"]) > 5:
        print(f"  ... 还有 {len(company_stats['files']) - 5} 个文件")
