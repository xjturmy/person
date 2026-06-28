"""区块 A · 看结论:雪花 + 同行业建议卡 + 优势/短板 Top3 + 一句话定位。"""
from __future__ import annotations

import sys
from pathlib import Path

from ._helpers import _section_banner, _dim_explanation


def render() -> None:
    st.markdown('<div id="block-a"></div>', unsafe_allow_html=True)
    # ═══ 区块 A · 看结论(雪花 + 优势短板)═══
    st.markdown(
        _section_banner("A", "🎯", "一眼看结论", "雪花图 · 优势短板 Top3 · 一句话定位"),
        unsafe_allow_html=True,
    )
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")

    # ─── 区块 A-0:💡 vs 同行业建议卡(Phase C)─────────────────────
    if selected_ticker:
        try:
            _here = str(Path(__file__).resolve().parents[1])
            if _here not in sys.path:
                sys.path.insert(0, _here)
            import peers.advisor as _pa
            _adv = _pa.advise(selected_ticker, name=selected)
            if _adv is not None and _adv.n_peers > 0:
                st.markdown(_pa.render_hero_card_html(_adv), unsafe_allow_html=True)
        except Exception as _pa_e:
            st.caption(f"⚠️ 同行建议引擎调用失败:{_pa_e}")

    # ─── V8 顶部:综合评分 + 雪花图(SWS 风格)+ 股价叠加全局 toggle ─
    score = company_score(selected_ticker, DB_MTIME) if selected_ticker else None
    head_left, head_mid = st.columns([1.0, 2.0])
    with head_left:
        st.markdown(f"### 🏢 {selected}")
        if score is not None and score.overall is not None:
            st.metric("★ 综合评分", f"{score.overall:.1f} / 100", help="6 维加权(估值/盈利/成长/现金流/安全/策略)")
            st.markdown(f"#### {score.overall_badge} {score.category or '—'}")
        else:
            st.caption("(评分不可用 — 数据缺失或 ticker 未映射)")
        st.toggle(
            "📈 在所有时序图叠加股价(右轴)", value=False, key="overlay_price",
            help="勾选后,公司详情下方的指标时序图会在右轴叠加 prices 表收盘价",
        )
        if decisions_db is not None:
            if st.button("➕ 一键补录决策", key="quick_add_decision",
                         help="带入当前公司,切换到「📝 决策日志」tab 即可填写表单"):
                st.session_state["dec_company"] = selected
                st.session_state["pending_decision_for"] = selected
                st.toast(f"已带入「{selected}」 → 切到「📝 决策日志」tab 即可", icon="➕")
    with head_mid:
        if score is not None:
            st.plotly_chart(render_radar(score), use_container_width=True)
        else:
            st.info("无法生成雪花图")

    # ─── 雷达下方:优势/短板 Top3 + 详解(每条 1-2 句话)──────────
    if score is not None:
        valid = [
            (sc.DIM_LABEL.get(k, k),
             score.dims[k].score,
             score.dims[k].badge or "⚪",
             score.dims[k].note or "",
             score.dims[k].raw)
            for k in SCORE_DIM_ORDER
            if score.dims.get(k) and score.dims[k].score is not None
        ]
        top = sorted(valid, key=lambda x: x[1], reverse=True)[:3]
        bot = sorted(valid, key=lambda x: x[1])[:3]

        col_top, col_bot = st.columns(2)
        with col_top:
            st.markdown("##### 🟢 优势 Top3 · 为什么强?")
            for label, val, badge, note, raw in top:
                with st.container(border=True):
                    st.markdown(
                        f"{badge} **{label}** · `{val:.0f}/100`"
                        + (f" · <span style='color:#6B7280;font-size:13px'>{note}</span>" if note else ""),
                        unsafe_allow_html=True,
                    )
                    explain = _dim_explanation(label, raw, val)
                    if explain:
                        st.caption(explain)
        with col_bot:
            st.markdown("##### 🔴 短板 Top3 · 为什么弱?")
            for label, val, badge, note, raw in bot:
                with st.container(border=True):
                    st.markdown(
                        f"{badge} **{label}** · `{val:.0f}/100`"
                        + (f" · <span style='color:#6B7280;font-size:13px'>{note}</span>" if note else ""),
                        unsafe_allow_html=True,
                    )
                    explain = _dim_explanation(label, raw, val)
                    if explain:
                        st.caption(explain)

        # 一句话定位
        if top and bot:
            t_label, _, _, t_note, _ = top[0]
            b_label, _, _, b_note, _ = bot[0]
            if t_label != b_label:
                st.caption(
                    f"💡 一句话定位:**{t_label}** 极强({t_note.split('·')[0].strip() if t_note else '—'})"
                    f",**{b_label}** 偏弱({b_note.split('·')[0].strip() if b_note else '—'})"
                )

        st.caption("横向对比同行 ➡ [Block C 行业横评](#block-c)")

    # ─── 区块 A 收尾:🎯 下季度合理价格区间(多模型加权)─────────────
    if selected_ticker:
        _render_price_range_card(selected_ticker, selected)


