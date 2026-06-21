#!/usr/bin/env python3
"""
ETF 成分股变化对比分析工具

用于追踪和分析 ETF 成分股的变化，识别行业轮动信号

用法:
  python3 compare_etf_changes.py --compare 新能源 消费
  python3 compare_etf_changes.py --trend 新能源
  python3 compare_etf_changes.py --all-comparison
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def load_theme_data(theme_dir):
    """加载主题的数据"""
    constituents_path = theme_dir / "constituents.csv"
    fundamentals_path = theme_dir / "fundamentals.csv"
    config_path = theme_dir.parent.parent / "投资主题" / theme_dir.name / "etf_config.json"

    data = {}

    # 加载成分股
    if constituents_path.exists():
        with open(constituents_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("代码", "").strip()
                if code:
                    data[code] = {
                        "name": row.get("名称", ""),
                        "weight": float(row.get("权重(%)", 0)) if row.get("权重(%)") else 0,
                    }

    # 加载财务数据
    if fundamentals_path.exists():
        with open(fundamentals_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("代码", "").strip()
                if code and code in data:
                    data[code].update({
                        "pe": float(row.get("PE", 0)) if row.get("PE") else 0,
                        "pb": float(row.get("PB", 0)) if row.get("PB") else 0,
                        "dyr": float(row.get("股息率(%)", 0)) if row.get("股息率(%)") else 0,
                    })

    return data

def analyze_theme_composition(theme_name, output_base):
    """分析单个主题的成分股构成"""
    theme_dir = output_base / "投资主题" / theme_name

    if not theme_dir.exists():
        print(f"❌ 主题不存在: {theme_name}")
        return None

    data = load_theme_data(theme_dir)

    if not data:
        print(f"❌ 无数据: {theme_name}")
        return None

    # 统计分析
    total_weight = sum(s.get("weight", 0) for s in data.values())
    top_10_weight = sorted(data.values(), key=lambda x: x.get("weight", 0), reverse=True)[:10]
    top_10_total = sum(s.get("weight", 0) for s in top_10_weight)

    analysis = {
        "theme": theme_name,
        "stocks_count": len(data),
        "top_10_count": len([s for s in top_10_weight if s.get("weight", 0) > 0]),
        "top_10_weight_pct": (top_10_total / total_weight * 100) if total_weight > 0 else 0,
        "avg_pe": sum(s.get("pe", 0) for s in data.values() if s.get("pe", 0) > 0) / len([s for s in data.values() if s.get("pe", 0) > 0]) if any(s.get("pe", 0) > 0 for s in data.values()) else 0,
        "avg_weight": total_weight / len(data) if data else 0,
        "top_10": top_10_weight,
    }

    return analysis

def compare_themes(theme_names, output_base):
    """对比多个主题"""
    analyses = {}

    for theme in theme_names:
        analysis = analyze_theme_composition(theme, output_base)
        if analysis:
            analyses[theme] = analysis

    if not analyses:
        print("❌ 无有效的主题数据")
        return

    print("\n" + "=" * 80)
    print(f"主题对比分析: {', '.join(theme_names)}")
    print("=" * 80)

    # 基本对比
    print("\n📊 基本构成对比:")
    print(f"\n{'主题':<15} {'成分股数':<12} {'TOP10数':<12} {'TOP10占比':<12} {'平均PE':<12} {'平均权重':<12}")
    print("-" * 75)

    for theme, analysis in analyses.items():
        print(f"{theme:<15} {analysis['stocks_count']:<12} {analysis['top_10_count']:<12} {analysis['top_10_weight_pct']:>10.1f}% {analysis['avg_pe']:>10.2f} {analysis['avg_weight']:>10.2f}%")

    # TOP 成分股对比
    print("\n\n🏆 TOP 10 成分股对比:")
    print("-" * 80)

    all_top_stocks = defaultdict(list)
    for theme, analysis in analyses.items():
        for i, stock in enumerate(analysis['top_10'], 1):
            all_top_stocks[stock.get('name', stock.get('code', ''))].append({
                'theme': theme,
                'rank': i,
                'weight': stock.get('weight', 0)
            })

    # 找出出现在多个主题TOP10中的股票
    shared_stocks = {name: data for name, data in all_top_stocks.items() if len(data) > 1}

    if shared_stocks:
        print(f"\n在多个主题TOP10中出现的股票:")
        for stock_name, appearances in sorted(shared_stocks.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"\n  {stock_name}:")
            for app in appearances:
                print(f"    - {app['theme']}: TOP {app['rank']} (权重: {app['weight']:.2f}%)")
    else:
        print("\n没有股票同时出现在多个主题的TOP10中")

    return analyses

def generate_comparison_report(analyses, output_path):
    """生成对比报告"""
    report = f"""# ETF 主题对比分析报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 主题概览

"""

    for theme, analysis in analyses.items():
        report += f"""
### {theme}

- **成分股总数**: {analysis['stocks_count']}
- **TOP 10 成分股数**: {analysis['top_10_count']}
- **TOP 10 权重占比**: {analysis['top_10_weight_pct']:.1f}%
- **平均 PE**: {analysis['avg_pe']:.2f}
- **平均权重**: {analysis['avg_weight']:.2f}%

"""

    report += """
---

## 💡 分析结论

通过对比可以看出：

1. **集中度**: TOP 10 权重占比越高，主题越集中
2. **估值**: 平均 PE 反映整个主题的估值水位
3. **权重分布**: 均衡还是集中反映市场对该主题的看法

建议结合权重变化和估值变化来识别行业轮动机会。

"""

    return report

def main():
    parser = argparse.ArgumentParser(description="ETF 成分股变化对比分析")
    parser.add_argument("--compare", nargs="+", help="对比多个主题 (e.g., 新能源 消费)")
    parser.add_argument("--trend", help="分析单个主题的成分股趋势")
    parser.add_argument("--all-comparison", action="store_true", help="对比所有主题")
    parser.add_argument("--output-dir", default="03_macro/01_ETF分析工具",
                       help="输出目录基路径")

    args = parser.parse_args()

    output_base = Path(__file__).parent.parent / args.output_dir

    if args.all_comparison:
        # 获取所有主题
        themes_dir = output_base / "投资主题"
        if themes_dir.exists():
            themes = [d.name for d in themes_dir.iterdir() if d.is_dir()]
            themes.sort()
            analyses = compare_themes(themes, output_base)

            if analyses:
                report = generate_comparison_report(analyses, None)
                print("\n" + report)

    elif args.compare:
        analyses = compare_themes(args.compare, output_base)

    elif args.trend:
        print(f"\n分析主题: {args.trend}")
        analysis = analyze_theme_composition(args.trend, output_base)

        if analysis:
            print(f"\n成分股构成:")
            print(f"  总数: {analysis['stocks_count']}")
            print(f"  TOP 10 占比: {analysis['top_10_weight_pct']:.1f}%")
            print(f"  平均 PE: {analysis['avg_pe']:.2f}")

            print(f"\nTOP 10 成分股:")
            for i, stock in enumerate(analysis['top_10'], 1):
                print(f"  {i:2d}. {stock.get('name', stock.get('code', ''))} ({stock.get('code', '')})")
                print(f"      权重: {stock.get('weight', 0):.2f}%")

    else:
        print("❌ 错误: 需要指定 --compare, --trend, 或 --all-comparison")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
