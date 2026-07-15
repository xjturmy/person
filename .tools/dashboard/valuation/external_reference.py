"""External price reference audit.

This module intentionally keeps external sell-side targets outside the core
fair-value model.  Internal valuation remains the decision anchor; external
references are used as a sanity check for optimism/pessimism.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_CSV = PROJECT_ROOT / ".config" / "external_price_refs.csv"
COMPANIES_DIR = PROJECT_ROOT / "02_companies"


@dataclass
class ExternalPriceReference:
    ticker: str
    name: str
    source: str
    as_of: date | None
    target_mid: float | None
    target_low: float | None
    target_high: float | None
    coverage: int | None
    current_price: float | None
    note: str = ""

    @property
    def upside_pct(self) -> float | None:
        if self.target_mid is None or self.current_price is None or self.current_price <= 0:
            return None
        return self.target_mid / self.current_price - 1.0


@dataclass
class ReferenceCheck:
    ticker: str
    name: str
    internal_price: float | None
    external: ExternalPriceReference | None
    diff_pct: float | None
    verdict_code: str
    verdict_label: str
    action_hint: str


def _norm_ticker(raw: str) -> str:
    text = str(raw or "").strip()
    if text.isdigit() and len(text) < 6:
        return text.zfill(6)
    return text


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_date(value) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _company_dir_for(ticker: str) -> Path | None:
    ticker = _norm_ticker(ticker)
    if not COMPANIES_DIR.exists():
        return None
    for p in COMPANIES_DIR.iterdir():
        if not p.is_dir():
            continue
        # A folder match is preferred over scanning files.  Most company
        # folders are numbered, so ticker lookup falls back to README files.
        readme = p / "04_券商分析" / "README.md"
        if ticker in p.name:
            return p
        if readme.exists():
            try:
                if ticker in readme.read_text(encoding="utf-8"):
                    return p
            except OSError:
                pass
    # Last fallback: use companies.csv if present.
    csv_path = PROJECT_ROOT / ".config" / "companies.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if _norm_ticker(row.get("stock", "")) == ticker:
                    folder = row.get("folder", "")
                    p = COMPANIES_DIR / folder
                    return p if p.exists() else None
    return None


def _load_manual_reference(ticker: str, path: Path = CONFIG_CSV) -> ExternalPriceReference | None:
    ticker = _norm_ticker(ticker)
    if not path.exists():
        return None
    best: ExternalPriceReference | None = None
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if _norm_ticker(row.get("ticker", "")) != ticker:
                continue
            ref = ExternalPriceReference(
                ticker=ticker,
                name=str(row.get("name") or "").strip(),
                source=str(row.get("source") or "manual").strip(),
                as_of=_to_date(row.get("as_of")),
                target_mid=_to_float(row.get("target_mid") or row.get("target_price")),
                target_low=_to_float(row.get("target_low")),
                target_high=_to_float(row.get("target_high")),
                coverage=int(_to_float(row.get("coverage")) or 0) or None,
                current_price=_to_float(row.get("current_price")),
                note=str(row.get("note") or "").strip(),
            )
            if best is None or ((ref.as_of or date.min) >= (best.as_of or date.min)):
                best = ref
    return best


def _load_broker_reference(ticker: str) -> ExternalPriceReference | None:
    ticker = _norm_ticker(ticker)
    company_dir = _company_dir_for(ticker)
    if company_dir is None:
        return None
    target_csv = company_dir / "04_券商分析" / "02_评级与目标价.csv"
    if not target_csv.exists():
        return None

    rows: list[dict] = []
    with target_csv.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            target = _to_float(row.get("当前目标价"))
            if target is None or target <= 0:
                continue
            rows.append(row)
    if not rows:
        return None

    def row_date(row: dict) -> date:
        return _to_date(row.get("报告日期")) or date.min

    latest_day = max(row_date(r) for r in rows)
    recent = [r for r in rows if row_date(r) == latest_day]
    targets = [_to_float(r.get("当前目标价")) for r in recent]
    targets = [x for x in targets if x is not None and x > 0]
    if not targets:
        return None
    orgs = {str(r.get("券商名称") or "").strip() for r in recent if str(r.get("券商名称") or "").strip()}
    closes = [_to_float(r.get("最新收盘价")) for r in recent]
    closes = [x for x in closes if x is not None and x > 0]
    return ExternalPriceReference(
        ticker=ticker,
        name=company_dir.name.split("_", 1)[-1],
        source="broker_csv",
        as_of=latest_day,
        target_mid=mean(targets),
        target_low=min(targets),
        target_high=max(targets),
        coverage=len(orgs) or len(targets),
        current_price=closes[0] if closes else None,
        note=f"来自 {target_csv.relative_to(PROJECT_ROOT)} 最新报告日目标价",
    )


def load_external_reference(ticker: str, name: str = "") -> ExternalPriceReference | None:
    """Load the best available external reference.

    Priority:
    1. `.config/external_price_refs.csv` manual/Wind/Choice import.
    2. Company `04_券商分析/02_评级与目标价.csv` generated by broker pipeline.
    """
    manual = _load_manual_reference(ticker)
    broker = _load_broker_reference(ticker)
    candidates = [x for x in (manual, broker) if x is not None]
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x.as_of or date.min, 1 if x.source.lower().startswith("wind") else 0))
    ref = candidates[-1]
    if name and not ref.name:
        ref.name = name
    return ref


def compare_with_internal(
    ticker: str,
    name: str,
    internal_price: float | None,
    external: ExternalPriceReference | None = None,
) -> ReferenceCheck:
    ticker = _norm_ticker(ticker)
    external = external if external is not None else load_external_reference(ticker, name=name)
    if external is None or external.target_mid is None:
        return ReferenceCheck(
            ticker, name, internal_price, None, None,
            "missing_external", "⚪ 外部参考缺失",
            "先补 Wind/券商目标价,当前只用内部估值。",
        )
    if internal_price is None or internal_price <= 0:
        return ReferenceCheck(
            ticker, name, internal_price, external, None,
            "reference_only", "⚪ 仅有外部参考",
            "不能直接作为买入价,先补内部合理价。",
        )

    diff = external.target_mid / internal_price - 1.0
    if abs(diff) <= 0.10:
        code = "aligned"
        label = "🟢 内外基本一致"
        hint = "内部估值得到外部验证,可按原条件单纪律执行。"
    elif diff > 0.10:
        code = "external_higher"
        label = "🟡 外部明显更乐观"
        hint = "不要立刻抬高买入线;复核增长/ROE/估值倍数是否保守。"
    else:
        code = "external_lower"
        label = "🔴 外部明显更谨慎"
        hint = "收紧加仓条件,优先复核内部估值是否过度乐观。"

    return ReferenceCheck(ticker, name, internal_price, external, diff, code, label, hint)


__all__ = [
    "ExternalPriceReference",
    "ReferenceCheck",
    "load_external_reference",
    "compare_with_internal",
]
