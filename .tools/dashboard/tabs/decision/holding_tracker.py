"""持仓跟踪与决策 UI — 段 2 主渲染。

入口:render(snap)
- 单仓选择器(selectbox + 上一只 / 下一只)
- 标题行:{name} ({ticker}) · {流派标签}
- 4 卡片:长期买入指标 / 买入金字塔 / 卖出方式 / ⚡ 短期建议
- 行动摘要(bordered container)
- 底部 3 按钮:录入决策 / 执行清仓 / 取消观察(待接入决策日志)
"""
from __future__ import annotations

import streamlit as st

from dashboard.valuation.fair_price import compute_fair_range
from tabs.decision.holding_guide import compute_holding_guide


_STATE_KEY = "holding_tracker_v1_idx"


def _fmt_price(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"¥{v:,.{decimals}f}"


def _fmt_pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}%"


def _fmt_pct_ratio(v: float | None, decimals: int = 1) -> str:
    """0-1 比例 → '85.0%'。"""
    if v is None:
        return "—"
    return f"{v*100:.{decimals}f}%"


def render(snap) -> None:
    st.markdown("### 📖 持仓跟踪与决策")

    # 候选 rows
    candidates = [r for r in snap.rows if r.status in ("active", "watch")]
    if not candidates:
        st.info("当前没有 active / watch 持仓,无法跟踪。")
        return

    # session_state 索引
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = 0
    idx = st.session_state[_STATE_KEY]
    if idx >= len(candidates):
        idx = 0
        st.session_state[_STATE_KEY] = 0

    # 顶栏:selectbox + 上一只 + 下一只
    col_sel, col_prev, col_next = st.columns([6, 1, 1])
    options = [f"{r.name} ({r.ticker})" for r in candidates]
    with col_sel:
        choice = st.selectbox(
            "选择持仓",
            options=options,
            index=idx,
            key="holding_tracker_v1_select",
            label_visibility="collapsed",
        )
        new_idx = options.index(choice)
        if new_idx != idx:
            st.session_state[_STATE_KEY] = new_idx
            idx = new_idx
    with col_prev:
        if st.button("⬅️ 上一只", width="stretch", key="holding_tracker_v1_prev"):
            st.session_state[_STATE_KEY] = (idx - 1) % len(candidates)
            st.rerun()
    with col_next:
        if st.button("➡️ 下一只", width="stretch", key="holding_tracker_v1_next"):
            st.session_state[_STATE_KEY] = (idx + 1) % len(candidates)
            st.rerun()

    row = candidates[idx]

    # 算 fair + guide
    try:
        fair = compute_fair_range(row.ticker, row.name)
    except Exception as exc:  # 防御:数据库异常时降级
        st.warning(f"合理价计算失败:{exc}")
        fair = None
    guide = compute_holding_guide(row, snap, fair)

    # 标题
    st.markdown(f"#### 📖 {row.name} ({row.ticker}) · {guide.school_label} · {guide.price_source}")

    # 数据降级提示
    if not guide.verified and guide.notes:
        st.info(" / ".join(guide.notes))

    # 单元切换（参照"选股"页面 radio 预设样式）
    UNIT_LONG = "🎯 长期买入指标"
    UNIT_PYRAMID = "🪜 买入金字塔"
    UNIT_SELL = "💰 卖出方式"
    UNIT_SHORT = "⚡ 短期建议"
    UNIT_SUMMARY = "📝 行动摘要"
    units = [UNIT_LONG, UNIT_PYRAMID, UNIT_SELL, UNIT_SHORT, UNIT_SUMMARY]

    with st.container(border=True):
        st.markdown("**🧭 操作单元(选一个看详情)**")
        unit = st.radio(
            "操作单元",
            options=units,
            horizontal=True,
            key=f"holding_tracker_v1_unit_{row.ticker}",
            label_visibility="collapsed",
        )

        st.markdown("---")

        if unit == UNIT_LONG:
            st.markdown(f"### {UNIT_LONG}")
            st.caption(f"流派:{guide.school_label} · 价格口径:{guide.price_source} · 决定买不买 / 买多便宜")
            k1, k2, k3 = st.columns(3)
            k1.metric("合理价", _fmt_price(guide.fair_price))
            k2.metric("安全买入线", _fmt_price(guide.buy_line),
                      help="合理价 × 安全边际系数")
            k3.metric("当前价", _fmt_price(guide.current_price),
                      delta=_fmt_pct(guide.gap_to_low_pct),
                      delta_color="inverse",
                      help="当前 vs 买入线;负值=已进入买入区")
            st.markdown(f"**档位:** {guide.verdict_label}")
            if guide.position_range_label:
                st.markdown(f"**仓位范围:** {guide.position_range_label}")
            if guide.position_status:
                st.markdown(f"**仓位判断:** {guide.position_status}")
            if guide.manual_band_note:
                st.caption(f"人工备注:{guide.manual_band_note}")
            with st.expander("▼ 方法论详情(展开看公式)", expanded=False):
                if guide.price_source == "人工最终确认":
                    st.markdown(
                        "- **当前采用人工最终确认价格区间**:来自 `portfolio.yaml.price_band`\n"
                        "- 操作优先级高于模型估算价\n"
                        "- 缺少人工区间时,才回退 Graham / 林奇 / 巴菲特口径"
                    )
                elif guide.rule == "graham":
                    st.markdown(
                        "- **合理价** = Graham Number = √(22.5 × EPS × BVPS)\n"
                        "- **安全买入线** = 合理价 × 0.85\n"
                        "- **档位**:基于 5 档 verdict(极度低估 / 低估 / 合理 / 高估 / 极度高估)"
                    )
                elif guide.rule == "lynch":
                    st.markdown(
                        "- **合理价** ≈ EPS × (增长率 + 1)(PEG=1 时)\n"
                        "- **安全买入线** = 合理价 × 0.9\n"
                        "- 当前若无增长率数据,回落 Graham 占位"
                    )
                else:
                    st.markdown(
                        "- **合理价** ≈ PE 历史中位数 × 当前 EPS(占位:Graham × 1.1)\n"
                        "- **安全买入线** = 合理价 × 0.9\n"
                        "- 巴菲特派更看护城河,价格只是参考"
                    )

        elif unit == UNIT_PYRAMID:
            st.markdown(f"### {UNIT_PYRAMID}")
            st.caption("分档建仓 — 价格越跌,买得越多")
            if not guide.pyramid:
                st.warning("无金字塔数据(合理价缺失)")
            else:
                hits = sum(1 for *_, h in guide.pyramid if h)
                st.metric("已触发档位", f"{hits} / {len(guide.pyramid)}")
                for tier, price, weight, hit in guide.pyramid:
                    mark = "✅" if hit else "⏳"
                    cur = guide.current_price
                    gap = f"(当前距此档 {(cur-price)/price*100:+.1f}%)" if cur else ""
                    st.markdown(
                        f"- {mark} **{tier}** · {_fmt_price(price)} · 仓位 {weight*100:.0f}% {gap}"
                    )
            with st.expander("▼ 金字塔配比说明", expanded=False):
                st.markdown(
                    "- 一档买入线触发 → 第 1 笔小仓试探\n"
                    "- 价格继续下跌 → 二档、三档加大投入\n"
                    "- 价值派(3 档 3/4/3 配比)/ 防御派(2 档 5/5)"
                )

        elif unit == UNIT_SELL:
            st.markdown(f"### {UNIT_SELL}")
            st.caption("什么时候该走 — 止盈 / 止损 / 再平衡")
            k1, k2, k3 = st.columns(3)
            k1.metric("止盈价", _fmt_price(guide.take_profit))
            k2.metric("止损规则", guide.stop_loss_rule or "—")
            k3.metric("再平衡", guide.rebalance_rule or "—")
            with st.expander("▼ 卖出规则说明", expanded=False):
                if guide.rule == "graham":
                    st.markdown(
                        "- **止盈**:合理价 × 1.5(明显高估)\n"
                        "- **止损**:F-Score 跌破 4(基本面恶化)\n"
                        "- **再平衡**:偏离目标权重 > 5%"
                    )
                elif guide.rule == "lynch":
                    st.markdown(
                        "- **止盈**:PEG > 2 或增速降至 10% 以下\n"
                        "- **故事破裂**:六类分类降级 / 行业逻辑变化"
                    )
                else:
                    st.markdown(
                        "- **过热减仓**:PE 分位 > 85% 触发部分减仓\n"
                        "- 巴菲特派一般不轻易卖出,除非护城河瓦解"
                    )

        elif unit == UNIT_SHORT:
            st.markdown(f"### {UNIT_SHORT}")
            st.caption("市场短期信号 — 现在该不该动")
            k1, k2, k3 = st.columns(3)
            k1.metric("PE 分位(10y)", _fmt_pct_ratio(guide.pe_pct))
            k2.metric("过热阈值", _fmt_pct_ratio(guide.overheat_threshold))
            if guide.pe_pct is not None:
                gap_pp = (guide.overheat_threshold - guide.pe_pct) * 100
                k3.metric("距过热", f"{gap_pp:+.1f}pp",
                          delta_color="off")
            else:
                k3.metric("距过热", "—")
            st.markdown(f"### 建议动作:**{guide.short_term_action}**")
            with st.expander("▼ 短期信号说明", expanded=False):
                st.markdown(
                    "- **PE 分位 ≥ 85%** → 过热区,评估减仓\n"
                    "- **PE 分位 ≤ 30%** → 冷区,考虑加仓\n"
                    "- **30%-85%** → 持有观望"
                )

        else:  # 行动摘要
            st.markdown(f"### {UNIT_SUMMARY}")
            st.caption("综合长期 / 短期信号,给出 3-5 条具体动作")
            st.markdown(guide.summary_md)

    # 底部 3 按钮
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("📋 录入决策", width="stretch",
                     key=f"holding_tracker_v1_log_{row.ticker}"):
            st.toast("待接入决策日志", icon="🚧")
    with b2:
        if st.button("🚪 执行清仓", width="stretch",
                     key=f"holding_tracker_v1_exit_{row.ticker}"):
            st.toast("待接入决策日志", icon="🚧")
    with b3:
        if st.button("❌ 取消观察", width="stretch",
                     key=f"holding_tracker_v1_drop_{row.ticker}"):
            st.toast("待接入决策日志", icon="🚧")


__all__ = ["render"]
