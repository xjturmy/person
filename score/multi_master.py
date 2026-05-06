"""多大师评分汇总 — 跑所有可执行的 master yaml,输出 15 家公司 × N 大师评分矩阵。

用法:
    python3 .tools/score/multi_master.py                  # 默认 2024 年报 + 全 15 家
    python3 .tools/score/multi_master.py --year 2023
    python3 .tools/score/multi_master.py --tickers 600519,000333

输出:
    控制台 markdown 表格 + 02_companies/_汇总/评分_全大师矩阵.md
"""
from __future__ import annotations

import argparse
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / ".tools" / "rules"
DB_PATH = ROOT / "data" / "preson.duckdb"
REPORT = ROOT / "02_companies" / "_汇总" / "评分_全大师矩阵.md"

ENGINE = SourceFileLoader("engine", str(Path(__file__).parent / "engine.py")).load_module()

# 大师 → 风格归类(v2.0 验收"价值/成长双维度")
MASTER_STYLE = {
    "piotroski": "value",
    "graham": "value",
    "altman": "value",          # 风险/破产 → 价值阵营
    "buffett": "growth",        # 优质成长(质量+增长)
    "lynch": "growth",          # GARP
    "greenblatt": "value",      # Magic Formula = 估值+回报
    "damodaran": "value",       # DCF = 估值
}


def load_rules_doc(path: Path) -> dict:
    """加载 yaml 并兼容 garp_rules / rules 双键(lynch 用 garp_rules)。"""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "rules" not in doc:
        for alt in ("garp_rules", "core_rules"):
            if alt in doc:
                doc["rules"] = doc[alt]
                break
    return doc


