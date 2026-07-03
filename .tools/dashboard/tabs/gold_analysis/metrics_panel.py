"""黄金 sub-tab ② 关键指标面板 — 合并实际利率定价 / 关键比率 / 周期定位。

v2.7 简化:原 ② / ③ / ④ 三个轻量 sub-tab 合一,减少用户点击,提升一屏信息密度。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


def _render_metrics_panel(snap: Snapshot, db_mtime: float) -> None:
    st.markdown("### 📊 关键指标面板")
    st.caption(
        "📚 方法论:[02_实际利率定价模型.md]"
        f"({KNOWLEDGE_BASE}/02_实际利率定价模型.md) · "
        "[03_配置比例量化.md]"
        f"({KNOWLEDGE_BASE}/03_配置比例量化.md) · "
        "[05_关键指标速查.md]"
        f"({KNOWLEDGE_BASE}/05_关键指标速查.md)"
    )

    # ───────────── 区块 A · 实际利率定价 ─────────────
    st.markdown("#### A · 实际利率定价(范式一锚)")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        rr = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
        rrp = f"{snap.real_rate_pct_10y*100:.0f}% 分位" if snap.real_rate_pct_10y is not None else "—"
        st.metric("实际利率(10Y-CPI)", rr, rrp,
                  help="< 0 利好黄金 · > 0 压制(2022 后失效期需查范式二/三)")
    with col_b:
        n10y = f"{snap.nominal_10y:.2f}%" if snap.nominal_10y is not None else "—"
        st.metric("名义 10Y", n10y)
    with col_c:
        cpi = f"{snap.cpi_yoy:.2f}%" if snap.cpi_yoy is not None else "—"
        st.metric("CPI YoY", cpi)
    with col_d:
        gusd = f"${snap.gold_usd:.0f}/oz" if snap.gold_usd is not None else "—"
        st.metric("USD 金价(派生)", gusd, help="沪金 × USDCNY × 31.1g/oz")

    rates = _ratios_cached(db_mtime, days=365 * 20)
    gold_usd = _indicator_cached("GOLD_USD_DERIVED", db_mtime, days=365 * 20)
    if not rates.empty and not gold_usd.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            rates = rates.dropna(subset=["real_rate"])
            gold_usd = gold_usd.dropna()

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(x=gold_usd["date"], y=gold_usd["value"],
                           name="USD 金价", line=dict(color="#fbbf24", width=2)),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=rates["date"], y=rates["real_rate"],
                           name="实际利率(右轴 反向)",
                           line=dict(color="#1e3a8a", width=2, dash="dot")),
                secondary_y=True,
            )
            fig.update_layout(
                hovermode="x unified", height=360,
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", y=1.05),
            )
            fig.update_yaxes(title="USD/oz", secondary_y=False)
            fig.update_yaxes(title="实际利率 %", secondary_y=True, autorange="reversed")
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")
    else:
        st.info("数据不足(实际利率或 USD 金价缺失)")

    with st.expander("💡 四象限决策矩阵(实际利率 × 通胀)", expanded=False):
        st.markdown("""
| 象限 | 实际利率 | 通胀 | 黄金强度 | 配置 | 当前对照 |
|------|---------|------|---------|------|---------|
| I 通胀繁荣 | < 0 | 高 | ⭐⭐⭐⭐ | 15-20% | — |
| II 滞胀型 | < 0 | 高 | ⭐⭐⭐⭐⭐ | 20-25% | — |
| III 通缩衰退 | > 0 | 低 | ⭐⭐⭐ | 5-10% | — |
| **IV 通胀回落** | **> 0** | **正常** | **⭐⭐** | **0-5%(范式二/三激活时仍可持有)** | ✅ **当前位置** |

