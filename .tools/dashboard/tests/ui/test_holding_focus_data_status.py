from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".tools" / "dashboard"))


def test_holding_focus_status_pipelines_are_classified():
    import holding_focus_data_status as status

    rows = {row.ticker: row for row in status.collect_status()}

    assert rows["601766"].pipeline == "lixinger_company"
    assert rows["02097"].pipeline == "lixinger_company"
    assert rows["515000"].pipeline == "etf"
    assert rows["512590"].pipeline == "etf"
    assert rows["510880"].pipeline == "etf"
    assert rows["518880"].pipeline == "gold_etf"
    assert rows["159562"].pipeline == "gold_stock_etf"
    assert rows["517400"].pipeline == "gold_stock_etf"
