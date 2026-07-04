"""保险公司价值修复法价格区间。

第一版使用已落地数据的 PB 历史估值带:
- 当前价 = 市值 / 总股本(总股本由净利润 / EPS 反推)
- BPS = 当前价 / PB
- 买入线 / 合理中枢 / 卖出线 = BPS × 自身 PB 10y P20 / Median / P80

EV/NBV、偿付能力等保险专属字段当前未稳定入库,先在 notes 中提示。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "preson.duckdb"


@dataclass
class InsuranceValueRange:
    ticker: str
    name: str
    verified: bool
    current_price: float | None
    buy_price: float | None
    fair_price: float | None
    sell_price: float | None
    pb: float | None
    pb_p20: float | None
    pb_median: float | None
    pb_p80: float | None
    bps: float | None
    roe: float | None
    dividend_yield: float | None
    embedded_value: float | None
    new_business_value: float | None
    p_ev: float | None
    as_of: date | None
    verdict_label: str
    note: str
    details: list[str] = field(default_factory=list)


@dataclass
class InsurancePeerRow:
    ticker: str
    name: str
    current_price: float | None
    buy_price: float | None
    fair_price: float | None
    sell_price: float | None
    pb: float | None
    pb_median: float | None
    pb_discount_pct: float | None
    roe: float | None
    dividend_yield: float | None
    embedded_value: float | None
    new_business_value: float | None
    p_ev: float | None
    roe_to_pb: float | None
    verdict_label: str
    score: float | None
    note: str


def _conn(db_path: Path | str = DB_PATH):
    return duckdb.connect(str(db_path), read_only=True)


def _latest(con, table: str, ticker: str, metric: str) -> tuple[float | None, date | None]:
    row = con.execute(
        f"""
        SELECT value, date FROM {table}
        WHERE ticker = ? AND metric = ? AND value IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        [ticker, metric],
    ).fetchone()
    if not row:
        return None, None
    return float(row[0]), row[1]


def _pb_band(con, ticker: str) -> tuple[float | None, float | None, float | None, int]:
    row = con.execute(
        """
        SELECT
          quantile_cont(value, 0.20),
          median(value),
          quantile_cont(value, 0.80),
          count(*)
        FROM valuation
        WHERE ticker = ? AND metric = 'PB' AND value > 0
          AND date >= (CURRENT_DATE - INTERVAL 10 YEAR)
        """,
        [ticker],
    ).fetchone()
    if not row:
        return None, None, None, 0
    return (
        float(row[0]) if row[0] is not None else None,
        float(row[1]) if row[1] is not None else None,
        float(row[2]) if row[2] is not None else None,
        int(row[3] or 0),
    )


def _company_folder(ticker: str) -> str | None:
    companies_csv = ROOT / ".config" / "companies.csv"
    if not companies_csv.exists():
        return None
    df = pd.read_csv(companies_csv, dtype={"stock": str})
    for _, row in df.iterrows():
        stock = str(row.get("stock") or "").strip()
        stock = stock.zfill(6) if stock.isdigit() else stock
        if stock == ticker:
            return str(row.get("folder") or "").strip() or None
    return None


def _latest_insurance_csv(ticker: str, metric: str) -> tuple[float | None, date | None]:
    folder = _company_folder(ticker)
    if not folder:
        return None, None
    path = ROOT / "02_companies" / folder / "01_基本面数据" / "历史数据" / "保险.csv"
    if not path.exists():
        return None, None
    df = pd.read_csv(path)
    if "date" not in df.columns or metric not in df.columns:
        return None, None
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    df = df.dropna(subset=["date", metric]).sort_values("date", ascending=False)
    if df.empty:
        return None, None
    row = df.iloc[0]
    return float(row[metric]), row["date"]


def _latest_insurance_metric(con, ticker: str, metric: str) -> tuple[float | None, date | None]:
    try:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'insurance_metrics'"
        ).fetchone()[0]
        if exists:
            row = con.execute(
                """
                SELECT value, date FROM insurance_metrics
                WHERE ticker = ? AND metric = ? AND value IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """,
                [ticker, metric],
            ).fetchone()
            if row:
                return float(row[0]), row[1]
    except Exception:
        pass
    return _latest_insurance_csv(ticker, metric)


def _label(current: float | None, buy: float | None, fair: float | None,
           sell: float | None) -> str:
    if current is None or buy is None or fair is None or sell is None:
        return "⚪ 数据不足"
    if current <= buy:
        return "🟢 买入/加仓区"
    if current <= fair:
        return "🟢 偏低可分批"
    if current <= sell:
        return "🟡 合理持有区"
    return "🔴 偏高减仓观察"


