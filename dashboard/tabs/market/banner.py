"""市场 Tab · ⓪ 综合结论 banner — 三信号合成(康波 / 格雷厄姆差值 / A股全指 PE 分位)。"""
from __future__ import annotations

import streamlit as st

from ._helpers import (
    _graham_rating,
    _load_kondratieff,
    _load_macro_latest,
)


def _section_verdict_banner(macro_path: str, macro_mtime: float) -> None:
    """三信号合成:康波(静态权重) + 格雷厄姆差值(动态) + A 股全指 PE 全周期分位(动态)。

    评分规则(每信号 -1 / 0 / +1):
      康波(萧条期防御) → -1   (静态)
      格雷厄姆差值 ≥4% → +1 / [2,4)% → 0 / <2% → -1
      A 股全指 PE 5y 分位 ≤30% → +1 / 30-70% → 0 / >70% → -1
    合成总分 → 总评级 + 推荐权益区间
    """
    kdf = _load_kondratieff()
    hs = _load_macro_latest(macro_path, "A_FULL_PE", macro_mtime)
    yld = _load_macro_latest(macro_path, "10Y_YIELD", macro_mtime)

    # 信号 1:康波(静态从 yaml)
    kondratieff_phase = kdf.get("phase", "萧条期中后段") if kdf else "萧条期中后段"
    kondratieff_emoji = kdf.get("phase_emoji", "🔴") if kdf else "🔴"
    kondratieff_score = -1  # 萧条期默认偏防御

    # 信号 2:格雷厄姆指数(差值法,理杏仁口径)
    if hs and yld and hs["value"] > 0 and yld["value"] > 0:
        ey_pct = (1.0 / hs["value"]) * 100.0       # 盈利收益率 %
        bond_pct = yld["value"]                    # 10Y 国债已是 %
        graham_diff = ey_pct - bond_pct
        g_label, g_badge, eq_lo, eq_hi = _graham_rating(graham_diff)
        graham_score = 1 if graham_diff >= 4.0 else (0 if graham_diff >= 2.0 else -1)
        graham_text = f"{g_badge} {graham_diff:+.2f}% {g_label}"
    else:
        graham_diff = None
        graham_score = 0
        graham_text = "⚪ 数据缺"
        eq_lo, eq_hi = 40, 55

    # 信号 3:A 股全指 PE 5y 分位
    if hs and hs.get("pct_5y") is not None:
        pct = hs["pct_5y"]
        if pct <= 0.30:
            hs_score, hs_badge = 1, "🟢"
        elif pct <= 0.70:
            hs_score, hs_badge = 0, "🟡"
        else:
            hs_score, hs_badge = -1, "🔴"
        hs_text = f"{hs_badge} {hs['value']:.1f}({pct*100:.0f}% 分位)"
    else:
        hs_score = 0
        hs_text = "⚪ 数据缺"

    total = kondratieff_score + graham_score + hs_score

    # 综合判定 — 取格雷厄姆建议区间为主,康波做防御封顶
    if total >= 2:
        verdict_emoji, verdict_text = "🟢🟢", "股市极度吸引 · 加仓窗口"
        eq_target = eq_hi
    elif total == 1:
        verdict_emoji, verdict_text = "🟢", "股市偏吸引 · 逐步加仓"
        eq_target = (eq_lo + eq_hi) // 2
    elif total == 0:
        verdict_emoji, verdict_text = "🟡", "股债平衡 · 持有观察"
        eq_target = (eq_lo + eq_hi) // 2
    elif total == -1:
        verdict_emoji, verdict_text = "🟡", "防御为主 · 谨慎加仓"
        eq_target = eq_lo
    else:
        verdict_emoji, verdict_text = "🔴", "全面防御 · 减仓避险"
        eq_target = max(20, eq_lo - 10)

    # 康波封顶:萧条期权益建议不超过 75%
    eq_max_by_kw = (kdf or {}).get("equity_target_pct_max", 75)
    eq_target = min(eq_target, eq_max_by_kw)

    # 信号通过数(+1 算通过)
    pass_n = sum(1 for s in (kondratieff_score, graham_score, hs_score) if s >= 0)

    # 渲染:浅色背景 banner
    color = {"🟢🟢": "#1b8a3a", "🟢": "#1b8a3a", "🟡": "#f0ad4e", "🔴": "#d9534f"}.get(verdict_emoji, "#888")
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, {color}22 0%, transparent 100%);
                    border-left: 5px solid {color};
                    padding: 14px 18px; border-radius: 8px; margin: 8px 0 16px;">
          <div style="font-size: 18px; font-weight: 700;">
            {verdict_emoji} 当前综合判断:{verdict_text}
            <span style="font-size: 13px; color: #555; margin-left: 12px; font-weight: 500;">
              建议权益占比 ≈ <b>{eq_target}%</b> · 三信号通过 {pass_n}/3
            </span>
          </div>
          <div style="font-size: 13px; color: #444; margin-top: 8px;">
            <b>康波</b>:{kondratieff_emoji} {kondratieff_phase}(防御主)　|
            <b>股债收益差</b>:{graham_text}　|
            <b>A 股全指 PE 5y 分位</b>:{hs_text}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
