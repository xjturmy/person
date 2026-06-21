"""巴菲特分类自适应评分器 — 对齐 Lynch 范式。

设计目标:把 .tools/rules/buffett.yaml 的"硬阈值/绝对触发"换成
"三类自适应 + 类型专属 5 维评分(0-100)+ 加权综合",让 Buffett
与 Lynch 同口径,可在 UI 上横向并列对比。

三类(避免与 Lynch 6 类冲突,定位"巴菲特视角"):
  compounder       — 复利稳健型(茅台/伊利/美的):ROE 长期≥15% + CAGR 5-20%
  cyclical_value   — 周期价值型(中车/三美):波动大但 ROIC 长期为正
  quality_growth   — 高质量成长型(宁王/比亚迪/中际旭创):CAGR ≥20% + FCF 转正

5 维(每维 0-100):
  moat_quality          护城河质量    25%
  compounding           复利能力      25%
  capital_allocation    资本配置      20%
  financial_safety      财务安全      15%
  valuation             估值合理性    15%

数据装配复用 lynch.classifier.load_metrics_from_db(同一套 DuckDB 字段),
额外补 fcf_cagr / roe_10y_min 等 buffett 专属指标。

阈值表见同目录 dim_formulas.yaml。

CLI:
  .venv/bin/python .tools/dashboard/masters/buffett/classifier.py 600519
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml
try:
    from dashboard_helpers import get_conn
except Exception:
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    try:
        from dashboard_helpers import get_conn
    except Exception:
        _sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
        from dashboard_helpers import get_conn

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"
DIM_FORMULAS_PATH = Path(__file__).with_name("dim_formulas.yaml")


# ───── 阈值表加载 ────────────────────────────────────────────────────

def _load_dim_formulas() -> dict:
    return yaml.safe_load(DIM_FORMULAS_PATH.read_text(encoding="utf-8"))


_DIM_CFG = _load_dim_formulas()
_RATING = _DIM_CFG.get("rating_thresholds", {"excellent": 75, "good": 60, "warning": 45})
_DIM_SCHEMA = _DIM_CFG["dim_schema"]
_CLS_META = _DIM_CFG["classification"]


# ───── 数据结构(对齐 lynch.classifier) ──────────────────────────────

@dataclass
class ClassificationResult:
    cls_id: str
    cls_name: str
    cls_emoji: str
    confidence: float
    reason: str
    key_metrics: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "cls_id": self.cls_id, "cls_name": self.cls_name,
            "cls_emoji": self.cls_emoji, "confidence": self.confidence,
            "reason": self.reason,
            "key_metrics": dict(self.key_metrics),
            "notes": list(self.notes),
            "extra": dict(self.extra),
        }


@dataclass
class DimScore:
    key: str
    label: str
    score: float | None
    badge: str
    weight: float
    inputs: dict[str, str]
    formula: str
    note: str

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label,
            "score": self.score, "badge": self.badge, "weight": self.weight,
            "inputs": dict(self.inputs), "formula": self.formula, "note": self.note,
        }


# ───── 工具函数 ──────────────────────────────────────────────────────

def _clip(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _badge(s: float | None) -> str:
    if s is None:
        return "⚪"
    if s >= _RATING["excellent"]: return "🟢"
    if s >= _RATING["good"]:      return "🟡"
    if s >= _RATING["warning"]:   return "🟠"
    return "🔴"


def _missing(key: str, label: str, weight: float, what: str) -> DimScore:
    return DimScore(key=key, label=label, score=None, badge="⚪",
                    weight=weight, inputs={"⚠️": what}, formula="—",
                    note=f"数据缺失:{what}")


def _linear(value: float, full_at: float, zero_at: float) -> float:
    """value=full_at → 100,value=zero_at → 0,线性映射;clip 到 [0,100]。

    自动处理 zero_at > full_at(反向规则,如负债率)的情况。
    """
    if full_at == zero_at:
        return 50.0
    pct = (value - zero_at) / (full_at - zero_at)
    return _clip(pct * 100)


def _pct(x: float | None, decimals: int = 1) -> str:
    return "—" if x is None else f"{x * 100:.{decimals}f}%"


def _num(x: float | None, decimals: int = 2) -> str:
    return "—" if x is None else f"{x:.{decimals}f}"


# ───── 5 维评分函数 ──────────────────────────────────────────────────

def _score_moat_quality(m: dict, cls_id: str) -> DimScore:
    cfg = _DIM_SCHEMA["moat_quality"]
    cal = cfg["type_calibration"][cls_id]
    w = cfg["weight"]
    roe_mean = m.get("roe_10y_mean") or m.get("roe")
    if roe_mean is None:
        return _missing("moat_quality", cfg["label"], w, "ROE 长期均值")
    score = _linear(roe_mean, cal["roe_full"], cal["roe_zero"])
    # 毛利率稳定性加分(若有 5y cv)
    cv = m.get("net_margin_5y_cv")
    if cv is not None:
        # cv < 0.10 极稳定 +5,> 0.30 不稳定 -5
        if cv < 0.10:   score = _clip(score + 5)
        elif cv > 0.30: score = _clip(score - 5)
    return DimScore(
        key="moat_quality", label=cfg["label"], score=score, badge=_badge(score), weight=w,
        inputs={"ROE 长期": _pct(roe_mean), "净利率 5y CV": _pct(cv) if cv else "—"},
        formula=f"ROE 线性映射({cal['roe_zero']*100:.0f}% → 0,{cal['roe_full']*100:.0f}% → 100)+ 稳定性 ±5",
        note="深护城河" if score >= 75 else "一般护城河" if score >= 45 else "护城河浅",
    )


def _score_compounding(m: dict, cls_id: str) -> DimScore:
    cfg = _DIM_SCHEMA["compounding"]
    cal = cfg["type_calibration"][cls_id]
    w = cfg["weight"]
    # 优先 FCF CAGR;否则营收 CAGR;再否则净利 YoY
    cagr = m.get("fcf_cagr_10y") or m.get("rev_cagr_5y") or m.get("rev_cagr_3y")
    source = "FCF 10y" if m.get("fcf_cagr_10y") else "营收 CAGR" if m.get("rev_cagr_5y") or m.get("rev_cagr_3y") else None
    if cagr is None:
        np_yoy = m.get("np_yoy_recent")
        if np_yoy is None:
            return _missing("compounding", cfg["label"], w, "FCF / 营收 CAGR / 净利增速")
        cagr = np_yoy
        source = "净利 YoY 兜底"
    score = _linear(cagr, cal["cagr_full"], cal["cagr_zero"])
    return DimScore(
        key="compounding", label=cfg["label"], score=score, badge=_badge(score), weight=w,
        inputs={f"CAGR ({source})": _pct(cagr)},
        formula=f"{cal['cagr_zero']*100:+.0f}% → 0,{cal['cagr_full']*100:+.0f}% → 100",
        note="强复利" if score >= 75 else "稳" if score >= 45 else "弱/负增长",
    )


def _score_capital_allocation(m: dict, cls_id: str) -> DimScore:
    cfg = _DIM_SCHEMA["capital_allocation"]
    cal = cfg["type_calibration"][cls_id]
    w = cfg["weight"]
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is None:
        # ROE 兜底(高 ROE 公司通常资本配置好)
        roe = m.get("roe")
        if roe is None:
            return _missing("capital_allocation", cfg["label"], w, "CFO/净利润 或 ROE")
        score = _clip(roe * 400)
        return DimScore(
            key="capital_allocation", label=cfg["label"], score=score, badge=_badge(score), weight=w,
            inputs={"ROE (兜底)": _pct(roe)},
            formula="CFO/NI 缺失,用 ROE × 400 兜底",
            note="高效" if roe >= 0.18 else "一般",
        )
    score = _linear(cfo_ni, cal["cfo_ni_full"], cal["cfo_ni_zero"])
    return DimScore(
        key="capital_allocation", label=cfg["label"], score=score, badge=_badge(score), weight=w,
        inputs={"CFO/NI": _num(cfo_ni)},
        formula=f"{cal['cfo_ni_zero']:.1f} → 0,{cal['cfo_ni_full']:.1f} → 100",
        note="高质量现金" if score >= 75 else "可接受" if score >= 45 else "现金转化弱",
    )


def _score_financial_safety(m: dict, cls_id: str) -> DimScore:
    cfg = _DIM_SCHEMA["financial_safety"]
    cal = cfg["type_calibration"][cls_id]
    w = cfg["weight"]
    debt = m.get("debt_ratio")
    if debt is None:
        return _missing("financial_safety", cfg["label"], w, "资产负债率")
    # 反向:debt_safe → 100,debt_danger → 0
    score = _linear(debt, full_at=cal["debt_safe"], zero_at=cal["debt_danger"])
    cr = m.get("current_ratio")
    if cr is not None:
        if cr >= 2.0:   score = _clip(score + 5)
        elif cr < 1.0:  score = _clip(score - 5)
    return DimScore(
        key="financial_safety", label=cfg["label"], score=score, badge=_badge(score), weight=w,
        inputs={"负债率": _pct(debt), "流动比率": _num(cr) if cr else "—"},
        formula=f"负债率 ≤ {cal['debt_safe']*100:.0f}% 满分 / ≥ {cal['debt_danger']*100:.0f}% 0 分;流动比率 ±5",
        note="稳健" if score >= 75 else "可接受" if score >= 45 else "杠杆偏高",
    )


def _score_valuation(m: dict, cls_id: str) -> DimScore:
    cfg = _DIM_SCHEMA["valuation"]
    cal = cfg["type_calibration"][cls_id]
    w = cfg["weight"]
    pct = m.get("pe_pct_10y")
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    if pct is None and pe is None:
        return _missing("valuation", cfg["label"], w, "PE-TTM 或 10y 分位")
    if pct is not None:
        # 分位 0 → 100;target 分位 → 75;1.0 → 0(分段)
        target = cal["pe_pct_target"]
        if pct <= target:
            score = 75 + (target - pct) / target * 25  # 0→100,target→75
        else:
            score = max(0, 75 * (1 - (pct - target) / (1 - target)))
        score = _clip(score)
        inputs = {"PE 10y 分位": _pct(pct)}
        formula = f"分位 0→100,{target*100:.0f}%→75,100%→0"
    else:
        score = _clip(120 - pe * 2)
        inputs = {"PE-TTM": _num(pe, 1)}
        formula = "120 − 2×PE(无 10y 分位时兜底)"
    # PE×PB ≤ 22.5(格雷厄姆复合)加分,> 50 减分
    if pe is not None and pb is not None:
        cross = pe * pb
        inputs["PE×PB"] = _num(cross, 1)
        if cross <= 22.5:  score = _clip(score + 5)
        elif cross > 50:   score = _clip(score - 5)
    return DimScore(
        key="valuation", label=cfg["label"], score=score, badge=_badge(score), weight=w,
        inputs=inputs, formula=formula,
        note="低估" if score >= 75 else "合理" if score >= 45 else "偏贵",
    )


_DIM_SCORERS = {
    "moat_quality":       _score_moat_quality,
    "compounding":        _score_compounding,
    "capital_allocation": _score_capital_allocation,
    "financial_safety":   _score_financial_safety,
    "valuation":          _score_valuation,
}


def compute_buffett_dims(metrics: dict, cls_id: str) -> list[DimScore]:
    """按 Buffett 类别计算专属 5 维评分(0-100)。"""
    if cls_id not in _CLS_META:
        cls_id = "compounder"  # fallback
    out = []
    for key, scorer in _DIM_SCORERS.items():
        try:
            r = scorer(metrics, cls_id)
        except Exception as e:
            r = _missing(key, _DIM_SCHEMA[key]["label"], _DIM_SCHEMA[key]["weight"], f"err:{e}")
        out.append(r)
    return out


def overall_buffett(dims: list[DimScore]) -> tuple[float, str]:
    """加权综合分;缺失维度补 50 中性。"""
    total = 0.0
    for d in dims:
        s = d.score if d.score is not None else 50.0
        total += d.weight * s
    if total >= _RATING["excellent"]: badge = "🟢"
    elif total >= _RATING["good"]:    badge = "🟡"
    elif total >= _RATING["warning"]: badge = "🟠"
    else: badge = "🔴"
    return round(total, 1), badge


# ───── 分类逻辑 ──────────────────────────────────────────────────────

def classify(m: dict[str, Any]) -> ClassificationResult:
    """三步分类:
      1) 营收 CAGR ≥ 20% + FCF 转正 → quality_growth
      2) 营收波动大(净利率 CV > 0.30 或 ROE 跨度大)+ ROE 长期为正 → cyclical_value
      3) 其余 → compounder
    """
    cagr = m.get("rev_cagr_5y") or m.get("rev_cagr_3y")
    cagr_label = "5y" if m.get("rev_cagr_5y") is not None else "3y"
    roe = m.get("roe") or m.get("roe_10y_mean")
    fcf_cagr = m.get("fcf_cagr_10y")
    cv = m.get("net_margin_5y_cv")
    industry_l1 = (m.get("industry_sw_l1") or "").strip()

    km = {
        "申万一级": industry_l1 or "—",
        f"营收 {cagr_label} CAGR": _pct(cagr),
        "ROE 当前": _pct(m.get("roe")),
        "ROE 10y 均": _pct(m.get("roe_10y_mean")),
        "FCF 10y CAGR": _pct(fcf_cagr),
        "净利率 5y CV": _pct(cv),
        "负债率": _pct(m.get("debt_ratio")),
        "PE-TTM": _num(m.get("pe_ttm"), 1),
        "PE 10y 分位": _pct(m.get("pe_pct_10y")),
    }

    # ─ 步骤 1:高质量成长型
    if cagr is not None and cagr >= 0.20:
        fcf_ok = (fcf_cagr is not None and fcf_cagr > 0) or (m.get("cfo_to_ni") and m["cfo_to_ni"] > 0.5)
        if fcf_ok:
            return _build_result(
                "quality_growth", 0.85,
                f"营收 {cagr_label} CAGR {_pct(cagr)} ≥ 20% + FCF/CFO 正向 → 高质量成长型(后期苹果型)",
                km, m,
                extra_note="跟踪营收增速维持 + FCF 转化率;高增长缺少 FCF 不算 quality",
            )
        # 高增长但 FCF 不正 → 仍归 quality_growth 但降信心
        return _build_result(
            "quality_growth", 0.65,
            f"营收 {cagr_label} CAGR {_pct(cagr)} ≥ 20% 但 FCF 尚未转正 → 高质量成长型(候选)",
            km, m,
            extra_note="资本性扩张期,等 FCF 转正再加仓",
        )

    # ─ 步骤 2:周期价值型
    if cv is not None and cv > 0.30 and roe is not None and roe > 0:
        return _build_result(
            "cyclical_value", 0.75,
            f"净利率 5y CV {_pct(cv)} > 30% 波动显著 + ROE {_pct(roe)} > 0 长期为正 → 周期价值型",
            km, m,
            extra_note="低位买入(PE 分位 < 20% 时);PB 比 PE 更可靠",
        )

    # ─ 步骤 3:复利稳健型(默认)
    if cagr is None or roe is None:
        return _build_result(
            "compounder", 0.40,
            "数据不足以判定增长/质量分支,默认归入复利稳健型(置信度低)",
            km, m,
            extra_note="补全营收 CAGR / ROE 后重新分类",
        )
    return _build_result(
        "compounder", 0.85 if roe >= 0.15 else 0.65,
        f"营收 {cagr_label} CAGR {_pct(cagr)} 温和 + ROE {_pct(roe)} 长期可持续 → 复利稳健型",
        km, m,
        extra_note="巴菲特最爱的'喜诗糖果'类型 — 看长期 ROE 持续性",
    )


def _build_result(cls_id: str, conf: float, reason: str,
                  km: dict, m: dict, extra_note: str = "") -> ClassificationResult:
    meta = _CLS_META[cls_id]
    notes = [meta["desc"]]
    if extra_note:
        notes.append(extra_note)
    return ClassificationResult(
        cls_id=cls_id,
        cls_name=meta["name_cn"],
        cls_emoji=meta["emoji"],
        confidence=round(conf, 2),
        reason=reason,
        key_metrics=km,
        notes=notes,
    )


# ───── 数据装配 ──────────────────────────────────────────────────────

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return get_conn(str(db_path))


def _roe_10y_stats(con, ticker: str) -> tuple[float | None, float | None]:
    """返回 (ROE 10y 均值, ROE 10y 最小值)。基于 profitability 表所有 ROE 记录。"""
    cutoff = (date.today() - timedelta(days=365 * 10)).isoformat()
    try:
        rows = con.execute(
            "SELECT value FROM profitability "
            "WHERE ticker = ? AND metric = '净资产收益率(ROE)' "
            "AND value IS NOT NULL AND date >= ? ORDER BY date",
            [ticker, cutoff],
        ).fetchall()
    except Exception:
        return None, None
    if not rows:
        return None, None
    vals = [float(r[0]) for r in rows if r[0] is not None]
    if not vals:
        return None, None
    return sum(vals) / len(vals), min(vals)


def _fcf_cagr_10y(con, ticker: str) -> float | None:
    """自由现金流 10y CAGR(理杏仁直接字段);数据不足 10 年回退 5 年。"""
    for years in (10, 5):
        cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
        try:
            rows = con.execute(
                "SELECT date, value FROM cashflow "
                "WHERE ticker = ? AND metric = '自由现金流量' "
                "AND value IS NOT NULL AND date >= ? ORDER BY date",
                [ticker, cutoff],
            ).fetchall()
        except Exception:
            rows = []
        if len(rows) < 3:
            continue
        df = pd.DataFrame(rows, columns=["date", "value"])
        df["year"] = pd.to_datetime(df["date"]).dt.year
        yearly = df.groupby("year")["value"].last().dropna()
        if len(yearly) < 3:
            continue
        first, last = yearly.iloc[0], yearly.iloc[-1]
        n = len(yearly) - 1
        if first <= 0 or last <= 0 or n <= 0:
            # 用同比几何平均近似(避免负值开方)
            yoy = yearly.pct_change().dropna()
            if yoy.empty:
                continue
            factors = (yoy + 1).clip(lower=0.1)
            return float(factors.prod() ** (1.0 / len(factors)) - 1)
        return float((last / first) ** (1.0 / n) - 1)
    return None


def load_metrics_from_db(ticker: str, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """复用 lynch.classifier.load_metrics_from_db,叠加 Buffett 专属指标。"""
    # 复用 Lynch 数据装配(同一套字段)
    sys_path = str(Path(__file__).resolve().parent.parent.parent)
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from masters.lynch.classifier import load_metrics_from_db as _lynch_load  # noqa: E402

    m = _lynch_load(ticker, db_path=db_path)

    # 叠加 Buffett 专属
    con = _conn(db_path)
    try:
        roe_mean, roe_min = _roe_10y_stats(con, ticker)
        m["roe_10y_mean"] = roe_mean
        m["roe_10y_min"] = roe_min
        m["fcf_cagr_10y"] = _fcf_cagr_10y(con, ticker)
    finally:
        pass  # get_conn 单例,不关
    return m


def classify_ticker(ticker: str, **kwargs) -> ClassificationResult:
    m = load_metrics_from_db(ticker, **kwargs)
    return classify(m)


# ───── CLI ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="*", default=[])
    args = ap.parse_args()

    targets = args.ticker
    if not targets:
        comp = pd.read_csv(ROOT / ".config" / "companies.csv", dtype={"stock": str})
        targets = comp["stock"].tolist()

    for t in targets:
        try:
            r = classify_ticker(t)
            dims = compute_buffett_dims(load_metrics_from_db(t), r.cls_id)
            overall, badge = overall_buffett(dims)
            print(f"\n{'─'*68}")
            print(f"  {r.cls_emoji} {r.cls_name}  ·  {t}  ·  综合 {overall:.1f} {badge}  ·  conf={r.confidence:.0%}")
            print(f"{'─'*68}")
            print(f"  {r.reason}")
            print(f"\n  5 维评分:")
            for d in dims:
                s = "—" if d.score is None else f"{d.score:.0f}"
                print(f"    {d.badge} {d.label:<14} {s:>5}  w={d.weight:.2f}  ({d.note})")
        except Exception as e:
            print(f"\n❌ {t}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
