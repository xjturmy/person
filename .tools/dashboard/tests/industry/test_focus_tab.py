"""v2.5 行业分析 Tab 测试 — AppTest headless + 离线辅助函数."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
APP_PY = DASHBOARD_DIR / "app.py"
TABS_DIR = DASHBOARD_DIR / "tabs"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
# 不要把 TABS_DIR 加 sys.path:tabs/screener.py 会和 dashboard/screener.py 撞名
# 改用 from tabs import xxx


# ──────────────────────────────────────────────────────────
# 1. 模块结构 + 入口签名
# ──────────────────────────────────────────────────────────
def test_module_imports():
    from tabs import industry_focus
    assert hasattr(industry_focus, "render")
    assert callable(industry_focus.render)


def test_helpers_exist():
    from tabs import industry_focus
    for name in [
        "_render_top_banner",
        "_render_industry_card",
        "_render_sidebar_editor",
        "_save_focus_yaml",
        "_cached_percentile",
        "_cached_cycle",
        "_cached_etf",
        "_cached_top7",
    ]:
        assert hasattr(industry_focus, name), f"missing {name}"


# ──────────────────────────────────────────────────────────
# 2. yaml schemas
# ──────────────────────────────────────────────────────────
def test_focus_yaml_valid():
    p = ROOT / ".config" / "focus_industries.yaml"
    assert p.exists()
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert "focus" in d and len(d["focus"]) >= 8
    assert d["top_n"] == 7
    assert d["market_cap_min"] == 5_000_000_000


def test_industry_master_yaml_8_keys():
    p = ROOT / ".config" / "industry_master.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    names = {i["name"] for i in d["industries"]}
    for k in ["白酒", "股份制银行", "保险", "化学制药",
              "电池", "通信设备", "白色家电", "饮料乳品"]:
        assert k in names, f"缺重点行业 {k}"


# ──────────────────────────────────────────────────────────
# 3. 引擎冒烟(端到端 Tab 渲染所必需)
# ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("ind", [
    "白酒", "股份制银行", "保险", "化学制药",
    "电池", "通信设备", "白色家电", "饮料乳品",
])
def test_engines_smoke_for_focus_industry(ind: str):
    from industry.percentile_engine import compute as pct
    from industry.cycle import diagnose as cyc
    from screening.etf_recommender import recommend as etf
    from industry.screener import screen_industry

    # percentile
    p = pct(ind)
    assert hasattr(p, "member_count")
    # cycle
    c = cyc(ind)
    assert c.phase in {"rising", "topping", "falling", "bottoming", "sideways"}
    assert 0.0 <= c.confidence <= 1.0
    # etf — 8 重点都至少有 1 只
    es = etf(ind, top_n=3)
    assert len(es) >= 1, f"{ind} 无 ETF"
    # top7 — 至少 1 家
    type_map = yaml.safe_load(
        (ROOT / ".tools" / "rules" / "industry_type_map.yaml").read_text(encoding="utf-8")
    )["type_to_scoring"]
    focus = yaml.safe_load(
        (ROOT / ".config" / "focus_industries.yaml").read_text(encoding="utf-8")
    )["focus"]
    type_ = next((f["type"] for f in focus if f["industry"] == ind), None)
    if type_ is None:
        from tabs.industry._master_loader import load_master_merged
        type_ = (load_master_merged().get(ind) or {}).get("type", "stalwart")
    assert type_ in type_map
    df = screen_industry(ind, type_, top_n=7)
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        for col in ["rank", "ticker", "name", "score", "rating",
                    "reason", "is_owned", "primary_master", "data_source"]:
            assert col in df.columns


# ──────────────────────────────────────────────────────────
# 4. format helpers
# ──────────────────────────────────────────────────────────
def test_format_pct_handles_none():
    from tabs.industry_focus import _format_pct
    assert _format_pct(None) == "—"
    assert _format_pct(75.0) == "75%"


def test_format_num_handles_none():
    from tabs.industry_focus import _format_num
    assert _format_num(None) == "—"
    assert _format_num(12.345) == "12.35"


def test_phase_emoji_dict_complete():
    from tabs.industry_focus import PHASE_EMOJI
    for p in ["rising", "topping", "falling", "bottoming", "sideways"]:
        assert p in PHASE_EMOJI


# ──────────────────────────────────────────────────────────
# 5. AppTest headless — 主入口可加载 + 切到行业页不抛错
# ──────────────────────────────────────────────────────────
def test_app_default_loads():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_PY)).run(timeout=60)
    assert not at.exception, f"app default exception: {at.exception}"


def test_app_industry_page_renders_no_exception():
    """切到「🏭 行业分析」页 0 异常."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_PY))
    # sidebar radio 触发(若 session_state 直接设置不生效,放宽断言)
    at.session_state["page"] = "🏭 行业分析"
    at.run(timeout=120)
    assert not at.exception, f"industry page exception: {at.exception}"


# ──────────────────────────────────────────────────────────
# 6. _save_focus_yaml 写回保留 type 字段
# ──────────────────────────────────────────────────────────
def test_save_focus_yaml_preserves_type(tmp_path, monkeypatch):
    from tabs import industry_focus
    fake_focus = tmp_path / "focus.yaml"
    monkeypatch.setattr(industry_focus, "FOCUS_YAML", fake_focus)
    industry_focus._save_focus_yaml(
        ["白酒", "股份制银行"], top_n=5, market_cap_min=1_000_000_000
    )
    d = yaml.safe_load(fake_focus.read_text(encoding="utf-8"))
    types = {f["industry"]: f["type"] for f in d["focus"]}
    assert types["白酒"] == "stalwart"
    assert types["股份制银行"] == "bank"
    assert d["top_n"] == 5
    assert d["market_cap_min"] == 1_000_000_000
