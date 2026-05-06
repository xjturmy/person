"""loader.save_portfolio / upsert_holdings 单测."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from loader import load_yaml_dict, save_portfolio, upsert_holdings  # noqa: E402

errs: list[str] = []


def expect(c: bool, msg: str) -> None:
    print(f"  {'✅' if c else '❌'} {msg}")
    if not c:
        errs.append(msg)


with tempfile.TemporaryDirectory() as td:
    test_yaml = Path(td) / "portfolio.yaml"
    test_yaml.write_text(yaml.safe_dump({
        "_meta": {"version": "1.0", "status": "demo", "base_currency": "CNY"},
        "account": {"total_capital": 1000000},
        "rebalance": {"max_position_weight": 0.20},
        "holdings": [
            {"ticker": "600519", "name": "贵州茅台", "status": "watch",
             "target_weight": 0.10},
        ],
        "exited": [],
    }, allow_unicode=True), encoding="utf-8")

    # ─── save_portfolio 备份机制 ───
    print("─── save_portfolio: 备份 ───")
    doc = load_yaml_dict(test_yaml)
    doc["_meta"]["last_updated"] = "test"
    bak = save_portfolio(doc, path=test_yaml)
    expect(bak is not None and bak.exists(), f"产生备份 {bak.name if bak else ''}")
    expect(test_yaml.exists(), "原文件仍存在")

    # ─── upsert: 已有 ticker 更新 ───
    print("─── upsert: 已有 ticker 更新 shares + 翻转 demo→live ───")
    bak, stats = upsert_holdings([
        {"ticker": "600519", "name": "贵州茅台", "status": "active",
         "shares": 100, "cost_basis": 1500, "target_weight": 0.10},
    ], path=test_yaml)
    expect(stats["updated"] == 1, "updated=1")
    expect(stats["added"] == 0, "added=0")
    expect(stats["status_flipped"], "demo → live")

    after = load_yaml_dict(test_yaml)
    h = after["holdings"][0]
    expect(h["shares"] == 100 and h["cost_basis"] == 1500, "shares/cost 已更新")
    expect(h["status"] == "active", "status=active")
    expect(after["_meta"]["status"] == "live", "_meta.status=live")
    expect("last_updated" in after["_meta"], "last_updated 已写")

    # ─── upsert: 新 ticker 追加 ───
    print("─── upsert: 新 ticker 追加 ───")
    bak, stats = upsert_holdings([
        {"ticker": "000333", "name": "美的集团", "status": "active",
         "shares": 200, "cost_basis": 65.0},
    ], path=test_yaml)
    expect(stats["added"] == 1, "added=1")
    after = load_yaml_dict(test_yaml)
    expect(len(after["holdings"]) == 2, "holdings 增至 2")
    tickers = {h["ticker"] for h in after["holdings"]}
    expect("000333" in tickers, "000333 已加入")

    # ─── 多次 upsert 不重复 ───
    print("─── upsert 幂等(同 ticker 反复 upsert)───")
    upsert_holdings([
        {"ticker": "000333", "name": "美的集团", "status": "active",
         "shares": 250, "cost_basis": 70.0},
    ], path=test_yaml)
    after = load_yaml_dict(test_yaml)
    expect(len(after["holdings"]) == 2, "holdings 仍为 2")
    h333 = next(h for h in after["holdings"] if h["ticker"] == "000333")
    expect(h333["shares"] == 250, "shares 已更新到 250")

print()
if errs:
    print(f"❌ 失败 {len(errs)} 项")
    for e in errs:
        print(f"  - {e}")
    sys.exit(1)
print("✅ loader 测试全通过")
