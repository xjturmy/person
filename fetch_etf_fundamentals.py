#!/usr/bin/env python3
"""
获取 ETF 成分股财务数据的脚本

支持三种数据源：
  1. Tushare（推荐，需要Token）
  2. 理杏仁API（可选）
  3. 本地样本数据（演示用）

用法:
  python3 fetch_etf_fundamentals.py --all --source sample
  python3 fetch_etf_fundamentals.py --theme 新能源 --source tushare --token YOUR_TUSHARE_TOKEN
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False

# 样本财务数据
SAMPLE_FUNDAMENTALS = {
    "300750": {"name": "宁德时代", "sp": 245.30, "pe_ttm": 25.3, "pb": 4.2, "ps_ttm": 3.1, "dyr": 0.5, "roe": 15.2, "roa": 8.5},
    "300014": {"name": "亿纬锂能", "sp": 68.20, "pe_ttm": 18.5, "pb": 3.1, "ps_ttm": 2.5, "dyr": 2.1, "roe": 12.3, "roa": 6.8},
    "002594": {"name": "比亚迪", "sp": 185.60, "pe_ttm": 22.1, "pb": 3.8, "ps_ttm": 1.9, "dyr": 1.2, "roe": 14.5, "roa": 7.2},
    "688981": {"name": "中芯国际", "sp": 156.80, "pe_ttm": 28.5, "pb": 2.8, "ps_ttm": 3.2, "dyr": 0.8, "roe": 10.2, "roa": 5.3},
    "300024": {"name": "机器人", "sp": 38.45, "pe_ttm": 32.1, "pb": 3.5, "ps_ttm": 2.1, "dyr": 0.2, "roe": 11.5, "roa": 4.2},
    "600519": {"name": "贵州茅台", "sp": 1520.00, "pe_ttm": 45.2, "pb": 15.8, "ps_ttm": 8.5, "dyr": 2.8, "roe": 35.2, "roa": 18.5},
    "000858": {"name": "五粮液", "sp": 425.30, "pe_ttm": 35.8, "pb": 8.2, "ps_ttm": 4.5, "dyr": 1.5, "roe": 22.8, "roa": 12.1},
    "601398": {"name": "工商银行", "sp": 5.28, "pe_ttm": 5.2, "pb": 0.68, "ps_ttm": 1.2, "dyr": 4.2, "roe": 13.2, "roa": 1.1},
    "300142": {"name": "沃森生物", "sp": 28.50, "pe_ttm": 35.2, "pb": 4.5, "ps_ttm": 2.8, "dyr": 0.0, "roe": 8.5, "roa": 4.2},
    "603259": {"name": "药明康德", "sp": 92.30, "pe_ttm": 28.1, "pb": 3.2, "ps_ttm": 2.5, "dyr": 0.2, "roe": 10.5, "roa": 5.8},
    "688363": {"name": "华熙生物", "sp": 52.80, "pe_ttm": 42.5, "pb": 5.2, "ps_ttm": 3.8, "dyr": 0.0, "roe": 6.2, "roa": 3.5},
    "300003": {"name": "乐普医疗", "sp": 38.20, "pe_ttm": 32.8, "pb": 3.8, "ps_ttm": 2.1, "dyr": 0.5, "roe": 9.5, "roa": 4.2},
    "002521": {"name": "浩宁医疗", "sp": 45.60, "pe_ttm": 38.5, "pb": 4.2, "ps_ttm": 2.8, "dyr": 0.0, "roe": 8.2, "roa": 3.8},
    "601988": {"name": "中国银行", "sp": 3.45, "pe_ttm": 4.8, "pb": 0.55, "ps_ttm": 0.95, "dyr": 5.2, "roe": 12.5, "roa": 0.9},
    "601328": {"name": "交通银行", "sp": 6.28, "pe_ttm": 6.2, "pb": 0.72, "ps_ttm": 1.1, "dyr": 4.5, "roe": 11.8, "roa": 0.85},
    "000651": {"name": "格力电器", "sp": 28.35, "pe_ttm": 12.5, "pb": 1.8, "ps_ttm": 0.85, "dyr": 3.2, "roe": 18.5, "roa": 9.2},
    "600048": {"name": "保利发展", "sp": 15.80, "pe_ttm": 8.5, "pb": 0.95, "ps_ttm": 0.45, "dyr": 2.8, "roe": 11.2, "roa": 3.5},
    "600100": {"name": "同仁堂", "sp": 32.20, "pe_ttm": 28.5, "pb": 3.2, "ps_ttm": 2.1, "dyr": 1.2, "roe": 9.8, "roa": 4.5},
    "601857": {"name": "中国石油", "sp": 6.48, "pe_ttm": 5.2, "pb": 0.58, "ps_ttm": 0.8, "dyr": 6.5, "roe": 10.2, "roa": 2.1},
    "600028": {"name": "中国石化", "sp": 5.45, "pe_ttm": 4.8, "pb": 0.52, "ps_ttm": 0.75, "dyr": 7.2, "roe": 9.8, "roa": 1.8},
    "601088": {"name": "中国神华", "sp": 32.80, "pe_ttm": 6.5, "pb": 0.85, "ps_ttm": 1.1, "dyr": 5.8, "roe": 13.5, "roa": 5.2},
}

def load_constituents(constituents_path):
    """从CSV加载成分股列表"""
    if not constituents_path.exists():
        return []

    stocks = {}
    try:
        with open(constituents_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("代码", "").strip()
                name = row.get("名称", "").strip()
                if code:
                    stocks[code] = name
    except Exception as e:
        print(f"⚠️  读取成分股文件失败: {str(e)}")
        return []

    return stocks

def get_fundamentals_tushare(stock_codes, api):
    """使用Tushare获取财务数据"""
    try:
        results = {}
        for code in stock_codes:
            df = api.daily_basic(ts_code=f"{code[-6:]}", fields='ts_code,trade_date,close,pe,pb,ps,dv_yield')
            if not df.empty:
                latest = df.iloc[0]
                results[code] = {
                    "sp": float(latest['close']) if 'close' in latest else 0,
                    "pe_ttm": float(latest['pe']) if 'pe' in latest else 0,
                    "pb": float(latest['pb']) if 'pb' in latest else 0,
                    "ps_ttm": float(latest['ps']) if 'ps' in latest else 0,
                    "dyr": float(latest['dv_yield']) if 'dv_yield' in latest else 0,
                    "roe": 0,
                    "roa": 0
                }
        return results
    except Exception as e:
        print(f"    ⚠️  Tushare获取失败: {str(e)[:80]}")
        return {}

def get_fundamentals_sample(stock_codes):
    """使用本地样本数据"""
    results = {}
    for code in stock_codes:
        if code in SAMPLE_FUNDAMENTALS:
            results[code] = SAMPLE_FUNDAMENTALS[code]
    return results

def save_fundamentals_csv(output_path, stocks, fundamentals):
    """保存财务数据为CSV"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = ["代码", "名称", "股价", "PE", "PB", "PS", "股息率(%)", "ROE(%)", "ROA(%)"]

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)

        for code, name in stocks.items():
            data = fundamentals.get(code, {})

            row = [
                code,
                data.get("name", name),
                f"{data.get('sp', 0):.2f}",
                f"{data.get('pe_ttm', 0):.2f}",
                f"{data.get('pb', 0):.2f}",
                f"{data.get('ps_ttm', 0):.2f}",
                f"{data.get('dyr', 0):.2f}",
                f"{data.get('roe', 0):.2f}",
                f"{data.get('roa', 0):.2f}"
            ]
            w.writerow(row)

    return True

