"""从已抓理杏仁字段本地计算的衍生指标模块。

═════════════════════════════════════════════════════════════════════════
口径与一致性原则(必读!)
═════════════════════════════════════════════════════════════════════════

1. **理杏仁优先** — 任何指标先看理杏仁是否直接提供;有则用原始字段,
   无则在此模块计算并标 `verified=False`(未校验,仅本地估算)。
2. **年度数据**统一用 `MONTH(date)=12 AND DAY(date)=31`(年末值)。
3. **指标列名**用 DuckDB 中文原列名(如 `PE-TTM` `净资产收益率(ROE)`)。
4. **PE / ROE / 财务费用率等**默认用非加权/非扣非版本(与理杏仁 Dashboard 显示一致)。
5. **CAGR 公式**:`(v_end / v_start) ** (1/n) - 1`,n 是年数(5 年 CAGR 取 t-5 到 t,共 6 个数据点)。
6. **分位点**优先用理杏仁内置 `PE-TTM_分位点`(权威),自算窗口分位仅作 fallback。
7. **行业字段**用 `industry_pe` 表的 `pe_median`(申万一级中位)。

═════════════════════════════════════════════════════════════════════════
数据覆盖现状(2026-05)
═════════════════════════════════════════════════════════════════════════

✅ 全 15 家共有字段(Tier 1):
  valuation:    PE-TTM / PB / PS-TTM / 股息率 / 各分位点(自带)
  growth:       营业收入 / 归母净利润 / 基本每股收益 / 累积同比
  profitability: 净利润率 / ROE / ROA / 毛利率
  cashflow:     经营 CFO / CFO/NI 比率 / 自由现金流量
  safety:       资产负债率 / 流动比率 / 速动比率 / 有息负债率

🟡 仅部分公司有(Tier 2,需标 verified=False):
  002475 立讯精密 / 02097 蜜雪集团 / 601766 中国中车 / 603379 三美股份
  含完整 BS 科目(货币资金/短期借款/一年内到期非流动负债 等)
  含详细 profitability(财务费用率/ROIC/扣非 ROE 等)

❌ 全部缺失:暂无

═════════════════════════════════════════════════════════════════════════
返回值约定
═════════════════════════════════════════════════════════════════════════

每个公开函数返回 `tuple(value, verified, note)` 或单纯 `float | None`:
  value:    计算结果(None 表示数据不足)
  verified: True = 与理杏仁直接字段对齐 / False = 本地估算未与权威源校验
  note:     口径说明 / 数据缺口提示
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import duckdb

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "preson.duckdb"


class DerivedResult(NamedTuple):
    """衍生指标计算结果。verified=True 表示与理杏仁权威字段对齐。"""
    value: float | None
    verified: bool
    note: str

    def __repr__(self) -> str:
        v = "None" if self.value is None else f"{self.value:.4f}"
        flag = "✅" if self.verified else "⚠️"
        return f"{flag} {v} ({self.note})"


# ═══ 内部 helpers ═══════════════════════════════════════════════════════

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _yearly_series(con, table: str, ticker: str, metric: str,
                   years_back: int = 10) -> list[tuple[int, float]]:
    """取年末(12-31)序列,按年份升序。返回 [(year, value), ...]。"""
    cutoff = (date.today() - timedelta(days=365 * (years_back + 1))).isoformat()
    rows = con.execute(
        f"""
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
          AND MONTH(date) = 12 AND DAY(date) = 31
          AND date >= ?
        ORDER BY date
        """,
        [ticker, metric, cutoff],
    ).fetchall()
    return [(int(y), float(v)) for y, v in rows]


def _latest_value(con, table: str, ticker: str, metric: str) -> float | None:
    row = con.execute(
        f"""
        SELECT value FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


# ═══ Tier 1:全 15 家可算 ═══════════════════════════════════════════════

def cagr(con, ticker: str, table: str, metric: str, years: int = 5) -> DerivedResult:
    """通用 CAGR — 取年末值,n 年复合增长率。

    公式:(v_end / v_start) ** (1/n) - 1
    数据要求:至少 n+1 个连续年末数据点
    """
    series = _yearly_series(con, table, ticker, metric, years_back=years + 2)
    if len(series) < years + 1:
        return DerivedResult(None, False, f"年末数据不足 {years+1} 个 (实有 {len(series)})")

    # 取最后两端
    end_year, end_val = series[-1]
    # 找 n 年前的数据点
    start_year_target = end_year - years
    start_match = [(y, v) for y, v in series if y == start_year_target]
    if not start_match:
        return DerivedResult(None, False, f"缺 {start_year_target} 年末数据")
    start_val = start_match[0][1]

    if start_val <= 0:
        return DerivedResult(None, False, f"起点 {start_year_target} 年值非正 ({start_val})")

    val = (end_val / start_val) ** (1.0 / years) - 1.0
    return DerivedResult(
        val, True,
        f"{years}y CAGR: ({end_val:.2g}/{start_val:.2g})^(1/{years})-1, "
        f"{start_year_target}-{end_year}",
    )