def compute_insurance_value_range(
    ticker: str,
    name: str = "",
    db_path: Path | str = DB_PATH,
) -> InsuranceValueRange:
    ticker = (ticker or "").strip().zfill(6) if (ticker or "").strip().isdigit() else ticker
    con = _conn(db_path)
    try:
        pb, pb_date = _latest(con, "valuation", ticker, "PB")
        market_cap, mcap_date = _latest(con, "valuation", ticker, "市值(元)")
        eps, eps_date = _latest(con, "growth", ticker, "基本每股收益")
        net_income, ni_date = _latest(con, "growth", ticker, "归属于母公司普通股股东的净利润")
        roe, roe_date = _latest(con, "profitability", ticker, "净资产收益率(ROE)")
        dy, dy_date = _latest(con, "valuation", ticker, "股息率")
        ev, ev_date = _latest_insurance_metric(con, ticker, "内含价值(EV)")
        nbv, nbv_date = _latest_insurance_metric(con, ticker, "新业务价值(NBV)")
        pb_p20, pb_median, pb_p80, pb_count = _pb_band(con, ticker)
    finally:
        con.close()

    p_ev = market_cap / ev if market_cap is not None and ev and ev > 0 else None
    as_of = pb_date or mcap_date or eps_date or ni_date or roe_date or dy_date or ev_date or nbv_date
    missing = []
    for label, value in (
        ("PB", pb),
        ("市值", market_cap),
        ("EPS", eps),
        ("净利润", net_income),
        ("PB 历史带", pb_median),
    ):
        if value is None:
            missing.append(label)

    if missing or not pb or pb <= 0 or not eps or eps <= 0 or not net_income or net_income <= 0:
        return InsuranceValueRange(
            ticker=ticker, name=name, verified=False,
            current_price=None, buy_price=None, fair_price=None, sell_price=None,
            pb=pb, pb_p20=pb_p20, pb_median=pb_median, pb_p80=pb_p80,
            bps=None, roe=roe, dividend_yield=dy,
            embedded_value=ev, new_business_value=nbv, p_ev=p_ev, as_of=as_of,
            verdict_label="⚪ 数据不足",
            note="缺少 " + "、".join(missing or ["有效 PB/EPS/净利润"]),
        )

    shares = net_income / eps
    current = market_cap / shares if shares > 0 else None
    bps = current / pb if current is not None and pb > 0 else None
    if bps is None or pb_p20 is None or pb_median is None or pb_p80 is None:
        return InsuranceValueRange(
            ticker=ticker, name=name, verified=False,
            current_price=current, buy_price=None, fair_price=None, sell_price=None,
            pb=pb, pb_p20=pb_p20, pb_median=pb_median, pb_p80=pb_p80,
            bps=bps, roe=roe, dividend_yield=dy,
            embedded_value=ev, new_business_value=nbv, p_ev=p_ev, as_of=as_of,
            verdict_label="⚪ 数据不足",
            note=f"PB 历史样本不足({pb_count} 个)",
        )

    buy = bps * pb_p20
    fair = bps * pb_median
    sell = bps * pb_p80
    return InsuranceValueRange(
        ticker=ticker, name=name, verified=True,
        current_price=current, buy_price=buy, fair_price=fair, sell_price=sell,
        pb=pb, pb_p20=pb_p20, pb_median=pb_median, pb_p80=pb_p80,
        bps=bps, roe=roe, dividend_yield=dy,
        embedded_value=ev, new_business_value=nbv, p_ev=p_ev, as_of=as_of,
        verdict_label=_label(current, buy, fair, sell),
        note="保险价值修复法:用自身 PB 10y 估值带衡量低估/修复空间",
        details=[
            f"PB 历史样本 {pb_count} 个",
            "EV/NBV、偿付能力、新业务价值待补数据后纳入第二层校验",
        ],
    )


_PREFERRED_INSURANCE_PEERS = ["601318", "601601", "601628", "601319"]


def _insurance_company_names(con) -> dict[str, str]:
    rows = con.execute(
        "SELECT ticker, name FROM companies WHERE lower(category) = 'insurance' OR name LIKE '%保险%'"
    ).fetchall()
    return {str(t): str(n) for t, n in rows}


def _peer_score(r: InsuranceValueRange) -> tuple[float | None, float | None, float | None]:
    if r.pb is None or r.pb <= 0 or r.pb_median is None or r.pb_median <= 0:
        return None, None, None
    pb_discount = (r.pb / r.pb_median - 1) * 100
    roe_to_pb = r.roe / r.pb if r.roe is not None else None
    dy = r.dividend_yield
    if dy is not None and dy > 1:
        dy = dy / 100.0
    if roe_to_pb is None:
        score = None
    else:
        valuation_bonus = max(-0.30, min(0.30, -pb_discount / 100.0))
        score = roe_to_pb * 0.60 + valuation_bonus * 0.30 + (dy or 0.0) * 0.10
    return pb_discount, roe_to_pb, score


def compare_insurance_peers(
    ticker: str,
    name: str = "",
    peer_limit: int = 3,
    db_path: Path | str = DB_PATH,
) -> list[InsurancePeerRow]:
    """返回目标公司 + 3 个保险同行的价格/质量横评。"""
    ticker = (ticker or "").strip()[:6]
    con = _conn(db_path)
    try:
        names = _insurance_company_names(con)
    finally:
        con.close()

    peer_codes = [p for p in _PREFERRED_INSURANCE_PEERS if p != ticker][:peer_limit]
    codes = [ticker] + peer_codes
    out: list[InsurancePeerRow] = []
    for code in codes:
        company_name = name if code == ticker and name else names.get(code, code)
        rng = compute_insurance_value_range(code, company_name, db_path=db_path)
        pb_discount, roe_to_pb, score = _peer_score(rng)
        out.append(
            InsurancePeerRow(
                ticker=code,
                name=company_name,
                current_price=rng.current_price,
                buy_price=rng.buy_price,
                fair_price=rng.fair_price,
                sell_price=rng.sell_price,
                pb=rng.pb,
                pb_median=rng.pb_median,
                pb_discount_pct=pb_discount,
                roe=rng.roe,
                dividend_yield=rng.dividend_yield,
                embedded_value=rng.embedded_value,
                new_business_value=rng.new_business_value,
                p_ev=rng.p_ev,
                roe_to_pb=roe_to_pb,
                verdict_label=rng.verdict_label,
                score=score,
                note=rng.note,
            )
        )
    return out


def format_price(value: float | None) -> str:
    return f"¥{value:,.2f}" if value is not None else "—"


__all__ = [
    "InsurancePeerRow",
    "InsuranceValueRange",
    "compare_insurance_peers",
    "compute_insurance_value_range",
    "format_price",
]
