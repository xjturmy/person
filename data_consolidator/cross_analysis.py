#!/usr/bin/env python3
"""
跨公司对比分析工具

从各公司的 历史数据/ 中提取最新指标，生成：
1. _汇总/估值对比.csv - 所有公司当前估值对比
2. _汇总/盈利对比.csv - 所有公司当前盈利对比
3. _汇总/成长对比.csv - 所有公司成长指标对比
4. _汇总/全景.md - 一屏看全15家公司关键指标

使用方法：
    python3 .tools/data_consolidator/cross_analysis.py
"""

import re
from pathlib import Path
from datetime import datetime

import pandas as pd


COMPANIES_DIR = Path("/Users/gongyong/Desktop/Keyi/Ruby/preson/02_companies")
OUTPUT_DIR = COMPANIES_DIR / "_汇总"


def try_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fmt_pct(val):
    f = try_float(val)
    if f is None:
        return "N/A"
    return f"{f*100:.2f}%"


def fmt_num(val, digits=2):
    f = try_float(val)
    if f is None:
        return "N/A"
    if abs(f) >= 1e8:
        return f"{f/1e8:.2f}亿"
    if abs(f) >= 1e4:
        return f"{f/1e4:.2f}万"
    return f"{f:.{digits}f}"


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"  ⚠️ 读取失败 {path}: {e}")
        return pd.DataFrame()


def get_latest_row(df: pd.DataFrame) -> pd.Series:
    """获取最新一行（按 date 降序后的第一行）"""
    if df.empty:
        return pd.Series()
    if "date" in df.columns:
        df = df.sort_values("date", ascending=False)
    return df.iloc[0]


def collect_company_data(company_dir: Path) -> dict:
    """收集一家公司的关键指标"""
    company_name = re.sub(r"^\d+_", "", company_dir.name)
    history_dir = company_dir / "01_基本面数据" / "历史数据"

    if not history_dir.exists():
        return {}

    data = {"公司": company_name}

    # 估值指标
    valuation_df = read_csv_safe(history_dir / "估值.csv")
    if not valuation_df.empty:
        latest = get_latest_row(valuation_df)
        data["日期"] = latest.get("date", "")
        data["PE-TTM"] = latest.get("PE-TTM", "")
        data["PE分位"] = latest.get("PE-TTM_分位点", "")
        data["PB"] = latest.get("PB", "")
        data["PB分位"] = latest.get("PB_分位点", "")
        data["PS-TTM"] = latest.get("PS-TTM", "")
        data["PS分位"] = latest.get("PS-TTM_分位点", "")
        data["股息率"] = latest.get("股息率", "")

    # 盈利指标
    profit_df = read_csv_safe(history_dir / "盈利.csv")
    if not profit_df.empty:
        latest = get_latest_row(profit_df)
        data["ROE"] = latest.get("净资产收益率(ROE)", "")
        data["ROA"] = latest.get("总资产收益率(ROA)", "")
        data["净利润率"] = latest.get("净利润率", "")
        data["毛利率"] = latest.get("毛利率(GM)", "")

    # 成长指标
    growth_df = read_csv_safe(history_dir / "成长.csv")
    if not growth_df.empty:
        latest = get_latest_row(growth_df)
        data["营业收入"] = latest.get("营业收入", "")
        data["净利润"] = latest.get("归属于母公司普通股股东的净利润", "")

    # 现金流
    cashflow_df = read_csv_safe(history_dir / "现金流.csv")
    if not cashflow_df.empty:
        latest = get_latest_row(cashflow_df)
        data["经营现金流"] = latest.get("经营活动产生的现金流量净额", "")
        data["自由现金流"] = latest.get("自由现金流量", "")

    # 安全性
    safety_df = read_csv_safe(history_dir / "安全性.csv")
    if not safety_df.empty:
        latest = get_latest_row(safety_df)
        data["资产负债率"] = latest.get("资产负债率", "")
        data["流动比率"] = latest.get("流动比率", "")

    return data


def generate_cross_csv(all_data: list[dict]) -> pd.DataFrame:
    """生成跨公司对比 DataFrame"""
    df = pd.DataFrame(all_data)
    return df