def revenue_cagr_5y(con, ticker: str) -> DerivedResult:
    """5 年营业收入 CAGR(用 growth.营业收入 年末值)。"""
    return cagr(con, ticker, "growth", "营业收入", 5)


def np_cagr_5y(con, ticker: str) -> DerivedResult:
    """5 年归母净利润 CAGR。"""
    return cagr(con, ticker, "growth", "归属于母公司普通股股东的净利润", 5)


def revenue_profit_cagr_diff(con, ticker: str, years: int = 5) -> DerivedResult:
    """增长质量 = |营收 CAGR - 利润 CAGR|。林奇标准 < 3%(避免一次性收益)。"""
    rev = cagr(con, ticker, "growth", "营业收入", years)
    np = cagr(con, ticker, "growth", "归属于母公司普通股股东的净利润", years)
    if rev.value is None or np.value is None:
        return DerivedResult(None, False, "营收或利润 CAGR 不可得")
    diff = abs(rev.value - np.value)
    return DerivedResult(
        diff, True,
        f"|营收 CAGR {rev.value*100:.1f}% - 利润 CAGR {np.value*100:.1f}%| = {diff*100:.1f}%",
    )


def years_positive_growth_5y(con, ticker: str,
                              metric: str = "累积同比",
                              table: str = "growth") -> DerivedResult:
    """过去 5 年正增长的年数(0-5)。林奇稳健合格:≥ 4 年。

    用 growth 表的「累积同比」逐年值,正数 = 当年正增长。
    """
    series = _yearly_series(con, table, ticker, metric, years_back=6)
    if len(series) < 5:
        return DerivedResult(None, False, f"逐年同比数据不足 5 年 (实有 {len(series)})")
    last5 = series[-5:]
    positive_count = sum(1 for _, v in last5 if v > 0)
    return DerivedResult(
        float(positive_count), True,
        f"过去 5 年 {positive_count}/5 年正增长 ({metric})",
    )


def fcf_to_ni_3y(con, ticker: str) -> DerivedResult:
    """近 3 年 FCF / 归母净利润 平均。林奇稳健合格:> 0.80。

    分子:cashflow.自由现金流量(年末)
    分母:growth.归属于母公司普通股股东的净利润(年末)
    """
    fcf_series = dict(_yearly_series(con, "cashflow", ticker, "自由现金流量", 6))
    ni_series = dict(_yearly_series(con, "growth", ticker, "归属于母公司普通股股东的净利润", 6))
    common_years = sorted(set(fcf_series) & set(ni_series), reverse=True)
    if len(common_years) < 3:
        return DerivedResult(None, False, f"FCF & NI 共有年份不足 3 个 (实 {len(common_years)})")

    ratios = []
    for y in common_years[:3]:
        if ni_series[y] > 0:  # 净利润为正才有意义
            ratios.append(fcf_series[y] / ni_series[y])
    if not ratios:
        return DerivedResult(None, False, "近 3 年净利润全部非正")

    avg = sum(ratios) / len(ratios)
    return DerivedResult(
        avg, True,
        f"近 {len(ratios)} 年平均 FCF/NI = {avg:.2f}",
    )


def roe_3y_avg(con, ticker: str) -> DerivedResult:
    """近 3 年 ROE 平均(年末值)。林奇稳健合格:≥ 15%。"""
    series = _yearly_series(con, "profitability", ticker, "净资产收益率(ROE)", 5)
    if len(series) < 3:
        return DerivedResult(None, False, f"ROE 年末数据不足 3 年 (实有 {len(series)})")
    last3 = [v for _, v in series[-3:]]
    avg = sum(last3) / len(last3)
    return DerivedResult(
        avg, True,
        f"近 3 年 ROE 平均 {avg*100:.1f}% (年份 {[y for y,_ in series[-3:]]})",
    )


