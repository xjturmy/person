"""黄金 sub-tab ⑦ 金股 ETF 杠杆视图(v2.6 主题 3 板块 I)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


# ─── ⑦ 金股 ETF 杠杆视图(v2.6 主题 3 板块 I)──────────────────────────


def _format_beta(b: float | None, decimals: int = 2) -> str:
    return f"{b:.{decimals}f}" if isinstance(b, (int, float)) else "—"


def _render_stock_etf_leverage(overheat: dict | None, db_mtime: float) -> None:
    st.markdown("### ⑦ 金股 ETF 杠杆视图(放大版黄金 ETF)")
    st.caption(
        "📈 **核心洞察**:金股 ETF(金矿股票挂钩)是黄金 ETF 的放大工具,"
        "β 通常 1.5-2.5 倍。⚠️ **双向性**:β 放大上涨,也放大下跌 — "
        "金价红灯时高 β 应优先减。"
    )

    master = _stock_etf_master_cached(db_mtime)
    if master.empty:
        st.warning("⚠️ 金股 ETF 数据未就绪 — 跑 `.tools/db/fetch_gold_stock_etf.py` 后刷新。")
        return

    # 1. β 计算
    betas = _stock_betas_cached(db_mtime)
    beta_map = {b["etf_code"]: b for b in betas}

    # 2. 顶部 banner — 金价 verdict + 杠杆总建议
    verdict_id = (overheat or {}).get("verdict_id", "hold")
    verdict_label = (overheat or {}).get("verdict_label", "🟡 数据未就绪")
    # 取 4 只 β_60d 中位数作"代表 β"给 banner advice;
    # 同一只 ETF 的 R² 一并取出,避免低 R² 的极端 β 污染 banner
    valid_pairs = [
        (b.get("beta_60d"), b.get("r_squared_60d"))
        for b in betas
        if b.get("beta_60d") is not None
    ]
    if valid_pairs:
        valid_pairs_sorted = sorted(valid_pairs, key=lambda p: p[0])
        rep_beta, rep_r2 = valid_pairs_sorted[len(valid_pairs_sorted) // 2]
    else:
        rep_beta, rep_r2 = None, None

    banner_advice = None
    if _OVERHEAT_AVAILABLE:
        try:
            banner_advice = _stock_etf_advice(verdict_id, rep_beta, r_squared=rep_r2)
        except Exception as e:
            st.warning(f"杠杆建议引擎失败:{e}")

    if banner_advice:
        rep_b_str = _format_beta(rep_beta)
        bg = (OVERHEAT_GRADIENT_RED if "🔴" in banner_advice.advice
              else OVERHEAT_GRADIENT_YELLOW if "🟡" in banner_advice.advice
              else OVERHEAT_GRADIENT_GREEN if "🟢" in banner_advice.advice
              else "linear-gradient(90deg, #475569 0%, #64748b 100%)")
        st.markdown(
            f'<div style="background:{bg};padding:14px 20px;border-radius:10px;'
            f'color:#fff;margin-bottom:10px">'
            f'<div style="font-size:13px;opacity:0.85">金价红绿灯:{verdict_label}'
            f' · 代表 β(中位 60d):{rep_b_str}</div>'
            f'<div style="font-size:18px;font-weight:700;margin-top:4px">{banner_advice.advice}</div>'
            f'<div style="font-size:12px;opacity:0.9;margin-top:4px">'
            f'📐 仓位倍数:×{banner_advice.position_multiplier:.2f}  ·  '
            f'{banner_advice.rationale}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 3. 主图 — 金股 ETF vs 黄金 ETF 归一化叠加(180d)
    st.markdown("#### 归一化净值对比 · 金股 ETF vs 黄金 ETF(180 天)")
    prices = _stock_etf_prices_cached(db_mtime, days=180)
    gold_prices = _etf_prices_cached(db_mtime, days=180)
    if not prices.empty and not gold_prices.empty:
        try:
            import plotly.graph_objects as go
            fig = go.Figure()
            # 黄金 ETF 518880(基准,粗灰线)
            g518 = gold_prices[gold_prices["etf_code"] == "518880"].sort_values("date")
            if not g518.empty:
                base = g518["close"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=g518["date"], y=g518["close"] / base * 100,
                    mode="lines", name="518880 黄金 ETF(基准)",
                    line=dict(color="#fbbf24", width=3, dash="dot"),
                ))
            # 4 只金股 ETF(细线)
            colors = ["#dc2626", "#7c3aed", "#0ea5e9", "#10b981"]
            for i, code in enumerate(master["etf_code"]):
                sub = prices[prices["etf_code"] == code].sort_values("date")
                if sub.empty:
                    continue
                base = sub["close"].iloc[0]
                name = master.loc[master["etf_code"] == code, "etf_name"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=sub["date"], y=sub["close"] / base * 100,
                    mode="lines", name=f"{code} {name}",
                    line=dict(color=colors[i % len(colors)], width=1.8),
                ))
            fig.update_layout(
                height=360, hovermode="x unified",
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="归一化净值(基期 = 100)",
                legend=dict(orientation="h", y=1.08, font=dict(size=10)),
            )
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"主图渲染失败:{e}")
    else:
        st.info("价格数据不足,跑 `fetch_gold_stock_etf.py --years 1` 补数据。")

    # 4. 横评表格 + 个性化决策卡
    st.markdown("#### 4 只金股 ETF 横评 + 个性化决策")

    rows = []
    for _, etf in master.iterrows():
        code = etf["etf_code"]
        b = beta_map.get(code, {})
        sub = prices[prices["etf_code"] == code].sort_values("date") if not prices.empty else pd.DataFrame()
        # 1y 涨跌 = 期末/期初 - 1(本视图只有 180d,故展示 180d 涨跌)
        chg_pct = None
        if len(sub) >= 2:
            chg_pct = (sub["close"].iloc[-1] / sub["close"].iloc[0] - 1) * 100

        beta_60d = b.get("beta_60d")
        r2_60d = b.get("r_squared_60d")
        advice = None
        if _OVERHEAT_AVAILABLE:
            try:
                advice = _stock_etf_advice(verdict_id, beta_60d, r_squared=r2_60d)
            except Exception:
                advice = None

        rows.append({
            "代码": code,
            "名称": etf["etf_name"],
            "交易所": etf["exchange"],
            "费率(%)": etf["fee_rate"],
            "180d 涨跌(%)": chg_pct,
            "β_30d": b.get("beta_30d"),
            "β_60d": beta_60d,
            "β_180d": b.get("beta_180d"),
            "R²_60d": b.get("r_squared_60d"),
            "建议": advice.advice if advice else "—",
            "仓位 ×": advice.position_multiplier if advice else None,
        })

    df_view = pd.DataFrame(rows)
    st.dataframe(
        df_view,
        width="stretch", hide_index=True,
        column_config={
            "费率(%)": st.column_config.NumberColumn(format="%.2f"),
            "180d 涨跌(%)": st.column_config.NumberColumn(format="%+.2f"),
            "β_30d": st.column_config.NumberColumn(format="%.2f"),
            "β_60d": st.column_config.NumberColumn(format="%.2f"),
            "β_180d": st.column_config.NumberColumn(format="%.2f"),
            "R²_60d": st.column_config.NumberColumn(format="%.3f",
                help="60d 回归拟合优度;>0.7 = β 可信"),
            "仓位 ×": st.column_config.NumberColumn(format="×%.2f"),
        },
    )

    # 4 张决策卡(每只一张)
    cols = st.columns(len(master))
    for i, row in enumerate(rows):
        with cols[i]:
            mult = row["仓位 ×"]
            mult_str = f"×{mult:.2f}" if isinstance(mult, (int, float)) else "—"
            border_color = ("#dc2626" if "🔴" in (row["建议"] or "")
                            else "#fbbf24" if "🟡" in (row["建议"] or "")
                            else "#10b981" if "🟢" in (row["建议"] or "")
                            else "#64748b")
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border:1px solid {border_color};background:rgba(100,116,139,0.05);'
                f'margin-bottom:6px;height:140px">'
                f'<div style="font-size:11px;color:#888">{row["交易所"]} · '
                f'β_60d {_format_beta(row["β_60d"])}</div>'
                f'<div style="font-size:15px;font-weight:700;margin-top:2px">{row["代码"]}</div>'
                f'<div style="font-size:12px;color:#555;margin-top:2px">{row["名称"]}</div>'
                f'<div style="font-size:11px;color:#444;margin-top:6px">{row["建议"]}</div>'
                f'<div style="font-size:11px;color:#666;margin-top:4px">仓位倍数:{mult_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # 5. β 滚动副图(可选展开)
    with st.expander("📊 β 滚动窗口对照(30 / 60 / 180 天)", expanded=False):
        if betas:
            beta_df = pd.DataFrame([{
                "代码": b["etf_code"], "β_30d": b.get("beta_30d"),
                "β_60d": b.get("beta_60d"), "β_180d": b.get("beta_180d"),
                "R²_60d": b.get("r_squared_60d"), "样本量": b.get("n_obs_max"),
                "as_of": b.get("as_of"),
            } for b in betas])
            st.dataframe(beta_df, width="stretch", hide_index=True,
                column_config={
                    "β_30d": st.column_config.NumberColumn(format="%.3f"),
                    "β_60d": st.column_config.NumberColumn(format="%.3f"),
                    "β_180d": st.column_config.NumberColumn(format="%.3f"),
                    "R²_60d": st.column_config.NumberColumn(format="%.3f"),
                })
            st.caption(
                "📌 **β 窗口选择**:30d 灵敏但噪声大,180d 稳健但慢;"
                "**默认看 60d**(平衡)。R² < 0.5 时 β 不稳定,建议持有观望。"
            )
        else:
            st.info("β 数据未生成(金股 ETF 数据不足或表未建)。")

    # 6. 教育卡(双向性提醒)
    with st.expander("💡 金股 ETF vs 黄金 ETF · 怎么用", expanded=False):
        st.markdown("""