def _render_price_range_card(ticker: str, name: str) -> None:
    """渲染下季度合理价格区间卡:三模型公允价 + 区间标尺 + verdict。"""
    # 优先读预计算 bundle.price_range(<5ms);缺失降级 live 计算。
    pr = None
    try:
        import analytics_store as _store
        pr = _store.price_range(ticker)
    except Exception:
        pr = None

    # lynch_type 在 if 块外(下方 caption)也会引用,必须无条件初始化,
    # 否则走预计算分支(pr 非 None)时 lynch_type 未定义 → UnboundLocalError。
    lynch_type = None
    if pr is None:
        try:
            from valuation.price_range import compute_next_quarter_range
        except Exception as e:
            st.caption(f"⚠️ price_range 加载失败:{e}")
            return
        # 取 lynch_type 用于权重 — 只算当前这一家(按 mtime 缓存),
        # 不再对全市场跑 score_lynch_classifier_all(load_all())(实测 17.5s)。
        try:
            from masters.lynch.classifier import lynch_type_of
            lynch_type = lynch_type_of(ticker, DB_MTIME)
        except Exception:
            pass
        pr = compute_next_quarter_range(ticker, name=name, lynch_type=lynch_type)

    st.markdown("---")
    st.markdown("### 🎯 下季度合理价格区间")
    st.caption(
        "三模型加权聚合:Graham(账面安全) · PEG=1(成长公允) · Gordon DDM(股息折现)。"
        + (f" · 林奇分类:`{lynch_type}`" if lynch_type else " · 林奇分类:未知,使用等权")
    )

    if pr.floor is None or pr.ceiling is None:
        st.warning(f"{pr.verdict_label}({'; '.join(pr.notes) or '三模型均不可得'})")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📉 下沿 floor", f"¥{pr.floor:,.2f}", help="三模型公允价最小值")
    col2.metric("🎯 中枢 mid", f"¥{pr.mid:,.2f}", help="按林奇分类加权后的目标价")
    col3.metric("📈 上沿 ceiling", f"¥{pr.ceiling:,.2f}", help="三模型公允价最大值")
    if pr.current_price is not None:
        deviation = (pr.current_price - pr.mid) / pr.mid * 100
        col4.metric("当前价",
                    f"¥{pr.current_price:,.2f}",
                    delta=f"{deviation:+.1f}% vs 中枢",
                    delta_color="inverse")
    else:
        col4.metric("当前价", "—")

    # 一句话 verdict
    if pr.current_price is not None:
        st.markdown(
            f"#### {pr.verdict_label} · 当前 ¥{pr.current_price:.2f} ∈ "
            f"[¥{pr.floor:.2f}, ¥{pr.ceiling:.2f}]"
        )

    # 三模型明细表
    import pandas as _pd
    rows = []
    for m in pr.models:
        rows.append({
            "模型": m.name,
            "公允价": f"¥{m.fair_price:,.2f}" if m.fair_price is not None else "—",
            "权重": f"{m.weight*100:.0f}%" if m.weight > 0 else "—",
            "校验": "✓" if m.verified else "—",
            "说明": m.note,
        })
    st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if pr.notes:
        with st.expander("⚠️ 降级说明"):
            for n in pr.notes:
                st.caption("• " + n)

