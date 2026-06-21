"""v2.4 step-C · 芒格多元思维 Tab 离线 + AppTest 验证。

测试覆盖:
  1. 模块导入 + 关键常量(LATTICE_LAYERS / CHECKLIST_ITEMS / BIASES)结构
  2. _verdict_from_avg() 决策规则边界
  3. _build_decision_md() 完整 markdown 构建
  4. AppTest:Default 页 + PAGE_MUNGER 切换 0 异常
  5. 关键词命中(芒格 / 多元思维 / 决策清单)

运行:
  python3 .tools/dashboard/test_munger_tab.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
APP = DASHBOARD_DIR / "app.py"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))


def test_module_imports():
    """模块可导入,关键常量存在。"""
    from tabs.munger_analysis import (
        LATTICE_LAYERS, CHECKLIST_ITEMS, BIASES, FAILURE_CATEGORIES,
        DECISION_RULES, QUOTES, PRINCIPLES,
        _verdict_from_avg, _build_decision_md, _data_hint_for,
        render,
    )
    assert len(LATTICE_LAYERS) == 4, f"应有 4 层格栅,实际 {len(LATTICE_LAYERS)}"
    assert len(CHECKLIST_ITEMS) == 10, f"应有 10 项清单,实际 {len(CHECKLIST_ITEMS)}"
    assert len(BIASES) == 9, f"应有 9 项偏差,实际 {len(BIASES)}"
    assert len(FAILURE_CATEGORIES) == 4, f"应有 4 大失败路径,实际 {len(FAILURE_CATEGORIES)}"
    assert callable(render)
    print("  ✅ 模块导入 + 4 层格栅 + 10 项清单 + 9 项偏差 + 4 大失败路径")


def test_checklist_structure():
    """每项清单必须有 id / title / questions / weight。"""
    from tabs.munger_analysis import CHECKLIST_ITEMS
    for item in CHECKLIST_ITEMS:
        for k in ("id", "title", "questions", "weight"):
            assert k in item, f"清单项缺 {k}: {item.get('id')}"
        assert isinstance(item["questions"], list) and len(item["questions"]) >= 2
        assert 0 < item["weight"] <= 2
    ids = [it["id"] for it in CHECKLIST_ITEMS]
    assert len(set(ids)) == len(ids), f"清单 id 重复: {ids}"
    print(f"  ✅ 10 项清单结构完整 + id 唯一")


def test_verdict_thresholds():
    """决策规则边界:4.0+ 强烈买 / 3.0-4.0 可买 / 2.0-3.0 观望 / <2.0 PASS。"""
    from tabs.munger_analysis import _verdict_from_avg
    assert _verdict_from_avg(4.5)[1] == "强烈买入"
    assert _verdict_from_avg(4.0)[1] == "强烈买入"
    assert _verdict_from_avg(3.5)[1] == "可以买入"
    assert _verdict_from_avg(3.0)[1] == "可以买入"
    assert _verdict_from_avg(2.5)[1] == "观望"
    assert _verdict_from_avg(2.0)[1] == "观望"
    assert _verdict_from_avg(1.5)[1] == "PASS"
    assert _verdict_from_avg(0.0)[1] == "PASS"
    print("  ✅ 决策规则 4 档边界全通过")


def test_data_hint_pulls_metrics():
    """_data_hint_for 应正确拉 PE/PB/ROE/股息率。"""
    from tabs.munger_analysis import _data_hint_for
    m = {"pe_ttm": 12.5, "pb": 1.8, "dividend_yield": 0.035, "roe": 0.18,
         "gross_margin": 0.45, "net_margin": 0.22, "peg": 0.85}
    h1 = _data_hint_for("checklist_pe_pb_dy", m)
    assert h1 and "12.5" in h1 and "1.80" in h1 and "3.50%" in h1, f"PE/PB/DY hint 异常: {h1}"
    h2 = _data_hint_for("checklist_roe", m)
    assert h2 and "18.0%" in h2 and "45.0%" in h2 and "22.0%" in h2, f"ROE hint 异常: {h2}"
    h3 = _data_hint_for("checklist_peg", m)
    assert h3 and "0.85" in h3, f"PEG hint 异常: {h3}"
    h4 = _data_hint_for(None, m)
    assert h4 is None
    print(f"  ✅ data_hint:{h1} | {h2} | {h3}")


def test_build_decision_md():
    """_build_decision_md 应生成完整 markdown,含五大区块。"""
    from tabs.munger_analysis import _build_decision_md, CHECKLIST_ITEMS, BIASES
    m = {"pe_ttm": 25.0, "pb": 5.0, "roe": 0.30, "dividend_yield": 0.018}
    checklist = {
        "scores": {it["id"]: 4 for it in CHECKLIST_ITEMS},
        "avg": 4.0, "label": "强烈买入",
    }
    reverse = {
        "flagged": {"industry": ["颠覆性技术出现(如柯达被数码相机)"], "competition": [],
                    "management": [], "macro": []},
        "notes": {"industry": "AI 替代风险待观察",
                  "competition": "", "management": "", "macro": ""},
        "total_flagged": 1,
    }
    biases = {
        "triggered": {bn: (i < 2) for i, (bn, _, _) in enumerate(BIASES)},
        "n_triggered": 2,
    }
    md = _build_decision_md(
        ticker="600519", company="贵州茅台", m=m,
        checklist=checklist, reverse=reverse, biases=biases,
    )
    # 5 大区块都在
    for keyword in ["一、当前估值快照", "二、10 项决策清单评分",
                    "三、反向思维(失败路径)", "四、心理偏差自检", "五、综合结论"]:
        assert keyword in md, f"md 缺 {keyword}"
    # 估值数据写入
    assert "PE-TTM:25.0" in md
    assert "PB:5.00" in md
    # 评分写入
    assert "4.00 / 5.0" in md
    # 反向思维
    assert "颠覆性技术" in md
    # 偏差
    assert "确认偏差" in md
    # 综合结论
    assert "强烈买入" in md or "可以买入" in md
    print(f"  ✅ md 生成 {len(md)} 字符 / 5 区块齐全")


def test_apptest_default_runs():
    """AppTest:Default 页(市场周期)运行 0 异常。"""
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    t.run()
    assert not t.exception, f"Default 页异常: {t.exception}"
    print("  ✅ AppTest Default 页 0 异常")


def test_apptest_munger_page():
    """AppTest:切到 PAGE_COMPANY(芒格 sub-tab)后 0 异常 + 关键词命中。

    v2.7 简化导航:11 → 5 顶级页面;芒格从顶级 PAGE_MUNGER 降为
    🏢 公司研究 → 🧠 芒格 sub-tab。原 `nav = "🧠 芒格多元思维"`
    在 PAGES list 内不存在,会落到默认页(市场&行业),关键词全 0 命中。
    """
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    t.session_state["nav"] = "🏢 公司研究"
    t.run()
    assert not t.exception, f"PAGE_COMPANY 异常: {t.exception}"

    # 把所有 markdown / caption / subheader 文本拼起来检查
    all_text_chunks = []
    for el_type in ("markdown", "caption", "subheader", "header", "title"):
        try:
            for el in t.get(el_type):
                if hasattr(el, "value") and el.value:
                    all_text_chunks.append(str(el.value))
        except Exception:
            pass
    all_text = "\n".join(all_text_chunks)

    # 关键词命中
    keywords = ["芒格", "多元思维", "决策"]
    hits = [k for k in keywords if k in all_text]
    assert len(hits) >= 2, f"关键词命中 {len(hits)}/{len(keywords)}: {hits}"
    print(f"  ✅ AppTest PAGE_MUNGER 0 异常 / 关键词命中 {len(hits)}/{len(keywords)}: {hits}")


def test_apptest_munger_subtabs_render():
    """切到 PAGE_COMPANY → 芒格 sub-tab + 验证 5 sub-tab 内容(markdown 标题)都被渲染。

    v2.7:芒格降为 🏢 公司研究 → 🧠 芒格 sub-tab。Streamlit AppTest 默认会执行
    所有 st.tabs() 分支体,5 个 munger 内部 sub-tab 的 markdown 都会被渲染到 t.markdown。
    """
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_file(str(APP), default_timeout=120)
    t.session_state["nav"] = "🏢 公司研究"
    t.run()
    assert not t.exception, f"异常: {t.exception}"

    # 拼起所有 markdown 文本
    all_md_chunks: list[str] = []
    try:
        for el in t.markdown:
            if hasattr(el, "value") and el.value:
                all_md_chunks.append(str(el.value))
    except Exception:
        pass
    all_md = "\n".join(all_md_chunks)

    # 5 sub-tab 各自的 section header(我在 _render_step1~5 里渲染的)
    expected_keys = [
        "多元思维格栅",       # ① _render_step1_lattice
        "决策检查清单",       # ② _render_step2_checklist
        "反向思维",           # ③ _render_step3_reverse
        "心理偏差自检",       # ④ _render_step4_biases
        "决策报告导出",       # ⑤ _render_step5_export
    ]
    hits = [k for k in expected_keys if k in all_md]
    assert len(hits) >= 4, (
        f"sub-tab 内容命中 {len(hits)}/5: 期望 {expected_keys}, "
        f"全 markdown 长度={len(all_md)}"
    )
    print(f"  ✅ 5 sub-tab 内容全部渲染 ({len(hits)}/{len(expected_keys)}): {hits}")


if __name__ == "__main__":
    import traceback
    tests = [
        test_module_imports,
        test_checklist_structure,
        test_verdict_thresholds,
        test_data_hint_pulls_metrics,
        test_build_decision_md,
        test_apptest_default_runs,
        test_apptest_munger_page,
        test_apptest_munger_subtabs_render,
    ]
    failed = 0
    print(f"运行 {len(tests)} 个测试 …")
    print()
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print()
    if failed == 0:
        print(f"✅ 全部 {len(tests)} 个测试通过")
        sys.exit(0)
    else:
        print(f"❌ {failed}/{len(tests)} 失败")
        sys.exit(1)