def evaluate_valuation(pe_quantile, pb_quantile) -> str:
    """基于分位数评估估值水平"""
    pe = try_float(pe_quantile)
    pb = try_float(pb_quantile)
    scores = []
    if pe is not None:
        scores.append(pe)
    if pb is not None:
        scores.append(pb)
    if not scores:
        return "N/A"
    avg = sum(scores) / len(scores)
    if avg < 0.2:
        return "🟢 极度低估"
    elif avg < 0.4:
        return "🟢 低估"
    elif avg < 0.6:
        return "🟡 合理"
    elif avg < 0.8:
        return "🟠 偏高"
    else:
        return "🔴 高估"


def generate_panorama_md(all_data: list[dict]) -> str:
    """生成全景摘要 md"""
    lines = []
    lines.append("# 📊 公司全景对比")
    lines.append("")
    lines.append(f"> 最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 覆盖公司：{len(all_data)} 家")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 估值对比
    lines.append("## 📈 估值对比")
    lines.append("")
    lines.append("| 公司 | PE-TTM | PE分位 | PB | PB分位 | 股息率 | 估值评估 |")
    lines.append("|------|--------|--------|-----|--------|--------|----------|")
    for data in all_data:
        pe = fmt_num(data.get("PE-TTM"), 2)
        pe_q = fmt_pct(data.get("PE分位"))
        pb = fmt_num(data.get("PB"), 2)
        pb_q = fmt_pct(data.get("PB分位"))
        div = fmt_pct(data.get("股息率"))
        evaluation = evaluate_valuation(data.get("PE分位"), data.get("PB分位"))
        lines.append(f"| {data['公司']} | {pe} | {pe_q} | {pb} | {pb_q} | {div} | {evaluation} |")
    lines.append("")

    # 盈利能力对比
    lines.append("## 💰 盈利能力对比")
    lines.append("")
    lines.append("| 公司 | ROE | ROA | 净利润率 | 毛利率 |")
    lines.append("|------|-----|-----|----------|--------|")
    for data in all_data:
        roe = fmt_pct(data.get("ROE"))
        roa = fmt_pct(data.get("ROA"))
        np_rate = fmt_pct(data.get("净利润率"))
        gm = fmt_pct(data.get("毛利率"))
        lines.append(f"| {data['公司']} | {roe} | {roa} | {np_rate} | {gm} |")
    lines.append("")

    # 规模对比
    lines.append("## 📊 经营规模对比")
    lines.append("")
    lines.append("| 公司 | 营业收入 | 净利润 | 经营现金流 | 自由现金流 |")
    lines.append("|------|----------|--------|------------|------------|")
    for data in all_data:
        rev = fmt_num(data.get("营业收入"), 0)
        np_ = fmt_num(data.get("净利润"), 0)
        ocf = fmt_num(data.get("经营现金流"), 0)
        fcf = fmt_num(data.get("自由现金流"), 0)
        lines.append(f"| {data['公司']} | {rev} | {np_} | {ocf} | {fcf} |")
    lines.append("")

    # 安全性对比
    lines.append("## 🛡️ 安全性对比")
    lines.append("")
    lines.append("| 公司 | 资产负债率 | 流动比率 |")
    lines.append("|------|------------|----------|")
    for data in all_data:
        dar = fmt_pct(data.get("资产负债率"))
        cr = fmt_num(data.get("流动比率"), 2)
        lines.append(f"| {data['公司']} | {dar} | {cr} |")
    lines.append("")

    # 排行榜
    lines.append("---")
    lines.append("")
    lines.append("## 🏆 排行榜")
    lines.append("")

    # 最低估（按 PE 分位数）
    valid = [d for d in all_data if try_float(d.get("PE分位")) is not None]
    valid.sort(key=lambda x: try_float(x.get("PE分位")) or 1.0)
    lines.append("### 🟢 估值最低 Top 5（按 PE 分位）")
    lines.append("")
    lines.append("| 排名 | 公司 | PE-TTM | PE分位 | PB | 股息率 |")
    lines.append("|------|------|--------|--------|-----|--------|")
    for i, d in enumerate(valid[:5], 1):
        lines.append(
            f"| {i} | {d['公司']} | {fmt_num(d.get('PE-TTM'), 2)} | "
            f"{fmt_pct(d.get('PE分位'))} | {fmt_num(d.get('PB'), 2)} | "
            f"{fmt_pct(d.get('股息率'))} |"
        )
    lines.append("")

    # ROE 排行
    valid = [d for d in all_data if try_float(d.get("ROE")) is not None]
    valid.sort(key=lambda x: try_float(x.get("ROE")) or 0, reverse=True)
    lines.append("### 💎 ROE 最高 Top 5")
    lines.append("")
    lines.append("| 排名 | 公司 | ROE | ROA | 毛利率 |")
    lines.append("|------|------|-----|-----|--------|")
    for i, d in enumerate(valid[:5], 1):
        lines.append(
            f"| {i} | {d['公司']} | {fmt_pct(d.get('ROE'))} | "
            f"{fmt_pct(d.get('ROA'))} | {fmt_pct(d.get('毛利率'))} |"
        )
    lines.append("")

    # 股息率排行
    valid = [d for d in all_data if try_float(d.get("股息率")) is not None]
    valid.sort(key=lambda x: try_float(x.get("股息率")) or 0, reverse=True)
    lines.append("### 💰 股息率最高 Top 5")
    lines.append("")
    lines.append("| 排名 | 公司 | 股息率 | PE-TTM | ROE |")
    lines.append("|------|------|--------|--------|-----|")
    for i, d in enumerate(valid[:5], 1):
        lines.append(
            f"| {i} | {d['公司']} | {fmt_pct(d.get('股息率'))} | "
            f"{fmt_num(d.get('PE-TTM'), 2)} | {fmt_pct(d.get('ROE'))} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 📂 数据文件")
    lines.append("")
    lines.append("- `估值对比.csv` - 所有公司估值指标")
    lines.append("- `盈利对比.csv` - 所有公司盈利指标")
    lines.append("- `规模对比.csv` - 所有公司经营规模")
    lines.append("- `安全性对比.csv` - 所有公司安全性指标")
    lines.append("")

    return "\n".join(lines)


