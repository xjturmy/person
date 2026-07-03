"""黄金 sub-tab ⑤ ETF 选择(4 只对比 + 归一化叠加 + 推荐评分)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


# ─── ⑤ ETF 选择 ─────────────────────────────────────────────────────────


def _render_etf(db_mtime: float) -> None:
    st.markdown("### ⑤ 黄金 ETF 选择")
    st.caption(
        "📚 方法论:[04_黄金ETF选择.md]"
        f"({KNOWLEDGE_BASE}/04_黄金ETF选择.md)"
    )

    master = _etf_master_cached(db_mtime)
    if master.empty:
        st.warning("ETF master 未填,先跑 `fetch_gold_etf.py`")
        return

    # 4 列对比卡片
    cols = st.columns(len(master))
    for i, (_, etf) in enumerate(master.iterrows()):
        with cols[i]:
            highlight = "⭐ 推荐" if etf["etf_code"] == "518880" else ""
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border:1px solid #fbbf24;background:rgba(251,191,36,0.08);margin-bottom:6px">'
                f'<div style="font-size:11px;color:#888">{etf["exchange"]} · {etf["manager"]}</div>'
                f'<div style="font-size:16px;font-weight:700;margin-top:2px">{etf["etf_code"]}</div>'
                f'<div style="font-size:13px;margin-top:2px">{etf["etf_name"]}</div>'
                f'<div style="font-size:11px;color:#666;margin-top:6px">'
                f'费率 {etf["fee_rate"]:.2f}% / 跟踪 {etf["tracking"]}</div>'
                f'<div style="font-size:11px;color:#10b981;font-weight:600;margin-top:4px">{highlight}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # 归一化叠加图
    st.markdown("#### 归一化净值对比(3 年)")
    prices = _etf_prices_cached(db_mtime, days=365 * 3)
    if not prices.empty:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            for code in master["etf_code"]:
                sub = prices[prices["etf_code"] == code].sort_values("date")
                if sub.empty:
                    continue
                base = sub["close"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=sub["date"],
                    y=sub["close"] / base * 100,
                    mode="lines",
                    name=code,
                    line=dict(width=2),
                ))
            fig.update_layout(
                height=380, hovermode="x unified",
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="归一化净值(基期 = 100)",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")
    else:
        st.info("ETF 价格数据未填,先跑 `fetch_gold_etf.py`")

    with st.expander("💡 ETF 选择原则", expanded=False):
        st.markdown("""
**首选标的**:**华安黄金 ETF(518880)**
- 规模最大(~430 亿)→ 流动性最好 → 跟踪误差最小
- 上交所挂牌 → 国内券商均可交易
- 4 只费率均为 0.6%,**不在费率上选,而在流动性**

**工具组合(推荐)**:
- 70-80% **黄金 ETF(518880)** — 主仓 / 流动性 / 战术调整
- 10-20% **银行积存金** — 自动定投 / 强制储蓄
- 5-10% **实物金条** — 极端避险 / 长期 / 心理锚

**避坑提醒**:
- ❌ 黄金股(GDX/紫金矿业)— 短期受**大盘指数 > 金价**影响
- ❌ 黄金期货 / 期权 — 普通投资者爆仓概率 > 80%
- ❌ 银行纸黄金 — 费率比 ETF 高 5-10 倍
""")


