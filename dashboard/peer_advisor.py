"""Phase C · 同行对比建议引擎。

输入:ticker + 同行业分位摘要
输出:综合估值评级(低估/偏低/合理/偏高/高估)+ 关键证据 + 一句话总结

不依赖 streamlit;dataclass 返回值,UI 在 components/ 渲染。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / ".tools" / "rules" / "peer_advice.yaml"


# 类型别名
Direction = Literal["high_good", "low_good"]
Signal = int  # [-2, +2]


@dataclass
class MetricVerdict:
    metric: str
    self_value: float | None
    percentile: float | None
    signal: Signal              # -2 / -1 / 0 / +1 / +2
    label: str                  # "强 / 偏强 / 合理 / 偏弱 / 弱"
    direction: Direction
    weight: int


@dataclass
class PeerAdvice:
    ticker: str
    name: str
    industry: str
    n_peers: int
    verdicts: list[MetricVerdict] = field(default_factory=list)
    weighted_sum: float = 0
    overall_label: str = "—"        # 低估 / 偏低 / 合理 / 偏高 / 高估
    overall_emoji: str = "🟡"
    overall_color: str = "#F59E0B"
    quality_label: str = "中性"     # 优质 / 中性 / 存疑
    summary_oneliner: str = ""


# ─── 规则加载 ───────────────────────────────────────────────────────

_RULES_CACHE: dict | None = None


def _load_rules(path: Path = RULES_PATH) -> dict:
    global _RULES_CACHE
    if _RULES_CACHE is not None:
        return _RULES_CACHE
    with path.open(encoding="utf-8") as f:
        _RULES_CACHE = yaml.safe_load(f)
    return _RULES_CACHE


# ─── 单指标判定 ──────────────────────────────────────────────────────

def _signal_from_percentile(
    pct: float | None, thresholds: dict, direction: Direction,
) -> tuple[Signal, str]:
    """根据分位 + 方向 + 阈值返回 (signal, label)。"""
    if pct is None:
        return 0, "数据缺失"

    sp = thresholds["strong_pos"]
    mp = thresholds["mild_pos"]
    mn = thresholds["mild_neg"]
    sn = thresholds["strong_neg"]

    if direction == "low_good":
        # 分位低 = 好(self 便宜)→ 信号正
        if pct <= sp:
            return +2, "估值低"
        if pct <= mp:
            return +1, "偏低"
        if pct >= sn:
            return -2, "估值高"
        if pct >= mn:
            return -1, "偏高"
        return 0, "合理"
    else:
        # high_good:分位高 = 好(self 强)→ 信号正
        if pct >= sp:
            return +2, "强"
        if pct >= mp:
            return +1, "偏强"
        if pct <= sn:
            return -2, "弱"
        if pct <= mn:
            return -1, "偏弱"
        return 0, "合理"


def _band_lookup(weighted_sum: float, bands: list[dict]) -> dict:
    """权重和 → 评级 band(bands 按 min 降序排列)。"""
    sorted_bands = sorted(bands, key=lambda b: b["min"], reverse=True)
    for b in sorted_bands:
        if weighted_sum >= b["min"]:
            return b
    return sorted_bands[-1]


def _quality_from(verdicts: list[MetricVerdict]) -> str:
    """质量评级:基于 ROE / F-Score / 净利YoY 综合。"""
    quality_metrics = ["ROE", "F-Score lite", "净利YoY"]
    quality_signals = [v.signal for v in verdicts if v.metric in quality_metrics]
    if not quality_signals:
        return "中性"
    avg = sum(quality_signals) / len(quality_signals)
    if avg >= 1:
        return "优质"
    if avg <= -1:
        return "存疑"
    return "中性"


# ─── 主入口 ─────────────────────────────────────────────────────────

def advise(ticker: str, name: str = "") -> PeerAdvice | None:
    """
    生成 ticker 的同行对比建议。

    流程:
      1. 调 industry_percentile.all_metrics_summary 拿 9 指标分位
      2. 对每指标 → MetricVerdict(signal/label)
      3. 加权求和 → 综合 band → overall_label + emoji
      4. quality 评级 → 一句话总结
    """
    import sys
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    import industry_percentile as ipx  # noqa: E402

    rules = _load_rules()
    metric_rules = rules["metrics"]

    # 取所有指标的分位
    all_ips = []
    industry = ""
    n_peers = 0
    for m in metric_rules:
        ip = ipx.industry_percentile(ticker, m)
        if ip is None:
            continue
        all_ips.append(ip)
        if not industry:
            industry = ip.industry
        if not n_peers:
            n_peers = ip.n_peers

    if not all_ips:
        return None

    # 单指标判定
    verdicts: list[MetricVerdict] = []
    weighted_sum = 0.0
    total_weight = 0
    for ip in all_ips:
        rule = metric_rules.get(ip.metric)
        if rule is None:
            continue
        sig, lbl = _signal_from_percentile(
            ip.percentile, rule["thresholds"], rule["direction"],
        )
        weight = rule.get("weight", 1)
        verdicts.append(MetricVerdict(
            metric=ip.metric, self_value=ip.self_value,
            percentile=ip.percentile, signal=sig, label=lbl,
            direction=rule["direction"], weight=weight,
        ))
        if ip.percentile is not None:
            weighted_sum += sig * weight
            total_weight += weight

    # 综合 band
    band = _band_lookup(weighted_sum, rules["aggregation"]["bands"])
    quality = _quality_from(verdicts)

    # Top 证据(信号绝对值最大的 3 个)
    sig_sorted = sorted(verdicts, key=lambda v: abs(v.signal) * v.weight, reverse=True)
    top_evidence = []
    for v in sig_sorted:
        if v.signal == 0 or v.percentile is None:
            continue
        top_evidence.append(f"{v.metric} 第 {v.percentile:.0f} 分位({v.label})")
        if len(top_evidence) >= 3:
            break

    summary = (
        f"{band['label']} · 综合{quality}"
        + (" — " + ",".join(top_evidence) if top_evidence else "")
    )

    return PeerAdvice(
        ticker=ticker,
        name=name,
        industry=industry,
        n_peers=n_peers,
        verdicts=verdicts,
        weighted_sum=weighted_sum,
        overall_label=band["label"],
        overall_emoji=band.get("emoji", "🟡"),
        overall_color=band.get("color", "#F59E0B"),
        quality_label=quality,
        summary_oneliner=summary,
    )


# ─── Hero 卡 HTML ───────────────────────────────────────────────────

def render_hero_card_html(advice: PeerAdvice) -> str:
    """生成 Hero 区「💡 vs 同行 N 家」建议卡 HTML。"""
    # 颜色:overall_color 为底色;Emoji 大字 + 标签
    chip_html = "".join(
        f'<span style="display:inline-block;background:#F3F4F6;color:#374151;'
        f'padding:3px 10px;border-radius:999px;font-size:12px;margin-right:6px;'
        f'margin-bottom:4px;">'
        f'{e}</span>' for e in advice.summary_oneliner.split("—")[1].strip().split(",")
    ) if "—" in advice.summary_oneliner else ""

    return (
        f'<div style="border:1px solid {advice.overall_color}40;background:{advice.overall_color}08;'
        f'border-radius:10px;padding:14px 16px;margin:10px 0;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="font-size:24px;">{advice.overall_emoji}</div>'
        f'<div>'
        f'<div style="font-size:13px;color:#6B7280;">vs 同行业「{advice.industry}」 {advice.n_peers} 家</div>'
        f'<div style="font-size:18px;font-weight:700;color:{advice.overall_color};">'
        f'{advice.overall_label} · 综合{advice.quality_label}'
        f'</div>'
        f'</div>'
        f'</div>'
        + (f'<div style="margin-top:8px;">{chip_html}</div>' if chip_html else "")
        + f'</div>'
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", default="600519", nargs="?")
    args = ap.parse_args()

    a = advise(args.ticker)
    if a is None:
        print(f"{args.ticker} 无同行数据")
    else:
        print(f"\n=== {args.ticker} {a.name or ''} 同行对比建议 ===")
        print(f"行业:{a.industry}({a.n_peers} 同行)")
        print(f"加权信号:{a.weighted_sum:+.1f}")
        print(f"综合评级:{a.overall_emoji} {a.overall_label} · {a.quality_label}")
        print(f"一句话:{a.summary_oneliner}\n")
        print("分指标:")
        for v in a.verdicts:
            sv = f"{v.self_value:.2f}" if v.self_value is not None else "—"
            pv = f"{v.percentile:.0f}" if v.percentile is not None else "—"
            print(f"  {v.metric:14s} self={sv:>8s}  分位={pv:>3s}  "
                  f"信号={v.signal:+d}({v.label})")
