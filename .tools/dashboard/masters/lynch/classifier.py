"""彼得林奇 6 类分类器(A2 + A3)。

林奇《One Up On Wall Street》6 大类:
  1. slow_grower      缓慢增长型 — 大型成熟公司,营收 CAGR 低,股息高
  2. stalwart         稳定增长型 — 大盘消费防御股,CAGR 中等,ROE 稳定
  3. fast_grower      快速增长型 — 中小型,CAGR 高,扩张期
  4. cyclical         周期型     — 行业周期主导(汽车/化工/航空/有色)
  5. asset_play       资产隐蔽型 — 现金/资产/隐蔽业务被低估
  6. turnaround       困境反转型 — 近年盈利大幅下滑但还未出局

判断顺序(优先级):
  cyclical → turnaround → asset_play → fast_grower → stalwart → slow_grower
  即"行业属性 > 困境信号 > 资产 > 增速分级"

输入:
  metrics dict — 至少含
    rev_cagr_5y / rev_cagr_3y     营收复合增速(0.18 = 18%)
    roe                            最新 ROE(0.32 = 32%)
    pe_ttm / pb / market_cap       绝对估值
    cash_to_market_cap             现金/总市值(0.30 = 30%)
    debt_ratio                     资产负债率
    rev_yoy_recent                 最近一期营收同比
    np_yoy_recent                  最近一期净利润同比
    industry_sw_l1                 申万一级
    industry_sw_l2                 申万二级
    dividend_yield                 股息率
    name / ticker                  仅展示用

输出:
  ClassificationResult(
    cls_id='fast_grower',
    cls_name='快速增长型',
    cls_emoji='🚀',
    confidence=0.85,
    reason='营收 5y CAGR 18% > 15% 阈值,ROE 32% > 12%;非周期行业(食品饮料);分到快速增长型。',
    key_metrics={'5y CAGR':'18%', 'ROE':'32%', 'PE-TTM':'21x'},
    notes=['估值 PE 21x 处 10y 9.4% 分位 — 快速增长型中估值合理'],
  )

CLI:
  .venv/bin/python .tools/dashboard/lynch_classifier.py 600519
"""
from __future__ import annotations

import argparse
import functools
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"

# 周期性行业(申万一级)— 林奇判断"周期型"的主依据
# 来源:01_knowledge/03_投资策略与选股/02_彼得林奇投资法/01_六类公司分类法.md
# "汽车、钢铁、航空、化工、航运" + 常见衍生(有色/煤炭/建材/地产)
CYCLICAL_INDUSTRIES = {
    "汽车", "钢铁", "有色金属", "石油石化", "煤炭",
    "建筑材料", "化工", "基础化工",
    "交通运输", "航空", "航运",
    "房地产", "建筑装饰",
}

# 银行/保险:知识库归"传统银行=缓慢增长"。CAGR<10% 时按缓慢,
# 但若 ROE 长期 ≥15% 仍可视为稳健(招商银行/平安等)
FINANCIAL_INDUSTRIES = {"银行", "非银金融", "保险", "证券"}
HOME_APPLIANCE_KEYWORDS = ("家电", "白色家电", "家用电器")


def _is_home_appliance(m: dict[str, Any]) -> bool:
    text = " ".join(str(m.get(k) or "") for k in ("industry_sw_l1", "industry_sw_l2", "industry"))
    return any(k in text for k in HOME_APPLIANCE_KEYWORDS)


@dataclass
class ClassificationResult:
    cls_id: str
    cls_name: str
    cls_emoji: str
    confidence: float
    reason: str
    key_metrics: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # extra:UI 信号位 — 是否金融业 / 行业不完美匹配 / 推荐主次拆分等
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


CLASS_META = {
    "slow_grower":  ("缓慢增长型", "🐢", "成熟大盘股,适合靠股息长期持有"),
    "stalwart":     ("稳定增长型", "🛡️", "消费防御类,在熊市中跑赢市场"),
    "fast_grower":  ("快速增长型", "🚀", "高成长但需警惕估值过高"),
    "cyclical":     ("周期型",     "🔄", "行业周期主导,买入卖出时点最关键"),
    "asset_play":   ("资产隐蔽型", "💰", "市场低估其资产价值,等待催化"),
    "turnaround":   ("困境反转型", "🔧", "重大问题中反转,胜率不高但赔率大"),
}

# A4:每类专属 5 维 schema
# key:对应 compute_lynch_dims 内部分支;label:UI 展示;weight:综合分加权
LYNCH_DIM_SCHEMA: dict[str, list[dict]] = {
    "fast_grower": [
        {"key": "peg",         "label": "PEG (估值/增速)", "weight": 0.25},
        {"key": "rev_growth",  "label": "营收增速",        "weight": 0.20},
        {"key": "np_growth",   "label": "净利增速",        "weight": 0.20},
        {"key": "roe",         "label": "ROE",            "weight": 0.20},
        {"key": "valuation",   "label": "估值合理度",      "weight": 0.15},
    ],
    "stalwart": [
        {"key": "roe_quality", "label": "ROE 质量",       "weight": 0.25},
        {"key": "dividend",    "label": "股息覆盖",        "weight": 0.20},
        {"key": "cfo_quality", "label": "现金流质量",      "weight": 0.20},
        {"key": "valuation",   "label": "估值合理度",      "weight": 0.20},
        {"key": "moat_proxy",  "label": "护城河 (ROE 代理)", "weight": 0.15},
    ],
    "cyclical": [
        {"key": "valuation_pb","label": "估值低位 (PB)",   "weight": 0.30},
        {"key": "leverage",    "label": "杠杆控制",        "weight": 0.20},
        {"key": "cfo",         "label": "现金流",          "weight": 0.20},
        {"key": "rev_growth",  "label": "营收恢复",        "weight": 0.15},
        {"key": "valuation",   "label": "PE 分位低位",     "weight": 0.15},
    ],
    "asset_play": [
        {"key": "cash_to_mc",  "label": "现金/市值",       "weight": 0.30},
        {"key": "valuation_pb","label": "PB 折价",         "weight": 0.25},
        {"key": "dividend",    "label": "股息率",          "weight": 0.15},
        {"key": "moat_proxy",  "label": "资产质量 (ROE)",  "weight": 0.15},
        {"key": "valuation",   "label": "PE 分位",         "weight": 0.15},
    ],
    "turnaround": [
        {"key": "cfo_positive","label": "经营性现金流",     "weight": 0.30},
        {"key": "debt_trend",  "label": "负债可控",        "weight": 0.20},
        {"key": "rev_stabilize","label": "营收企稳",       "weight": 0.20},
        {"key": "roe_floor",   "label": "ROE 触底",        "weight": 0.15},
        {"key": "valuation_pb","label": "安全边际 (低 PB)", "weight": 0.15},
    ],
    "slow_grower": [
        {"key": "dividend",    "label": "股息率",          "weight": 0.30},
        {"key": "roe_quality", "label": "ROE 稳定",        "weight": 0.20},
        {"key": "leverage",    "label": "杠杆控制",        "weight": 0.20},
        {"key": "valuation",   "label": "估值合理度",      "weight": 0.15},
        {"key": "rev_growth",  "label": "营收稳健 (低基数)", "weight": 0.15},
    ],
}


@dataclass
class DimScore:
    """A5:单维度评分明细。每个 attribute 都是可解释的。"""
    key: str
    label: str
    score: float | None              # 0-100;None 表示数据缺失
    badge: str                       # 🟢🟡🔴⚪
    weight: float                    # 该 dim 在综合分中的权重
    inputs: dict[str, str]           # 原始值(展示用,字符串化)
    formula: str                     # 公式说明
    note: str                        # 一句话解读

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label,
            "score": self.score, "badge": self.badge, "weight": self.weight,
            "inputs": dict(self.inputs), "formula": self.formula, "note": self.note,
        }


# ───── A4:维度评分函数 ─────────────────────────────────────────────────

