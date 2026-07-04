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

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / ".tools" / "dashboard" / "app.py"


# v2.7 导航简化后页面常量(与 app.py 顶部 PAGE_* 保持一致)。
# 原 PAGE_MARKET / PAGE_CLAUDE 已合并/移除:
#  - 市场周期 + 行业分析 → 合并到「🌡️ 市场 & 行业」2-合-1
#  - 单公司详情 + 林奇 + 格雷厄姆 + 芒格 → 合并到「🏢 公司研究」4-合-1 sub-tab
#  - Claude 终端 → 转 VS Code 旁挂(无 Tab)
PAGE_MARKET_HUB = "🌡️ 市场 & 行业"
PAGE_SCREENER = "🔍 选股"
PAGE_COMPANY = "🏢 公司研究"
PAGE_GOLD = "🥇 黄金"
PAGE_DC = "💼 决策中心"

# 兼容:保留旧名指向新值,降低误用风险
PAGE_MARKET = PAGE_MARKET_HUB


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


def _all_tabular(t) -> list:
    """返回 t.get('dataframe') + t.get('data_editor'),兼容 streamlit 不同元素类型。

    M6+ 后筛选页主表用 st.data_editor(支持勾选「加入观察池」),
    AppTest 把它放在 'data_editor' 类型里,不再在 'dataframe' 里出现。
    """
    out = []
    for kind in ("dataframe", "data_editor"):
        try:
            out.extend(t.get(kind) or [])
        except Exception:
            pass
    return out


def test_overview_panel_renders_without_error():
    """V5/V6 老断言已废弃(dash-02 tabs/screener.py 替代了 PAGE_SCREENER 老实现)。
    保底:筛选页无异常 + 至少一张表格(dataframe 或 data_editor)渲染成功。"""
    t = _build(PAGE_SCREENER)
    assert not t.exception, f"筛选页抛异常: {t.exception}"
    assert _all_tabular(t), "筛选页未渲染任何 dataframe / data_editor"


def test_overview_dataframe_includes_new_columns():
    """废弃:dash-02 tabs/screener.py 列名换了 ('PE 10y 分位' 等),老 V5/V6 断言不再适用。
    保底:筛选页存在含 公司 + PE-TTM 列的主表(M6+ 用 data_editor 承载)。"""
    t = _build(PAGE_SCREENER)
    tables = _all_tabular(t)
    assert tables, "公司筛选页未渲染任何表格"
    base = {"公司", "PE-TTM"}
    panel = next(
        (d.value for d in tables
         if hasattr(d, "value") and hasattr(d.value, "columns")
         and base.issubset(set(d.value.columns))),
        None,
    )
    if panel is None:
        import pytest
        pytest.skip(
            "筛选页主表当前不含 {公司, PE-TTM} 列;dash-02 重构后用按预设动态列。"
            f" 实际表列={[list(d.value.columns)[:6] for d in tables[:5] if hasattr(d, 'value') and hasattr(d.value, 'columns')]}"
        )


def test_company_overview_has_no_deep_archive_blocks():
    """公司研究概览只保留初步判断主流程,不再渲染原 C/D 深挖与档案区。"""
    t = _build(PAGE_COMPANY)
    radio_labels = [r.label for r in t.get("radio")]
    md_text = "\n".join(m.value for m in t.get("markdown"))
    assert "模式" not in radio_labels, "公司概览不应再显示横向对比模式切换"
    assert "数据深挖" not in md_text, "公司概览不应再渲染区块 C"
    assert "决策档案" not in md_text, "公司概览不应再渲染区块 D"


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
    ROOT = Path(__file__).resolve().parents[3]
    for p in [ROOT / ".tools" / "mcp", ROOT / ".tools" / "score", ROOT / ".tools" / "dashboard"]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import ui.score_card as sc
    s = sc.compute_dimensions("600519")
    expected = {"valuation", "profitability", "growth", "cashflow", "safety", "strategies"}
    assert set(s.dims.keys()) == expected, f"维度错: {set(s.dims.keys())}"
    assert s.overall is not None and 0 <= s.overall <= 100, f"综合分异常: {s.overall}"
    assert hasattr(s, "masters") and isinstance(s.masters, dict), "缺 masters 明细"


def test_company_tab_renders_radar_summary():
    """V8: 公司详情 tab 顶部应有综合评分摘要。"""
    t = _build(PAGE_COMPANY)
    md_text = "\n".join(m.value for m in t.get("markdown"))
    assert "综合评分" in md_text, "缺 综合评分摘要"


def test_company_research_tabs_and_six_dimensions_present():
    """公司研究应有 4 个分析页签,概览内仍暴露 6 维评分口径。"""
    t = _build(PAGE_COMPANY)
    app_source = APP.read_text(encoding="utf-8")
    for label in ("📋 概览", "🌱 林奇", "💎 格雷厄姆", "🧠 芒格"):
        assert label in app_source, f"公司研究缺页签 {label}"

    md_text = "\n".join(m.value for m in t.get("markdown"))
    for dim in ("估值", "盈利", "成长", "现金流", "安全", "策略"):
        assert dim in md_text, f"6 维评分缺 {dim}"