def list_executable_yamls() -> list[Path]:
    """返回有 rules / garp_rules 的 yaml 文件(跳过 piotroski_bank/insurance,这些通过行业自动切换)。"""
    out = []
    for p in sorted(RULES_DIR.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        if p.stem in ("piotroski_bank", "piotroski_insurance"):
            continue  # 由 engine.run_score 自动切换
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and ("rules" in doc or "garp_rules" in doc):
            out.append(p)
    return out


def list_all_tickers() -> list[tuple[str, str]]:
    import duckdb
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute("SELECT ticker, name FROM companies ORDER BY folder").fetchall()
    finally:
        con.close()


def run_one(rules_path: Path, ticker: str, year: int) -> tuple[float, int, int] | None:
    """返回 (得分, 有效项数, 总规则数);失败返回 None。"""
    try:
        data = ENGINE.load_duckdb_data(ticker)
    except Exception:
        return None

    # 改造版 run_score:统计有效项 + 总规则
    doc = load_rules_doc(rules_path)
    if data.industry in doc.get("exclude_industries", []):
        return None

    # 行业自动切换
    industry_files = doc.get("industry_specific_files") or {}
    specific = industry_files.get(data.industry)
    if specific:
        sp = rules_path.parent / specific
        if sp.exists():
            return run_one(sp, ticker, year)

    rules = doc.get("rules", [])
    if not rules:
        return None

    evaluator = ENGINE.FormulaEvaluator(data, year)
    score = 0.0
    valid = 0
    for rule in rules:
        f = rule["formula"]
        # 跳过多行/嵌套公式(damodaran 的 DCF / lynch 的复合表达式)
        if "\n" in f or "==" in f or "Z'" in f or "DCF" in f:
            continue
        result = evaluator.eval(f)
        if result is None:
            continue
        valid += 1
        if bool(result):
            score += rule.get("score_if_pass", 1)
        else:
            score += rule.get("score_if_fail", 0)
    return score, valid, len(rules)


def aggregate_by_style(per_master: dict[str, tuple[float, int, int] | None]) -> dict[str, tuple[float, float]]:
    """按 value / growth 风格聚合,返回归一化分(0-100)。"""
    style_score = {"value": (0.0, 0), "growth": (0.0, 0)}
    for master, result in per_master.items():
        if result is None:
            continue
        score, valid, total = result
        style = MASTER_STYLE.get(master)
        if style is None or valid == 0:
            continue
        # 归一化到 0-1 后累加(避免不同大师 max_score 不一致)
        normalized = score / total if total else 0
        prev_score, prev_count = style_score[style]
        style_score[style] = (prev_score + normalized, prev_count + 1)
    return {
        s: (round(100 * total_score / count, 1) if count else 0.0, count)
        for s, (total_score, count) in style_score.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--tickers", help="逗号分隔(默认全 15 家)")
    args = ap.parse_args()

    yamls = list_executable_yamls()
    masters = [p.stem for p in yamls]
    print(f"\n📚 可执行规则:{len(yamls)} 套 → {', '.join(masters)}\n")

    if args.tickers:
        tickers = [(t.strip(), t.strip()) for t in args.tickers.split(",")]
    else:
        tickers = list_all_tickers()

    # 表头
    header = f"{'公司':<12}" + "".join(f"{m:>14}" for m in masters) + f"{'价值':>10}{'成长':>10}"
    sep = "─" * len(header)
    print(header)
    print(sep)

    md_lines = [
        "# 大师评分 · 全维度矩阵",
        "",
        f"> 数据源:`data/preson.duckdb` · 引擎:[engine.py](../../.tools/score/engine.py)",
        f">",
        f"> **生成命令**:`python3 .tools/score/multi_master.py --year {args.year}`",
        f">",
        f"> 评分格式:**得分/总规则数(可跑项数)** · 价值/成长 = 风格聚合(0-100,归一化均值)",
        "",
        "## 矩阵",
        "",
        "| 公司 | " + " | ".join(masters) + " | 价值评分 | 成长评分 |",
        "|------|" + "|".join(["------"] * len(masters)) + "|------|------|",
    ]

    for ticker, name in tickers:
        per_master: dict[str, tuple[float, int, int] | None] = {}
        cells = []
        for yaml_path, master in zip(yamls, masters):
            res = run_one(yaml_path, ticker, args.year)
            per_master[master] = res
            if res is None:
                cells.append("—")
            else:
                score, valid, total = res
                cells.append(f"{int(score)}/{total}({valid})")

        styles = aggregate_by_style(per_master)
        value_score, value_n = styles["value"]
        growth_score, growth_n = styles["growth"]

        # 控制台
        cells_console = [c.replace("(", "(") for c in cells]
        row = f"{name:<10}" + "".join(f"{c:>14}" for c in cells_console) + f"{value_score:>9.1f}{growth_score:>10.1f}"
        print(row)

        # markdown
        md_lines.append(
            f"| {name} | " + " | ".join(cells) + f" | **{value_score:.1f}** | **{growth_score:.1f}** |"
        )

    md_lines.append("")
    md_lines.append("## 解读")
    md_lines.append("")
    md_lines.append("- **得分/总规则数(可跑项数)**:可跑项 << 总规则数 = 数据缺口大,得分参考性低")
    md_lines.append("- **价值评分**:piotroski + graham + altman + greenblatt + damodaran 中可跑项归一化均值 × 100")
    md_lines.append("- **成长评分**:buffett + lynch 中可跑项归一化均值 × 100")
    md_lines.append("- 大部分大师当前因 BS/EV/EBIT 等字段缺失只跑 1-2 项 — 这是 P3 / 后续 ingest 扩展的目标,详见 [评分体系数据缺口.md](评分体系数据缺口.md)")
    md_lines.append("")
    md_lines.append(f"## 字段说明")
    md_lines.append("")
    md_lines.append("| 大师 | 风格归属 | 当前可跑项 | 主要缺什么 |")
    md_lines.append("|------|------|------|------|")
    md_lines.append("| piotroski | 价值 | 9/9(P1 衍生改写) | 无(完整) |")
    md_lines.append("| graham | 价值 | 2/7 | market_cap / long_term_debt / dividend_history / bvps |")
    md_lines.append("| buffett | 成长 | 1/5 | owner_earnings / roic / buyback_yield |")
    md_lines.append("| lynch | 成长 | 1/5 | total_liabilities / institutional_holding / insider_buying |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n📝 markdown 报告 → {REPORT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
