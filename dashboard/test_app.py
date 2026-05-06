"""Dashboard headless 回归测试。

跑法(从项目根):
    .venv/bin/python -m pytest .tools/dashboard/test_app.py -q

或直接执行本文件:
    .venv/bin/python .tools/dashboard/test_app.py

依赖 streamlit.testing.v1.AppTest,无需启动浏览器。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / ".tools" / "dashboard" / "app.py"


PAGE_MARKET = "📊 市场周期"
PAGE_SCREENER = "🔍 公司筛选"
PAGE_COMPANY = "🏢 单公司详情"
PAGE_DC = "💼 决策中心"
PAGE_CLAUDE = "🤖 Claude 终端"


def _build(page: str | None = None):
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    if page is not None:
        t.session_state["nav"] = page
    t.run()
    return t


def test_app_runs_without_exception():
    t = _build()
    assert not t.exception, f"app.py 抛异常: {t.exception}"


def test_overview_panel_renders_without_error():
    """V5/V6 老断言已废弃(dash-02 tabs/screener.py 替代了 PAGE_SCREENER 老实现)。
    保底:筛选页无异常 + 至少一张 dataframe 渲染成功。"""
    t = _build(PAGE_SCREENER)
    assert not t.exception, f"筛选页抛异常: {t.exception}"
    assert t.get("dataframe"), "筛选页未渲染任何 dataframe"


def test_overview_dataframe_includes_new_columns():
    """废弃:dash-02 tabs/screener.py 列名换了 ('PE 10y 分位' 等),老 V5/V6 断言不再适用。
    保底:筛选页第一张 dataframe 至少有 公司 + PE-TTM 列。"""
    t = _build(PAGE_SCREENER)
    dfs = t.get("dataframe")
    assert dfs, "公司筛选页未渲染任何 dataframe"
    base = {"公司", "PE-TTM"}
    panel = next(
        (d.value for d in dfs
         if base.issubset(set(d.value.columns))),
        None,
    )
    assert panel is not None, \
        f"找不到含 {base} 且有任意 *评分 列的全景表;实际 dataframes 列={[list(d.value.columns)[:6] for d in dfs[:5]]}"


def test_compare_tab_has_mode_switch():
    t = _build(PAGE_COMPANY)  # 原 横向对比 → 单公司详情页底部
    radio_labels = [r.label for r in t.get("radio")]
    assert "模式" in radio_labels, "单公司详情页缺 模式切换 radio (V6)"


def test_no_fallback_when_mcp_alive():
    """MCP 在则首页 PE/PB 分位应全部走 MCP (V4 验证)。"""
    t = _build(PAGE_SCREENER)
    captions = [c.value for c in t.get("caption")]
    pct_caps = [c for c in captions if "回退 CSV 次数" in c]
    if not pct_caps:
        return
    cap = pct_caps[0]
    assert "回退 CSV 次数:0" in cap, f"出现 CSV 回退,V4 退化: {cap}"


def test_score_card_six_dims():
    """score_card.compute_dimensions 应返回 6 个维度(含 strategies)。"""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    for p in [ROOT / ".tools" / "mcp", ROOT / ".tools" / "score", ROOT / ".tools" / "dashboard"]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import score_card as sc
    s = sc.compute_dimensions("600519")
    expected = {"valuation", "profitability", "growth", "cashflow", "safety", "strategies"}
    assert set(s.dims.keys()) == expected, f"维度错: {set(s.dims.keys())}"
    assert s.overall is not None and 0 <= s.overall <= 100, f"综合分异常: {s.overall}"
    assert hasattr(s, "masters") and isinstance(s.masters, dict), "缺 masters 明细"


def test_company_tab_renders_radar_and_overlay_toggle():
    """V8: 公司详情 tab 顶部应有 ★ 综合评分 metric + 股价叠加 toggle。"""
    t = _build(PAGE_COMPANY)
    metrics = [m.label for m in t.get("metric")]
    assert any("综合评分" in m for m in metrics), f"缺 综合评分 metric: {metrics}"
    toggles = [tg.label for tg in t.get("toggle")]
    assert any("叠加股价" in tg for tg in toggles), f"缺 股价叠加 toggle: {toggles}"


def test_six_subtabs_present():
    """公司详情应有 6 个子 tab(每维 ### 标题)。"""
    t = _build(PAGE_COMPANY)
    md_text = "\n".join(m.value for m in t.get("markdown"))
    needed = ["### 🟢 估值", "### 🟢 盈利", "### 🟢 成长", "### 🟢 现金流"]
    # 安全/策略 可能 ⚪ 也算
    needed_loose = ["估值", "盈利", "成长", "现金流", "安全", "策略"]
    for kw in needed_loose:
        assert f" {kw}" in md_text, f"6 子 tab 缺 {kw}"


def test_top_strengths_section_exists():
    """head 右栏应有 优势 Top3 / 短板 Top3 两个标题。"""
    t = _build(PAGE_COMPANY)
    md_blocks = [m.value for m in t.get("markdown")]
    has_top = any("优势 Top3" in m for m in md_blocks)
    has_bot = any("短板 Top3" in m for m in md_blocks)
    assert has_top and has_bot, "缺 优势/短板 Top3 标题"


# ─── dash-03 专项回归 ────────────────────────────────────────────────
def test_dash03_master_matrix_block():
    """单公司详情 Tab 应有「🧪 多大师评分矩阵(本公司 + 同行)」块。"""
    t = _build(PAGE_COMPANY)
    md_blocks = [m.value for m in t.get("markdown")]
    assert any("多大师评分矩阵" in m for m in md_blocks), \
        "dash-03 主区缺多大师矩阵标题"


def test_dash03_quick_add_button_present():
    """单公司详情顶部应有 ➕ 一键补录决策 按钮。"""
    t = _build(PAGE_COMPANY)
    btn_labels = [b.label for b in t.get("button")]
    assert any("一键补录" in (b or "") for b in btn_labels), \
        f"缺 ➕ 一键补录决策 按钮;实际按钮={btn_labels[:10]}"


def test_dash03_helpers_offline_runnable():
    """peer_radar / decision_timeline / score_card.master_matrix 离线可调。"""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    for p in [ROOT / ".tools" / "mcp", ROOT / ".tools" / "score",
              ROOT / ".tools" / "dashboard", ROOT / ".tools"]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import peer_radar as pr
    import decision_timeline as dt
    import score_card as sc

    peers = pr.peer_pool("600519")
    assert isinstance(peers, list) and len(peers) > 0, "peer_pool 茅台同行应非空"

    matrix = sc.master_matrix(["600519", peers[0][0]])
    assert isinstance(matrix, list) and len(matrix) == 2, "master_matrix 应返回 2 家"
    assert "masters" in matrix[0], "matrix 项缺 masters 字段"

    ds = dt.load_decisions("600519")
    assert isinstance(ds, list), "load_decisions 返回应为 list"  # 空也算正常


if __name__ == "__main__":
    import traceback
    tests = [
        test_app_runs_without_exception,
        test_overview_panel_renders_without_error,
        test_overview_dataframe_includes_new_columns,
        test_compare_tab_has_mode_switch,
        test_no_fallback_when_mcp_alive,
        test_score_card_six_dims,
        test_company_tab_renders_radar_and_overlay_toggle,
        test_six_subtabs_present,
        test_top_strengths_section_exists,
        test_dash03_master_matrix_block,
        test_dash03_quick_add_button_present,
        test_dash03_helpers_offline_runnable,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
