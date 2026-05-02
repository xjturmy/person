#!/usr/bin/env python3
"""
生成 ETF 分析报告脚本

自动读取配置、成分股、财务数据，生成完整的 ETF 分析报告
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime

def load_etf_config(config_path):
    """加载 ETF 配置文件"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 加载配置失败: {str(e)}")
        return None

def load_constituents_and_fundamentals(theme_dir):
    """加载成分股和财务数据"""
    constituents_path = theme_dir / "constituents.csv"
    fundamentals_path = theme_dir / "fundamentals.csv"

    stocks = {}

    # 加载财务数据（优先级高）
    if fundamentals_path.exists():
        with open(fundamentals_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("代码", "").strip()
                if code:
                    stocks[code] = {
                        "name": row.get("名称", ""),
                        "sp": float(row.get("股价", 0)) if row.get("股价") else 0,
                        "pe_ttm": float(row.get("PE", 0)) if row.get("PE") else 0,
                        "pb": float(row.get("PB", 0)) if row.get("PB") else 0,
                        "dyr": float(row.get("股息率(%)", 0)) if row.get("股息率(%)") else 0,
                        "roe": float(row.get("ROE(%)", 0)) if row.get("ROE(%)") else 0,
                        "roa": float(row.get("ROA(%)", 0)) if row.get("ROA(%)") else 0,
                        "weight": 0,
                    }

    # 加载成分股权重
    if constituents_path.exists():
        with open(constituents_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("代码", "").strip()
                weight = float(row.get("权重(%)", 0)) if row.get("权重(%)") else 0

                if code not in stocks:
                    stocks[code] = {"name": row.get("名称", "")}

                stocks[code]["weight"] = weight

    return stocks

def calculate_statistics(stocks):
    """计算统计数据"""
    if not stocks:
        return {}

    pe_values = [s.get('pe_ttm', 0) for s in stocks.values() if s.get('pe_ttm', 0) > 0]
    pb_values = [s.get('pb', 0) for s in stocks.values() if s.get('pb', 0) > 0]
    dyr_values = [s.get('dyr', 0) for s in stocks.values()]
    roe_values = [s.get('roe', 0) for s in stocks.values() if s.get('roe', 0) > 0]

    stats = {}

    if pe_values:
        stats['min_pe'] = min(pe_values)
        stats['max_pe'] = max(pe_values)
        stats['avg_pe'] = sum(pe_values) / len(pe_values)
        stats['count_low_pe'] = len([x for x in pe_values if x < 15])
        stats['count_mid_pe'] = len([x for x in pe_values if 15 <= x < 25])
        stats['count_high_pe'] = len([x for x in pe_values if x >= 25])
        total = len(pe_values)
        stats['pct_low_pe'] = stats['count_low_pe'] / total * 100
        stats['pct_mid_pe'] = stats['count_mid_pe'] / total * 100
        stats['pct_high_pe'] = stats['count_high_pe'] / total * 100
    else:
        stats.update({'min_pe': 0, 'max_pe': 0, 'avg_pe': 0, 'count_low_pe': 0,
                      'count_mid_pe': 0, 'count_high_pe': 0, 'pct_low_pe': 0,
                      'pct_mid_pe': 0, 'pct_high_pe': 0})

    if pb_values:
        stats['min_pb'] = min(pb_values)
        stats['max_pb'] = max(pb_values)
        stats['avg_pb'] = sum(pb_values) / len(pb_values)
    else:
        stats.update({'min_pb': 0, 'max_pb': 0, 'avg_pb': 0})

    if dyr_values:
        stats['min_dyr'] = min(dyr_values)
        stats['max_dyr'] = max(dyr_values)
        stats['avg_dyr'] = sum(dyr_values) / len(dyr_values)
        stats['count_high_div'] = len([x for x in dyr_values if x > 3])
        stats['count_mid_div'] = len([x for x in dyr_values if 1 <= x <= 3])
        stats['count_low_div'] = len([x for x in dyr_values if x < 1])
    else:
        stats.update({'min_dyr': 0, 'max_dyr': 0, 'avg_dyr': 0, 'count_high_div': 0,
                      'count_mid_div': 0, 'count_low_div': 0})

    if roe_values:
        stats['min_roe'] = min(roe_values)
        stats['max_roe'] = max(roe_values)
        stats['avg_roe'] = sum(roe_values) / len(roe_values)
    else:
        stats.update({'min_roe': 0, 'max_roe': 0, 'avg_roe': 0})

    return stats

def generate_report(theme_name, output_base, config, stocks, stats):
    """生成报告内容"""
    # 排序成分股
    sorted_stocks = sorted(stocks.values(), key=lambda x: x.get('weight', 0), reverse=True)
    top_stocks = sorted_stocks[:10]

    # 生成 ETF 表格
    etf_table = ""
    for etf in config.get('etfs', []):
        etf_table += f"| {etf.get('code')} | {etf.get('name')} | {etf.get('manager', '')} | {etf.get('index_name', '')} | {etf.get('inception_date', '')} |\n"

    # 生成成分股表格
    stock_table = ""
    for i, stock in enumerate(top_stocks, 1):
        stock_table += f"| {i} | {stock.get('code', '')} | {stock.get('name', '')} | {stock.get('weight', 0):.2f} | {stock.get('pe_ttm', 0):.2f} | {stock.get('pb', 0):.2f} | {stock.get('dyr', 0):.2f} |\n"

    # 生成估值评价
    avg_pe = stats.get('avg_pe', 0)
    if avg_pe < 15:
        valuation = "**✅ 低估**: 平均 PE 为 {:.2f}，处于低位".format(avg_pe)
    elif avg_pe < 20:
        valuation = "**✅ 合理**: 平均 PE 为 {:.2f}，处于合理范围".format(avg_pe)
    elif avg_pe < 30:
        valuation = "**⚠️  偏高**: 平均 PE 为 {:.2f}，处于偏高位置".format(avg_pe)
    else:
        valuation = "**❌ 高估**: 平均 PE 为 {:.2f}，处于高位".format(avg_pe)

    report = f"""# {theme_name} ETF 综合分析报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据来源**: 本地 ETF 配置 + 成分股 + 财务数据

---

## 📊 概览

### 主题信息
- **主题名称**: {theme_name}
- **包含 ETF 数**: {len(config.get('etfs', []))}
- **总成分股数**: {len(stocks)}
- **平均 PE**: {stats.get('avg_pe', 0):.2f}
- **平均 PB**: {stats.get('avg_pb', 0):.2f}

### ETF 列表

| 代码 | 名称 | 管理公司 | 跟踪指数 | 成立日期 |
|------|------|---------|---------|---------|
{etf_table}

---

## 📈 成分股分析

### 成分股权重分布 TOP 10

| 排名 | 股票代码 | 股票名称 | 权重(%) | PE | PB | 股息率(%) |
|------|---------|---------|---------|----|----|-----------|
{stock_table}

### 成分股财务指标统计

| 指标 | 最小值 | 平均值 | 最大值 |
|------|--------|--------|--------|
| PE-TTM | {stats.get('min_pe', 0):.2f} | {stats.get('avg_pe', 0):.2f} | {stats.get('max_pe', 0):.2f} |
| PB | {stats.get('min_pb', 0):.2f} | {stats.get('avg_pb', 0):.2f} | {stats.get('max_pb', 0):.2f} |
| 股息率(%) | {stats.get('min_dyr', 0):.2f} | {stats.get('avg_dyr', 0):.2f} | {stats.get('max_dyr', 0):.2f} |
| ROE(%) | {stats.get('min_roe', 0):.2f} | {stats.get('avg_roe', 0):.2f} | {stats.get('max_roe', 0):.2f} |

### 成分股分类统计

**按 PE 分布:**
- PE < 15: {stats.get('count_low_pe', 0)} 个 ({stats.get('pct_low_pe', 0):.1f}%)
- PE 15-25: {stats.get('count_mid_pe', 0)} 个 ({stats.get('pct_mid_pe', 0):.1f}%)
- PE > 25: {stats.get('count_high_pe', 0)} 个 ({stats.get('pct_high_pe', 0):.1f}%)

**按股息率分布:**
- 高收益 (> 3%): {stats.get('count_high_div', 0)} 个
- 中等收益 (1-3%): {stats.get('count_mid_div', 0)} 个
- 低收益 (< 1%): {stats.get('count_low_div', 0)} 个

---

## 💡 投资建议

### 当前估值评价

{valuation}

### 成分股质量评价

- **盈利能力**: 平均 ROE {stats.get('avg_roe', 0):.2f}%
- **现金分配**: 平均股息率 {stats.get('avg_dyr', 0):.2f}%
- **财务杠杆**: 平均 PB {stats.get('avg_pb', 0):.2f}

---

**报告版本**: v1.0
**更新频率**: 按需
**数据质量**: 样本数据（建议使用真实数据源更新）

"""

    return report

def generate_report_for_theme(theme_name, output_base):
    """为单个主题生成报告"""
    theme_dir = Path(output_base) / "投资主题" / theme_name
    config_path = theme_dir / "etf_config.json"

    # 加载配置
    config = load_etf_config(config_path)
    if not config:
        return False

    # 加载数据
    stocks = load_constituents_and_fundamentals(theme_dir)
    stats = calculate_statistics(stocks)

    # 生成报告
    report = generate_report(theme_name, output_base, config, stocks, stats)

    # 保存报告
    report_path = theme_dir / "分析报告.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    return True

def main():
    parser = argparse.ArgumentParser(description="生成ETF分析报告")
    parser.add_argument("--theme", help="主题名称")
    parser.add_argument("--all", action="store_true", help="生成所有主题的报告")
    parser.add_argument("--output-dir", default="03_macro/01_ETF分析工具",
                       help="输出目录基路径")

    args = parser.parse_args()

    output_base = Path(__file__).parent.parent / args.output_dir

    themes = []
    if args.all:
        themes_dir = output_base / "投资主题"
        if themes_dir.exists():
            themes = [d.name for d in themes_dir.iterdir() if d.is_dir()]
            themes.sort()
    elif args.theme:
        themes = [args.theme]
    else:
        print("❌ 错误: 需要指定 --theme 或 --all")
        parser.print_help()
        sys.exit(1)

    print("=" * 80)
    print("生成 ETF 分析报告")
    print("=" * 80)

    success_count = 0

    for theme in themes:
        print(f"\n📝 生成报告: {theme}...", end=" ")

        if generate_report_for_theme(theme, output_base):
            print("✅")
            success_count += 1
        else:
            print("❌")

    print("\n" + "=" * 80)
    print(f"✅ 完成: {success_count}/{len(themes)} 个主题的报告已生成")
    print("=" * 80)

    return 0 if success_count == len(themes) else 1

if __name__ == "__main__":
    sys.exit(main())