**为什么金股 ETF 是「放大版黄金 ETF」**

金股 ETF 跟踪的是金矿/有色金属股票指数,而非实物黄金:
- 矿企经营杠杆(固定成本不变,金价涨 → 利润放大)
- 市场情绪杠杆(金价涨 → 资金涌入金股板块)

**β = 1.5 意味着什么?**
- 金价涨 10% → 金股 ETF 涨 ~15%
- 金价**跌** 10% → 金股 ETF **跌** ~15% ⚠️
- **β 不是单向利好**,放大上涨也放大下跌

**操作矩阵(已自动应用于上方决策卡)**

| 金价 verdict | β < 2.0 | β ≥ 2.0 |
|---|---|---|
| 🟢 加仓 / 小幅加仓 | 🟢 加金股放大 ×1.2 | 🟡 谨慎加金股 ×1.0 |
| 🟡 持有观望 | 🟡 持金股观望 ×1.0 | 🟡 持金股观望 ×1.0 |
| 🔴 暂停 / 局部过热 | 🔴 减金股(同步)×0.8 | 🔴 优先减金股 ×0.6 |

**仓位倍数怎么用**

黄金大类目标 X%(由范式投票决定,看好默认 20%)。金股建议仓位 =
**X × default_stock_share × multiplier**(yaml: `default_stock_share_in_gold = 0.30`)。

举例:战略目标 20%,multiplier=1.2 → 金股建议 20% × 30% × 1.2 = **7.2%** 黄金大类;
其中 12.8% 走实物 ETF(518880 等),7.2% 走金股 ETF。

**金股 ETF 的特性局限**

- **R² 不稳**:本视图 4 只 ETF R² 在 0.26 - 0.997 不等 — 因为部分 ETF 跟踪的是
  "沪深港金属矿业"而非纯金股,与黄金的相关性会偏离
- **样本短**:多数金股 ETF 2024 后上市,长窗口 β(180d)样本可能 < 180
- **不要做主动选股**:本视图聚焦 ETF 层;紫金/山东黄金等单股是公司分析 Tab 的事
""")


