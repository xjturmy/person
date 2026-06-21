"""peg_curve 离线单测 — 跑真实 DuckDB 数据.

注意:本文件原为脚本式执行,顶层 sys.exit(1) 会让 pytest collect 阶段崩溃。
现已包到 _run_all() + __main__ guard;pytest 调用 test_peg_curve_smoke()
走相同逻辑但用 assert 而非 sys.exit。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd

from valuation.peg_curve import (
    build_peg_series,
    compute_profit_ttm,
    compute_ttm_yoy,
    grade_peg,
)


def _run_all() -> list[str]:
    """脚本/pytest 共用主体,返回失败描述列表(空=全过)。"""
    errs: list[str] = []

    def expect(c: bool, msg: str) -> None:
        print(f"  {'✅' if c else '❌'} {msg}")
        if not c:
            errs.append(msg)

    # ─── grade_peg 5 档 ───
    print("─── grade_peg 5 档评级 ───")
    expect(grade_peg(0.3).label.startswith("🟢🟢"), "<0.5 极度低估")
    expect(grade_peg(0.8).label.startswith("🟢 "), "0.5-1 合理偏低")
    expect(grade_peg(1.2).label.startswith("🟡"), "1-1.5 略贵")
    expect(grade_peg(1.8).label.startswith("🟠"), "1.5-2 高估")
    expect(grade_peg(3.0).label.startswith("🔴"), ">2 严重高估")
    expect(grade_peg(float("nan")).label.startswith("⚪"), "NaN 不适用")

    # ─── compute_profit_ttm 单元逻辑 ───
    print("─── compute_profit_ttm:Q4 = 当年报告值 ───")
    mock = pd.DataFrame([
        {"date": "2024-03-31", "value": 100},
        {"date": "2024-06-30", "value": 250},
        {"date": "2024-09-30", "value": 380},
        {"date": "2024-12-31", "value": 500},  # 全年
        {"date": "2025-03-31", "value": 120},
        {"date": "2025-06-30", "value": 280},
        {"date": "2025-09-30", "value": 420},
        {"date": "2025-12-31", "value": 560},  # 全年
    ])
    ttm = compute_profit_ttm(mock)
    ttm = ttm.set_index("date")
    expect(float(ttm.loc["2024-12-31", "ttm"]) == 500, "Q4 TTM = 当年累计 500")
    expect(float(ttm.loc["2025-12-31", "ttm"]) == 560, "Q4 TTM = 当年累计 560")
    # 2025-Q1: 120 + 500 - 100 = 520
    expect(float(ttm.loc["2025-03-31", "ttm"]) == 520, f"Q1 TTM=520(得到 {ttm.loc['2025-03-31', 'ttm']})")
    # 2025-Q2: 280 + 500 - 250 = 530
    expect(float(ttm.loc["2025-06-30", "ttm"]) == 530, "Q2 TTM=530")
    # 2025-Q3: 420 + 500 - 380 = 540
    expect(float(ttm.loc["2025-09-30", "ttm"]) == 540, "Q3 TTM=540")

    # ─── compute_ttm_yoy ───
    print("─── compute_ttm_yoy ───")
    yoy = compute_ttm_yoy(ttm.reset_index())
    yoy = yoy.set_index("date")
    # 2025-12 TTM YoY = (560/500 - 1)*100 = 12%
    expect(abs(float(yoy.loc["2025-12-31", "ttm_yoy_pct"]) - 12.0) < 0.001,
           f"2025 年报 YoY=12%(得到 {yoy.loc['2025-12-31', 'ttm_yoy_pct']:.2f}%)")

    # ─── 真实数据集成测试(需 DuckDB)───
    print("─── 真实数据(比亚迪 002594)───")
    ROOT = Path(__file__).resolve().parents[4]
    DB = ROOT / "data" / "preson.duckdb"
    if not DB.exists():
        print("  ⚠️  DuckDB 不存在,跳过集成测试")
    else:
        df = build_peg_series("002594", db_path=DB, lookback_years=5)
        expect(not df.empty, f"返回非空(行数 {len(df)})")
        expect("peg" in df.columns and "pe_ttm" in df.columns, "列齐全")

        valid = df.dropna(subset=["peg"])
        print(f"    总行 {len(df)} / 有效 PEG 行 {len(valid)}")
        if not valid.empty:
            last = valid.iloc[-1]
            print(f"    最新 PE-TTM={last['pe_ttm']:.2f} / 3y CAGR={last['growth_pct']:.2f}% / PEG={last['peg']:.2f}")
            # 合理性:PEG 正值
            expect(float(last["peg"]) > 0, "最新 PEG 正值")
            # PEG 应等于 PE / growth_pct
            recomputed = float(last["pe_ttm"]) / float(last["growth_pct"])
            expect(abs(recomputed - float(last["peg"])) < 0.01, "PEG 公式自洽")

        # 多家公司 smoke
        print("─── 多家公司 smoke ───")
        for t, n in [("000333", "美的"), ("600519", "茅台"), ("600036", "招行")]:
            d = build_peg_series(t, db_path=DB, lookback_years=5)
            v = d.dropna(subset=["peg"])
            if v.empty:
                print(f"  • {n}({t}): 无有效 PEG(可能负增长)")
            else:
                print(f"  • {n}({t}): {len(v)} 行有效, 最新 PEG={float(v.iloc[-1]['peg']):.2f}")

        # 不存在的 ticker 兜底
        print("─── 不存在 ticker 兜底 ───")
        bad = build_peg_series("999999", db_path=DB)
        expect(bad.empty, "未知 ticker 返回空 DataFrame")

    return errs


def test_peg_curve_smoke() -> None:
    """pytest 入口:跑全部用例,失败列表非空则断言失败。"""
    errs = _run_all()
    assert not errs, "失败项:\n  - " + "\n  - ".join(errs)


if __name__ == "__main__":
    errs = _run_all()
    print()
    if errs:
        print(f"❌ 失败 {len(errs)} 项")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    print("✅ peg_curve 全部用例通过")
