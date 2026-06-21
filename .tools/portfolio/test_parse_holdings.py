"""parse_holdings.py 单测 — 直接 python3 执行(不依赖 pytest)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_holdings import (
    build_candidates,
    classify,
    parse_line,
    parse_text,
)

PASS = "✅"
FAIL = "❌"
errs: list[str] = []


def expect(cond: bool, label: str) -> None:
    print(f"  {PASS if cond else FAIL} {label}")
    if not cond:
        errs.append(label)


print("─── 格式 1:CSV 600519,100,1500 ───")
ph = parse_line("600519,100,1500")
expect(ph and ph.ticker == "600519", "ticker=600519")
expect(ph and ph.shares == 100.0, "shares=100")
expect(ph and ph.cost_basis == 1500.0, "cost=1500")

print("─── 格式 2:Tab 600036\\t500\\t34.5 ───")
ph = parse_line("600036\t500\t34.5")
expect(ph and ph.ticker == "600036", "ticker=600036")
expect(ph and ph.shares == 500.0, "shares=500")
expect(ph and ph.cost_basis == 34.5, "cost=34.5")

print("─── 格式 3:空格 000333 200 65.0 ───")
ph = parse_line("000333 200 65.0")
expect(ph and ph.ticker == "000333", "ticker=000333")
expect(ph and ph.shares == 200.0, "shares=200")
expect(ph and ph.cost_basis == 65.0, "cost=65.0")

print("─── 格式 4:中英 美的集团 000333 200 65.0 ───")
ph = parse_line("美的集团 000333 200 65.0")
expect(ph and ph.ticker == "000333", "ticker=000333")
expect(ph and ph.name == "美的集团", "name=美的集团")
expect(ph and ph.shares == 200.0, "shares=200")
expect(ph and ph.cost_basis == 65.0, "cost=65.0")

print("─── 格式 5:中文混合带单位 000333 美的集团 200股 成本65.00 ───")
ph = parse_line("000333 美的集团 200股 成本65.00")
expect(ph and ph.ticker == "000333", "ticker=000333")
expect(ph and ph.name == "美的集团", "name=美的集团")
expect(ph and ph.shares == 200.0, "shares=200")
expect(ph and ph.cost_basis == 65.0, "cost=65.0")

print("─── 格式 6:券商完整行 600519 贵州茅台 100 1500.00 1612.00 11.20% +11200 ───")
ph = parse_line("600519 贵州茅台 100 1500.00 1612.00 11.20% +11200")
expect(ph and ph.ticker == "600519", "ticker=600519")
expect(ph and ph.shares == 100.0, "shares=100")
expect(ph and ph.cost_basis == 1500.0, "cost=1500")
expect(ph and ph.last_price == 1612.0, "last_price=1612")
# 11.20% 应该被丢;+11200 暂不强求(用户得到的浮盈数会污染 last_price 字段?)
# 我们设计上接受第 3 个数字作 last_price,如果用户再加列就溢出 — 先确保前 3 个对

print("─── 港股 5 位:02097 100 ───")
ph = parse_line("02097 100 5.5")
expect(ph and ph.ticker == "02097", "ticker=02097(港股)")
expect(ph and ph.shares == 100.0, "shares=100")

print("─── 货币符号 ¥ 600519 100 ¥1500 ───")
ph = parse_line("600519 100 ¥1500")
expect(ph and ph.cost_basis == 1500.0, "cost=1500(去除 ¥)")

print("─── 异常 1:无 ticker ───")
ph = parse_line("贵州茅台 100 1500")
expect(ph is not None, "返回非 None")
expect(ph and ph.parse_error and "代码" in ph.parse_error, "parse_error 提示无代码")

print("─── 异常 2:空行/注释 ───")
expect(parse_line("") is None, "空行返回 None")
expect(parse_line("   ") is None, "空白返回 None")
expect(parse_line("# 这是注释") is None, "# 开头返回 None")

print("─── 异常 3:只有 ticker ───")
ph = parse_line("600519")
expect(ph and ph.parse_error and "数值" in ph.parse_error, "parse_error 提示缺数")

print("─── 多行 parse_text ───")
text = """
600519,100,1500
600036,500,34.5

# 注释行
000333  200  65.0
"""
result = parse_text(text)
expect(len(result) == 3, f"3 行有效(实际 {len(result)})")
expect(all(r.ok for r in result), "全部 ok")

print("─── 状态识别 classify ───")
universe = {"600519", "600036", "000333"}
held = {"600519"}
ph_existing = parse_line("600519,100,1500")
ph_new = parse_line("600036,500,34.5")
ph_unknown = parse_line("000001,100,10")
ph_failed = parse_line("贵州茅台 100 1500")
ph_incomplete = parse_line("600519 100")  # 缺 cost

s_e = classify(ph_existing, universe, held)
s_n = classify(ph_new, universe, held)
s_u = classify(ph_unknown, universe, held)
s_f = classify(ph_failed, universe, held)
s_i = classify(ph_incomplete, universe, held)

expect(s_e.code == "ok_existing" and s_e.default_check, "已持仓默认勾选")
expect(s_n.code == "ok_new" and s_n.default_check, "新增默认勾选")
expect(s_u.code == "not_in_universe" and not s_u.default_check, "不在 15 家不勾")
expect(s_f.code == "parse_failed" and not s_f.default_check, "失败不勾")
expect(s_i.code == "incomplete" and not s_i.default_check, "字段不全不勾")

print("─── build_candidates 集成 ───")
parsed = parse_text("600519,100,1500\n000333,200,65.0\n000001,100,10")
rows = build_candidates(
    parsed,
    universe_tickers={"600519", "000333"},
    held_tickers={"600519"},
    name_map={"600519": "贵州茅台", "000333": "美的集团"},
)
expect(len(rows) == 3, "3 行")
expect(rows[0].parsed.name == "贵州茅台", "name 自动填充")
expect(rows[2].status.code == "not_in_universe", "000001 不在 universe")

# ─── 总结 ────
print()
if errs:
    print(f"{FAIL} 失败 {len(errs)} 项:")
    for e in errs:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"{PASS} 全部用例通过")