**当前(2026-05)**:实际利率 +1.63% / CPI YoY 2.73% → **象限 IV**
但范式二/三仍激活 → 黄金不应大幅减仓,维持战略配置
""")

    st.divider()

    # ───────────── 区块 B · 关键比率 + 分位仪表盘 ─────────────
    st.markdown("#### B · 关键比率(金油 / 金银 / SPDR)")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        rr = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
        rrp = f"{snap.real_rate_pct_10y*100:.0f}% 分位" if snap.real_rate_pct_10y is not None else "—"
        st.metric("① 实际利率", rr, rrp)
    with col_b:
        go_v = f"{snap.gold_oil:.1f}" if snap.gold_oil is not None else "—"
        gop = f"{snap.gold_oil_pct_10y*100:.0f}% 分位" if snap.gold_oil_pct_10y is not None else "—"
        st.metric("② 金油比", go_v, gop)
    with col_c:
        gs_v = f"{snap.gold_silver:.1f}" if snap.gold_silver is not None else "—"
        gsp = f"{snap.gold_silver_pct_10y*100:.0f}% 分位" if snap.gold_silver_pct_10y is not None else "—"
        st.metric("③ 金银比(SGE)", gs_v, gsp,
                  help="SGE 国内口径,与 LBMA 国际(~88)不可直接对比")
    with col_d:
        spdr = f"{snap.spdr_holdings:.0f} 吨" if snap.spdr_holdings is not None else "未启用"
        st.metric("④ SPDR 持仓", spdr,
                  help="jin10.com 中国 IP 卡 → 走 .config/spdr_holdings_manual.csv 手填")

    ratios = _ratios_cached(db_mtime, days=365 * 10)
    if not ratios.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(rows=2, cols=2,
                                subplot_titles=("实际利率(%)", "金油比",
                                                "金银比(SGE)",
                                                "(SPDR 持仓 — 数据待接入)"))
            d = ratios["date"]
            for r, c, ycol, color in [
                (1, 1, "real_rate", "#1e3a8a"),
                (1, 2, "gold_oil",  "#b45309"),
                (2, 1, "gold_silver", "#dc2626"),
            ]:
                if ycol in ratios.columns:
                    fig.add_trace(
                        go.Scatter(x=d, y=ratios[ycol],
                                   line=dict(color=color, width=2),
                                   showlegend=False),
                        row=r, col=c,
                    )

            spdr_df = _indicator_cached("SPDR_HOLDINGS", db_mtime, days=365 * 10)
            if not spdr_df.empty:
                fig.add_trace(
                    go.Scatter(x=spdr_df["date"], y=spdr_df["value"],
                               line=dict(color="#fbbf24", width=2), showlegend=False),
                    row=2, col=2,
                )
                fig.layout.annotations[3].text = "SPDR 持仓(吨)"

            fig.update_layout(height=480, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")

    with st.expander("📐 分位仪表盘(metric × window)", expanded=False):
        pct_df = _percentiles_cached(db_mtime)
        if not pct_df.empty:
            pivot = pct_df.pivot_table(
                index="metric", columns="window_label",
                values="percentile", aggfunc="first",
            )

            def _pct_color(v):
                if pd.isna(v):
                    return ""
                v = max(0.0, min(1.0, float(v)))
                if v <= 0.5:
                    t = v * 2
                    r = int(26 + (255 - 26) * t)
                    g = int(152 + (255 - 152) * t)
                    b = int(80 + (191 - 80) * t)
                else:
                    t = (v - 0.5) * 2
                    r = int(255 + (215 - 255) * t)
                    g = int(255 + (48 - 255) * t)
                    b = int(191 + (39 - 191) * t)
                return f"background-color: rgb({r},{g},{b}); color: #1a1a1a"

            st.dataframe(
                pivot.style.format("{:.1%}", na_rep="—").map(_pct_color),
                width="stretch",
            )
            st.caption("🟢 低分位(可能加仓)/ 🔴 高分位(可能减仓)")
        else:
            st.info("分位数据未生成,先跑 `fetch_gold_ratios.py`")

    st.divider()

    # ───────────── 区块 C · 周期定位(康波四阶段)─────────────
    st.markdown("#### C · 周期定位(康波四阶段)")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("当前周期阶段", "第五次康波萧条期",
                  help="周金涛预测 2030-2035 切回升期")
    with col_b:
        st.metric("黄金战略权重", "15-25%",
                  help="萧条期对黄金最有利")
    with col_c:
        st.metric("预计切换时间", "2030-2035",
                  help="AI 商用化 + 新动能爆发 = 切换标志")

    with st.expander("📜 四次萧条期对照 + 康波示意图", expanded=False):
        st.markdown("""
```text
┌─────────────────────────────────────────────────────────────────┐
│           康波四阶段:股票/商品/现金/黄金的轮动               │
├─────────────────────────────────────────────────────────────────┤
│   回升期        繁荣期         衰退期         萧条期(当前)    │
│  2030/35-?    1991-2004    2004-2020       2020-2030/35        │
│   ┌──────┐    ┌──────┐      ┌──────┐      ┌──────────┐      │
│   │ 股票 │───►│ 商品 │─────►│ 现金 │─────►│   黄金   │      │
│   └──────┘    └──────┘      └──────┘      └──────────┘      │
│      ✅           ❌            ⚠️            ⭐⭐⭐         │
│   配置:5-10%   0-5%          5-10%          15-25% ← 当前    │
└─────────────────────────────────────────────────────────────────┘
```
""")
        historical = pd.DataFrame({
            "康波": ["第一次", "第二次", "第三次", "第四次", "第五次(当前)"],
            "萧条期": ["1815-1849", "1873-1896", "1929-1949", "1973-1982", "2020-2030/35?"],
            "黄金表现": ["保值", "缓慢上行", "金本位崩溃后大涨",
                     "+1300% (1971-1980)", "进行中"],
            "驱动因素": [
                "拿破仑战争结束 / 工业初期",
                "长萧条 / 银本位危机",
                "大萧条 / 二战 / 布雷顿森林",
                "石油危机 / 滞胀 / 美元脱金",
                "AI 革命 / 去美元化 / 地缘冲突",
            ],
        })
        st.dataframe(historical, width="stretch", hide_index=True)

    with st.expander("💡 配置比例公式(三层联动)", expanded=False):
        st.markdown("""
**第一步**:康波阶段 → 战略基础区间
- 萧条期 15-25% / 衰退期 5-10% / 回升期 5-10% / 繁荣期 0-5%

**第二步**:风险偏好乘数
- 低风险(股 < 10%):基础 × 0.1 → 黄金 1-2%
- 中风险(股 20-40%):基础 × 0.7 → 黄金 14-17%
- 高风险(股 ≥ 50%):基础 × 1.6 → 黄金 32-40% ⭐(鲁政委定律)

**第三步**:战术微调
- 三范式全开 + 实际利率 < -1%:+5%
- 钝化 + 实际利率 > +2%:-5%

**示例**(高风险偏好,2026-05):
- 战略基础 20% × 1.6 = 32% + 战术 +5% = **37%** ≈ 鲁政委 38% 上限
""")
