"""test_portfolio_write.py — add_to_portfolio / remove_from_portfolio 单元测试。

覆盖:
  - 空 yaml / 不存在 → 首次写入成功 + 自动建文件
  - 已存在 ticker → 跳过(返回 False)
  - 删除存在 → 成功 + 自动 .bak 备份
  - 删除不存在 → False
  - 保留已有 positions 不被覆盖
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DASH = HERE.parent.parent  # .tools/dashboard
if str(DASH) not in sys.path:
    sys.path.insert(0, str(DASH))

from valuation.fair_price import (  # noqa: E402
    add_to_portfolio,
    remove_from_portfolio,
    is_in_portfolio,
    load_portfolio,
)


def test_add_to_empty_file_creates(tmp_path):
    """yaml 不存在 → 创建新文件并写入"""
    path = tmp_path / "portfolio.yaml"
    assert add_to_portfolio("600519", "贵州茅台", path=path)
    assert path.exists()
    assert is_in_portfolio("600519", path=path)


def test_add_duplicate_skipped(tmp_path):
    path = tmp_path / "portfolio.yaml"
    add_to_portfolio("600519", "贵州茅台", path=path)
    # 第二次添加同 ticker → False
    assert add_to_portfolio("600519", "贵州茅台", path=path) is False


def test_add_empty_ticker_rejected(tmp_path):
    path = tmp_path / "portfolio.yaml"
    assert add_to_portfolio("", "x", path=path) is False
    assert not path.exists()


def test_remove_existing(tmp_path):
    path = tmp_path / "portfolio.yaml"
    add_to_portfolio("600519", "贵州茅台", path=path)
    add_to_portfolio("000333", "美的集团", path=path)
    assert remove_from_portfolio("600519", path=path)
    assert not is_in_portfolio("600519", path=path)
    assert is_in_portfolio("000333", path=path)  # 其余不动


def test_remove_nonexistent(tmp_path):
    path = tmp_path / "portfolio.yaml"
    add_to_portfolio("600519", "贵州茅台", path=path)
    assert remove_from_portfolio("999999", path=path) is False


def test_remove_creates_backup(tmp_path):
    path = tmp_path / "portfolio.yaml"
    add_to_portfolio("600519", "贵州茅台", path=path)
    remove_from_portfolio("600519", path=path)
    bak = path.with_suffix(path.suffix + ".bak")
    assert bak.exists()


def test_preserve_existing_richer_entries(tmp_path):
    """已有详细 holdings(school/rationale/criteria) 不应被覆盖(v2.8+:positions → holdings)"""
    path = tmp_path / "portfolio.yaml"
    initial = {
        "holdings": [{
            "ticker": "600519", "name": "贵州茅台", "status": "watch",
            "school": "价值",
            "rationale": "PE 处于历史低位",
            "criteria_met": ["PE-TTM 10y 分位 ≤ 25%", "ROE ≥ 20%"],
            "review_triggers": ["PE > 30"],
        }]
    }
    path.write_text(yaml.safe_dump(initial, allow_unicode=True), encoding="utf-8")
    # 添加新 ticker
    assert add_to_portfolio("000333", "美的集团", path=path)
    # 原有 detail 保留
    portfolio = load_portfolio(path)
    assert portfolio["600519"].school == "价值"
    assert "PE-TTM 10y 分位 ≤ 25%" in portfolio["600519"].criteria_met
    assert portfolio["000333"].name == "美的集团"


def test_added_entry_has_placeholder_fields(tmp_path):
    path = tmp_path / "portfolio.yaml"
    add_to_portfolio("600519", "贵州茅台", path=path)
    portfolio = load_portfolio(path)
    entry = portfolio["600519"]
    assert entry.school == "未分类"
    assert entry.rationale == "(待填写)"
    assert entry.criteria_met == []
    assert entry.review_triggers == []
