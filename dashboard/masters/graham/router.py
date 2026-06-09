"""格雷厄姆评分体系行业路由器(v2.5 TODO#1 G1)。

screener 入口按 industry_l2 自动分流到对应 yaml:
  - 银行 / 股份制银行 / 城商行 / 农商行 / 国有大行 → graham_bank.yaml
  - 保险 / 寿险 / 财险                              → graham_insurance.yaml
  - 其他                                            → graham.yaml(默认)

调用约定:
    from masters.graham.router import route, route_by_ticker
    yaml_path = route(ticker="600036", industry="股份制银行")  # graham_bank.yaml
    yaml_path = route_by_ticker("600036")                      # 自动查 csv

数据源:.config/companies.csv 的 industry_l2 列(权威)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[4]
RULES_DIR = ROOT / ".tools" / "rules"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"

# 行业关键字 → yaml 文件名(顺序敏感:银行/保险优先)
BANK_KEYWORDS = (
    "股份制银行",
    "城商行",
    "农商行",
    "国有大行",
    "商业银行",
    "银行",        # 兜底,放最后
)
INSURANCE_KEYWORDS = (
    "寿险",
    "财险",
    "人寿",
    "保险",        # 兜底,放最后
)

DEFAULT_YAML = "graham.yaml"
BANK_YAML = "graham_bank.yaml"
INSURANCE_YAML = "graham_insurance.yaml"


def _classify(industry: str) -> str:
    """行业字符串 → yaml 文件名(纯字符串匹配)。"""
    if not industry:
        return DEFAULT_YAML
    s = str(industry).strip()
    if not s:
        return DEFAULT_YAML

    for kw in BANK_KEYWORDS:
        if kw in s:
            return BANK_YAML
    for kw in INSURANCE_KEYWORDS:
        if kw in s:
            return INSURANCE_YAML
    return DEFAULT_YAML


def route(ticker: str, industry: Optional[str] = None) -> str:
    """主路由函数。返回 yaml 绝对路径(str)。

    Args:
        ticker: 股票代码(6 位 A 股 / 5 位港股),仅日志用
        industry: industry_l2 值(优先用此);为 None 时不动用 csv

    Returns:
        yaml 文件绝对路径,例如 ".../.tools/rules/graham_bank.yaml"
    """
    yaml_name = _classify(industry or "")
    return str(RULES_DIR / yaml_name)


def route_by_ticker(ticker: str, csv_path: Optional[Path] = None) -> str:
    """按 ticker 自动从 companies.csv 查 industry_l2 后路由。

    Args:
        ticker: 股票代码(stock 列匹配)
        csv_path: 自定义 csv 路径(测试用),None=用默认 .config/companies.csv

    Returns:
        yaml 绝对路径;ticker 不在 csv 时返回主 yaml
    """
    path = csv_path or COMPANIES_CSV
    industry = _read_industry(ticker, path)
    return route(ticker, industry)


def _read_industry(ticker: str, csv_path: Path) -> Optional[str]:
    """从 companies.csv 读 industry_l2(纯标准库,避免 pandas 启动开销)。"""
    if not csv_path.exists():
        return None
    import csv
    try:
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("stock", "")).strip() == str(ticker).strip():
                    return str(row.get("industry_l2", "") or "").strip() or None
    except Exception:
        return None
    return None


# ═══ 离线 CLI 验证 ═══════════════════════════════════════════════════════

def _smoke_test() -> None:
    """打印 15 家公司路由结果。"""
    import csv
    print(f"{'═' * 60}")
    print("  graham_router 路由结果(基于 .config/companies.csv)")
    print('═' * 60)
    if not COMPANIES_CSV.exists():
        print(f"  ⚠️ {COMPANIES_CSV} 不存在")
        return
    with COMPANIES_CSV.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = row.get("stock", "")
            n = row.get("name", "")
            ind = row.get("industry_l2", "")
            yaml_path = route(t, ind)
            yaml_name = Path(yaml_path).name
            print(f"  {t:8s} {n:8s} industry_l2={ind:10s} → {yaml_name}")


if __name__ == "__main__":
    _smoke_test()