def _clip(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _badge(s: float | None) -> str:
    if s is None:
        return "⚪"
    if s >= 75: return "🟢"
    if s >= 60: return "🟡"
    if s >= 45: return "🟠"
    return "🔴"


def _missing(key: str, label: str, weight: float, what: str) -> DimScore:
    return DimScore(key=key, label=label, score=None, badge="⚪",
                    weight=weight, inputs={"⚠️": what}, formula="—",
                    note=f"数据缺失:{what}")


def _score_peg(m, w):
    """PEG 评分 — 理杏仁口径:PEG = PE-TTM ÷ (净利润 3y CAGR × 100)。

    其中 3y CAGR 用倒数第二份年报作 end(滞后一年保稳定),
    实测美的 14/10.5 = 1.33 ✅ 与理杏仁页面一致。
    """
    pe = m.get("pe_ttm")
    np_yoy = m.get("np_ttm_yoy")          # 百分数 10.5(理杏仁口径=3y CAGR)
    peg_lx = m.get("peg_lixinger")
    if pe is None or np_yoy is None or np_yoy <= 0 or peg_lx is None:
        # 兜底:净利 3y CAGR 不可用时退化到营收 CAGR(标注)
        cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
        if pe is None or cagr is None or cagr <= 0:
            return _missing("peg", "PEG (估值/增速)", w,
                            "PE-TTM 或 净利润 3y CAGR")
        peg = pe / (cagr * 100)
        s = _clip(100 - (peg - 0.5) * 50)
        note = (
            f"营收 CAGR 兜底(净利负增长 {(np_yoy or 0):+.1f}%)"
        )
        return DimScore(
            key="peg", label="PEG (估值/增速)", score=s, badge=_badge(s), weight=w,
            inputs={"PE-TTM": f"{pe:.1f}", "营收CAGR(兜底)": f"{cagr*100:.1f}%",
                    "PEG": f"{peg:.2f}"},
            formula="PEG = PE ÷ (营收CAGR×100) — 兜底,理杏仁口径不可用时",
            note=note,
        )
    peg = peg_lx
    s = _clip(100 - (peg - 0.5) * 50)
    note = "便宜 (PEG<1)" if peg < 1 else "合理 (1-2)" if peg < 2 else "偏贵 (>2)"
    return DimScore(
        key="peg", label="PEG (估值/增速)", score=s, badge=_badge(s), weight=w,
        inputs={"PE-TTM": f"{pe:.1f}", "净利TTM YoY": f"{np_yoy:+.1f}%",
                "PEG": f"{peg:.2f}"},
        formula="PEG = PE-TTM ÷ (净利润 TTM YoY% × 100) · 理杏仁口径",
        note=note,
    )


def _score_rev_growth(m, w):
    cagr = m.get("rev_cagr_3y") or m.get("rev_cagr_5y")
    if cagr is None:
        return _missing("rev_growth", "营收增速", w, "营收 CAGR")
    # 0% → 0; 25% → 100,线性
    s = _clip(cagr * 400)
    return DimScore(
        key="rev_growth", label="营收增速", score=s, badge=_badge(s), weight=w,
        inputs={"3y CAGR": f"{cagr*100:.1f}%"},
        formula="0% → 0,25% → 100,线性映射",
        note=("高速" if cagr >= 0.20 else "稳健" if cagr >= 0.10 else "平淡"),
    )


def _score_np_growth(m, w):
    np = m.get("np_yoy_recent")
    if np is None:
        return _missing("np_growth", "净利增速", w, "净利润 YoY")
    s = _clip(np * 200 + 50)  # -25% → 0, +25% → 100
    return DimScore(
        key="np_growth", label="净利增速", score=s, badge=_badge(s), weight=w,
        inputs={"净利 YoY": f"{np*100:.1f}%"},
        formula="-25% → 0,+25% → 100;线性",
        note="加速" if np > 0.20 else "稳" if np > 0 else "下滑",
    )


def _score_roe(m, w, label="ROE"):
    roe = m.get("roe")
    if roe is None:
        return _missing("roe", label, w, "ROE")
    s = _clip(roe * 400)  # 0% → 0, 25% → 100
    return DimScore(
        key="roe", label=label, score=s, badge=_badge(s), weight=w,
        inputs={"ROE": f"{roe*100:.1f}%"},
        formula="0% → 0,25%+ → 100;线性",
        note="强" if roe >= 0.20 else "良" if roe >= 0.12 else "平",
    )


def _score_roe_quality(m, w, label="ROE 质量"):
    """稳定增长型偏好高 + 稳定 ROE。这里只看绝对值(稳定性需要历史序列,留 TODO)。"""
    return _score_roe(m, w, label=label)


def _score_moat_proxy(m, w):
    """护城河代理 = ROE,长期高 ROE 是定价权信号。"""
    return _score_roe(m, w, label="护城河 (ROE 代理)")


def _score_valuation(m, w, label="估值合理度"):
    """基于 PE-TTM 全周期分位反向(分位越低分越高)。当前用 metrics 中的 pe_pct_10y(若有),否则 pe_ttm 区间。"""
    pct = m.get("pe_pct_10y")
    if pct is not None:
        s = _clip(100 * (1 - pct))
        return DimScore(
            key="valuation", label=label, score=s, badge=_badge(s), weight=w,
            inputs={"PE 10y 分位": f"{pct*100:.1f}%"},
            formula="100·(1 − PE 全周期分位);分位越低分越高",
            note="低位" if pct < 0.30 else "中性" if pct < 0.70 else "高位",
        )
    pe = m.get("pe_ttm")
    if pe is None:
        return _missing("valuation", label, w, "PE-TTM 或分位")
    # PE: 10x → 100, 60x → 0
    s = _clip(120 - pe * 2)
    return DimScore(
        key="valuation", label=label, score=s, badge=_badge(s), weight=w,
        inputs={"PE-TTM": f"{pe:.1f}"},
        formula="120 − 2×PE,简化区间映射",
        note="低 PE" if pe < 15 else "中性" if pe < 30 else "高 PE",
    )


def _score_valuation_pb(m, w, label="PB 估值"):
    pb = m.get("pb")
    if pb is None:
        return _missing("valuation_pb", label, w, "PB")
    # PB <= 1 → 100; >= 5 → 0
    s = _clip(125 - pb * 25)
    return DimScore(
        key="valuation_pb", label=label, score=s, badge=_badge(s), weight=w,
        inputs={"PB": f"{pb:.2f}"},
        formula="125 − 25×PB(PB<1 → 100,PB≥5 → 0)",
        note="深度低估" if pb < 1 else "低估" if pb < 2 else "中性" if pb < 3 else "偏高",
    )


def _score_leverage(m, w):
    debt = m.get("debt_ratio")
    if debt is None:
        return _missing("leverage", "杠杆控制", w, "资产负债率")
    s = _clip((0.70 - debt) * 250)  # 30% → 100, 70% → 0
    return DimScore(
        key="leverage", label="杠杆控制", score=s, badge=_badge(s), weight=w,
        inputs={"负债率": f"{debt*100:.1f}%"},
        formula="(0.70 − 负债率) × 250;<30% 满分,>70% 0 分",
        note="低杠杆" if debt < 0.40 else "适中" if debt < 0.60 else "偏高",
    )


def _score_dividend(m, w, label="股息率"):
    dy = m.get("dividend_yield")
    if dy is None:
        return _missing("dividend", label, w, "股息率")
    s = _clip(dy * 2000)  # 0 → 0, 5% → 100
    return DimScore(
        key="dividend", label=label, score=s, badge=_badge(s), weight=w,
        inputs={"股息率": f"{dy*100:.2f}%"},
        formula="股息率 × 2000(5% → 100)",
        note="高股息" if dy >= 0.04 else "适中" if dy >= 0.02 else "低",
    )


def _score_cfo_quality(m, w, label="现金流质量"):
    """现金流质量:优先 CFO/NI,缺失时才用 ROE 代理。"""
    cfo_ni = m.get("cfo_to_ni")
    if cfo_ni is not None:
        s = _clip((cfo_ni - 0.5) * 200)  # 0.5 → 0,1.0 → 100
        if _is_home_appliance(m):
            note = (
                "家电校正:优秀现金牛" if cfo_ni >= 0.9
                else "家电校正:可接受" if cfo_ni >= 0.7
                else "家电校正:现金流偏弱"
            )
        else:
            note = "高质量" if cfo_ni >= 1.0 else "可接受" if cfo_ni >= 0.8 else "弱"
        return DimScore(
            key="cfo_quality", label=label, score=s, badge=_badge(s), weight=w,
            inputs={"CFO/净利润": f"{cfo_ni:.2f}"},
            formula="(CFO/净利润 − 0.5) × 200;1.0+ → 满分",
            note=note,
        )
    roe = m.get("roe")
    if roe is None:
        return _missing("cfo_quality", label, w, "CFO/NI 或 ROE")
    s = _clip(roe * 350 + 10)
    return DimScore(
        key="cfo_quality", label=label, score=s, badge=_badge(s), weight=w,
        inputs={"ROE (代理)": f"{roe*100:.1f}%"},
        formula="代理指标:ROE × 350 + 10(CFO/NI 数据待装配)",
        note="高质量" if roe >= 0.18 else "稳" if roe >= 0.10 else "弱",
    )


def _score_cfo(m, w):
    return _score_cfo_quality(m, w, label="现金流")


def _score_cfo_positive(m, w):
    return _score_cfo_quality(m, w, label="经营性现金流")


def _score_cash_to_mc(m, w):
    cash_mc = m.get("cash_to_market_cap")
    if cash_mc is None:
        return _missing("cash_to_mc", "现金/市值", w,
                        "现金/总市值 (数据待装配)")
    s = _clip(cash_mc * 250)  # 40% → 100
    return DimScore(
        key="cash_to_mc", label="现金/市值", score=s, badge=_badge(s), weight=w,
        inputs={"现金/市值": f"{cash_mc*100:.1f}%"},
        formula="现金/总市值 × 250(40%+ → 满分)",
        note="资产密集" if cash_mc >= 0.30 else "一般",
    )


def _score_debt_trend(m, w):
    """负债趋势 = 负债率反向(没历史趋势,先用绝对值)。"""
    base = _score_leverage(m, w)
    return DimScore(
        key="debt_trend", label="负债可控",
        score=base.score, badge=base.badge, weight=w,
        inputs=base.inputs,
        formula="代理:当前负债率(历史趋势数据待装配)",
        note=base.note,
    )


def _score_rev_stabilize(m, w):
    """营收企稳 = 最近营收 YoY 不再大幅下滑。"""
    yoy = m.get("rev_yoy_recent")
    if yoy is None:
        return _missing("rev_stabilize", "营收企稳", w, "营收 YoY")
    s = _clip((yoy + 0.20) * 250)  # -20% → 0, 20% → 100
    return DimScore(
        key="rev_stabilize", label="营收企稳", score=s, badge=_badge(s), weight=w,
        inputs={"营收 YoY": f"{yoy*100:.1f}%"},
        formula="(YoY + 20%) × 250(-20% → 0,+20% → 100)",
        note="企稳" if yoy >= 0 else "仍下滑" if yoy >= -0.10 else "恶化",
    )


def _score_roe_floor(m, w):
    """ROE 触底 = ROE 是否还高于 0(简化)。"""
    roe = m.get("roe")
    if roe is None:
        return _missing("roe_floor", "ROE 触底", w, "ROE")
    if roe < 0:
        s = 20.0
        note = "尚未触底"
    elif roe < 0.05:
        s = 50.0
        note = "刚触底"
    else:
        s = _clip(roe * 400)
        note = "已恢复"
    return DimScore(
        key="roe_floor", label="ROE 触底", score=s, badge=_badge(s), weight=w,
        inputs={"ROE": f"{roe*100:.1f}%"},
        formula="ROE < 0 → 20;< 5% → 50;否则 ROE × 400",
        note=note,
    )


# 维度 key → 评分函数
_DIM_SCORERS = {
    "peg":          _score_peg,
    "rev_growth":   _score_rev_growth,
    "np_growth":    _score_np_growth,
    "roe":          _score_roe,
    "roe_quality":  _score_roe_quality,
    "moat_proxy":   _score_moat_proxy,
    "valuation":    _score_valuation,
    "valuation_pb": _score_valuation_pb,
    "leverage":     _score_leverage,
    "dividend":     _score_dividend,
    "cfo_quality":  _score_cfo_quality,
    "cfo":          _score_cfo,
    "cfo_positive": _score_cfo_positive,
    "cash_to_mc":   _score_cash_to_mc,
    "debt_trend":   _score_debt_trend,
    "rev_stabilize":_score_rev_stabilize,
    "roe_floor":    _score_roe_floor,
}


def compute_lynch_dims(metrics: dict, cls_id: str) -> list[DimScore]:
    """A4:按 Lynch 类别计算专属 5 维评分。"""
    schema = LYNCH_DIM_SCHEMA.get(cls_id, LYNCH_DIM_SCHEMA["slow_grower"])
    results = []
    for d in schema:
        scorer = _DIM_SCORERS.get(d["key"])
        if scorer is None:
            results.append(_missing(d["key"], d["label"], d["weight"], "scorer 未实现"))
            continue
        # 部分 scorer 接受 label 参数,统一用 schema label 覆盖
        try:
            r = scorer(metrics, d["weight"])
            r.label = d["label"]
            results.append(r)
        except Exception as e:
            results.append(_missing(d["key"], d["label"], d["weight"], f"err:{e}"))
    return results


def overall_lynch(dims: list[DimScore]) -> tuple[float, str]:
    """综合分 = 加权平均;缺失维度按 50 中性占位。"""
    total = 0.0
    for d in dims:
        s = d.score if d.score is not None else 50.0
        total += d.weight * s
    if total >= 75: badge = "🟢"
    elif total >= 60: badge = "🟡"
    elif total >= 45: badge = "🟠"
    else: badge = "🔴"
    return round(total, 1), badge


def _pct(x: float | None, decimals: int = 1) -> str:
    return "—" if x is None else f"{x*100:.{decimals}f}%"


def _num(x: float | None, decimals: int = 1) -> str:
    return "—" if x is None else f"{x:.{decimals}f}"


# ───── 主分类逻辑 ────────────────────────────────────────────────────

def _verify_financials(primary: str, m: dict) -> tuple[list[str], float]:
    """步骤二:财务特征验证(知识库 PDF 第 3 页表格)。

    返回 (warnings, confidence_delta)。confidence_delta 为负:验证失败时降信心。

    阈值:
      稳健:ROE ≥ 15% / debt < 50% / CFO/NI > 1
      快速:ROE ≥ 15% / debt < 40%(铁律) / CFO/NI > 0.8
      缓慢:股息率 ≥ 4%(防御性配置)
    """
    warnings: list[str] = []
    delta = 0.0
    roe = m.get("roe")
    debt = m.get("debt_ratio")
    div = m.get("dividend_yield")
    is_home_appliance = _is_home_appliance(m)

    if primary == "stalwart":
        if roe is not None and roe < 0.15:
            warnings.append(f"⚠️ ROE {_pct(roe)} < 15%,稳健性不足(优秀稳健龙头门槛 ≥ 15%)")
            delta -= 0.15
        debt_warning_line = 0.65 if is_home_appliance else 0.55
        if debt is not None and debt > debt_warning_line:
            label = "家电校正" if is_home_appliance else "稳健增长"
            warnings.append(
                f"⚠️ 资产负债率 {_pct(debt)} > {debt_warning_line*100:.0f}%"
                f",偏离{label}财务结构"
            )
            delta -= 0.10
        elif debt is not None and is_home_appliance:
            warnings.append(
                f"✅ 家电校正:资产负债率 {_pct(debt)} ≤ 65%,不按通用 50% 硬卡"
            )
    elif primary == "fast_grower":
        if debt is not None and debt >= 0.40:
            warnings.append(f"⚠️ 资产负债率 {_pct(debt)} ≥ 40% — 违反快速增长股「铁律」,需重审分类")
            delta -= 0.20
        if roe is not None and roe < 0.15:
            warnings.append(f"⚠️ ROE {_pct(roe)} < 15%,增长质量存疑(可能并非好的快速增长型)")
            delta -= 0.10
    elif primary == "slow_grower":
        if div is not None and div >= 0.04:
            warnings.append(f"✅ 股息率 {_pct(div, 2)} ≥ 4%,符合缓慢增长典型股息特征")
            delta += 0.10
        elif div is not None and div < 0.02:
            warnings.append(f"⚠️ 股息率 {_pct(div, 2)} < 2%,缺乏缓慢增长股的防御性吸引")
            delta -= 0.05

    return warnings, delta


def _detect_special_features(m: dict) -> list[str]:
    """步骤三:特殊情况识别(困境反转 / 隐蔽资产)— 作为辅助标签。"""
    tags: list[str] = []
    np_yoy = m.get("np_yoy_recent")
    pb = m.get("pb")
    cash_mc = m.get("cash_to_market_cap")
    rev_yoy = m.get("rev_yoy_recent")

    # 困境反转:严重亏损/巨额下滑 + (PB 低位 OR 营收已企稳)
    severe_drop = np_yoy is not None and np_yoy < -0.30
    rev_recovering = rev_yoy is not None and rev_yoy >= 0  # "营收企稳"近似
    pb_low = pb is not None and pb < 1.5
    if severe_drop and (pb_low or rev_recovering):
        tags.append(
            f"困境反转特征:净利 YoY {_pct(np_yoy)} 大幅下滑"
            + (f" + PB {_num(pb, 2)} 历史低位" if pb_low else "")
            + (f" + 营收 YoY {_pct(rev_yoy)} 已企稳" if rev_recovering else "")
        )

    # 隐蔽资产:现金/市值高 OR PB 远低于 1
    if cash_mc is not None and cash_mc >= 0.30:
        tags.append(f"隐蔽资产特征:现金/总市值 {_pct(cash_mc)} ≥ 30%")
    elif pb is not None and pb < 1.0:
        tags.append(f"隐蔽资产特征:PB {_num(pb, 2)} < 1,账面价值被低估")

    return tags


def classify(m: dict[str, Any]) -> ClassificationResult:
    """按知识库 4 步法判定:周期 → CAGR 初步分级 → 财务验证 → 特殊情况附加。

    知识库:01_knowledge/03_投资策略与选股/02_彼得林奇投资法/01_六类公司分类法.md
    """
    industry_l1 = (m.get("industry_sw_l1") or "").strip()
    rev_cagr_5y = m.get("rev_cagr_5y")
    rev_cagr_3y = m.get("rev_cagr_3y")
    roe = m.get("roe")
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    cash_mc = m.get("cash_to_market_cap")
    debt = m.get("debt_ratio")
    np_yoy = m.get("np_yoy_recent")
    rev_yoy = m.get("rev_yoy_recent")
    div = m.get("dividend_yield")

    km = {
        "申万一级": industry_l1 or "—",
        "营收 5y CAGR": _pct(rev_cagr_5y),
        "营收 3y CAGR": _pct(rev_cagr_3y),
        "ROE": _pct(roe),
        "PE-TTM": _num(pe),
        "PB": _num(pb, 2),
        "股息率": _pct(div, 2),
        "资产负债率": _pct(debt),
        "现金/市值": _pct(cash_mc),
    }

    cagr = rev_cagr_5y if rev_cagr_5y is not None else rev_cagr_3y
    cagr_label = "5y" if rev_cagr_5y is not None else "3y"
    special_tags = _detect_special_features(m)

    # ═══ 步骤一:行业属性优先 — 银行/保险特殊处理 ═══════════════
    # 知识库:"传统银行=缓慢增长";保险用内含价值法,不适用普通成长分级
    # 这里:CAGR + ROE 决定稳健 vs 缓慢,但跳过快速增长(债 > 40% 是行业特性)
    if industry_l1 in FINANCIAL_INDUSTRIES:
        if cagr is None or roe is None:
            return ClassificationResult(
                cls_id="slow_grower",
                cls_name=CLASS_META["slow_grower"][0],
                cls_emoji=CLASS_META["slow_grower"][1],
                confidence=0.55,
                reason=f"金融业「{industry_l1}」+ 数据不足 → 暂归缓慢增长(知识库:传统银行 = 缓慢)",
                key_metrics=km,
                notes=["金融业不适用普通成长分级(债 > 40% 是行业特性);保险应另用内含价值法"],
            )
        # 金融业的"稳健"门槛:CAGR ≥ 10% AND ROE ≥ 15%(招行/平安式 优秀龙头)
        if cagr >= 0.10 and roe >= 0.15:
            primary_fin = "stalwart"
            reason_fin = (
                f"金融业「{industry_l1}」 + 营收 CAGR {_pct(cagr)} ≥ 10% + ROE {_pct(roe)} ≥ 15%"
                f" → 稳健增长型(优秀金融龙头)"
            )
            conf_fin = 0.85
        else:
            primary_fin = "slow_grower"
            reason_fin = (
                f"金融业「{industry_l1}」 + CAGR {_pct(cagr)} 或 ROE {_pct(roe)} 未达稳健龙头门槛"
                f" → 缓慢增长型(知识库:传统银行 = 缓慢,主要靠股息)"
            )
            conf_fin = 0.85 if (div is not None and div >= 0.04) else 0.75

        notes_fin = ["⚠️ **林奇 6 类不完美适用** — 金融业核心估值用内含价值(保险 EV)/ 拨备(银行),而非 PEG / PB"]
        notes_fin.append("金融业不适用 PEG / 现金流 / 负债率铁律(行业特性)")

        # 金融周期信号检测:净利率 5y CV > 30% → 推荐主次拆分
        # 保险投资端 / 银行不良率周期 都会让净利率剧烈波动 — 是真实的"金融周期"
        cv = m.get("net_margin_5y_cv")
        suggest_split = False
        if cv is not None and cv > 0.30:
            cv_pct = cv * 100
            notes_fin.append(
                f"🔴 **检测到金融周期信号**:5y 净利率变异系数 {cv_pct:.0f}% > 30% — "
                f"利润随利率/资本市场周期剧烈波动(典型 stalwart 应 <20%)"
            )
            suggest_split = True

        if industry_l2 := (m.get("industry_sw_l2") or "").strip():
            if industry_l2 in ("保险", "证券"):
                notes_fin.append(
                    f"📐 **{industry_l2}估值法**:正确口径是"
                    f"{'内含价值(EV)+ 新业务价值(NBV)+ 投资收益率分解' if industry_l2 == '保险' else '自营 / 经纪 / 投行 分部估值 + 净资本充足率'}"
                    f",林奇 PEG / PB 都是粗代理"
                )
                suggest_split = True

        # 推荐主次拆分(让用户用 _render_type_editor 标双特征)
        if suggest_split:
            notes_fin.append(
                "💡 **建议主次拆分**:在下方「类型编辑器」勾选 "
                f"主类型 = {CLASS_META[primary_fin][1]} {CLASS_META[primary_fin][0]} 70% "
                "+ 次类型 = 🔄 周期型 30%(资本/利率周期),综合定位更准"
            )

        if primary_fin == "stalwart":
            notes_fin.append("适合长期持有 — 关注 ROE 持续性 + 拨备覆盖率(银行)/ 内含价值(保险)")
        else:
            notes_fin.append("重点看股息率 + 不良/赔付率,而非成长")
        notes_fin.append(CLASS_META[primary_fin][2])
        if special_tags:
            notes_fin.extend(special_tags)

        # 给前端 UI 一个标志位,用于显示"金融周期警告 banner"
        return ClassificationResult(
            cls_id=primary_fin,
            cls_name=CLASS_META[primary_fin][0],
            cls_emoji=CLASS_META[primary_fin][1],
            confidence=conf_fin,
            reason=reason_fin,
            key_metrics=km,
            notes=notes_fin,
            extra={
                "is_financial": True,
                "industry_l2": industry_l2 or "",
                "net_margin_cv": cv,
                "suggest_split_secondary": "cyclical" if suggest_split else "",
                "suggest_split_weight": 70 if suggest_split else 100,
                "lynch_six_class_misfit": True,
            },
        )

    if industry_l1 in CYCLICAL_INDUSTRIES:
        # 周期型:行业属性主导,即便 CAGR 高也归周期(典型如汽车/化工)
        secondary = ""
        if cagr is not None and cagr >= 0.20:
            secondary = f" + 当前处行业上行期(CAGR {_pct(cagr)})"
        notes = [
            "判断买卖时点比挑公司更重要 — 看 PB / 库存 / 产能利用率",
            CLASS_META["cyclical"][2],
        ]
        if special_tags:
            notes.extend(special_tags)
        return ClassificationResult(
            cls_id="cyclical",
            cls_name=CLASS_META["cyclical"][0],
            cls_emoji=CLASS_META["cyclical"][1],
            confidence=0.85,
            reason=(
                f"行业「{industry_l1}」属典型周期性行业(产品价格/库存/产能利用率有明显周期)"
                f" → 营收/盈利受行业周期主导{secondary},归为周期型"
            ),
            key_metrics=km,
            notes=notes,
        )

    # ═══ 步骤二之前:数据缺失兜底 ═══════════════════════════════
    if cagr is None:
        notes = [
            "营收 CAGR 数据缺失 — 需补全 3-5 年营收同比数据后重新分类",
            "若属高速扩张早期(如新上市公司),实际可能是快速增长型",
        ]
        if special_tags:
            notes.extend(special_tags)
        return ClassificationResult(
            cls_id="slow_grower",
            cls_name="未分类(数据不足)",
            cls_emoji="❓",
            confidence=0.20,
            reason="缺乏营收 CAGR 数据 → 暂无法按知识库 4 步法分类",
            key_metrics=km,
            notes=notes,
        )

    # ═══ 步骤一(续)+ 步骤二:CAGR 分级 + 财务验证 ═══════════════
    # 知识库标准:CAGR < 10% / 10-20% / ≥ 20%(更优 ≥ 25-35%)
    # 但 P3 步骤二强调"先定性后定量"——CAGR 5-10% 边缘区如 ROE ≥ 15% + 财务稳健,
    # 仍可归稳健(消费/家电/白酒龙头典型);CAGR ≥ 10% 是更标准的稳健入场。
    if cagr >= 0.20:
        primary = "fast_grower"
        base_conf = 0.90 if cagr >= 0.25 else 0.80
        primary_reason = (
            f"营收 {cagr_label} CAGR {_pct(cagr)} ≥ 20%(高速扩张区间)"
            + ("·达到 ≥ 25% 优级标准" if cagr >= 0.25 else "")
        )
    elif cagr >= 0.10:
        primary = "stalwart"
        base_conf = 0.85
        primary_reason = (
            f"营收 {cagr_label} CAGR {_pct(cagr)} 处 10-20% 稳健区间(可预测增长)"
        )
    elif cagr >= 0.05 and roe is not None and roe >= 0.15:
        # 边缘稳健:CAGR 5-10% + ROE ≥ 15% → 消费/家电/白酒龙头型
        # debt 高(如家电业 60%)在步骤二验证里加警告,不降级
        primary = "stalwart"
        base_conf = 0.75
        primary_reason = (
            f"营收 {cagr_label} CAGR {_pct(cagr)} 处 5-10% 边缘区,但 ROE {_pct(roe)} ≥ 15%"
            f" → 边缘稳健型(消费/家电/白酒龙头特征,先定性后定量)"
        )
    else:
        primary = "slow_grower"
        base_conf = 0.80
        primary_reason = (
            f"营收 {cagr_label} CAGR {_pct(cagr)} < 10%"
            + (
                "(且 ROE 或财务结构未达稳健龙头门槛)"
                if cagr >= 0.05
                else "(增速与 GDP 相当或偏低)"
            )
        )

    # 步骤二:财务特征验证(可能修正 confidence,加 warnings)
    warnings, delta = _verify_financials(primary, m)
    confidence = max(0.30, min(0.95, base_conf + delta))

    # 严重违反"快速增长铁律"(债 ≥ 40% AND ROE < 15%)→ 降级到稳健
    if (
        primary == "fast_grower"
        and debt is not None and debt >= 0.40
        and roe is not None and roe < 0.15
    ):
        warnings.append("→ 同时违反负债铁律 + ROE 不足,降级为稳健增长型(增速虽高但质量不达标)")
        primary = "stalwart"
        confidence = max(0.55, confidence - 0.10)

    # 稳健候选 ROE 严重不足(< 12%)→ 降级缓慢
    if (
        primary == "stalwart"
        and roe is not None and roe < 0.12
        and cagr < 0.15
    ):
        warnings.append("→ ROE < 12% 且 CAGR 偏低,降级为缓慢增长型(更接近成熟大盘特征)")
        primary = "slow_grower"
        confidence = max(0.60, confidence - 0.05)

    # PEG 注释(快速增长候选)— 理杏仁口径:PE-TTM ÷ (净利润 TTM YoY% × 100)
    peg_note = ""
    if primary == "fast_grower" and pe is not None:
        peg_lx_val = m.get("peg_lixinger")
        if peg_lx_val is not None:
            peg_note = f" · PEG ≈ {peg_lx_val:.2f}(理杏仁)"
            peg_note += (" — 估值合理(PEG<1)" if peg_lx_val < 1
                         else " — 估值偏高(PEG>2)" if peg_lx_val > 2
                         else " — 估值适中")
        elif cagr > 0:
            peg_fb = pe / (cagr * 100)
            peg_note = f" · PEG ≈ {peg_fb:.2f}(营收CAGR兜底)"

    # 困境反转特殊处理:np 大幅下滑 + PB 低位 → 主分类升级为 turnaround
    severe_distress = (
        np_yoy is not None and np_yoy < -0.30
        and pb is not None and pb < 1.5
    )
    if severe_distress and primary != "fast_grower":
        primary = "turnaround"
        confidence = 0.70
        primary_reason = (
            f"净利 YoY {_pct(np_yoy)} < -30% + PB {_num(pb, 2)} 历史低位"
            f" → 困境反转候选(原 {primary_reason})"
        )

    # 资产隐蔽特殊处理:现金/市值 ≥ 40% AND PB < 1.5 → 主分类升级为 asset_play
    if cash_mc is not None and cash_mc >= 0.40 and (pb is None or pb < 1.5):
        primary = "asset_play"
        confidence = 0.75
        primary_reason = (
            f"现金/总市值 {_pct(cash_mc)} ≥ 40% + PB {_num(pb, 2)}"
            f" → 净现金占比极高,主类改判隐蔽资产型"
        )

    # 组合最终 reason
    full_reason = primary_reason + peg_note
    if warnings:
        full_reason += "\n        步骤二验证:" + "; ".join(warnings)

    notes = []
    if primary == "fast_grower":
        notes = ["重点跟踪营收/利润季报维持高速,警惕减速信号(知识库:连续 8 季度单季 >20% 是更强信号)"]
    elif primary == "stalwart":
        notes = ["适合长期持有 + 估值合理时分批加仓(组合「压舱石」)"]
    elif primary == "slow_grower":
        notes = ["重点看股息覆盖率与稳定性,而非成长(防御性配置)"]
    elif primary == "turnaround":
        notes = ["必须看现金流是否仍正、有无反转催化(知识库:核心反转指标连续 2 季度改善)"]
    elif primary == "asset_play":
        notes = ["等催化 — 大额回购 / 分红 / 资产分拆 / 子公司剥离"]
    notes.append(CLASS_META.get(primary, ("", "", ""))[2] if primary in CLASS_META else "")
    notes = [n for n in notes if n]

    if special_tags:
        notes.extend(special_tags)

    return ClassificationResult(
        cls_id=primary,
        cls_name=CLASS_META[primary][0],
        cls_emoji=CLASS_META[primary][1],
        confidence=round(confidence, 2),
        reason=full_reason,
        key_metrics=km,
        notes=notes,
    )


# ───── 数据装配:从 DuckDB + companies.csv 拼出 metrics ─────────────────

def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _latest_value(con, table: str, ticker: str, metric: str) -> float | None:
    row = con.execute(
        f"SELECT value FROM {table} WHERE ticker = ? AND metric = ? "
        f"AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
        [ticker, metric],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _np_yoy_from_series(con, ticker: str) -> float | None:
    """从「归属于母公司普通股股东的净利润」累积序列派生最近一期净利同比(小数)。

    理杏仁 growth 表无「净利润同比」metric,只给累积绝对值。取最新一期与去年
    同月日(同口径累积期)相比。返回 0.02 = +2%;数据不足返回 None。
    """
    try:
        rows = con.execute(
            "SELECT date, value FROM growth "
            "WHERE ticker = ? AND metric = '归属于母公司普通股股东的净利润' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 12",
            [ticker],
        ).fetchall()
    except Exception:
        return None
    if len(rows) < 2:
        return None
    latest_d, latest_v = rows[0]
    md = str(latest_d)[5:]  # 'MM-DD'
    yr = int(str(latest_d)[:4])
    prev_v = None
    for d, v in rows[1:]:
        if str(d)[5:] == md and int(str(d)[:4]) == yr - 1:
            prev_v = v
            break
    if prev_v is None or prev_v == 0:
        return None
    try:
        return float(latest_v) / float(prev_v) - 1.0
    except Exception:
        return None


def _pe_pct_10y(con, ticker: str) -> float | None:
    """与 score_card._pe_percentile 一致的 10y 全周期分位。"""
    cutoff = (date.today() - timedelta(days=365 * 10)).isoformat()
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
    return float(row[0]) if row and row[0] is not None else None


def _rev_cagr(con, ticker: str, years: int) -> float | None:
    """用『累积同比』近似 N 年 CAGR(取最近 N 年的几何平均)。

    简化:取最近年 metric 值 v_now / N 年前的 v_then,(v_now/v_then)^(1/N) - 1
    实际我们手上是『同比』而非营收绝对值 → 退化为最近 N 年同比的几何平均。
    """
    cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
    rows = con.execute(
        """
        SELECT date, value FROM growth
        WHERE ticker = ? AND metric = '累积同比' AND value IS NOT NULL
              AND date >= ?
        ORDER BY date
        """,
        [ticker, cutoff],
    ).fetchall()
    if not rows:
        return None
    # 取每年末尾(最后一个非 None)
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["year"] = pd.to_datetime(df["date"]).dt.year
    yearly = df.groupby("year")["value"].last()
    if yearly.empty:
        return None
    # 同比的几何平均近似 CAGR
    factors = (yearly + 1).clip(lower=0.01)  # 避免负值出错
    return float(factors.prod() ** (1.0 / len(factors)) - 1)


# ─── 单季 YoY 连续性(跨模块共享)─────────────────────────────────────────
#
# 用法:lynch_analysis.py 第 2 步层 2 + lynch_abcd_scorer.py "增长连续性 15 分项"
# 共用同一份 8 季 YoY 数据,避免"评分用最新一期 / 图表用 8 季"口径分裂。
#
# 数据源策略:
#   1. 优先取 growth 表 '同比'(理杏仁后续若补回)
#   2. 否则从 '营业收入' 累计值派生:
#      单季 = 累计本季 - 累计上季(同年内);Q1 直接用累计
#      YoY = 单季今年 / 单季去年同期 - 1


@dataclass
class QuarterlyContinuity:
    """8 季单季 YoY 连续性统计。"""
    series: list[tuple[str, float]]  # [(date_iso, yoy), ...] 按时间升序
    n_quarters: int                  # 实际拿到的季度数
    hits_20pct: int                  # >20% 命中数
    hits_10pct: int                  # >10% 命中数
    hits_0: int                      # ≥0 命中数(防"连续负增长")
    latest_yoy: float | None         # 最新单季 YoY
    median_yoy: float | None         # 中位数(避免极端值主导)
    source: str                      # 'direct' / 'derived' / 'empty'

    def fast_grower_pass(self) -> bool:
        """快速增长铁律:8 季中 ≥6 季 >20%。"""
        return self.n_quarters >= 6 and self.hits_20pct >= 6

    def stalwart_pass(self) -> bool:
        """稳健增长铁律:8 季中 ≥6 季 >10%。"""
        return self.n_quarters >= 6 and self.hits_10pct >= 6

    def to_dict(self) -> dict:
        return {
            "series": [(d, float(y)) for d, y in self.series],
            "n_quarters": self.n_quarters,
            "hits_20pct": self.hits_20pct,
            "hits_10pct": self.hits_10pct,
            "hits_0": self.hits_0,
            "latest_yoy": self.latest_yoy,
            "median_yoy": self.median_yoy,
            "source": self.source,
        }


def quarterly_continuity(con, ticker: str, n_quarters: int = 8) -> QuarterlyContinuity:
    """计算近 N 季单季营收 YoY 连续性 — 纯计算,无 streamlit 依赖。

    con: 已打开的 duckdb 只读连接(由调用方管理生命周期)
    """
    empty = QuarterlyContinuity([], 0, 0, 0, 0, None, None, "empty")
    if not ticker:
        return empty

    # 多取 2 年作 yoy 锚:N 季 + 4 季去年同期 = N+4 季,保险起见取 (N/4 + 2) 年
    years_back = max(3, n_quarters // 4 + 2)
    cutoff = (date.today() - timedelta(days=365 * years_back)).isoformat()

    # ---- 路径 1:直接取 '同比' ----
    try:
        rows = con.execute(
            """
            SELECT date, value FROM growth
            WHERE ticker = ? AND metric = '同比' AND value IS NOT NULL
                  AND date >= ?
            ORDER BY date DESC LIMIT ?
            """,
            [ticker, cutoff, n_quarters],
        ).fetchall()
    except Exception:
        rows = []

    if rows:
        df = pd.DataFrame(rows, columns=["date_str", "yoy"]).sort_values("date_str")
        return _build_continuity(df, source="direct")

    # ---- 路径 2:从累计营收派生单季 YoY ----
    try:
        rev_rows = con.execute(
            """
            SELECT date, value FROM growth
            WHERE ticker = ? AND metric = '营业收入' AND value IS NOT NULL
                  AND date >= ?
            ORDER BY date ASC
            """,
            [ticker, cutoff],
        ).fetchall()
    except Exception:
        rev_rows = []

    if not rev_rows:
        return empty

    rev = pd.DataFrame(rev_rows, columns=["date_str", "cum_revenue"])
    rev["date"] = pd.to_datetime(rev["date_str"])
    rev["year"] = rev["date"].dt.year
    rev["quarter"] = rev["date"].dt.month // 3  # 3→1 / 6→2 / 9→3 / 12→4
    rev = rev.sort_values(["year", "quarter"]).reset_index(drop=True)

    # 单季还原:Q1 用累计;Q2/Q3/Q4 = 当期累计 - 上一季累计(同年内)
    rev["prev_cum"] = rev.groupby("year")["cum_revenue"].shift(1)
    rev["single_q"] = rev["cum_revenue"] - rev["prev_cum"].fillna(0)

    # YoY:同一 quarter 上一年单季对齐
    rev["prev_year_single"] = rev.groupby("quarter")["single_q"].shift(1)
    rev["yoy"] = (rev["single_q"] / rev["prev_year_single"] - 1).where(
        rev["prev_year_single"].abs() > 1e-6
    )

    out = (
        rev.dropna(subset=["yoy"])
        .sort_values("date")
        .tail(n_quarters)[["date_str", "yoy"]]
        .reset_index(drop=True)
    )
    if out.empty:
        return empty
    return _build_continuity(out, source="derived")


def _build_continuity(df: "pd.DataFrame", source: str) -> QuarterlyContinuity:
    """把 (date_str, yoy) 表转成 QuarterlyContinuity。"""
    series = [(str(r["date_str"])[:10], float(r["yoy"])) for _, r in df.iterrows()]
    yoys = [y for _, y in series]
    n = len(series)
    hits_20 = sum(1 for y in yoys if y > 0.20)
    hits_10 = sum(1 for y in yoys if y > 0.10)
    hits_0 = sum(1 for y in yoys if y >= 0)
    latest = yoys[-1] if yoys else None
    median = float(pd.Series(yoys).median()) if yoys else None
    return QuarterlyContinuity(
        series=series, n_quarters=n,
        hits_20pct=hits_20, hits_10pct=hits_10, hits_0=hits_0,
        latest_yoy=latest, median_yoy=median, source=source,
    )


# ─── ABCD 评分辅助:从原始时序自动派生稳定性 / 行业对比 / 股息连续 ─────


def _net_margin_5y_cv(con, ticker: str) -> tuple[float | None, float | None]:
    """5y 净利率(净利润/营收)的 标准差/均值(变异系数)+ 均值(0-1)。

    数据源:growth 表的 '归属于母公司普通股股东的净利润' / '营业收入'(同期)
    返回 (cv, mean) ;若数据不足返回 (None, None)。
    """
    try:
        rows = con.execute(
            """
            WITH np AS (
                SELECT date, value AS np_v FROM growth
                WHERE ticker = ? AND metric = '归属于母公司普通股股东的净利润'
                      AND value IS NOT NULL
            ),
            rev AS (
                SELECT date, value AS rev_v FROM growth
                WHERE ticker = ? AND metric = '营业收入' AND value IS NOT NULL
            )
            SELECT np.date, np.np_v / NULLIF(rev.rev_v, 0) AS margin
            FROM np JOIN rev ON np.date = rev.date
            WHERE rev.rev_v > 0
            ORDER BY np.date DESC LIMIT 20
            """,
            [ticker, ticker],
        ).fetchall()
    except Exception:
        return None, None
    if len(rows) < 4:
        return None, None
    margins = [float(r[1]) for r in rows if r[1] is not None]
    if not margins:
        return None, None
    n = len(margins)
    mean = sum(margins) / n
    if mean == 0:
        return None, None
    var = sum((x - mean) ** 2 for x in margins) / n
    std = var ** 0.5
    return std / abs(mean), mean


def _gross_margin_vs_industry(con, ticker: str,
                                industry_l2: str) -> tuple[float | None, float | None, float | None, str | None]:
    """毛利率 vs 行业:返回 (公司当前 GM, 行业中位 GM, 差距 pp, source)。

    source ∈ {"db", "static", None}:
      - "db"     = profitability 表里有 `{industry_l2}(申万) - 毛利率(GM)` 聚合 metric
      - "static" = 走 industry_gm_static.py 静态字典(verified=False)
      - None     = 行业不适用毛利率(银行/保险)或公司无毛利率数据
    """
    # 公司毛利率(最新)— 静态回退也需要拿到自身 GM 才能算 diff
    try:
        co_row = con.execute(
            "SELECT value FROM profitability WHERE ticker = ? AND metric = '毛利率(GM)' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
            [ticker],
        ).fetchone()
    except Exception:
        return None, None, None, None
    if not co_row:
        return None, None, None, None
    co_gm = float(co_row[0])

    # 1) 优先查 profitability 表里的行业聚合 metric
    if industry_l2:
        try:
            ind_row = con.execute(
                "SELECT value FROM profitability "
                "WHERE metric = ? AND value IS NOT NULL "
                "ORDER BY date DESC LIMIT 1",
                [f"{industry_l2}(申万) - 毛利率(GM)"],
            ).fetchone()
        except Exception:
            ind_row = None
        if ind_row:
            ind_gm = float(ind_row[0])
            diff_pp = (co_gm - ind_gm) * 100 if co_gm < 1 else (co_gm - ind_gm)
            return co_gm, ind_gm, diff_pp, "db"

    # 2) 回退到静态字典
    try:
        from industry.gm_static import get_static_industry_gm
    except ImportError:
        return co_gm, None, None, None
    _label, ind_gm_pct = get_static_industry_gm(ticker)
    if ind_gm_pct is None:
        return co_gm, None, None, None
    co_pct = co_gm * 100 if co_gm < 1 else co_gm
    diff_pp = co_pct - ind_gm_pct
    # 把静态值也按比例(0-1)归一,跟 db 路径返回口径一致
    ind_gm_norm = ind_gm_pct / 100 if co_gm < 1 else ind_gm_pct
    return co_gm, ind_gm_norm, diff_pp, "static"


def _cyclical_safety_metrics(con, ticker: str) -> tuple[float | None, float | None]:
    """周期股财务安全:返回 (CFO/总负债, 流动负债/总负债)。"""
    try:
        # CFO(经营活动现金流净额,最新)
        cfo_row = con.execute(
            "SELECT value FROM cashflow WHERE ticker=? AND metric='经营活动产生的现金流量净额' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
            [ticker],
        ).fetchone()
        debt_row = con.execute(
            "SELECT value FROM safety WHERE ticker=? AND metric='负债合计' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
            [ticker],
        ).fetchone()
        cur_debt_row = con.execute(
            "SELECT value FROM safety WHERE ticker=? AND metric='流动负债合计' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
            [ticker],
        ).fetchone()
    except Exception:
        return None, None

    cfo = float(cfo_row[0]) if cfo_row and cfo_row[0] is not None else None
    debt = float(debt_row[0]) if debt_row and debt_row[0] is not None else None
    cur_debt = float(cur_debt_row[0]) if cur_debt_row and cur_debt_row[0] is not None else None

    cfo_to_debt = (cfo / debt) if (cfo is not None and debt and debt > 0) else None
    short_ratio = (cur_debt / debt) if (cur_debt is not None and debt and debt > 0) else None
    return cfo_to_debt, short_ratio


def _ps_5y_pct(con, ticker: str) -> float | None:
    """当前 PS-TTM 在自身 5y 时序中的分位(0-1,越低 = 越便宜)。"""
    try:
        rows = con.execute(
            "SELECT value FROM valuation WHERE ticker = ? AND metric = 'PS-TTM' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1300",
            [ticker],
        ).fetchall()
    except Exception:
        return None
    if not rows or len(rows) < 30:
        return None
    cur = float(rows[0][0])
    series = [float(r[0]) for r in rows if r[0] is not None]
    rank = sum(1 for v in series if v <= cur) / len(series)
    return rank


def _dividend_yield_5y_pct(con, ticker: str) -> float | None:
    """当前股息率在自身 5y 时序中的分位(0-1)。越大 = 当前历史高位 = 价格相对低。"""
    try:
        rows = con.execute(
            "SELECT date, value FROM valuation WHERE ticker = ? AND metric = '股息率' "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 1300",  # ~5y 日频
            [ticker],
        ).fetchall()
    except Exception:
        return None
    if not rows or len(rows) < 30:
        return None
    cur = float(rows[0][1])
    if cur <= 0:
        return 0.0
    series = [float(r[1]) for r in rows if r[1] is not None]
    rank = sum(1 for v in series if v <= cur) / len(series)
    return rank


def _dividend_continuous_years(con, ticker: str) -> int | None:
    """从 valuation.股息率 时序倒数,数连续 >0 的年数。返回 int 或 None。"""
    try:
        rows = con.execute(
            "SELECT date, value FROM valuation WHERE ticker = ? AND metric = '股息率' "
            "AND value IS NOT NULL ORDER BY date DESC",
            [ticker],
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["year"] = pd.to_datetime(df["date"]).dt.year
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    # 每年最高股息率(任一日 >0 即视为该年派息)
    yearly = df.groupby("year")["value"].max().sort_index(ascending=False)
    # 从最近年份往前数连续 >0 的年数
    cnt = 0
    for v in yearly:
        if v is not None and v > 0:
            cnt += 1
        else:
            break
    return cnt


def _load_metrics_uncached(ticker: str, db_path: Path | str = DB_PATH,
                        industry_csv: Path | str = COMPANIES_CSV) -> dict[str, Any]:
    """从 DuckDB + companies.csv 装配单家公司的彼得林奇判断输入。"""
    m: dict[str, Any] = {"ticker": ticker}

    # 行业从 companies.csv 读
    # 注:companies.csv 的 stock 列历史上丢了前导零(如 '333' / '2097'),
    # 而 ticker 已规范化为 '000333' / '02097' → 直接字符串相等会全失配,
    # 导致 18 家深市/港股公司 name/category/industry 全部丢失(WP3 ① 修复)。
    # 先把 csv stock 按各自 category 规范化后再匹配。
    try:
        try:
            from tickers import normalize_ticker as _norm
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from tickers import normalize_ticker as _norm
        comp = pd.read_csv(industry_csv, dtype={"stock": str})
        comp["_stock_norm"] = comp.apply(
            lambda r: _norm(r["stock"], market=r.get("category")),
            axis=1,
        )
        row = comp[comp["_stock_norm"] == ticker]
        if row.empty:  # 兜底:旧逻辑直配(防御)
            row = comp[comp["stock"] == ticker]
        if not row.empty:
            m["name"] = row.iloc[0].get("name")
            m["industry_sw_l1"] = row.iloc[0].get("industry") or ""
            m["industry_sw_l2"] = row.iloc[0].get("industry_l2") or ""
            m["category"] = row.iloc[0].get("category") or ""
    except Exception:
        m["industry_sw_l1"] = ""

    con = _conn(db_path)
    try:
        # 估值口径(2026-05-06 数据规则):优先扣非,fallback GAAP
        # 见 .config/数据更新规则.md
        pe_recurring = _latest_value(con, "valuation", ticker, "PE-TTM(扣非)")
        pe_gaap = _latest_value(con, "valuation", ticker, "PE-TTM")
        m["pe_ttm"] = pe_recurring if pe_recurring is not None else pe_gaap
        m["pe_ttm_recurring"] = pe_recurring          # 扣非(主用)
        m["pe_ttm_gaap"] = pe_gaap                    # GAAP(备用)
        m["pe_uses_fallback"] = pe_recurring is None and pe_gaap is not None

        pb_clean = _latest_value(con, "valuation", ticker, "PB(不含商誉)")
        pb_gaap = _latest_value(con, "valuation", ticker, "PB")
        m["pb"] = pb_clean if pb_clean is not None else pb_gaap
        m["pb_clean"] = pb_clean                      # 不含商誉(主用)
        m["pb_gaap"] = pb_gaap                        # 含商誉(备用)
        m["pb_uses_fallback"] = pb_clean is None and pb_gaap is not None

        m["dividend_yield"] = _latest_value(con, "valuation", ticker, "股息率")
        m["roe"] = _latest_value(con, "profitability", ticker, "净资产收益率(ROE)")
        m["debt_ratio"] = _latest_value(con, "safety", ticker, "资产负债率")
        # M6 林奇财务护栏:补 4 项指标
        m["current_ratio"] = _latest_value(con, "safety", ticker, "流动比率")
        m["cfo_to_ni"] = _latest_value(
            con, "cashflow", ticker,
            "经营活动产生的现金流量净额对净利润的比率"
        )
        m["rev_yoy_recent"] = _latest_value(con, "growth", ticker, "累积同比")
        # 净利 YoY:理杏仁 growth 表并不提供「归母净利润_累积同比」metric(0 行),
        # 旧代码两次取值恒得 None,导致 lynch 困境/周期判定 + graham 困境/价值陷阱
        # 全部拿不到净利同比(WP3 ① 修复)。改为从「归属于母公司普通股股东的净利润」
        # 累积序列派生:最新一期 vs 去年同月日,得到小数(0.02 = +2%)。
        m["np_yoy_recent"] = _latest_value(con, "growth", ticker, "归母净利润_累积同比")
        if m["np_yoy_recent"] is None:
            m["np_yoy_recent"] = _latest_value(con, "growth", ticker, "归母净利润_同比")
        if m["np_yoy_recent"] is None:
            m["np_yoy_recent"] = _np_yoy_from_series(con, ticker)
        m["rev_cagr_5y"] = _rev_cagr(con, ticker, 5)
        m["rev_cagr_3y"] = _rev_cagr(con, ticker, 3)
        m["pe_pct_10y"] = _pe_pct_10y(con, ticker)

        # cash_to_market_cap 简化:暂无可靠数据来源,先 None
        m["cash_to_market_cap"] = None
    finally:
        con.close()

    # 净利润 TTM YoY + 当前 PEG(理杏仁同口径,与 peg_curve.py 一致)
    # PEG = PE-TTM ÷ (净利润 TTM YoY% × 100) 不是营收 CAGR
    m["np_ttm_yoy"] = None
    m["peg_lixinger"] = None
    try:
        from valuation.peg_curve import build_peg_series
        peg_df = build_peg_series(ticker, db_path=db_path, lookback_years=5)
        if not peg_df.empty:
            valid = peg_df.dropna(subset=["peg"])
            if not valid.empty:
                last = valid.iloc[-1]
                m["np_ttm_yoy"] = float(last["growth_pct"])  # 百分数,如 10.5(理杏仁口径=3y CAGR)
                m["peg_lixinger"] = float(last["peg"])
    except Exception:
        pass

    # 周转天数从独立 turnover.duckdb 读(避免主库写锁冲突)
    m["inventory_turnover_days"] = None
    m["receivables_turnover_days"] = None
    m["total_asset_turnover"] = None
    turnover_db = Path(db_path).parent / "turnover.duckdb"
    if turnover_db.exists():
        try:
            tcon = duckdb.connect(str(turnover_db), read_only=True)
            try:
                for metric, key in [
                    ("存货周转天数", "inventory_turnover_days"),
                    ("应收账款周转天数", "receivables_turnover_days"),
                    ("总资产周转率", "total_asset_turnover"),
                ]:
                    row = tcon.execute(
                        "SELECT value FROM turnover_metrics "
                        "WHERE ticker=? AND metric=? AND value IS NOT NULL "
                        "ORDER BY date DESC LIMIT 1",
                        [ticker, metric],
                    ).fetchone()
                    if row and row[0] is not None:
                        m[key] = float(row[0])
            finally:
                tcon.close()
        except Exception:
            pass

    # ─── ABCD 评分自动派生:净利率稳定性 / 毛利率行业差 / 股息连续年数 ───
    try:
        con2 = _conn(db_path)
        try:
            cv, mean = _net_margin_5y_cv(con2, ticker)
            m["net_margin_5y_cv"] = cv
            m["net_margin_5y_mean"] = mean

            ind_l2 = m.get("industry_sw_l2") or m.get("industry_sw_l1") or ""
            co_gm, ind_gm, diff_pp, gm_source = _gross_margin_vs_industry(con2, ticker, ind_l2)
            m["gross_margin_self"] = co_gm
            m["gross_margin_industry_median"] = ind_gm
            m["gross_margin_vs_industry_pp"] = diff_pp
            m["gross_margin_industry_source"] = gm_source

            m["dividend_years_continuous"] = _dividend_continuous_years(con2, ticker)
            m["dividend_yield_5y_pct"] = _dividend_yield_5y_pct(con2, ticker)
            m["ps_5y_pct"] = _ps_5y_pct(con2, ticker)

            cfo_dt, short_r = _cyclical_safety_metrics(con2, ticker)
            m["cfo_to_total_debt"] = cfo_dt
            m["short_debt_ratio"] = short_r
        finally:
            con2.close()
    except Exception:
        pass

    return m


def _db_mtime_of(p: Path | str) -> float:
    try:
        return Path(p).stat().st_mtime
    except OSError:
        return 0.0


@functools.lru_cache(maxsize=256)
def _load_metrics_cached(ticker: str, db_mtime: float) -> dict[str, Any]:
    return _load_metrics_uncached(ticker)


def load_metrics_from_db(ticker: str, db_path: Path | str = DB_PATH,
                        industry_csv: Path | str = COMPANIES_CSV) -> dict[str, Any]:
    """装配单家公司的林奇判断输入。

    默认数据源走 (ticker, db_mtime) lru_cache(公司页一次 render 会被调多次,
    实测未缓存 ~190ms/次)。返回浅拷贝,防调用方变异污染缓存。
    """
    if str(db_path) == str(DB_PATH) and str(industry_csv) == str(COMPANIES_CSV):
        return dict(_load_metrics_cached(ticker, _db_mtime_of(db_path)))
    return _load_metrics_uncached(ticker, db_path, industry_csv)


@functools.lru_cache(maxsize=256)
def _classify_ticker_cached(ticker: str, db_mtime: float) -> ClassificationResult:
    """按 (ticker, db_mtime) 缓存单家分类;db_mtime 变即失效(配合 cron 增量)。"""
    return classify_ticker(ticker)


def lynch_type_of(ticker: str, db_mtime: float = 0.0) -> str | None:
    """单家公司的林奇分类 id(cls_id)。

    供单公司详情页用 — 避免为取一家 lynch_type 而对全市场跑 classify。
    """
    try:
        return _classify_ticker_cached(ticker, db_mtime).cls_id or None
    except Exception:
        return None


def classify_ticker(ticker: str, **kwargs) -> ClassificationResult:
    m = load_metrics_from_db(ticker, **kwargs)
    return classify(m)


# ───── CLI ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="*", default=[])
    args = ap.parse_args()

    if args.ticker:
        targets = args.ticker
    else:
        comp = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
        targets = comp["stock"].tolist()

    for t in targets:
        try:
            r = classify_ticker(t)
            print(f"\n{'─'*64}")
            print(f"  {r.cls_emoji} {r.cls_name}  ·  {t}  ·  confidence={r.confidence:.0%}")
            print(f"{'─'*64}")
            print(f"  {r.reason}")
            print(f"\n  关键数据:")
            for k, v in r.key_metrics.items():
                print(f"    {k:<14}{v}")
            if r.notes:
                print(f"\n  提示:")
                for n in r.notes:
                    print(f"    · {n}")
        except Exception as e:
            print(f"\n❌ {t}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
