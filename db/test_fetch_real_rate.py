"""离线单测 · fetch_real_rate FRED 兜底逻辑。

不联网,不写 DB。聚焦:
- FRED CSV 解析格式(列名兼容 / 旧 DATE 与新 observation_date)
- 月环比派生公式正确性
- 异常 CSV 防御
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "db"))
from fetch_real_rate import _parse_fred_cpi_csv, fetch_us_cpi_mom_fred  # noqa: E402


SAMPLE_NEW = """observation_date,CPIAUCSL
2025-08-01,322.000
2025-09-01,322.644
2025-10-01,323.450
2025-11-01,324.100
2025-12-01,324.910
2026-01-01,325.700
2026-02-01,326.500
2026-03-01,327.100
2026-04-01,327.800
"""

SAMPLE_OLD = """DATE,CPIAUCSL
2025-08-01,322.000
2025-09-01,322.644
"""


class TestParseFredCpiCsv(unittest.TestCase):
    def test_new_header_observation_date(self) -> None:
        df = _parse_fred_cpi_csv(SAMPLE_NEW)
        self.assertEqual(list(df.columns), ["date", "level"])
        self.assertEqual(len(df), 9)
        self.assertEqual(str(df.iloc[0]["date"]), "2025-08-01")
        self.assertAlmostEqual(df.iloc[0]["level"], 322.000, places=3)
        self.assertAlmostEqual(df.iloc[-1]["level"], 327.800, places=3)

    def test_legacy_header_DATE(self) -> None:
        df = _parse_fred_cpi_csv(SAMPLE_OLD)
        self.assertEqual(list(df.columns), ["date", "level"])
        self.assertEqual(len(df), 2)
        self.assertEqual(str(df.iloc[-1]["date"]), "2025-09-01")

    def test_unexpected_header_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            _parse_fred_cpi_csv("foo,bar\n1,2\n")

    def test_sorted_ascending(self) -> None:
        # 故意乱序,验证排序输出
        unsorted = (
            "observation_date,CPIAUCSL\n"
            "2026-01-01,325.7\n"
            "2025-12-01,324.9\n"
            "2025-08-01,322.0\n"
        )
        df = _parse_fred_cpi_csv(unsorted)
        self.assertEqual(
            [str(d) for d in df["date"].tolist()],
            ["2025-08-01", "2025-12-01", "2026-01-01"],
        )

    def test_drops_na_rows(self) -> None:
        with_na = (
            "observation_date,CPIAUCSL\n"
            "2025-08-01,322.0\n"
            "2025-09-01,.\n"      # FRED 用 '.' 表示缺失
            "2025-10-01,323.5\n"
        )
        df = _parse_fred_cpi_csv(with_na)
        self.assertEqual(len(df), 2)


class TestMomDerivationCorrectness(unittest.TestCase):
    """手算 3 个已知样本 → 验证 fetch_us_cpi_mom_fred 派生公式。

    用 monkeypatch _retry 让它返回 SAMPLE_NEW,不触发网络。
    """

    def test_mom_pct_against_hand_compute(self) -> None:
        import fetch_real_rate as mod
        # monkeypatch:_retry 直接返回 SAMPLE_NEW 字符串
        original_retry = mod._retry
        mod._retry = lambda fn, **kw: SAMPLE_NEW
        try:
            df = fetch_us_cpi_mom_fred()
        finally:
            mod._retry = original_retry

        # 9 行 level → 8 行 MoM(第 1 行 shift(1) 为 NaN 被 dropna)
        self.assertEqual(len(df), 8)

        # 手算样本 1:Sep = 322.644 / 322.000 - 1 = 0.001999... ≈ 0.2000%
        sep = df[df["date"].astype(str) == "2025-09-01"].iloc[0]
        self.assertAlmostEqual(sep["value"], (322.644 / 322.000 - 1) * 100, places=6)
        self.assertAlmostEqual(sep["value"], 0.199999, places=4)

        # 手算样本 2:Oct = 323.450 / 322.644 - 1 ≈ 0.2498%
        oct_ = df[df["date"].astype(str) == "2025-10-01"].iloc[0]
        self.assertAlmostEqual(oct_["value"], (323.450 / 322.644 - 1) * 100, places=6)

        # 手算样本 3:Apr-2026 = 327.800 / 327.100 - 1 ≈ 0.2140%
        apr = df[df["date"].astype(str) == "2026-04-01"].iloc[0]
        self.assertAlmostEqual(apr["value"], (327.800 / 327.100 - 1) * 100, places=6)

    def test_output_schema_fields(self) -> None:
        import fetch_real_rate as mod
        original_retry = mod._retry
        mod._retry = lambda fn, **kw: SAMPLE_NEW
        try:
            df = fetch_us_cpi_mom_fred()
        finally:
            mod._retry = original_retry

        self.assertEqual(set(df.columns), {"date", "value", "indicator", "unit", "frequency", "source"})
        self.assertTrue((df["indicator"] == "US_CPI_MOM").all())
        self.assertTrue((df["unit"] == "%").all())
        self.assertTrue((df["frequency"] == "M").all())
        self.assertTrue((df["source"] == "FRED:CPIAUCSL").all())

    def test_too_few_rows_raises(self) -> None:
        import fetch_real_rate as mod
        original_retry = mod._retry
        mod._retry = lambda fn, **kw: "observation_date,CPIAUCSL\n2025-08-01,322.0\n"
        try:
            with self.assertRaises(RuntimeError):
                fetch_us_cpi_mom_fred()
        finally:
            mod._retry = original_retry


class TestFallbackChain(unittest.TestCase):
    """fetch_us_cpi_mom() akshare 失败 → 自动切 FRED。"""

    def test_akshare_failure_falls_back_to_fred(self) -> None:
        import fetch_real_rate as mod

        # 让 akshare import + 调用全失败
        sentinel = pd.DataFrame({
            "date": [pd.Timestamp("2025-09-01").date()],
            "value": [0.2],
            "indicator": ["US_CPI_MOM"],
            "unit": ["%"],
            "frequency": ["M"],
            "source": ["FRED:CPIAUCSL"],
        })

        original_fred = mod.fetch_us_cpi_mom_fred
        mod.fetch_us_cpi_mom_fred = lambda: sentinel

        # 模拟 akshare 抛错:用 monkeypatch _retry 抛
        original_retry = mod._retry
        def _boom(fn, **kw):
            raise RuntimeError("simulated SSL EOF")
        mod._retry = _boom

        try:
            out = mod.fetch_us_cpi_mom()
        finally:
            mod._retry = original_retry
            mod.fetch_us_cpi_mom_fred = original_fred

        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["source"], "FRED:CPIAUCSL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
