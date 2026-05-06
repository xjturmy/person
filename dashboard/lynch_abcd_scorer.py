"""彼得林奇 ABCD/12345 双维评分引擎(三类公司:稳健 / 快速 / 周期)。

文档同源:01_knowledge/03_投资策略与选股/02_彼得林奇投资法/
  - 02_稳健增长型_ABCD评估.md
  - 03_快速增长型_ABCD评估.md
  - 04_周期型_ABCD评估.md

设计:
- 每个评分项返回 ScoreItem(key, label, score, max_score, source, detail)
  source: "auto"(财报)/ "manual"(用户 slider)/ "missing"(缺数据)
- 三类公司各有"好公司"+"好价格"两套评分表
- 调整因子:加分项 / 减分项,可数据驱动也可用户标记
- 最终输出 AbcdResult,包含 ABCD 等级 / 12345 等级 / 矩阵决策

API:
    from lynch_abcd_scorer import score_abcd
    result = score_abcd(ticker, m, cls_id_used,
                        manual_inputs={'industry_share': 7, ...})
    # result.company_score / result.price_score / result.matrix_decision
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# ───── 数据结构 ──────────────────────────────────────────────────────────


@dataclass
class ScoreItem:
    key: str                  # e.g. "rev_cagr"
    label: str                # e.g. "营收 CAGR"
    score: float              # 0 ~ max_score
    max_score: float
    source: str               # "auto" / "manual" / "missing"
    detail: str               # 一句话说明:为什么得这个分
    raw_value: Any = None     # 原始指标值(显示用)


@dataclass
class AdjustItem:
    key: str
    label: str
    delta: float              # +/- 调整分
    triggered: bool           # 是否触发
    polarity: str             # "bonus" / "penalty"
    detail: str


@dataclass
class AbcdResult:
    cls_id: str               # stalwart / fast_grower / cyclical
    cls_name: str             # 中文名

    company_items: list[ScoreItem] = field(default_factory=list)
    company_adjusts: list[AdjustItem] = field(default_factory=list)
    company_base_score: float = 0.0
    company_adjust_total: float = 0.0
    company_final_score: float = 0.0
    company_grade: str = "D"           # A / B / C / D
    company_max: float = 100.0

    price_items: list[ScoreItem] = field(default_factory=list)
    price_adjusts: list[AdjustItem] = field(default_factory=list)
    price_base_score: float = 0.0
    price_adjust_total: float = 0.0
    price_final_score: float = 0.0
    price_grade: int = 5               # 1 / 2 / 3 / 4 / 5
    price_max: float = 100.0

    matrix_decision: str = ""          # "全力出击" / ...
    matrix_color: str = "#9CA3AF"      # 决策色


# ───── 辅助 ─────────────────────────────────────────────────────────────


def _missing(key: str, label: str, max_score: float, what: str = "") -> ScoreItem:
    return ScoreItem(
        key=key, label=label, score=0, max_score=max_score,
        source="missing",
        detail=f"缺 {what or '数据'},暂记 0 分",
    )


def _ge(value: float | None, *thresholds_scores: tuple) -> tuple[float, str] | None:
    """阈值梯度评分。thresholds_scores 形如 [(>=阈值, 得分, 标签), ...] 从高到低。
    返回 (得分, 标签) 或 None。
    """
    if value is None:
        return None
    for th, sc, lab in thresholds_scores:
        if value >= th:
            return sc, lab
    return 0, "未达阈值"


def _le(value: float | None, *thresholds_scores: tuple) -> tuple[float, str] | None:
    """反向阈值:value 越小越好。thresholds_scores 形如 [(<=阈值, 得分, 标签), ...] 从低到高。"""
    if value is None:
        return None
    for th, sc, lab in thresholds_scores:
        if value <= th:
            return sc, lab
    return 0, "超过阈值"


def _grade_company(score: float) -> str:
    """ABCD 等级 — 三类共用同一阈值表(文档约定)。"""
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    return "D"


def _grade_price(score: float) -> int:
    """12345 等级 — 三类共用。"""
    if score >= 85: return 1
    if score >= 70: return 2
    if score >= 55: return 3
    if score >= 40: return 4
    return 5


# ───── 矩阵决策 ──────────────────────────────────────────────────────────


# 4×5 决策矩阵:[公司质量等级][价格等级] → (决策文案, 颜色)
# 文档同源,适用于稳健 / 快速 / 周期(措辞略有差异,这里取通用版)
MATRIX = {
    "A": {
        1: ("🟢🟢🟢 全力出击 · 战略性仓位",       "#16A34A"),
        2: ("🟢🟢 积极建仓 · 主要仓位",           "#22C55E"),
        3: ("🟡 持有 / 谨慎新增",                "#EAB308"),
        4: ("🟠 停止买入 / 减仓",                "#F97316"),
        5: ("🔴 坚决卖出",                       "#DC2626"),
    },
    "B": {
        1: ("🟢🟢 重点配置 · 重要持仓",           "#22C55E"),
        2: ("🟢 适度配置 · 卫星仓位",             "#65A30D"),
        3: ("🟡 持有 / 跟踪",                    "#EAB308"),
        4: ("🟠 考虑减仓",                       "#F97316"),
        5: ("🔴 卖出",                           "#DC2626"),
    },
    "C": {
        1: ("🟡 小仓试探 · ≤ 5%",                "#FACC15"),
        2: ("🟠 少量试探(需明确催化)",          "#FB923C"),
        3: ("⚪ 观望",                           "#9CA3AF"),
        4: ("🔴 回避",                           "#DC2626"),
        5: ("🔴 坚决回避",                       "#B91C1C"),
    },
    "D": {
        1: ("⚠️ 投机性参与 · 极小仓",             "#F59E0B"),
        2: ("🔴 不参与",                         "#DC2626"),
        3: ("🔴 不参与",                         "#DC2626"),
        4: ("🔴 不参与",                         "#DC2626"),
        5: ("🔴 不参与",                         "#DC2626"),
    },
}


# ═══════════════════════════════════════════════════════════════════════
# 🛡️ STALWART — 稳健增长型评分(对应 02_稳健增长型_ABCD评估.md)
# ═══════════════════════════════════════════════════════════════════════


def _stalwart_company(m: dict, manual: dict) -> tuple[list[ScoreItem], list[AdjustItem]]:
    """稳健"好公司"评分:9 项 = 45 + 30 + 25 = 100 分。"""
    items: list[ScoreItem] = []

    # 1. 增长稳定性(45)─────────────────────────
    # 1.1 营收 5y CAGR(20):10-15% 满分,15-20% 16,5-10% 10,其它 5
    cagr = m.get("rev_cagr_5y")
    if cagr is None:
        items.append(_missing("rev_cagr", "营收 5y CAGR", 20, "rev_cagr_5y"))
    else:
        pct = cagr * 100
        if 10 <= pct <= 15:
            sc, lab = 20, f"{pct:.1f}% 完美稳健区间"
        elif 15 < pct <= 20:
            sc, lab = 16, f"{pct:.1f}% 略偏快但仍稳健"
        elif 5 <= pct < 10:
            sc, lab = 10, f"{pct:.1f}% 偏低(接近缓慢类)"
        else:
            sc, lab = 5, f"{pct:.1f}% 不在稳健区间"
        items.append(ScoreItem("rev_cagr", "营收 5y CAGR", sc, 20,
                                "auto", lab, raw_value=pct))

    # 1.2 增长连续性(15)— 用最近营收 YoY 近似(每季 8 季数据 _quarterly_yoy 难直接拿)
    yoy = m.get("rev_yoy_recent")
    if yoy is None:
        items.append(_missing("growth_continuity", "增长连续性", 15, "rev_yoy"))
    else:
        pct = yoy * 100
        if pct >= 10:
            sc, lab = 15, f"最新 YoY {pct:.1f}% ≥ 10%(近似 8/8 季)"
        elif pct >= 5:
            sc, lab = 10, f"最新 YoY {pct:.1f}% 偏弱"
        else:
            sc, lab = 3, f"最新 YoY {pct:.1f}% 已断档"
        items.append(ScoreItem("growth_continuity", "增长连续性(单季 YoY)", sc, 15,
                                "auto", lab, raw_value=pct))

    # 1.3 净利率稳定性(10)— 自动从 5y 净利率时序算变异系数
    cv = m.get("net_margin_5y_cv")
    nm_mean = m.get("net_margin_5y_mean")
    if cv is None:
        items.append(_manual_or_missing(
            "margin_stability", "净利率稳定性", 10,
            manual.get("margin_stability"),
            hint="5y 净利率标准差/均值 <10% = 10 分;10-20% = 6 分;>20% = 0 分",
        ))
    else:
        cv_pct = cv * 100
        nm_pct = (nm_mean or 0) * 100
        if cv_pct < 10:
            sc, lab = 10, f"5y 变异系数 {cv_pct:.1f}%(均值 {nm_pct:.1f}%,极稳)"
        elif cv_pct < 20:
            sc, lab = 6, f"5y 变异系数 {cv_pct:.1f}%(均值 {nm_pct:.1f}%,偏稳)"
        elif cv_pct < 35:
            sc, lab = 3, f"5y 变异系数 {cv_pct:.1f}%(波动较大)"
        else:
            sc, lab = 0, f"5y 变异系数 {cv_pct:.1f}%(波动太大,不属稳健)"
        items.append(ScoreItem("margin_stability", "净利率稳定性",
                                sc, 10, "auto", lab, raw_value=cv_pct))

    # 2. 护城河(30)─────────────────────────
    # 2.1 ROE 持续性(15)
    roe = m.get("roe")
    if roe is None:
        items.append(_missing("roe_durability", "ROE 5y 均值", 15, "roe"))
    else:
        pct = roe * 100 if roe < 1 else roe
        if pct >= 18:
            sc, lab = 15, f"ROE {pct:.1f}% ≥ 18%(护城河强)"
        elif pct >= 15:
            sc, lab = 11, f"ROE {pct:.1f}%(护城河合格)"
        elif pct >= 12:
            sc, lab = 6, f"ROE {pct:.1f}%(护城河弱)"
        else:
            sc, lab = 0, f"ROE {pct:.1f}% < 12%(无护城河)"
        items.append(ScoreItem("roe_durability", "ROE 持续性", sc, 15,
                                "auto", lab, raw_value=pct))

    # 2.2 毛利率 vs 行业(10)— 自动从 profitability 表行业 key 取
    diff_pp = m.get("gross_margin_vs_industry_pp")
    co_gm = m.get("gross_margin_self")
    ind_gm = m.get("gross_margin_industry_median")
    if diff_pp is None:
        items.append(_manual_or_missing(
            "gross_margin_vs_peers", "毛利率 vs 行业", 10,
            manual.get("gross_margin_vs_peers"),
            hint="领先 ≥5pp = 10 分;持平 = 6 分;落后 = 0 分(行业数据缺)",
        ))
    else:
        co_pct = (co_gm * 100) if co_gm and co_gm < 1 else (co_gm or 0)
        ind_pct = (ind_gm * 100) if ind_gm and ind_gm < 1 else (ind_gm or 0)
        if diff_pp >= 5:
            sc, lab = 10, f"自身 {co_pct:.1f}% vs 行业 {ind_pct:.1f}% · 领先 +{diff_pp:.1f}pp"
        elif diff_pp >= -1:
            sc, lab = 6, f"自身 {co_pct:.1f}% vs 行业 {ind_pct:.1f}% · 持平 {diff_pp:+.1f}pp"
        else:
            sc, lab = 0, f"自身 {co_pct:.1f}% vs 行业 {ind_pct:.1f}% · 落后 {diff_pp:+.1f}pp"
        items.append(ScoreItem("gross_margin_vs_peers", "毛利率 vs 行业",
                                sc, 10, "auto", lab, raw_value=diff_pp))

    # 2.3 品牌 / 分销 / 规模优势(5)— 用 ROE 高 + 毛利率领先 做规模代理 baseline
    # 用户可后续覆盖
    roe_strong = (m.get("roe") or 0) >= 0.18
    gm_lead = (m.get("gross_margin_vs_industry_pp") or 0) >= 5
    manual_v = manual.get("brand_moat")
    if manual_v is not None:
        v = max(0, min(5, float(manual_v)))
        items.append(ScoreItem("brand_moat", "品牌/分销/规模优势",
                                v, 5, "manual",
                                f"用户评分 {v:.0f}/5",
                                raw_value=manual_v))
    else:
        # 自动 baseline:ROE 强 +2 / 毛利率领先 +2 / 默认 1(中性)
        baseline = 1
        reasons = []
        if roe_strong:
            baseline += 2
            reasons.append("ROE ≥18%")
        if gm_lead:
            baseline += 2
            reasons.append("毛利率领先行业")
        baseline = min(5, baseline)
        reason_str = " + ".join(reasons) if reasons else "默认中性"
        items.append(ScoreItem("brand_moat", "品牌/分销/规模优势",
                                baseline, 5, "auto",
                                f"自动 baseline {baseline}/5({reason_str};用户可调整)",
                                raw_value=baseline))

    # 3. 财务韧性(25)─────────────────────────
    # 3.1 资产负债率(10)
    debt = m.get("debt_ratio")
    if debt is None:
        items.append(_missing("debt_ratio", "资产负债率", 10, "debt_ratio"))
    else:
        pct = debt * 100 if debt < 1 else debt
        if pct < 30:
            sc, lab = 10, f"{pct:.1f}% 极低杠杆"
        elif pct < 50:
            sc, lab = 7, f"{pct:.1f}% 低杠杆"
        elif pct < 65:
            sc, lab = 3, f"{pct:.1f}% 中等杠杆"
        else:
            sc, lab = 0, f"{pct:.1f}% 高杠杆"
        items.append(ScoreItem("debt_ratio", "资产负债率", sc, 10,
                                "auto", lab, raw_value=pct))

    # 3.2 CFO/NI(10)
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is None:
        items.append(_missing("cfo_quality", "CFO/净利润", 10, "cfo_to_ni"))
    else:
        if cfo_ni >= 1.0:
            sc, lab = 10, f"CFO/NI {cfo_ni:.2f} ≥ 1.0(优秀)"
        elif cfo_ni >= 0.9:
            sc, lab = 7, f"CFO/NI {cfo_ni:.2f} 健康"
        elif cfo_ni >= 0.7:
            sc, lab = 3, f"CFO/NI {cfo_ni:.2f} 偏弱"
        else:
            sc, lab = 0, f"CFO/NI {cfo_ni:.2f} 应收/存货沉淀"
        items.append(ScoreItem("cfo_quality", "CFO/净利润", sc, 10,
                                "auto", lab, raw_value=cfo_ni))

    # 3.3 股息支付历史(5)— 自动从 valuation 时序数连续派息年数
    years = m.get("dividend_years_continuous")
    div = m.get("dividend_yield")
    if years is None:
        items.append(_missing("dividend_history", "股息支付历史", 5,
                                "valuation.股息率 时序"))
    else:
        div_pct = (div * 100) if div else 0
        if years >= 10:
            sc, lab = 5, f"连续派息 {years} 年 ≥ 10 年(当前 {div_pct:.2f}%)"
        elif years >= 5:
            sc, lab = 3, f"连续派息 {years} 年(当前 {div_pct:.2f}%)"
        elif years >= 1:
            sc, lab = 1, f"仅连续 {years} 年派息(不稳定)"
        else:
            sc, lab = 0, "未派息或缺数据"
        items.append(ScoreItem("dividend_history", "股息支付历史",
                                sc, 5, "auto", lab, raw_value=years))

    return items, _stalwart_adjusts(m, manual)


def _stalwart_adjusts(m: dict, manual: dict) -> list[AdjustItem]:
    """稳健调整因子(±10 分,6 项,多数主观)。"""
    items: list[AdjustItem] = []

    # 加分:连续 5y ROE 稳定 ≥ 20%(自动近似:看当前 ROE)
    roe = m.get("roe")
    if roe is not None:
        roe_pct = roe * 100 if roe < 1 else roe
        triggered = roe_pct >= 20
        items.append(AdjustItem(
            "roe_5y_stable", "连续 5y ROE 稳定 ≥ 20%",
            8 if triggered else 0, triggered, "bonus",
            f"当前 ROE {roe_pct:.1f}% — 5y 均值 ≥20% 由用户在历史数据中确认"
            if triggered else f"当前 ROE {roe_pct:.1f}% < 20%",
        ))

    # 主观加减项 — 用户标记
    for key, label, delta, polarity, hint in [
        ("buyback", "持续股票回购(非债务驱动)", 5, "bonus",
         "近 3 年回购金额 ≥ 净利润 5%,且 FCF 覆盖"),
        ("market_share_strengthen", "行业龙头地位强化", 3, "bonus",
         "市占率提升 ≥ 5pp 或竞对出清"),
        ("growth_stagnation", "增长滑落到缓慢类", -15, "penalty",
         "营收 CAGR 连 2 年 <5% 且 ROE 持续走低"),
        ("tech_disruption", "主业被技术替代", -10, "penalty",
         "核心产品被颠覆(如 PC→移动 / 燃油→EV)"),
        ("goodwill_impair", "重大商誉减值/造假预警", -15, "penalty",
         "商誉减值 > 净资产 10% 或外部审计变更"),
    ]:
        flag = bool(manual.get(f"adj_{key}"))
        items.append(AdjustItem(
            key, label, delta if flag else 0, flag, polarity,
            hint,
        ))

    return items


def _stalwart_price(m: dict, manual: dict) -> tuple[list[ScoreItem], list[AdjustItem]]:
    """稳健"好价格"评分:6 项 = 60 + 40 = 100 分。"""
    items: list[ScoreItem] = []

    # 1. 增长估值锚(60)
    # 1.1 PEG 估值(35)
    peg = m.get("peg_lixinger")
    if peg is None:
        # 退化:用 PE / 5y CAGR
        pe = m.get("pe_ttm")
        cagr = m.get("rev_cagr_5y")
        if pe and cagr and cagr > 0:
            peg = pe / (cagr * 100)
    if peg is None:
        items.append(_missing("peg", "PEG 估值", 35, "PE-TTM 或 CAGR"))
    else:
        if peg <= 0.8:
            sc, lab = 35, f"PEG {peg:.2f} ≤ 0.8(高度低估)"
        elif peg <= 1.0:
            sc, lab = 28, f"PEG {peg:.2f}(适度低估)"
        elif peg <= 1.3:
            sc, lab = 18, f"PEG {peg:.2f}(合理)"
        elif peg <= 1.7:
            sc, lab = 8, f"PEG {peg:.2f}(偏高)"
        else:
            sc, lab = 0, f"PEG {peg:.2f} > 1.7(估值反转预警)"
        items.append(ScoreItem("peg", "PEG 估值", sc, 35,
                                "auto", lab, raw_value=peg))

    # 1.2 PE 历史分位(15)
    pct10y = m.get("pe_pct_10y")
    if pct10y is None:
        items.append(_missing("pe_pct", "PE 5y 分位", 15, "pe_pct_10y"))
    else:
        p = pct10y * 100 if pct10y < 1 else pct10y
        if p < 30:
            sc, lab = 15, f"{p:.0f}% 分位 — 低估"
        elif p < 50:
            sc, lab = 11, f"{p:.0f}% 分位 — 偏低"
        elif p < 70:
            sc, lab = 6, f"{p:.0f}% 分位 — 中位"
        else:
            sc, lab = 0, f"{p:.0f}% 分位 — 高估"
        items.append(ScoreItem("pe_pct", "PE 历史分位", sc, 15,
                                "auto", lab, raw_value=p))

    # 1.3 PB 与 ROE 匹配 ROE/PB(10)
    roe = m.get("roe")
    pb = m.get("pb")
    if roe is None or pb is None or pb <= 0:
        items.append(_missing("roe_pb", "ROE/PB", 10, "roe / pb"))
    else:
        roe_pct = roe * 100 if roe < 1 else roe
        ratio = roe_pct / pb
        if ratio >= 5:
            sc, lab = 10, f"ROE/PB {ratio:.1f}(性价比佳)"
        elif ratio >= 3:
            sc, lab = 6, f"ROE/PB {ratio:.1f}(中等)"
        else:
            sc, lab = 0, f"ROE/PB {ratio:.1f}(偏差)"
        items.append(ScoreItem("roe_pb", "ROE/PB", sc, 10,
                                "auto", lab, raw_value=ratio))

    # 2. 股息与情绪(40)
    # 2.1 股息率(15)
    div = m.get("dividend_yield")
    if div is None:
        items.append(_missing("dividend_yield", "股息率", 15, "dividend_yield"))
    else:
        pct = div * 100 if div < 1 else div
        if pct >= 3:
            sc, lab = 15, f"{pct:.2f}% ≥ 3%"
        elif pct >= 2:
            sc, lab = 10, f"{pct:.2f}% 偏低"
        elif pct >= 1:
            sc, lab = 5, f"{pct:.2f}% 弱"
        else:
            sc, lab = 0, f"{pct:.2f}% 几无"
        items.append(ScoreItem("dividend_yield", "股息率", sc, 15,
                                "auto", lab, raw_value=pct))

    # 2.2 股息率历史分位(10)— 自动从 valuation 5y 时序
    div_pct_5y = m.get("dividend_yield_5y_pct")
    if div_pct_5y is None:
        items.append(_missing("div_pct", "股息率 5y 分位", 10, "valuation 时序"))
    else:
        p = div_pct_5y * 100
        if p > 70:
            sc, lab = 10, f"{p:.0f}% 分位 — 历史高位(价格相对低)"
        elif p > 40:
            sc, lab = 6, f"{p:.0f}% 分位 — 中位"
        else:
            sc, lab = 0, f"{p:.0f}% 分位 — 历史低位(价格相对高)"
        items.append(ScoreItem("div_pct", "股息率 5y 分位",
                                sc, 10, "auto", lab, raw_value=p))

    # 2.3 机构情绪(15)— 用 PE 5y 分位 + 股息率 5y 分位 代理"冷门程度"
    manual_v = manual.get("institution_mood")
    if manual_v is not None:
        v = max(0, min(15, float(manual_v)))
        items.append(ScoreItem("institution_mood", "机构关注度",
                                v, 15, "manual", f"用户评分 {v:.0f}/15"))
    else:
        pct = m.get("pe_pct_10y")
        div_pct = m.get("dividend_yield_5y_pct")
        score = 7  # 默认中性
        reasons = []
        if pct is not None:
            p = pct * 100 if pct < 1 else pct
            if p < 30:
                score += 4; reasons.append(f"PE 分位 {p:.0f}% 冷门")
            elif p > 70:
                score -= 4; reasons.append(f"PE 分位 {p:.0f}% 热门")
            else:
                reasons.append(f"PE 分位 {p:.0f}% 中性")
        if div_pct is not None:
            d = div_pct * 100
            if d > 70:
                score += 3; reasons.append(f"股息分位 {d:.0f}% 历史高位")
            elif d < 30:
                score -= 2; reasons.append(f"股息分位 {d:.0f}% 历史低位")
        score = max(0, min(15, score))
        items.append(ScoreItem("institution_mood", "机构关注度",
                                score, 15, "auto",
                                f"代理估算 {score}/15:" + " · ".join(reasons)
                                + " · 真机构持股数据待接入",
                                raw_value=score))

    return items, _stalwart_price_adjusts(m, manual)


def _stalwart_price_adjusts(m: dict, manual: dict) -> list[AdjustItem]:
    """稳健好价格调整(±10,4 项)。"""
    out: list[AdjustItem] = []
    for key, label, delta, polarity, hint in [
        ("non_fund_panic", "非基本面错杀", 10, "bonus",
         "1 个月内跌 >20%,基本面未变"),
        ("results_lag", "业绩超预期但股价滞涨", 5, "bonus",
         "季报营收/利润超预期 ≥ 10% 但股价 1 个月涨幅 < 增长幅度"),
        ("peg_high", "PEG > 1.5 反转预警", -12, "penalty",
         "估值开始透支未来增长"),
        ("insider_sell", "高位机构减持", -8, "penalty",
         "PE 5y >70% 分位时,大股东 / 长期机构减持 ≥1% 流通股"),
    ]:
        # PEG > 1.5 自动判断
        if key == "peg_high":
            peg = m.get("peg_lixinger")
            if peg is None:
                pe = m.get("pe_ttm"); cagr = m.get("rev_cagr_5y")
                if pe and cagr and cagr > 0:
                    peg = pe / (cagr * 100)
            triggered = (peg or 0) > 1.5
            out.append(AdjustItem(key, label, delta if triggered else 0,
                                    triggered, polarity,
                                    f"PEG {peg:.2f}" if peg else hint))
        else:
            flag = bool(manual.get(f"adj_{key}"))
            out.append(AdjustItem(key, label, delta if flag else 0,
                                    flag, polarity, hint))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 🚀 FAST GROWER — 快速增长型评分(对应 03_快速增长型_ABCD评估.md)
# ═══════════════════════════════════════════════════════════════════════


def _fast_company(m: dict, manual: dict) -> tuple[list[ScoreItem], list[AdjustItem]]:
    """快速"好公司"评分:7 项 = 50 + 30 + 20 = 100 分。"""
    items: list[ScoreItem] = []

    # 1. 增长动能与质量(50)
    # 1.1 3y 营收 CAGR(25)
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    if cagr is None:
        items.append(_missing("rev_cagr", "营收 3y CAGR", 25, "cagr"))
    else:
        pct = cagr * 100
        if pct >= 35:
            sc, lab = 25, f"{pct:.1f}% ≥ 35%(超高速)"
        elif pct >= 25:
            sc, lab = 20, f"{pct:.1f}% 高速"
        elif pct >= 20:
            sc, lab = 15, f"{pct:.1f}% 快速"
        else:
            sc, lab = 0, f"{pct:.1f}% < 20%(不属快速类)"
        items.append(ScoreItem("rev_cagr", "营收 3y CAGR", sc, 25,
                                "auto", lab, raw_value=pct))

    # 1.2 增长连续性(15)— 用最新季 YoY
    yoy = m.get("rev_yoy_recent")
    if yoy is None:
        items.append(_missing("growth_continuity", "增长连续性", 15, "rev_yoy"))
    else:
        pct = yoy * 100
        if pct >= 20:
            sc, lab = 15, f"最新 YoY {pct:.1f}% ≥ 20%"
        elif pct >= 10:
            sc, lab = 10, f"最新 YoY {pct:.1f}% 偏弱"
        else:
            sc, lab = 3, f"最新 YoY {pct:.1f}% 已显著放缓"
        items.append(ScoreItem("growth_continuity", "增长连续性(单季 YoY)", sc, 15,
                                "auto", lab, raw_value=pct))

    # 1.3 市场空间/份额(10)— 用 CAGR 强度做"还在抢份额"的代理
    cagr_pct = (cagr or 0) * 100
    yoy_pct = ((m.get("rev_yoy_recent") or 0) * 100)
    manual_v = manual.get("market_space")
    if manual_v is not None:
        v = max(0, min(10, float(manual_v)))
        items.append(ScoreItem("market_space", "市场空间/份额",
                                v, 10, "manual", f"用户评分 {v:.0f}/10"))
    else:
        # 代理:CAGR ≥40% + 单季 YoY ≥30% → 蓝海前 10
        # CAGR 25-40% + YoY 20-30% → 主战场 6-8
        # CAGR <20% → 已饱和 2
        if cagr_pct >= 40 and yoy_pct >= 30:
            v, reason = 9, f"CAGR {cagr_pct:.0f}% + YoY {yoy_pct:.0f}%(蓝海高速扩张)"
        elif cagr_pct >= 30:
            v, reason = 7, f"CAGR {cagr_pct:.0f}%(主战场扩张)"
        elif cagr_pct >= 20:
            v, reason = 5, f"CAGR {cagr_pct:.0f}%(已切入但成熟中)"
        else:
            v, reason = 3, f"CAGR {cagr_pct:.0f}%(可能已饱和)"
        items.append(ScoreItem("market_space", "市场空间/份额",
                                v, 10, "auto",
                                f"代理估算 {v}/10:{reason} · 用户可调整",
                                raw_value=cagr_pct))

    # 2. 商业模式与壁垒(30)— 用 ROE + 毛利率领先做代理
    roe = m.get("roe") or 0
    roe_pct = roe * 100 if roe < 1 else roe
    gm_lead = m.get("gross_margin_vs_industry_pp") or 0

    # 2.1 盈利模式可复制性(15)— ROE 持续高 + CAGR 高 = 验证有效
    manual_v = manual.get("model_replicability")
    if manual_v is not None:
        v = max(0, min(15, float(manual_v)))
        items.append(ScoreItem("model_replicability", "盈利模式可复制性",
                                v, 15, "manual", f"用户评分 {v:.0f}/15"))
    else:
        if roe_pct >= 18 and cagr_pct >= 25:
            v, reason = 13, f"ROE {roe_pct:.1f}% + CAGR {cagr_pct:.0f}%(模式已验证且持续放大)"
        elif roe_pct >= 15 and cagr_pct >= 20:
            v, reason = 10, f"ROE {roe_pct:.1f}% + CAGR {cagr_pct:.0f}%(模式有效)"
        elif roe_pct >= 10:
            v, reason = 6, f"ROE {roe_pct:.1f}%(模式存在但赢面待验证)"
        else:
            v, reason = 3, f"ROE {roe_pct:.1f}%(模式赢面弱)"
        items.append(ScoreItem("model_replicability", "盈利模式可复制性",
                                v, 15, "auto",
                                f"代理估算 {v}/15:{reason} · 用户可调整",
                                raw_value=roe_pct))

    # 2.2 竞争优势/护城河(15)— ROE 高(资本效率)+ 毛利率领先 + CAGR 高
    manual_v = manual.get("moat")
    if manual_v is not None:
        v = max(0, min(15, float(manual_v)))
        items.append(ScoreItem("moat", "竞争优势(护城河)",
                                v, 15, "manual", f"用户评分 {v:.0f}/15"))
    else:
        score = 0
        reasons = []
        if roe_pct >= 20:
            score += 5; reasons.append(f"ROE {roe_pct:.1f}% 极强")
        elif roe_pct >= 15:
            score += 3; reasons.append(f"ROE {roe_pct:.1f}% 强")
        if gm_lead >= 5:
            score += 5; reasons.append(f"毛利率领先 {gm_lead:.1f}pp")
        elif gm_lead >= 0:
            score += 2; reasons.append(f"毛利率与行业持平")
        if cagr_pct >= 30:
            score += 4; reasons.append(f"CAGR {cagr_pct:.0f}% 持续抢份额")
        elif cagr_pct >= 20:
            score += 2; reasons.append(f"CAGR {cagr_pct:.0f}%")
        score = min(15, score)
        reason_str = " + ".join(reasons) if reasons else "无明显护城河信号"
        items.append(ScoreItem("moat", "竞争优势(护城河)",
                                score, 15, "auto",
                                f"代理估算 {score}/15:{reason_str} · 用户可调整(专利数等需手补)",
                                raw_value=score))

    # 3. 财务安全(20)
    # 3.1 资产负债率(10) — 林奇铁律 < 40%
    debt = m.get("debt_ratio")
    if debt is None:
        items.append(_missing("debt_ratio", "资产负债率", 10, "debt"))
    else:
        pct = debt * 100 if debt < 1 else debt
        if pct < 30:
            sc, lab = 10, f"{pct:.1f}% < 30%(优秀)"
        elif pct < 40:
            sc, lab = 7, f"{pct:.1f}% < 40%(林奇铁律)"
        elif pct < 50:
            sc, lab = 4, f"{pct:.1f}% 偏高"
        else:
            sc, lab = 0, f"{pct:.1f}% > 50%(高度风险)"
        items.append(ScoreItem("debt_ratio", "资产负债率", sc, 10,
                                "auto", lab, raw_value=pct))

    # 3.2 经营现金流(10)
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is None:
        items.append(_missing("cfo", "现金流状况", 10, "cfo_to_ni"))
    else:
        if cfo_ni > 0.5:
            sc, lab = 10, f"CFO/NI {cfo_ni:.2f}(持续为正)"
        elif cfo_ni > 0:
            sc, lab = 6, f"CFO/NI {cfo_ni:.2f} 基本持平"
        elif cfo_ni > -0.05:
            sc, lab = 3, f"CFO/NI {cfo_ni:.2f} 负但可控"
        else:
            sc, lab = 0, f"CFO/NI {cfo_ni:.2f} 大幅为负"
        items.append(ScoreItem("cfo", "经营现金流", sc, 10,
                                "auto", lab, raw_value=cfo_ni))

    return items, _fast_adjusts(m, manual)


def _fast_adjusts(m: dict, manual: dict) -> list[AdjustItem]:
    """快速好公司调整因子(±15,6 项)。"""
    out: list[AdjustItem] = []
    for key, label, delta, polarity, hint in [
        ("growth_acc", "增长加速", 8, "bonus",
         "最新季营收/盈利环比加速(如 25%→40%+),且可持续"),
        ("cross_validate", "跨界成功验证", 5, "bonus",
         "新区域 / 新产品线首季数据大幅超预期"),
        ("tech_breakthrough", "新产品/技术突破", 3, "bonus",
         "革命性产品或关键专利,可能开辟新增长曲线"),
        ("growth_decel", "增长失速", -15, "penalty",
         "连续 2 季营收增速下滑 >10pp 或利润下滑 >15pp"),
        ("efficiency_drop", "单店/单模型效率恶化", -10, "penalty",
         "新业务 ROI/坪效持续低于成熟业务"),
        ("concentration", "客户/产品过度集中", -8, "penalty",
         "单一客户/产品收入占比 >40% 且有流失风险"),
    ]:
        flag = bool(manual.get(f"adj_{key}"))
        out.append(AdjustItem(key, label, delta if flag else 0,
                                flag, polarity, hint))
    return out


def _fast_price(m: dict, manual: dict) -> tuple[list[ScoreItem], list[AdjustItem]]:
    """快速"好价格"评分:4 项 = 70 + 30 = 100 分。"""
    items: list[ScoreItem] = []

    # 1. 增长估值锚(70)
    # 1.1 PEG(45)— 快速类容忍度更高
    peg = m.get("peg_lixinger")
    if peg is None:
        pe = m.get("pe_ttm")
        cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
        if pe and cagr and cagr > 0:
            peg = pe / (cagr * 100)
    if peg is None:
        items.append(_missing("peg", "PEG 估值", 45, "PE / CAGR"))
    else:
        if peg <= 1.0:
            sc, lab = 45, f"PEG {peg:.2f} ≤ 1.0(甜蜜区)"
        elif peg <= 1.3:
            sc, lab = 35, f"PEG {peg:.2f} 合理"
        elif peg <= 1.7:
            sc, lab = 20, f"PEG {peg:.2f} 偏贵"
        elif peg <= 2.0:
            sc, lab = 5, f"PEG {peg:.2f} 接近泡沫"
        else:
            sc, lab = 0, f"PEG {peg:.2f} > 2.0(泡沫警戒)"
        items.append(ScoreItem("peg", "PEG 估值", sc, 45,
                                "auto", lab, raw_value=peg))

    # 1.2 PS 估值辅助(25)— 行业 PS 数据缺,改用自身 PS 5y 分位代理
    ps_pct = m.get("ps_5y_pct")
    manual_v = manual.get("ps_vs_industry")
    if manual_v is not None:
        v = max(0, min(25, float(manual_v)))
        items.append(ScoreItem("ps_vs_industry", "PS vs 行业",
                                v, 25, "manual", f"用户评分 {v:.0f}/25"))
    elif ps_pct is not None:
        p = ps_pct * 100
        # 用 自身 PS 5y 分位 代理 行业对比(低分位 ≈ 估值便宜)
        if p < 20:
            v, lab = 25, f"PS 5y 分位 {p:.0f}%(自身历史低位)"
        elif p < 40:
            v, lab = 18, f"PS 5y 分位 {p:.0f}%(偏低)"
        elif p < 60:
            v, lab = 10, f"PS 5y 分位 {p:.0f}%(中位)"
        else:
            v, lab = 3, f"PS 5y 分位 {p:.0f}%(偏高)"
        items.append(ScoreItem("ps_vs_industry", "PS vs 行业",
                                v, 25, "auto",
                                f"代理估算 {v}/25:{lab}(行业 PS 数据缺,用自身分位代理)",
                                raw_value=p))
    else:
        items.append(_missing("ps_vs_industry", "PS vs 行业", 25,
                                "PS-TTM 时序"))

    # 2. 相对与情绪(30)
    # 2.1 PE 3y 历史分位(15)— 复用 10y 数据
    pct = m.get("pe_pct_10y")
    if pct is None:
        items.append(_missing("pe_pct", "PE 历史分位", 15, "pe_pct_10y"))
    else:
        p = pct * 100 if pct < 1 else pct
        if p < 30:
            sc, lab = 15, f"{p:.0f}% 分位 — 低估"
        elif p < 60:
            sc, lab = 10, f"{p:.0f}% 中位"
        elif p < 90:
            sc, lab = 5, f"{p:.0f}% 偏高"
        else:
            sc, lab = 0, f"{p:.0f}% 历史高位"
        items.append(ScoreItem("pe_pct", "PE 历史分位", sc, 15,
                                "auto", lab, raw_value=p))

    # 2.2 机构关注度(15)— 用市值规模 + PE 历史分位代理"冷门程度"
    manual_v = manual.get("institution_mood")
    if manual_v is not None:
        v = max(0, min(15, float(manual_v)))
        items.append(ScoreItem("institution_mood", "机构关注度",
                                v, 15, "manual", f"用户评分 {v:.0f}/15"))
    else:
        # 代理逻辑:
        # PE 5y 分位 < 30% → 市场冷门(机构未追捧)= 高分
        # PE 5y 分位 > 70% → 市场热门 = 低分
        # 中位 → 中性 7-8 分
        pct = m.get("pe_pct_10y")
        if pct is None:
            v, reason = 7, "无 PE 分位数据,默认中性"
        else:
            p = pct * 100 if pct < 1 else pct
            if p < 30:
                v, reason = 12, f"PE 5y 分位 {p:.0f}%(市场冷门 → 机构未追捧)"
            elif p < 60:
                v, reason = 8, f"PE 5y 分位 {p:.0f}%(中性)"
            elif p < 85:
                v, reason = 5, f"PE 5y 分位 {p:.0f}%(机构积极)"
            else:
                v, reason = 2, f"PE 5y 分位 {p:.0f}%(过度热门)"
        items.append(ScoreItem("institution_mood", "机构关注度",
                                v, 15, "auto",
                                f"代理估算 {v}/15:{reason} · 真机构持股数据待接入",
                                raw_value=v))

    return items, _fast_price_adjusts(m, manual)


def _fast_price_adjusts(m: dict, manual: dict) -> list[AdjustItem]:
    """快速好价格调整(±10/12,4 项)。"""
    out: list[AdjustItem] = []
    for key, label, delta, polarity, hint in [
        ("non_fund_panic", "非基本面错杀回调", 10, "bonus",
         "1 个月内跌 >30%,基本面未变"),
        ("valuation_lag", "估值滞后于业绩", 5, "bonus",
         "业绩超预期但股价涨幅显著低于盈利增幅"),
        ("market_frenzy", "市场狂热与过度交易", -12, "penalty",
         "股价 1 个月涨 >50% + 成交量历史天量 + 媒体狂吹"),
        ("insider_sell", "内部人/机构高位减持", -8, "penalty",
         "PE > 历史 80% 分位时大股东减持"),
    ]:
        flag = bool(manual.get(f"adj_{key}"))
        out.append(AdjustItem(key, label, delta if flag else 0,
                                flag, polarity, hint))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 🔄 CYCLICAL — 周期型评分(对应 04_周期型_ABCD评估.md)
# ═══════════════════════════════════════════════════════════════════════


def _cyclical_company(m: dict, manual: dict) -> tuple[list[ScoreItem], list[AdjustItem]]:
    """周期"好公司"评分:7 项 = 50 + 35 + 15 = 100 分。"""
    items: list[ScoreItem] = []

    # 1.1 偿债安全边际(25)— 用 CFO/总负债 代理(现金数据缺,CFO 是常用替代)
    cfo_to_debt = m.get("cfo_to_total_debt")
    manual_v = manual.get("debt_safety")
    if manual_v is not None:
        v = max(0, min(25, float(manual_v)))
        items.append(ScoreItem("debt_safety", "偿债安全边际",
                                v, 25, "manual", f"用户评分 {v:.0f}/25"))
    elif cfo_to_debt is not None:
        if cfo_to_debt > 0.4:
            v, lab = 25, f"CFO/总负债 {cfo_to_debt:.2f} >0.4(韧性强)"
        elif cfo_to_debt > 0.3:
            v, lab = 18, f"CFO/总负债 {cfo_to_debt:.2f} 偏好"
        elif cfo_to_debt > 0.2:
            v, lab = 10, f"CFO/总负债 {cfo_to_debt:.2f} 中等"
        elif cfo_to_debt > 0.1:
            v, lab = 5, f"CFO/总负债 {cfo_to_debt:.2f} 偏弱"
        else:
            v, lab = 0, f"CFO/总负债 {cfo_to_debt:.2f} 紧张"
        items.append(ScoreItem("debt_safety", "偿债安全边际",
                                v, 25, "auto",
                                f"代理估算 {v}/25:{lab}(用 CFO/总负债 代理 (现金+CFO)/总债务)",
                                raw_value=cfo_to_debt))
    else:
        items.append(_missing("debt_safety", "偿债安全边际", 25,
                                "CFO 或总负债"))

    # 1.2 CFO/NI 自动
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is None:
        items.append(_missing("cfo_quality", "CFO 质量(低谷期)", 15, "cfo_to_ni"))
    else:
        if cfo_ni >= 1.0:
            sc, lab = 15, f"CFO/NI {cfo_ni:.2f} ≥ 1.0(扛得住低谷)"
        elif cfo_ni >= 0.5:
            sc, lab = 8, f"CFO/NI {cfo_ni:.2f} 偶弱"
        else:
            sc, lab = 0, f"CFO/NI {cfo_ni:.2f} 常负"
        items.append(ScoreItem("cfo_quality", "CFO/NI(低谷期)", sc, 15,
                                "auto", lab, raw_value=cfo_ni))

    # 1.3 债务结构(10)— 流动负债 / 总负债 代理短期负债占比
    short_ratio = m.get("short_debt_ratio")
    manual_v = manual.get("debt_structure")
    if manual_v is not None:
        v = max(0, min(10, float(manual_v)))
        items.append(ScoreItem("debt_structure", "债务结构与成本",
                                v, 10, "manual", f"用户评分 {v:.0f}/10"))
    elif short_ratio is not None:
        p = short_ratio * 100
        if p < 30:
            v, lab = 10, f"流动负债占比 {p:.0f}%(短债低,稳)"
        elif p < 50:
            v, lab = 6, f"流动负债占比 {p:.0f}%(中性)"
        else:
            v, lab = 2, f"流动负债占比 {p:.0f}%(短债高,压力)"
        items.append(ScoreItem("debt_structure", "债务结构与成本",
                                v, 10, "auto",
                                f"代理估算 {v}/10:{lab}(用流动负债比代理短期债务比)",
                                raw_value=p))
    else:
        items.append(_missing("debt_structure", "债务结构与成本", 10,
                                "流动负债/总负债"))

    # 2.1 成本竞争力(20)— 毛利率 vs 行业 代理
    diff_pp = m.get("gross_margin_vs_industry_pp")
    manual_v = manual.get("cost_competitive")
    if manual_v is not None:
        v = max(0, min(20, float(manual_v)))
        items.append(ScoreItem("cost_competitive", "成本竞争力",
                                v, 20, "manual", f"用户评分 {v:.0f}/20"))
    elif diff_pp is not None:
        if diff_pp >= 8:
            v, lab = 20, f"毛利率领先行业 {diff_pp:.1f}pp(成本前 20%)"
        elif diff_pp >= 3:
            v, lab = 12, f"毛利率领先行业 {diff_pp:.1f}pp(前 40%)"
        elif diff_pp >= -2:
            v, lab = 8, f"毛利率与行业持平 {diff_pp:+.1f}pp"
        else:
            v, lab = 2, f"毛利率落后 {diff_pp:.1f}pp(成本高企)"
        items.append(ScoreItem("cost_competitive", "成本竞争力",
                                v, 20, "auto",
                                f"代理估算 {v}/20:{lab}(用毛利率行业差代理单位现金成本)",
                                raw_value=diff_pp))
    else:
        # 行业毛利率数据缺,fallback 用 ROE 代理(高 ROE = 通常成本优势)
        roe = (m.get("roe") or 0)
        roe_pct = roe * 100 if roe < 1 else roe
        if roe_pct >= 18:
            v, lab = 14, f"ROE {roe_pct:.1f}% ≥18%(估算成本前 30%)"
        elif roe_pct >= 12:
            v, lab = 9, f"ROE {roe_pct:.1f}%(估算成本中前)"
        elif roe_pct >= 8:
            v, lab = 5, f"ROE {roe_pct:.1f}%(估算成本中等)"
        else:
            v, lab = 0, f"ROE {roe_pct:.1f}%(成本可能偏高)"
        items.append(ScoreItem("cost_competitive", "成本竞争力",
                                v, 20, "auto",
                                f"代理估算 {v}/20:{lab}(行业毛利率数据缺,用 ROE 二级代理)",
                                raw_value=roe_pct))

    # 2.2 市场份额(15)— 用 ROE 高 + 毛利率领先 + 营收 CAGR 稳定 综合代理"行业地位"
    manual_v = manual.get("market_share")
    if manual_v is not None:
        v = max(0, min(15, float(manual_v)))
        items.append(ScoreItem("market_share", "市场份额与地位",
                                v, 15, "manual", f"用户评分 {v:.0f}/15"))
    else:
        roe = (m.get("roe") or 0)
        roe_pct = roe * 100 if roe < 1 else roe
        gm_lead = m.get("gross_margin_vs_industry_pp") or 0
        cagr_5y = (m.get("rev_cagr_5y") or 0) * 100
        score = 0
        reasons = []
        if roe_pct >= 15:
            score += 6; reasons.append(f"ROE {roe_pct:.1f}% 强")
        elif roe_pct >= 10:
            score += 3; reasons.append(f"ROE {roe_pct:.1f}% 中")
        if gm_lead >= 5:
            score += 5; reasons.append(f"毛利领先 {gm_lead:.1f}pp")
        elif gm_lead >= 0:
            score += 2; reasons.append(f"毛利持平")
        if cagr_5y >= 10:
            score += 4; reasons.append(f"5y CAGR {cagr_5y:.0f}% 稳定增长")
        elif cagr_5y >= 0:
            score += 1; reasons.append(f"5y CAGR {cagr_5y:.0f}%")
        score = min(15, score)
        reason_str = " + ".join(reasons) if reasons else "无明显地位优势信号"
        items.append(ScoreItem("market_share", "市场份额与地位",
                                score, 15, "auto",
                                f"代理估算 {score}/15:{reason_str}",
                                raw_value=score))

    # 3.1 低谷期战略(10)— 用历史 ROE 稳定性 / CFO 持续性 推断管理层是否扛过低谷
    manual_v = manual.get("low_cycle_strategy")
    if manual_v is not None:
        v = max(0, min(10, float(manual_v)))
        items.append(ScoreItem("low_cycle_strategy", "低谷期战略",
                                v, 10, "manual", f"用户评分 {v:.0f}/10"))
    else:
        cv = m.get("net_margin_5y_cv")
        cfo_ni = m.get("cfo_to_ni") or 0
        if cv is not None and cv < 0.3 and cfo_ni >= 1.0:
            v, lab = 9, f"5y 净利率 CV {cv:.2f} 稳 + CFO/NI {cfo_ni:.2f}(经历过低谷未变形)"
        elif cv is not None and cv < 0.5 and cfo_ni > 0:
            v, lab = 6, f"5y 净利率 CV {cv:.2f} 中等 + CFO 转正(挺过来了)"
        elif cv is not None and cv < 0.8:
            v, lab = 4, f"5y 净利率 CV {cv:.2f}(波动大,韧性中等)"
        else:
            v, lab = 2, "历史波动大,韧性弱(默认中性偏低)"
        items.append(ScoreItem("low_cycle_strategy", "低谷期战略",
                                v, 10, "auto",
                                f"代理估算 {v}/10:{lab}(管理层历史事件待用户补)",
                                raw_value=v))

    # 3.2 资本开支纪律(5)— 暂用 CFO/NI 持续性代理(纪律 = 不烧现金扩张)
    manual_v = manual.get("capex_discipline")
    if manual_v is not None:
        v = max(0, min(5, float(manual_v)))
        items.append(ScoreItem("capex_discipline", "资本开支纪律",
                                v, 5, "manual", f"用户评分 {v:.0f}/5"))
    else:
        cfo_ni = m.get("cfo_to_ni") or 0
        debt = m.get("debt_ratio") or 1
        debt_pct = debt * 100 if debt < 1 else debt
        if cfo_ni >= 1.0 and debt_pct < 50:
            v, lab = 4, f"CFO/NI {cfo_ni:.2f} + 负债 {debt_pct:.0f}%(纪律好)"
        elif cfo_ni >= 0.7:
            v, lab = 3, f"CFO/NI {cfo_ni:.2f}(中等纪律)"
        else:
            v, lab = 1, f"CFO/NI {cfo_ni:.2f}(可能顺周期烧钱)"
        items.append(ScoreItem("capex_discipline", "资本开支纪律",
                                v, 5, "auto",
                                f"代理估算 {v}/5:{lab}(精确反周期判断需 capex 时序)",
                                raw_value=v))

    return items, _cyclical_adjusts(m, manual)


def _cyclical_adjusts(m: dict, manual: dict) -> list[AdjustItem]:
    """周期好公司调整(±10,4 项,全主观)。"""
    out: list[AdjustItem] = []
    for key, label, delta, polarity, hint in [
        ("debt_optimize", "困境中优化资负表", 8, "bonus",
         "下行期成功降低杠杆"),
        ("cheap_long_funding", "获得低成本长期资金", 5, "bonus",
         "低迷期以极低利率获长期贷款"),
        ("peak_acq", "景气高点巨额并购", -15, "penalty",
         "在行业 PE 创周期新高时高溢价并购"),
        ("funding_dry", "关键融资渠道枯竭", -10, "penalty",
         "授信被削减或评级下调"),
    ]:
        flag = bool(manual.get(f"adj_{key}"))
        out.append(AdjustItem(key, label, delta if flag else 0,
                                flag, polarity, hint))
    return out


def _cyclical_price(m: dict, manual: dict) -> tuple[list[ScoreItem], list[AdjustItem]]:
    """周期"好价格"评分:5 项 = 60 + 40 = 100 分。

    注:周期股用 PB(不是 PE)。文档强调"用 PB 不用 PE"。
    """
    items: list[ScoreItem] = []

    # 1. 行业景气度(60)— 行业大宗商品 / 库存 / 产能 数据库无,用公司层信号代理
    # 1.1 产品价格分位(30)— 用 公司毛利率 5y 分位 代理(成本贵→毛利低,产品价低也会传到毛利)
    # 因数据有限,fallback 用公司 PE 5y 分位反向(高 PE 通常意味着行业低谷亏损 → 周期底部)
    pe_pct = m.get("pe_pct_10y")
    manual_v = manual.get("product_price_pct")
    if manual_v is not None:
        v = max(0, min(30, float(manual_v)))
        items.append(ScoreItem("product_price_pct", "产品价格 5y 分位",
                                v, 30, "manual", f"用户评分 {v:.0f}/30"))
    elif pe_pct is not None:
        # 周期股 PE 反向:PE 高位时常是行业低谷(亏损或微利)→ 产品价低 → 这里给高分
        # PE 低位时常是行业高峰 → 产品价高 → 这里给低分
        p = pe_pct * 100 if pe_pct < 1 else pe_pct
        if p >= 80:
            v, lab = 22, f"PE 5y {p:.0f}% 历史高位(周期股反向 → 产品价底部区域)"
        elif p >= 60:
            v, lab = 16, f"PE 5y {p:.0f}%(可能复苏初期)"
        elif p >= 40:
            v, lab = 10, f"PE 5y {p:.0f}%(周期中段)"
        else:
            v, lab = 4, f"PE 5y {p:.0f}% 低位(周期股反向 → 产品价高位)"
        items.append(ScoreItem("product_price_pct", "产品价格 5y 分位",
                                v, 30, "auto",
                                f"代理估算 {v}/30:{lab}(周期股 PE 反向解读 — 行业大宗价格数据待补)",
                                raw_value=p))
    else:
        items.append(_missing("product_price_pct", "产品价格 5y 分位", 30,
                                "PE 时序"))

    # 1.2 行业库存与产能(20)— 用公司营收 YoY 代理(YoY 转正 = 库存出清)
    yoy = m.get("rev_yoy_recent")
    manual_v = manual.get("industry_inventory")
    if manual_v is not None:
        v = max(0, min(20, float(manual_v)))
        items.append(ScoreItem("industry_inventory", "行业库存与产能",
                                v, 20, "manual", f"用户评分 {v:.0f}/20"))
    elif yoy is not None:
        y = yoy * 100
        if y > 10:
            v, lab = 16, f"营收 YoY {y:.1f}%(行业需求回暖,库存出清)"
        elif y > 0:
            v, lab = 12, f"营收 YoY {y:+.1f}%(初步回暖)"
        elif y > -10:
            v, lab = 6, f"营收 YoY {y:+.1f}%(仍承压)"
        else:
            v, lab = 2, f"营收 YoY {y:+.1f}%(行业仍恶化)"
        items.append(ScoreItem("industry_inventory", "行业库存与产能",
                                v, 20, "auto",
                                f"代理估算 {v}/20:{lab}(行业库存数据待补,用公司营收 YoY 代理)",
                                raw_value=y))
    else:
        items.append(_missing("industry_inventory", "行业库存与产能", 20,
                                "rev_yoy"))

    # 1.3 行业资本开支(10)— 数据库无,默认中性 5(用户可调)
    manual_v = manual.get("industry_capex")
    if manual_v is not None:
        v = max(0, min(10, float(manual_v)))
        items.append(ScoreItem("industry_capex", "行业资本开支",
                                v, 10, "manual", f"用户评分 {v:.0f}/10"))
    else:
        items.append(ScoreItem("industry_capex", "行业资本开支",
                                5, 10, "auto",
                                "默认中性 5/10(行业产能扩张计划数据需手补)",
                                raw_value=5))

    # 2. 估值与情绪(40)
    # 2.1 PB 5y 分位(20)— 用 pe_pct_10y 做近似(理想用 PB 自身分位,后续可补)
    pct = m.get("pe_pct_10y")
    if pct is None:
        items.append(_missing("pb_pct", "PB 5y 分位", 20, "pb_pct(暂用 pe_pct 近似)"))
    else:
        p = pct * 100 if pct < 1 else pct
        if p < 10:
            sc, lab = 20, f"{p:.0f}% 极低(底部)"
        elif p < 30:
            sc, lab = 15, f"{p:.0f}% 偏低"
        elif p < 50:
            sc, lab = 8, f"{p:.0f}% 中位"
        else:
            sc, lab = 0, f"{p:.0f}% 高位"
        items.append(ScoreItem("pb_pct", "PB 历史分位(用 PE 近似)", sc, 20,
                                "auto", lab + " · 数据待替换为 PB 分位",
                                raw_value=p))

    # 2.2 市场情绪(20)— 用 PE 5y 分位 + 公司层 PB 分位 综合代理"市场关注度"
    manual_v = manual.get("institution_mood")
    if manual_v is not None:
        v = max(0, min(20, float(manual_v)))
        items.append(ScoreItem("institution_mood", "机构关注度",
                                v, 20, "manual", f"用户评分 {v:.0f}/20"))
    else:
        # 周期股冷门(机构无人问)= 高分,热门 = 低分
        # PE 高(行业低谷)+ PB 低 = 经典冷门 = 高分
        pct = m.get("pe_pct_10y")
        if pct is None:
            v, reason = 10, "无 PE 分位数据,默认中性"
        else:
            p = pct * 100 if pct < 1 else pct
            if p >= 70 or p < 20:
                # 周期反向:PE 极高(亏损低谷) 或 极低(暴涨期顶部)
                if p >= 70:
                    v, reason = 16, f"PE 分位 {p:.0f}% 历史高位(周期低谷 → 机构离场 = 冷门)"
                else:
                    v, reason = 4, f"PE 分位 {p:.0f}% 历史低位(周期高峰 → 机构追捧 = 热门)"
            elif p >= 50:
                v, reason = 12, f"PE 分位 {p:.0f}%(关注度偏低)"
            else:
                v, reason = 8, f"PE 分位 {p:.0f}%(关注度偏高)"
        items.append(ScoreItem("institution_mood", "机构关注度",
                                v, 20, "auto",
                                f"代理估算 {v}/20:{reason} · 真机构持股数据待接入",
                                raw_value=v))

    return items, _cyclical_price_adjusts(m, manual)


def _cyclical_price_adjusts(m: dict, manual: dict) -> list[AdjustItem]:
    """周期好价格调整(±10/15,4 项)。"""
    out: list[AdjustItem] = []
    for key, label, delta, polarity, hint in [
        ("policy_stim", "宏观政策强刺激", 10, "bonus",
         "强刺激政策出台,股价尚未反应"),
        ("standard_bankruptcy", "行业标志性破产/整合", 8, "bonus",
         "主要竞争对手破产,供给收缩"),
        ("media_consensus", "媒体分析师集体唱多", -15, "penalty",
         "'超级周期到来 / 这次不一样'类口号出现"),
        ("price_disconnect", "产品价创新高股价滞涨", -10, "penalty",
         "产品价超上轮顶峰但股价乏力,盈利无法传导"),
    ]:
        flag = bool(manual.get(f"adj_{key}"))
        out.append(AdjustItem(key, label, delta if flag else 0,
                                flag, polarity, hint))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 主 API
# ═══════════════════════════════════════════════════════════════════════


def _manual_or_missing(key: str, label: str, max_score: float,
                       manual_value: float | int | None,
                       *, hint: str = "") -> ScoreItem:
    """如果用户填了 manual_value(0 ~ max_score)就用,否则记 missing。"""
    if manual_value is None:
        return ScoreItem(
            key=key, label=label, score=0, max_score=max_score,
            source="missing",
            detail=f"⚠️ 需手动评分:{hint}",
        )
    v = max(0, min(max_score, float(manual_value)))
    return ScoreItem(
        key=key, label=label, score=v, max_score=max_score,
        source="manual",
        detail=f"用户评分 {v:.0f}/{max_score:.0f} · {hint}",
    )


_DISPATCH: dict[str, dict[str, Callable]] = {
    "stalwart": {
        "company": _stalwart_company,
        "price":   _stalwart_price,
        "name_cn": "稳健增长型",
    },
    "fast_grower": {
        "company": _fast_company,
        "price":   _fast_price,
        "name_cn": "快速增长型",
    },
    "cyclical": {
        "company": _cyclical_company,
        "price":   _cyclical_price,
        "name_cn": "周期型",
    },
}


def applicable(cls_id: str) -> bool:
    """该类型是否有 ABCD 评估实现。"""
    return cls_id in _DISPATCH


def score_abcd(ticker: str, m: dict, cls_id: str,
               manual: dict | None = None) -> AbcdResult | None:
    """主入口:评估 (公司质量 ABCD, 价格吸引力 12345)。

    Args:
        ticker: 股票代码
        m: 来自 lynch_classifier.load_metrics_from_db 的指标 dict
        cls_id: stalwart / fast_grower / cyclical(其它返回 None)
        manual: 主观评分输入,key 形如:
                ─ 评分项:{"market_space": 7, "moat": 12, ...}(0 ~ max_score)
                ─ 调整因子:{"adj_growth_acc": True, "adj_growth_decel": False, ...}

    Returns:
        AbcdResult,若类型不适用返回 None。
    """
    if cls_id not in _DISPATCH:
        return None
    manual = manual or {}
    spec = _DISPATCH[cls_id]

    # 公司质量
    c_items, c_adjusts = spec["company"](m, manual)
    c_base = sum(it.score for it in c_items)
    c_adj_total = sum(a.delta for a in c_adjusts)
    c_final = c_base + c_adj_total
    c_grade = _grade_company(c_final)

    # 价格吸引力
    p_items, p_adjusts = spec["price"](m, manual)
    p_base = sum(it.score for it in p_items)
    p_adj_total = sum(a.delta for a in p_adjusts)
    p_final = p_base + p_adj_total
    p_grade = _grade_price(p_final)

    decision, color = MATRIX[c_grade][p_grade]

    return AbcdResult(
        cls_id=cls_id,
        cls_name=spec["name_cn"],
        company_items=c_items,
        company_adjusts=c_adjusts,
        company_base_score=c_base,
        company_adjust_total=c_adj_total,
        company_final_score=c_final,
        company_grade=c_grade,
        company_max=sum(it.max_score for it in c_items),
        price_items=p_items,
        price_adjusts=p_adjusts,
        price_base_score=p_base,
        price_adjust_total=p_adj_total,
        price_final_score=p_final,
        price_grade=p_grade,
        price_max=sum(it.max_score for it in p_items),
        matrix_decision=decision,
        matrix_color=color,
    )


__all__ = [
    "ScoreItem", "AdjustItem", "AbcdResult",
    "score_abcd", "applicable", "MATRIX",
    "_grade_company", "_grade_price",   # 主次合并用
]
