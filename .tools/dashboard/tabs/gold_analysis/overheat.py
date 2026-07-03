"""黄金 sub-tab ⑥ 短期过热扫描(v2.4 step-D)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


# ─── ⑥ 短期过热扫描(v2.4 step-D)──────────────────────────────────────


def _render_overheat(overheat: dict | None, paradigm_actives: int,
                     db_mtime: float) -> None:
    st.markdown("### ⑥ 短期过热扫描(防追高)")
    st.caption(
        "📚 用途:在三大范式「长期主导身份」之上,补一层周/日级"
        "「短期热度」,回答 *今天该不该追?是建仓窗口还是暂停?* · "
        "阈值见 [.tools/rules/gold_overheat.yaml](#)"
    )

    if not overheat or overheat.get("_error"):
        msg = "引擎未启用,请确认 PyYAML 已装,且 `.tools/rules/gold_overheat.yaml` 路径正确"
        if overheat and overheat.get("_error"):
            msg = f"引擎执行失败:{overheat['_error']}"
        st.warning(f"⚠️ {msg}")
        return

    # ── 综合判定卡 ──
    red, yel, gre = (overheat.get("red_count", 0),
                     overheat.get("yellow_count", 0),
                     overheat.get("green_count", 0))
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("🔴 红灯", red, help="过热警示信号数(0-6)")
    with col_b:
        st.metric("🟡 黄灯", yel, help="局部偏热信号数")
    with col_c:
        st.metric("🟢 绿灯", gre, help="健康信号数")
    with col_d:
        st.metric("综合判定", overheat.get("verdict_label", "—").split(" ")[-1],
                  help=overheat.get("verdict_action", ""))

    # 大趋势联动建议
    try:
        advice = (_overheat_advice(overheat["verdict_id"], paradigm_actives)
                  if _OVERHEAT_AVAILABLE else "")
    except Exception:
        advice = ""
    if advice:
        st.success(f"💡 **联动建议**(范式 {paradigm_actives}/3 激活 + "
                   f"短期 {overheat['verdict_label']}):{advice}")

    st.divider()

    # ── 6 信号矩阵 ──
    st.markdown("#### 6 信号矩阵 × 3 档红绿灯")
    signals = overheat.get("signals", [])
    if not signals:
        st.info("信号数据缺失")
        return

    rows = []
    for sig in signals:
        cv = sig.get("current_value")
        unit = sig.get("unit", "") or ""
        if cv is None:
            cur_str = "—"
        else:
            try:
                cur_str = f"{float(cv):.2f}{unit}"
            except (TypeError, ValueError):
                cur_str = str(cv)
        rows.append({
            "状态": sig.get("emoji", "⚪"),
            "信号": sig["name"],
            "当前值": cur_str,
            "阈值": sig.get("threshold_str", ""),
            "来源": sig.get("source", "—"),
            "说明": sig.get("note", ""),
        })
    df_sig = pd.DataFrame(rows)
    st.dataframe(df_sig, width="stretch", hide_index=True)

    # ── 历史回看时序图(可切换 1 年 / 5 年)──
    col_h1, col_h2 = st.columns([4, 1])
    with col_h2:
        period = st.radio(
            "周期",
            options=["近 1 年", "近 5 年"],
            index=0,
            key="overheat_history_period",
            horizontal=True,
            label_visibility="collapsed",
        )
    days_map = {"近 1 年": 365, "近 5 年": 365 * 5}
    hist_days = days_map[period]
    with col_h1:
        st.markdown(f"#### 历史回看({period})")
    hist = _overheat_history_cached(db_mtime, days=hist_days)
    if hist.empty:
        st.info("尚无过热历史快照 — 跑 `python3 .tools/dashboard/overheat_engine.py "
                "--backfill --years 5` 一次性回填,之后 update.py 每周累积一行")
    else:
        try:
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Bar(x=hist["date"], y=hist["red_count"],
                                 name="🔴 红", marker_color="#dc2626"))
            fig.add_trace(go.Bar(x=hist["date"], y=hist["yellow_count"],
                                 name="🟡 黄", marker_color="#f59e0b"))
            fig.add_trace(go.Bar(x=hist["date"], y=hist["green_count"],
                                 name="🟢 绿", marker_color="#10b981"))
            fig.update_layout(
                barmode="stack", height=320,
                margin=dict(l=20, r=20, t=20, b=20),
                hovermode="x unified",
                yaxis_title="信号数(0-6)",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, width="stretch")
            st.caption(f"📊 共 {len(hist)} 个采样点(每日 1 个)· 🔴 高位 = 历史过热警示 · "
                       "可对比 GOLD_USD_DERIVED 时序看是否对应回调")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")

    # ── 仓位走廊(短期热度 × 战略目标 × 当前持仓 → 建议)──
    with st.expander("📐 仓位走廊 · 短期热度 → 当前合理仓位", expanded=True):
        try:
            from valuation.corridor import compute_corridor, load_corridor_config
            cfg = load_corridor_config()
            default_x = float(cfg.get("default_strategic_pct", 20.0))
            default_pw = int(cfg.get("default_period_weeks", 26))

            col_x, col_y, col_n = st.columns(3)
            with col_x:
                strategic_pct = st.number_input(
                    "战略目标 X (%)", min_value=0.0, max_value=50.0,
                    value=float(st.session_state.get("gold_strategic_pct", default_x)),
                    step=0.5, key="gold_strategic_pct",
                    help="范式投票 + 康波决定的黄金目标占比上限。看好默认 20%,看空默认 5%。",
                )
            with col_y:
                current_pct = st.number_input(
                    "当前持仓 Y (%)", min_value=0.0, max_value=50.0,
                    value=float(st.session_state.get("gold_current_pct", 10.0)),
                    step=0.5, key="gold_current_pct",
                    help="你账户中黄金资产(实物 + ETF + 期货)占总资产的比例。",
                )
            with col_n:
                period_weeks = st.number_input(
                    "建仓/减仓周期(周)", min_value=4, max_value=104,
                    value=int(st.session_state.get("gold_period_weeks", default_pw)),
                    step=1, key="gold_period_weeks",
                    help="匀速建仓或减仓的总周数。默认 26(半年);减仓信号紧迫时可缩到 8。",
                )

            verdict_id = overheat.get("verdict_id", "add")
            corridor = compute_corridor(
                verdict_id, strategic_pct, current_pct,
                period_weeks=int(period_weeks),
            )

            # 走廊可视化:水平条
            tier_map = {
                "add": "🟢 add",
                "add_caution": "🟢 caution",
                "hold": "🟡 hold",
                "pause_partial": "🔴 partial",
                "pause": "🔴 pause",
            }
            decision_color = {"add": "#10b981", "hold": "#f59e0b", "reduce": "#dc2626"}
            color = decision_color.get(corridor.decision, "#64748b")

            col_l, col_r = st.columns([2, 1])
            with col_l:
                import plotly.graph_objects as go
                fig = go.Figure()
                # 走廊带(浅灰)
                fig.add_shape(type="rect",
                              x0=corridor.lower_pct, x1=corridor.upper_pct,
                              y0=0.3, y1=0.7,
                              fillcolor="rgba(148, 163, 184, 0.25)",
                              line=dict(width=0))
                # 走廊中线(目标)
                fig.add_vline(x=corridor.target_pct, line_dash="dash",
                              line_color="#475569",
                              annotation_text=f"目标 {corridor.target_pct:.1f}%",
                              annotation_position="top")
                # 战略上限 X
                fig.add_vline(x=corridor.strategic_pct, line_dash="dot",
                              line_color="#1e3a8a",
                              annotation_text=f"战略 X={corridor.strategic_pct:.0f}%",
                              annotation_position="bottom")
                # 当前持仓点
                fig.add_trace(go.Scatter(
                    x=[corridor.current_pct], y=[0.5],
                    mode="markers+text",
                    marker=dict(size=20, color=color, line=dict(color="white", width=2)),
                    text=[f"Y={corridor.current_pct:.1f}%"],
                    textposition="bottom center",
                    showlegend=False,
                ))
                fig.update_layout(
                    height=180,
                    margin=dict(l=20, r=20, t=30, b=30),
                    xaxis=dict(range=[0, max(corridor.strategic_pct + 5, corridor.current_pct + 3)],
                               title="占总资产比例 %"),
                    yaxis=dict(visible=False, range=[0, 1]),
                    plot_bgcolor="white",
                )
                st.plotly_chart(fig, width="stretch")

            with col_r:
                arrow = "▲" if corridor.decision == "add" else (
                    "▼" if corridor.decision == "reduce" else "→")
                st.markdown(
                    f"### {arrow} {corridor.decision_label}\n\n"
                    f"**当前档**:{tier_map.get(verdict_id, verdict_id)}({corridor.discount:.0%} × X)\n\n"
                    f"**走廊**:{corridor.lower_pct:.1f}% ~ {corridor.upper_pct:.1f}%\n\n"
                    f"**本周建议**:{corridor.weekly_step_pct:+.2f}% / 周\n\n"
                    f"_({corridor.tier_label})_"
                )

            # 决策细节
            if corridor.decision == "add":
                gap = corridor.upper_pct - corridor.current_pct
                weeks = max(1, int(round(gap / max(corridor.weekly_step_pct, 1e-6))))
                st.success(
                    f"✅ 当前 Y={corridor.current_pct:.1f}% 低于走廊下界 {corridor.lower_pct:.1f}% — "
                    f"按每周 {corridor.weekly_step_pct:+.2f}% 加仓,约 {weeks} 周达上界 {corridor.upper_pct:.1f}%。"
                )
            elif corridor.decision == "reduce":
                gap = corridor.current_pct - corridor.lower_pct
                weeks = max(1, int(round(gap / max(abs(corridor.weekly_step_pct), 1e-6))))
                st.error(
                    f"⚠️ 当前 Y={corridor.current_pct:.1f}% 高于走廊上界 {corridor.upper_pct:.1f}% — "
                    f"按每周 {corridor.weekly_step_pct:+.2f}% 减仓,约 {weeks} 周降到下界 {corridor.lower_pct:.1f}%。"
                )
            else:
                st.info(
                    f"⏸ 当前 Y={corridor.current_pct:.1f}% 在走廊 "
                    f"{corridor.lower_pct:.1f}% ~ {corridor.upper_pct:.1f}% 内 — 持有不动。"
                )

            st.caption(
                "💡 短期热度档位变了 → 走廊重画 → 重新比较 Y 与新走廊 → 决定本周是加 / 持 / 减。"
                "仓位倾向不是单次步长,而是阶梯式上限折扣。"
            )
        except Exception as e:
            st.warning(f"仓位走廊渲染失败:{e}")

    # ── 大趋势 × 短期联动矩阵 ──
    with st.expander("💡 大趋势 × 短期 8 种联动操作建议", expanded=False):
        st.markdown("""
| 大趋势(范式投票)| 短期判定 | 操作建议 |
|---|---|---|
| 看好(≥2/3) | 🟢 加仓窗口 | ✅ **加仓**(双绿,大胆建仓) |
| 看好         | 🟢 可小幅加仓 | ✅ **小幅加仓**(温和买入) |
| 看好         | 🟡 持有观望 | 🟡 **持有不动**(等过热释放再加) |
| 看好         | 🔴 局部过热 | ⚠️ **暂停建仓**(局部冷却) |
| 看好         | 🔴 暂停建仓 | ⚠️ **暂停建仓**(过热警示,大趋势好也不追高)|
| 看空(≤1/3) | 🟢 加仓窗口 | 🟢 **反弹机会**(高风险,大趋势空但已超卖)|
| 看空         | 🔴 暂停建仓 | 🔻 **减仓信号**(双红,高位风险) |

**核心原则**:大趋势看好 ≠ 任何时点都能进。**追高被套**是黄金投资最常见损失模式。
""")


