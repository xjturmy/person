#!/usr/bin/env python3
"""
获取 ETF 成分股列表的脚本

支持两种数据源：
  1. Tushare（推荐，需要Token）
  2. 本地样本数据

用法:
  python3 fetch_etf_constituents.py --all --source tushare --token YOUR_TUSHARE_TOKEN
  python3 fetch_etf_constituents.py --theme 新能源 --source sample
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime
import time

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False

# 样本数据：ETF代码到成分股的映射（用于演示和备用）
SAMPLE_CONSTITUENTS = {
    "399417": [  # 新能源汽车指数
        ("300750", "宁德时代", 10.25),
        ("300014", "亿纬锂能", 8.50),
        ("002594", "比亚迪", 7.20),
    ],
    "000688": [  # 科创板50指数
        ("688981", "中芯国际", 5.2),
        ("688536", "思瑞浦", 4.1),
        ("688139", "通富微电", 3.8),
    ],
    "000592": [  # 中证机器人指数
        ("300024", "机器人", 6.5),
        ("002415", "海康威视", 5.2),
        ("603986", "兆易创新", 4.1),
    ],
    "399812": [  # 消费精选指数
        ("600519", "贵州茅台", 8.5),
        ("000858", "五粮液", 6.2),
        ("601398", "工商银行", 3.1),
    ],
    "399764": [  # 生物科技指数
        ("300142", "沃森生物", 5.2),
        ("603259", "药明康德", 4.8),
        ("688363", "华熙生物", 4.1),
    ],
    "913000": [  # 纳斯达克生物科技指数
        ("300142", "沃森生物", 5.2),
        ("603259", "药明康德", 4.8),
    ],
    "399989": [  # 中证医疗指数
        ("603259", "药明康德", 5.5),
        ("300003", "乐普医疗", 4.2),
        ("002521", "浩宁医疗", 3.1),
    ],
    "000990": [  # 中证银行指数
        ("601398", "工商银行", 12.5),
        ("601988", "中国银行", 10.2),
        ("601328", "交通银行", 8.1),
    ],
    "399950": [  # 中证消费指数
        ("600519", "贵州茅台", 10.5),
        ("000858", "五粮液", 8.2),
        ("000651", "格力电器", 6.1),
    ],
    "399808": [  # 中证房地产指数
        ("600048", "保利发展", 4.2),
        ("600100", "同仁堂", 3.5),
        ("601899", "紫金矿业", 2.8),
    ],
    "399858": [  # 能源互联网指数
        ("300015", "爱尔眼科", 5.2),
        ("600009", "上海机场", 4.1),
    ],
    "399815": [  # 中证全指能源指数
        ("601857", "中国石油", 8.5),
        ("600028", "中国石化", 7.2),
        ("601088", "中国神华", 6.1),
    ],
}

def get_constituents_tushare(index_code, api):
    """使用Tushare获取成分股"""
    try:
        df = api.index_weight(index_code=index_code, start_date='20260101', end_date=datetime.now().strftime('%Y%m%d'))

        if df.empty:
            return None

        # 最新日期的数据
        latest_date = df['trade_date'].max()
        latest_data = df[df['trade_date'] == latest_date]

        constituents = []
        for _, row in latest_data.iterrows():
            constituents.append({
                "code": row['con_code'],
                "name": row['con_name'],
                "weight": float(row['weight']),
                "adjust_factor": float(row.get('adj_factor', 1.0))
            })

        return constituents
    except Exception as e:
        print(f"    ⚠️  Tushare获取失败: {str(e)[:80]}")
        return None

def get_constituents_sample(index_code):
    """使用本地样本数据"""
    stocks = SAMPLE_CONSTITUENTS.get(index_code, [])

    if not stocks:
        return None

    constituents = []
    for code, name, weight in stocks:
        constituents.append({
            "code": code,
            "name": name,
            "weight": weight,
            "adjust_factor": 1.0
        })

    return constituents

def save_constituents_csv(output_path, constituents):
    """保存成分股为CSV文件"""
    if not constituents:
        return False

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = ["代码", "名称", "权重(%)", "调整因子"]

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)

        for item in constituents:
            row = [
                item.get("code", ""),
                item.get("name", ""),
                f"{item.get('weight', ''):.2f}" if isinstance(item.get("weight"), (int, float)) else "",
                f"{item.get('adjust_factor', ''):.2f}" if isinstance(item.get("adjust_factor"), (int, float)) else ""
            ]
            w.writerow(row)

    return True

def process_theme(theme_name, api, source, output_base):
    """处理单个主题的所有ETF"""
    theme_dir = Path(output_base) / "投资主题" / theme_name
    config_path = theme_dir / "etf_config.json"

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 配置文件解析失败: {str(e)}")
        return False

    etfs = config.get("etfs", [])
    if not etfs:
        print(f"⚠️  {theme_name} 中没有ETF配置")
        return True

    print(f"\n📊 处理主题: {theme_name} (共 {len(etfs)} 个ETF)")
    print("-" * 80)

    all_success = True

    for etf in etfs:
        etf_code = etf.get("code")
        etf_name = etf.get("name")
        index_code = etf.get("index_code")

        print(f"  {etf_code} {etf_name} (指数: {index_code})", end=" ... ")

        # 获取成分股
        if source == "tushare" and api:
            constituents = get_constituents_tushare(index_code, api)
        else:
            constituents = get_constituents_sample(index_code)

        if constituents:
            csv_path = theme_dir / "constituents.csv"

            # 保存成分股（只需保存一次，因为同一指数的成分股相同）
            if not csv_path.exists():
                if save_constituents_csv(csv_path, constituents):
                    print(f"✅ ({len(constituents)}个成分股)")
                else:
                    print(f"❌ 保存失败")
                    all_success = False
            else:
                print(f"✅ (已存在，{len(constituents)}个)")
        else:
            print(f"⚠️  无数据")

        time.sleep(0.5)

    return all_success

def main():
    parser = argparse.ArgumentParser(description="获取ETF成分股列表")
    parser.add_argument("--theme", help="主题名称 (新能源/机器人/消费/芯片半导体)")
    parser.add_argument("--all", action="store_true", help="处理所有主题")
    parser.add_argument("--source", default="sample", choices=["tushare", "sample"],
                       help="数据源 (默认: sample，推荐: tushare)")
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
    print("ETF 成分股列表获取")
    print(f"数据源: {args.source}")
    print("=" * 80)

    api = None
    if args.source == "tushare":
        if not TUSHARE_AVAILABLE:
            print("⚠️  Tushare未安装，切换到样本数据")
            args.source = "sample"
        elif not args.token:
            print("⚠️  未提供Tushare Token，切换到样本数据")
            args.source = "sample"
        else:
            try:
                api = ts.pro_api(args.token)
                print("✅ Tushare连接成功\n")
            except Exception as e:
                print(f"⚠️  Tushare连接失败: {str(e)}")
                print("切换到样本数据\n")
                args.source = "sample"

    success_count = 0

    for theme in themes:
        if process_theme(theme, api, args.source, output_base):
            success_count += 1

    print("\n" + "=" * 80)
    print(f"✅ 完成: {success_count}/{len(themes)} 个主题成功")

    if args.source == "sample":
        print("⚠️  使用的是样本数据，建议使用Tushare获取实时数据")
        print("安装: pip install tushare")
        print("获取Token: https://tushare.pro/user/profile")

    print("=" * 80)

    return 0 if success_count == len(themes) else 1

if __name__ == "__main__":
    sys.exit(main())
