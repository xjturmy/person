"""格雷厄姆评分体系辅助模块(v2.5 TODO#1 G2/G4)。

提供:
  - compute_ncav_status(ticker)  → Net-Net 极度低估检测(G4)
  - parse_g7_or(rule, metrics)   → g7 PE×PB OR 条件解析(G2)
  - STEPS_TO_YAML_RULES_MAP      → 五步法 ↔ yaml 准则对照(G5)

Author: Claude (v2.5 TODO#1, 2026-05-10)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"


# ═══ G5:五步法 → yaml 准则对照表 ═══════════════════════════════════════════
# 详细说明见 .tools/rules/graham_yaml_steps_mapping.md
STEPS_TO_YAML_RULES_MAP: dict[str, dict] = {
    "step1_classify": {
        "desc": "公司类别判定(深度低估 / 防御 / 进取 / 特殊)",
        "yaml_rules": [],
        "note": "由 graham_steps.py classify_graham_type() 处理,不进 yaml 评分",
    },
    "step2_fundamentals": {
        "desc": "基本面硬指标统计",
        "yaml_rules": ["g1_size", "g2_financial_strength", "g3_earnings_stability"],
        "note": "防御型 7 准则核心 — 规模 / 财务强度 / 盈利稳定性",
    },
    "step3_valuation": {
        "desc": "估值温和性",
        "yaml_rules": ["g6_pe_moderate", "g7_pb_moderate"],
        "note": "g7 v2.5 新增 PE×PB ≤ 22.5 的 OR 条件(高 ROE 公司放宽)",
    },
    "step4_dividends_growth": {
        "desc": "派息记录 + 盈利增长",
        "yaml_rules": ["g4_dividend_record", "g5_earnings_growth"],
        "note": "g4 由 derived_metrics.years_continuous_dividend 提供数据",
    },
    "step4_graham_number": {
        "desc": "Graham Number 估值上限",
        "yaml_rules": ["graham_number_check"],
        "note": "第 4 步估值补充 — √(22.5 × EPS × BVPS) 合理价格上限",
    },
    "step5_ncav": {
        "desc": "净流动资产极端低估检测(Net-Net)",
        "yaml_rules": ["ncav_critical_bonus"],
        "note": "v2.5 新增 +3 bonus;A 股极少触发,触发即极端低估信号",
    },
}


# ═══ G4:NCAV 极度低估计算 ═══════════════════════════════════════════════════

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _latest(con, table: str, ticker: str, metric: str) -> float | None:
    """从指定表取最新非空值。"""
    row = con.execute(
        f"""
        SELECT value FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def compute_ncav_status(ticker: str, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """计算 NCAV(净流动资产)并判断 Net-Net 极端低估状态。

    NCAV = 流动资产 - 总负债
    Net-Net 极度低估条件:市值 < NCAV × 0.67

    数据来源:
      - 流动资产:valuation 表的「流动资产」或 safety 表的派生值
      - 总负债:safety 表(资产负债率 × 总资产,近似)
      - 市值:valuation 表的「总市值」

    返回:
        {
            "ticker": str,
            "ncav": float | None,       # 净流动资产(亿元)
            "market_cap": float | None, # 总市值(亿元)
            "ratio": float | None,      # 市值 / NCAV(< 0.67 = 极度低估)
            "status": str,              # "extreme_undervalue" | "undervalue" | "fair" | "no_data"
            "score_bonus": int,         # 3 = 触发 bonus,0 = 不触发
            "note": str,
        }
    """
    con = _conn(db_path)
    result: dict[str, Any] = {
        "ticker": ticker,
        "ncav": None,
        "market_cap": None,
        "ratio": None,
        "status": "no_data",
        "score_bonus": 0,
        "note": "",
    }
    try:
        # 1. 流动资产与总负债 — 从 safety 表读(理杏仁已提供)
        #    优先用「流动资产合计」;部分公司该字段为 0/NULL,
        #    fallback 用流动比率 × 流动负债合计近似
        current_assets = _latest(con, "safety", ticker, "流动资产合计")
        if current_assets is not None and current_assets <= 0:
            current_assets = None  # 0 视为无效

        if current_assets is None:
            # fallback: 流动资产 = 流动比率 × 流动负债合计
            cr = _latest(con, "safety", ticker, "流动比率")
            cl = _latest(con, "safety", ticker, "流动负债合计")
            if cr is not None and cl is not None and cl > 0:
                current_assets = cr * cl
                result["note"] = "流动资产由(流动比率×流动负债合计)近似,verified=False"
            else:
                result["note"] = "流动资产合计缺失且无法用CR×CL近似"
                return result

        total_liabilities = _latest(con, "safety", ticker, "负债合计")
        if total_liabilities is None:
            result["note"] = (result["note"] or "") + "; 负债合计字段缺失"
            return result

        ncav = current_assets - total_liabilities  # 元
        result["ncav"] = round(ncav / 1e8, 2) if ncav > 1e4 else round(ncav, 4)

        # 2. 总市值 — A 股用「市值(元)」,港股用「市值(港币)」
        mc = _latest(con, "valuation", ticker, "市值(元)")
        if mc is None:
            mc = _latest(con, "valuation", ticker, "市值(港币)")
        if mc is None:
            result["note"] = (result["note"] or "") + "; 市值字段缺失(已试市值(元)/市值(港币))"
            return result
        result["market_cap"] = round(mc / 1e8, 2)

        # 3. 判断状态
        if ncav <= 0:
            result["status"] = "negative_ncav"
            result["note"] = (result["note"] or "") + f"; NCAV < 0({ncav:.2f}),净资产为负"
            return result

        ratio = mc / ncav
        result["ratio"] = round(ratio, 3)

        if ratio < 0.67:
            result["status"] = "extreme_undervalue"
            result["score_bonus"] = 3
            result["note"] = (result["note"] or "") + (
                f"; 市值/NCAV={ratio:.2f} < 0.67 — 极度低估(Net-Net 触发!)"
            )
        elif ratio < 1.0:
            result["status"] = "undervalue"
            result["note"] = (result["note"] or "") + (
                f"; 市值/NCAV={ratio:.2f}(< 1.0 低估,未触发 Net-Net 阈值)"
            )
        else:
            result["status"] = "fair"
            result["note"] = (result["note"] or "") + (
                f"; 市值/NCAV={ratio:.2f}(≥ 1.0 非极端低估)"
            )

    except Exception as e:
        result["note"] = f"计算异常: {e}"
    finally:
        con.close()

    return result


# ═══ G2:g7 OR 条件解析 ═══════════════════════════════════════════════════════

def parse_g7_or(pb: float | None, pe: float | None) -> dict[str, Any]:
    """解析 g7_pb_moderate 的 OR 条件。

    v2.5 G2 实现:PB ≤ 1.5 主条件 OR PE×PB ≤ 22.5 替代条件。

    Args:
        pb: 最新 PB 值
        pe: 最新 PE-TTM 值

    Returns:
        {
            "pass": bool,
            "primary_pass": bool,    # PB ≤ 1.5
            "alt_pass": bool | None, # PE×PB ≤ 22.5(pe 为 None 时 None)
            "pe_x_pb": float | None,
            "reason": str,
            "score": int,            # 0 或 2
        }
    """
    if pb is None:
        return {
            "pass": False,
            "primary_pass": False,
            "alt_pass": None,
            "pe_x_pb": None,
            "reason": "PB 数据缺失",
            "score": 0,
        }

    primary_pass = pb <= 1.5
    pe_x_pb: float | None = None
    alt_pass: bool | None = None

    if pe is not None and pe > 0:
        pe_x_pb = round(pe * pb, 2)
        alt_pass = pe_x_pb <= 22.5

    passed = primary_pass or (alt_pass is True)

    if primary_pass:
        reason = f"PB {pb:.2f} ≤ 1.5 ✅(主条件通过)"
    elif alt_pass is True:
        reason = f"PB {pb:.2f} > 1.5,但 PE×PB = {pe_x_pb:.1f} ≤ 22.5 ✅(替代条件通过)"
    elif alt_pass is False:
        reason = f"PB {pb:.2f} > 1.5,PE×PB = {pe_x_pb:.1f} > 22.5 ❌(两条件均不满足)"
    else:
        reason = f"PB {pb:.2f} > 1.5,PE 数据缺失,无法计算替代条件 ❌"

    return {
        "pass": passed,
        "primary_pass": primary_pass,
        "alt_pass": alt_pass,
        "pe_x_pb": pe_x_pb,
        "reason": reason,
        "score": 2 if passed else 0,
    }


# ═══ CLI 快速验证 ═══════════════════════════════════════════════════════════

def _smoke_test() -> None:
    import csv
    import sys

    companies_csv = ROOT / ".config" / "companies.csv"
    print(f"{'═' * 72}")
    print("  graham_extras 实测(NCAV + g7 OR)")
    print("═" * 72)

    # 测试 g7 OR 条件
    print("\n  [G2] g7 OR 条件测试")
    test_cases = [
        ("招商银行", 0.85, 6.5),
        ("贵州茅台", 8.0, 22.0),
        ("美的集团", 3.2, 14.0),
        ("新华保险", 0.6, 8.0),
    ]
    for name, pb, pe in test_cases:
        r = parse_g7_or(pb, pe)
        flag = "✅" if r["pass"] else "❌"
        print(f"  {name:8s} PB={pb} PE={pe}: {flag} {r['reason']}")

    # 测试 NCAV
    print("\n  [G4] NCAV 状态(4 家公司)")
    targets = [
        ("600036", "招商银行"),
        ("600519", "贵州茅台"),
        ("000333", "美的集团"),
        ("601336", "新华保险"),
    ]
    for ticker, name in targets:
        r = compute_ncav_status(ticker)
        status = r["status"]
        ratio = r["ratio"]
        bonus = r["score_bonus"]
        ratio_str = f"{ratio:.3f}" if ratio is not None else "N/A"
        print(f"  {ticker} {name:6s}: status={status:20s} ratio={ratio_str} bonus={bonus}")
        print(f"           note: {r['note'][:80]}")


if __name__ == "__main__":
    _smoke_test()