def main():
    print("🔍 扫描所有公司数据...")

    all_data = []
    for company_dir in sorted(COMPANIES_DIR.glob("*")):
        if not company_dir.is_dir():
            continue
        if company_dir.name.startswith("_") or company_dir.name.startswith("."):
            continue
        data = collect_company_data(company_dir)
        if data:
            all_data.append(data)
            print(f"  ✓ {data['公司']}")

    if not all_data:
        print("❌ 未找到任何公司数据")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 生成综合 CSV
    df = pd.DataFrame(all_data)
    all_csv = OUTPUT_DIR / "全部指标.csv"
    df.to_csv(all_csv, index=False)
    print(f"\n✓ 全部指标 → {all_csv.name}")

    # 生成分类 CSV
    cols_map = {
        "估值对比.csv": ["公司", "日期", "PE-TTM", "PE分位", "PB", "PB分位", "PS-TTM", "PS分位", "股息率"],
        "盈利对比.csv": ["公司", "ROE", "ROA", "净利润率", "毛利率"],
        "规模对比.csv": ["公司", "营业收入", "净利润", "经营现金流", "自由现金流"],
        "安全性对比.csv": ["公司", "资产负债率", "流动比率"],
    }
    for filename, cols in cols_map.items():
        avail = [c for c in cols if c in df.columns]
        if avail:
            (OUTPUT_DIR / filename).write_text(df[avail].to_csv(index=False), encoding="utf-8")
            print(f"✓ {filename}")

    # 生成全景 md
    panorama = generate_panorama_md(all_data)
    panorama_path = OUTPUT_DIR / "全景.md"
    panorama_path.write_text(panorama, encoding="utf-8")
    print(f"\n✓ 全景对比 → {panorama_path.name}")

    print(f"\n🎉 完成，输出目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
