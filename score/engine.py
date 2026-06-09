"""
大师评分引擎骨架 — 不依赖 DuckDB，可用 mock 数据先跑通规则解析。

用法：
    python -m .tools.score.engine --rules piotroski.yaml --mock
    python -m .tools.score.engine --rules buffett.yaml --ticker 600519 --data-source csv

后续 W1 DuckDB 落地后，把 _load_data() 切到 DuckDB 即可，规则引擎核心逻辑不变。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:
    sys.stderr.write("缺少 PyYAML，运行：pip install pyyaml\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / ".tools" / "rules"
DEFAULT_DB = ROOT / "data" / "preson.duckdb"

DUCKDB_METRIC_MAP: dict[str, list[tuple[str, str]]] = {
    "profitability": [
        ("总资产收益率(ROA)", "roa"),
        ("净资产收益率(ROE)", "roe"),
        ("毛利率(GM)", "gross_margin"),
        ("净利润率", "net_margin"),
        # P2 新增 2026-05-06
        ("资本回报率(ROIC)", "roic"),
    ],
    "safety": [
        ("资产负债率", "debt_ratio"),
        ("流动比率", "current_ratio"),
        ("速动比率", "quick_ratio"),
        ("有息负债率", "interest_debt_ratio"),
        # P2 BS 聚合 2026-05-06 — graham/buffett/altman/lynch 必需
        ("资产合计", "total_assets"),
        ("负债合计", "total_liabilities"),
        ("所有者权益合计", "book_equity"),
        ("流动资产合计", "current_assets"),
        ("流动负债合计", "current_liabilities"),
        ("长期负债合计", "long_term_debt"),
    ],
    "growth": [
        ("营业收入", "revenue"),
        ("归属于母公司普通股股东的净利润", "net_income"),
        ("基本每股收益", "eps"),
    ],
    "cashflow": [
        ("自由现金流量", "fcf"),
        ("经营活动产生的现金流量净额", "cfo"),
        ("经营活动产生的现金流量净额对净利润的比率", "cfo_to_ni"),
    ],
    "valuation": [
        ("PE-TTM", "pe_ttm"),
        ("PB", "pb"),
        ("PS-TTM", "ps_ttm"),
        ("股息率", "dividend_yield"),
        # P2 市值 2026-05-06 — graham g1_size 必需
        ("市值(元)", "market_cap"),
    ],
    # 银行业派生指标 (P3 部分解锁,2026-05-05)
    # 由 .tools/db/fetch_bank_metrics.py 从 sina BS+IS 派生写入
    "bank_metrics": [
        ("provision_to_loans", "provision_to_loans"),
        ("net_interest_to_revenue", "net_interest_to_revenue"),
        ("net_interest_yoy", "net_interest_yoy"),
        ("loans_yoy", "loans_yoy"),
    ],
}

CATEGORY_TO_INDUSTRY = {
    "non_financial": "消费品",
    "bank": "银行",
    "insurance": "保险",
    "hk": "港股",
}


# ---------- 数据访问层（待 W1 DuckDB 落地后替换）-----------------------------

@dataclass
class CompanyData:
    """单个公司的多年财务数据（按年）。值为 dict[year_int -> float]。"""
    ticker: str
    name: str
    industry: str
    metrics: dict[str, dict[int, float]] = field(default_factory=dict)

    def get(self, metric: str, year: int) -> float | None:
        return self.metrics.get(metric, {}).get(year)

    def yoy(self, metric: str, year: int) -> float | None:
        cur, prev = self.get(metric, year), self.get(metric, year - 1)
        if cur is None or prev is None:
            return None
        return cur - prev

    def years(self) -> list[int]:
        if not self.metrics:
            return []
        return sorted(set().union(*(v.keys() for v in self.metrics.values())))


def load_mock_data() -> CompanyData:
    """模拟数据 — 茅台 ROA/ROE 来自实际 CSV 抽取，其余为占位。"""
    return CompanyData(
        ticker="600519",
        name="贵州茅台",
        industry="消费品",
        metrics={
            "roa":          {2016: 0.180, 2017: 0.234, 2018: 0.257, 2019: 0.257,
                             2020: 0.250, 2021: 0.238, 2022: 0.257, 2023: 0.294,
                             2024: 0.313, 2025: 0.283},
            "roe":          {2016: 0.252, 2017: 0.337, 2018: 0.355, 2019: 0.339,
                             2020: 0.320, 2021: 0.306, 2022: 0.325, 2023: 0.362,
                             2024: 0.384, 2025: 0.344},
            "gross_margin": {2016: 0.912, 2017: 0.898, 2018: 0.911, 2019: 0.913,
                             2020: 0.914, 2021: 0.915, 2022: 0.919, 2023: 0.920,
                             2024: 0.919, 2025: 0.912},
            "debt_ratio":   {2024: 0.150, 2025: 0.164},
            "cfo":          {2024: 92e9, 2025: 61.5e9},
            "current_ratio":{2024: 5.85, 2025: 5.09},
            "shares_outstanding": {2024: 1.256e9, 2025: 1.256e9},
            "total_assets": {2024: 0.290e12, 2025: 0.291e12},
            "revenue":      {2024: 174e9, 2025: 169e9},
            "long_term_debt": {2024: 0.0, 2025: 0.0},
            "pe_ttm":       {2025: 21.5},
            "pb":           {2025: 7.2},
        },
    )


def load_csv_data(ticker_dir: Path) -> CompanyData:
    """从 02_companies/{n}_{name}/01_基本面数据/历史数据/ CSV 加载（年末数据）。"""
    import csv

    metrics: dict[str, dict[int, float]] = {}

    csv_map = {
        "盈利.csv":  [("总资产收益率(ROA)", "roa"),
                     ("净资产收益率(ROE)", "roe"),
                     ("毛利率(GM)",       "gross_margin"),
                     ("净利润率",          "net_margin")],
        "安全性.csv":[("资产负债率",        "debt_ratio"),
                     ("流动比率",          "current_ratio"),
                     ("速动比率",          "quick_ratio"),
                     ("有息负债率",        "interest_debt_ratio")],
        "成长.csv":  [("营业收入",          "revenue"),
                     ("归属于母公司普通股股东的净利润", "net_income"),
                     ("基本每股收益",      "eps")],
        "现金流.csv":[("自由现金流量",      "fcf"),
                     ("经营活动产生的现金流量净额", "cfo")],
    }

    for filename, mappings in csv_map.items():
        path = ticker_dir / "01_基本面数据" / "历史数据" / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = row.get("date", "")
                if not date.endswith("-12-31"):
                    continue
                year = int(date[:4])
                for col, metric_key in mappings:
                    val = row.get(col)
                    if val and val.strip():
                        try:
                            metrics.setdefault(metric_key, {})[year] = float(val)
                        except ValueError:
                            pass

    name = ticker_dir.name.split("_", 1)[1] if "_" in ticker_dir.name else ticker_dir.name
    return CompanyData(ticker=ticker_dir.name, name=name, industry="消费品", metrics=metrics)


def load_duckdb_data(ticker: str, db_path: Path | None = None) -> CompanyData:
    """从 data/preson.duckdb 加载单家公司年末数据(12-31)。值映射为英文 metric_key。"""
    import duckdb

    db = db_path or DEFAULT_DB
    if not db.exists():
        raise FileNotFoundError(f"DuckDB 不存在: {db},先跑 .tools/db/ingest.py")

    con = duckdb.connect(str(db), read_only=True)
    try:
        info = con.execute(
            "SELECT name, category FROM companies WHERE ticker = ?", [ticker]
        ).fetchone()
        if info is None:
            raise ValueError(f"ticker {ticker} 不在 companies 表")
        name, category = info
        industry = CATEGORY_TO_INDUSTRY.get(category or "", "未知")

        # 检查表存在(bank_metrics 是 P3 后新增,可能未建)
        existing_tables = {
            r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }

        metrics: dict[str, dict[int, float]] = {}
        for table, mappings in DUCKDB_METRIC_MAP.items():
            if table not in existing_tables:
                continue
            for cn, key in mappings:
                rows = con.execute(
                    f"SELECT EXTRACT(YEAR FROM date) AS y, value "
                    f"FROM {table} "
                    f"WHERE ticker = ? AND metric = ? "
                    f"  AND MONTH(date) = 12 AND DAY(date) = 31",
                    [ticker, cn],
                ).fetchall()
                if rows:
                    metrics[key] = {
                        int(y): float(v) for y, v in rows if v is not None
                    }
    finally:
        con.close()

    # P2 衍生指标(2026-05-06)— 让 yaml 直接引用,不必每条规则自算
    _add_derived_metrics(metrics)

    return CompanyData(ticker=ticker, name=name or ticker, industry=industry, metrics=metrics)


def _add_derived_metrics(metrics: dict[str, dict[int, float]]) -> None:
    """从 BS / 盈利 / 成长字段衍生常用聚合指标,原地修改 metrics dict。

    衍生项:
      - earnings_per_share = eps  (alias,yaml 公式兼容)
      - net_current_assets = current_assets - current_liabilities (graham g2)
      - debt_to_assets_pct = total_liabilities / total_assets * 100 (lynch 总负债率)
      - eps_3y_avg = avg(eps[t-2..t])  (graham g5)
      - eps_growth_3y = (eps[t]/eps[t-3])^(1/3) - 1  (lynch peg)
    """
    # alias
    if "eps" in metrics and "earnings_per_share" not in metrics:
        metrics["earnings_per_share"] = dict(metrics["eps"])

    # net_current_assets
    if "current_assets" in metrics and "current_liabilities" in metrics:
        ncoa: dict[int, float] = {}
        for y, ca in metrics["current_assets"].items():
            cl = metrics["current_liabilities"].get(y)
            if ca is not None and cl is not None:
                ncoa[y] = ca - cl
        if ncoa:
            metrics["net_current_assets"] = ncoa

    # debt_to_assets_pct(直接百分比形式,yaml 用 <= 40 / <= 0.4 都易判)
    if "total_liabilities" in metrics and "total_assets" in metrics:
        d2a: dict[int, float] = {}
        for y, tl in metrics["total_liabilities"].items():
            ta = metrics["total_assets"].get(y)
            if tl is not None and ta is not None and ta != 0:
                d2a[y] = tl / ta
        if d2a:
            metrics["debt_to_assets"] = d2a

    # eps_3y_avg(滚动 3 年算术平均)
    if "eps" in metrics:
        eps_map = metrics["eps"]
        avg3: dict[int, float] = {}
        for y in sorted(eps_map):
            vals = [eps_map.get(y), eps_map.get(y - 1), eps_map.get(y - 2)]
            if all(v is not None for v in vals):
                avg3[y] = sum(vals) / 3
        if avg3:
            metrics["eps_3y_avg"] = avg3

        # eps_growth_3y(几何 CAGR,要求两端 >0)
        cagr3: dict[int, float] = {}
        for y in sorted(eps_map):
            cur, base = eps_map.get(y), eps_map.get(y - 3)
            if cur is not None and base is not None and base > 0 and cur > 0:
                cagr3[y] = (cur / base) ** (1 / 3) - 1
        if cagr3:
            metrics["eps_growth_3y"] = cagr3


# ---------- 公式求值器 ------------------------------------------------------

class FormulaEvaluator:
    """轻量公式求值。支持 yoy()、min()、max()、cagr() 等函数 + 字段引用 + 算术比较。

    yoy/min/cagr 的参数支持任意算术表达式(如 yoy(net_income / eps)),
    但参数内不允许出现嵌套括号或函数调用。
    """

    # 参数允许字母/数字/_/算术符号/空格,不允许嵌套括号
    YOY_RE = re.compile(r"yoy\(\s*([a-z_0-9+\-*/.\s]+?)\s*\)")
    MIN_RE = re.compile(r"min\(\s*([a-z_]+)\s*,\s*(\d+)\s*\)")
    CAGR_RE = re.compile(r"cagr\(\s*([a-z_]+)\s*,\s*(\d+)\s*\)")

    def __init__(self, data: CompanyData, year: int):
        self.data = data
        self.year = year

    def eval(self, formula: str) -> bool | float | None:
        """求值，返回 bool / float / None（数据缺失）。"""
        f = formula.strip()

        # 处理函数：yoy / min / cagr
        f = self.YOY_RE.sub(lambda m: self._yoy_repl(m.group(1)), f)
        f = self.MIN_RE.sub(lambda m: self._min_repl(m.group(1), int(m.group(2))), f)
        f = self.CAGR_RE.sub(lambda m: self._cagr_repl(m.group(1), int(m.group(2))), f)

        # 替换裸字段
        for metric in self.data.metrics:
            f = re.sub(rf"\b{metric}\b(?!\()", self._field_repl(metric), f)

        # 替换中文/比较符号 → Python
        f = f.replace(" AND ", " and ").replace(" OR ", " or ")

        # None 短路
        if "None" in f:
            return None

        try:
            # eval 仅在受控规则字符串上使用 — 不接受用户输入
            return eval(f, {"__builtins__": {}}, {})
        except Exception as e:
            return None

    def _eval_at_year(self, expr: str, year: int) -> float | None:
        """对一个算术表达式按指定年份求值;任一字段缺失返回 None。"""
        f = expr
        for metric in self.data.metrics:
            if not re.search(rf"\b{metric}\b", f):
                continue
            v = self.data.metrics.get(metric, {}).get(year)
            if v is None:
                return None
            f = re.sub(rf"\b{metric}\b(?!\()", repr(v), f)
        if re.search(r"[a-z_]", f):  # 还有未替换的字母 → 未知字段,视为缺失
            return None
        try:
            return eval(f, {"__builtins__": {}}, {})
        except Exception:
            return None

    def _field_repl(self, metric: str) -> str:
        v = self.data.get(metric, self.year)
        return repr(v) if v is not None else "None"

    def _yoy_repl(self, expr: str) -> str:
        cur = self._eval_at_year(expr, self.year)
        prev = self._eval_at_year(expr, self.year - 1)
        if cur is None or prev is None:
            return "None"
        return repr(cur - prev)

    def _min_repl(self, metric: str, n: int) -> str:
        vals = [self.data.get(metric, y) for y in range(self.year - n + 1, self.year + 1)]
        if any(v is None for v in vals):
            return "None"
        return repr(min(vals))

    def _cagr_repl(self, metric: str, n: int) -> str:
        end, start = self.data.get(metric, self.year), self.data.get(metric, self.year - n)
        if end is None or start is None or start <= 0:
            return "None"
        return repr((end / start) ** (1 / n) - 1)


# ---------- 评分引擎 --------------------------------------------------------

@dataclass
class RuleResult:
    rule_id: str
    name: str
    passed: bool | None
    score: float
    formula: str

    def __str__(self) -> str:
        flag = "✅" if self.passed else "❌" if self.passed is False else "⚠️ "
        return f"  {flag} [{self.rule_id}] {self.name} → {self.score:.1f} 分"


@dataclass
class ScoreResult:
    master: str
    master_cn: str
    method: str
    ticker: str
    year: int
    total_score: float
    max_score: float | None
    rating: str
    details: list[RuleResult]

    def report(self) -> str:
        out = [
            f"\n{'='*70}",
            f"  {self.master_cn} ({self.master}) — {self.method}",
            f"  {self.ticker} | 年份 {self.year} | 评级：{self.rating}",
            f"  得分：{self.total_score:.1f}" + (f" / {self.max_score}" if self.max_score else ""),
            f"{'='*70}",
        ]
        for d in self.details:
            out.append(str(d))
        return "\n".join(out)


def classify(score: float, threshold: dict) -> str:
    if "excellent" in threshold and score >= threshold["excellent"]:
        return "🟢 优秀"
    if "good" in threshold and score >= threshold["good"]:
        return "🟡 良好"
    if "warning" in threshold and score >= threshold["warning"]:
        return "🟠 警戒"
    return "🔴 不合格"


_GRADE_TIERS = ("excellent", "good", "fair", "weak", "fail")


def eval_rule(rule: dict, evaluator: "FormulaEvaluator") -> tuple[float, bool | None, str]:
    """统一规则求值。支持三种 schema:

    1) classic:  rule.formula(经典 boolean)
    2) OR/AND:   rule.formula_primary + rule.formula_alt + rule.pass_logic
    3) grades:   rule.formula 含 grade_threshold 占位 + rule.grades 多档

    Returns:
        (score, passed, formula_for_display)
        passed 为 None 表示数据缺失/不可评估(调用方决定是否计入 valid)。
    """
    if "grades" in rule:
        formula = rule.get("formula", "") or ""
        for tier in _GRADE_TIERS:
            tier_def = rule["grades"].get(tier)
            if not tier_def:
                continue
            threshold = tier_def.get("threshold", 0)
            if isinstance(threshold, str) and threshold.strip() == "-inf":
                threshold = float("-inf")
            actual = formula.replace("grade_threshold", repr(threshold))
            result = evaluator.eval(actual)
            if result is True:
                return float(tier_def.get("score", 0)), True, formula
            if result is None:
                return 0.0, None, formula
        return 0.0, False, formula

    if "formula_primary" in rule:
        primary = evaluator.eval(rule.get("formula_primary", ""))
        alt = evaluator.eval(rule.get("formula_alt", ""))
        if primary is None and alt is None:
            return 0.0, None, rule.get("formula_primary", "")
        logic = (rule.get("pass_logic") or "OR").upper()
        if logic == "AND":
            passed = bool(primary) and bool(alt)
        else:
            passed = bool(primary) or bool(alt)
        score = rule.get("score_if_pass", 1) if passed else rule.get("score_if_fail", 0)
        return float(score), passed, f"{rule.get('formula_primary','')} {logic} {rule.get('formula_alt','')}"

    formula = rule.get("formula", "") or ""
    if not formula:
        return 0.0, None, ""
    result = evaluator.eval(formula)
    if result is None:
        return 0.0, None, formula
    passed = bool(result)
    score = rule.get("score_if_pass", 1) if passed else rule.get("score_if_fail", 0)
    return float(score), passed, formula


def run_score(rules_path: Path, data: CompanyData, year: int) -> ScoreResult | None:
    rules_doc = yaml.safe_load(rules_path.read_text(encoding="utf-8"))

    # 行业排除
    if data.industry in rules_doc.get("exclude_industries", []):
        print(f"⚠️  {data.name}（{data.industry}）不适用 {rules_doc['master_cn']} — 已跳过")
        return None

    # 行业自动切换:若 YAML 声明了 industry_specific_files,则按公司行业切到专用规则
    industry_files = rules_doc.get("industry_specific_files") or {}
    specific_filename = industry_files.get(data.industry)
    if specific_filename:
        specific_path = rules_path.parent / specific_filename
        if specific_path.exists() and specific_path != rules_path:
            return run_score(specific_path, data, year)
        # 文件不存在则降级用主版本(避免硬失败)

    evaluator = FormulaEvaluator(data, year)
    details: list[RuleResult] = []
    total = 0.0

    for rule in rules_doc.get("rules", []):
        score, passed, formula = eval_rule(rule, evaluator)
        details.append(RuleResult(
            rule_id=rule["id"],
            name=rule.get("name", rule["id"]),
            passed=passed,
            score=float(score),
            formula=formula,
        ))

    # 重算总分（不重复加权）
    total = sum(d.score for d in details)

    return ScoreResult(
        master=rules_doc["master"],
        master_cn=rules_doc["master_cn"],
        method=rules_doc.get("method", ""),
        ticker=data.ticker,
        year=year,
        total_score=total,
        max_score=rules_doc.get("max_score"),
        rating=classify(total, rules_doc.get("threshold", {})),
        details=details,
    )


# ---------- CLI -------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="大师评分引擎（骨架版）")
    ap.add_argument("--rules", default="piotroski.yaml", help="规则 YAML 文件名（rules/ 目录下）")
    ap.add_argument("--mock", action="store_true", help="使用 mock 数据（茅台 2016-2025）")
    ap.add_argument("--ticker-dir", help="公司目录路径（CSV 模式，如 02_companies/06_贵州茅台）")
    ap.add_argument("--ticker", help="公司代码（DuckDB 模式，如 600519）")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--list-rules", action="store_true", help="列出所有可用规则文件")
    args = ap.parse_args()

    if args.list_rules:
        for p in sorted(RULES_DIR.glob("*.yaml")):
            print(f"  - {p.name}")
        return

    rules_path = RULES_DIR / args.rules
    if not rules_path.exists():
        sys.exit(f"❌ 规则文件不存在：{rules_path}")

    if args.mock:
        data = load_mock_data()
    elif args.ticker:
        data = load_duckdb_data(args.ticker)
    elif args.ticker_dir:
        data = load_csv_data(Path(args.ticker_dir).resolve())
    else:
        sys.exit("❌ 必须指定 --mock / --ticker / --ticker-dir")

    print(f"📂 数据加载：{data.name} | 年份覆盖：{data.years()[:3]}...{data.years()[-3:] if len(data.years()) > 3 else ''}")

    result = run_score(rules_path, data, args.year)
    if result:
        print(result.report())


if __name__ == "__main__":
    main()
