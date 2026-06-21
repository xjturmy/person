"""黄金 sub-tab ① 三大范式投票(15 信号矩阵)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


# ─── ① 三大范式投票 ─────────────────────────────────────────────────────


def _render_paradigm(snap: Snapshot, vote) -> None:
    st.markdown("### ① 三大范式投票(15 信号矩阵)")
    st.caption(
        "📚 方法论:[01_三大范式判定.md]"
        f"({KNOWLEDGE_BASE}/01_三大范式判定.md)"
        " · 鲁政委《保卫财富》框架"
        " · 📸 **快照型判定**:13/15 信号为人工季度复审值(康波/地缘/央行购金等),"
        "历史不可回看,本卡仅展示「当下」结果"
    )

    # 引擎可用 → 用引擎信号(dict 列表);否则回落 static
    engine_signals = getattr(vote, "signals", None)
    if engine_signals:
        # 引擎结果格式:list[dict] — 适配为 UI 期望格式
        # paradigm 字段(经济金融 / 技术革命 / 大国博弈)从 paradigm_label 提取
        p_map = {"economic_financial": "经济金融",
                 "tech_revolution": "技术革命",
                 "great_power_struggle": "大国博弈"}
        signals = []
        for sig in engine_signals:
            if isinstance(sig, dict):
                p_zh = p_map.get(sig.get("paradigm", ""), sig.get("paradigm", ""))
                signals.append({
                    "id": sig["signal_id"],
                    "p": p_zh,
                    "name": sig["name"],
                    "current": str(sig.get("current_value")) if sig.get("current_value") is not None else "—",
                    "threshold": sig.get("threshold_str", ""),
                    "active": bool(sig.get("active", False)),
                    "source": sig.get("source", "—"),
                })
    else:
        signals = fill_dynamic_signals(snap)
    by_paradigm = {"经济金融": [], "技术革命": [], "大国博弈": []}
    for sig in signals:
        by_paradigm.setdefault(sig.get("p", ""), []).append(sig)

    col_a, col_b, col_c = st.columns(3)
    paradigm_meta = [
        ("经济金融", "🟢 范式一", "短期(月-季)", vote.p1_count, vote.p1_active, col_a),
        ("技术革命", "🟡 范式二", "中期(年-十年)", vote.p2_count, vote.p2_active, col_b),
        ("大国博弈", "🔴 范式三", "长期(十年-世代)", vote.p3_count, vote.p3_active, col_c),
    ]

    for p_name, p_label, p_horizon, count, active, col in paradigm_meta:
        with col:
            badge = "✅ 激活" if active else "⚪ 钝化"
            color = "#10b981" if active else "#9ca3af"
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border-left:4px solid {color};background:rgba(0,0,0,0.04);margin-bottom:6px">'
                f'<div style="font-size:13px;color:#666">{p_label} · {p_horizon}</div>'
                f'<div style="font-size:18px;font-weight:700;margin-top:4px">{p_name}</div>'
                f'<div style="font-size:14px;margin-top:4px">{badge} · {count}/5 信号</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            for sig in by_paradigm[p_name]:
                emoji = "✅" if sig["active"] else "⚪"
                st.markdown(
                    f'<div style="padding:6px 8px;font-size:12px;line-height:1.5">'
                    f'{emoji} <b>{sig["name"]}</b><br/>'
                    f'<span style="color:#888">阈值:{sig["threshold"]}</span><br/>'
                    f'<span style="color:#444">当前:{sig["current"]}</span><br/>'
                    f'<span style="color:#aaa;font-size:11px">来源:{sig["source"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    st.divider()
    st.markdown("#### 投票判定 → 主导身份 → 配置区间")
    pct_lo, pct_hi = vote.suggested_pct
    actives = sum([vote.p1_active, vote.p2_active, vote.p3_active])
    st.markdown(f"""
- **范式一(经济金融)**:{vote.p1_count}/5 信号激活 → {"✅ 激活" if vote.p1_active else "⚪ 钝化"}
- **范式二(技术革命)**:{vote.p2_count}/5 信号激活 → {"✅ 激活" if vote.p2_active else "⚪ 钝化"}
- **范式三(大国博弈)**:{vote.p3_count}/5 信号激活 → {"✅ 激活" if vote.p3_active else "⚪ 钝化"}

**主导身份**:{vote.dominant_label}({actives}/3 范式激活)
**建议黄金占比**:{pct_lo:.0f}-{pct_hi:.0f}%(高风险偏好客户可至 38%,鲁政委震撼结论)
""")
    if vote.verified:
        st.success(
            f"✅ 当前判定来源:**yaml 投票引擎**(`{getattr(vote, 'source', '—')}`)"
            "。yaml 阈值见 [.tools/rules/gold_paradigm.yaml](#)。"
            " 数据真实接入度:实际利率 / SPDR(若手填)/ 康波 / 地缘 / 央行购金 / 美元储备 / 全部 yaml manual_const。"
        )
        if hasattr(vote, "note") and vote.note:
            st.caption(f"💡 {vote.note}")
    else:
        st.info(
            "⚠️ 当前判定来源:**静态判定**(yaml 引擎未启用,可能 yaml 路径错或 PyYAML 缺)。"
            " 待接入项:VIX 实时数据 / 美股科技-金价相关性 / 美国生产力 YoY。"
        )