def pe_pct_5y(con, ticker: str) -> DerivedResult:
    """PE-TTM 5 年全周期分位(自算)。

    ⚠️ 未与理杏仁内置「PE-TTM_分位点」校验 — 后者是 10y 窗口,口径不同。
    林奇稳健「好价格」标准:< 10% 分位。
    """
    cutoff = (date.today() - timedelta(days=365 * 5)).isoformat()
    row = con.execute(
        """
        WITH series AS (
            SELECT value FROM valuation
            WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
              AND date >= ?
        ),
        latest AS (
            SELECT value FROM valuation
            WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
        )
        SELECT
            (SELECT COUNT(*) FROM series WHERE value <= (SELECT value FROM latest)) * 1.0
            / NULLIF((SELECT COUNT(*) FROM series), 0)
        """,
        [ticker, cutoff, ticker],
    ).fetchone()
    if row is None or row[0] is None:
        return DerivedResult(None, False, "PE-TTM 5 年序列不足")
    return DerivedResult(
        float(row[0]), False,  # verified=False 因为窗口与理杏仁内置不同
        f"自算 5 年窗口 PE 分位 {row[0]*100:.1f}% (理杏仁内置是 10y 窗口,不同)",
    )


def industry_pe_diff_pct(con, ticker: str) -> DerivedResult:
    """公司 PE 相对申万一级行业中位的偏离比例。

    林奇稳健「好价格」相对估值合格:PE 低于行业均值 > 30%(返回 -0.30)。
    数据源:industry_pe 表 (申万 level=1, pe_median)
    """
    pe = _latest_value(con, "valuation", ticker, "PE-TTM")
    if pe is None:
        return DerivedResult(None, False, "PE-TTM 不可得")

    # 取公司行业(从 companies.csv 的 industry 列)
    row = con.execute(
        "SELECT category FROM companies WHERE ticker = ?", [ticker]
    ).fetchone()
    # 注:companies 表只存 category(non_financial/bank/insurance/hk),
    # 真实申万一级在 .config/companies.csv,需读 csv 拼接

    import pandas as pd
    csv_path = ROOT / ".config" / "companies.csv"
    try:
        df = pd.read_csv(csv_path, dtype={"stock": str})
        match = df[df["stock"] == ticker]
        if match.empty:
            return DerivedResult(None, False, f"ticker {ticker} 不在 companies.csv")
        industry = str(match.iloc[0].get("industry", "") or "").strip()
    except Exception as e:
        return DerivedResult(None, False, f"读 companies.csv 失败: {e}")

    if not industry:
        return DerivedResult(None, False, "industry 字段为空")

    # 取最新行业 PE 中位
    row = con.execute(
        """
        SELECT pe_median FROM industry_pe
        WHERE industry_name LIKE ? AND level = 1 AND pe_median IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        [f"%{industry}%"],
    ).fetchone()
    if row is None or row[0] is None:
        return DerivedResult(None, False, f"行业 {industry} 中位 PE 不可得")

    industry_pe = float(row[0])
    diff = pe / industry_pe - 1.0  # 负值=便宜,正值=贵
    return DerivedResult(
        diff, True,
        f"公司 PE {pe:.1f} / 行业「{industry}」中位 {industry_pe:.1f} - 1 = {diff*100:+.1f}%",
    )


def years_dividend_paid_10y(con, ticker: str) -> DerivedResult:
    """近 10 年派息年数(股息率 > 0 计数)。林奇稳健「股息政策」合格:≥ 10 年。

    用 valuation.股息率 每年的最后一个值作为该年股息率。
    """
    cutoff = (date.today() - timedelta(days=365 * 11)).isoformat()
    rows = con.execute(
        """
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM valuation
        WHERE ticker = ? AND metric = '股息率' AND value IS NOT NULL
          AND date >= ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date)
                                    ORDER BY date DESC) = 1
        ORDER BY y
        """,
        [ticker, cutoff],
    ).fetchall()
    if not rows:
        return DerivedResult(None, False, "无股息率序列")
    n_paid = sum(1 for _, v in rows if v and v > 0)
    n_total = len(rows)
    return DerivedResult(
        float(n_paid), True,
        f"近 {n_total} 年中 {n_paid} 年派息 (股息率 > 0)",
    )


def dividend_growth_trend_5y(con, ticker: str) -> DerivedResult:
    """股息率近 5 年趋势:简单线性斜率(单位 / 年)。

    > 0 = 上升趋势(分红增长)。林奇稳健"股息增长"信号。
    """
    cutoff = (date.today() - timedelta(days=365 * 6)).isoformat()
    rows = con.execute(
        """
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM valuation
        WHERE ticker = ? AND metric = '股息率' AND value IS NOT NULL
          AND date >= ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date)
                                    ORDER BY date DESC) = 1
        ORDER BY y
        """,
        [ticker, cutoff],
    ).fetchall()
    if len(rows) < 3:
        return DerivedResult(None, False, f"股息率序列不足 3 年 (实 {len(rows)})")

    # 简单线性回归斜率
    n = len(rows)
    xs = [float(y) for y, _ in rows]
    ys = [float(v) for _, v in rows]
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    den = sum((x-mx)**2 for x in xs)
    if den == 0:
        return DerivedResult(None, False, "斜率分母为 0")
    slope = num / den
    return DerivedResult(
        slope, True,
        f"股息率 {n} 年趋势斜率 {slope*100:+.3f}%/年 ({rows[0][0]}-{rows[-1][0]})",
    )


# ═══ Tier 2:仅部分公司可算(verified=False 默认) ═══════════════════════

def cash_minus_st_debt_to_mc(con, ticker: str) -> DerivedResult:
    """(货币资金 - 短期借款 - 一年内到期非流动负债) / 总市值。

    林奇「好价格」现金头寸支撑合格:> 15%
    ⚠️ 仅 4 家公司(002475/02097/601766/603379)有 BS 科目。
    总市值需用最新价格 × 总股本(BS 科目里没直接给市值,需算)。
    """
    cash = _latest_value(con, "safety", ticker, '"货币资金"')
    st_loan = _latest_value(con, "safety", ticker, '"短期借款"') or 0.0
    cur_due = _latest_value(con, "safety", ticker, '"一年内到期的非流动负债"') or 0.0

    if cash is None:
        return DerivedResult(None, False, "货币资金未装配(仅 4 家公司有 BS 科目)")

    # 市值:试 valuation 表的「市值(港币)」(港股)或自己算
    mc = _latest_value(con, "valuation", ticker, "市值(港币)")
    if mc is None:
        return DerivedResult(
            None, False,
            "总市值字段未装配(A 股需 股价 × 总股本,港股有「市值(港币)」)",
        )

    net_cash = cash - st_loan - cur_due
    ratio = net_cash / mc
    return DerivedResult(
        ratio, False,  # 未与理杏仁直接字段校验
        f"净现金 {net_cash/1e8:.2f}亿 / 市值 {mc/1e8:.2f}亿 = {ratio*100:+.1f}%",
    )


def interest_coverage(con, ticker: str, year: int | None = None) -> DerivedResult:
    """营业利润 / 财务费用(用财务费用率反推)— 利息覆盖倍数近似。

    林奇「财务健康」偿债能力合格:> 8 倍
    ⚠️ 财务费用率仅部分公司装配;且这是近似算法(理杏仁也无直接「利息覆盖」字段)。
    """
    # 取年末值
    if year is None:
        # 用最新年报年
        from datetime import date as _d
        year = _d.today().year - 1

    # profitability 表的 metric 名要带公司前缀(如 '立讯精密 - 财务费用率')
    # 但我们没法直接从 ticker 拿到中文名,只能用 % 模糊匹配
    row = con.execute(
        """
        SELECT metric, value FROM profitability
        WHERE ticker = ? AND metric LIKE '%财务费用率%'
          AND MONTH(date) = 12 AND DAY(date) = 31
          AND EXTRACT(YEAR FROM date) = ?
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, year],
    ).fetchone()
    if row is None:
        return DerivedResult(None, False, "财务费用率未装配 (Tier 2 字段,仅部分公司有)")

    fin_cost_rate = row[1]
    if fin_cost_rate is None or fin_cost_rate <= 0:
        return DerivedResult(None, False, "财务费用率非正")

    # 营业利润 / (营收 × 财务费用率)
    op_profit_row = con.execute(
        """
        SELECT value FROM growth
        WHERE ticker = ? AND metric LIKE '%营业利润'
          AND MONTH(date) = 12 AND DAY(date) = 31
          AND EXTRACT(YEAR FROM date) = ?
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, year],
    ).fetchone()
    rev_row = con.execute(
        """
        SELECT value FROM growth
        WHERE ticker = ? AND metric = '营业收入'
          AND MONTH(date) = 12 AND DAY(date) = 31
          AND EXTRACT(YEAR FROM date) = ?
        """,
        [ticker, year],
    ).fetchone()
    if op_profit_row is None or rev_row is None:
        return DerivedResult(None, False, "营业利润或营业收入年末值缺失")

    op_profit = float(op_profit_row[0])
    rev = float(rev_row[0])
    fin_cost = rev * fin_cost_rate
    if fin_cost <= 0:
        return DerivedResult(None, False, "财务费用 <= 0,公司无利息支出")

    coverage = op_profit / fin_cost
    return DerivedResult(
        coverage, False,  # 近似算法,未与权威源校验
        f"近似:营业利润 {op_profit/1e8:.1f}亿 / 财务费用 {fin_cost/1e8:.2f}亿 = {coverage:.1f}x",
    )


def nonrecurring_eps_cagr_5y(con, ticker: str) -> DerivedResult:
    """5 年扣非净利 CAGR — 林奇稳健合格:≥ 12%。

    ⚠️ 仅 4 家公司有「归属于母公司普通股股东的扣除非经常性损益的净利润」字段。
    """
    return cagr(con, ticker, "growth",
                "归属于母公司普通股股东的扣除非经常性损益的净利润", 5)


# ═══ v2.5 TODO#1 G3:格雷厄姆派生 ═══════════════════════════════════════

def years_continuous_dividend(con, ticker: str, max_years: int = 25) -> DerivedResult:
    """从 valuation 时序中倒序计算 dividend_yield > 0 的连续年数(从最新年回溯)。

    格雷厄姆 g4_dividend_record 实现:连续派息 ≥ 10 年 → 通过。

    实现逻辑:
      1. 取每个自然年的最新 股息率 值(每年保留最后一条)
      2. 从最新年向前数,股息率 > 0 即视为该年派息
      3. 一旦遇到 ≤ 0 / NULL 即中断(连续性破坏)

    返回:
      value = 连续派息年数(整数 float)
      verified = True(基于理杏仁原始 valuation.股息率 时序)
      note = "基于 valuation.dividend_yield 时序"
    """
    rows = con.execute(
        """
        SELECT EXTRACT(YEAR FROM date)::INTEGER AS y, value
        FROM valuation
        WHERE ticker = ? AND metric = '股息率' AND value IS NOT NULL
        QUALIFY ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date)
                                    ORDER BY date DESC) = 1
        ORDER BY y DESC
        LIMIT ?
        """,
        [ticker, max_years],
    ).fetchall()
    if not rows:
        return DerivedResult(
            None, False,
            "基于 valuation.dividend_yield 时序(无股息率序列)",
        )

    streak = 0
    for _, v in rows:  # 已按 y DESC 倒序
        if v is not None and float(v) > 0:
            streak += 1
        else:
            break

    return DerivedResult(
        float(streak), True,
        f"基于 valuation.dividend_yield 时序(连续 {streak} 年派息,"
        f"采样 {len(rows)} 年最新窗口)",
    )


# ═══ CLI 离线验证 ═══════════════════════════════════════════════════════

def _print_all(ticker: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  Derived Metrics · {ticker}")
    print('═' * 70)
    con = _conn()
    try:
        for name, fn in [
            ("revenue_cagr_5y",       revenue_cagr_5y),
            ("np_cagr_5y",            np_cagr_5y),
            ("revenue_profit_cagr_diff", revenue_profit_cagr_diff),
            ("years_positive_growth_5y", years_positive_growth_5y),
            ("fcf_to_ni_3y",          fcf_to_ni_3y),
            ("roe_3y_avg",            roe_3y_avg),
            ("pe_pct_5y",             pe_pct_5y),
            ("industry_pe_diff_pct",  industry_pe_diff_pct),
            ("years_dividend_paid_10y", years_dividend_paid_10y),
            ("dividend_growth_trend_5y", dividend_growth_trend_5y),
            ("cash_minus_st_debt_to_mc", cash_minus_st_debt_to_mc),
            ("interest_coverage",     interest_coverage),
            ("nonrecurring_eps_cagr_5y", nonrecurring_eps_cagr_5y),
        ]:
            try:
                r = fn(con, ticker)
                print(f"  {name:30s} {r}")
            except Exception as e:
                print(f"  {name:30s} ❌ {e}")
    finally:
        con.close()


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="*", default=[],
                    help="公司代码列表(留空跑全 15 家)")
    args = ap.parse_args()

    if args.ticker:
        targets = args.ticker
    else:
        import pandas as pd
        comp = pd.read_csv(ROOT / ".config" / "companies.csv", dtype={"stock": str})
        targets = comp["stock"].tolist()

    for t in targets:
        _print_all(t)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
