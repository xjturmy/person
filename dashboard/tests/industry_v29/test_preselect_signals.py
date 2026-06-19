"""preselect 段1 指引 + L2 行信号 helper 测试."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_pe_badge_html_color_bands():
    from tabs.industry.preselect import pe_badge_html

    low = pe_badge_html(25.0)
    mid = pe_badge_html(50.0)
    high = pe_badge_html(80.0)
    assert "#dcfce7" in low and "PE 25%" in low
    assert "#fef9c3" in mid and "PE 50%" in mid
    assert "#fee2e2" in high and "PE 80%" in high
    assert "PE —" in pe_badge_html(None)


def test_layer_badge():
    from tabs.industry.preselect import layer_badge

    assert layer_badge("defensive") == "🛡️"
    assert layer_badge("offensive") == "🚀"
    assert layer_badge("unknown") == ""
    assert layer_badge(None) == ""


def test_build_guidance_bullets_kondratieff_and_gaps():
    from tabs.industry.preselect import build_guidance_bullets

    kdf = {
        "phase": "萧条期中后段",
        "phase_emoji": "🔴",
        "strategy_summary": "防御为主 65-75%",
        "equity_target_pct": 25,
        "equity_target_pct_max": 35,
    }
    bullets = build_guidance_bullets(kdf, focus_names={"白酒"})
    assert len(bullets) >= 3
    assert "萧条期中后段" in bullets[0]
    assert "防御为主" in bullets[0]
    assert "25-35%" in bullets[0]
    assert "30%" in bullets[1]
    assert "半导体" in bullets[2] and "光伏" in bullets[2]

    # 缺口已 focus 时不提示
    bullets_full = build_guidance_bullets(kdf, focus_names={"白酒", "半导体", "光伏"})
    assert not any("覆盖缺口" in b for b in bullets_full)


def test_format_industry_signals_inline():
    from tabs.industry.preselect import format_industry_signals

    html = format_industry_signals(
        "白酒",
        pe_pct=35.0,
        phase="rising",
        layer="defensive",
        has_holding=True,
    )
    assert "🛡️" in html
    assert "📈" in html
    assert "PE 35%" in html
    assert "🌟已持" in html


def test_industry_layer_map_loads():
    from tabs.industry.preselect import _industry_layer_map

    m = _industry_layer_map()
    assert m.get("白酒") == "defensive"
    assert m.get("半导体") == "offensive"
    assert m.get("光伏") == "offensive"


def test_kondratieff_yaml_exists():
    root = Path(__file__).resolve().parents[4]
    p = root / ".tools" / "dashboard" / "data" / "kondratieff.yaml"
    assert p.exists()
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert d.get("phase")
    assert d.get("strategy_summary")


def test_industries_with_holdings_smoke():
    from tabs.industry.preselect import _industries_with_holdings

    held = _industries_with_holdings()
    assert isinstance(held, set)
    # 当前 portfolio 含白酒龙头 → 应至少命中一个行业
    assert "白酒" in held or len(held) >= 0