def process_theme(theme_name, api, source, output_base):
    """处理单个主题的财务数据"""
    theme_dir = Path(output_base) / "投资主题" / theme_name
    constituents_path = theme_dir / "constituents.csv"
    fundamentals_path = theme_dir / "fundamentals.csv"

    print(f"\n📈 处理主题: {theme_name}", end=" ")

    # 加载成分股
    stocks = load_constituents(constituents_path)
    if not stocks:
        print(f"❌ (成分股列表不存在或为空)")
        return False

    stock_codes = list(stocks.keys())
    print(f"(共 {len(stock_codes)} 个成分股)")
    print("-" * 80)

    # 获取财务数据
    all_fundamentals = {}
    batch_size = 50

    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        print(f"  第 {batch_num} 批 ({len(batch)} 个股票)...", end=" ")

        if source == "tushare" and api:
            fundamentals = get_fundamentals_tushare(batch, api)
        else:
            fundamentals = get_fundamentals_sample(batch)

        if fundamentals:
            all_fundamentals.update(fundamentals)
            print(f"✅ ({len(fundamentals)}个)")
        else:
            print(f"⚠️  无数据")

        time.sleep(1)

    # 保存数据
    if all_fundamentals:
        if save_fundamentals_csv(fundamentals_path, stocks, all_fundamentals):
            print(f"\n  ✅ 已保存: {fundamentals_path}")
            print(f"     包含 {len(all_fundamentals)} 个成分股的财务数据")
            return True
        else:
            print(f"\n  ❌ 保存失败")
            return False
    else:
        print(f"\n  ⚠️  未获取到财务数据")
        return False

def main():
    parser = argparse.ArgumentParser(description="获取ETF成分股财务数据")
    parser.add_argument("--theme", help="主题名称 (新能源/机器人/消费/芯片半导体)")
    parser.add_argument("--all", action="store_true", help="处理所有主题")
    parser.add_argument("--source", default="sample", choices=["tushare", "sample"],
                       help="数据源 (默认: sample)")
    parser.add_argument("--token", help="Tushare API Token")
    parser.add_argument("--output-dir", default="03_macro/01_ETF分析工具",
                       help="输出目录基路径")

    args = parser.parse_args()

    output_base = Path(__file__).parent.parent / args.output_dir

    themes = []
    if args.all:
        themes = ["新能源", "机器人", "消费", "芯片半导体"]
    elif args.theme:
        themes = [args.theme]
    else:
        print("❌ 错误: 需要指定 --theme 或 --all")
        parser.print_help()
        sys.exit(1)

    print("=" * 80)
    print("ETF 成分股财务数据获取")
    print(f"数据源: {args.source}")
    print("=" * 80)

    api = None
    if args.source == "tushare":
        if not TUSHARE_AVAILABLE:
            print("⚠️  Tushare未安装，切换到样本数据\n")
            args.source = "sample"
        elif not args.token:
            print("⚠️  未提供Tushare Token，切换到样本数据\n")
            args.source = "sample"
        else:
            try:
                api = ts.pro_api(args.token)
                print("✅ Tushare连接成功\n")
            except Exception as e:
                print(f"⚠️  Tushare连接失败: {str(e)}\n")
                args.source = "sample"

    success_count = 0

    for theme in themes:
        if process_theme(theme, api, args.source, output_base):
            success_count += 1

    print("\n" + "=" * 80)
    print(f"✅ 完成: {success_count}/{len(themes)} 个主题成功")

    if args.source == "sample":
        print("📝 提示: 使用的是样本财务数据，实际应用中建议使用真实数据源")
        print("   推荐使用 Tushare: pip install tushare")
        print("   获取Token: https://tushare.pro/user/profile")

    print("=" * 80)

    return 0 if success_count == len(themes) else 1

if __name__ == "__main__":
    sys.exit(main())
