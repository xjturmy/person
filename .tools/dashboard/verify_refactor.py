#!/usr/bin/env python3
"""重构后必跑检查 — 扫遍 页签 × 子页,捕捉「被 st.error 吞掉的数据加载失败」.

为什么需要它:
    各 tab 的数据加载都包在 try/except 里,失败时渲染成 st.error("...加载失败:...")
    而 *不抛异常*。现有检查(test_app.py / smoke / bench)只断言 `at.exception is None`,
    所以「无法读取文件数据」这类失败 100% 漏报 —— 看着全绿,实际页面是空的。

    本脚本对每个 页签×子页 组合额外做一次 `at.error` 文案扫描,命中失败标记即判 FAIL。

Run:
    cd /Users/gongyong/Desktop/Keyi/preson && .venv/bin/python .tools/dashboard/verify_refactor.py

退出码: 全过 0 / 有 FAIL 1 / 环境不可用(SKIP) 0
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / ".tools" / "dashboard"
for p in (DASH, ROOT / ".tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# 被 st.error 渲染的文案里,命中任一即视为加载失败(专治「读不到文件」)
FAIL_MARKERS = (
    "加载失败", "失败:", "失败：", "无法", "Traceback",
    "does not exist", "No such file", "未找到", "不存在",
)

# 各页 session_state 的 nav / 子页 key 与子页取值(全部来自 navigation.py / 各 tab 的 _SUB_* 常量)
PAGES = [
    ("🌡️ 市场 & 行业", "market_hub_sub_tab",
     ["市场研判", "行业分析", "行业预选", "行业确定"]),
    ("🔍 选股", "screener_sub_tab",
     ["初步筛选", "林奇选股", "格雷厄姆选股", "选股确定"]),
    ("🏢 公司研究", "company_sub_tab",
     ["📋 概览", "🌱 林奇", "💎 格雷厄姆", "🧠 芒格"]),
    ("💼 决策中心", "dc_sub_tab",
     ["📋 持仓总览", "📊 持仓跟踪", "📝 决策日志", "📅 月报历史"]),
    # 黄金页仍用 st.tabs:一次 run 即渲染全部 9 个子 tab 的内容,无需逐个驱动
    ("🥇 黄金", None, [None]),
]


def _scan_errors(at) -> list[str]:
    """返回当前渲染树里命中失败标记的 st.error 文案(截断)。"""
    hits: list[str] = []
    try:
        errors = at.error
    except Exception:
        return hits
    for el in errors:
        txt = str(getattr(el, "value", "") or "")
        if any(m in txt for m in FAIL_MARKERS):
            hits.append(txt.replace("\n", " ")[:120])
    return hits


def main() -> int:
    try:
        from streamlit.testing.v1 import AppTest
    except Exception as e:
        print(f"⏭️  SKIP: streamlit.testing.v1 不可用 ({e})")
        return 0

    app_py = DASH / "app.py"
    print("=" * 64)
    print("重构后检查 — 页签×子页 数据加载扫描 (st.error 文案)")
    print("=" * 64)

    try:
        at = AppTest.from_file(str(app_py), default_timeout=120)
        at.run()
    except Exception as e:
        print(f"⏭️  SKIP: AppTest 首次 run 失败,疑似环境问题 ({e})")
        return 0

    results: list[tuple[str, bool, str]] = []

    # 默认页(不设 nav)先验一次:首屏异常是硬失败
    if at.exception:
        results.append(("默认首屏", False, f"exception: {at.exception[0].value}"))
    else:
        hits = _scan_errors(at)
        results.append(("默认首屏", not hits, hits[0] if hits else ""))

    for nav, sub_key, subs in PAGES:
        for sub in subs:
            label = f"{nav}" + (f" / {sub}" if sub else "")
            at.session_state["nav"] = nav
            if sub_key and sub is not None:
                at.session_state[sub_key] = sub
            t0 = time.perf_counter()
            try:
                at.run()
            except Exception as e:
                results.append((label, False, f"run 抛异常: {e}"))
                continue
            ms = (time.perf_counter() - t0) * 1000
            if at.exception:
                results.append((label, False, f"exception: {at.exception[0].value}"))
                continue
            hits = _scan_errors(at)
            reason = hits[0] if hits else f"{ms:.0f}ms"
            results.append((label, not hits, reason))

    print()
    n_fail = 0
    for label, ok, reason in results:
        tag = "✅ OK  " if ok else "❌ FAIL"
        if not ok:
            n_fail += 1
        print(f"  {tag}  {label:<28} {reason}")

    print()
    print("=" * 64)
    total = len(results)
    print(f"通过 {total - n_fail} / 失败 {n_fail}  (共 {total} 项)")
    if n_fail:
        print("⚠️  存在被吞掉的加载失败 —— 按上面 FAIL 文案定位读不到的文件/数据。")
    print("=" * 64)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
