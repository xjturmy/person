from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".tools" / "dashboard"))


def test_focus_holdings_are_user_confirmed_scope():
    from tabs.decision.holding_focus import FOCUS_HOLDINGS

    names = [item.name for item in FOCUS_HOLDINGS]
    tickers = [item.ticker for item in FOCUS_HOLDINGS]

    assert names == [
        "中国中车",
        "新华保险",
        "海康威视",
        "蜜雪集团",
        "机器人ETF",
        "券商ETF",
        "有色ETF",
        "黄金股ETF",
        "黄金ETF",
        "化工ETF",
        "红利低波",
        "红利50",
    ]
    assert tickers == [
        "601766",
        "601336",
        "002415",
        "02097",
        "515000",
        "512000",
        "517400",
        "159562",
        "518880",
        "159870",
        "512590",
        "510880",
    ]