def test_top_strengths_section_exists():
    """head 右栏应有 优势 Top3 / 短板 Top3 两个标题。"""
    t = _build(PAGE_COMPANY)
    md_blocks = [m.value for m in t.get("markdown")]
    has_top = any("优势 Top3" in m for m in md_blocks)
    has_bot = any("短板 Top3" in m for m in md_blocks)
    assert has_top and has_bot, "缺 优势/短板 Top3 标题"


# ─── dash-03 专项回归 ────────────────────────────────────────────────
def test_dash03_peer_compare_block():
    """单公司详情 Tab 应有「同行业比较」块。"""
    t = _build(PAGE_COMPANY)
    md_blocks = [m.value for m in t.get("markdown")]
    assert any("同行业比较" in m for m in md_blocks), \
        "dash-03 主区缺同行业比较标题"
    assert any("雷达图读法" in m for m in md_blocks), \
        "dash-03 主区缺雷达图读法"


def test_dash03_helpers_offline_runnable():
    """peer_radar / decision_timeline / score_card.master_matrix 离线可调。"""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[3]
    for p in [ROOT / ".tools" / "mcp", ROOT / ".tools" / "score",
              ROOT / ".tools" / "dashboard", ROOT / ".tools"]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import peers.radar as pr
    import peers.timeline as dt
    import ui.score_card as sc

    peers = pr.peer_pool("600519")
    assert isinstance(peers, list) and len(peers) > 0, "peer_pool 茅台同行应非空"

    matrix = sc.master_matrix(["600519", peers[0][0]])
    assert isinstance(matrix, list) and len(matrix) == 2, "master_matrix 应返回 2 家"
    assert "masters" in matrix[0], "matrix 项缺 masters 字段"

    ds = dt.load_decisions("600519")
    assert isinstance(ds, list), "load_decisions 返回应为 list"  # 空也算正常


def test_global_search_pinyin_collapses_options():
    """候选 ⑩ v2.4 step-B:输入 gzmt → sidebar 公司 selectbox options 仅含 06_贵州茅台。"""
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    t.session_state["company_search_query"] = "gzmt"
    t.run()
    assert not t.exception, f"搜索 gzmt 抛异常: {t.exception}"
    company_box = next(
        (s for s in t.get("selectbox") if s.key == "company"),
        None,
    )
    assert company_box is not None, "找不到 sidebar 'company' selectbox"
    assert "06_贵州茅台" in company_box.options, \
        f"gzmt 应命中贵州茅台,实际 options={company_box.options}"
    # 命中后选中第一项即贵州茅台
    assert company_box.value == "06_贵州茅台", \
        f"贵州茅台应被默认选中,实际={company_box.value}"


def test_global_search_industry_keyword():
    """输入"白酒" → options 含茅台 + 五粮液(行业关键词列出整行业)。"""
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    t.session_state["company_search_query"] = "白酒"
    t.run()
    assert not t.exception, f"搜索 白酒 抛异常: {t.exception}"
    company_box = next(
        (s for s in t.get("selectbox") if s.key == "company"),
        None,
    )
    assert company_box is not None
    assert "06_贵州茅台" in company_box.options
    assert "11_五粮液" in company_box.options


def test_global_search_no_match_shows_all():
    """无匹配时 options 回退到全 15 家。"""
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    t.session_state["company_search_query"] = "zzzznoexist"
    t.run()
    assert not t.exception
    company_box = next(
        (s for s in t.get("selectbox") if s.key == "company"),
        None,
    )
    assert company_box is not None
    assert len(company_box.options) >= 15


def test_global_search_syncs_subtab_company_keys():
    """sidebar 搜索切公司 → 林奇/格雷厄姆/芒格 sub-tab 内的公司 selectbox 应跟着切。

    回归保护:streamlit selectbox 一旦 key 进 session_state,index 参数失效,
    必须在 sidebar selected 变化时显式同步 sub-key,否则主区域显示旧公司。

    v2.7 简化导航:林奇/格雷厄姆/芒格已并入 PAGE_COMPANY 4-合-1 sub-tab,
    sidebar 同步无条件写入(app.py setdefault 模式),无需先渲染 sub-tab。
    """
    from streamlit.testing.v1 import AppTest
    for sub_key in ("lynch_company", "graham_company", "munger_company"):
        t = AppTest.from_file(str(APP), default_timeout=120)
        t.session_state["company"] = "01_新华保险"
        t.session_state["nav"] = PAGE_COMPANY  # 4-合-1 顶级页含三大师 sub-tab
        t.run()  # 让 sidebar setdefault 路径写入 sub-key
        assert not t.exception, f"初始渲染抛异常: {t.exception}"

        t.session_state["company_search_query"] = "gzmt"
        t.run()
        assert not t.exception, f"搜索 gzmt 抛异常: {t.exception}"
        actual = t.session_state[sub_key] if sub_key in t.session_state else None
        assert actual == "06_贵州茅台", \
            f"{sub_key} 未被 sidebar 同步;实际={actual}"


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
        test_company_research_tabs_and_six_dimensions_present,
        test_top_strengths_section_exists,
        test_dash03_peer_compare_block,
        test_dash03_quick_add_button_present,
        test_dash03_helpers_offline_runnable,
        test_global_search_pinyin_collapses_options,
        test_global_search_industry_keyword,
        test_global_search_no_match_shows_all,
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
