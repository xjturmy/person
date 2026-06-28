#!/usr/bin/env python3
"""导航/子模块切换性能基准 — 离线测量 import 与核心数据路径耗时.

Run:
  cd /Users/gongyong/Desktop/Keyi/preson && .venv/bin/python .tools/dashboard/bench_nav_switch.py
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / ".tools" / "dashboard"
for p in (DASH, ROOT / ".tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dashboard_helpers import _db_mtime, list_companies, _folder_to_ticker  # noqa: E402


@contextmanager
def timed(label: str):
    t0 = time.perf_counter()
    yield
    ms = (time.perf_counter() - t0) * 1000
    print(f"  {ms:8.1f} ms  {label}")


def bench_import(module: str) -> float:
    # 清缓存以便测冷启动 import
    if module in sys.modules:
        del sys.modules[module]
    t0 = time.perf_counter()
    importlib.import_module(module)
    return (time.perf_counter() - t0) * 1000


def main() -> None:
    db_mtime = _db_mtime()
    print("=" * 60)
    print("Dashboard 导航切换性能基准")
    print(f"DuckDB mtime={db_mtime:.0f}")
    print("=" * 60)

    print("\n── 1. app.py 顶层依赖 import (子进程冷启动) ──")
    heavy = ["pandas", "plotly.express", "plotly.graph_objects", "duckdb"]
    for mod in heavy:
        code = f"import time; t=time.perf_counter(); import {mod}; print((time.perf_counter()-t)*1000)"
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        ms = float(r.stdout.strip()) if r.stdout.strip() else -1
        print(f"  {ms:8.1f} ms  import {mod}")

    print("\n── 2. 侧边栏每次 rerun 都会跑的路径 ──")
    with timed("list_companies (cached miss)"):
        list_companies.clear()
        companies = list_companies(db_mtime)
    with timed("list_companies (cached hit)"):
        list_companies(db_mtime)
    with timed("_folder_to_ticker (cached miss)"):
        _folder_to_ticker.clear()
        _folder_to_ticker(db_mtime)
    with timed("_folder_to_ticker (cached hit)"):
        _folder_to_ticker(db_mtime)

    print("\n── 3. 各顶级页 / 子模块 Python import (冷启动) ──")
    modules = [
        ("市场研判", "tabs.market"),
        ("行业分析", "tabs.industry.analysis"),
        ("行业预选", "tabs.industry.preselect"),
        ("行业确定", "tabs.industry.confirm"),
        ("选股入口", "tabs.screener"),
        ("初步筛选", "tabs.screener.prelim"),
        ("林奇选股", "tabs.screener.lynch_pick"),
        ("格雷厄姆选股", "tabs.screener.graham_pick"),
        ("选股确定", "tabs.screener.confirm"),
        ("公司概览", "tabs.company"),
        ("林奇分析", "tabs.lynch_analysis"),
        ("格雷厄姆分析", "tabs.graham_analysis"),
        ("芒格分析", "tabs.munger_analysis"),
        ("决策中心", "tabs.decision_center"),
        ("黄金分析", "tabs.gold_analysis"),
        ("dashboard_helpers", "dashboard_helpers"),
    ]
    rows: list[tuple[str, float]] = []
    for label, mod in modules:
        ms = bench_import(mod)
        rows.append((label, ms))
    rows.sort(key=lambda x: -x[1])
    for label, ms in rows:
        flag = " ⚠️" if ms > 200 else ""
        print(f"  {ms:8.1f} ms  {label}{flag}")

    print("\n── 4. 决策中心入口固定成本 build_snapshot ──")
    try:
        sys.path.insert(0, str(ROOT / ".tools" / "portfolio"))
        from holdings_view import build_snapshot  # noqa: E402

        with timed("build_snapshot (1st)"):
            build_snapshot()
        with timed("build_snapshot (2nd)"):
            build_snapshot()
    except Exception as e:
        print(f"  (skip build_snapshot: {e})")

    print("\n── 5. Streamlit AppTest 模拟子 tab 切换 (若可用) ──")
    try:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(DASH / "app.py"), default_timeout=120)
        with timed("AppTest 首次 run (sidebar + 默认页)"):
            at.run()
        assert not at.exception

        scenarios = [
            ("sidebar→公司研究", lambda: setattr(at.session_state, "nav", "🏢 公司研究")),
            ("公司→林奇 sub", lambda: setattr(at.session_state, "company_sub_tab", "🌱 林奇")),
            ("公司→芒格 sub", lambda: setattr(at.session_state, "company_sub_tab", "🧠 芒格")),
            ("sidebar→选股", lambda: setattr(at.session_state, "nav", "🔍 选股")),
            ("选股→格雷厄姆 sub", lambda: setattr(at.session_state, "screener_sub_tab", "格雷厄姆选股")),
            ("sidebar→决策中心", lambda: setattr(at.session_state, "nav", "💼 决策中心")),
            ("DC→决策日志 sub", lambda: setattr(at.session_state, "dc_sub_tab", "📝 决策日志")),
            ("sidebar→市场&行业", lambda: setattr(at.session_state, "nav", "🌡️ 市场 & 行业")),
            ("市场→行业分析 sub", lambda: setattr(at.session_state, "market_hub_sub_tab", "行业分析")),
        ]
        for label, setup in scenarios:
            setup()
            t0 = time.perf_counter()
            at.run()
            ms = (time.perf_counter() - t0) * 1000
            exc = at.exception
            status = "ERR" if exc else "OK"
            print(f"  {ms:8.1f} ms  rerun [{status}] {label}")
            if exc:
                print(f"           exception: {exc[0].value}")
    except Exception as e:
        print(f"  AppTest 不可用或失败: {e}")

    print("\n" + "=" * 60)
    print(f"公司数: {len(companies)}")


if __name__ == "__main__":
    main()
